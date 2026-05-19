"""
app.py — FinNode GraphRAG 챗봇
================================
Hugging Face Spaces 배포 진입점.
Gradio ChatInterface + LangGraph 기반 대화 흐름 제어.

실행:
    python app.py
"""

from typing import List, TypedDict

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
    print("✅ [자가 진단 완료] Neo4j AuraDB 지식 그래프에 완벽하게 접속되었습니다!")
except Exception as e:
    print(f"❌ [자가 진단 실패] Neo4j DB 연결 확인 중 에러가 발생했습니다: {e}")
    raise e

# ──────────────────────────────────────────
# 1. LangGraph 챗봇 State 정의
# ──────────────────────────────────────────


class ChatState(TypedDict):
    question: str        # 사용자 질문
    history: List[dict]  # 대화 히스토리 [{"role": "user"/"assistant", "content": "..."}]
    context: str         # GraphRAG 검색 결과
    answer: str          # 최종 답변


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


# ──────────────────────────────────────────
# 5. Gradio UI 구성
# ──────────────────────────────────────────

with gr.Blocks(
    title="FinNode — AI 기업 트렌드 분석 챗봇",
    theme=gr.themes.Soft(primary_hue="indigo"),
) as demo:
    gr.Markdown(
        """
        # 🔗 FinNode — AI 기업 트렌드 분석 챗봇
        > 최신 AI 뉴스를 기반으로 구축된 지식 그래프(GraphRAG)에서 답변합니다.

        **예시 질문**
        - 삼성전자의 최근 AI 기술 트렌드는?
        - 카카오가 개발 중인 AI 서비스 목록을 알려줘
        - 어떤 기업이 LLM 기술을 개발하나요?
        - 최근 AI 관련 뉴스 기사를 요약해줘
        """
    )

    chatbot = gr.ChatInterface(
        fn=chat,
        chatbot=gr.Chatbot(
            height=500,
            placeholder="질문을 입력하면 지식 그래프에서 답변을 찾아드립니다.",
        ),
        textbox=gr.Textbox(
            placeholder="예: 네이버의 AI 기술 트렌드는 무엇인가요?",
            container=False,
            scale=7,
        ),
        examples=[
            "삼성전자의 최근 AI 기술 트렌드는?",
            "카카오가 개발 중인 AI 서비스 목록을 알려줘",
            "어떤 기업이 LLM 기술을 개발하나요?",
            "최근 AI 관련 뉴스 기사를 요약해줘",
        ],
        cache_examples=False,
    )

if __name__ == "__main__":
    demo.launch(server_name="0.0.0.0", server_port=7860)
