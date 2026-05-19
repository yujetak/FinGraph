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
from neo4j_graphrag.llm import OpenAILLM
from neo4j_graphrag.embeddings.openai import OpenAIEmbeddings
from neo4j_graphrag.retrievers import (
    VectorRetriever,
    VectorCypherRetriever,
    Text2CypherRetriever,
    ToolsRetriever,
)
from neo4j_graphrag.generation import RagTemplate, GraphRAG

dotenv.load_dotenv()

# ──────────────────────────────────────────
# 1. DB / LLM / Embedder 초기화
# ──────────────────────────────────────────

URI      = os.getenv("NEO4J_URI", "neo4j://localhost:7687")
AUTH     = (os.getenv("NEO4J_USERNAME", "neo4j"), os.getenv("NEO4J_PASSWORD", "password"))
driver   = neo4j.GraphDatabase.driver(URI, auth=AUTH)

rag_llm  = OpenAILLM(model_name="gpt-4o", model_params={"temperature": 0})
embedder = OpenAIEmbeddings(model="text-embedding-3-small")

INDEX_NAME = "content_vector_index"

# ──────────────────────────────────────────
# 2. Retriever 세 종류 초기화
# ──────────────────────────────────────────

# (1) 본문 청크 의미 유사도 검색
vector_retriever = VectorRetriever(
    driver=driver,
    index_name=INDEX_NAME,
    embedder=embedder,
)

# (2) 벡터 검색 후 그래프 탐색 (기업·기술·서비스 함께 반환)
_retrieval_query = """
MATCH (content:Content)<-[:HAS_CHUNK]-(article:Article)
OPTIONAL MATCH (article)-[:MENTIONS]->(company:AICompany)
OPTIONAL MATCH (company)-[:DEVELOPS]->(tech:AITechnology)
OPTIONAL MATCH (company)-[:DEVELOPS]->(svc:AIService)
OPTIONAL MATCH (article)-[:MENTIONS]->(field:AIField)
RETURN
    content.chunk          AS chunk,
    article.title          AS article_title,
    article.url            AS article_url,
    article.published_date AS article_date,
    collect(DISTINCT company.name) AS companies,
    collect(DISTINCT tech.name)    AS technologies,
    collect(DISTINCT svc.name)     AS services,
    collect(DISTINCT field.name)   AS fields
ORDER BY article.published_date DESC
LIMIT 3
"""

vector_cypher_retriever = VectorCypherRetriever(
    driver=driver,
    index_name=INDEX_NAME,
    retrieval_query=_retrieval_query,
    embedder=embedder,
)

# (3) 자연어 → Cypher 자동 변환 검색
def _get_schema() -> str:
    with driver.session() as s:
        nodes = s.run(
            "CALL db.schema.nodeTypeProperties() "
            "YIELD nodeType, propertyName "
            "RETURN nodeType, collect(propertyName) as props"
        ).data()
        rels = s.run(
            "MATCH (n)-[r]->(m) "
            "RETURN DISTINCT labels(n)[0] as src, type(r) as rel, labels(m)[0] as tgt "
            "LIMIT 30"
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

    """USER INPUT: 최근 AI 관련 기사 5개
CYPHER QUERY:
MATCH (a:Article)-[:MENTIONS]->(:AICompany)
RETURN DISTINCT a.article_id, a.title, a.url, a.published_date
ORDER BY a.published_date DESC LIMIT 5""",

    """USER INPUT: 어떤 기업이 LLM 기술을 개발하나요?
CYPHER QUERY:
MATCH (c:AICompany)-[:DEVELOPS]->(t:AITechnology)
WHERE t.name CONTAINS "언어모델" OR t.name CONTAINS "LLM"
RETURN c.name, t.name""",
]

text2cypher_retriever = Text2CypherRetriever(
    driver=driver,
    llm=rag_llm,
    neo4j_schema=_get_schema(),
    examples=_examples,
)

# ──────────────────────────────────────────
# 3. ToolsRetriever + GraphRAG 조립
# ──────────────────────────────────────────

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
            description="자연어를 Cypher로 변환. 특정 기업 서비스 목록, 기술 보유 기업 등 구조적 질의에 사용.",
        ),
    ],
)

_prompt_template = RagTemplate(
    template="""당신은 AI 기술 트렌드 분석 전문가입니다.
취업 준비생이 기업 지원 동기를 작성할 수 있도록 해당 기업의 AI 서비스·기술 트렌드를 명확하게 설명해 주세요.

질문: {query_text}

검색된 정보:
{context}

답변 지침:
1. 기업이 개발 중인 AI 기술과 서비스를 구체적으로 명시하세요.
2. 뉴스 기사 제목과 URL을 근거로 포함하세요.
3. 지원자가 어떤 서비스에 어떻게 기여할 수 있는지 시사점을 1~2줄 추가하세요.
4. 검색 결과에 없는 내용은 추측하지 마세요.

답변:""",
    expected_inputs=["context", "query_text"],
)

# app.py에서 이 객체를 직접 import하여 사용합니다.
graphrag = GraphRAG(
    llm=rag_llm,
    retriever=tools_retriever,
    prompt_template=_prompt_template,
)
