import sys

with open('app.py', 'r', encoding='utf-8') as f:
    lines = f.readlines()

# 157번째 라인부터 문제가 생김 (res_comp = session.run(...))
# 156번째 라인은 '# 상위 5개 회사 키워드 리스트업 추가' 임
cut_idx = -1
for i, line in enumerate(lines):
    if '# 상위 5개 회사 키워드 리스트업 추가' in line:
        cut_idx = i
        break

if cut_idx == -1:
    print("Cannot find cut index!")
    sys.exit(1)

# 그 아래로 launch_kwargs = { 가 있는 라인을 찾음
end_idx = -1
for i in range(cut_idx, len(lines)):
    if 'launch_kwargs = {' in line or 'launch_kwargs =' in lines[i]:
        end_idx = i
        break

if end_idx == -1:
    print("Cannot find end index!")
    sys.exit(1)

before_lines = lines[:cut_idx + 1]
after_lines = lines[end_idx:]

correct_middle = '''            res_comp = session.run(
                "MATCH (c:AICompany) "
                "OPTIONAL MATCH (a:Article)-[:MENTIONS]->(c) "
                "RETURN c.name as name, count(a) as cnt "
                "ORDER BY cnt DESC LIMIT 5"
            )
            stats["companies_list"] = [{"name": row["name"]} for row in res_comp]

            res_art = session.run(
                "MATCH (a:Article) "
                "RETURN a.title as title, a.published_date as date, a.url as url "
                "ORDER BY a.published_date DESC LIMIT 4"
            )
            stats["recent_articles"] = [
                {"title": r["title"], "date": r["date"], "url": r["url"]}
                for r in res_art
            ]
    except Exception as e:
        print(f"⚠️ [통계 조회 실패] {e}")
    return stats


# ──────────────────────────────────────────
# 5. Gradio UI 구성
# ──────────────────────────────────────────

theme_obj = gr.themes.Soft(primary_hue="indigo", secondary_hue="slate")

CHATBOT_DESCRIPTION = """
### 🌌 국내 AI 뉴스 기사를 기반으로 구축된 지식 그래프(GraphRAG)에 질문하세요.

- 📰 **기업별 AI 트렌드** — 삼성, 카카오, 네이버 등 주요 기업의 최신 AI 동향
- 🔬 **기술 키워드 분석** — LLM, 생성형 AI, 파운데이션 모델 등 핵심 기술 정리
- 🔗 **실제 뉴스 출처 제공** — 답변마다 근거 기사 링크 포함

👇 **아래 예시 질문 버튼을 클릭하거나 직접 입력해 보세요.**
"""

FINAL_CSS = CUSTOM_CSS + """
/* ── 전체 화면 너비 대폭 확대 ── */
.gradio-container {
    max-width: 1400px !important;
    width: 95% !important;
    margin: 0 auto !important;
}

/* ── 챗봇 컨테이너 테두리 및 짤림(Overflow) 방지 ── */
div[data-testid="chatbot"], .chatbot-container, .chatbot {
    border: none !important;
    overflow: visible !important; 
}

/* ── 챗봇 내부 Placeholder(소개글 영역) 위쪽 짤림 영구 방어 ── */
.placeholder, [class*="placeholder"] {
    display: flex !important;
    flex-direction: column !important;
    align-items: center !important;
    justify-content: flex-start !important; /* 위쪽 짤림 방지 */
    padding-top: 5% !important; /* 위에서 살짝 내림 */
    height: 50% !important; 
    flex-grow: 0 !important; 
    overflow: visible !important; 
    margin: 0 auto !important;
}

/* ── 소개글(Prose) 아이보리/쿨톤 회색 웰컴 카드 ── */
.placeholder .prose {
    background: #f8fafc !important; /* 대시보드 카드와 동일한 색상 */
    border: 1px solid #e2e8f0 !important;
    border-radius: 12px !important;
    padding: 16px 24px !important; /* 높이 세이브 */
    box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.05) !important;
    max-width: 700px !important;
    margin: 0 auto 12px auto !important;
    display: block !important;
    height: auto !important;
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

/* ── 예시 질문 컨테이너 (그리드 배치) ── */
[class*="examples"], .gr-samples-wrapper, .examples-container {
    display: grid !important;
    grid-template-columns: repeat(2, 1fr) !important;
    gap: 12px !important;
    width: 100% !important;
    max-width: 900px !important; /* 잘림 방지 */
    margin: 0 auto 40px auto !important;
    background: transparent !important;
    border: none !important;
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
    white-space: normal !important; /* 두줄 허용하되 900px 덕분에 보통 한 줄로 나옴 */
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

final_content = "".join(before_lines) + "\n" + correct_middle + "\n" + "".join(after_lines)

with open('app.py', 'w', encoding='utf-8') as f:
    f.write(final_content)

print("APP.PY PERFECTLY RECOVERED AND UPDATED!")
