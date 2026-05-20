"""
finRetrieval.py — GraphRAG 검색 모듈
=====================================
app.py에서 import하여 Gradio 챗봇과 연동합니다.

사용법:
    from src.retrieval.finRetrieval import graphrag

    response = graphrag.search(query_text="삼성전자 AI 서비스는?")
    print(response.answer)
"""

import logging
import os
from dataclasses import dataclass
from typing import Any

# Neo4j DBMS server warning (Deprecated vector queryNodes 등) 로깅 차단
logging.getLogger("neo4j").setLevel(logging.ERROR)
logging.getLogger("neo4j.notifications").setLevel(logging.ERROR)

import dotenv
import neo4j
from neo4j_graphrag.embeddings.openai import OpenAIEmbeddings
from neo4j_graphrag.generation import GraphRAG, RagTemplate
from neo4j_graphrag.llm import OpenAILLM
from neo4j_graphrag.retrievers import (
    Text2CypherRetriever,
    ToolsRetriever,
    VectorCypherRetriever,
)

dotenv.load_dotenv()


@dataclass
class HybridResult:
    """GraphRAG 또는 일반 지식 기반 통합 응답 결과"""

    answer: str            # 최종 답변 문자열
    mode: str              # "graph": 그래프 검색 기반 | "general": GPT-4o-mini 일반 지식 기반
    retriever_result: Any = None  # RetrieverResult (mode="graph"일 때만 유효)


def get_neo4j_driver() -> neo4j.Driver:
    uri = os.getenv("NEO4J_URI", "neo4j://localhost:7687")
    client_id = os.getenv("NEO4J_CLIENT_ID")
    client_secret = os.getenv("NEO4J_CLIENT_SECRET")
    
    if client_id and client_secret:
        try:
            d = neo4j.GraphDatabase.driver(uri, auth=(client_id, client_secret))
            d.verify_connectivity()
            return d
        except Exception:
            pass  # Fallback to Username/Password
            
    username = os.getenv("NEO4J_USERNAME", "neo4j")
    password = os.getenv("NEO4J_PASSWORD", "password")
    d = neo4j.GraphDatabase.driver(uri, auth=(username, password))
    d.verify_connectivity()
    return d


INDEX_NAME = "content_vector_index"

# ──────────────────────────────────────────
# 2. Retriever 관련 상수 및 설정
# ──────────────────────────────────────────

_retrieval_query = """
MATCH (node)<-[:HAS_CHUNK]-(article:Article)
OPTIONAL MATCH (article)-[:MENTIONS]->(company:AICompany)
OPTIONAL MATCH (company)-[:DEVELOPS]->(tech:AITechnology)
OPTIONAL MATCH (company)-[:DEVELOPS]->(svc:AIService)
OPTIONAL MATCH (article)-[:MENTIONS]->(field:AIField)

// 동일 기업/기술/서비스를 언급하는 관련 기사까지 확장 탐색 (횡단 검색)
OPTIONAL MATCH (related_article:Article)
WHERE related_article <> article
  AND (
    EXISTS { (related_article)-[:MENTIONS]->(:AICompany)<-[:MENTIONS]-(article) }
    OR EXISTS { (related_article)-[:MENTIONS]->(:AITechnology)<-[:MENTIONS]-(article) }
    OR EXISTS { (related_article)-[:MENTIONS]->(:AIService)<-[:MENTIONS]-(article) }
  )
WITH
    node, article, company, tech, svc, field,
    collect(DISTINCT related_article.title)[..3] AS related_titles,
    collect(DISTINCT related_article.url)[..3]   AS related_urls
RETURN
    node.chunk             AS chunk,
    article.title          AS article_title,
    article.url            AS article_url,
    article.published_date AS article_date,
    collect(DISTINCT company.name) AS companies,
    collect(DISTINCT tech.name)    AS technologies,
    collect(DISTINCT svc.name)     AS services,
    collect(DISTINCT field.name)   AS fields,
    related_titles         AS related_article_titles,
    related_urls           AS related_article_urls
"""


def _get_schema(driver: neo4j.Driver) -> str:
    with driver.session() as s:
        nodes = s.run(
            "CALL db.schema.nodeTypeProperties() "
            "YIELD nodeType, propertyName "
            "RETURN nodeType, collect(propertyName) as props"
        ).data()
        rels = s.run(
            "MATCH (n)-[r]->(m) RETURN DISTINCT labels(n)[0] as src, type(r) as rel, labels(m)[0] as tgt LIMIT 30"
        ).data()
    txt = "=== Neo4j Schema ===\n노드:\n"
    for n in nodes:
        txt += f"- {n['nodeType']}: {n['props']}\n"
    txt += "\n관계:\n"
    for r in rels:
        txt += f"- ({r['src']})-[:{r['rel']}]->({r['tgt']})\n"
    return txt


_examples = [
    """USER INPUT: 카카오의 AI 서비스 목록을 알려주세요
CYPHER QUERY:
    MATCH (c:AICompany {name:"카카오"})-[:DEVELOPS]->(s:AIService)
    OPTIONAL MATCH (a:Article)-[:MENTIONS]->(s)
    RETURN s.name AS name, s.description AS description, a.title AS article_title, a.url AS article_url""",
    """USER INPUT: 삼성전자가 개발 중인 AI 기술은?
CYPHER QUERY:
    MATCH (c:AICompany {name:"삼성전자"})-[:DEVELOPS]->(t:AITechnology)
    OPTIONAL MATCH (a:Article)-[:MENTIONS]->(t)
    RETURN t.name AS name, t.description AS description, a.title AS article_title, a.url AS article_url""",
    """USER INPUT: 어떤 기업이 LLM 기술을 개발하나요?
CYPHER QUERY:
    MATCH (c:AICompany)-[:DEVELOPS]->(t:AITechnology)
    WHERE t.name CONTAINS "언어모델" OR t.name CONTAINS "LLM"
    OPTIONAL MATCH (a:Article)-[:MENTIONS]->(t)
    RETURN c.name AS company_name, t.name AS tech_name, a.title AS article_title, a.url AS article_url""",
    """USER INPUT: 금융이나 핀테크 분야에 기술을 적용하고 있는 기업들은 어디야?
CYPHER QUERY:
    MATCH (c:AICompany)-[:DEVELOPS]->(t)-[:USED_IN]->(f:AIField)
    WHERE f.name CONTAINS "금융" OR f.name CONTAINS "핀테크"
    OPTIONAL MATCH (a:Article)-[:MENTIONS]->(t)
    RETURN DISTINCT c.name AS company_name, t.name AS tech_name, f.name AS field_name, a.title AS article_title, a.url AS article_url""",
    """USER INPUT: 금융AI 분야에 가장 적극적인 기업 TOP 3와 대표 서비스
CYPHER QUERY:
    MATCH (c:AICompany)-[:DEVELOPS]->(s)-[:USED_IN]->(f:AIField)
    WHERE f.name CONTAINS "금융" OR f.name CONTAINS "핀테크"
    OPTIONAL MATCH (a:Article)-[:MENTIONS]->(s)
    RETURN DISTINCT c.name AS company_name, s.name AS service_name, f.name AS field_name, a.title AS article_title, a.url AS article_url
    LIMIT 3""",
    """USER INPUT: 최근 AI 관련 뉴스 기사를 요약해줘
CYPHER QUERY:
    MATCH (a:Article)-[:HAS_CHUNK]->(c:Content)
    RETURN a.title AS title, a.url AS url, a.published_date AS published_date, c.chunk AS chunk
    ORDER BY a.published_date DESC
    LIMIT 3""",
    """USER INPUT: 최근 가장 관심이 높은 AI 기술이 뭐야?
CYPHER QUERY:
    MATCH (a:Article)-[:MENTIONS]->(t:AITechnology)
    OPTIONAL MATCH (c:AICompany)-[:DEVELOPS]->(t)
    WITH t, count(DISTINCT a) AS article_count, collect(DISTINCT c.name)[..3] AS companies, collect(DISTINCT a.title)[..3] AS article_titles, collect(DISTINCT a.url)[..3] AS article_urls
    ORDER BY article_count DESC
    RETURN t.name AS tech_name, t.description AS description, article_count, companies, article_titles, article_urls
    LIMIT 5""",
    """USER INPUT: AI 기술 트렌드를 분석해줘
CYPHER QUERY:
    MATCH (a:Article)-[:MENTIONS]->(t:AITechnology)
    OPTIONAL MATCH (c:AICompany)-[:DEVELOPS]->(t)
    WITH t, count(DISTINCT a) AS article_count, collect(DISTINCT c.name)[..3] AS companies, collect(DISTINCT a.title)[..2] AS article_titles, collect(DISTINCT a.url)[..2] AS article_urls
    ORDER BY article_count DESC
    RETURN t.name AS tech_name, article_count, companies, article_titles, article_urls
    LIMIT 5""",
    """USER INPUT: 현대차 또는 로봇 관련 AI 뉴스 알려줘
CYPHER QUERY:
    MATCH (a:Article)-[:MENTIONS]->(c:AICompany)
    WHERE c.name CONTAINS '현대' OR c.name CONTAINS '로봇'
    OPTIONAL MATCH (a)-[:MENTIONS]->(t:AITechnology)
    OPTIONAL MATCH (a)-[:MENTIONS]->(s:AIService)
    RETURN a.title AS article_title, a.url AS article_url, a.published_date AS article_date,
           collect(DISTINCT c.name) AS companies, collect(DISTINCT t.name) AS technologies, collect(DISTINCT s.name) AS services
    ORDER BY a.published_date DESC LIMIT 5""",
]

# ──────────────────────────────────────────
# 3. ToolsRetriever + GraphRAG 조립
# ──────────────────────────────────────────


from neo4j_graphrag.retrievers.base import Retriever
from neo4j_graphrag.types import RawSearchResult, RetrieverResult


class HybridFallbackRetriever(Retriever):
    VERIFY_NEO4J_VERSION = False

    def __init__(self, tools_retriever: Retriever, fallback_retriever: Retriever) -> None:
        self.tools_retriever = tools_retriever
        self.fallback_retriever = fallback_retriever
        super().__init__(driver=tools_retriever.driver)

    def get_search_results(self, *args: Any, **kwargs: Any) -> RawSearchResult:
        return RawSearchResult(records=[])

    def search(self, query_text: str = "", **kwargs: Any) -> RetrieverResult:
        res = self.tools_retriever.search(query_text=query_text, **kwargs)
        if not res or not res.items:
            return self.fallback_retriever.search(query_text=query_text, **kwargs)
        return res


class CustomRagTemplate(RagTemplate):
    EXPECTED_INPUTS = ["context", "query_text"]

    def format(self, query_text: str, context: str, examples: str = "") -> str:
        # 부모 시그니처(MyPy) 준수 및 Vulture 미사용 변수 검사 방어
        _ = examples
        return self._format(query_text=query_text, context=context)


_prompt_template = CustomRagTemplate(
    template="""당신은 AI 및 핀테크 기술 트렌드 전문가이자, 취업 준비생의 역량 분석을 돕는 전략 컨설턴트입니다.
반드시 아래 제공된 [컨텍스트(Neo4j 지식 그래프 검색 결과)]에 기반해서만 답변하고, 컨텍스트에 근거하지 않은 사실을 지어내거나 가상의 링크(example.com 등)를 절대 생성하지 마세요.

답변은 대중이나 취업 준비생이 실질적으로 트렌드를 깊이 있게 파악하고 자소서/면접 등에 즉각 활용할 수 있도록, 아래의 [고정 브리핑 보고서 포맷]을 **토씨 하나 틀리지 않고 엄격히 준수**하여 매우 체계적이고 깔끔한 마크다운 양식으로 정성스럽게 브리핑해 주세요.

★ [중요 - 가독성 및 개행 규칙]:
각 주요 섹션(###) 사이에는 무조건 빈 줄을 2줄 이상 추가하고, 모든 개별 목록 기호(- 및 **) 항목 사이사이에도 반드시 1줄 이상의 빈 줄(개행)을 삽입하여 시각적 가독성을 극대화해 주세요.

---

# 📋 [FinGraph AI 분석 브리핑]

### 1. 📊 한 줄 요약 & 핵심 트렌드

- **한 줄 요약**: [해당 트렌드의 핵심 요점을 단 한 줄로 명료하게 요약]

- **주요 인사이트**: [이 이슈가 현재 IT/AI 및 금융 핀테크 업계 전체에 던지는 핵심 화두 기재]


### 2. 🔍 상세 분석 및 팩트 정리

[컨텍스트에 기록된 실제 사실 관계들을 근거로 구체적 사실을 정리]

- **이슈 전개**: [구체적인 이슈 발생 배경 및 진행 경과]

- **기업 동향**: [관련 핵심 기업들의 실물 비즈니스 움직임 및 대응 행보. 컨텍스트에 여러 기업/기술이 있다면 모두 언급]

- **기술 트렌드**: [컨텍스트에 등장하는 핵심 AI 기술들을 비교/분류하여 전체 트렌드 흐름 분석]

- **인프라/사회적 요인**: [전력망 부족, 대중적 불안감, 하드웨어적 제약 사항 등 핵심 요인]


### 3. 💡 취업/자소서/면접 실전 가이드

[지원자가 면접이나 자기소개서에서 차별화된 통찰을 보여줄 수 있는 방법 제시]

- **금융/IT 업계 시사점**: [거시적인 파급효과와 지속가능성 관점 제시]

- **실전 자소서/면접 활용 Tip**: [지원동기나 역량 기술서 작성 시 본인의 역량과 어떻게 연계하여 풀어낼지에 대한 맞춤 가이드]


### 📰 4. 근거 뉴스 출처 (GraphRAG 검색 기사)

> 컨텍스트에 실제로 존재하는 기사 URL만 기재하고, 존재하지 않는 기사는 절대 지어내지 마세요.
> 검색된 기사가 있는 경우 아래 형식으로 열거하고, 없으면 이 섹션을 생략하세요.
>
> 예시:
> - *[기사 제목](기사 URL)* — 보도일자

---

질문: {query_text}

[컨텍스트]
{context}

답변:""",
    expected_inputs=["context", "query_text"]
)


class LazyGraphRAG:
    """임포트 시점에 DB 연결을 방지하고 실제 호출될 때 GraphRAG 인스턴스를 초기화하는 지연 평가 프록시"""

    def __init__(self) -> None:
        self._graphrag: Any = None
        self._hybrid_retriever: Any = None  # 품질 평가용 직접 접근 가능한 리트리버
        self._rag_llm: Any = None           # 일반 지식 답변 생성용 LLM

    def _init_once(self) -> None:
        if self._graphrag is not None:
            return
            
        # OpenAI 클라이언트 및 임베더 지연 초기화 (CI 크래시 방지)
        self._rag_llm = OpenAILLM(model_name="gpt-4o-mini", model_params={"temperature": 0})
        embedder = OpenAIEmbeddings(model="text-embedding-3-small")

        driver = get_neo4j_driver()
        
        vector_cypher_retriever = VectorCypherRetriever(
            driver=driver,
            index_name=INDEX_NAME,
            retrieval_query=_retrieval_query,
            embedder=embedder,
        )
        
        text2cypher_retriever = Text2CypherRetriever(
            driver=driver,
            llm=self._rag_llm,
            neo4j_schema=_get_schema(driver),
            examples=_examples,
        )
        
        tools_retriever = ToolsRetriever(
            driver=driver,
            llm=self._rag_llm,
            tools=[
                vector_cypher_retriever.convert_to_tool(
                    name="vector_retriever",
                    description=(
                        "뉴스 본문 의미 유사도 기반 검색 + 연결된 엔티티(기업·기술·서비스·분야) 관계 그래프 탐색. "
                        "특정 주제/기업/기술에 대해 뉴스 기사 및 관련 그래프 관계를 함께 분석할 때 사용. "
                        "예: '현대차 AI 뉴스', '특정 기술의 적용 사례'."
                    ),
                ),
                text2cypher_retriever.convert_to_tool(
                    name="text2cypher_retriever",
                    description=(
                        "자연어를 Neo4j Cypher 쿼리로 변환하여 그래프 구조를 집계·탐색. "
                        "'가장 많이 언급된 기술', '트렌드 분석', '특정 기업의 서비스 목록', "
                        "'어떤 기업이 X 기술을 개발하나', '최근 뉴스 요약' 등 "
                        "집계(COUNT/ORDER BY)나 구조적 관계 질의에 반드시 사용."
                    ),
                ),
            ],
        )

        self._hybrid_retriever = HybridFallbackRetriever(
            tools_retriever=tools_retriever,
            fallback_retriever=vector_cypher_retriever,
        )

        self._graphrag = GraphRAG(
            llm=self._rag_llm,
            retriever=self._hybrid_retriever,
            prompt_template=_prompt_template,
        )

    def _is_context_sufficient(self, query_text: str, history: list, retriever_result: Any) -> bool:
        """검색된 컨텍스트가 질문 및 이전 대화 흐름에 실질적으로 도움이 되는 금융/기술 뉴스 데이터인지 GPT-4o-mini로 판단"""
        if retriever_result is None:
            return False
        if not hasattr(retriever_result, "items") or not retriever_result.items:
            return False
        total_content = " ".join(
            getattr(item, "content", "") for item in retriever_result.items
        ).strip()
        if len(total_content) < 100:
            return False

        # GPT-4o-mini 기반 지능적 자가 진단 (이전 대화 히스토리 및 질문의 맥락 결합 판정)
        try:
            assert self._rag_llm is not None
            context_snippet = total_content[:800]

            # 이전 대화 히스토리의 맥락 요약 추출 (최근 3개 메시지)
            normalized_history = self._normalize_history(history)
            history_summary = "없음"
            if normalized_history:
                history_summary = "\n".join(
                    f"- {msg['role']}: {msg['content'][:150]}" 
                    for msg in normalized_history[-3:]
                )

            routing_prompt = (
                "당신은 금융/기술 트렌드 RAG 시스템의 지능형 라우터입니다.\n"
                "사용자의 [현재 질문] 및 [최근 대화 히스토리]가 아래 제공된 [검색된 뉴스 데이터]와 의미적으로 밀접하게 연관되어 있고, "
                "해당 데이터를 기반으로 질문에 실제 구체적이고 신뢰할 수 있는 답변을 제공할 수 있는지 평가하세요.\n\n"
                "특히, 현재 질문이 '그거에 대해 좀 더 설명해줘'나 '자소서 팁을 더 다듬어줘'와 같은 후속 대화형 질문일 경우, "
                "[최근 대화 히스토리]에 명시된 주요 금융/기술 트렌드 주제(예: 삼성전자 AI, 카카오 AI 등)가 "
                "아래 뉴스 데이터의 핵심 내용과 일치하는지 종합적으로 고려해야 합니다.\n\n"
                "만약 질문 및 대화 맥락이 아래 뉴스 데이터와 전혀 무관한 일반 상식, 일상적인 대화, 수학, 예술 등 "
                "지식 그래프(뉴스 데이터베이스)에 없는 주제의 질문이라면 반드시 'NO'라고 답해야 합니다.\n"
                "뉴스 팩트 데이터를 결합하여 올바른 답변을 작성할 수 있는 맥락이라면 'YES', 그렇지 않다면 'NO'라고만 답하세요.\n\n"
                f"[최근 대화 히스토리]\n{history_summary}\n\n"
                f"[현재 질문]\n{query_text}\n\n"
                f"[검색된 뉴스 데이터]\n{context_snippet}\n\n"
                "판정 (YES 또는 NO로만 답변):"
            )
            # 아주 빠르고 저렴한 단일 토큰 YES/NO 응답 생성
            response = self._rag_llm.invoke(
                input=routing_prompt,
                model_params={"temperature": 0, "max_tokens": 5}
            )
            decision = str(response.content).strip().upper()
            return "YES" in decision
        except Exception:
            # 예외 발생 시 안전을 위해 기존의 기본 길이 기반 판정으로 폴백
            return len(total_content) >= 100

    def _normalize_history(self, history: list) -> list:
        """Gradio 히스토리(dict 또는 tuple 형식)를 LLM message_history 형식으로 정규화"""
        normalized: list = []
        for msg in history:
            if isinstance(msg, dict) and "role" in msg and "content" in msg:
                normalized.append({"role": msg["role"], "content": str(msg["content"])})
            elif isinstance(msg, (list, tuple)) and len(msg) == 2:
                if msg[0]:
                    normalized.append({"role": "user", "content": str(msg[0])})
                if msg[1]:
                    normalized.append({"role": "assistant", "content": str(msg[1])})
        return normalized

    def _generate_general_answer(self, query_text: str, history: list) -> str:
        """그래프 검색 결과 없이 GPT-4o-mini 일반 지식으로 답변 생성 (대화 히스토리 반영)"""
        assert self._rag_llm is not None
        system_prompt = (
            "당신은 AI 및 핀테크 기술 트렌드 전문가이자, 취업 준비생의 역량 분석을 돕는 전략 컨설턴트입니다.\n"
            "현재 FinGraph 지식 그래프(Neo4j GraphRAG)에서 관련 뉴스 기사를 찾지 못했습니다.\n"
            "이전 대화 맥락을 충분히 반영하고, GPT-4o-mini의 일반 학습 데이터에 기반하여 최선을 다해 전문적으로 답변해 주세요.\n\n"
            "[중요 지침]\n"
            "- 실제 존재하지 않는 뉴스 링크, 날짜, 가짜 URL을 절대 생성하지 마세요.\n"
            "- 가능하다면 취업 준비생이 면접/자소서에 활용할 수 있는 실질적인 인사이트를 포함해 주세요.\n"
            "- 답변이 일반 AI 학습 데이터 기반임을 숨기지 말고 자연스럽게 언급하며 시작하세요."
        )
        normalized_history = self._normalize_history(history)
        response = self._rag_llm.invoke(
            input=query_text,
            message_history=normalized_history,
            system_instruction=system_prompt,
        )
        return str(response.content)

    def search_with_fallback(self, query_text: str, history: list) -> HybridResult:
        """GraphRAG 검색 -> 컨텍스트 품질 평가 -> 일반 지식 Fallback 통합 메서드.

        Args:
            query_text: 사용자 질문 텍스트
            history:    이전 대화 히스토리 (Gradio 형식)

        Returns:
            HybridResult: 답변, 모드("graph"|"general"), RetrieverResult
        """
        self._init_once()
        assert self._hybrid_retriever is not None
        assert self._graphrag is not None

        # 1단계: LLM 호출 없이 DB 쿼리만으로 검색 실행
        retriever_result = self._hybrid_retriever.search(query_text=query_text)

        # 2단계: 컨텍스트 품질 평가 후 라우팅
        if self._is_context_sufficient(query_text, history, retriever_result):
            # 3a. 그래프 기반 -> GraphRAG 브리핑 답변 생성
            rag_result = self._graphrag.search(query_text=query_text)
            return HybridResult(
                answer=rag_result.answer,
                mode="graph",
                retriever_result=rag_result.retriever_result,
            )
        else:
            # 3b. 일반 지식 기반 -> 히스토리 포함 GPT-4o-mini 직접 호출
            answer = self._generate_general_answer(query_text, history)
            return HybridResult(answer=answer, mode="general", retriever_result=None)

    def search(self, *args: Any, **kwargs: Any) -> Any:
        self._init_once()
        assert self._graphrag is not None
        return self._graphrag.search(*args, **kwargs)

    def __getattr__(self, name: str) -> Any:
        self._init_once()
        return getattr(self._graphrag, name)


# app.py에서 이 객체를 직접 import하여 사용합니다 (이때는 DB 연결을 시도하지 않음).
graphrag = LazyGraphRAG()
