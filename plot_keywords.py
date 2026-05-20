# -*- coding: utf-8 -*-
"""
FinGraph 키워드 시각화 유틸리티
- 저작권: (c) 2026 yujetak / FinGraph Contributors (MIT License)
- 역할: 수집된 전체 뉴스 데이터베이스 내 AI 관련 주요 키워드(기업/기술/서비스)의 출현 빈도를 분석하여
        좌측 대시보드 화면에 적재할 고품질 막대그래프 이미지(keyword_frequencies.png)를 생성합니다.
"""
import os

import dotenv
import matplotlib.pyplot as plt
import neo4j
import pandas as pd

dotenv.load_dotenv()


# Windows 환경 한글 폰트 설정
plt.rc('font', family='Malgun Gothic')
plt.rcParams['axes.unicode_minus'] = False


def get_neo4j_driver() -> neo4j.Driver:
    uri = os.getenv("NEO4J_URI", "neo4j://localhost:7687")
    client_id = os.getenv("NEO4J_CLIENT_ID")
    client_secret = os.getenv("NEO4J_CLIENT_SECRET")
    
    if client_id and client_secret:
        try:
            d = neo4j.GraphDatabase.driver(uri, auth=(client_id, client_secret))
            d.verify_connectivity()
            return d
        except Exception:
            pass
            
    username = os.getenv("NEO4J_USERNAME", "neo4j")
    password = os.getenv("NEO4J_PASSWORD", "password")
    d = neo4j.GraphDatabase.driver(uri, auth=(username, password))
    d.verify_connectivity()
    return d


def create_keyword_plot():
    driver = get_neo4j_driver()

    query = """
    MATCH (a:Article)-[:MENTIONS]->(n)
    WHERE NOT n:Content
    RETURN n.name AS keyword, count(a) AS freq
    ORDER BY freq DESC
    LIMIT 20
    """

    with driver.session() as session:
        res = session.run(query)
        data = [dict(record) for record in res]

    driver.close()

    if not data:
        print("키워드 데이터가 없습니다.")
        return

    df = pd.DataFrame(data)
    
    # 막대 그래프 그리기 (역순으로 정렬하여 가장 많은 것이 위로 오게 함)
    plt.figure(figsize=(10, 8))
    bars = plt.barh(df['keyword'][::-1], df['freq'][::-1], color='#3b5a82')
    
    plt.xlabel('출현 빈도 (관련 기사 수)', fontsize=12)
    plt.ylabel('키워드 (기업/기술/서비스)', fontsize=12)
    plt.title('상위 20개 AI 관련 키워드 출현 빈도', fontsize=16, fontweight='bold')
    
    # 막대 옆에 수치 텍스트 표시
    for bar in bars:
        width = bar.get_width()
        plt.text(width + 0.1, bar.get_y() + bar.get_height() / 2, f'{int(width)}', 
                 ha='left', va='center', fontsize=10)

    plt.tight_layout()
    output_path = 'keyword_frequencies.png'
    plt.savefig(output_path, dpi=300, bbox_inches='tight')
    print(f"Graph successfully saved to {output_path}")


if __name__ == "__main__":
    create_keyword_plot()
