---
title: FinGraph
emoji: 🕸️
colorFrom: indigo
colorTo: indigo
sdk: gradio
sdk_version: 4.44.1
python_version: 3.10.14
app_file: app.py
pinned: false
---
# FinNode 🕸️

**Neo4j GraphRAG 기반 AI 뉴스 지식 그래프 플랫폼**

[![Python](https://img.shields.io/badge/Python-3.10%2B-blue.svg)](https://www.python.org/)
[![Neo4j](https://img.shields.io/badge/Neo4j-AuraDB-blue.svg)](https://neo4j.com/)
[![LangGraph](https://img.shields.io/badge/LangGraph-Pipeline-orange.svg)](https://langchain.com/)
[![Gradio](https://img.shields.io/badge/Gradio-UI-red.svg)](https://gradio.app/)
[![CI](https://github.com/yuje/FinGraph/actions/workflows/ci.yml/badge.svg)](https://github.com/yuje/FinGraph/actions/workflows/ci.yml)

---

## 📝 보고서
> [최종 기획안 및 프로젝트 보고서 (업데이트 예정)]()

## 🎥 시연 영상
> [서비스 시연 영상 링크 (업데이트 예정)]()

---

## 1. 프로젝트 배경 및 목적
최신 AI 기술과 핀테크 트렌드는 빠르게 변화하며, 일반적인 RAG(검색 증강 생성) 기술만으로는 여러 뉴스 기사에 흩어져 있는 **'기업-기술-서비스' 간의 복잡한 관계**를 파악하기 어렵습니다. 

**FinNode**는 네이버 뉴스에서 AI 관련 기사를 실시간으로 수집하고, **LangGraph 파이프라인**을 통해 엔티티와 관계를 자동 추출하여 **Neo4j 지식 그래프**에 적재합니다. 이를 기반으로 Vector 및 Cypher 복합 검색(GraphRAG)을 수행하여, 단순한 문서 검색을 넘어 **"현재 금융AI 분야에서 가장 적극적인 기업과 기술 트렌드"**를 완벽한 근거와 함께 추론하고 답변하는 차세대 챗봇 시스템입니다.

---

## 2. 시스템 아키텍처

```text
[Naver News] 
     │ Selenium 크롤링
     ▼
[LangGraph Pipeline] (gpt-4o-mini)
  check_ai ──(AI 아님)──▶ 스킵
     │ (AI 관련)
     ▼
  extract_entities
     │
     ▼
  extract_relations
     │
     ▼
[Neo4j AuraDB]
  Article / Content / AICompany / AITechnology / AIService / AIField / Media
     │
     ▼
[GraphRAG ToolsRetriever] ──▶ gpt-4o 최종 답변 생성
     │
     ▼
[Gradio 챗봇 UI (Hugging Face Spaces 배포)]
```

---

## 3. 주요 기능

- **실시간 뉴스 크롤링**: Selenium 헤드리스 브라우저로 네이버 뉴스 카테고리별 기사 자동 수집
- **LangGraph AI 파이프라인**: 수집된 기사를 3단계 자동 분석 (`판별` → `엔티티 추출` → `관계 추출`)
- **Neo4j 지식 그래프 적재**: 추출된 엔티티(Company, Tech, Service 등)와 관계를 MERGE 트랜잭션으로 중복 없이 DB 적재
- **GraphRAG 챗봇**: 3가지 Retriever를 통합한 ToolsRetriever 기반 자연어 질의응답
  - `Vector Retriever`: 본문 청크 의미 유사도 검색
  - `VectorCypher Retriever`: 벡터 검색 후 해당 기사의 연관 그래프(기업·기술·서비스) 반환 (트렌드 분석에 최적화)
  - `Text2Cypher Retriever`: 자연어 → Cypher 쿼리 자동 변환 및 데이터 집계

---

## 4. 기술 스택

- **Language**: Python 3.10
- **AI / LLM**: LangChain, LangGraph, OpenAI (`gpt-4o`, `text-embedding-3-small`)
- **Database**: Neo4j (AuraDB Cloud)
- **Web / Crawling**: Gradio, Selenium, Pandas
- **CI/CD**: GitHub Actions, Hugging Face Spaces

---

## 5. 그래프 스키마

### 노드 및 관계
| 구분 | 내용 |
|------|-----------|
| **노드 (Nodes)** | `Article`, `Content`, `AICompany`, `AITechnology`, `AIService`, `AIField`, `Media`, `Category` |
| **관계 (Edges)** | `HAS_CHUNK`, `PUBLISHED`, `BELONGS_TO`, `MENTIONS`, `DEVELOPS`, `INVESTS_IN`, `PARTNERS_WITH`, `APPLIES`, `USED_IN`, `RELATED_TO` |

---

## 6. 설치 및 실행 가이드

### 사전 준비
- Python 3.10+
- Neo4j AuraDB 인스턴스 (또는 로컬 Neo4j)
- OpenAI API Key

### 로컬 실행
```bash
# 1. 저장소 클론
git clone https://github.com/yuje/FinGraph.git
cd FinGraph

# 2. 가상환경 생성 및 의존성 설치
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# 3. 환경 변수 설정
cp .env.example .env
# .env 파일에 OpenAI Key, Neo4j 접속 정보 입력

# 4. Gradio 앱 실행
python app.py
```
브라우저에서 `http://localhost:7860` 접속

---

## 7. 배포 (Hugging Face Spaces)

GitHub → Hugging Face Spaces 자동 배포가 `deploy.yml`을 통해 설정되어 있습니다.
`main` 브랜치에 Push 시 자동으로 동기화됩니다.

1. **Hugging Face 토큰 발급**: Settings → Tokens에서 Write 권한 토큰 생성
2. **GitHub Secrets 등록**: `HF_TOKEN`, `HF_REPO` (예: yuje/FinNode) 등록
3. **HF Space Secrets 등록**: `.env` 항목(OpenAI, Neo4j 키) 동일하게 등록
