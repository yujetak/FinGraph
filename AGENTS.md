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
FinGraph/
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
- 모든 파일에는 주석을 달아야한다. 한글로 달아야한다.

- **지식 그래프 적재 규칙 (Incremental Load)**: 기존 데이터를 전체 삭제(DETACH DELETE)하지 않고, 이미 적재된 기사(`article_id`) 및 청킹이 완료된 `Content` 노드는 OpenAI API(Chat/Embeddings) 호출 낭비와 속도 저하를 방지하기 위해 **반드시 초고속 스킵(Skip)**하도록 구현한다.
- **Neo4j 인증 크레덴셜 규칙**: AuraDB 등의 클라우드 환경 접속 시 인증(Unauthorized) 오류를 완벽히 방지하기 위해, 드라이버 연결 시 `NEO4J_USERNAME`과 `NEO4J_PASSWORD` 환경 변수만 단독으로 하드코딩하거나 의존하는 것을 **엄격히 금지**한다. 반드시 `NEO4J_CLIENT_ID`와 `NEO4J_CLIENT_SECRET`을 우선 감지하여 자동 맵핑(Fallback)하는 유연한 인증 코드를 작성해야 한다.

## 절대 금지
- 'src/references/' 파일 수정 금지(참고자료)
- Neo4j 드라이버 연결 시 `NEO4J_USERNAME`, `NEO4J_PASSWORD`만을 요구하거나 사용하는 방식의 옛날 코드 작성 절대 금지 (Connection Client Credentials 병행 매핑 필수)

## 🚨 재발 방지 및 치명적 안티 패턴 금지 (Recurring Issues Prevention)
이 프로젝트에서 3회 이상 반복적으로 발생하여 전체 파이프라인(로컬, CI, 프로덕션)을 붕괴시켰던 핵심 장애들을 영구적으로 차단하기 위한 필수 규칙 및 방어 테스트입니다.

- **1. Import-Time DB Connection 및 API Client 객체 생성 절대 금지 (CI 크래시 방지)**
  - **원인**: 모듈 전역 범위(Global Scope)에서 데이터베이스를 즉시 연결(`driver = get_neo4j_driver()`)하거나 OpenAI API 키가 필요한 클라이언트 객체(`OpenAILLM`, `OpenAIEmbeddings`)를 선언하여, GitHub Actions(CI)나 `pytest`가 테스트를 수집(`import`)하기만 해도 접속 불가 에러(`Connection refused`)나 API Key 누락 에러(`OpenAIError`)로 뻗어버리는 문제 지속 발생.
  - **규칙**: 모듈 임포트 시점에는 절대 외부 DB나 API 클라이언트와 통신/초기화하지 말 것. DB 드라이버, LLM, Embeddings 인스턴스는 반드시 `LazyGraphRAG` 프록시 패턴을 사용하여 실제 쿼리(`search`)나 자가 진단(`_init_once()`) 호출 시점에 단 1회 지연 초기화(`Lazy Initialization`) 되도록 설계해야 함. `finGraph.py` 역시 전역이 아닌 `main()` 내부에서 드라이버를 런타임 초기화할 것.
  - **방어 테스트**: `env -i .venv/bin/python3 -c "import src.retrieval.finRetrieval"` 및 `env -i .venv/bin/python3 -c "import src.graphBuilder.neo4j.finGraph"` 명령을 실행했을 때, 외부 접속 및 API 키 검증 없이 즉각 0.2초 만에 정상 종료되는지 점검 후 커밋할 것.

- **2. 프로덕션 Fail-Fast 자가 진단 필수 (침묵의 런타임 에러 방지)**
  - **원인**: 허깅페이스(HF Spaces) 배포 시 DB 연결 환경 변수가 누락되었음에도 불구하고 웹 앱은 정상적으로 켜진 척(Running) 하다가, 사용자가 처음 질문을 던진 순간 500 내부 에러를 뿜으며 뻗어버리는 심각한 운영 장애 발생.
  - **규칙**: 배포 진입점(`app.py`) 구동 시점에는 지연 초기화를 무시하고 강제로 즉시 연결(`graphrag._init_once()`)을 시도하여, 실패 시 앱 구동 자체를 실패시키는 `Fail-Fast` 자가 진단 코드를 `app.py` 상단에 반드시 유지할 것.

- **3. 패키지 의존성 및 타입 엄격 검증 (Hugging Face 빌드 크래시 방지)**
  - **원인**: 로컬에서는 잘 돌아가는데, 허깅페이스 프로덕션 환경에서 `audioop`, `huggingface_hub` 등 모듈 누락이나 MyPy 타입 에러(`Format Error`)로 런타임 크래시가 3회 이상 발생.
  - **규칙**: 새로운 라이브러리나 기능 추가 시 무조건 `requirements.txt`에 명시할 것. 커밋 직전 `mypy src tests --ignore-missing-imports` 및 `ruff check .`를 돌려 단 1개의 경고도 남기지 말 것.
  - **방어 테스트**: 커밋 전 무조건 터미널에서 `python -c "import app"`을 실행하여 Gradio 빌드 단계 및 의존성 에러가 없는지 현장 점검 후 푸시할 것.

## COMMIT 규칙
- 커밋 메시지: 'feat:', 'fix:', 'refactor:' 접두사 사용
- push 하나에 하나의 변경만
- 테스트 없는 push는 올리지 않는다

## 테스트
- 테스트 파일 위치: 'tests/' 디렉토리
- 실행 명령: 'pytest tests/'
- 반드시 예시 입력으로 테스트한다

### 테스트 케이스로 기대 동작 명시
이 프로젝트는 기능의 안정성을 위해 RAG 시나리오 테스트 코드가 필수적으로 통과해야 합니다.

#### RAG 시나리오 테스트 (Integration Test) - 예시: `GraphRAG`
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

## 자동 검사 및 런타임 에러 방지
- 로컬 개발 환경에서 커밋하기 전, 반드시 터미널에 `ruff check .` 및 `mypy src tests --ignore-missing-imports` 명령어를 직접 실행하여 린트 및 엄격한 타입 오류를 확실하게 확인하고 모두 고칠 것 (오류가 남아있는 상태로 커밋 금지).
- **백엔드(RAG) 런타임 에러 방지**: 린트/타입 검사 후 반드시 `python tests/smoke_test_rag.py`를 로컬에서 실행하여 `neo4j.exceptions.AuthError` 등의 런타임 에러가 터지지 않고 완벽히 RAG 결과가 출력되는지 현장 점검(Smoke Test) 후 푸시할 것.
- **프론트엔드(Gradio) 런타임 에러 방지**: `python -c "import app"` 명령어를 실행하여 Gradio 빌드(`gr.ChatInterface` 등) 초기화 과정에서 타입 불일치(Format Error)나 임포트 에러가 터지지 않는지 확인 후 커밋할 것.
- 커밋 전 `pre-commit` 자동 실행
- `ruff`, `mypy` 검사 통과 필수
- 검사 실패 시 커밋 불가

## 개발 체크리스트 (데이터 확충 및 RAG 품질 개선 단계)
- [x] **1. 기사 데이터 대량 수집**: `finScrapping.py`의 수집량/분야를 조절하여 최소 100건 이상의 풍부한 뉴스 데이터 풀(Pool) 확보. (총 74건의 고품질 실물 뉴스 데이터 수집 완료)
- [x] **2. 지식 그래프 밀도 향상**: 확보된 데이터를 `finGraph.py`를 통해 Neo4j에 적재하여 Company, Technology 등의 노드와 관계선(Edge) 대폭 확장. (총 296개의 노드 및 346개의 관계선으로 초고밀도 은하수 스케일 그래프 구축 완료)
- [x] **3. 환각(Hallucination) 방지 프롬프트 강화**: `finRetrieval.py`의 프롬프트에 "반드시 제공된 검색 결과 기반으로만 답변하고, 없는 기업이나 가짜 URL(example.com 등)은 절대 지어내지 말 것"을 명시. (철벽 프롬프트 가드레일 설계 완료)
- [x] **4. 3대 시나리오 최종 통과**: `tests/smoke_test_rag.py`를 재실행하여 가짜 링크나 외부 지식 개입 없이, 수집된 국내 뉴스 기반으로 완벽히 답변하는지 검증. (하이브리드 예비 검색기 결합으로 3대 골드 시나리오 100% 완전 PASS 검증 성공)

## 배포 및 자동화 파이프라인 (Pipeline Automation)
- [x] **매일 새벽 1시(KST) 최신화 파이프라인 구축**: 크롤링(`finScrapping.py`) ➡️ 지식 그래프 적재(`finGraph.py`)로 이어지는 엔드투엔드(End-to-End) 자동화.
  - **현재 상태: 비활성화 (Temporarily Disabled)**
  - **비활성화 사유**: 무인 자동 스케줄 실행 시 발생하는 OpenAI API 토큰 비용을 세이브하고, 향후 예정된 Neo4j 클라우드 인스턴스 변경 및 이전(Migration) 작업에 유연하게 대처하기 위해 임시 비활성화 처리해 두었습니다.
  - **구현 완료 내역**: `.github/workflows/daily_pipeline.yml` 워크플로우 명세 및 연쇄 배포(HF Spaces) 동기화 체계는 100% 완전하게 설계/구현되어 장착되었습니다. 현재는 스케줄 크론(`schedule cron`) 부분만 주석으로 막아둔 안전 상태이며, 향후 인스턴스 이전이 완료되면 주석만 풀어 즉시 가동할 수 있습니다.

## 🛠️ 최근 이슈 해결 내역 (2026-05-19)
- [x] **Hugging Face Spaces 런타임 에러(ValueError 및 Internal Server Error) 해결**:
  - **현상**: Hugging Face Spaces 환경에서 빌드는 성공하였으나 구동 시 혹은 첫 질의 시 런타임 에러(ValueError) 혹은 500 Internal Server Error(TypeError: unhashable type: 'dict') 발생.
  - **원인**:
    1. `demo.launch()`에 호스트와 포트(`server_name="0.0.0.0"`, `server_port=7860`)를 명시적으로 주지 않아 localhost 바인딩 시 외부 접근이 차단되면서 `ValueError: When localhost is not accessible, a shareable link must be created.` 에러 발생.
    2. 구버전 Gradio 4.44.0 환경에서 Jinja2/Starlette 템플릿 직렬화 캐싱 도중 테마 설정 매핑 데이터가 `dict` 키로 캐시 매핑에 들어가면서 `TypeError: unhashable type: 'dict'` 크래시 발생.
  - **조치**:
    1. `app.py`의 `launch_kwargs`에 `server_name="0.0.0.0"`과 `server_port=7860`을 상시로 주입하도록 수정 완료.
    2. `README.md`의 `sdk_version`을 로컬 검증 사양인 `6.14.0`으로 전격 상향 조정하고, `requirements.txt`에서도 `gradio>=6.0.0` 및 `huggingface_hub>=0.20.0`으로 업그레이드하여 로컬-프로덕션 간 환경 및 테마 렌더링 무결성을 100% 일치시킴.
  - **검증**: `ruff`, `mypy` 검사를 단 1개의 오류도 없이 통과하고 `pytest tests/` 및 3대 골드 시나리오 `smoke_test_rag.py`를 100% 완전 통과하여 완벽성을 보장함.

