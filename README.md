# Dacare LLM

외국인 대상 보험 혜택 안내 챗봇 — FastAPI + LangGraph + Chroma

## 지원 보험사
- UHCG
- Cigna
- Tricare
- MSH China
- NHIS (국민건강보험)

## 파일구조

```
Dacare_LLM/
│
├── .github/
│   └── ISSUE_TEMPLATE/
│       ├── bug_report.md
│       └── feature_request.md
│
├── app/
│   ├── main.py                     # FastAPI 앱 생성, 라우터 등록, CORS 설정
│   ├── schemas.py                  # Pydantic 모델 — ChatRequest / ChatResponse 정의
│   └── api/
│       ├── chat.py                 # POST /chat — LangGraph graph.invoke() 호출 후 응답 반환
│       └── health.py               # GET  /health — 서버 상태 확인 (배포용 헬스체크)
│
├── graph/
│   ├── builder.py                  # 그래프 조립 — 노드 등록, 조건부 엣지 연결, SqliteSaver 체크포인터
│   │                               #   route_after_analyze() : intent → 파이프라인 분기
│   │                               #   route_after_nhis()    : NHIS → claim 연계 분기
│   └── nodes/
│       ├── analyze_node.py         # [진입점] 안전필터 → 언어감지 → Intent Router (LLM)
│       │                           #   반환: language, intent, intents, insurer, insurers, slots
│       ├── within_node.py          # [① 보험 내 비교] 동일 보험사 플랜 비교표 생성
│       │                           #   진입: intent == "within_compare"
│       ├── compare_node.py         # [② 보험사 비교] 멀티 컬렉션 병렬 검색 + 보험사 비교표 생성
│       │                           #   진입: intent == "cross_compare"
│       ├── calculate_node.py       # [③ 계산] 실시간 환율 API + 본인부담금 계산
│       │                           #   진입: intent == "calculation"
│       ├── procedure_node.py       # [④ 절차 안내] general_guidelines RAG 검색 + 단계별 안내
│       │                           #   진입: intent == "procedure"
│       ├── nhis_node.py            # [⑤ NHIS] 멀티턴 — 자격확인 → NHIS 정보 → 민간보험 연계
│       │                           #   진입: intent == "nhis"  /  분기: → claim_node
│       ├── claim_node.py           # [⑥ 청구 + 양식] 청구 절차 안내 + 청구서 양식 제공
│       │                           #   진입: intent == "claim" 또는 nhis_node 연계
│       ├── clarify_node.py         # [재질문] 슬롯 부족·의도 불명확 시 사용자에게 재질문
│       │                           #   진입: intent == "clarify" 또는 missing_slots 존재
│       ├── retrieve_node.py        # [공통 RAG] query_collection() / query_multi_collections() 헬퍼 제공
│       │                           #   각 파이프라인 노드에서 직접 import해서 사용
│       └── generate_node.py        # [공통 생성] call_llm_with_docs() 헬퍼 제공
│                                   #   각 파이프라인 노드에서 직접 import해서 사용
│
├── plugins/
│   ├── base.py                     # InsurancePlugin ABC — 모든 플러그인이 구현해야 할 인터페이스
│   ├── uhcg/
│   │   ├── uhcg_plugin.py          # UHCGPlugin — 플랜 목록, 시스템 프롬프트, 슬롯 분석 구현
│   │   └── ingest.py               # UHCG PDF → 청킹 → DocumentMetadata 태깅 → uhcg_plans 컬렉션 저장
│   ├── cigna/
│   │   ├── cigna_plugin.py         # CignaPlugin — 플랜 목록, 시스템 프롬프트, 슬롯 분석 구현
│   │   └── ingest.py               # Cigna PDF → 청킹 → DocumentMetadata 태깅 → cigna_plans 컬렉션 저장
│   ├── tricare/
│   │   ├── tricare_plugin.py       # TricarePlugin — 플랜 목록, 시스템 프롬프트, 슬롯 분석 구현
│   │   └── ingest.py               # Tricare PDF → 청킹 → DocumentMetadata 태깅 → tricare_plans 컬렉션 저장
│   ├── msh_china/
│   │   ├── msh_china_plugin.py     # MSHChinaPlugin — 플랜 목록, 시스템 프롬프트, 슬롯 분석 구현
│   │   └── ingest.py               # MSH PDF → 청킹 → DocumentMetadata 태깅 → msh_china_plans 컬렉션 저장
│   └── nhis/
│       ├── nhis_plugin.py          # NHISPlugin — 자격 확인 질의, 급여 범위 안내 구현
│       ├── ingest.py               # NHIS 웹 크롤링 + PDF → 청킹 → nhis 컬렉션 저장
│
├── utils/
│   ├── schemas.py                  # LangGraph 전역 상태 및 데이터 계약 정의
│   │                               #   InsuranceState  : 모든 노드가 공유하는 상태
│   │                               #   Intent          : intent 값 상수 클래스
│   │                               #   DocumentMetadata: ChromaDB 메타데이터 표준 (모든 ingest.py 준수)
│   │                               #   initial_state() : graph.invoke() 초기값 생성 헬퍼
│   ├── language.py                 # 언어 감지 — langdetect(1차) → LLM fallback(2차)
│   │                               #   detect_language(text) → "ko"|"en"|"ja"|"zh"|"fr"|"de"|"es"
│   ├── safety.py                   # 안전 필터 — 키워드 블랙리스트(1차) → LLM 심층 검사(2차)
│   │                               #   check_blocked(text) → 차단 메시지 or ""
│   ├── currency.py                 # 환율 조회 + 본인부담금 계산
│   │                               #   get_exchange_rate(currency) → float (10분 캐시)
│   │                               #   convert_to_krw(amount, currency) → dict
│   │                               #   calculate_copay(total, currency, deductible, rate) → dict
│   └── comparison.py               # 비교표 생성 헬퍼 (within_node / compare_node 공용)
│                                   #   build_comparison_prompt() : 비교 LLM 프롬프트 조립
│                                   #   merge_docs_for_comparison(): ChromaDB 결과 → 비교 형식 변환
│                                   #   rerank_by_relevance()      : 표 문서 우선 Re-ranking
│
├── vectordb/                       # ChromaDB 단일 저장소 (git 제외)
│                                   #   컬렉션 목록:
│                                   #     uhcg_plans / cigna_plans / tricare_plans / msh_china_plans
│                                   #     nhis / general_guidelines / claim_procedures
│
├── data/                           # 원본 문서 보관 (git 제외)
│   ├── uhcg/
│   ├── cigna/
│   ├── tricare/
│   ├── msh_china/
│   ├── nhis/
│   └── forms/                      # 보험사별 청구서 양식 PDF/DOCX
│                                   #   uhcg_claim_form.pdf / cigna_claim_form.pdf 등
│
├── scripts/
│   ├── ingest_all.py               # 보험사 지정 인자로 수집 실행 (예: python ingest_all.py uhcg cigna)
│   └── migrate_vectordb.py         # 벡터DB 스키마 변경 시 컬렉션 재생성 및 마이그레이션
│
├── notebooks/                      # 실험 및 분석용 Jupyter 노트북
├── evaluation/                     # RAG 자동 평가 (eval_runner.py, eval_dataset.json)
├── docs/                           # 프로젝트 문서 (API 명세, 온보딩 가이드)
├── .env.example
├── .gitignore
├── requirements.txt
└── README.md
```

## 시작하기

```bash
# 환경변수 설정
cp .env.example .env

# 패키지 설치
pip install -r requirements.txt

# PDF 데이터 전처리 (보험사 지정 필수)
python scripts/ingest_all.py uhcg cigna

# 서버 실행
uvicorn app.main:app --reload
```

## 문서
- [API 명세](docs/api_spec.md)
- [새 보험사 추가 가이드](docs/onboarding_guide.md)
