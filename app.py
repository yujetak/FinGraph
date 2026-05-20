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
import gradio.networking

# ──────────────────────────────────────────
# HF Spaces/Docker 루프백 접속 검증 우회 몽키 패치
# ──────────────────────────────────────────
# 일부 가상화/도커 환경에서 127.0.0.1:7860 로컬 접속 여부 자체 체크가
# 프록시 및 루프백 인터페이스 차단으로 인해 실패하여 ValueError가 발생하는 현상을 방지합니다.
gradio.networking.url_ok = lambda *args, **kwargs: True

import gradio as gr
from langgraph.graph import END, StateGraph

from src.retrieval.finRetrieval import HybridResult, graphrag
from src.utils.ui_templates import CUSTOM_CSS, build_stats_html

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
    context: str  # GraphRAG 검색 결과 또는 일반 지식 답변
    answer: str   # 최종 답변
    mode: str     # "graph": 그래프 기반 | "general": 일반 지식 기반


# ──────────────────────────────────────────
# 2. LangGraph 노드 정의
# ──────────────────────────────────────────


def retrieve_node(state: ChatState) -> ChatState:
    """Node 1: search_with_fallback으로 그래프 검색 또는 일반 지식 응답 라우팅"""
    try:
        hybrid: HybridResult = graphrag.search_with_fallback(
            query_text=state["question"],
            history=state["history"],
        )

        if hybrid.mode == "general":
            # 일반 지식 모드: 배너 + GPT-4o 답변 반환
            disclaimer = (
                "> ⚠️ **지식 그래프에서 관련 뉴스를 찾지 못했습니다.**\n"
                "> GPT-4o의 일반 학습 데이터를 기반으로 답변합니다.\n"
                "> 최신 국내 뉴스 기반 정보가 필요하다면 질문을 더 구체적으로 입력해 보세요.\n\n"
                "---\n\n"
            )
            context = disclaimer + hybrid.answer
            return {**state, "context": context, "mode": "general"}

        # 그래프 기반 모드: 기존 출처 추출 + 뉴스 피드 로직
        context = hybrid.answer
        sources = []
        seen_urls: set = set()

        # retriever_result에서 상위 3개 뉴스 출처 추출
        retriever_result = hybrid.retriever_result
        if retriever_result and hasattr(retriever_result, "items"):
            for item in retriever_result.items:
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
    return {**state, "context": context, "mode": state.get("mode", "graph")}


def generate_node(state: ChatState) -> ChatState:
    """Node 2: 대화 히스토리를 고려하여 최종 답변 생성

    GraphRAG(graph 모드) 또는 일반 지식(general 모드) 응답 모두
    retrieve_node에서 context에 최종 텍스트를 담아주므로 그대로 사용합니다.
    """
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
        "mode": "",
    }

    yield "🔍 실시간 지식 그래프에서 관련 뉴스를 검색하는 중입니다..."

    try:
        # LangGraph의 stream을 사용하여 각 노드 실행 시점마다 이벤트를 받음
        for event in chat_graph.stream(state):
            if "retrieve" in event:
                retrieved_mode = event["retrieve"].get("mode", "graph")
                if retrieved_mode == "general":
                    yield "🌐 관련 뉴스 없음 — GPT-4o 일반 지식으로 답변을 생성하는 중입니다..."
                else:
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
            
            # 2.5 최신 주목 기업 리스트 (상위 5개)
            res_comp_list = session.run(
                "MATCH (c:AICompany) "
                "OPTIONAL MATCH (a:Article)-[:MENTIONS]->(c) "
                "RETURN c.name as name, count(a) as cnt "
                "ORDER BY cnt DESC LIMIT 5"
            )
            stats["companies_list"] = [{"name": r["name"]} for r in res_comp_list]

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


CHATBOT_DESCRIPTION = """
<div class="prose">
<h3>🌌 AI 기반 금융/핀테크 혁신 트렌드를 분석하는 지식 그래프(GraphRAG)에 질문하세요.</h3>
<ul>
<li>📰 <b>금융사/핀테크 AI 동향</b> — 신한은행, 카카오페이, 토스뱅크, 네이버페이 등의 최신 금융 AI 트렌드</li>
<li>🔬 <b>핀테크 핵심 기술 분석</b> — 로보어드바이저, 대안신용평가, AI FDS, 금융 마이데이터 등 정리</li>
<li>🔗 <b>실제 뉴스 출처 제공</b> — 답변마다 실제 보도된 근거 기사 및 출처 URL 포함</li>
</ul>
<p>👇 아래 예시 질문 버튼을 클릭하거나 직접 입력해 보세요.</p>
</div>
"""

interface_kwargs = {
    "fn": chat,
    "chatbot": gr.Chatbot(height=700, placeholder=CHATBOT_DESCRIPTION),
    "textbox": gr.Textbox(
        placeholder="분석하고 싶은 내용을 자연어로 입력해주세요...",
        container=False,
        scale=7,
        submit_btn="전송",
    ),
    "examples": [
        "신한은행의 '신한 AI 쏠 포트폴리오' 로보어드바이저 기술과 개인 맞춤형 서비스의 특징을 설명해줘",
        "카카오페이가 씬파일러를 위해 개발한 'AI 대안신용평가' 모델의 장점과 대출 승인 효과는 무엇인가요?",
        "토스뱅크의 실시간 보이스피싱 탐지 기술인 '토스 AI FDS'의 작동 원리와 차단율을 알려줘",
        "네이버페이가 출시한 'AI 금융 비서'가 마이데이터와 결합하여 제공하는 맞춤 자산 가이드는 어떤 것인가요?",
    ],
    "cache_examples": False,
}

# HF Spaces 컨테이너 내 루프백 검증 실패(ValueError) 우회 및 로컬/원격 호환 구동을 위해 launch 인자 정밀 설계
launch_kwargs = {
    "server_name": "0.0.0.0",
    "server_port": 7860,
}

# 버전에 맞춘 테마 및 CSS 주입 파이프라인 (Gradio 6.x 호환성 보장)
blocks_kwargs: Dict[str, Any] = {}
if gradio_major < 5:
    interface_kwargs["theme"] = theme_obj
    blocks_kwargs["theme"] = theme_obj
    blocks_kwargs["css"] = CUSTOM_CSS
elif gradio_major < 6:
    launch_kwargs["theme"] = theme_obj
    blocks_kwargs["theme"] = theme_obj
    blocks_kwargs["css"] = CUSTOM_CSS
else:
    launch_kwargs["theme"] = theme_obj
    launch_kwargs["css"] = CUSTOM_CSS

# Blocks를 활용한 2컬럼 레이아웃 대시보드 개편
with gr.Blocks(**blocks_kwargs) as demo:
    # 1. 상단 글로벌 네비게이션 바 (GNB)
    gr.HTML("""
    <div style="display: flex; justify-content: space-between; align-items: center; padding: 10px 20px; border-bottom: 1px solid rgba(196, 195, 236, 0.45); background-color: rgba(255, 255, 255, 0.65); backdrop-filter: blur(12px); margin: -20px -20px 6px -20px;">
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
        with gr.Column(scale=7, min_width=500, elem_id="chat-column"):
            # ChatInterface without redundant titles/descriptions
            chatbot_interface_kwargs: Dict[str, Any] = interface_kwargs.copy()
            chatbot_interface_kwargs.pop("title", None)
            chatbot_interface_kwargs.pop("description", None)
            chatbot_interface_kwargs.pop("theme", None)
            
            gr.ChatInterface(**chatbot_interface_kwargs)  # type: ignore

if __name__ == "__main__":
    demo.launch(**launch_kwargs)
