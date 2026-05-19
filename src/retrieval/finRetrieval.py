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
RETURN
    node.chunk             AS chunk,
    article.title          AS article_title,
    article.url            AS article_url,
    article.published_date AS article_date,
    collect(DISTINCT company.name) AS companies,
    collect(DISTINCT tech.name)    AS technologies,
    collect(DISTINCT svc.name)     AS services,
    collect(DISTINCT field.name)   AS fields
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
]

# ──────────────────────────────────────────
# 3. ToolsRetriever + GraphRAG 조립
# ──────────────────────────────────────────

from typing import Any

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

답변은 대중이나 취업 준비생이 실질적으로 트렌드를 깊이 있게 파악하고 자소서/면접 등에 즉각 활용할 수 있도록, 아래의 [프리미엄 4단계 레이아웃] 구조를 엄격히 준수하여 매우 체계적이고 깔끔한 마크다운 양식으로 정성스럽게 브리핑해 주세요.

---

### 📊 [핵심 요약 및 트렌드 인사이트]
- **한 줄 요약**: 해당 트렌드의 핵심 요점을 단 한 줄로 명료하게 요약합니다.
- **주요 인사이트**: 이 이슈가 현재 IT/AI 및 금융 핀테크 업계 전체에 던지는 핵심 화두가 무엇인지 명시합니다.

### 🔍 [상세 이슈 및 핵심 팩트 분석]
컨텍스트를 근거로 구체적인 사실 관계를 일목요연한 글머리기호(bullet points)로 상세히 정리합니다.
- 예: 이슈의 전개 과정, 관련 기업들의 구체적인 움직임, 발생하고 있는 현상(예: 전력난, 반발, 기술적 한계 등).

### 💡 [시사점 및 지원동기/자소서 활용 가이드]
이 뉴스가 갖는 거시적 의미와 핀테크/금융 대기업 채용 준비생이 서류/면접에 활용할 수 있는 차별화된 전략 포인트를 도출합니다.
- **업계 시사점**: 기술 발전과 사회적 수용성(ESG, 인프라, 전력망 확보 등) 간의 균형적 관점 제시.
- **실전 활용 Tip**: 지원동기나 면접 답변 구성 시 해당 트렌드를 어떻게 본인의 역량(예: 지속 가능한 기술 기획, 신뢰받는 AI 설계 등)과 연계하여 풀어낼 수 있을지에 대한 맞춤형 가이드라인 제공.

### 📰 [출처 및 근거 자료]
- 컨텍스트에 포함된 기사의 실물 제목과 링크를 마크다운 링크 형식으로 투명하고 정밀하게 표기합니다.
  - 예: * [기사 제목](기사 URL) - 보도일자/언론사

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

    def _init_once(self) -> None:
        if self._graphrag is not None:
            return
            
        # OpenAI 클라이언트 및 임베더 지연 초기화 (CI 크래시 방지)
        rag_llm = OpenAILLM(model_name="gpt-4o", model_params={"temperature": 0})
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
            llm=rag_llm,
            neo4j_schema=_get_schema(driver),
            examples=_examples,
        )
        
        tools_retriever = ToolsRetriever(
            driver=driver,
            llm=rag_llm,
            tools=[
                vector_cypher_retriever.convert_to_tool(
                    name="vector_retriever",
                    description="뉴스 본문의 키워드 및 의미(내용) 유사도 기반 검색. 뉴스 기사의 실제 출처(기사 제목, URL)와 관련 기업/기술/서비스 그래프를 함께 분석해 답변할 때 사용.",
                ),
                text2cypher_retriever.convert_to_tool(
                    name="text2cypher_retriever",
                    description="자연어를 Cypher로 변환. 특정 기업 서비스 목록, 기술 보유 기업 등 구조적 질의, 또는 '최근 기사 요약' 같은 최신 전체 뉴스 검색에 사용.",
                ),
            ],
        )
        
        hybrid_retriever = HybridFallbackRetriever(
            tools_retriever=tools_retriever,
            fallback_retriever=vector_cypher_retriever,
        )
        
        self._graphrag = GraphRAG(
            llm=rag_llm,
            retriever=hybrid_retriever,
            prompt_template=_prompt_template,
        )

    def search(self, *args: Any, **kwargs: Any) -> Any:
        self._init_once()
        assert self._graphrag is not None
        return self._graphrag.search(*args, **kwargs)

    def __getattr__(self, name: str) -> Any:
        self._init_once()
        return getattr(self._graphrag, name)


# app.py에서 이 객체를 직접 import하여 사용합니다 (이때는 DB 연결을 시도하지 않음).
graphrag = LazyGraphRAG()
