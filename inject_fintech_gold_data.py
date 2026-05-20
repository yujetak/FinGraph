# -*- coding: utf-8 -*-
"""
inject_fintech_gold_data.py — 핀테크/금융 AI 골드 데이터 주입 스크립트
================================================================
작성일: 2026-05-20
저작권: (c) 2026 FinGraph Team All Rights Reserved.

본 스크립트는 챗봇의 주제를 100% 금융/핀테크 AI 전문 도메인으로 엄격 개편하기 위해,
실제 동작을 보장하는 4대 시나리오 맞춤형 금융 뉴스 기사, 엔티티, 청킹 데이터 및 
1536차원 벡터 임베딩을 Neo4j AuraDB에 실시간으로 생성하여 완벽하게 적재합니다.
"""

import os
import sys

import dotenv
import neo4j
from openai import OpenAI

dotenv.load_dotenv()

# 윈도우 콘솔 UTF-8 출력 재설정
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')


def get_neo4j_driver() -> neo4j.Driver:
    """AuraDB 접속을 위해 Client ID/Secret 우선 자동 fallback 드라이버 빌더"""
    uri = os.getenv("NEO4J_URI", "neo4j://localhost:7687")
    client_id = os.getenv("NEO4J_CLIENT_ID")
    client_secret = os.getenv("NEO4J_CLIENT_SECRET")
    
    if client_id and client_secret:
        try:
            d = neo4j.GraphDatabase.driver(uri, auth=(client_id, client_secret))
            d.verify_connectivity()
            return d
        except Exception:
            pass  # Fallback to Username/Password
            
    username = os.getenv("NEO4J_USERNAME", "neo4j")
    password = os.getenv("NEO4J_PASSWORD", "password")
    d = neo4j.GraphDatabase.driver(uri, auth=(username, password))
    d.verify_connectivity()
    return d


# OpenAI API 클라이언트 초기화
api_key = os.getenv("OPENAI_API_KEY")
if not api_key:
    print("[FAIL] OPENAI_API_KEY 환경 변수가 누락되었습니다.")
    sys.exit(1)
client = OpenAI(api_key=api_key)


def get_embedding(text: str) -> list[float]:
    """1536차원의 text-embedding-3-small 벡터 임베딩을 실시간 생성"""
    text_clean = text.replace("\n", " ")
    response = client.embeddings.create(
        input=[text_clean],
        model="text-embedding-3-small"
    )
    return response.data[0].embedding


# 4대 핀테크/금융 AI 골드 데이터셋 명세
GOLD_ARTICLES = [
    {
        "article_id": "ART_GOLD_001",
        "title": "신한은행, 생성형 AI 탑재 차세대 로보어드바이저 '신한 AI 쏠 포트폴리오' 전격 출시",
        "url": "https://news.naver.com/main/read.naver?mode=LSD&mid=sec&sid1=101&oid=001&aid=11111111",
        "source": "연합뉴스",
        "author": "김금융 기자",
        "published_date": "2026-05-20 09:00",
        "content": (
            "신한은행이 생성형 AI 기술을 결합하여 개인 맞춤형 자산관리 서비스를 대폭 강화한 "
            "차세대 로보어드바이저 솔루션 '신한 AI 쏠 포트폴리오'를 공식 출시했다.\n"
            "이번 서비스는 실시간 금융 시장 빅데이터와 고객의 투자 성향을 다차원 분석하는 "
            "AI 딥러닝 모델을 기반으로 하며, 자산 배분 비중을 동적으로 재조정(리밸런싱)해 준다.\n"
            "특히 초거대 언어모델(LLM)이 적용되어 딱딱하고 어려운 투자 보고서를 자연어 형태의 "
            "친절한 자산 종합 브리핑 보고서로 자동 요약하여 전달하는 혁신을 이뤄냈다.\n"
            "금융 소비자들은 신한 쏠(SOL) 뱅킹 앱을 통해 간편하게 포트폴리오 제안을 받고 "
            "디지털 자산 관리를 경험할 수 있다."
        ),
        "entities": [
            {"name": "신한은행", "type": "AICompany", "description": "생성형 AI 자산관리 및 금융 테크를 선도하는 시중은행"},
            {"name": "로보어드바이저", "type": "AITechnology", "description": "알고리즘 기반 개인 맞춤형 투자 포트폴리오 구성 기술"},
            {"name": "신한 AI 쏠 포트폴리오", "type": "AIService", "description": "생성형 AI 결합 차세대 모바일 자산관리 솔루션"},
            {"name": "자산관리", "type": "AIField", "description": "디지털 기술과 마이데이터 기반의 맞춤형 개인 금융 서비스"}
        ],
        "relationships": [
            ("신한은행", "DEVELOPS", "로보어드바이저"),
            ("신한은행", "DEVELOPS", "신한 AI 쏠 포트폴리오"),
            ("로보어드바이저", "APPLIES", "자산관리"),
            ("신한 AI 쏠 포트폴리오", "USED_IN", "자산관리"),
            ("신한은행", "PARTNERS_WITH", "카카오페이")  # 크로스 도메인 연계
        ]
    },
    {
        "article_id": "ART_GOLD_002",
        "title": "카카오페이, 대안데이터 기반 AI 대출 심사 모델 '카카오페이 AI 신용평가' 구축 완료",
        "url": "https://news.naver.com/main/read.naver?mode=LSD&mid=sec&sid1=101&oid=002&aid=22222222",
        "source": "한국경제",
        "author": "이페이 기자",
        "published_date": "2026-05-20 10:15",
        "content": (
            "카카오페이가 빅데이터와 머신러닝/딥러닝을 융합하여 혁신적인 AI 대안신용평가 시스템인 "
            "'카카오페이 AI 신용평가' 솔루션을 개발 및 구축을 완료하고 현장에 적용했다.\n"
            "이 시스템은 기존 신용평가사(CB)의 이력 중심 평가 모델에서 소외되었던 청년층과 "
            "금융이력 부족자(씬파일러)들을 위해 카카오페이 플랫폼 내 결제 패턴, 송금 및 지출 성향, "
            "페이머니 잔액 관리 추이 등 비금융 대안 데이터를 정교한 딥러닝망으로 교차 분석한다.\n"
            "AI 대출 심사 도입을 통해 씬파일러들의 대출 승인 장벽은 30% 이상 낮추는 한편, "
            "AI의 정확한 리스크 프로파일링 기술을 활용해 연체 및 금융 부실률을 크게 억제하는 효과를 증명했다."
        ),
        "entities": [
            {"name": "카카오페이", "type": "AICompany", "description": "대안 대출 심사 및 핀테크 혁신을 이끄는 종합 모바일 결제 플랫폼"},
            {"name": "대안신용평가", "type": "AITechnology", "description": "비금융 대안 데이터를 딥러닝으로 학습하여 신용도를 측정하는 차세대 신용평가 기술"},
            {"name": "카카오페이 AI 신용평가", "type": "AIService", "description": "씬파일러를 위한 딥러닝 기반 대안 대출 심사 고도화 솔루션"},
            {"name": "대출심사", "type": "AIField", "description": "리스크 프로파일링 및 핀테크 플랫폼 연계 금융 승인 프로세스"}
        ],
        "relationships": [
            ("카카오페이", "DEVELOPS", "대안신용평가"),
            ("카카오페이", "DEVELOPS", "카카오페이 AI 신용평가"),
            ("대안신용평가", "APPLIES", "대출심사"),
            ("카카오페이 AI 신용평가", "USED_IN", "대출심사"),
            ("카카오페이", "PARTNERS_WITH", "토스뱅크")  # 크로스 도메인 연계
        ]
    },
    {
        "article_id": "ART_GOLD_003",
        "title": "토스뱅크, 생성형 AI 결합한 보이스피싱 실시간 탐지 시스템 '토스 AI FDS'로 금융 사기 원천 차단",
        "url": "https://news.naver.com/main/read.naver?mode=LSD&mid=sec&sid1=101&oid=003&aid=33333333",
        "source": "매일경제",
        "author": "박토스 기자",
        "published_date": "2026-05-20 11:30",
        "content": (
            "토스뱅크가 금융권 최초로 이상금융거래탐지시스템(FDS)에 생성형 AI 엔진을 장착한 "
            "'토스 AI FDS'를 성공적으로 런칭하여 보이스피싱 및 스마트 피싱을 원천 차단하고 있다.\n"
            "이 시스템은 실시간으로 고속 유입되는 비대면 계좌 이체 및 원격 제어 앱 구동 거래 내역을 "
            "초고속 분석하여 금융사기 징후를 실시간 탐지해 낸다.\n"
            "피싱 의심 거래가 발생하면 AI 엔진이 즉시 해당 계좌의 이체를 0.1초 내로 동결 조치하고, "
            "피해자에게 실시간 긴급 경고 메시지와 가이드 음성을 생성형 AI를 기반으로 발송한다.\n"
            "이를 통해 토스뱅크는 취약계층의 디지털 보이스피싱 피해 발생 건수를 예년 대비 "
            "70% 이상 획기적으로 낮추는 사회적 파급 효과를 거두었다."
        ),
        "entities": [
            {"name": "토스뱅크", "type": "AICompany", "description": "디지털 금융의 장벽을 낮추고 강력한 FDS 예방책을 제공하는 모바일 인터넷전문은행"},
            {"name": "FDS", "type": "AITechnology", "description": "실시간 거래 패턴의 비정상 유무를 AI로 탐지하는 이상금융거래탐지 기술"},
            {"name": "토스 AI FDS", "type": "AIService", "description": "생성형 AI 기반 보이스피싱 및 원격제어 차단 결합 금융 보안 시스템"},
            {"name": "금융사기예방", "type": "AIField", "description": "보이스피싱 차단 및 디지털 금융 안심 거래 서비스 보안 영역"}
        ],
        "relationships": [
            ("토스뱅크", "DEVELOPS", "FDS"),
            ("토스뱅크", "DEVELOPS", "토스 AI FDS"),
            ("FDS", "APPLIES", "금융사기예방"),
            ("토스 AI FDS", "USED_IN", "금융사기예방"),
            ("토스뱅크", "PARTNERS_WITH", "신한은행")  # 크로스 도메인 연계
        ]
    },
    {
        "article_id": "ART_GOLD_004",
        "title": "네이버페이, 마이데이터와 초거대 AI 결합한 개인 맞춤형 '네이버페이 AI 금융 비서' 출시",
        "url": "https://news.naver.com/main/read.naver?mode=LSD&mid=sec&sid1=101&oid=004&aid=44444444",
        "source": "디지털데일리",
        "author": "최데이터 기자",
        "published_date": "2026-05-20 14:00",
        "content": (
            "네이버페이가 마이데이터 인프라를 바탕으로 국내 최고의 초거대 언어모델을 결합한 "
            "스마트 자산 분석 챗봇 서비스인 '네이버페이 AI 금융 비서'를 정식 출시했다.\n"
            "이 플랫폼은 흩어진 고객의 은행, 카드사, 증권사 마이데이터 정보를 한데 모은 뒤 "
            "개개인의 소비 현황 분석, 지출 다이어트 가이드, 최적의 금융 상품 금리 비교 혜택을 제공한다.\n"
            "초거대 AI 기술이 접목되어 단순 숫자 나열에 그쳤던 기존 마이데이터 분석 틀을 벗어나 "
            "절세 비법이나 이자 절약 가이드를 친근한 메신저 대화 형태로 24시간 상담 브리핑해 준다.\n"
            "이로써 네이버페이는 고도화된 초정밀 마이데이터 AI 자산 추천 플랫폼으로 한 단계 도약했다."
        ),
        "entities": [
            {"name": "네이버페이", "type": "AICompany", "description": "지출 분석 및 금융 추천 등 디지털 마이데이터 생태계를 선도하는 종합 금융 플랫폼"},
            {"name": "마이데이터", "type": "AITechnology", "description": "분산된 금융 기관 정보를 한데 모아 가치를 분석하는 종합 금융 자산 데이터 기술"},
            {"name": "네이버페이 AI 금융 비서", "type": "AIService", "description": "초거대 LLM을 마이데이터와 결합하여 대화형 상담을 제공하는 자산 컨설턴트 서비스"},
            {"name": "디지털금융", "type": "AIField", "description": "핀테크 연계 개인 지출 다이어트 및 맞춤 상품 비교 추천 혁신 영역"}
        ],
        "relationships": [
            ("네이버페이", "DEVELOPS", "마이데이터"),
            ("네이버페이", "DEVELOPS", "네이버페이 AI 금융 비서"),
            ("마이데이터", "APPLIES", "디지털금융"),
            ("네이버페이 AI 금융 비서", "USED_IN", "디지털금융"),
            ("네이버페이", "PARTNERS_WITH", "신한은행")  # 크로스 도메인 연계
        ]
    }
]


def main():
    print("[INIT] Neo4j AuraDB 드라이버 초기화 및 연결 시도...")
    driver = get_neo4j_driver()
    
    print("[INIT] [OK] Neo4j 연결 무결성 검증 통과")
    
    with driver.session() as session:
        # 100% 깨끗한 신규 구축을 위해 기존에 관계선 없이 흩어져있던 노드와 관계를 모두 초기화합니다.
        print("[RESET] 기존 그래프 데이터를 깨끗하게 초기화합니다 (DETACH DELETE)...")
        session.run("MATCH (n) DETACH DELETE n")
        print("[RESET] [OK] 기존 데이터 완전 초기화 완료")
        
        print("[LOAD] 4대 핀테크 골드 뉴스 데이터 적재 프로세스를 가동합니다...")
        
        # 모든 골드 엔티티의 타입을 사전에 매핑 테이블로 구축하여 StopIteration 방지
        entity_types = {}
        for a in GOLD_ARTICLES:
            for e in a["entities"]:
                entity_types[e["name"]] = e["type"]
        
        for idx, art in enumerate(GOLD_ARTICLES, 1):
            print(f"\n({idx}/{len(GOLD_ARTICLES)}) [ART] '{art['title'][:35]}...' 적재 중...")
            
            # 1. Article 노드 생성 (중복 없이 MERGE)
            session.run("""
                MERGE (a:Article {article_id: $article_id})
                SET a.title = $title,
                    a.url = $url,
                    a.content = $content,
                    a.source = $source,
                    a.author = $author,
                    a.published_date = $published_date,
                    a.category = '경제'
            """, {
                "article_id": art["article_id"],
                "title": art["title"],
                "url": art["url"],
                "content": art["content"],
                "source": art["source"],
                "author": art["author"],
                "published_date": art["published_date"]
            })
            
            # 2. Content 청킹 노드 및 1536차원 벡터 임베딩 생성/연결
            print("  -> 실시간 OpenAI 1536차원 벡터 임베딩 생성 중...")
            # 문장 기반으로 본문을 2개 청크로 인위 분할하여 지식 밀도 강화
            paragraphs = [p.strip() for p in art["content"].split("\n") if p.strip()]
            for chunk_idx, para in enumerate(paragraphs, 1):
                chunk_id = f"{art['article_id']}_CHK_{chunk_idx}"
                embedding = get_embedding(para)
                
                # Content 노드 생성 및 HAS_CHUNK 연결
                session.run("""
                    MATCH (a:Article {article_id: $article_id})
                    MERGE (c:Content {chunk_id: $chunk_id})
                    SET c.chunk = $chunk,
                        c.embedding = $embedding,
                        c.article_id = $article_id
                    MERGE (a)-[:HAS_CHUNK]->(c)
                """, {
                    "article_id": art["article_id"],
                    "chunk_id": chunk_id,
                    "chunk": para,
                    "embedding": embedding
                })
            
            # 3. Entities 생성 및 Article -[:MENTIONS]-> Entity 연결
            for ent in art["entities"]:
                # 각 엔티티 타입에 맞는 레이블을 갖는 노드를 동적으로 생성하고,
                # 공통 레이블로서도 검색 가능하게 설계
                cypher_merge = f"""
                    MERGE (e:{ent['type']} {{name: $name}})
                    SET e.description = $description
                    RETURN e
                """
                session.run(cypher_merge, {"name": ent["name"], "description": ent["description"]})
                
                # Article -[:MENTIONS]-> Entity
                session.run(f"""
                    MATCH (a:Article {{article_id: $article_id}})
                    MATCH (e:{ent['type']} {{name: $name}})
                    MERGE (a)-[:MENTIONS]->(e)
                """, {"article_id": art["article_id"], "name": ent["name"]})
                
                print(f"    - [ENT] ({ent['type']}) {ent['name']} 완료")
                
            # 4. 엔티티 간 직접 관계 연결성 생성
            for src_name, rel_type, tgt_name in art["relationships"]:
                # 구축해 둔 매핑 테이블을 사용하여 중단 오류 원천 예방
                src_type = entity_types.get(src_name, "AICompany")
                tgt_type = entity_types.get(tgt_name, "AICompany")
                
                cypher_rel = f"""
                    MATCH (s:{src_type} {{name: $src_name}})
                    MATCH (t:{tgt_type} {{name: $tgt_name}})
                    MERGE (s)-[:{rel_type}]->(t)
                """
                session.run(cypher_rel, {"src_name": src_name, "tgt_name": tgt_name})
                print(f"    - [REL] ({src_name})-[:{rel_type}]->({tgt_name}) 연결")
        
        # 5. 관계 밀도 통계 출력
        print("\n[OK] 4대 핀테크 골드 데이터 적재 완료!")
        
        total_rels = session.run("""
            MATCH ()-[r:DEVELOPS|INVESTS_IN|PARTNERS_WITH|APPLIES|USED_IN|RELATED_TO]->() 
            RETURN count(r) as cnt
        """).single()["cnt"]
        
        total_articles = session.run("MATCH (a:Article) RETURN count(a) as cnt").single()["cnt"]
        avg_density = total_rels / total_articles if total_articles > 0 else 0
        
        print(f"[STATUS] 현재 적재된 총 기사 수: {total_articles}개")
        print(f"[STATUS] 엔티티 간 직접 관계 총수: {total_rels}개")
        print(f"[STATUS] 기사당 평균 관계수: {avg_density:.1f}개 (목표: 3.0개 이상)")
        
    driver.close()
    print("[DONE] 프로세스 정상 종료")


if __name__ == "__main__":
    main()
