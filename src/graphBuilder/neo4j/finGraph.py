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


# Windows cp949 인코딩 환경에서 이모지 출력 시 UnicodeEncodeError 방지를 위한 안전한 print 함수 정의
def safe_print(*args, **kwargs) -> None:
    import sys
    try:
        # end나 sep 인자를 올바르게 처리할 수 있도록 내장 print의 기능 준수
        sep = kwargs.get("sep", " ")
        end = kwargs.get("end", "\n")
        msg = sep.join(map(str, args))
        sys.stdout.write(msg + end)
        sys.stdout.flush()
    except UnicodeEncodeError:
        msg = sep.join(map(str, args))
        cleaned = (
            msg.replace("✅", "[OK]")
            .replace("⚠️", "[WARN]")
            .replace("🚨", "[ERR]")
            .replace("⏭️", "[SKIP]")
            .replace("🤖", "[AI]")
            .replace("🏢", "[COMP]")
            .replace("🌌", "[GRAPH]")
            .replace("📰", "[NEWS]")
            .replace("🔬", "[TECH]")
            .replace("🔗", "[LINK]")
        )
        try:
            sys.stdout.write(cleaned + end)
            sys.stdout.flush()
        except Exception:
            ascii_msg = msg.encode("ascii", errors="replace").decode("ascii")
            sys.stdout.write(ascii_msg + end)
            sys.stdout.flush()


print = safe_print


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
    d = neo4j.GraphDatabase.driver(uri, auth=(username, password))
    d.verify_connectivity()
    return d


driver = None

# 엔티티/관계 추출은 gpt-4o를 사용하여 그래프 품질을 최대화한다
chat_llm = ChatOpenAI(model="gpt-4o", temperature=0)
rag_llm = OpenAILLM(model_name="gpt-4o-mini", model_params={"temperature": 0})
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
    retry_count: int               # 엔티티 추출 재시도 카운터
    reflection_feedback: str       # 엔티티 추출 자기반성 피드백
    relation_retry_count: int      # 관계 추출 재시도 카운터
    relation_feedback: str         # 관계 추출 자기반성 피드백


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
    """Node 2: 엔티티 추출 (자기반성 피드백 반영 및 타입 정합성 검증)"""
    retry_count = state.get("retry_count", 0) + 1
    feedback = state.get("reflection_feedback", "")
    
    feedback_prompt = ""
    if feedback:
        feedback_prompt = (
            f"\n\n⚠️ [이전 시도에 대한 검증 오류 피드백]:\n{feedback}\n"
            "위 오류를 반드시 분석하여, 이번에는 중복되거나 비어있거나 불완전하지 않고 "
            "정확한 타입과 설명을 갖춘 올바른 엔티티만 엄격하게 JSON으로 추출해주세요."
        )

    prompt = f"""다음 AI 뉴스에서 핵심 엔티티들을 추출하세요.
엔티티 유형:
- AICompany: 기업/기관 (예: 삼성전자, OpenAI)
- AITechnology: AI 기술 (예: 대규모언어모델, 강화학습)
- AIService: 서비스/제품 (예: ChatGPT, HyperCLOVA X)
- AIField: 적용 분야 (예: 금융AI, AI 반도체)

제목: {state["title"]}
본문: {state["text"][:900]}{feedback_prompt}

JSON으로만 응답: {{"entities":[{{"name":"...","type":"AICompany|AITechnology|AIService|AIField","description":"..."}}]}}"""
    
    res = chat_llm.invoke(prompt)
    entities = []
    new_feedback = ""
    
    try:
        raw = str(res.content).strip()
        if "```" in raw:
            raw = raw.split("```")[1].lstrip("json")
        data = json.loads(raw)
        extracted = data.get("entities", [])
        
        allowed_types = {"AICompany", "AITechnology", "AIService", "AIField"}
        valid_entities = []
        for e in extracted:
            name = e.get("name", "").strip()
            etype = e.get("type", "").strip()
            desc = e.get("description", "").strip()
            
            if not name:
                new_feedback += "- 엔티티의 이름(name) 필드가 누락되었거나 비어있습니다.\n"
                continue
            if etype not in allowed_types:
                new_feedback += f"- 엔티티 '{name}'의 타입 '{etype}'은 허용된 종류({', '.join(allowed_types)})가 아닙니다.\n"
                continue
            if not desc:
                new_feedback += f"- 엔티티 '{name}'에 대한 설명(description)이 생략되었습니다.\n"
                continue
                
            valid_entities.append({
                "name": name,
                "type": etype,
                "description": desc
            })
            
        entities = valid_entities
        if not entities:
            new_feedback = "유효한 엔티티가 하나도 추출되지 않았습니다."
            
    except Exception as err:
        entities = []
        new_feedback = f"응답 JSON 파싱 실패 또는 형식이 올바르지 않습니다. 에러: {str(err)}"
        
    return {
        **state,
        "entities": entities,
        "retry_count": retry_count,
        "reflection_feedback": new_feedback.strip()
    }


def extract_relations(state: ArticleState) -> ArticleState:
    """Node 3: 관계 추출 (자기반성 피드백 반영 및 엔티티명 정합성 검증)"""
    if not state["entities"]:
        return {**state, "relations": [], "relation_retry_count": 0, "relation_feedback": ""}

    relation_retry = state.get("relation_retry_count", 0) + 1
    rel_feedback = state.get("relation_feedback", "")

    # 엔티티명 목록을 정확히 제공하여 LLM이 이름을 임의로 변경하지 않도록 한다
    names_list = [e["name"] for e in state["entities"]]
    elist = "\n".join([f"- {e['name']} ({e['type']})" for e in state["entities"]])

    feedback_prompt = ""
    if rel_feedback:
        feedback_prompt = (
            f"\n\n⚠️ [이전 시도 관계 추출 오류 피드백]:\n{rel_feedback}\n"
            "위 오류를 반드시 수정하여, source/target 이름이 엔티티 목록에 있는 이름과 정확히 일치하는 "
            "관계만 JSON으로 응답하세요."
        )

    prompt = (
        f"다음 AI 뉴스에서 엔티티 간의 관계를 추출하세요.\n\n"
        f"엔티티 목록 (이름은 정확히 이 목록에서만 사용):\n{elist}\n\n"
        f"본문: {state['text'][:900]}\n\n"
        "관계 유형:\n"
        "- DEVELOPS: 기업이 기술/서비스를 개발\n"
        "- INVESTS_IN: 기업이 다른 기업/분야에 투자\n"
        "- PARTNERS_WITH: 기업 간 파트너십/협력\n"
        "- APPLIES: 기업이 기술을 특정 분야에 적용\n"
        "- USED_IN: 기술/서비스가 특정 분야/제품에 활용\n"
        "- RELATED_TO: 일반적 연관 관계\n\n"
        "규칙: source와 target은 반드시 위 엔티티 목록의 정확한 이름을 사용할 것. "
        "엔티티가 최소 2개 이상이면 반드시 1개 이상의 관계를 추출할 것.\n\n"
        f"{feedback_prompt}"
        'JSON으로만 응답: {"relations":[{"source":"엔티티명","relation":"관계유형","target":"엔티티명"}]}'
    )

    res = chat_llm.invoke(prompt)
    relations: List[Dict] = []
    new_rel_feedback = ""

    try:
        raw = str(res.content).strip()
        if "```" in raw:
            raw = raw.split("```")[1].lstrip("json").strip()
        parsed = json.loads(raw).get("relations", [])

        # 엔티티 이름 집합으로 관계 소스/타겟 정합성 검증
        names_set = set(names_list)
        allowed = {"DEVELOPS", "INVESTS_IN", "PARTNERS_WITH", "APPLIES", "USED_IN", "RELATED_TO"}
        valid_rels: List[Dict] = []
        for r in parsed:
            src = r.get("source", "").strip()
            tgt = r.get("target", "").strip()
            rel = r.get("relation", "").strip().upper()
            if src not in names_set:
                new_rel_feedback += f"- source '{src}'이 엔티티 목록에 없음\n"
                continue
            if tgt not in names_set:
                new_rel_feedback += f"- target '{tgt}'이 엔티티 목록에 없음\n"
                continue
            if rel not in allowed:
                new_rel_feedback += f"- 관계유형 '{rel}'은 허용되지 않음\n"
                continue
            if src == tgt:
                new_rel_feedback += f"- source와 target이 동일({src})하여 제외\n"
                continue
            valid_rels.append({"source": src, "relation": rel, "target": tgt})

        relations = valid_rels
        # 엔티티가 2개 이상인데 관계가 0개이면 피드백
        if len(names_list) >= 2 and not relations:
            new_rel_feedback = (
                f"엔티티가 {len(names_list)}개임에도 유효 관계가 0개입니다. "
                "본문에서 반드시 연관되는 엔티티 쌍을 찾아 관계를 추출하세요."
            )
    except Exception as err:
        relations = []
        new_rel_feedback = f"JSON 파싱 실패: {str(err)}"

    return {
        **state,
        "relations": relations,
        "relation_retry_count": relation_retry,
        "relation_feedback": new_rel_feedback.strip(),
    }


def route_after_check(state: ArticleState) -> str:
    """AI 관련 기사인지 판별 후 라우팅"""
    return "extract_entities" if state["is_ai_related"] else END


def validate_entities(state: ArticleState) -> str:
    """엔티티 품질 검증 — 미달 시 최대 3회 자기반성(Self-Reflection) 루프"""
    retry_count = state.get("retry_count", 0)
    feedback = state.get("reflection_feedback", "")
    entities = state.get("entities", [])

    if (feedback or not entities) and retry_count < 3:
        print(f"    ⚠️ [엔티티 Self-Reflection] 품질 미달 ({retry_count}/3). 피드백: {feedback[:80]}")
        return "extract_entities"

    if feedback and retry_count >= 3:
        print(f"    🚨 [엔티티 Self-Reflection] 3회 초과, 강제 통과. 피드백: {feedback[:80]}")

    return "extract_relations"


def validate_relations(state: ArticleState) -> str:
    """관계 품질 검증 — 엔티티 2개 이상인데 관계 0개이면 최대 2회 재시도"""
    rel_retry = state.get("relation_retry_count", 0)
    rel_feedback = state.get("relation_feedback", "")
    relations = state.get("relations", [])
    entities = state.get("entities", [])

    # 엔티티가 2개 이상인데 관계가 없고 아직 재시도 여유가 있으면 루프
    if len(entities) >= 2 and not relations and rel_retry < 2:
        print(f"    ⚠️ [관계 Self-Reflection] 관계 0개 ({rel_retry}/2). 재시도: {rel_feedback[:80]}")
        return "extract_relations"

    if rel_feedback and relations:
        # 유효 관계가 있지만 일부 피드백도 있음 — 통과
        print(f"    ⚠️ [관계 Self-Reflection] 일부 무효 관계 제외됨. 유효 관계: {len(relations)}개")

    return END


builder = StateGraph(ArticleState)
builder.add_node("check_ai", check_ai_relevance)
builder.add_node("extract_entities", extract_entities)
builder.add_node("extract_relations", extract_relations)
builder.set_entry_point("check_ai")
builder.add_conditional_edges("check_ai", route_after_check)

# 엔티티 자기반성 루프
builder.add_conditional_edges(
    "extract_entities",
    validate_entities,
    {
        "extract_entities": "extract_entities",
        "extract_relations": "extract_relations",
    },
)

# 관계 자기반성 루프 (신규)
builder.add_conditional_edges(
    "extract_relations",
    validate_relations,
    {
        "extract_relations": "extract_relations",
        END: END,
    },
)

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
    global driver
    driver = get_neo4j_driver()
    
    # 1. 모든 엑셀 파일 로드 후 병합 및 고유 기사만 필터링 (루트 및 scrapping 폴더 모두 탐색)
    xlsx_files = sorted(glob.glob("Articles_*.xlsx") + glob.glob(os.path.join("src", "graphBuilder", "scrapping", "Articles_*.xlsx")))
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
            retry_count=0,
            reflection_feedback="",
            relation_retry_count=0,
            relation_feedback="",
        )
        out = pipeline.invoke(state)
        if out["is_ai_related"]:
            with driver.session() as s:
                for entity in out["entities"]:
                    s.execute_write(upsert_entity, entity)
                for r in out["relations"]:
                    s.execute_write(upsert_relation, r)
                s.execute_write(upsert_article_and_mentions, row, out["entities"])
            rel_cnt = len(out["relations"])
            ent_cnt = len(out["entities"])
            # 엔티티가 2개 이상인데 관계가 없으면 경고 표시
            rel_warn = " ⚠️ 관계=0" if ent_cnt >= 2 and rel_cnt == 0 else ""
            print(
                f"  ✅ [{idx + 1}/{len(df)}] 신규 적재완료: {title[:35]}... "
                f"| 엔티티: {ent_cnt}개 | 관계: {rel_cnt}개{rel_warn}"
            )
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
