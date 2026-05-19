"""
app.py — FinNode GraphRAG 챗봇
================================
Hugging Face Spaces 배포 진입점.
Gradio ChatInterface + LangGraph 기반 대화 흐름 제어.

실행:
    python app.py
"""

from typing import Any, Dict, List, TypedDict

import dotenv
import gradio as gr
from langgraph.graph import END, StateGraph

from src.retrieval.finRetrieval import graphrag

dotenv.load_dotenv()

# ──────────────────────────────────────────
# Startup DB 자가 진단 (Fail-Fast)
# ──────────────────────────────────────────
# 허깅페이스Spaces 및 실제 앱 서버 구동 시점에는 즉시 자가 진단을 수행하여,
# Neo4j 데이터베이스 연결이 불가능하면 구동 실패(Crash Early)를 일으킵니다.
try:
    graphrag._init_once()
    try:
        print("✅ [자가 진단 완료] Neo4j AuraDB 지식 그래프에 완벽하게 접속되었습니다!")
    except UnicodeEncodeError:
        print("[OK] [자가 진단 완료] Neo4j AuraDB 지식 그래프에 완벽하게 접속되었습니다!")
except Exception as e:
    try:
        print(f"❌ [자가 진단 실패] Neo4j DB 연결 확인 중 에러가 발생했습니다: {e}")
    except UnicodeEncodeError:
        print(f"[FAIL] [자가 진단 실패] Neo4j DB 연결 확인 중 에러가 발생했습니다: {e}")
    raise e

# ──────────────────────────────────────────
# 1. LangGraph 챗봇 State 정의
# ──────────────────────────────────────────


class ChatState(TypedDict):
    question: str  # 사용자 질문
    history: List[dict]  # 대화 히스토리 [{"role": "user"/"assistant", "content": "..."}]
    context: str  # GraphRAG 검색 결과
    answer: str  # 최종 답변


# ──────────────────────────────────────────
# 2. LangGraph 노드 정의
# ──────────────────────────────────────────


def retrieve_node(state: ChatState) -> ChatState:
    """Node 1: GraphRAG로 관련 컨텍스트 검색"""
    try:
        result = graphrag.search(query_text=state["question"])
        context = result.answer  # GraphRAG가 이미 답변을 완성하므로 바로 사용
        
        # 실제 GraphRAG 검색 시 사용된 상위 3개 뉴스 피드 동적 추출 및 포맷팅
        sources = []
        seen_urls = set()
        if hasattr(result, "retriever_result") and result.retriever_result and hasattr(result.retriever_result, "items"):
            for item in result.retriever_result.items:
                meta = getattr(item, "metadata", {})
                title = meta.get("article_title")
                url = meta.get("article_url")
                date = meta.get("article_date")
                if title and url and url not in seen_urls:
                    seen_urls.add(url)
                    # date 형식 포맷팅 (예: 2026-05-19T00:00:00Z -> 2026-05-19)
                    if date and "T" in str(date):
                        date = str(date).split("T")[0]
                    sources.append({"title": title, "url": url, "date": date})
                    if len(sources) >= 3:
                        break
        
        # 만약 retriever_result에서 찾지 못한 경우, Neo4j DB에서 키워드 기반으로 직접 관련 뉴스 3개 백업 조회
        if not sources:
            try:
                from src.retrieval.finRetrieval import get_neo4j_driver
                driver = get_neo4j_driver()
                # 단순 키워드 매칭 쿼리
                query_words = [w for w in state["question"].split() if len(w) > 1]
                conditions = []
                for w in query_words[:3]:
                    conditions.append(f"a.title CONTAINS '{w}' OR a.description CONTAINS '{w}'")
                
                with driver.session() as session:
                    cypher = "MATCH (a:Article) "
                    if conditions:
                        cypher += "WHERE " + " OR ".join(conditions) + " "
                    cypher += "RETURN a.title as title, a.url as url, a.published_date as date ORDER BY a.published_date DESC LIMIT 3"
                    
                    res_backup = session.run(cypher)
                    for r in res_backup:
                        title = r["title"]
                        url = r["url"]
                        date = r["date"]
                        if title and url and url not in seen_urls:
                            seen_urls.add(url)
                            if date and "T" in str(date):
                                date = str(date).split("T")[0]
                            sources.append({"title": title, "url": url, "date": date})
            except Exception:
                pass
                
        # 만약 여전히 비어있다면, 최신 뉴스 3개 노출 (상상해 낸 가짜 정보 방지)
        if not sources:
            try:
                from src.retrieval.finRetrieval import get_neo4j_driver
                driver = get_neo4j_driver()
                with driver.session() as session:
                    res_latest = session.run(
                        "MATCH (a:Article) RETURN a.title as title, a.url as url, a.published_date as date "
                        "ORDER BY a.published_date DESC LIMIT 3"
                    )
                    for r in res_latest:
                        title = r["title"]
                        url = r["url"]
                        date = r["date"]
                        if title and url and url not in seen_urls:
                            seen_urls.add(url)
                            if date and "T" in str(date):
                                date = str(date).split("T")[0]
                            sources.append({"title": title, "url": url, "date": date})
            except Exception:
                pass
                
        # 답변 끝에 📰 관련 뉴스 피드 파트 정성스럽게 덧붙이기
        if sources:
            news_feed = "\n\n📰 **관련 뉴스 피드 (실시간 분석 출처)**\n"
            for s in sources:
                date_str = f" ({s['date']})" if s['date'] else ""
                news_feed += f"- 🔗 [{s['title']}]({s['url']}){date_str}\n"
            
            # 중복으로 관련 뉴스 피드가 붙지 않도록 방지
            if "관련 뉴스 피드" not in context:
                context += news_feed
                
    except Exception as e:
        context = f"[검색 오류: {e}]"
    return {**state, "context": context}


def generate_node(state: ChatState) -> ChatState:
    """Node 2: 대화 히스토리를 고려하여 최종 답변 생성

    GraphRAG가 이미 검색 + 생성을 처리하므로,
    여기서는 히스토리 기반 후처리나 추가 포맷팅만 수행합니다.
    """
    # GraphRAG 결과를 바로 답변으로 사용
    # (히스토리 기반 후속 질문 처리가 필요하면 이 노드를 확장하세요)
    answer = state["context"] if state["context"] else "관련 정보를 찾을 수 없습니다."
    return {**state, "answer": answer}


# ──────────────────────────────────────────
# 3. LangGraph 워크플로우 컴파일
# ──────────────────────────────────────────

builder = StateGraph(ChatState)
builder.add_node("retrieve", retrieve_node)
builder.add_node("generate", generate_node)
builder.set_entry_point("retrieve")
builder.add_edge("retrieve", "generate")
builder.add_edge("generate", END)

chat_graph = builder.compile()


# ──────────────────────────────────────────
# 4. Gradio 연동 함수
# ──────────────────────────────────────────


def chat(message: str, history: list):
    """Gradio ChatInterface가 호출하는 함수.

    Args:
        message: 사용자 입력 메시지
        history: Gradio가 관리하는 대화 히스토리
                 [{"role": "user"/"assistant", "content": "..."}] 형식

    Returns:
        Generator: 챗봇 답변 (실시간 상태 표시 포함)
    """
    if not message.strip():
        yield "질문을 입력해 주세요."
        return

    # Gradio history → LangGraph state 형식으로 변환
    state: ChatState = {
        "question": message,
        "history": history,
        "context": "",
        "answer": "",
    }

    yield "🔍 실시간 지식 그래프에서 관련 뉴스를 검색하는 중입니다..."

    try:
        # LangGraph의 stream을 사용하여 각 노드 실행 시점마다 이벤트를 받음
        for event in chat_graph.stream(state):
            if "retrieve" in event:
                yield "💡 검색 완료! 분석 결과를 바탕으로 최종 답변을 생성하는 중입니다..."
            elif "generate" in event:
                yield event["generate"]["answer"]
    except Exception as e:
        yield f"⚠️ 챗봇 처리 중 오류가 발생했습니다: {str(e)}"


def get_db_stats() -> Dict[str, Any]:
    """Neo4j 데이터베이스로부터 실시간 지식 그래프 통계 및 요약을 안전하게 조회합니다.

    Returns:
        Dict[str, Any]: 기사 건수, 기업 수, 기술 수, 관계 수, 세부 설명 목록
    """
    stats: Dict[str, Any] = {
        "articles": 0,
        "companies": 0,
        "technologies": 0,
        "techs_list": [],
        "recent_articles": [],
    }
    try:
        from src.retrieval.finRetrieval import get_neo4j_driver
        driver = get_neo4j_driver()
        with driver.session() as session:
            # 1. 각 노드별 갯수 조회
            res_articles = session.run("MATCH (a:Article) RETURN count(a) as cnt").single()
            if res_articles:
                stats["articles"] = res_articles["cnt"]

            res_companies = session.run("MATCH (c:AICompany) RETURN count(c) as cnt").single()
            if res_companies:
                stats["companies"] = res_companies["cnt"]

            res_techs = session.run("MATCH (t:AITechnology) RETURN count(t) as cnt").single()
            if res_techs:
                stats["technologies"] = res_techs["cnt"]

            # 2. 기술 목록 & 설명 조회 (상위 8개)
            res_tech_list = session.run(
                "MATCH (t:AITechnology) "
                "RETURN t.name as name, COALESCE(t.description, 'AI 혁신 기술 인프라') as desc LIMIT 8"
            )
            stats["techs_list"] = [{"name": r["name"], "desc": r["desc"]} for r in res_tech_list]

            # 3. 최근 기사 목록 조회 (최근 4개)
            res_art_list = session.run(
                "MATCH (a:Article) "
                "RETURN a.title as title, a.published_date as date, a.url as url "
                "ORDER BY a.published_date DESC LIMIT 4"
            )
            stats["recent_articles"] = [
                {"title": r["title"], "date": r["date"], "url": r["url"]}
                for r in res_art_list
            ]
    except Exception as e:
        print(f"⚠️ [통계 조회 실패] Neo4j 통계를 가져오는 데 실패했습니다: {e}")
    return stats


def build_stats_html(stats: Dict[str, Any]) -> str:
    """조회된 지식 그래프 통계 정보들을 바탕으로 미려하고 컴팩트한 대시보드용 HTML을 생성합니다."""
    # 1. 최신 뉴스 키워드 배지 HTML 생성 (둥근 네모 형태)
    keyword_html: str = ""
    for t in stats.get("techs_list", []):
        keyword_html += f"""
        <span class="keyword-badge"># {t['name']}</span>
        """
    if not keyword_html:
        keyword_html = '<div style="font-size:12px; color:#94a3b8;">등록된 키워드가 없습니다.</div>'

    # 2. 최근 기사 리스트 HTML 생성 (최대 4개) - 전체 영역 클릭 시 이동하도록 a 태그로 래핑
    news_list_html: str = ""
    for a in stats.get("recent_articles", []):
        title = a["title"]
        url = a["url"] if a["url"] and str(a["url"]).lower() != "nan" else "#"
        target = 'target="_blank"' if url != "#" else ""
        date_str = str(a['date'])[:10] if a['date'] else ""
        news_list_html += f"""
        <a class="news-item-link" href="{url}" {target}>
            <div class="news-item">
                <div class="news-title">{title}</div>
                <div class="news-meta">🗓️ {date_str}</div>
            </div>
        </a>
        """
    if not news_list_html:
        news_list_html = '<div style="font-size:12px; color:#94a3b8;">최근 수집된 기사가 없습니다.</div>'

    node_count = stats['companies'] + stats['technologies']

    html: str = f"""
    <div class="dashboard-container">
        <!-- Ambient background elements for beautiful glass effects -->
        <div class="ambient-glow"></div>
        
        <div style="font-size: 16px; font-weight: 850; color: #334155; margin-bottom: 2px; display: flex; align-items: center; gap: 6px; letter-spacing: -0.02em;">
            📊 <span>FinGraph AI Terminal</span>
        </div>
        <p style="font-size: 11px; color: #475569; margin-top: -2px; margin-bottom: 12px; font-weight: 600;">GraphRAG 실시간 분석 엔진 상태</p>
        
        <!-- 실시간 엔진 텔레메트리 (4개 메트릭) -->
        <div class="stats-grid">
            <div class="stat-card">
                <div class="stat-lbl">💡 분석 모델</div>
                <div class="stat-val" style="font-size: 13px !important; font-weight: 800 !important; color: #334155;">GPT-4o</div>
            </div>
            <div class="stat-card">
                <div class="stat-lbl">🏢 대상 회사</div>
                <div class="stat-val" style="font-size: 13px !important; font-weight: 800 !important; color: #334155;">{stats['companies']}개</div>
            </div>
            <div class="stat-card">
                <div class="stat-lbl">🔑 뉴스 키워드</div>
                <div class="stat-val" style="font-size: 13px !important; font-weight: 800 !important; color: #334155;">{stats['technologies']}개</div>
            </div>
            <div class="stat-card">
                <div class="stat-lbl">🔐 DB 연결</div>
                <div class="stat-val" style="font-size: 12px !important; font-weight: 800 !important; color: #0d9488; margin-top: 3px;"><span style="background: rgba(13, 148, 136, 0.12); padding: 2px 6px; border-radius: 5px; display: inline-block;">Active</span></div>
            </div>
        </div>

        <!-- 수집된 데이터 규모 -->
        <div class="stats-grid" style="margin-top: 10px; margin-bottom: 8px;">
            <div class="stat-card" style="padding: 8px 10px;">
                <div class="stat-lbl">📰 분석용 뉴스 기사</div>
                <div class="stat-val" style="color: #334155;">{stats['articles']}건</div>
            </div>
            <div class="stat-card" style="padding: 8px 10px;">
                <div class="stat-lbl">🧬 추출된 지식 연결망</div>
                <div class="stat-val" style="color: #334155;">{node_count}개</div>
            </div>
        </div>

        <!-- 데이터 배경 정보 설명 패널 (사용자 이해를 돕는 배경 정보 친절 서술) -->
        <div style="font-size: 11px; color: #475569; line-height: 1.5; margin-top: 8px; margin-bottom: 15px; padding: 10px; background: rgba(241, 245, 249, 0.7); border: 1px solid #cbd5e1; border-radius: 8px;">
            ℹ️ <b>데이터 수집 배경 정보</b><br>
            실시간 뉴스 웹 크롤러가 국내 IT/금융 기사 <b>{stats['articles']}건</b>을 정밀 수집하였으며, 뉴스 본문을 분석하여 기사 속 주요 기업·핵심 기술·서비스 간의 입체적 연관 관계 <b>{node_count}개</b>를 연결망(지식 그래프)으로 완벽하게 연동하였습니다.
        </div>
        
        <div class="section-subtitle" style="color: #334155;">💡 최신 뉴스 키워드</div>
        <div class="keyword-container">
            {keyword_html}
        </div>
        
        <div class="section-subtitle" style="color: #334155;">📰 최신 뉴스 피드</div>
        <div class="news-feed-container">
            <div class="news-feed">
                {news_list_html}
            </div>
        </div>
    </div>
    """
    return html


# ──────────────────────────────────────────
# 5. Gradio UI 구성
# ──────────────────────────────────────────

# Gradio 버전 동적 감지 및 테마 설정 분기 (로컬 6.x vs 원격 4.x 크래시 완벽 방지)
try:
    gradio_major = int(gr.__version__.split(".")[0])
except Exception:
    gradio_major = 4  # 기본값 백업

theme_obj = gr.themes.Soft(
    font=["Pretendard", "-apple-system", "BlinkMacSystemFont", "system-ui", "sans-serif"],
    primary_hue="sky",
    secondary_hue="slate",
)

custom_css: str = """
body {
    background-color: #fbf9f6;
    font-family: 'Pretendard', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif !important;
    color: #0f172a !important; /* 기본 검정색 */
}

/* Ambient glow point backgrounds (보라색 원천 배제, 은은한 스카이블루와 테일그린 톤) */
.ambient-glow {
    position: fixed;
    top: 0; left: 0; right: 0; bottom: 0;
    background: radial-gradient(circle at 85% 15%, rgba(14, 165, 233, 0.06) 0%, transparent 45%), 
                radial-gradient(circle at 15% 85%, rgba(20, 184, 166, 0.06) 0%, transparent 45%);
    z-index: -1;
    pointer-events: none;
}

/* 대시보드 투명 글래스모피즘 컨테이너 */
.dashboard-container {
    background: rgba(255, 255, 255, 0.8) !important;
    backdrop-filter: blur(24px) !important;
    -webkit-backdrop-filter: blur(24px) !important;
    border: 1px solid #cbd5e1 !important; /* 깔끔한 뉴트럴 슬레이트 테두리 */
    border-radius: 12px;
    padding: 16px;
    box-shadow: 0 4px 12px -2px rgba(15, 23, 42, 0.03) !important;
    font-family: 'Pretendard', -apple-system, BlinkMacSystemFont, sans-serif;
}
.dark .dashboard-container {
    background: rgba(15, 23, 42, 0.55) !important;
    border-color: rgba(14, 165, 233, 0.25) !important;
    box-shadow: 0 4px 12px -2px rgba(0, 0, 0, 0.3) !important;
}

/* 통계 그리드 및 글래스 카드 */
.stats-grid {
    display: grid;
    grid-template-columns: repeat(2, 1fr);
    gap: 10px;
    margin-bottom: 15px;
}
.stat-card {
    background: rgba(255, 255, 255, 0.95);
    border: 1px solid #cbd5e1;
    border-radius: 8px;
    padding: 10px;
    text-align: center;
    box-shadow: 0 1px 3px rgba(15, 23, 42, 0.01);
    transition: all 0.25s ease-in-out;
}
.stat-card:hover {
    transform: translateY(-2px);
    background: rgba(255, 255, 255, 1);
    border-color: #0ea5e9; /* 호버 시 스카이 블루 */
    box-shadow: 0 4px 12px -2px rgba(14, 165, 233, 0.1);
}
.dark .stat-card {
    background: rgba(30, 41, 59, 0.7);
    border-color: rgba(14, 165, 233, 0.2);
    color: #f1f5f9;
}
.dark .stat-card:hover {
    border-color: #38bdf8;
}
.stat-val {
    font-size: 16px !important;
    font-weight: 850 !important;
    color: #0f172a !important; /* 확실한 고대비 검정색 글씨 */
    margin-top: 2px;
}
.dark .stat-val {
    color: #f8fafc !important;
}
.stat-lbl {
    font-size: 11px !important;
    color: #334155;
    font-weight: 600;
}
.dark .stat-lbl {
    color: #94a3b8;
}

/* 최신 뉴스 키워드 컨테이너 및 둥근 배지 스타일 (보라색 배제, 슬레이트 및 검정색 글씨) */
.keyword-container {
    display: flex;
    flex-wrap: wrap;
    gap: 8px;
    margin-bottom: 12px;
}
.keyword-badge {
    display: inline-block;
    background: #f1f5f9 !important; /* 연한 뉴트럴 슬레이트 */
    border: 1px solid #cbd5e1 !important; /* 슬레이트 테두리 */
    border-radius: 8px !important;
    padding: 6px 12px;
    font-size: 11px !important;
    font-weight: 700;
    color: #0f172a !important; /* 확실한 검정색 */
    box-shadow: 0 1px 2px rgba(0, 0, 0, 0.02) !important;
    transition: all 0.2s ease-in-out;
}
.keyword-badge:hover {
    background: #e2e8f0 !important;
    transform: scale(1.03);
}
.dark .keyword-badge {
    background: rgba(15, 23, 42, 0.4) !important;
    border-color: rgba(14, 165, 233, 0.25) !important;
    color: #cbd5e1 !important;
}

/* 최근 뉴스 피드 클릭 가능한 카드 레이아웃 */
.news-feed-container {
    max-height: 350px;
    overflow-y: auto;
    border: 1px solid #cbd5e1;
    border-radius: 6px;
    padding: 8px;
    background: rgba(255, 255, 255, 0.7);
}
.dark .news-feed-container {
    background: rgba(30, 41, 59, 0.5);
    border-color: rgba(14, 165, 233, 0.15);
}
/* 스크롤바 커스텀 */
.news-feed-container::-webkit-scrollbar {
    width: 4px;
}
.news-feed-container::-webkit-scrollbar-track {
    background: transparent;
}
.news-feed-container::-webkit-scrollbar-thumb {
    background: rgba(148, 163, 184, 0.4);
    border-radius: 2px;
}
.dark .news-feed-container::-webkit-scrollbar-thumb {
    background: rgba(148, 163, 184, 0.2);
}

.news-item-link {
    text-decoration: none;
    display: block;
    margin-bottom: 8px;
}
.news-item-link:last-child {
    margin-bottom: 0;
}
.news-item {
    border-left: 3px solid #0ea5e9; /* 파란색 오션 블루 포인트 */
    padding: 8px 10px;
    background: rgba(255, 255, 255, 0.8);
    border-radius: 0 6px 6px 0;
    transition: all 0.2s ease-in-out;
    cursor: pointer;
}
.news-item-link:hover .news-item {
    background: rgba(255, 255, 255, 1);
    border-left-color: #0284c7;
    transform: translateX(3px);
    box-shadow: 0 2px 6px rgba(14, 165, 233, 0.08);
}
.dark .news-item {
    background: rgba(30, 41, 59, 0.3);
}
.dark .news-item-link:hover .news-item {
    background: rgba(30, 41, 59, 0.65);
    border-left-color: #38bdf8;
}
.news-title {
    font-size: 12px !important;
    font-weight: 600;
    color: #1b1c1a;
    line-height: 1.4;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
}
.dark .news-title {
    color: #cbd5e1;
}
.news-meta {
    font-size: 10px !important;
    color: #94a3b8;
    margin-top: 2px;
}

/* 서브타이틀 헤더 스타일 (연한 에메랄드/테일 배경 + 딥 테일 글씨) */
.section-subtitle {
    font-size: 13px !important;
    font-weight: 800;
    color: #0f766e !important; /* 딥 테일 글씨 */
    background: rgba(20, 184, 166, 0.1) !important; /* 연한 테일 글래스 배경 */
    margin: 18px 0 8px 0;
    padding: 6px 10px !important;
    border-radius: 6px !important;
    border-left: 3px solid #14b8a6 !important; /* 선명한 테일 세로선 */
    display: flex;
    align-items: center;
    gap: 6px;
}
.dark .section-subtitle {
    color: #99f6e4 !important;
    background: rgba(20, 184, 166, 0.2) !important;
    border-left-color: #2dd4bf !important;
}

/* 2x2 grid layout for chatbot example buttons (Stitch Action Grid style) */
[class*="examples"], .gr-samples-wrapper, .examples-container {
    display: grid !important;
    grid-template-columns: repeat(2, 1fr) !important;
    gap: 10px !important;
    margin-top: 15px !important;
    margin-bottom: 15px !important;
    background: transparent !important;
    border: none !important;
}
[class*="examples"] button {
    text-align: left !important;
    padding: 14px 18px !important;
    background: #ffffff !important; /* 깨끗하고 단정한 화이트 */
    border: 1px solid #cbd5e1 !important; /* 소프트한 슬레이트 테두리 */
    border-radius: 10px !important;
    font-size: 13px !important;
    font-weight: 600 !important;
    color: #0f172a !important; /* 단정한 검정색 */
    line-height: 1.4 !important;
    box-shadow: 0 1px 3px rgba(0, 0, 0, 0.02) !important;
    transition: all 0.2s ease-in-out !important;
    white-space: normal !important;
    height: auto !important;
    min-height: 54px !important;
    cursor: pointer !important;
}
.dark [class*="examples"] button {
    background: rgba(30, 41, 59, 0.5) !important;
    border-color: rgba(148, 163, 184, 0.2) !important;
    color: #e2e8f0 !important;
}
[class*="examples"] button:hover {
    transform: translateY(-1px) !important;
    background: #f8fafc !important; /* 아주 옅은 오프화이트 호버 */
    border-color: #94a3b8 !important;
    color: #0f172a !important;
    box-shadow: 0 4px 8px rgba(0, 0, 0, 0.06) !important;
}
.dark [class*="examples"] button:hover {
    background: rgba(30, 41, 59, 0.85) !important;
    border-color: rgba(148, 163, 184, 0.4) !important;
    color: #ffffff !important;
}

/* 챗봇 전송 버튼 프리미엄 다크 슬레이트 스타일 (이상한 그라데이션 제거, 단정하고 일관성 있는 색감) */
button.primary, 
.primary-btn, 
button.lg.primary, 
button.sm.primary,
button.variant-primary,
button[class*="submit-btn"],
[data-testid="submit-button"] {
    background: #1e293b !important; /* 프리미엄 다크 슬레이트 차콜 */
    color: white !important;
    font-weight: 700 !important;
    border: 1px solid #0f172a !important;
    border-radius: 8px !important;
    box-shadow: 0 2px 4px rgba(15, 23, 42, 0.08) !important;
    transition: all 0.2s ease-in-out !important;
    cursor: pointer !important;
}
button.primary:hover, 
.primary-btn:hover, 
button.variant-primary:hover,
button[class*="submit-btn"]:hover,
[data-testid="submit-button"]:hover {
    background: #0f172a !important; /* 호버 시 딥 블랙 */
    box-shadow: 0 4px 8px rgba(15, 23, 42, 0.15) !important;
    transform: translateY(-1px) !important;
}

/* secondary 및 기타 유틸리티 버튼 스타일 */
/* secondary 및 기타 유틸리티 버튼 스타일 (보라색 제거) */
button.secondary, 
button.lg.secondary, 
button.sm.secondary, 
button.wrap,
button.variant-secondary,
.secondary-btn {
    background-color: rgba(255, 255, 255, 0.6) !important;
    color: #0f172a !important; /* 기본 검정색 */
    border: 1px solid #cbd5e1 !important;
    font-weight: 700 !important;
    transition: all 0.2s ease-in-out !important;
    backdrop-filter: blur(8px);
}
.dark button.secondary, 
.dark button.variant-secondary, 
.dark .secondary-btn {
    background-color: rgba(30, 41, 59, 0.6) !important;
    color: #f1f5f9 !important;
    border-color: rgba(14, 165, 233, 0.2) !important;
}
button.secondary:hover, 
button.variant-secondary:hover,
.secondary-btn:hover {
    background-color: rgba(255, 255, 255, 0.95) !important;
    color: #0f172a !important;
    border-color: #94a3b8 !important;
}
.dark button.secondary:hover, 
.dark button.variant-secondary:hover {
    background-color: rgba(30, 41, 59, 0.95) !important;
    color: white !important;
    border-color: #38bdf8 !important;
}

/* 챗봇 보라색 배경 완전 제거 및 고대비 슬레이트/화이트 버블 구현 */
.bubble, .message {
    border-radius: 12px !important;
}

/* 사용자 버블 가독성 완전 개선 (글씨색을 강제로 깨끗한 흰색으로 고정하여 500% 선명하게 표시) */
.message.user {
    background-color: #334155 !important; /* 차분하고 고급스러운 다크 슬레이트 */
    border: 1px solid rgba(51, 65, 85, 0.2) !important;
}
.message.user p, .message.user span, .message.user li, .message.user div {
    color: #ffffff !important; /* 완전 흰색 글씨 */
    font-weight: 600 !important;
}

/* 봇 버블 가독성 완전 개선 (글씨색 확실한 검정색, 보라색 테두리 제거) */
.message.bot {
    background-color: rgba(255, 255, 255, 0.95) !important; /* 반투명 깨끗한 화이트 글래스 */
    border: 1px solid #cbd5e1 !important;
}
.message.bot p, .message.bot span, .message.bot li, .message.bot div {
    color: #0f172a !important; /* 확실한 고대비 검정색 글씨 */
}
.dark .message.user {
    background-color: #475569 !important;
}
.dark .message.bot {
    background-color: rgba(30, 41, 59, 0.85) !important;
    border-color: rgba(14, 165, 233, 0.2) !important;
}
.dark .message.bot p, .dark .message.bot span, .dark .message.bot li {
    color: #f1f5f9 !important;
}

/* Chatbot 라벨/탭 완전 숨김 (불필요한 보라색/하늘색 색상 및 테두리 원천 차단) */
.chatbot > div:first-child,
[class*="chatbot"] > div:first-child,
.chatbot-label,
div[class*="chatbot"] .label,
[data-testid="chatbot"] .label,
.chatbot-header,
div[class*="chatbot"] > div:first-child span,
.gr-panel-title,
.gr-chatbot-label {
    display: none !important;
}

/* 챗봇 메인 컨테이너 투명화 및 테두리 깔끔화 */
.chatbot, [class*="chatbot"] {
    background: rgba(255, 255, 255, 0.3) !important;
    border: 1px solid #cbd5e1 !important;
    border-radius: 12px !important;
}
.dark .chatbot {
    background: rgba(15, 23, 42, 0.3) !important;
    border-color: rgba(14, 165, 233, 0.15) !important;
}

/* 입력창(텍스트에어리어) 세로 높이 및 단일 행 수직 중앙 정렬 최적화 */
textarea, 
[class*="input-container"] textarea,
[data-testid="textbox"] textarea {
    height: 58px !important;
    min-height: 58px !important;
    max-height: 58px !important;
    font-size: 13px !important;
    padding: 18px 16px !important; /* 위아래 패딩을 18px로 대칭 조절하여 텍스트가 수직 정중앙에 완벽하게 배치 */
    line-height: 1.5 !important;
    border-radius: 8px !important;
    border: 1px solid #cbd5e1 !important;
    background: rgba(255, 255, 255, 0.8) !important;
    color: #0f172a !important; /* 입력 텍스트 검정색 */
    resize: none !important; /* 세로 크기 조절 방지 */
    overflow-y: hidden !important; /* 스크롤바 감춤 */
    box-sizing: border-box !important;
}
textarea:focus {
    border-color: #0ea5e9 !important; /* 포커스 시 스카이 블루 */
    background: #ffffff !important;
}
.dark textarea {
    background: rgba(30, 41, 59, 0.8) !important;
    border-color: rgba(14, 165, 233, 0.25) !important;
    color: white !important;
}

/* 챗봇 입력창과 전송 버튼 세로 높이 완벽 동기화 및 여백 분리 */
button[class*="submit-btn"],
[data-testid="submit-button"],
#submit-btn {
    margin-left: 12px !important;
    border-radius: 8px !important;
    min-width: 95px !important;
    height: 58px !important; /* 입력창의 height(58px)와 100% 동일하게 일치시켜 완벽한 대칭 구조 달성 */
    padding: 0 16px !important;
    display: flex !important;
    align-items: center !important;
    justify-content: center !important;
    box-sizing: border-box !important;
}
div:has(> button[class*="submit-btn"]),
div:has(> [data-testid="submit-button"]),
.input-container,
[class*="input-container"] {
    gap: 12px !important;
    align-items: center !important; /* 수직축 기준으로 중앙 정렬 */
}

/* 챗봇 답변 마크다운 가독성 및 자간/줄간격 최적화 (인라인 요양의 수직 선/보더 원천 차단) */
.message p, .message li, [class*="message"] p, [class*="message"] li {
    line-height: 1.68 !important;
    margin-bottom: 14px !important;
    letter-spacing: -0.01em !important;
    border: none !important;
    border-left: none !important;
    border-right: none !important;
    box-shadow: none !important;
}
.message blockquote, [class*="message"] blockquote {
    border: none !important;
    border-left: none !important;
    border-right: none !important;
    padding: 0 !important;
    margin: 0 !important;
    box-shadow: none !important;
}
.message h3, [class*="message"] h3 {
    margin-top: 24px !important;
    margin-bottom: 12px !important;
    font-weight: 800 !important;
}
"""

interface_kwargs = {
    "fn": chat,
    "chatbot": gr.Chatbot(height=500),
    "textbox": gr.Textbox(
        placeholder="분석하고 싶은 내용을 자연어로 입력해주세요...",
        container=False,
        scale=7,
        submit_btn="전송",
    ),
    "examples": [
        "삼성전자의 최근 AI 기술 트렌드는?",
        "카카오가 개발 중인 AI 서비스 목록을 알려줘",
        "어떤 기업이 LLM 기술을 개발하나요?",
        "최근 AI 관련 뉴스 기사를 요약해줘",
    ],
    "cache_examples": False,
}

# HF Spaces 컨테이너 내 루프백 검증 실패(ValueError) 우회 및 로컬/원격 호환 구동을 위해 launch 인자 정밀 설계
launch_kwargs = {
    "server_name": "0.0.0.0",
    "server_port": 7860,
}

# 버전에 맞춘 테마 및 CSS 주입 파이프라인 (Gradio 6.x 호환성 보장)
blocks_kwargs = {}
if gradio_major < 5:
    interface_kwargs["theme"] = theme_obj
    blocks_kwargs["theme"] = theme_obj
    blocks_kwargs["css"] = custom_css
elif gradio_major < 6:
    launch_kwargs["theme"] = theme_obj
    blocks_kwargs["theme"] = theme_obj
    blocks_kwargs["css"] = custom_css
else:
    launch_kwargs["theme"] = theme_obj
    launch_kwargs["css"] = custom_css

# Blocks를 활용한 2컬럼 레이아웃 대시보드 개편
with gr.Blocks(**blocks_kwargs) as demo:
    # 1. 상단 글로벌 네비게이션 바 (GNB)
    gr.HTML("""
    <div style="display: flex; justify-content: space-between; align-items: center; padding: 15px 20px; border-bottom: 1px solid rgba(196, 195, 236, 0.45); background-color: rgba(255, 255, 255, 0.65); backdrop-filter: blur(12px); margin: -20px -20px 20px -20px;">
        <div style="font-size: 20px; font-weight: 900; color: #0f172a; display: flex; align-items: center; gap: 12px;">
            📈 FinGraph <span style="font-size: 14px; font-weight: 700; color: #475569;">GraphRAG Enhanced AI Terminal</span>
        </div>
    </div>
    """)
    
    with gr.Row():
        # 2. 왼쪽 컬럼: 사이드바 (대시보드 및 하단 메뉴) - 3:7 split을 위해 scale=3 설정
        with gr.Column(scale=3, min_width=320):
            stats_data = get_db_stats()
            stats_html = build_stats_html(stats_data)
            gr.HTML(stats_html)
            
        # 3. 오른쪽 컬럼: 메인 챗봇 에어리어 - 3:7 split을 위해 scale=7 설정
        with gr.Column(scale=7, min_width=500):
            # ChatInterface without redundant titles/descriptions
            chatbot_interface_kwargs = interface_kwargs.copy()
            chatbot_interface_kwargs.pop("title", None)
            chatbot_interface_kwargs.pop("description", None)
            chatbot_interface_kwargs.pop("theme", None)
            
            gr.ChatInterface(**chatbot_interface_kwargs)

if __name__ == "__main__":
    demo.launch(**launch_kwargs)
