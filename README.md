# TRICARE PDF Preprocessing

## 📌 개요

TRICARE 보험 관련 PDF 문서를 RAG 기반 챗봇에 활용하기 위해 전처리를 수행했음.  
목표는 PDF → JSON 구조화까지 진행하는 것이었음.

전체 흐름은 아래와 같았음:

PDF → Text Extraction → Cleaning → Section → JSON

---

## 📂 처리 대상 파일

| 파일명 | 설명 | 특징 |
|--------|------|------|
| dd2642.pdf | 의료비 청구서 | 행정 문구 및 header 반복 많았음 |
| dd2527.pdf | 사고/상해 관련 책임 확인서 | 법적 안내 문구 많았음 |

---

## 🛠 사용 라이브러리

| 라이브러리 | 사용 이유 |
|------------|----------|
| pdfplumber | PDF 텍스트 추출 용도였음 |
| re | 불필요 텍스트 제거용 정규표현식 처리였음 |
| json | 전처리 결과 저장용이었음 |
| pathlib | 경로 관리용이었음 |

---

## ⚠️ PDF 전처리 특이사항

### 1. 텍스트 깨짐 현상 있었음
- PDF 구조 특성상 문장이 중간에 끊기는 경우 발생했음
- 예:The public reporting bur


👉 해결 방식:
- 문장 기반 제거는 실패했음
- 패턴 기반 제거 방식으로 처리했음

---

### 2. Header / Footer 반복 문제 있었음
- 모든 페이지에 동일 문구 반복되었음

예: PREVIOUS EDITION IS OBSOLETE
OMB No...
CUI (when filled in)


👉 해결:
- 공통 제거 함수 적용했음

---

### 3. 파일별 구조 차이 있었음

#### dd2642.pdf
- 청구 절차 중심 문서였음
- IMPORTANT, ITEMIZED BILL, TIMELY FILING 등 구조 존재했음

#### dd2527.pdf
- 사고/상해 관련 법적 문서였음
- SECTION I / II / III 구조로 구성되어 있었음

👉 해결:
- 파일별 cleaning 로직 분리했음

---

## 🧹 Cleaning 전략

### 공통 제거 대상

- OMB / CUI / Page 정보 제거했음
- PREVIOUS EDITION 제거했음
- DEFENSE HEALTH AGENCY 제거했음

---

### dd2642 전용 제거

- Prescribed by 관련 문구 제거했음
- TRICARE Operations Manual 제거했음
- OMB approval expires 제거했음
- public reporting burden 관련 문구 제거했음

👉 이유:
- 챗봇 답변과 직접적인 관련 없었음

---

### dd2527 전용 제거

- public reporting burden 문구 제거했음
- PLEASE DO NOT RETURN 문구 제거했음

👉 이유:
- 사용자 질의와 관련 없는 행정 안내였음

---

## 🧠 핵심 설계

### 1. 파일별 Cleaning 분리

clean_common / clean_dd2642 / clean_dd2527 / clean_text 구조로 설계했음

👉 이유:
- PDF 구조가 서로 달랐음
- 동일 로직 적용 시 정보 손실 발생 가능했음

---

### 2. Section 단위 분리

#### dd2642.pdf

- claim_overview
- important_claim_instructions
- how_to_fill_out_form

#### dd2527.pdf

- injury_form_instructions
- injury_general_information
- injury_type_and_cause
- injury_miscellaneous

👉 이유:
- 페이지 단위보다 의미 단위 검색이 중요했음

---

### 3. JSON 구조

```json
{
  "doc_id": "...",
  "section_id": "...",
  "section_title": "...",
  "content": "...",
  "topic": [...]
}
```
---

### 📤 결과

- 출력 파일:
outputs/json_docs/tricare_forms.json 생성했음

---

### 🚀 다음 단계

Section → Chunk → Vector DB → RAG 연결 예정이었음

---

### 📌 UHC 데이터 관련 특이사항

- UHC 데이터 수집량이 적었던 이유는 다음과 같았음:

1. 공개된 공식 PDF 자료 수 자체가 제한적이었음
2. 일부 문서는 로그인/유료 접근이 필요했음
3. TRICARE 대비 구조화된 문서 확보가 어려웠음
4. 데이터 품질이 일정하지 않아 전처리 기준 통일이 어려웠음

👉 따라서 우선 TRICARE 기준으로 전처리 파이프라인을 먼저 구축했음

---

### 🎯 요약

1. PDF → Cleaning → Section JSON 생성까지 완료했음
2. Chunk 및 Vector DB 단계는 팀원과 상의하에 진행하기로 함