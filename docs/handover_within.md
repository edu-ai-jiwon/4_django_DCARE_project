# 인수인계 — 보험 내 비교(within) 파이프라인

> 이 문서는 새 Claude 세션에서 작업을 이어받을 수 있도록 작성된 인수인계 파일입니다.

---

## 담당자 정보

- **담당자**: kimjiwon
- **담당 보험사**: TRICARE, UHC(UnitedHealthcare Global)
- **현재 브랜치**: `preprocessing`
- **작업 범위**: LangGraph 파이프라인 ① 보험 내 비교(`within_compare`) — TRICARE/UHC 데이터 한정 선행 구현

---

## 프로젝트 개요

`Dacare_LLM` — 해외 체류자용 보험 상담 LLM 챗봇.

```
사용자 질의
  → analyze_node (언어감지 + Intent 분류)
  → route_after_analyze()
  → 6개 파이프라인 노드 중 하나
  → GPT-4o 답변 생성
  → FastAPI 응답
```

6개 파이프라인:
- ① `within_compare`  — **이번 작업 범위** — 동일 보험사 내 플랜 비교
- ② `cross_compare`   — 보험사 간 비교
- ③ `calculation`     — 환율/본인부담금 계산
- ④ `procedure`       — 절차 안내
- ⑤ `nhis`           — NHIS 상담
- ⑥ `claim`          — 청구 양식

벡터 저장소: ChromaDB (`./vectordb/`)
LLM: OpenAI GPT-4o (`OPENAI_API_KEY` 필요)
임베딩: `paraphrase-multilingual-mpnet-base-v2` (sentence-transformers, 다국어 지원)

---

## 이번 세션에서 완료한 작업

### 1. `plugins/tricare/ingest.py` 전체 재작성

기존 스켈레톤을 완전한 구현으로 교체. `tricare_ingest.py`(별도 파일)의 로직을 재활용하되 아래를 변경:

| 항목 | 기존 (`tricare_ingest.py`) | 변경 후 (`plugins/tricare/ingest.py`) |
|---|---|---|
| 컬렉션명 | `tricare_rag`, `tricare_cost_tables` | `tricare_plans` |
| 임베딩 | LangChain + HuggingFaceEmbeddings | chromadb 직접 + `STEmbedding` |
| 저장 방식 | LangChain Chroma | `chromadb.PersistentClient` |

처리 데이터:
- `data/tricare/guide/` — PDF 핸드북 13개 (OCONUS 키워드 필터링 적용)
- `data/tricare/guide/` — CSV 4개 (TricarePlans, Health_Plan_Costs, mental_health, exclusions)
- 표(table) 청크는 `pdfplumber`로 별도 추출

### 2. `plugins/uhcg/ingest.py` 전체 재작성

기존 스켈레톤을 완전한 구현으로 교체. `uhc_guide_preproecess.py` + `uhc_claim_preproecess.py` 로직을 통합:

| 처리 파일 | 방식 |
|---|---|
| Welcome Guide | 텍스트(fitz) + 표(pdfplumber, 8페이지만) |
| BeHealthy SOB | 모든 페이지 표만 추출 (benefit_summary) |
| Program Guide | 섹션 단위 분할 (13개 섹션 헤더 기준) |
| Business Travel FAQ | Q&A 쌍으로 분할 |
| Claim Forms (2개) | Section 1/2/3 단위 분할 |

컬렉션명: `uhcg_plans`

### 3. `graph/nodes/retrieve_node.py` 수정

임베딩 함수 추가 (ingest와 동일한 모델 사용):

```python
# 추가된 내용
from chromadb.utils.embedding_functions import SentenceTransformerEmbeddingFunction as STEmbedding
MULTILINGUAL_EF = STEmbedding(model_name="paraphrase-multilingual-mpnet-base-v2")

# 변경된 내용
collection = client.get_collection(collection_name, embedding_function=MULTILINGUAL_EF)
```

> ingest와 query 모두 같은 모델을 써야 임베딩 벡터가 일치함. 다르면 검색 결과가 쓰레기값 나옴.

### 4. `scripts/test_within.py` 신규 생성

TRICARE, UHC 두 케이스를 순서대로 실행하는 테스트 스크립트.

---

## 실행 방법

```bash
# 1. 의존성 설치 (이미 되어 있으면 생략)
pip install -r requirements.txt

# 2. 벡터DB 구축 (처음 한 번만 — 모델 첫 다운로드 ~1GB)
python scripts/ingest_all.py tricare uhcg

# 3. within_node 테스트
python scripts/test_within.py
```

`.env` 파일에 아래 키 필요:
```
OPENAI_API_KEY=sk-...
VECTORDB_PATH=./vectordb   # 기본값, 생략 가능
```

---

## 핵심 파일 구조 (이번 작업 관련)

```
Dacare_LLM/
├── graph/
│   ├── builder.py                  # 그래프 조립 — within은 이미 등록되어 있음
│   └── nodes/
│       ├── within_node.py          # ① 보험 내 비교 노드 (수정 불필요, 완성됨)
│       ├── retrieve_node.py        # RAG 검색 헬퍼 — MULTILINGUAL_EF 추가됨 ★
│       └── generate_node.py        # GPT-4o 호출 헬퍼 (수정 불필요)
├── plugins/
│   ├── tricare/
│   │   ├── ingest.py               # tricare_plans 컬렉션 구축 ★ (이번 작업)
│   │   └── tricare_ingest.py       # 구버전 (tricare_rag 컬렉션, 참고용으로만 존재)
│   └── uhcg/
│       ├── ingest.py               # uhcg_plans 컬렉션 구축 ★ (이번 작업)
│       ├── uhc_guide_preproecess.py  # 가이드 전처리 원본 (JSON 출력용, 참고용)
│       └── uhc_claim_preproecess.py  # 청구서 전처리 원본 (JSON 출력용, 참고용)
├── data/
│   ├── tricare/
│   │   ├── guide/   # PDF 13개 + CSV 4개
│   │   └── claim/   # dd2527.pdf, dd2642.pdf
│   └── uhc/
│       ├── guide/   # Welcome Guide, BeHealthy SOB, Program Guide, FAQ
│       └── claim/   # 청구서 양식 2개
├── scripts/
│   ├── ingest_all.py               # python ingest_all.py tricare uhcg 로 실행
│   └── test_within.py              # within_node 단독 테스트 ★ (이번 작업)
└── vectordb/                       # ingest 후 생성됨 (git 제외)
    ├── tricare_plans/
    └── uhcg_plans/
```

---

## 기술 결정 사항

| 결정 | 이유 |
|---|---|
| 임베딩: `paraphrase-multilingual-mpnet-base-v2` | 한국어 포함 50개 언어 지원, prefix 없이 사용 가능, sentence-transformers에 포함됨 |
| `chromadb.PersistentClient` 직접 사용 | `retrieve_node.py`가 이미 이 방식 사용 중 — 일관성 유지 |
| ingest시 컬렉션 delete → recreate | 증분 방식은 중복 ID 관리 복잡도가 높아 단순 재구축 방식 채택 |
| TRICARE OCONUS 필터링 유지 | 해외 체류자 대상 서비스이므로 OCONUS 관련 페이지만 사용하는 기존 정책 유지 |
| UHC welcome guide 표: pdfplumber, 나머지: fitz | 표 셀 추출 정확도 차이 — 나머지는 fitz가 빠르고 충분함 |

---

## 남은 작업 (TODO)

- [ ] `python scripts/test_within.py` 실제 실행 후 답변 품질 확인
- [ ] `within_node.py`의 `plan` 슬롯 필터링 동작 확인 (slots에 plan 있을 때 where 필터 적용)
- [ ] TRICARE 메타데이터 `plan` 값이 "all"/"NGR"/"ADDP"/"TRICARE For Life" 등 — 쿼리의 where 필터와 매칭되는지 확인
- [ ] 팀 전체 ingest 완료 후 전체 그래프(`graph/builder.py`) 통합 테스트
- [ ] `plugins/tricare/tricare_ingest.py` 정리 여부 팀과 논의 (구버전, 현재는 참고용)

---

## 참고: `within_node.py` 동작 흐름

```python
# within_node.py가 하는 일 (수정 불필요)
def within(state):
    insurer  = state["insurer"]           # "tricare" or "uhcg"
    slots    = state.get("slots", {})
    plan     = slots.get("plan", "")

    # 1. ChromaDB에서 {insurer}_plans 컬렉션 검색
    collection_name = f"{insurer}_plans"  # → "tricare_plans" or "uhcg_plans"

    # 2. plan 슬롯이 있으면 해당 plan 문서 집중 검색
    #    없으면 전체 검색

    # 3. build_comparison_prompt()로 비교 프롬프트 조립

    # 4. call_llm_with_docs()로 GPT-4o 호출 → 비교표 생성
```

`retrieve_node.query_collection()`이 `collection_name`으로 ChromaDB에서 검색하므로,
ingest시 컬렉션 이름이 `tricare_plans` / `uhcg_plans`으로 정확히 일치해야 함.
