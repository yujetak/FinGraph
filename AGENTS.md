###### 참고: https://wikidocs.net/340866
###### 하네스 엔지니어링: Global지침, Skills와 Workflow를 모두 포함하는 지침
###### 개발 시작부터 배포까지 모든 것은 AGENTS.md에 기록한다.
###### 예를들어 개발 단계에서 체크리스트를 만들어서 개발을 할 때마다 하나씩 체크하도록 지시한다.

# AGENTS.md

## 프로젝트 개요
- 목적: AI 기반 핀테크 기술의 트렌드를 파악하도록 돕는 챗봇
- 언어: Python 3.10
- 기술스택: GraphRAG, LangChain, LangGraph, Neo4j, HugingFace, Gradio

## 디렉토리 구조
FinNode/
├── app.py                  # Gradio + LangGraph 챗봇 (HF 배포 진입점)
├── src/
│   ├── references/         # 참고용 노트북 (수정 금지)
│   ├── utils/              # 순수 함수만 (텍스트 전처리 등)
│   ├── graphBuilder/
│   │   ├── scrapping/      # 뉴스 크롤링
│   │   │   ├── finScrapping.py
│   │   │   └── Articles_*.xlsx
│   │   └── neo4j/          # 그래프 적재
│   │       └── finGraph.py
│   └── retrieval/          # GraphRAG 검색
│       └── finRetrieval.py
├── Dockerfile
├── requirements.txt
├── .env.example
├── AGENTS.md
├── README.md
└── .github/workflows/deploy.yml

## 코드 규칙
- 함수명: snake_case
- 클래스명: PascalCase
- 변수명: camelCase
- 한 함수는 하나의 역할만 수행한다
- 타입 힌트 필수

## 절대 금지
- 'src/references/' 파일 수정 금지(참고자료)

## COMMIT 규칙
- 커밋 메시지: 'feat:', 'fix:', 'refactor:' 접두사 사용
- push 하나에 하나의 변경만
- 테스트 없는 push는 올리지 않는다

## 테스트
- 테스트 파일 위치: 'tests/' 디렉토리
- 실행 명령: 'pytest tests/'
- 반드시 예시 입력으로 테스트한다

### 테스트 케이스로 기대 동작 명시
이 프로젝트는 기능의 안정성을 위해 아래의 두 가지 수준의 테스트 코드가 필수적으로 통과해야 합니다.

#### 1. 단위 테스트 (Unit Test) - 예시: `chunk_text`
외부 의존성(DB, API) 없이 텍스트 전처리 로직이 완벽히 작동하는지 검증합니다.

```python
# tests/test_chunk_text.py
def test_chunk_text_empty_returns_empty_list():
    assert chunk_text("") == []

def test_chunk_text_short_text_returns_single_chunk():
    result = chunk_text("짧은 텍스트", size=500, overlap=50)
    assert len(result) == 1

def test_chunk_text_long_text_splits_into_multiple_chunks():
    result = chunk_text("가" * 1000, size=500, overlap=50)
    assert len(result) >= 2
```

#### 2. 통합 및 RAG 시나리오 테스트 (Integration Test) - 예시: `GraphRAG`
실제 뉴스 지식 그래프가 빌드된 후, 임의의 최신 데이터를 동적으로 탐색하여 포트폴리오 수준의 완성도 높은 답변을 도출하는지 검증합니다.

```python
# tests/test_retrieval.py
def test_portfolio_showcase_aggregation_query():
    """
    [포트폴리오 핵심 골드 시나리오]
    특정 기업 고정 없이, '금융AI' 분야의 적극적인 기업 TOP 3와 대표 서비스를 
    그래프 탐색을 통해 완벽한 근거(출처)와 함께 응답하는지 검증합니다.
    """
    showcase_query = "최근 수집된 뉴스에서 금융AI(AIField) 분야에 가장 적극적으로 기술을 개발하고 있는 기업 TOP 3와 그 기업들이 개발한 대표 서비스를 알려줘."
    response = graphrag.search(query_text=showcase_query)
    
    assert response is not None
    assert len(response.answer.strip()) > 0
    # 출처 표기 및 랭킹 구조화 지침 준수 여부 검증
    assert any(indicator in response.answer for indicator in ["1.", "TOP", "기사", "출처"]) # 일종의 skill
```

## 자동 검사
- 커밋 전 `pre-commit` 자동 실행
- `ruff`, `mypy` 검사 통과 필수
- 검사 실패 시 커밋 불가

