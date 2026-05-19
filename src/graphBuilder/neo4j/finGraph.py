"""
finGraph.py — AI 뉴스 지식 그래프 빌더
=====================================
실행 순서:
  1. finScrapping.py 실행 → Articles_*.xlsx 생성
  2. 이 파일 실행 → Neo4j에 엔티티/관계/벡터 적재

노드:   AICompany, AITechnology, AIService, AIField, Article, Content, Media
관계:   DEVELOPS, INVESTS_IN, PARTNERS_WITH, APPLIES, USED_IN, RELATED_TO,
        MENTIONS, HAS_CHUNK, PUBLISHED
"""

import glob
import json
import os
from typing import Dict, List, TypedDict

import dotenv
import neo4j
import pandas as pd
from langchain_openai import ChatOpenAI
from langgraph.graph import END, StateGraph
from neo4j_graphrag.embeddings.openai import OpenAIEmbeddings
from neo4j_graphrag.indexes import create_vector_index
from neo4j_graphrag.llm import OpenAILLM

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
            pass
            
    username = os.getenv("NEO4J_USERNAME", "neo4j")
    password = os.getenv("NEO4J_PASSWORD", "password")
    try:
        d = neo4j.GraphDatabase.driver(uri, auth=(username, password))
        d.verify_connectivity()
        return d
    except Exception as e:
        import sys
        if "pytest" in sys.modules or os.getenv("GITHUB_ACTIONS") == "true":
            print(f"⚠️ [TEST/CI ENVIRONMENT] Neo4j connection failed at import time: {e}. (Proceeding with dummy None driver)")
            return None
        raise e


driver = get_neo4j_driver()

chat_llm = ChatOpenAI(model="gpt-4o-mini", temperature=0)
rag_llm = OpenAILLM(model_name="gpt-4o", model_params={"temperature": 0})
embedder = OpenAIEmbeddings(model="text-embedding-3-small")

INDEX_NAME = "content_vector_index"

# ──────────────────────────────────────────
# 1. LangGraph 파이프라인 정의 (엔티티/관계 추출)
# ──────────────────────────────────────────


class ArticleState(TypedDict):
    article_id: str
    title: str
    text: str
    is_ai_related: bool
    entities: List[Dict]
    relations: List[Dict]


def check_ai_relevance(state: ArticleState) -> ArticleState:
    """Node 1: AI 관련 여부 판별"""
    prompt = (
        "다음 기사가 AI(인공지능) 기술·기업·서비스와 관련 있으면 yes, 아니면 no로만 답하세요.\n\n"
        f"{state['text'][:400]}\n\n답변(yes/no):"
    )
    res = chat_llm.invoke(prompt)
    return {
        **state,
        "is_ai_related": str(res.content).strip().lower().startswith("yes"),
    }


def extract_entities(state: ArticleState) -> ArticleState:
    """Node 2: 엔티티 추출"""
    prompt = f"""다음 AI 뉴스에서 엔티티를 추출하세요.
엔티티 유형:
- AICompany: 기업/기관 (예: 삼성전자, OpenAI)
- AITechnology: AI 기술 (예: 대규모언어모델, 강화학습)
- AIService: 서비스/제품 (예: ChatGPT, HyperCLOVA X)
- AIField: 적용 분야 (예: 금융AI, AI 반도체)

제목: {state["title"]}
본문: {state["text"][:900]}

JSON으로만 응답:{{"entities":[{{"name":"...","type":"AICompany|AITechnology|AIService|AIField","description":"..."}}]}}"""
    res = chat_llm.invoke(prompt)
    try:
        raw = str(res.content).strip()
        if "```" in raw:
            raw = raw.split("```")[1].lstrip("json")
        entities = json.loads(raw).get("entities", [])
    except Exception:
        entities = []
    return {**state, "entities": entities}


def extract_relations(state: ArticleState) -> ArticleState:
    """Node 3: 관계 추출"""
    if not state["entities"]:
        return {**state, "relations": []}
    elist = "\n".join([f"- {e['name']} ({e['type']})" for e in state["entities"]])
    prompt = (
        f"엔티티 목록:\n{elist}\n\n"
        "관계 유형: DEVELOPS, INVESTS_IN, PARTNERS_WITH, APPLIES, USED_IN, RELATED_TO\n"
        f"본문: {state['text'][:700]}\n\n"
        '공으로만:{"relations":[{"source":"...","relation":"...","target":"..."}]}'
    )
    res = chat_llm.invoke(prompt)
    try:
        raw = str(res.content).strip()
        if "```" in raw:
            raw = raw.split("```")[1].lstrip("json")
        relations = json.loads(raw).get("relations", [])
        names = {e["name"] for e in state["entities"]}
        relations = [r for r in relations if r.get("source") in names and r.get("target") in names]
    except Exception:
        relations = []
    return {**state, "relations": relations}


def route_after_check(state: ArticleState) -> str:
    return "extract_entities" if state["is_ai_related"] else END


builder = StateGraph(ArticleState)
builder.add_node("check_ai", check_ai_relevance)
builder.add_node("extract_entities", extract_entities)
builder.add_node("extract_relations", extract_relations)
builder.set_entry_point("check_ai")
builder.add_conditional_edges("check_ai", route_after_check)
builder.add_edge("extract_entities", "extract_relations")
builder.add_edge("extract_relations", END)
pipeline = builder.compile()


# ──────────────────────────────────────────
# 2. Neo4j 스키마 초기화 및 적재 함수
# ──────────────────────────────────────────

ENTITY_TYPE_MAP = {
    "AICompany": "AICompany",
    "AITechnology": "AITechnology",
    "AIService": "AIService",
    "AIField": "AIField",
}


def setup_schema(tx) -> None:
    constraints = [
        "CREATE CONSTRAINT IF NOT EXISTS FOR (n:AICompany)    REQUIRE n.name IS UNIQUE",
        "CREATE CONSTRAINT IF NOT EXISTS FOR (n:AITechnology)  REQUIRE n.name IS UNIQUE",
        "CREATE CONSTRAINT IF NOT EXISTS FOR (n:AIService)     REQUIRE n.name IS UNIQUE",
        "CREATE CONSTRAINT IF NOT EXISTS FOR (n:AIField)       REQUIRE n.name IS UNIQUE",
        "CREATE CONSTRAINT IF NOT EXISTS FOR (n:Article)       REQUIRE n.article_id IS UNIQUE",
        "CREATE CONSTRAINT IF NOT EXISTS FOR (n:Content)       REQUIRE n.content_id IS UNIQUE",
        "CREATE CONSTRAINT IF NOT EXISTS FOR (n:Media)         REQUIRE n.name IS UNIQUE",
    ]
    for c in constraints:
        try:
            tx.run(c)
        except Exception:
            pass


def upsert_entity(tx, e: Dict) -> None:
    ntype = ENTITY_TYPE_MAP.get(e.get("type", "AICompany"), "AICompany")
    tx.run(
        f"MERGE (n:{ntype} {{name:$name}}) "
        "ON CREATE SET n.description=$desc "
        "ON MATCH  SET n.description=COALESCE(n.description,$desc)",
        name=e["name"],
        desc=e.get("description", ""),
    )


def upsert_relation(tx, r: Dict) -> None:
    rel = r.get("relation", "RELATED_TO").upper().replace(" ", "_")
    allowed = {
        "DEVELOPS",
        "INVESTS_IN",
        "PARTNERS_WITH",
        "APPLIES",
        "USED_IN",
        "RELATED_TO",
    }
    if rel not in allowed:
        return
    try:
        tx.run(
            f"MATCH (s {{name:$src}}) MATCH (t {{name:$tgt}}) MERGE (s)-[:{rel}]->(t)",
            src=r["source"],
            tgt=r["target"],
        )
    except Exception:
        pass


def upsert_article_and_mentions(tx, row: pd.Series, entities: List[Dict]) -> None:
    tx.run(
        "MERGE (a:Article {article_id:$aid}) SET a.title=$title, a.url=$url, a.published_date=$date",
        aid=row.get("article_id", ""),
        title=row.get("title", ""),
        url=row.get("url", ""),
        date=str(row.get("published_date", "")),
    )
    if pd.notna(row.get("source", "")):
        tx.run(
            "MERGE (m:Media {name:$src}) WITH m MATCH (a:Article {article_id:$aid}) MERGE (m)-[:PUBLISHED]->(a)",
            src=row["source"],
            aid=row.get("article_id", ""),
        )
    for e in entities:
        ntype = ENTITY_TYPE_MAP.get(e.get("type", "AICompany"), "AICompany")
        try:
            tx.run(
                f"MATCH (a:Article {{article_id:$aid}}) MATCH (n:{ntype} {{name:$name}}) MERGE (a)-[:MENTIONS]->(n)",
                aid=row.get("article_id", ""),
                name=e["name"],
            )
        except Exception:
            pass


def chunk_text(text: str, size: int = 500, overlap: int = 50) -> List[str]:
    if not text or pd.isna(text):
        return []
    text = str(text)
    return [text[i : i + size].strip() for i in range(0, len(text), size - overlap) if text[i : i + size].strip()]


# ──────────────────────────────────────────
# 3. 메인 실행 (스크립트로 직접 호출 시)
# ──────────────────────────────────────────


def is_article_loaded(tx, aid: str) -> bool:
    """이미 DB에 적재된 기사인지 체크하여 중복 API 호출 방지"""
    res = tx.run("MATCH (a:Article {article_id:$aid}) RETURN count(a) as cnt", aid=aid)
    single = res.single()
    return (single["cnt"] > 0) if single else False


# ──────────────────────────────────────────
# 3. 메인 실행 (스크립트로 직접 호출 시)
# ──────────────────────────────────────────


def main() -> None:
    # 1. 모든 엑셀 파일 로드 후 병합 및 고유 기사만 필터링
    xlsx_files = sorted(glob.glob("Articles_*.xlsx"))
    if not xlsx_files:
        raise FileNotFoundError("Articles_*.xlsx 파일이 없습니다. finScrapping.py를 먼저 실행하세요.")
    
    dfs = []
    for f in xlsx_files:
        try:
            dfs.append(pd.read_excel(f))
        except Exception as e:
            print(f"⚠️ {f} 로드 실패: {e}")

    df = pd.concat(dfs, ignore_index=True).drop_duplicates(subset=["url"])
    print(f"✅ 로드 완료: 총 {len(xlsx_files)}개 엑셀 파일 통합 완료 ({len(df)}건의 고유 기사 대상)")

    # 2. Neo4j 스키마 생성 (삭제하지 않고 스키마만 준비)
    with driver.session() as s:
        s.execute_write(setup_schema)
    print("✅ Neo4j 스키마 준비 완료 (기존 데이터 보존)")

    # 3. 엔티티/관계 추출 및 적재 (신규 기사만 처리)
    print(f"총 {len(df)}건 중 신규 기사 필터링 및 처리 시작...")
    for idx, row in df.iterrows():
        aid = str(row.get("article_id", f"ART_{idx}"))
        title = str(row.get("title", ""))
        
        # 이미 적재된 기사인지 판별
        with driver.session() as s:
            exists = s.execute_read(is_article_loaded, aid)
        
        if exists:
            print(f"  ⏭️  [{idx + 1}/{len(df)}] 이미 적재됨 (스킵): {title[:35]}...")
            continue

        text = title + "\n" + str(row.get("content", ""))
        state: ArticleState = dict(
            article_id=aid,
            title=title,
            text=text,
            is_ai_related=False,
            entities=[],
            relations=[],
        )
        out = pipeline.invoke(state)
        if out["is_ai_related"]:
            with driver.session() as s:
                for entity in out["entities"]:
                    s.execute_write(upsert_entity, entity)
                for r in out["relations"]:
                    s.execute_write(upsert_relation, r)
                s.execute_write(upsert_article_and_mentions, row, out["entities"])
            print(f"  ✅ [{idx + 1}/{len(df)}] 신규 적재완료: {title[:35]}... | 엔티티: {[ent['name'] for ent in out['entities'][:4]]}")
        else:
            print(f"  ⏭️  [{idx + 1}/{len(df)}] AI 비관련 (적재 제외): {title[:35]}...")
    
    print("\n✅ 엔티티/관계 추출 및 Neo4j 증분 적재 완료")

    # 4. Content 청킹 + 임베딩 (신규 기사의 청크만 생성)
    print("Content 노드 생성 및 신규 임베딩 시작...")
    for idx, row in df.iterrows():
        aid = str(row.get("article_id", f"ART_{idx}"))
        
        # 이미 이 기사의 청크가 임베딩되어 연결되어 있는지 확인
        with driver.session() as s:
            res = s.run("MATCH (a:Article {article_id:$aid})-[:HAS_CHUNK]->(c:Content) RETURN count(c) as cnt", aid=aid)
            single = res.single()
            has_chunks = (single["cnt"] > 0) if single else False
        
        if has_chunks:
            continue

        chunks = chunk_text(str(row.get("content", "")))
        with driver.session() as s:
            for i, chunk in enumerate(chunks):
                cid = f"{aid}_chunk_{i}"
                vec = embedder.embed_query(chunk)
                s.run(
                    "MERGE (c:Content {content_id:$cid}) "
                    "SET c.chunk=$chunk, c.article_id=$aid, c.chunk_index=$i, c.embedding=$vec "
                    "WITH c MATCH (a:Article {article_id:$aid}) MERGE (a)-[:HAS_CHUNK]->(c)",
                    cid=cid,
                    chunk=chunk,
                    aid=aid,
                    i=i,
                    vec=vec,
                )
    print("✅ Content 노드 신규 임베딩 적재 완료")

    # 5. 벡터 인덱스 생성 (기존에 있으면 알아서 생략됨)
    create_vector_index(
        driver,
        INDEX_NAME,
        label="Content",
        embedding_property="embedding",
        dimensions=1536,
        similarity_fn="cosine",
    )
    print(f"✅ 벡터 인덱스 [{INDEX_NAME}] 갱신 및 검증 완료")


if __name__ == "__main__":
    main()
