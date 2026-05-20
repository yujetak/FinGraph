# -*- coding: utf-8 -*-
"""FinGraph UI Templates and Styling Assets.
This module houses all custom CSS and HTML templates used by the main Gradio
application to keep the main app.py clean and readable.
"""

from typing import Any, Dict

# ── 남색 팔레트 (Navy Blue) ──────────────────────────────────────
# 주 텍스트: #1e3a5f  /  보조: #3b5a82  /  연한: #6b8ab0
# 강조(바이올렛): #7c3aed  /  포인트 테두리: rgba(124,58,237,0.15)

# ── 1. 커스텀 CSS ────────────────────────────────────────────────
CUSTOM_CSS: str = """
/* ── Google Fonts 로드 ── */
@import url('https://fonts.googleapis.com/css2?family=Sora:wght@400;600;700;800&family=JetBrains+Mono:wght@400;500&family=Inter:wght@400;600&display=swap');

/* ── 전체 배경 / 기본 폰트 / 화면 너비 확대 ── */
body, .gradio-container {
    background-color: #F6F5FA !important;
    font-family: 'Sora', 'Inter', -apple-system, BlinkMacSystemFont, sans-serif !important;
    color: #1e3a5f !important;
}
.gradio-container {
    max-width: 1400px !important;
    width: 95% !important;
    margin: 0 auto !important;
}

/* ── Ambient glow ── */
.ambient-glow {
    position: fixed;
    top: 0; left: 0; right: 0; bottom: 0;
    background:
        radial-gradient(circle at 80% 10%, rgba(124,58,237,0.05) 0%, transparent 40%),
        radial-gradient(circle at 20% 90%, rgba(12,217,247,0.05) 0%, transparent 40%);
    z-index: -1;
    pointer-events: none;
}

/* ── 사이드바 전체 컨테이너 ── */
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

/* ── 구분선 ── */
.divider {
    border: none;
    border-top: 1px solid #e2e8f0;
    margin: 14px 0;
}

/* ── 패널 라벨 (섹션 제목) ── */
.panel-label {
    font-size: 11px;
    font-weight: 700;
    color: #64748b;
    text-transform: uppercase;
    letter-spacing: 0.07em;
    margin-bottom: 10px;
}

/* ── 상단 2 카드 (가로 배치) ── */
.top-cards {
    display: grid;
    grid-template-columns: repeat(2, 1fr);
    gap: 10px;
    margin-bottom: 12px;
}
.top-card {
    background: #f8fafc !important;
    border: 1px solid #e2e8f0 !important;
    border-radius: 10px !important;
    padding: 14px 14px 12px !important;
}
.top-card-lbl {
    font-size: 11px;
    font-weight: 600;
    color: #64748b;
    margin-bottom: 5px;
}
.top-card-val {
    font-size: 22px;
    font-weight: 800;
    color: #1e293b;
    line-height: 1.1;
}
.top-card-sub {
    font-size: 10px;
    color: #94a3b8;
    margin-top: 3px;
}

/* ── 인사이트 행 ── */
.insight-row {
    display: grid;
    grid-template-columns: repeat(2, 1fr);
    gap: 10px;
    margin-bottom: 16px;
}
.insight-card {
    background: #f0f4ff !important;
    border: 1px solid #c7d2fe !important;
    border-radius: 9px !important;
    padding: 10px 12px !important;
}
.insight-lbl {
    font-size: 10px;
    font-weight: 700;
    color: #6366f1;
    text-transform: uppercase;
    letter-spacing: 0.05em;
    margin-bottom: 4px;
}
.insight-val {
    font-size: 13px;
    font-weight: 700;
    color: #1e293b;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
}

/* ── 주요 기술 키워드 배지 (배경색 없음, 연한 보라 텍스트 개편) ── */
.keyword-container {
    display: flex;
    flex-wrap: wrap;
    gap: 6px;
    margin-bottom: 14px;
}
.keyword-badge {
    display: inline-block;
    background: transparent !important;
    border: 1px solid #ddd6fe !important;
    border-radius: 9999px !important;
    padding: 4px 12px !important;
    font-size: 11px !important;
    font-weight: 600 !important;
    color: #8b5cf6 !important;
}
.keyword-badge-first {
    background: transparent !important;
    color: #8b5cf6 !important;
    border: 1px solid #ddd6fe !important;
}

/* ── 회사 키워드 배지 (키워드 배지와 동일한 색, 크기, 배경색으로 통일) ── */
.company-badge-container {
    display: flex;
    flex-wrap: wrap;
    gap: 6px;
    margin-bottom: 14px;
}
.company-badge {
    display: inline-block;
    background: transparent !important;
    border: 1px solid #ddd6fe !important;
    border-radius: 9999px !important;
    padding: 4px 12px !important;
    font-size: 11px !important;
    font-weight: 600 !important;
    color: #8b5cf6 !important;
}
.company-badge-first {
    background: transparent !important;
    color: #8b5cf6 !important;
    border: 1px solid #ddd6fe !important;
}

/* ── 최신 뉴스 피드 ── */
.news-feed-container {
    flex-grow: 1 !important;
    max-height: 250px !important;
    overflow-y: auto !important;
}
.news-feed-container::-webkit-scrollbar { width: 3px; }
.news-feed-container::-webkit-scrollbar-track { background: transparent; }
.news-feed-container::-webkit-scrollbar-thumb {
    background: #cbd5e1;
    border-radius: 2px;
}
.news-item-link {
    text-decoration: none;
    display: block;
    margin-bottom: 8px;
}
.news-item-link:last-child { margin-bottom: 0; }
.news-item {
    border-left: 3px solid #6366f1 !important;
    padding: 10px 12px !important;
    background: #f8fafc !important;
    border-radius: 0 8px 8px 0 !important;
    transition: all 0.18s ease !important;
}
.news-item-link:hover .news-item {
    background: #ffffff !important;
    border-left-color: #06b6d4 !important;
    transform: translateX(3px) !important;
    box-shadow: 0 2px 8px rgba(0,0,0,0.06) !important;
}
.news-title {
    font-size: 13px !important;
    font-weight: 600 !important;
    color: #1e293b !important;
    line-height: 1.45 !important;
    white-space: normal;
    display: -webkit-box;
    -webkit-line-clamp: 2;
    -webkit-box-orient: vertical;
    overflow: hidden;
}
.news-meta {
    font-size: 11px !important;
    color: #94a3b8 !important;
    margin-top: 4px;
}

/* ── 챗봇 컨테이너 테두리 제거 ── */
div[data-testid="chatbot"], .chatbot-container, .chatbot {
    border: none !important;
}

/* ── 챗봇 내부 Placeholder(소개글 영역) 상단 짤림 영구 차단 ── */
.placeholder, [class*="placeholder"] {
    display: flex !important;
    flex-direction: column !important;
    align-items: center !important;
    justify-content: flex-start !important;
    padding-top: 40px !important;
    height: 100% !important;
    min-height: 400px !important;
    flex-grow: 1 !important; 
    overflow: auto !important; 
    margin: 0 auto !important;
}

/* ── 소개글(Prose) 웰컴 보드 (위쪽 절반) ── */
.placeholder .prose {
    background: #f8fafc !important;
    border: 1px solid #e2e8f0 !important;
    border-bottom: none !important;
    border-radius: 12px 12px 0 0 !important;
    padding: 24px 24px 10px 24px !important; 
    max-width: 800px !important;
    width: 100% !important;
    margin: 0 auto !important; 
    display: block !important;
    position: relative !important;
    z-index: 2 !important;
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
    max-width: 800px !important;
    margin: -32px auto 40px auto !important;
    background: #f8fafc !important;
    border: 1px solid #e2e8f0 !important;
    border-top: none !important;
    border-radius: 0 0 12px 12px !important;
    padding: 10px 24px 24px 24px !important; 
    box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.05) !important; 
    position: relative !important;
    z-index: 1 !important;
}

/* 개별 버튼 디자인 (연보라색 테마 & 강력한 중앙 정렬) */
.examples-container button, div[data-testid="chatbot"] button.example, button.example, .example-btn {
    border-radius: 8px !important;
    padding: 16px !important;
    text-align: center !important;
    font-size: 14px !important;
    font-weight: 600 !important;
    color: #4c1d95 !important; 
    background: #f5f3ff !important;
    background-color: #f5f3ff !important;
    border: 1px solid #e9d5ff !important; 
    box-shadow: 0 1px 2px rgba(0, 0, 0, 0.05) !important;
    transition: all 0.2s ease-in-out !important;
    display: flex !important;
    align-items: center !important;
    justify-content: center !important;
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

/* ── 전송 버튼: 너비 넓고 높이 입력창에 맞춤 ── */
button[class*="submit-btn"], #submit-btn, button[id*="submit"], button.submit-button {
    background: linear-gradient(135deg, #1e3a5f 0%, #7c3aed 100%) !important;
    color: white !important;
    font-weight: 700 !important;
    font-size: 13px !important;
    border: none !important;
    border-radius: 8px !important;
    box-shadow: 0 2px 10px rgba(30,58,95,0.18) !important;
    transition: all 0.16s ease !important;
    cursor: pointer !important;
    height: 46px !important;
    min-width: 68px !important;
    max-width: 88px !important;
    padding: 0 16px !important;
    display: flex !important;
    align-items: center !important;
    justify-content: center !important;
    box-sizing: border-box !important;
    opacity: 1 !important;
    visibility: visible !important;
}
button[class*="submit-btn"]:hover,
[data-testid="submit-button"]:hover {
    background: linear-gradient(135deg, #2a4f82 0%, #8b47ff 100%) !important;
    box-shadow: 0 4px 16px rgba(124,58,237,0.24) !important;
    transform: translateY(-1px) !important;
}

/* ── 입력창 ── */
textarea,
[class*="input-container"] textarea,
[data-testid="textbox"] textarea {
    height: 46px !important;
    min-height: 46px !important;
    max-height: 46px !important;
    font-size: 13px !important;
    padding: 14px 14px !important;
    line-height: 1.5 !important;
    border-radius: 8px !important;
    border: 1px solid rgba(30,58,95,0.15) !important;
    background: rgba(255,255,255,0.80) !important;
    color: #1e3a5f !important;
    resize: none !important;
    overflow-y: hidden !important;
    box-sizing: border-box !important;
}
textarea:focus {
    border-color: #7c3aed !important;
    background: rgba(255,255,255,0.97) !important;
    box-shadow: 0 0 0 3px rgba(124,58,237,0.09) !important;
    outline: none !important;
}
div:has(> button[class*="submit-btn"]),
div:has(> [data-testid="submit-button"]),
.input-container, [class*="input-container"] {
    gap: 9px !important;
    align-items: center !important;
}

/* ── 챗봇 탭/라벨 숨김 ── */
.chatbot > div:first-child, [class*="chatbot"] > div:first-child,
.chatbot-label, div[class*="chatbot"] .label,
[data-testid="chatbot"] .label, .chatbot-header,
.gr-panel-title, .gr-chatbot-label,
[data-testid="chatbot"] > div:first-child,
label.svelte-1ipelgc, span.svelte-1ipelgc {
    display: none !important;
}

/* ── 메시지 버블 기본 크기 축소 (사용자/봇 공통 세로 높이 최적화) ── */
.message,
.message-wrap .message,
[data-testid="user-message"],
[data-testid="bot-message"] {
    padding: 10px 14px !important;
    min-height: auto !important;
}

/* ── 사용자 버블 (다크그레이 프리미엄 테마) ── */
.message.user,
.message.user-message,
[data-testid="user-message"] {
    background-color: #111827 !important;
    border-radius: 12px 12px 0 12px !important;
    padding: 10px 14px !important; 
    margin: 2px 0 !important; 
    border: none !important;
    box-shadow: 0 2px 5px rgba(0, 0, 0, 0.08) !important;
    color: #ffffff !important;
}
.message.user *,
.message.user-message *,
[data-testid="user-message"] * {
    color: #ffffff !important;
    line-height: 1.4 !important; 
    margin: 0 !important; 
    background: transparent !important;
}

/* ── 봇 버블 (화이트 & 그레이 경계선 테마) ── */
.message.bot,
.message.bot-message,
[data-testid="bot-message"] {
    background-color: #ffffff !important;
    color: #1f2937 !important;
    border: 1px solid #e5e7eb !important;
    border-radius: 12px 12px 12px 0 !important;
    padding: 16px 20px !important;
    box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.05) !important;
}
.message.bot *,
.message.bot-message *,
[data-testid="bot-message"] * {
    color: #1e3a5f !important;
    background: transparent !important;
}

/* ── 메시지 내부 여백 완전 제어 ── */
.message p, .message li,
[class*="message"] p, [class*="message"] li {
    line-height: 1.55 !important;
    margin: 0 !important;
    margin-bottom: 6px !important;
    padding: 0 !important;
    border: none !important;
    border-left: none !important;
    box-shadow: none !important;
    background: transparent !important;
    color: #1e3a5f !important;
}
.message p:last-child, .message li:last-child {
    margin-bottom: 0 !important;
}
.message blockquote, [class*="message"] blockquote {
    border: none !important;
    border-left: none !important;
    padding: 0 !important;
    margin: 0 !important;
    background: transparent !important;
}
.message h3, [class*="message"] h3 {
    margin-top: 14px !important;
    margin-bottom: 6px !important;
    font-weight: 800 !important;
    color: #1e3a5f !important;
}

/* ── 전역 링크 / CSS 변수 ── */
:root {
    --color-accent: #7c3aed !important;
    --primary-500: #7c3aed !important;
    --primary-600: #6d28d9 !important;
}
a { color: #7c3aed !important; }

/* ── secondary 버튼 ── */
button.secondary, button.lg.secondary, button.sm.secondary,
button.wrap, button.variant-secondary, .secondary-btn {
    background-color: rgba(255,255,255,0.75) !important;
    color: #1e3a5f !important;
    border: 1px solid rgba(30,58,95,0.13) !important;
    font-weight: 600 !important;
    transition: all 0.16s ease !important;
}
button.secondary:hover, button.variant-secondary:hover {
    background-color: rgba(255,255,255,0.97) !important;
    border-color: rgba(124,58,237,0.24) !important;
}

/* ── 메인 레이아웃 컬럼 높이 동기화 ── */
#main-row { align-items: stretch !important; }
#main-row > div[class*="column"] {
    display: flex !important;
    flex-direction: column !important;
}

/* ── 왼쪽 패널 너비 오버플로우 완전 차단 ── */
.sidebar-container * {
    max-width: 100% !important;
    box-sizing: border-box !important;
    word-break: break-word !important;
    overflow-wrap: break-word !important;
}

/* ── 엄지 피드백 버튼 숨김 ── */
.feedback-area,
[data-testid="like-dislike"],
.like-dislike-area,
.message-buttons,
.chatbot-action-buttons,
button[aria-label="Good response"],
button[aria-label="Bad response"],
button[aria-label="thumbs up"],
button[aria-label="thumbs down"],
.bot + div > div > button,
.svelte-1ed2p3z { display: none !important; }

/* ── Gradio 6.x Chatbot 내부 오버플로우 및 스크롤바 최적화 ── */
div[data-testid="chatbot"] .message-wrap,
div[data-testid="chatbot"] .message-container,
div[data-testid="chatbot"] > div.wrapper,
div[data-testid="chatbot"] > div.scrollbar {
    overflow-y: auto !important;
    max-height: 600px !important;
}
"""


def build_stats_html(stats: Dict[str, Any]) -> str:
    """왼쪽 사이드바 전체 HTML 생성.

    구성:
    - 상단 2 카드 (분석 모델 / 기억수)
    - 구분선
    - 회사 키워드 배지 (5개)
    - 구분선
    - 뉴스 키워드 배지
    - 구분선
    - 최신 뉴스 피드
    """
    # ── 회사 키워드 배지 (5개) ───────────────────────────
    company_html = ""
    for idx, c in enumerate(stats.get("companies_list", [])):
        css = "company-badge company-badge-first" if idx == 0 else "company-badge"
        company_html += f'<span class="{css}"># {c["name"]}</span>\n'
    if not company_html:
        company_html = '<span style="font-size:10px;color:#6b8ab0;">등록된 회사 없음</span>'

    # ── 뉴스 키워드 배지 ──────────────────────────────
    keyword_html = ""
    for idx, t in enumerate(stats.get("techs_list", [])):
        css = "keyword-badge keyword-badge-first" if idx == 0 else "keyword-badge"
        keyword_html += f'<span class="{css}"># {t["name"]}</span>\n'
    if not keyword_html:
        keyword_html = '<span style="font-size:10px;color:#6b8ab0;">키워드 없음</span>'

    # ── 최신 뉴스 피드 ──────────────────────────────
    news_html = ""
    for a in stats.get("recent_articles", []):
        title = a["title"] or ""
        url = a["url"] if a["url"] and str(a["url"]).lower() != "nan" else "#"
        target = 'target="_blank"' if url != "#" else ""
        date_str = str(a["date"])[:10] if a["date"] else ""
        news_html += f"""
        <a class="news-item-link" href="{url}" {target}>
            <div class="news-item">
                <div class="news-title">{title}</div>
                <div class="news-meta">{date_str}</div>
            </div>
        </a>"""
    if not news_html:
        news_html = '<div style="font-size:10px;color:#6b8ab0;">기사를 불러오는 중...</div>'

    return f"""
    <div class="sidebar-container">

        <!-- 상단 2 카드 -->
        <div class="top-cards">
            <div class="top-card">
                <div class="top-card-lbl">🤖 분석 모델</div>
                <div class="top-card-val">GPT-4o</div>
                <div class="top-card-sub">초거대 AI 엔진</div>
            </div>
            <div class="top-card">
                <div class="top-card-lbl">🏢 대상 기업</div>
                <div class="top-card-val">{stats["companies"]}곳</div>
                <div class="top-card-sub">그래프 내 기업</div>
            </div>
        </div>

        <hr class="divider">

        <!-- 회사 키워드 -->
        <div class="panel-label">🏢 주요 대상 기업</div>
        <div class="company-badge-container">
            {company_html}
        </div>

        <hr class="divider">

        <!-- 뉴스 키워드 -->
        <div class="panel-label">🏷️ 주요 기술 키워드</div>
        <div class="keyword-container">
            {keyword_html}
        </div>

        <hr class="divider">

        <!-- 최신 뉴스 피드 -->
        <div class="panel-label">📡 최신 뉴스</div>
        <div class="news-feed-container">
            {news_html}
        </div>
    </div>
    """