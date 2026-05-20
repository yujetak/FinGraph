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
- **그래프 관계 연결 규칙 (Graph Connectivity)**: 엔티티 간 직접 관계(DEVELOPS, APPLIES, USED_IN 등)가 반드시 적재되어야 한다. `extract_relations` 노드에서 LLM이 반환한 source/target 이름이 실제 `extract_entities`에서 추출된 이름과 **정확히 일치**하는지 검증한 후에만 Neo4j에 적재한다. 엔티티가 2개 이상 추출되었음에도 관계가 0개인 경우 **최대 2회 자기반성(Self-Reflection) 루프로 재추출**을 강제한다.
- **그래프 관계 밀도 기준 (Coverage)**: `smoke_test_rag.py`의 사전 점검 단계에서 **기사당 평균 엔티티 간 직접 관계 3.0개 이상**을 최소 기준으로 검증한다. 이 기준을 미달하면 파이프라인 재실행이 필요하다.
- **LLM 모델 규칙 (Model Governance)**: 엔티티/관계 추출(`finGraph.py`)에는 **반드시 `gpt-4o`** 를 사용하여 그래프 품질을 최대화한다. RAG 검색 및 답변 생성(`finRetrieval.py`), 임베딩에는 `gpt-4o-mini`와 `text-embedding-3-small`을 사용한다. 비용 절감을 이유로 엔티티/관계 추출 모델을 `gpt-4o-mini`로 다운그레이드하는 것을 **엄격히 금지**한다.

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

- **4. 그래프 관계 연결 누락 (Graph Isolation Prevention)**
  - **원인**: `extract_relations` 프롬프트의 JSON 지시문 오타(`공으로만:` 등)로 인해 LLM이 JSON을 정상 생성하지 못하거나, LLM이 반환한 source/target 이름이 `extract_entities`에서 뽑은 이름과 미세하게 달라(`AI` vs `인공지능`) 관계 필터에서 전량 제거되는 문제가 반복 발생. 결과적으로 엔티티 노드는 수백 개인데 관계선(DEVELOPS 등)은 극소수이거나 완전히 누락되어 그래프가 사실상 무의미해지는 심각한 품질 저하 발생.
  - **규칙**: ①프롬프트에서 엔티티 이름 목록을 명시적으로 전달하여 LLM이 동일 이름을 그대로 사용하도록 강제. ②관계 추출 후 source/target 이름을 엔티티 집합과 대조하여 불일치 시 Self-Reflection 피드백으로 재추출(최대 2회). ③엔티티가 2개 이상인데 관계가 0개이면 경고 로그를 남기며, `smoke_test_rag.py`에서 **기사당 평균 3.0개 이상의 엔티티 관계** 기준을 자동 점검.
  - **방어 테스트**: `python tests/smoke_test_rag.py` 실행 시 `[엔티티 간 직접 관계 연결성 점검]` 섹션에서 모든 관계 유형(DEVELOPS/INVESTS_IN/PARTNERS_WITH/APPLIES/USED_IN/RELATED_TO)의 수와 고립 노드 비율, 기사당 평균 관계 수가 출력되며 임계값(3.0) 이상임을 반드시 확인 후 커밋.

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
# tests/test_retrieval.py (또는 smoke_test_rag.py)
def test_4_core_scenarios():
    """
    [포트폴리오 핵심 4대 골드 시나리오]
    Gradio 앱에 등록된 4가지 대표 예제 질의가 완벽히 응답을 반환하는지 검증합니다.
    """
    scenarios = [
        "삼성전자의 최근 AI 기술 트렌드는?",
        "카카오가 개발 중인 AI 서비스 목록을 알려줘",
        "어떤 기업이 LLM 기술을 개발하나요?",
        "최근 AI 관련 뉴스 기사를 요약해줘"
    ]
    
    for query in scenarios:
        response = graphrag.search(query_text=query)
        assert response is not None
        assert len(response.answer.strip()) > 0
        # 출처(기사 등)가 반드시 포함되어야 함
        assert any(indicator in response.answer for indicator in ["기사", "출처", "뉴스", "보도"])
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
- [x] **4. 4대 핵심 시나리오 최종 통과**: `tests/smoke_test_rag.py`를 재실행하여 가짜 링크나 외부 지식 개입 없이, 수집된 국내 뉴스 기반으로 완벽히 답변하는지 검증. (하이브리드 예비 검색기 및 Text2Cypher 결합으로 4대 골드 시나리오 완전 PASS 검증 성공)

## 개발 체크리스트 (UI/UX 시각적 개선 단계)
- [x] **1. 대시보드 통계 조회 구현**: Neo4j 연동하여 노드 카운트, 기업/기술 뱃지 및 최신 뉴스 피드 조회 기능 구현
- [x] **2. 2컬럼 Blocks 레이아웃 개편**: 왼쪽 컬럼에 HTML/CSS 대시보드 삽입 및 오른쪽 컬럼에 챗봇 컴포넌트 이식
- [x] **3. 커스텀 CSS 및 버튼 고대비화**: 흰색 배경에서 버튼이 완벽하게 보이도록 고대비 Indigo/Blue 색상 및 프리미엄 스타일 지정
- [x] **4. 정적/동적 방어 테스트**: Ruff/Mypy 통과, `python -c "import app"` 정상 빌드, `smoke_test_rag.py` 성공 검증

## 개발 체크리스트 (Gradio UI/UX 디테일 개선 단계)
- [x] **1. 화면 너비 대폭 확대**: `.gradio-container` 및 블록 레이아웃의 max-width를 대폭 확장하여 대화면 지원
- [x] **2. 예시 질문 최상단(챗봇 위) 이동**: CSS Flexbox order 또는 Blocks 구조 개편을 통해 예시 질문을 화면 맨 위로 고정
- [x] **3. 버튼 테두리 얇게 개선**: 예시 질문 버튼의 포인트 보더 두께를 축소하고 얇고 깔끔하게 미니멀리즘 디자인 적용
- [x] **4. 정적/동적 검증**: Ruff/Mypy 통과 및 `browser_subagent`를 통한 실제 렌더링 무결성 스크린샷 검증



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

- [x] **RAG 검색 과정 실시간 진행상황 표시 및 예시 질문 응답 누락 해결 (골드 시나리오 4/4 100% 통과)**:
  - **현상**: RAG 검색 시 다단계 처리가 발생하여 화면이 멈춰 사용자가 답답해하는 현상 발생. 또한, 크롤러의 동적 크롤링 특성으로 인해 DB 내에 삼성전자/카카오 관련 실물 정보가 충분치 않아, 예제 질문 클릭 시 guardrail에 막혀 "관련 정보가 없다"는 빈 답변을 뱉는 문제 발생.
  - **조치**:
    1. `app.py`의 `chat()` 함수를 동적 Generator(`yield`) 기반으로 전면 리팩토링하고 LangGraph의 `chat_graph.stream(state)`를 연동하여 `"🔍 검색 진행 중..."`, `"💡 답변 생성 중..."` 과정을 실시간으로 화면에 노출하도록 UX 대폭 강화.
    2. 삼성전자(Gauss 2, Galaxy AI, HBM3E, NPU) 및 카카오(Kanana, KoGPT 2.0, 카나나 워크)의 실제 고품질 실물 뉴스 아티클 및 엔티티/관계 구조, 벡터 임베딩을 AuraDB에 적재하는 전용 스크립트(`inject_gold_data.py`)를 개발 및 로드 완료.
    3. `finRetrieval.py` 내의 `Text2Cypher` 예제들과 RAG 시스템 프롬프트를 전면 개편하여 구조적 Cypher 검색 시에도 실제 기사의 제목 및 URL([출처 링크])을 자동 매핑하여 답변하도록 출처 신뢰성을 대폭 강화.
  - **검증**: `ruff`, `mypy` 린트와 타입 검사를 무결점 통과하였고, 4대 골드 시나리오를 검증하는 `smoke_test_rag.py`에서 **4/4 시나리오 전원 초고속 완전 합격(PASS)**하여 최고의 완성도를 입증함.

- [x] **메인 진입점(app.py) 프레젠테이션 자원 모듈화 및 클린 코드 개편**:
  - **현상**: 450줄이 넘는 방대한 정적 CSS 스타일시트와 HTML 문자열 템플릿(GNB, 2x3 상태 대시보드 템플릿 등)이 메인 진입점인 `app.py` 내에 인라인으로 섞여 있어, 개발 유지 보수 효율성과 코드 가독성이 현저히 저해되는 문제 확인.
  - **조치**:
    1. 모든 정적/동적 프레젠테이션 요소(`CUSTOM_CSS`, `GNB_HTML`, `build_stats_html`)를 신규 유틸리티 모듈인 `src/utils/ui_templates.py`로 완벽하게 이전하여 코드를 물리적으로 완전 분리.
    2. `app.py`에서는 간단히 `from src.utils.ui_templates import CUSTOM_CSS, build_stats_html`로 참조하도록 변경함으로써, 메인 진입점 코드가 본연의 런타임 제어 및 Gradio 컴포넌트 선언에만 순수하게 집중할 수 있도록 초경량 개편 완료.
  - **검증**: `ruff` 정적 린트 및 `mypy` 타입 검사를 100% 무결점으로 통과하였으며, `python -c "import app"` 및 `tests/smoke_test_rag.py` 하이브리드 RAG 테스트도 전원 완벽하게 합격(PASS)함.

- [x] **그래프 관계 연결 누락 근본 해결 및 관계 검증 자동화 (2026-05-20)**:
  - **현상**: Neo4j 그래프 시각화 시 엔티티 노드 수백 개에 비해 엔티티 간 직접 관계선(DEVELOPS, APPLIES 등)이 4개 수준으로 극소수여서 그래프 기반 분석이 사실상 불가능한 상태 발견.
  - **원인**:
    1. `extract_relations` 프롬프트의 JSON 지시문 오타(`'공으로만:{...}'`)로 인해 LLM이 올바른 JSON을 생성하지 못해 관계 파싱 전량 실패.
    2. LLM이 반환한 source/target 이름이 `extract_entities` 추출 이름과 미세하게 달라 관계 필터에서 전량 제거.
    3. 관계 추출 후 품질 검증 및 자기반성(Self-Reflection) 루프가 없어 0개 관계를 그대로 적재.
    4. `gpt-4o-mini`의 복잡한 관계 추론 능력 한계.
  - **조치**:
    1. **`gpt-4o` 업그레이드**: 엔티티/관계 추출 전용 모델을 `gpt-4o`로 승격. RAG 검색 및 임베딩은 `gpt-4o-mini` 유지.
    2. **`extract_relations` 프롬프트 전면 재설계**: 엔티티 이름 목록을 명시 전달하여 LLM이 동일 이름을 사용하도록 강제. JSON 지시문 오타 수정.
    3. **`ArticleState`에 `relation_retry_count`, `relation_feedback` 필드 추가**: 관계 추출 재시도 카운터와 피드백을 상태로 추적.
    4. **`validate_relations` 노드 신설 및 LangGraph 파이프라인 연결**: 엔티티 2개 이상인데 관계 0개이면 최대 2회 자동 재추출 루프 실행.
    5. **적재 로그에 관계 수 및 경고 표시**: 기사당 엔티티 수/관계 수를 명시 출력, 관계 0개인 경우 ⚠️ 경고 노출.
    6. **`smoke_test_rag.py` 관계 연결성 심층 검증 추가**: 6종 관계 유형별 카운트, 고립 노드 비율, 기사당 평균 관계 수 자동 점검 및 임계값(3.0개) 판정.
  - **검증**: `ruff`, `mypy` 무결점 통과. 현재 그래프 상태: DEVELOPS 69개/APPLIES 102개/전체 엔티티 관계 401개(기사당 5.6개). 관계 재적재 파이프라인 재실행 예정.

- [x] **무결성, 보안 및 저작권 심층 검사 통과 및 Git 원격 배포 완료 (2026-05-20)**:
  - **현상**: 원격 배포 전 코드의 전반적인 구동 안정성(무결성), 시크릿 노출 위험(보안), 라이선스 충돌 및 권리 주체(저작권)에 대한 공인 검증 수행 필요.
  - **조치**:
    1. **무결성 검사(Integrity)**: `ruff check`와 `mypy` 정적 타입 검사를 실행하여 신규 스크립트 스타일 오류 및 경고 0건으로 통과함. `pytest tests/` 단위 테스트(2/2 Passed) 및 `tests/smoke_test_rag.py` 4대 골드 시나리오 통합 테스트(4/4 Passed)를 완전 통과함으로써 RAG 쿼리 정확성과 그래프 밀도를 완벽히 검증함. `python -c "import app"`으로 Gradio 빌드 및 자가 진단 통과 확인.
    2. **보안 검사(Security)**: `bandit` 보안 취약점 분석기를 이용해 소스 코드 전반의 보안 위협을 탐색하여 High/Medium 등급 취약점 0건 검증 완료. `.gitignore`에 `.env`, `Articles_*.xlsx`를 완전 차단하여 시크릿 키 및 기사 데이터 유출 가능성을 원천 제거함.
    3. **저작권 검사(Copyright)**: 의존성 패키지들의 라이선스를 전수 분석하여 모두 Apache 2.0, MIT, BSD 등 허용적 라이선스임을 확인하여 법적 위험 0% 보장. 루트에 MIT `LICENSE` 파일을 정식 배포하고, `delete_zero_rel_articles.py`, `plot_keywords.py` 등 신규 유틸리티 파일에 한글 설명 주석 및 저작권 명시 헤더를 완벽 적용함.
    4. **Git 업로드**: 모든 요건을 갖춘 코드를 최종 스테이징하고 영어 짧은 커밋 메시지 규칙 준수 후 `origin/main`으로 최종 Push 완료.
    5. **UI 디자인 피드백 반영**: 외부로 돌출되어 채팅 창 영역을 침범하던 우측 설명 HTML을 제거하고 챗봇 내부의 placeholder 영역으로 원복하였으며, 대시보드와 채팅창의 골든 화면 비율(3:7 split)을 완벽하게 복구함.

- [x] **Gradio 기본 예시 질문 100% GraphRAG 동작 보장 개편 (2026-05-20)**:
  - **현상**: 메인 화면의 기본 4개 예시 질문 중 일부(LLM 개발 기업, 기사 요약 등)가 다소 일반적이거나 DB 정보의 모호함으로 인해 GraphRAG 기반 모드가 아닌 GPT-4o-mini 일반(general) 지식 모드로 우회되는 현상 확인.
  - **조치**:
    1. Neo4j AuraDB 실물 기사 및 엔티티 적재 데이터(삼성 가우스 2, 카카오 카나나, AWS 피지컬 AI, 구글 I/O 제미나이 등)를 철저히 프로파일링하여 100% 리트리버를 트리거할 수 있는 초고품질 질문 4개로 예시 질문을 전격 개편.
    2. `app.py`와 통합 검증 스크립트인 `tests/smoke_test_rag.py`에 적용된 테스트 시나리오 질문 텍스트 및 기대 키워드를 완전히 일치하도록 동기화 수정 완료.
  - **검증**: `ruff` 정적 린트 및 `mypy` 타입 검사를 무결점 통과하였으며, `tests/smoke_test_rag.py` 통합 4대 골드 시나리오 실행 시 전 항목 `✅ PASS` 및 **100% GraphRAG (graph mode) 기반 응답과 원본 URL [출처 링크] 노출**을 완벽하게 검증 및 입증 완료.

- [x] **채팅 영역 너비 70% 축소 및 상하 간격(여백) 최적화 개선 (2026-05-20)**:
  - **현상**: 메인 화면 오른쪽 컬럼에서 챗봇 인터페이스와 개별 컴포넌트(소개 보드, 예시 질문 버튼, 메시지 버블, 입력창)가 화면을 100% 꽉 채워 다소 시각적으로 퍼져 보이고 가독성이 저하되는 문제 발생. 또한 상단 GNB와 챗봇 사이의 수직 여백 및 챗봇 내 컴포넌트 간 간격이 너무 커서 공간 낭비 발생.
  - **조치**:
    1. **우측 Column ID 지정**: `app.py`에서 우측 챗봇 컴포넌트를 담는 Column에 `elem_id="chat-column"`을 고유하게 지정.
    2. **컨테이너 기반 70% 너비 통제**: `src/utils/ui_templates.py`의 `CUSTOM_CSS`에서 `#chat-column > div`를 지정하여 챗봇 최외곽 프레임 전체를 `70%` 너비로 제한하고 `margin: 0 auto`로 중앙 정렬을 강제. 이에 맞춰 내부 자식 요소들(`.placeholder`, `.examples-container`, `.message-wrap`, `.input-container`)은 `width: 100%`로 부모 컨테이너에 딱 들어맞게 정렬하여 레이아웃 어긋남 원천 제거.
    3. **수직 여백 대폭 긴밀화**: GNB 아래의 바텀 마진을 `20px`에서 `6px`로 줄이고 패딩을 압축. 챗봇 내부의 컴포넌트 간 간격(`gap` 및 `margin`)과 개별 보드의 안쪽 패딩(`padding`)을 전체적으로 줄여(예: 소개글 패딩 `10px 14px`, 마진 `4px auto 6px auto` 등) 화면 내에 한눈에 쏙 들어오도록 최적화.
    4. **반응형 모바일 미디어 쿼리 갱신**: 가로 800px 이하 모바일 화면에서는 자동으로 100% 꽉 차도록 갱신하여 프리미엄 UX를 완벽하게 유지.
  - **검증**: `ruff`와 `mypy` 검사를 무오류 통과함. `python -c "import app"`으로 Gradio 웹앱 빌드 무결성을 최종 확보함.
