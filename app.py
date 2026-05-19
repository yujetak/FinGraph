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


def chat(message: str, history: list) -> str:
    """Gradio ChatInterface가 호출하는 함수.

    Args:
        message: 사용자 입력 메시지
        history: Gradio가 관리하는 대화 히스토리
                 [{"role": "user"/"assistant", "content": "..."}] 형식

    Returns:
        str: 챗봇 답변
    """
    if not message.strip():
        return "질문을 입력해 주세요."

    # Gradio history → LangGraph state 형식으로 변환
    state: ChatState = {
        "question": message,
        "history": history,
        "context": "",
        "answer": "",
    }

    result = chat_graph.invoke(state)
    return result["answer"]


def get_db_stats() -> Dict[str, Any]:
    """Neo4j 데이터베이스로부터 실시간 지식 그래프 통계 및 요약을 안전하게 조회합니다.

    Returns:
        Dict[str, Any]: 기사 건수, 기업 수, 기술 수, 서비스 수, 분야 수, 벡터 청크 수 및 세부 목록
    """
    stats: Dict[str, Any] = {
        "articles": 0,
        "companies": 0,
        "technologies": 0,
        "services": 0,
        "fields": 0,
        "chunks": 0,
        "companies_list": [],
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

            res_services = session.run("MATCH (s:AIService) RETURN count(s) as cnt").single()
            if res_services:
                stats["services"] = res_services["cnt"]

            res_fields = session.run("MATCH (f:AIField) RETURN count(f) as cnt").single()
            if res_fields:
                stats["fields"] = res_fields["cnt"]

            res_chunks = session.run("MATCH (c:Content) RETURN count(c) as cnt").single()
            if res_chunks:
                stats["chunks"] = res_chunks["cnt"]

            # 2. 기업 및 기술 목록 조회 (상위 15개)
            res_comp_list = session.run("MATCH (c:AICompany) RETURN c.name as name LIMIT 15")
            stats["companies_list"] = [r["name"] for r in res_comp_list]

            res_tech_list = session.run("MATCH (t:AITechnology) RETURN t.name as name LIMIT 15")
            stats["techs_list"] = [r["name"] for r in res_tech_list]

            # 3. 최근 기사 목록 조회 (최근 5개)
            res_art_list = session.run(
                "MATCH (a:Article) "
                "RETURN a.title as title, a.published_date as date, a.url as url "
                "ORDER BY a.published_date DESC LIMIT 5"
            )
            stats["recent_articles"] = [
                {"title": r["title"], "date": r["date"], "url": r["url"]}
                for r in res_art_list
            ]
    except Exception as e:
        print(f"⚠️ [통계 조회 실패] Neo4j 통계를 가져오는 데 실패했습니다: {e}")
    return stats


def build_stats_html(stats: Dict[str, Any]) -> str:
    """조회된 지식 그래프 통계 정보들을 바탕으로 미려한 대시보드용 HTML을 생성합니다.

    Args:
        stats: get_db_stats() 함수에서 반환된 통계 딕셔너리

    Returns:
        str: 스타일링된 완성형 HTML 소스코드
    """
    # 1. 기업 뱃지 HTML 생성
    comp_badges: str = ""
    for c in stats.get("companies_list", []):
        comp_badges += f'<span class="badge-item">{c}</span>'
    if not comp_badges:
        comp_badges = '<span style="font-size:12px; color:#94a3b8;">등록된 기업이 없습니다.</span>'

    # 2. 기술 뱃지 HTML 생성
    tech_badges: str = ""
    for t in stats.get("techs_list", []):
        tech_badges += f'<span class="badge-item tech-badge">{t}</span>'
    if not tech_badges:
        tech_badges = '<span style="font-size:12px; color:#94a3b8;">등록된 기술이 없습니다.</span>'

    # 3. 최근 기사 리스트 HTML 생성
    news_list_html: str = ""
    for a in stats.get("recent_articles", []):
        title = a["title"]
        url = a["url"] if a["url"] and str(a["url"]).lower() != "nan" else "#"
        target = 'target="_blank"' if url != "#" else ""
        news_list_html += f"""
        <div class="news-item">
            <a class="news-title" href="{url}" {target}>{title}</a>
            <div class="news-meta">🗓️ {a['date']} | 🔗 원문 보기</div>
        </div>
        """
    if not news_list_html:
        news_list_html = '<div style="font-size:12px; color:#94a3b8;">최근 수집된 기사가 없습니다.</div>'

    html: str = f"""
    <div class="dashboard-container">
        <div style="font-size: 17px; font-weight: 800; color: #4f46e5; margin-bottom: 8px; display: flex; align-items: center; gap: 8px;">
            📊 <span>지식 그래프 대시보드</span>
        </div>
        <p style="font-size: 12px; color: #64748b; margin-top: -4px; margin-bottom: 16px;">Neo4j AuraDB 실시간 엔티티 연동 통계</p>
        
        <div class="stats-grid">
            <div class="stat-card">
                <div class="stat-lbl">📰 뉴스 기사</div>
                <div class="stat-val">{stats['articles']}건</div>
            </div>
            <div class="stat-card">
                <div class="stat-lbl">🏢 분석 기업</div>
                <div class="stat-val">{stats['companies']}개</div>
            </div>
            <div class="stat-card">
                <div class="stat-lbl">💡 핵심 기술</div>
                <div class="stat-val">{stats['technologies']}개</div>
            </div>
            <div class="stat-card">
                <div class="stat-lbl">⚙️ 등록 서비스</div>
                <div class="stat-val">{stats['services']}개</div>
            </div>
            <div class="stat-card" style="grid-column: span 2;">
                <div class="stat-lbl">🧩 지식 벡터 밀도 (Graph Vector Density)</div>
                <div class="stat-val" style="color: #059669;">{stats['chunks']} Chunks</div>
            </div>
        </div>
        
        <div class="section-subtitle">🏢 주요 분석 기업</div>
        <div class="badge-container">
            {comp_badges}
        </div>
        
        <div class="section-subtitle">💡 주요 핵심 기술</div>
        <div class="badge-container">
            {tech_badges}
        </div>
        
        <div class="section-subtitle">📰 최신 실시간 뉴스 피드</div>
        <div class="news-feed">
            {news_list_html}
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
    font=[gr.themes.GoogleFont("Pretendard"), gr.themes.GoogleFont("Noto Sans KR"), "sans-serif"],
    primary_hue="indigo",
    secondary_hue="blue",
)

custom_css: str = """
/* 대시보드 메인 컨테이너 */
.dashboard-container {
    background-color: #f8fafc;
    border: 1px solid #e2e8f0;
    border-radius: 12px;
    padding: 20px;
    font-family: 'Pretendard', 'Noto Sans KR', sans-serif;
    box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.05), 0 2px 4px -1px rgba(0, 0, 0, 0.03);
}
.dark .dashboard-container {
    background-color: #0f172a;
    border-color: #1e293b;
}

/* 통계 그리드 및 카드 */
.stats-grid {
    display: grid;
    grid-template-columns: repeat(2, 1fr);
    gap: 12px;
    margin-bottom: 20px;
}
.stat-card {
    background: white;
    border: 1px solid #e2e8f0;
    border-radius: 8px;
    padding: 12px;
    text-align: center;
    box-shadow: 0 1px 3px rgba(0, 0, 0, 0.02);
    transition: all 0.2s ease-in-out;
}
.stat-card:hover {
    transform: translateY(-2px);
    box-shadow: 0 4px 6px rgba(0, 0, 0, 0.06);
}
.dark .stat-card {
    background: #1e293b;
    border-color: #334155;
    color: #f1f5f9;
}
.stat-val {
    font-size: 20px;
    font-weight: 800;
    color: #4f46e5;
    margin-top: 4px;
}
.dark .stat-val {
    color: #818cf8;
}
.stat-lbl {
    font-size: 11px;
    color: #64748b;
    font-weight: 500;
}
.dark .stat-lbl {
    color: #94a3b8;
}

/* 뱃지 리스트 스타일 */
.badge-container {
    display: flex;
    flex-wrap: wrap;
    gap: 6px;
    margin-bottom: 16px;
}
.badge-item {
    background-color: #e0e7ff;
    color: #3730a3;
    font-size: 11px;
    font-weight: 600;
    padding: 4px 10px;
    border-radius: 20px;
    border: 1px solid #c7d2fe;
    transition: all 0.2s;
}
.badge-item:hover {
    background-color: #4f46e5;
    color: white;
    transform: scale(1.05);
}
.dark .badge-item {
    background-color: #1e1b4b;
    color: #c7d2fe;
    border-color: #312e81;
}
.dark .badge-item:hover {
    background-color: #818cf8;
    color: #0f172a;
}

.tech-badge {
    background-color: #ecfdf5;
    color: #065f46;
    border-color: #a7f3d0;
}
.tech-badge:hover {
    background-color: #10b981;
    color: white;
}
.dark .tech-badge {
    background-color: #064e3b;
    color: #a7f3d0;
    border-color: #065f46;
}
.dark .tech-badge:hover {
    background-color: #34d399;
    color: #064e3b;
}

/* 최근 뉴스 타임라인 스타일 */
.news-feed {
    margin-top: 15px;
}
.news-item {
    border-left: 3px solid #6366f1;
    padding-left: 12px;
    margin-bottom: 12px;
    position: relative;
}
.news-title {
    font-size: 12px;
    font-weight: 600;
    color: #1e293b;
    text-decoration: none;
    line-height: 1.4;
    display: block;
}
.news-title:hover {
    color: #4f46e5;
    text-decoration: underline;
}
.dark .news-title {
    color: #cbd5e1;
}
.dark .news-title:hover {
    color: #818cf8;
}
.news-meta {
    font-size: 10px;
    color: #94a3b8;
    margin-top: 2px;
}

/* 서브타이틀 헤더 스타일 */
.section-subtitle {
    font-size: 13px;
    font-weight: 700;
    color: #0f172a;
    margin: 18px 0 10px 0;
    border-bottom: 2px solid #e2e8f0;
    padding-bottom: 6px;
    display: flex;
    align-items: center;
    gap: 6px;
}
.dark .section-subtitle {
    color: #f8fafc;
    border-color: #334155;
}

/* 챗봇 버튼 고대비화 스타일 (흰색으로 안 보이던 현상 해결) */
button.primary, 
.primary-btn, 
button.lg.primary, 
button.sm.primary,
button.variant-primary {
    background-color: #4f46e5 !important;
    color: white !important;
    font-weight: 800 !important;
    border: none !important;
    box-shadow: 0 4px 6px rgba(79, 70, 229, 0.2) !important;
    transition: all 0.2s ease-in-out !important;
}
button.primary:hover, 
.primary-btn:hover, 
button.variant-primary:hover {
    background-color: #4338ca !important;
    box-shadow: 0 6px 12px rgba(79, 70, 229, 0.3) !important;
    transform: translateY(-1px) !important;
}

/* secondary 및 기타 유틸리티 버튼 스타일 */
button.secondary, 
button.lg.secondary, 
button.sm.secondary, 
button.wrap,
button.variant-secondary,
.secondary-btn {
    background-color: #f1f5f9 !important;
    color: #334155 !important;
    border: 1px solid #cbd5e1 !important;
    font-weight: 700 !important;
    transition: all 0.2s ease-in-out !important;
}
.dark button.secondary, 
.dark button.variant-secondary, 
.dark .secondary-btn {
    background-color: #1e293b !important;
    color: #f1f5f9 !important;
    border-color: #475569 !important;
}
button.secondary:hover, 
button.variant-secondary:hover,
.secondary-btn:hover {
    background-color: #e2e8f0 !important;
    color: #0f172a !important;
}
.dark button.secondary:hover, 
.dark button.variant-secondary:hover {
    background-color: #334155 !important;
    color: white !important;
}
"""

interface_kwargs = {
    "fn": chat,
    "chatbot": gr.Chatbot(height=500),
    "textbox": gr.Textbox(
        placeholder="분석하고 싶은 내용을 자연어로 입력해주세요...",
        container=False,
        scale=7,
    ),
    "title": "FinNode — AI 기업 트렌드 분석 챗봇",
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
    <div style="display: flex; justify-content: space-between; align-items: center; padding: 15px 20px; border-bottom: 1px solid #e2e8f0; background-color: white; margin: -20px -20px 20px -20px;">
        <div style="font-size: 20px; font-weight: 900; color: #0f172a; display: flex; align-items: center; gap: 12px;">
            FinNode <span style="font-size: 14px; font-weight: 600; color: #4f46e5;">GraphRAG 기반 엔터프라이즈 분석</span>
        </div>
        <div style="display: flex; gap: 18px; color: #64748b; font-size: 18px; cursor: pointer;">
            <span>🔔</span> <span>⚙️</span> <span>👤</span>
        </div>
    </div>
    """)
    
    with gr.Row():
        # 2. 왼쪽 컬럼: 사이드바 (대시보드 및 하단 메뉴)
        with gr.Column(scale=1, min_width=300):
            stats_data = get_db_stats()
            stats_html = build_stats_html(stats_data)
            gr.HTML(stats_html)
            
            # 사이드바 하단 도움말/설정 메뉴
            gr.HTML("""
            <div style="margin-top: 15px; padding: 15px 20px; background-color: #f8fafc; border: 1px solid #e2e8f0; border-radius: 12px; font-size: 14px; color: #475569; display: flex; flex-direction: column; gap: 12px; box-shadow: 0 1px 3px rgba(0,0,0,0.02);">
                <div style="cursor: pointer; display: flex; align-items: center; gap: 8px; transition: color 0.2s;" onmouseover="this.style.color='#4f46e5'" onmouseout="this.style.color='#475569'">
                    <span style="font-size:16px;">❔</span> 도움말
                </div>
                <div style="cursor: pointer; display: flex; align-items: center; gap: 8px; transition: color 0.2s;" onmouseover="this.style.color='#4f46e5'" onmouseout="this.style.color='#475569'">
                    <span style="font-size:16px;">👤</span> 사용자 설정
                </div>
            </div>
            """)
            
        # 3. 오른쪽 컬럼: 메인 챗봇 에어리어
        with gr.Column(scale=3):
            # 메인 타이틀 (챗봇 영역 상단 중앙)
            gr.HTML("""
            <div style="text-align: center; padding: 10px 0 20px 0;">
                <h2 style="font-size: 18px; font-weight: 700; color: #334155; margin-bottom: 5px;">FinNode — AI 기업 트렌드 분석 챗봇</h2>
                <p style="color: #64748b; font-size: 13px;">최신 AI 뉴스를 기반으로 구축된 지식 그래프(GraphRAG)에서 답변합니다.</p>
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
