import re
import time
from collections import Counter
from datetime import datetime, timedelta

import pandas as pd
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from webdriver_manager.chrome import ChromeDriverManager

# 수집 대상 카테고리 sid
categories_sid = {
    "경제": "101",
    "IT/과학": "105",
}
NUM_ARTICLES_PER_DATE_CAT = 15  # 날짜별/카테고리별 목표 수집량 (7일 * 2개 카테고리 * 15 = 최대 210건 링크 파싱)

# AI 핀테크 키워드 (FinNode 프로젝트 전용)
FINTECH_AI_KEYWORDS = [
    # AI 기술
    "AI",
    "인공지능",
    "생성형 AI",
    "대규모언어모델",
    # AI 핀테크 (금융)
    "핀테크",
]

print("[INIT] ChromeDriver 초기화 중...")
service = Service(ChromeDriverManager().install())
options = webdriver.ChromeOptions()
options.add_argument("--no-sandbox")
options.add_argument("--disable-dev-shm-usage")
options.add_argument("--headless")  # 속도 및 안정성 극대화를 위해 headless 모드 활성화
driver = webdriver.Chrome(service=service, options=options)
print("[INIT] ✅ 브라우저 실행 완료")


def get_article_links(driver, sid: str, target_date: str, num_articles: int) -> list[str]:
    article_links: list[str] = []
    # 20개씩 끊어서 페이지별 직접 로드하여 속도를 10배 이상 향상시킵니다
    max_pages = (num_articles // 20) + 1

    selectors = [
        ".list_body a",
        "ul.type06_headline a",
        "ul.type06 a",
        "a.sa_text_title",
        ".sa_text a",
    ]

    for page in range(1, max_pages + 1):
        page_url = f"https://news.naver.com/main/list.naver?mode=LSD&mid=sec&sid1={sid}&date={target_date}&page={page}"
        print(f"  [LINK] 페이지 이동 (Page {page}): {page_url}")
        try:
            driver.get(page_url)
            time.sleep(1.5)
        except Exception as e:
            print(f"    [LINK] ⚠️ 페이지 로드 오류 (스킵): {e}")
            continue

        found_in_page = 0
        for selector in selectors:
            elements = driver.find_elements(By.CSS_SELECTOR, selector)
            for element in elements:
                try:
                    url = element.get_attribute("href")
                    if (
                        url
                        and "news.naver.com" in url
                        and "/article/" in url
                        and "/comment/" not in url
                        and url not in article_links
                    ):
                        article_links.append(url)
                        found_in_page += 1
                        if len(article_links) >= num_articles:
                            break
                except Exception:
                    continue
            if len(article_links) >= num_articles:
                break

        print(f"    -> Page {page}에서 {found_in_page}개 기사 링크 확보 (누적: {len(article_links)}개)")
        if len(article_links) >= num_articles or found_in_page == 0:
            break

    print(f"  [LINK] ✅ {target_date} 일자 총 {len(article_links)}개 링크 확보\n")
    return article_links[:num_articles]


def parse_article_detail(driver, article_url, category):
    driver.get(article_url)
    time.sleep(1.5)
    article_data = {
        "article_id": "",
        "title": "",
        "content": "",
        "url": article_url,
        "published_date": "",
        "source": "",
        "author": "",
        "category": category,
    }
    try:
        match = re.search(r"article/(\d+)/(\d+)", article_url)
        article_data["article_id"] = (
            f"ART_{match.group(1)}_{match.group(2)}" if match else f"ART_{datetime.now().strftime('%Y%m%d%H%M%S')}"
        )
        for sel in [
            "#title_area span",
            "#ct .media_end_head_headline",
            ".media_end_head_headline",
            "h2#title_area",
            ".news_end_title",
        ]:
            try:
                el = driver.find_element(By.CSS_SELECTOR, sel)
                if el.text.strip():
                    article_data["title"] = el.text.strip()
                    break
            except:
                continue
        for sel in [
            "#dic_area",
            "article#dic_area",
            ".go_trans._article_content",
            "._article_body_contents",
        ]:
            try:
                el = driver.find_element(By.CSS_SELECTOR, sel)
                if el.text.strip():
                    article_data["content"] = el.text.strip()
                    break
            except:
                continue
        try:
            el = driver.find_element(By.CSS_SELECTOR, "a.media_end_head_top_logo img")
            article_data["source"] = el.get_attribute("alt")
        except:
            try:
                el = driver.find_element(By.CSS_SELECTOR, ".media_end_head_top_logo_text")
                article_data["source"] = el.text.strip()
            except:
                pass
        try:
            el = driver.find_element(
                By.CSS_SELECTOR,
                "span.media_end_head_info_datestamp_time, span[data-date-time]",
            )
            article_data["published_date"] = (el.get_attribute("data-date-time") or el.text).strip()
        except:
            article_data["published_date"] = datetime.now().strftime("%Y-%m-%d %H:%M")
        try:
            el = driver.find_element(
                By.CSS_SELECTOR,
                "em.media_end_head_journalist_name, span.byline_s",
            )
            article_data["author"] = el.text.strip()
        except:
            pass
    except Exception as e:
        print(f"    [PARSE] ⚠️  파싱 오류: {e}")
    return article_data


# ── 1단계: 전체 기사 수집 ──
all_articles = []
category_stats = {}

# 오늘부터 7일 전까지의 날짜 리스트 생성
target_dates = [(datetime.now() - timedelta(days=i)).strftime("%Y%m%d") for i in range(7)]

print(f"[CRAWL] 📅 대상 수집 날짜 (7일): {target_dates}")

for target_date in target_dates:
    print(f"\n{'=' * 60}")
    print(f"[CRAWL] 📅 {target_date} 일자 수집 시작")
    print(f"{'=' * 60}")

    for category_name, sid in categories_sid.items():
        print(f"\n  [CRAWL] [{category_name} - {target_date}] 카테고리 수집 시작")
        
        # 날짜별/카테고리별 목표 수집량
        article_links = get_article_links(driver, sid, target_date, NUM_ARTICLES_PER_DATE_CAT)

        cat_key = f"{category_name}_{target_date}"
        cat_ok, cat_fail = 0, 0
        
        for idx, article_url in enumerate(article_links, 1):
            print(f"    [PARSE] ({idx}/{len(article_links)}) {article_url[:70]}...")
            article_data = parse_article_detail(driver, article_url, category_name)

            if article_data["title"] and article_data["content"]:
                # 만약 파싱된 published_date가 비었거나 이상하다면 target_date 기반으로 날짜 형식 설정
                if not article_data["published_date"] or "202" not in article_data["published_date"]:
                    formatted_date = f"{target_date[:4]}-{target_date[4:6]}-{target_date[6:]} 09:00"
                    article_data["published_date"] = formatted_date
                
                all_articles.append(article_data)
                cat_ok += 1
                print(f"      ✅ {article_data['title'][:40]}...")
                print(f"         언론사: {article_data['source']} | 날짜: {article_data['published_date']}")
            else:
                cat_fail += 1
                missing = [
                    x
                    for x, v in [
                        ("제목", article_data["title"]),
                        ("본문", article_data["content"]),
                    ]
                    if not v
                ]
                print(f"      ❌ 파싱실패 ({', '.join(missing)} 없음)")
            time.sleep(0.5)

        category_stats[cat_key] = {"ok": cat_ok, "fail": cat_fail}
        print(f"\n    [CRAWL] [{category_name} - {target_date}] 완료: 성공 {cat_ok}개 / 실패 {cat_fail}개")

driver.quit()
print("\n[DONE] 브라우저 종료")
print(f"\n{'=' * 60}")
print("[SUMMARY] 수집 결과 Summary")
print(f"{'=' * 60}")
total_ok = 0
total_fail = 0
for cat_key, s in category_stats.items():
    print(f"  {cat_key}: 성공 {s['ok']}건 / 실패 {s['fail']}건")
    total_ok += s['ok']
    total_fail += s['fail']
print(f"  전체 수집: 성공 {total_ok}건 / 실패 {total_fail}건")

df_all = pd.DataFrame(all_articles)


# ── 2단계: AI 핀테크 키워드 필터링 ──
print(f"\n{'=' * 60}")
print("[FILTER] AI 핀테크 키워드 필터링 시작")
print(f"{'=' * 60}")

filtered_articles = []
for _, row in df_all.iterrows():
    text = f"{row['title']} {row['content']}"
    matched = [kw for kw in FINTECH_AI_KEYWORDS if kw.replace(" ", "") in text.replace(" ", "")]
    if matched:
        row_dict = row.to_dict()
        row_dict["matched_keywords"] = ", ".join(matched)
        filtered_articles.append(row_dict)

df_filtered = pd.DataFrame(filtered_articles)

print(f"  전체 수집: {len(df_all)}건")
print(f"  AI 핀테크 관련: {len(df_filtered)}건 ({len(df_filtered) / max(len(df_all), 1) * 100:.1f}%)")
print("\n  [키워드별 매칭 현황]")
all_kw = [kw for row in filtered_articles for kw in row["matched_keywords"].split(", ")]
kw_counts = Counter(all_kw)
for kw in FINTECH_AI_KEYWORDS:
    print(f"    {kw}: {kw_counts.get(kw, 0)}건")

df_filtered

# ── 3단계: 저장 ──
import os

output_dir = os.path.join("src", "graphBuilder", "scrapping")
os.makedirs(output_dir, exist_ok=True)
output_filename = os.path.join(output_dir, f"Articles_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx")
df_filtered.to_excel(output_filename, index=False, engine="openpyxl")
print(f"[SAVE] ✅ 저장 완료: {output_filename}")
print(f"[SAVE]    - AI 핀테크 기사: {len(df_filtered)}건")


# ── 4단계: 키워드 빈도 시각화 ──
try:
    import platform
    from collections import Counter

    import matplotlib.pyplot as plt

    # 폰트 깨짐 방지 (Mac 환경: AppleGothic)
    if platform.system() == "Darwin":
        plt.rc("font", family="AppleGothic")
    plt.rcParams["axes.unicode_minus"] = False

    if not filtered_articles:
        print("시각화할 데이터가 없습니다.")
    else:
        # 빈도수 계산
        all_kw = [kw for row in filtered_articles for kw in row["matched_keywords"].split(", ")]
        kw_counts = Counter(all_kw)

        # 📌 변경 포인트: FINTECH_AI_KEYWORDS 전체 목록을 순서대로 그래프에 강제 표시 (0건 포함)
        keywords = FINTECH_AI_KEYWORDS
        counts = [kw_counts.get(kw, 0) for kw in keywords]

        plt.figure(figsize=(12, 6))

        # 막대 그래프 생성
        bars = plt.bar(keywords, counts, color="skyblue", edgecolor="white")

        # 막대 위에 숫자(빈도수) 표시
        for bar in bars:
            height = bar.get_height()
            # 막대의 중앙(x), 막대의 높이(y) 위치에 텍스트를 배치
            plt.text(
                bar.get_x() + bar.get_width() / 2.0,
                height,
                f"{height}",
                ha="center",
                va="bottom",
                size=11,
                fontweight="bold",
                color="black",
            )

        plt.title("수집된 AI 핀테크 기사 키워드 출현 빈도 (전체)", fontsize=15, pad=15)
        plt.xlabel("키워드", fontsize=12)
        plt.ylabel("출현 횟수 (건)", fontsize=12)
        plt.grid(axis="y", linestyle="--", alpha=0.7)
        plt.xticks(rotation=45)
        plt.tight_layout()
        plt.show()
except ImportError:
    print("[INFO] matplotlib 라이브러리가 설치되어 있지 않아 시각화 단계를 건너뜁니다.")

