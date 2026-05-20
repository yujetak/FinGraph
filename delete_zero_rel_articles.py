# -*- coding: utf-8 -*-
"""
FinGraph 지식 그래프 무결성 관리 유틸리티
- 저작권: (c) 2026 yujetak / FinGraph Contributors (MIT License)
- 역할: 직접적인 엔티티 간 관계선(DEVELOPS, APPLIES 등)이 0개인 고립 기사 노드를 탐색하고 제거하여 
        그래프의 연결 밀도와 RAG 검색 무결성을 높입니다.
"""
import os

import dotenv
import neo4j

dotenv.load_dotenv()


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


if __name__ == "__main__":
    driver = get_neo4j_driver()
    with driver.session() as s:
        res = s.run('''
            MATCH (a:Article)
            OPTIONAL MATCH (a)-[:MENTIONS]->(n)
            OPTIONAL MATCH (n)-[r:DEVELOPS|INVESTS_IN|PARTNERS_WITH|APPLIES|USED_IN|RELATED_TO]-()
            WITH a, count(r) as rel_cnt
            WHERE rel_cnt = 0
            DETACH DELETE a
            RETURN count(a) as deleted_count
        ''')
        record = res.single()
        if record:
            print(f'Deleted articles with 0 relations: {record["deleted_count"]}')
    driver.close()

