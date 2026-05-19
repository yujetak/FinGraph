"""
analyze_dates.py — 수집된 뉴스 기사 발행 일자 트렌드 분석 및 최적 갱신 주기 도출 스크립트
===================================================================================
"""

import glob
import os
import platform

import matplotlib.pyplot as plt
import pandas as pd


def run_analysis():
    # 1. 프로젝트 폴더의 모든 Articles_*.xlsx 기사 파일 로드
    files = glob.glob("Articles_*.xlsx")
    if not files:
        print("❌ 분석할 Articles_*.xlsx 파일이 로컬 디렉토리에 없습니다.")
        return

    print(f"📂 발견된 뉴스 기사 파일 목록: {files}")

    # 2. 데이터 병합 및 중복 제거
    dfs = []
    for f in files:
        try:
            df = pd.read_excel(f)
            dfs.append(df)
        except Exception as e:
            print(f"⚠️ {f} 로드 실패: {e}")

    if not dfs:
        print("❌ 유효한 기사 데이터가 없습니다.")
        return

    df_all = pd.concat(dfs, ignore_index=True)
    df_all = df_all.drop_duplicates(subset=["url"])  # 동일 기사 중복 제거
    print(f"📊 병합 완료된 고유 AI 핀테크 기사 총량: {len(df_all)}건")

    # 3. 날짜 파싱 및 정렬 (날짜 포맷 표준화)
    df_all["published_date"] = pd.to_datetime(df_all["published_date"], errors="coerce")
    df_all = df_all.dropna(subset=["published_date"])
    df_all = df_all.sort_values(by="published_date")

    # 일자만 추출하여 집계
    df_all["date_only"] = df_all["published_date"].dt.date
    date_counts = df_all.groupby("date_only").size().reset_index(name="count")

    # 4. 분석표 터미널 출력
    print("\n" + "=" * 50)
    print("📅 [일자별 AI 핀테크 기사 생산 트렌드 표]")
    print("=" * 50)
    print(date_counts.to_string(index=False))
    print("=" * 50)

    # 5. 수학적 분석 및 권장 주기 추천
    total_days = (date_counts["date_only"].max() - date_counts["date_only"].min()).days + 1
    total_articles = date_counts["count"].sum()
    avg_daily = total_articles / max(total_days, 1)

    print(f"⏱️  관측 기간: {total_days}일 ({date_counts['date_only'].min()} ~ {date_counts['date_only'].max()})")
    print(f"📈 일평균 AI 핀테크 뉴스 생산량: {avg_daily:.2f}건")

    # 일평균 볼륨에 따른 최적화 자동화 주기 추천 알고리즘
    if avg_daily >= 10:
        recommendation = "✨ 매일 1회 갱신 (하루 기사 생산량이 10건 이상으로 매우 많아, 실시간 트렌드 포착을 위해 매일 새벽 1시 자동화가 필수적입니다.)"
    elif avg_daily >= 3:
        recommendation = "✨ 2~3일에 1회 갱신 (기사가 2~3일 단위로 적당히 모였을 때 그래프를 빌드하는 것이 API 비용 대비 지식 밀도 상 가장 효율적입니다.)"
    else:
        recommendation = "✨ 5일~1주에 1회 갱신 (AI 핀테크 틈새 도메인 특성상 일일 발행량이 3건 미만으로 협소하므로, 5일 간격으로 몰아서 갱신하는 것이 합리적입니다.)"

    print("-" * 50)
    print("💡 [최적의 GraphRAG 자동화 주기 제안]")
    print(f"   {recommendation}")
    print("=" * 50 + "\n")

    # 6. 차트 시각화 및 이미지 파일 저장
    if platform.system() == "Darwin":
        plt.rc("font", family="AppleGothic")  # Mac 한글 폰트 깨짐 방지
    plt.rcParams["axes.unicode_minus"] = False

    plt.figure(figsize=(10, 5))
    bars = plt.bar(
        date_counts["date_only"].astype(str),
        date_counts["count"],
        color="royalblue",
        edgecolor="black",
        alpha=0.85,
    )

    # 막대 위에 숫자 표시
    for bar in bars:
        height = bar.get_height()
        plt.text(
            bar.get_x() + bar.get_width() / 2.0,
            height + 0.1,
            f"{int(height)}건",
            ha="center",
            va="bottom",
            fontsize=10,
            fontweight="bold",
        )

    plt.title("일자별 AI 핀테크 뉴스 생산 트렌드 분석", fontsize=15, pad=15, fontweight="bold")
    plt.xlabel("기사 발행 일자", fontsize=12)
    plt.ylabel("생산 건수", fontsize=12)
    plt.grid(axis="y", linestyle="--", alpha=0.5)
    plt.xticks(rotation=25)
    plt.tight_layout()

    # artifacts 폴더 아래에 분석 결과물 차트 저장
    os.makedirs("artifacts", exist_ok=True)
    img_path = "artifacts/daily_trend_analysis.png"
    plt.savefig(img_path, dpi=200)
    print(f"💾 시각화 분석 차트 저장 완료 ➡️ [절대경로]: {os.path.abspath(img_path)}")


if __name__ == "__main__":
    run_analysis()
