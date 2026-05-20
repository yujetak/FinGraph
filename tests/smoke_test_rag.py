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

import io
import os
import sys
import time

# 프로젝트 루트 디렉토리를 Python 경로에 추가하여 ModuleNotFoundError 방지
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))


# Windows 환경에서 유니코드 이모지 출력 시 UnicodeEncodeError(cp949) 방지를 위한 stdout 인코딩 재설정
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

import dotenv

dotenv.load_dotenv()


# ── 0. 그래프 구성 사전 점검 (Neo4j 노드/관계 통계) ─────────────────────────
def check_graph_structure():
    import neo4j

    uri = os.getenv("NEO4J_URI", "neo4j://localhost:7687")
    client_id = os.getenv("NEO4J_CLIENT_ID")
    client_secret = os.getenv("NEO4J_CLIENT_SECRET")
    
    driver = None
    if client_id and client_secret:
        try:
            driver = neo4j.GraphDatabase.driver(uri, auth=(client_id, client_secret))
            driver.verify_connectivity()
        except Exception:
            driver = None
            
    if not driver:
        username = os.getenv("NEO4J_USERNAME", "neo4j")
        password = os.getenv("NEO4J_PASSWORD", "password")
        driver = neo4j.GraphDatabase.driver(uri, auth=(username, password))
        driver.verify_connectivity()

    print("\n" + "=" * 60)
    print("📊 [사전 점검] Neo4j 그래프 구성 현황")
    print("=" * 60)

    # ── 노드/기본 관계 수 점검 ──────────────────────────────────────────────
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

    # ── 엔티티 간 직접 관계 연결성 심층 점검 ───────────────────────────────
    print()
    print("  [엔티티 간 직접 관계 연결성 점검]")
    entity_rel_types = ["DEVELOPS", "INVESTS_IN", "PARTNERS_WITH", "APPLIES", "USED_IN", "RELATED_TO"]
    total_entity_rels = 0
    with driver.session() as s:
        for rel_type in entity_rel_types:
            cnt = s.run(
                f"MATCH ()-[r:{rel_type}]->() RETURN count(r) as cnt"
            ).single()["cnt"]
            total_entity_rels += cnt
            status = "✅" if cnt > 0 else "⚠️"
            print(f"    {status} {rel_type}: {cnt}개")

        # 고립 노드(관계가 전혀 없는 Content 제외) 비율 점검
        isolated = s.run(
            "MATCH (n) WHERE NOT (n)--() AND NOT n:Content RETURN count(n) as cnt"
        ).single()["cnt"]
        total_nodes = s.run(
            "MATCH (n) WHERE NOT n:Content RETURN count(n) as cnt"
        ).single()["cnt"]

    isolation_rate = (isolated / total_nodes * 100) if total_nodes > 0 else 0
    iso_status = "✅" if isolation_rate < 20 else "⚠️ 고립 노드 과다"
    print(f"\n    {iso_status} 고립 노드(Content 제외): {isolated}개 / 전체: {total_nodes}개 ({isolation_rate:.1f}%)")
    print(f"    엔티티 간 직접 관계 합계: {total_entity_rels}개")

    # 엔티티 간 관계가 전혀 없으면 실패 처리
    if total_entity_rels == 0:
        print("\n  ⛔ 엔티티 간 직접 관계(DEVELOPS/APPLIES 등)가 0개입니다. finGraph.py 재실행 필요.")
        all_ok = False

    # 최소 임계값: 기사 10건당 직접 관계 5개 이상 권고
    with driver.session() as s:
        article_cnt = s.run("MATCH (n:Article) RETURN count(n) as cnt").single()["cnt"]
    if article_cnt > 0:
        rels_per_article = total_entity_rels / article_cnt
        threshold_ok = rels_per_article >= 3.0
        t_status = "✅" if threshold_ok else "⚠️ 관계 밀도 부족"
        print(f"    {t_status} 기사당 평균 엔티티 관계: {rels_per_article:.1f}개 (권고: 3.0개 이상)")
        if not threshold_ok:
            all_ok = False

    driver.close()
    print()
    if not all_ok:
        print("⛔ 일부 노드/관계가 비어있거나 연결성이 부족합니다. finGraph.py 실행으로 그래프를 채워주세요.\n")
        sys.exit(1)
    else:
        print("✅ 그래프 구성 및 연결성 정상 — RAG 테스트를 시작합니다.\n")


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

    # 시나리오 1: 삼성전자 AI 기술 트렌드
    results.append(run_scenario(
        label="① 특정 기업 — 삼성전자의 최근 AI 기술 트렌드는?",
        query="삼성전자의 최근 AI 기술 트렌드는?",
        expected_keywords=["삼성전자", "AI", "기술"],
    ))

    # 시나리오 2: 카카오 AI 서비스
    results.append(run_scenario(
        label="② 특정 기업 — 카카오가 개발 중인 AI 서비스 목록을 알려줘",
        query="카카오가 개발 중인 AI 서비스 목록을 알려줘",
        expected_keywords=["카카오", "AI", "서비스"],
    ))

    # 시나리오 3: LLM 기술 개발 기업
    results.append(run_scenario(
        label="③ 특정 기술 — 어떤 기업이 LLM 기술을 개발하나요?",
        query="어떤 기업이 LLM 기술을 개발하나요?",
        expected_keywords=["LLM"],
    ))

    # 시나리오 4: 최근 AI 뉴스 기사 요약
    results.append(run_scenario(
        label="④ 전체 트렌드 — 최근 AI 관련 뉴스 기사를 요약해줘",
        query="최근 AI 관련 뉴스 기사를 요약해줘",
        expected_keywords=["AI"],
    ))

    # 최종 요약
    print("=" * 60)
    print("📋 최종 요약")
    print("=" * 60)
    labels = ["① 삼성전자 AI 트렌드", "② 카카오 AI 서비스", "③ LLM 개발 기업", "④ 최근 AI 뉴스 요약"]
    for label, passed in zip(labels, results):
        print(f"  {'✅ PASS' if passed else '⚠️  PARTIAL'} | {label}")
    print()
    pass_count = sum(results)
    print(f"  총 {pass_count}/{len(results)}개 시나리오 완전 통과")
