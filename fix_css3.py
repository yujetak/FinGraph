import sys

with open('app.py', 'r', encoding='utf-8') as f:
    lines = f.readlines()

start_idx = -1
for i, line in enumerate(lines):
    if 'FINAL_CSS = CUSTOM_CSS + """' in line:
        start_idx = i
        break

if start_idx == -1:
    print('Cannot find FINAL_CSS')
    sys.exit(1)

clean_css = '''FINAL_CSS = CUSTOM_CSS + """
/* ── 전체 화면 너비 확대 ── */
.gradio-container {
    max-width: 1400px !important;
    width: 95% !important;
    margin: 0 auto !important;
}

/* ── 챗봇 컨테이너 테두리 제거 ── */
div[data-testid="chatbot"], .chatbot-container, .chatbot {
    border: none !important;
    overflow: visible !important; 
}

/* ── 챗봇 내부 Placeholder(소개글 영역) 상단 짤림 영구 차단 ── */
.placeholder, [class*="placeholder"] {
    display: flex !important;
    flex-direction: column !important;
    align-items: center !important;
    justify-content: flex-start !important; /* 항상 위에서부터 뿌림 */
    padding-top: 40px !important; /* 상단 여백 넉넉히 주어 짤림 절대 불가 */
    height: 100% !important; /* 전체 높이 사용 */
    min-height: 400px !important;
    flex-grow: 1 !important; 
    overflow: visible !important; 
    margin: 0 auto !important;
}

/* ── 소개글(Prose) 웰컴 보드 (위쪽 절반) ── */
.placeholder .prose {
    background: #f8fafc !important; /* 쿨톤 회색 */
    border: 1px solid #e2e8f0 !important;
    border-bottom: none !important; /* 아래쪽 경계선 제거로 결합 준비 */
    border-radius: 12px 12px 0 0 !important; /* 아래쪽 모서리 직각으로 펴서 결합 준비 */
    padding: 24px 24px 10px 24px !important; 
    max-width: 800px !important; /* 800px 고정너비 */
    width: 100% !important;
    margin: 0 auto !important; 
    display: block !important;
    position: relative !important;
    z-index: 2 !important; /* 아래쪽 컨테이너 위로 살짝 덮게 함 */
}
.placeholder h3, [class*="placeholder"] h3 {
    color: #334155 !important; 
    font-weight: 800 !important;
    margin-top: 0 !important;
    margin-bottom: 12px !important;
}
.placeholder .prose ul {
    list-style-type: none !important;
    padding-left: 0 !important;
    margin-bottom: 12px !important;
}
.placeholder .prose li {
    margin-bottom: 4px !important; 
    color: #475569 !important;
    font-size: 14px !important;
    line-height: 1.5 !important;
}
.placeholder .prose p:last-child {
    font-weight: 700 !important;
    color: #4c1d95 !important; 
    background: #f3e8ff !important; 
    padding: 8px 16px !important;
    border-radius: 8px !important;
    display: inline-block !important;
    margin-bottom: 0 !important;
}

/* ── 예시 질문 컨테이너 (아래쪽 절반: 보드 병합 완료) ── */
[class*="examples"], .gr-samples-wrapper, .examples-container {
    display: grid !important;
    grid-template-columns: repeat(2, 1fr) !important;
    gap: 12px !important;
    width: 100% !important;
    max-width: 800px !important; /* 소개글과 800px 너비 일치 */
    
    /* 🌟 핵심: 위쪽 보드와 완벽 결합을 위한 마이너스 마진 🌟 */
    margin: -32px auto 40px auto !important; /* 32px 갭 제거 (Gradio 기본 갭) */
    
    background: #f8fafc !important; /* 소개글과 동일한 회색 배경 */
    border: 1px solid #e2e8f0 !important;
    border-top: none !important; /* 위쪽 경계선 제거 */
    border-radius: 0 0 12px 12px !important; /* 위쪽 모서리 직각으로 펴서 결합 완료 */
    padding: 10px 24px 24px 24px !important; 
    box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.05) !important; 
    position: relative !important;
    z-index: 1 !important; /* 위쪽 컨테이너 밑으로 겹치게 하여 흰줄 완전 소멸 */
}

/* 개별 버튼 디자인 (연보라색 테마 & 강력한 중앙 정렬) */
.examples-container button, div[data-testid="chatbot"] button.example, button.example, .example-btn {
    border-radius: 8px !important;
    padding: 16px !important;
    text-align: center !important; /* 텍스트 가운데 정렬 */
    font-size: 14px !important;
    font-weight: 600 !important;
    color: #4c1d95 !important; 
    background: #f5f3ff !important; /* 진짜 연보라색 배경 */
    background-color: #f5f3ff !important; /* 덮어쓰기 철벽 방어 */
    border: 1px solid #e9d5ff !important; 
    box-shadow: 0 1px 2px rgba(0, 0, 0, 0.05) !important;
    transition: all 0.2s ease-in-out !important;
    display: flex !important;
    align-items: center !important;
    justify-content: center !important; /* 완벽 중앙 배치 */
    min-height: 80px !important; 
    width: 100% !important;
    white-space: normal !important; 
}

.examples-container button:hover, div[data-testid="chatbot"] button.example:hover, button.example:hover, .example-btn:hover {
    border-color: #a855f7 !important; 
    background: #f3e8ff !important; 
    background-color: #f3e8ff !important; 
    transform: translateY(-2px) !important;
    box-shadow: 0 4px 6px rgba(0, 0, 0, 0.08) !important;
    color: #7c3aed !important;
}

/* ── 메시지 말풍선 정리 ── */
.message.user, [data-testid="user"] .message {
    background-color: #111827 !important;
    border-radius: 12px 12px 0 12px !important;
    padding: 7px 13px !important; 
    margin: 2px 0 !important; 
    border: none !important;
    box-shadow: 0 2px 5px rgba(0, 0, 0, 0.08) !important;
    min-height: unset !important; 
}
[data-testid="user"] > div, .bubble-wrap [data-testid="user"], .message-wrap.user > div, .message-row.user {
    background: transparent !important;
    background-color: transparent !important;
    border: none !important;
}
[data-testid="user"] .message *, .message.user * {
    color: #ffffff !important;
    line-height: 1.4 !important; 
    margin: 0 !important; 
}
[data-testid="bot"] .message, [data-testid="bot"] > div, .message-wrap.bot > div, .message.bot, .message-row.bot .message {
    background-color: #ffffff !important;
    color: #1f2937 !important;
    border: 1px solid #e5e7eb !important;
    border-radius: 12px 12px 12px 0 !important;
    padding: 16px 20px !important;
    box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.05) !important;
}

/* ── 피드백 및 전송 버튼 ── */
.message-buttons, button[aria-label="Good response"], button[aria-label="Bad response"], .like-dislike-area { display: none !important; }
button[class*="submit-btn"], #submit-btn, button[id*="submit"], button.submit-button {
    background: linear-gradient(135deg, #1e3a5f 0%, #7c3aed 100%) !important;
    color: white !important;
    border-radius: 8px !important;
    font-weight: bold !important;
    border: none !important;
    display: block !important;
    opacity: 1 !important;
    visibility: visible !important;
}

/* ── 메인 레이아웃 사이드바 균형 최적화 ── */
.sidebar-container {
    border: 1px solid #e2e8f0 !important;
    border-radius: 12px !important;
    padding: 24px 20px !important;
    background: #ffffff !important;
    height: 700px !important; 
    box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.04) !important;
    display: flex !important;
    flex-direction: column !important;
}
.news-feed-container {
    flex-grow: 1 !important;
    max-height: 250px !important;
    overflow-y: auto !important;
}
"""
'''

before_lines = lines[:start_idx]
final_content = ''.join(before_lines) + clean_css

with open('app.py', 'w', encoding='utf-8') as f:
    f.write(final_content)

print('Clean CSS recovery done!')
