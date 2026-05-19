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

            # 2. 기술 목록 & 설명 조회 (상위 25개)
            res_tech_list = session.run(
                "MATCH (t:AITechnology) "
                "RETURN t.name as name, COALESCE(t.description, 'AI 혁신 기술 인프라') as desc LIMIT 25"
            )
            stats["techs_list"] = [{"name": r["name"], "desc": r["desc"]} for r in res_tech_list]

            # 3. 최근 기사 목록 조회 (최근 15개)
            res_art_list = session.run(
                "MATCH (a:Article) "
                "RETURN a.title as title, a.published_date as date, a.url as url "
                "ORDER BY a.published_date DESC LIMIT 15"
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

    # 2. 최근 기사 리스트 HTML 생성 (최대 3개) - 전체 영역 클릭 시 이동하도록 a 태그로 래핑
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
        
        <div style="font-size: 16px; font-weight: 850; color: #5b5b7f; margin-bottom: 2px; display: flex; align-items: center; gap: 6px; letter-spacing: -0.02em;">
            📊 <span>FinGraph AI Terminal</span>
        </div>
        <p style="font-size: 11px; color: #47464e; margin-top: -2px; margin-bottom: 12px; font-weight: 500;">GraphRAG 실시간 분석 엔진</p>
        
        <div class="stats-grid">
            <div class="stat-card">
                <div class="stat-lbl">📰 학습 기사</div>
                <div class="stat-val">{stats['articles']}건</div>
            </div>
            <div class="stat-card">
                <div class="stat-lbl">🧬 지식 노드</div>
                <div class="stat-val">{node_count}개</div>
            </div>
        </div>
        
        <div class="section-subtitle">💡 최신 뉴스 키워드</div>
        <div class="keyword-container">
            {keyword_html}
        </div>
        
        <div class="section-subtitle">📰 최신 뉴스 피드</div>
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
    primary_hue="purple",
    secondary_hue="slate",
)

custom_css: str = """
body {
    background-color: #fbf9f6;
    font-family: 'Pretendard', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif !important;
}

/* Ambient glow point backgrounds */
.ambient-glow {
    position: fixed;
    top: 0; left: 0; right: 0; bottom: 0;
    background: radial-gradient(circle at 85% 15%, rgba(196, 195, 236, 0.35) 0%, transparent 45%), 
                radial-gradient(circle at 15% 85%, rgba(180, 200, 225, 0.3) 0%, transparent 45%);
    z-index: -1;
    pointer-events: none;
}

/* 대시보드 투명 퍼플 글래스모피즘 컨테이너 */
.dashboard-container {
    background: rgba(245, 243, 240, 0.45) !important;
    backdrop-filter: blur(24px) !important;
    -webkit-backdrop-filter: blur(24px) !important;
    border: 1px solid rgba(196, 195, 236, 0.45) !important;
    border-radius: 12px;
    padding: 16px;
    box-shadow: 0 4px 12px -2px rgba(88, 89, 125, 0.05) !important;
    font-family: 'Pretendard', -apple-system, BlinkMacSystemFont, sans-serif;
}
.dark .dashboard-container {
    background: rgba(15, 23, 42, 0.55) !important;
    border-color: rgba(129, 140, 248, 0.25) !important;
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
    background: rgba(255, 255, 255, 0.7);
    border: 1px solid rgba(196, 195, 236, 0.4);
    border-radius: 8px;
    padding: 10px;
    text-align: center;
    box-shadow: 0 1px 3px rgba(88, 89, 125, 0.02);
    transition: all 0.25s ease-in-out;
}
.stat-card:hover {
    transform: translateY(-2px);
    background: rgba(255, 255, 255, 0.9);
    border-color: rgba(91, 91, 127, 0.6);
    box-shadow: 0 4px 12px -2px rgba(88, 89, 125, 0.1);
}
.dark .stat-card {
    background: rgba(30, 41, 59, 0.7);
    border-color: rgba(129, 140, 248, 0.2);
    color: #f1f5f9;
}
.dark .stat-card:hover {
    border-color: rgba(129, 140, 248, 0.5);
}
.stat-val {
    font-size: 16px !important;
    font-weight: 850 !important;
    color: #5b5b7f; /* 투명 퍼플 에디션 포인트 색상 */
    margin-top: 2px;
}
.dark .stat-val {
    color: #c4c3ec;
}
.stat-lbl {
    font-size: 11px !important;
    color: #47464e;
    font-weight: 600;
}
.dark .stat-lbl {
    color: #94a3b8;
}

/* 최신 뉴스 키워드 컨테이너 및 둥근 배지 스타일 */
.keyword-container {
    display: flex;
    flex-wrap: wrap;
    gap: 8px;
    margin-bottom: 12px;
}
.keyword-badge {
    display: inline-block;
    background: rgba(196, 195, 236, 0.2);
    border: 1px solid rgba(196, 195, 236, 0.55);
    border-radius: 8px; /* 이전처럼 약간 둥근 네모 */
    padding: 6px 12px;
    font-size: 11px !important;
    font-weight: 700;
    color: #5b5b7f;
    box-shadow: 0 1px 3px rgba(88, 89, 125, 0.02);
    transition: all 0.2s ease-in-out;
}
.keyword-badge:hover {
    background: rgba(196, 195, 236, 0.35);
    transform: scale(1.03);
}
.dark .keyword-badge {
    background: rgba(129, 140, 248, 0.12);
    border-color: rgba(129, 140, 248, 0.25);
    color: #c4c3ec;
}

/* 최근 뉴스 피드 클릭 가능한 카드 레이아웃 */
.news-feed-container {
    max-height: 350px;
    overflow-y: auto;
    border: 1px solid rgba(196, 195, 236, 0.35);
    border-radius: 6px;
    padding: 8px;
    background: rgba(255, 255, 255, 0.5);
}
.dark .news-feed-container {
    background: rgba(30, 41, 59, 0.5);
    border-color: rgba(129, 140, 248, 0.15);
}
/* 스크롤바 커스텀 */
.news-feed-container::-webkit-scrollbar {
    width: 4px;
}
.news-feed-container::-webkit-scrollbar-track {
    background: transparent;
}
.news-feed-container::-webkit-scrollbar-thumb {
    background: rgba(91, 91, 127, 0.3);
    border-radius: 2px;
}
.dark .news-feed-container::-webkit-scrollbar-thumb {
    background: rgba(196, 195, 236, 0.3);
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
    border-left: 3px solid #5b5b7f; /* 퍼플 포인트 */
    padding: 8px 10px;
    background: rgba(255, 255, 255, 0.4);
    border-radius: 0 6px 6px 0;
    transition: all 0.2s ease-in-out;
    cursor: pointer;
}
.news-item-link:hover .news-item {
    background: rgba(255, 255, 255, 0.85);
    border-left-color: #434466;
    transform: translateX(3px);
    box-shadow: 0 2px 6px rgba(91, 91, 127, 0.08);
}
.dark .news-item {
    background: rgba(30, 41, 59, 0.3);
}
.dark .news-item-link:hover .news-item {
    background: rgba(30, 41, 59, 0.65);
    border-left-color: rgba(129, 140, 248, 0.6);
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

/* 서브타이틀 헤더 스타일 */
.section-subtitle {
    font-size: 13px !important;
    font-weight: 750;
    color: #1b1c1a;
    margin: 15px 0 6px 0;
    border-bottom: 1px solid rgba(196, 195, 236, 0.35);
    padding-bottom: 4px;
    display: flex;
    align-items: center;
    gap: 4px;
}
.dark .section-subtitle {
    color: #f8fafc;
    border-color: rgba(129, 140, 248, 0.2);
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
    background: rgba(255, 255, 255, 0.75) !important;
    border: 1px solid rgba(196, 195, 236, 0.5) !important;
    border-radius: 8px !important;
    font-size: 12px !important;
    font-weight: 600 !important;
    color: #47464e !important;
    line-height: 1.4 !important;
    box-shadow: 0 2px 5px rgba(88, 89, 125, 0.03) !important;
    transition: all 0.2s cubic-bezier(0.4, 0, 0.2, 1) !important;
    white-space: normal !important;
    height: auto !important;
    min-height: 54px !important;
    cursor: pointer !important;
}
.dark [class*="examples"] button {
    background: rgba(30, 41, 59, 0.75) !important;
    border-color: rgba(129, 140, 248, 0.25) !important;
    color: #cbd5e1 !important;
}
[class*="examples"] button:hover {
    transform: translateY(-2px) !important;
    background: rgba(255, 255, 255, 0.95) !important;
    border-color: #5b5b7f !important;
    box-shadow: 0 6px 12px rgba(91, 91, 127, 0.15) !important;
}
.dark [class*="examples"] button:hover {
    background: rgba(30, 41, 59, 0.95) !important;
    border-color: rgba(129, 140, 248, 0.6) !important;
}

/* 챗봇 버튼 퍼플 포인트 스타일 (흰색으로 안 보이던 현상 해결) */
button.primary, 
.primary-btn, 
button.lg.primary, 
button.sm.primary,
button.variant-primary {
    background-color: #5b5b7f !important;
    color: white !important;
    font-weight: 800 !important;
    border: none !important;
    box-shadow: 0 4px 6px rgba(91, 91, 127, 0.2) !important;
    transition: all 0.2s ease-in-out !important;
}
button.primary:hover, 
.primary-btn:hover, 
button.variant-primary:hover {
    background-color: #434466 !important;
    box-shadow: 0 6px 12px rgba(91, 91, 127, 0.3) !important;
    transform: translateY(-1px) !important;
}

/* secondary 및 기타 유틸리티 버튼 스타일 */
button.secondary, 
button.lg.secondary, 
button.sm.secondary, 
button.wrap,
button.variant-secondary,
.secondary-btn {
    background-color: rgba(255, 255, 255, 0.6) !important;
    color: #47464e !important;
    border: 1px solid rgba(196, 195, 236, 0.45) !important;
    font-weight: 700 !important;
    transition: all 0.2s ease-in-out !important;
    backdrop-filter: blur(8px);
}
.dark button.secondary, 
.dark button.variant-secondary, 
.dark .secondary-btn {
    background-color: rgba(30, 41, 59, 0.6) !important;
    color: #f1f5f9 !important;
    border-color: rgba(129, 140, 248, 0.2) !important;
}
button.secondary:hover, 
button.variant-secondary:hover,
.secondary-btn:hover {
    background-color: rgba(255, 255, 255, 0.95) !important;
    color: #1b1c1a !important;
    border-color: rgba(91, 91, 127, 0.5) !important;
}
.dark button.secondary:hover, 
.dark button.variant-secondary:hover {
    background-color: rgba(30, 41, 59, 0.95) !important;
    color: white !important;
    border-color: rgba(129, 140, 248, 0.4) !important;
}
"""

interface_kwargs = {
    "fn": chat,
    "chatbot": gr.Chatbot(height=500),
    "textbox": gr.Textbox(
        placeholder="분석하고 싶은 내용을 자연어로 입력해주세요...",
        container=False,
        scale=7,
        submit_btn="전송 📤",
    ),
    "title": "FinGraph — GraphRAG AI Terminal",
    "description": "> 최신 AI 뉴스를 기반으로 구축된 지식 그래프(GraphRAG)에서 답변합니다.",
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
        <div style="font-size: 20px; font-weight: 900; color: #5b5b7f; display: flex; align-items: center; gap: 12px;">
            FinGraph <span style="font-size: 14px; font-weight: 600; color: #5b5b7f;">GraphRAG Enhanced AI Terminal</span>
        </div>
        <div style="display: flex; gap: 18px; color: #5b5b7f; font-size: 18px; cursor: pointer;">
            <span>🔔</span> <span>⚙️</span> <span>👤</span>
        </div>
    </div>
    """)
    
    with gr.Row():
        # 2. 왼쪽 컬럼: 사이드바 (대시보드 및 하단 메뉴) - 4:6 split을 위해 scale=4 설정
        with gr.Column(scale=4, min_width=350):
            stats_data = get_db_stats()
            stats_html = build_stats_html(stats_data)
            gr.HTML(stats_html)
            
        # 3. 오른쪽 컬럼: 메인 챗봇 에어리어 - 4:6 split을 위해 scale=6 설정
        with gr.Column(scale=6, min_width=500):
            # 메인 타이틀 (챗봇 영역 상단 중앙)
            gr.HTML("""
            <div style="text-align: center; padding: 10px 0 20px 0;">
                <h2 style="font-size: 18px; font-weight: 800; color: #5b5b7f; margin-bottom: 5px;">FinGraph — GraphRAG AI Terminal</h2>
                <p style="color: #47464e; font-size: 13px;">최신 AI 뉴스를 기반으로 구축된 지식 그래프(GraphRAG)에서 답변합니다.</p>
            </div>
            """)
            
            # ChatInterface without redundant titles/descriptions
            chatbot_interface_kwargs = interface_kwargs.copy()
            chatbot_interface_kwargs.pop("title", None)
            chatbot_interface_kwargs.pop("description", None)
            chatbot_interface_kwargs.pop("theme", None)
            
            gr.ChatInterface(**chatbot_interface_kwargs)

if __name__ == "__main__":
    demo.launch(**launch_kwargs)
