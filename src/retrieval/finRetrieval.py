"""
finRetrieval.py — GraphRAG 검색 모듈
=====================================
app.py에서 import하여 Gradio 챗봇과 연동합니다.

사용법:
    from src.retrieval.finRetrieval import graphrag

    response = graphrag.search(query_text="삼성전자 AI 서비스는?")
    print(response.answer)
"""

import os

import dotenv
import neo4j
from neo4j_graphrag.embeddings.openai import OpenAIEmbeddings
from neo4j_graphrag.generation import GraphRAG, RagTemplate
from neo4j_graphrag.llm import OpenAILLM
from neo4j_graphrag.retrievers import (
    Text2CypherRetriever,
    ToolsRetriever,
    VectorCypherRetriever,
    VectorRetriever,
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
    RETURN s.name, s.description""",
    """USER INPUT: 삼성전자가 개발 중인 AI 기술은?
CYPHER QUERY:
    MATCH (c:AICompany {name:"삼성전자"})-[:DEVELOPS]->(t:AITechnology)
    RETURN t.name, t.description""",
    """USER INPUT: 어떤 기업이 LLM 기술을 개발하나요?
CYPHER QUERY:
    MATCH (c:AICompany)-[:DEVELOPS]->(t:AITechnology)
    WHERE t.name CONTAINS "언어모델" OR t.name CONTAINS "LLM"
    RETURN c.name, t.name""",
    """USER INPUT: 금융이나 핀테크 분야에 기술을 적용하고 있는 기업들은 어디야?
CYPHER QUERY:
    MATCH (c:AICompany)-[:DEVELOPS]->(t)-[:USED_IN]->(f:AIField)
    WHERE f.name CONTAINS "금융" OR f.name CONTAINS "핀테크"
    RETURN DISTINCT c.name, t.name, f.name""",
    """USER INPUT: 금융AI 분야에 가장 적극적인 기업 TOP 3와 대표 서비스
CYPHER QUERY:
    MATCH (c:AICompany)-[:DEVELOPS]->(s)-[:USED_IN]->(f:AIField)
    WHERE f.name CONTAINS "금융" OR f.name CONTAINS "핀테크"
    RETURN DISTINCT c.name, s.name, f.name
    LIMIT 3""",
    """USER INPUT: 최근 AI 관련 뉴스 기사를 요약해줘
CYPHER QUERY:
    MATCH (a:Article)-[:HAS_CHUNK]->(c:Content)
    RETURN a.title, a.url, a.published_date, c.chunk
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
    template="""당신은 AI 기술 트렌드 분석 전문가입니다.
반드시 아래 제공된 [컨텍스트(Neo4j 지식 그래프 검색 결과)]에 기반해서만 답변하세요.

⚠️ [엄격한 주의사항]
1. 컨텍스트에 없는 기업, 서비스, 기술은 절대 언급하지 마세요. (해외 기업도 컨텍스트에 있으면 요약 가능합니다)
2. 질문에 해당하는 정보가 컨텍스트에 없다면 지어내지 말고, "현재 수집된 최신 뉴스 데이터에는 관련 정보가 없습니다"라고 정직하게 답변하세요.
3. 근거로 제시할 URL은 오직 컨텍스트에 포함된 실제 기사의 URL만 사용하며, 'example.com' 같은 가짜 링크는 절대 생성하지 마세요.
4. 취업 지원 목적의 기업 분석은 구체적으로 작성하고, "최근 뉴스 기사 요약" 등의 일반 트렌드 질문은 핵심 내용을 잘 정리하여 브리핑해주세요.

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
        
        vector_retriever = VectorRetriever(
            driver=driver,
            index_name=INDEX_NAME,
            embedder=embedder,
        )
        
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
                vector_retriever.convert_to_tool(
                    name="vector_retriever",
                    description="뉴스 본문의 의미(내용) 유사도 기반 검색. AI 기술·서비스 관련 텍스트를 찾을 때 사용.",
                ),
                vector_cypher_retriever.convert_to_tool(
                    name="vectorcypher_retriever",
                    description="벡터 검색 후 해당 기사에서 언급된 기업·기술·서비스 그래프를 함께 반환. 기업 AI 트렌드 분석에 최적.",
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
