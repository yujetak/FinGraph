import json
from pipeline.workflow import pipeline
from pipeline.db_writer import write_graph_to_neo4j, chunk_and_embed_article

def run_test():
    # 1. 모의 테스트용 뉴스 기사 데이터 준비
    test_article = {
        "article_id": "TEST_ART_999",
        "title": "OpenAI, 차세대 인공지능 GPT-5 전격 공개 및 금융AI 적용 선언",
        "content": (
            "인공지능 대표 기업 OpenAI가 새로운 초지능 언어 모델인 GPT-5를 전격 발표했습니다. "
            "이번 모델은 고도의 금융분야 추론 능력을 극대화하여 다양한 금융AI(Financial AI) 시스템에 즉각 적용(APPLIES)됩니다. "
            "OpenAI는 이를 위해 글로벌 대형 금융사인 골드만삭스와 전략적 파트너십(PARTNERS_WITH)을 체결하고 상용 솔루션을 공동 공급하기로 합의했습니다."
        ),
        "url": "https://example.com/news/gpt5-finance",
        "published_date": "2026-05-19 09:30",
        "source": "테크파이낸셜"
    }

    print("==================================================")
    print("🚀 [1/3] LangGraph AI 분석 엔진 가동 (nodes.py)")
    print("==================================================")
    
    # 2. LangGraph 상태 초기화 및 파이프라인 구동
    initial_state = {
        "article_id": test_article["article_id"],
        "title": test_article["title"],
        "text": test_article["title"] + "\n" + test_article["content"],
        "is_ai_related": False,
        "entities": [],
        "relations": []
    }
    
    # 컴파일된 파이프라인 가동
    output_state = pipeline.invoke(initial_state)
    
    print(f"👉 AI 뉴스 여부 판별: {output_state['is_ai_related']}")
    print(f"👉 추출된 지식 엔티티 목록 (총 {len(output_state['entities'])}개):")
    print(json.dumps(output_state['entities'], indent=2, ensure_ascii=False))
    print(f"👉 추출된 엔티티 간 관계선 목록 (총 {len(output_state['relations'])}개):")
    print(json.dumps(output_state['relations'], indent=2, ensure_ascii=False))
    
    # 3. 데이터베이스 적재 실행
    if output_state['is_ai_related']:
        print("\n==================================================")
        print("💾 [2/3] Neo4j AuraDB 지식 그래프 노드 및 관계선 적재")
        print("==================================================")
        write_graph_to_neo4j(test_article, output_state['entities'], output_state['relations'])
        print("✅ 지식 그래프 적재 완료 (MERGE 트랜잭션 성공)")
        
        print("\n==================================================")
        print("🧠 [3/3] 본문 청킹 및 OpenAI text-embedding-3-small 벡터화")
        print("==================================================")
        chunk_and_embed_article(test_article)
        print("✅ 벡터 적재 완료 (HAS_CHUNK 노드 매핑 성공)")
        print("\n🎉 모든 파이프라인 단독 구동 테스트가 완벽히 성공했습니다!")
    else:
        print("\n⏭️ AI 관련 기사가 아니므로 그래프 상세 분석 및 벡터 적재를 건너뜁니다.")

if __name__ == "__main__":
    run_test()
