import os
import dotenv
import neo4j
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.font_manager as fm

dotenv.load_dotenv()

# Windows 환경 한글 폰트 설정
plt.rc('font', family='Malgun Gothic')
plt.rcParams['axes.unicode_minus'] = False

def create_keyword_plot():
    driver = neo4j.GraphDatabase.driver(
        os.getenv('NEO4J_URI'),
        auth=(os.getenv('NEO4J_USERNAME'), os.getenv('NEO4J_PASSWORD'))
    )

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
        plt.text(width + 0.1, bar.get_y() + bar.get_height()/2, f'{int(width)}', 
                 ha='left', va='center', fontsize=10)

    plt.tight_layout()
    output_path = 'keyword_frequencies.png'
    plt.savefig(output_path, dpi=300, bbox_inches='tight')
    print(f"Graph successfully saved to {output_path}")

if __name__ == "__main__":
    create_keyword_plot()
