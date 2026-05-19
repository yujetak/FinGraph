"""
smoke_test_rag.py — GraphRAG 3대 시나리오 현장 검증 스크립트
=============================================================
지원동기 작성 지원 챗봇으로서의 서비스 목적을 검증합니다.

시나리오:
  1. 특정 기업  - "카카오의 AI 서비스 트렌드는?"
  2. 특정 기술  - "LLM 기술을 개발하는 기업들은?"
  3. 전체 트렌드 - "금융AI 분야에서 가장 적극적인 기업 TOP 3와 대표 서비스"

실행 방법:
    python3 tests/smoke_test_rag.py
"""

import os
import sys
import time

import dotenv

dotenv.load_dotenv()

# ── 0. 그래프 구성 사전 점검 (Neo4j 노드/관계 통계) ─────────────────────────
def check_graph_structure():
    import neo4j

    uri = os.getenv("NEO4J_URI", "neo4j://localhost:7687")
    username = os.getenv("NEO4J_CLIENT_ID") or os.getenv("NEO4J_USERNAME") or "neo4j"
    password = os.getenv("NEO4J_CLIENT_SECRET") or os.getenv("NEO4J_PASSWORD") or "password"
    auth = (username, password)
    driver = neo4j.GraphDatabase.driver(uri, auth=auth)

    print("\n" + "=" * 60)
    print("📊 [사전 점검] Neo4j 그래프 구성 현황")
    print("=" * 60)

    queries = {
        "Article (기사)":        "MATCH (n:Article) RETURN count(n) as cnt",
        "AICompany (기업)":      "MATCH (n:AICompany) RETURN count(n) as cnt",
        "AITechnology (기술)":   "MATCH (n:AITechnology) RETURN count(n) as cnt",
        "AIService (서비스)":    "MATCH (n:AIService) RETURN count(n) as cnt",
        "AIField (분야)":        "MATCH (n:AIField) RETURN count(n) as cnt",
        "Content (청크+벡터)":   "MATCH (n:Content) RETURN count(n) as cnt",
        "MENTIONS 관계":         "MATCH ()-[r:MENTIONS]->() RETURN count(r) as cnt",
        "DEVELOPS 관계":         "MATCH ()-[r:DEVELOPS]->() RETURN count(r) as cnt",
    }

    all_ok = True
    for label, cypher in queries.items():
        with driver.session() as s:
            result = s.run(cypher).single()
            cnt = result["cnt"] if result else 0
            status = "✅" if cnt > 0 else "⚠️ 비어있음"
            if cnt == 0:
                all_ok = False
            print(f"  {status}  {label}: {cnt}개")

    driver.close()
    print()
    if not all_ok:
        print("⛔ 일부 노드/관계가 비어있습니다. finGraph.py 실행으로 그래프를 먼저 채워주세요.\n")
        sys.exit(1)
    else:
        print("✅ 그래프 구성 정상 — RAG 테스트를 시작합니다.\n")


# ── 1. GraphRAG 응답 품질 검증 ───────────────────────────────────────────────
def run_scenario(label: str, query: str, expected_keywords: list[str]):
    from src.retrieval.finRetrieval import graphrag

    print("=" * 60)
    print(f"🔍 시나리오: {label}")
    print(f"   질문: {query}")
    print("=" * 60)

    start = time.time()
    result = graphrag.search(query_text=query)
    elapsed = time.time() - start

    answer = result.answer if result and result.answer else ""

    print(f"\n📝 GraphRAG 응답 ({elapsed:.1f}초):\n")
    print(answer)

    # 품질 검증
    print("\n🔎 품질 체크:")
    all_pass = True

    # 1) 응답이 비어있지 않은가
    if len(answer.strip()) > 50:
        print("  ✅ 응답 길이 충분 (50자 이상)")
    else:
        print(f"  ❌ 응답이 너무 짧음 ({len(answer.strip())}자)")
        all_pass = False

    # 2) 기대 키워드 포함 여부
    found = [kw for kw in expected_keywords if kw in answer]
    missing = [kw for kw in expected_keywords if kw not in answer]
    if found:
        print(f"  ✅ 핵심 키워드 포함: {found}")
    if missing:
        print(f"  ⚠️  미포함 키워드: {missing}")

    # 3) 출처/근거 표기 여부
    source_indicators = ["기사", "출처", "뉴스", "보도", "따르면", "발표", "http"]
    has_source = any(ind in answer for ind in source_indicators)
    if has_source:
        print("  ✅ 출처/근거 표기 있음")
    else:
        print("  ⚠️  출처/근거 표기 없음 (RAG 응답이지만 근거가 불명확)")
        all_pass = False

    overall = "✅ PASS" if all_pass else "⚠️  PARTIAL (개선 여지 있음)"
    print(f"\n  → 최종 판정: {overall}")
    print()
    return all_pass


# ── 메인 실행 ────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    # 0. 그래프 구성 사전 점검
    check_graph_structure()

    results = []

    # 시나리오 1: 특정 기업
    results.append(run_scenario(
        label="① 특정 기업 — 지원동기 자료 조사",
        query="카카오가 개발 중인 AI 서비스와 기술 트렌드를 알려줘. 지원동기 작성에 참고하고 싶어.",
        expected_keywords=["카카오", "AI", "서비스"],
    ))

    # 시나리오 2: 특정 기술
    results.append(run_scenario(
        label="② 특정 기술 — LLM 기술 보유 기업 탐색",
        query="LLM(대규모 언어 모델) 기술을 개발하거나 도입하고 있는 국내 금융·핀테크 기업들은 어디야?",
        expected_keywords=["LLM", "AI", "기업"],
    ))

    # 시나리오 3: 전체 트렌드 (포트폴리오 대표 골드 쿼리)
    results.append(run_scenario(
        label="③ 전체 트렌드 — 금융AI 분야 TOP 3 기업",
        query="최근 수집된 뉴스에서 금융AI(AIField) 분야에 가장 적극적으로 기술을 개발하고 있는 기업 TOP 3와 그 기업들이 개발한 대표 서비스를 알려줘.",
        expected_keywords=["1.", "기업", "서비스", "AI"],
    ))

    # 최종 요약
    print("=" * 60)
    print("📋 최종 요약")
    print("=" * 60)
    labels = ["① 특정 기업", "② 특정 기술", "③ 전체 트렌드"]
    for label, passed in zip(labels, results):
        print(f"  {'✅ PASS' if passed else '⚠️  PARTIAL'} | {label}")
    print()
    pass_count = sum(results)
    print(f"  총 {pass_count}/{len(results)}개 시나리오 완전 통과")
