import os

import pytest

from src.retrieval.finRetrieval import graphrag

# API 키와 Neo4j 연결정보가 없을 경우 테스트를 건너뜁니다.
has_credentials = (
    os.getenv("OPENAI_API_KEY") is not None and 
    os.getenv("NEO4J_URI") is not None
)


@pytest.mark.skipif(
    not has_credentials, 
    reason="OpenAI API Key 또는 Neo4j 연결 환경변수가 없으므로 통합 테스트를 건너뜁니다."
)
def test_portfolio_showcase_aggregation_query():
    """
    [포트폴리오 핵심 시나리오]
    특정 기업을 지정하지 않고, 금융AI 분야의 최신 트렌드 기업 TOP 3와 대표 서비스를 
    동적으로 그래프 탐색(GraphRAG)하여 올바른 형식으로 답변하는지 검증합니다.
    """
    showcase_query = (
        "최근 수집된 뉴스에서 금융AI(AIField) 분야에 가장 적극적으로 기술을 개발하고 있는 "
        "기업 TOP 3와 그 기업들이 개발한 대표 서비스를 알려줘."
    )
    
    # GraphRAG 검색 및 생성 실행
    response = graphrag.search(query_text=showcase_query)
    
    # 1. 응답 객체 및 속성 존재 여부 검증
    assert response is not None
    assert hasattr(response, "answer")
    
    # 2. 답변 텍스트 유효성 검증
    answer = response.answer
    assert len(answer.strip()) > 0
    
    # 3. 답변 형식 검증 (순위 구조나 출처 지침 준수 여부)
    assert any(indicator in answer for indicator in ["1.", "첫째", "TOP", "기사", "출처"])
    
    print(f"\n✨ [포트폴리오 쇼케이스 RAG 결과]\n{answer}")


@pytest.mark.skipif(
    not has_credentials, 
    reason="OpenAI API Key 또는 Neo4j 연결 환경변수가 없으므로 통합 테스트를 건너뜁니다."
)
def test_hybrid_fallback_general_query():
    """
    [하이브리드 RAG Fallback 시나리오]
    지식 그래프(뉴스 데이터)에 전혀 수집되지 않은 일반 과학/역사 질문에 대해 
    검색 결과가 임계치 미만임을 감지하고 자동으로 GPT-4o 일반 지식 모드(general)로 라우팅하는지 검증합니다.
    """
    general_query = "피타고라스 정리와 그 실생활 활용 예시를 간단히 설명해줘."
    
    # search_with_fallback을 통한 라우팅 검색 수행
    result = graphrag.search_with_fallback(query_text=general_query, history=[])
    
    # 1. 반환 타입 및 모드 검증
    assert result is not None
    assert result.mode == "general"
    
    # 2. GPT-4o 일반 지식 답변 유효성 검증
    assert len(result.answer.strip()) > 0
    assert "피타고라스" in result.answer
    
    print(f"\n✨ [일반 지식 Fallback 라우팅 결과]\n{result.answer}")

