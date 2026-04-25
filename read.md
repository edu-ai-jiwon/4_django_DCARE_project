# TRICARE & UHC PDF Preprocessing

## 📌 개요

TRICARE 및 UHC 보험 관련 PDF 문서를 RAG 기반 챗봇에 활용하기 위해 전처리를 수행했음.  
목표는 PDF → JSON 구조화까지 진행하는 것이었음.

전체 흐름은 다음과 같았음:

PDF → Text Extraction → Cleaning → Section → JSON

---

## 📂 처리 대상 파일

### TRICARE

| 파일명 | 설명 | 특징 |
|--------|------|------|
| dd2642.pdf | 의료비 청구서 | 행정 문구 및 header 반복 많았음 |
| dd2527.pdf | 사고/상해 관련 책임 확인서 | 법적 안내 문구 많았음 |

---

### UHC

| 파일명 | 설명 | 특징 |
|--------|------|------|
| Business Travel FAQs | 출장자 FAQ | Q&A 구조 |
| BeHealthy SOB | 보장 항목 문서 | 표(Table) 구조 |
| Global Program Guide | 프로그램 안내 | 설명형 문서 |
| Welcome Guide | 가입자 안내 | 절차/가이드 중심 |
| Expat Claim Form | 보험 청구서 | 입력 필드 중심 |
| Dental Claim Form | 치과 청구서 | 표 + 입력 필드 혼합 |

---

## 🛠 사용 라이브러리 및 스택

| 라이브러리 | 사용 이유 |
|------------|----------|
| pdfplumber | PDF 텍스트 추출 |
| re | 정규표현식 기반 cleaning |
| json | 전처리 결과 저장 |
| pathlib | 경로 관리 |
| Jupyter Notebook | 실험 및 디버깅 |
| VSCode | 프로젝트 구조 관리 |

---

## ⚠️ PDF 전처리 공통 이슈

### 1. 텍스트 깨짐 현상

- PDF 구조 특성상 문장이 중간에 끊기는 문제 발생했음
- 예: `The public reporting bur`

👉 해결:
- 문장 기반 제거 실패
- 정규표현식 기반 패턴 제거 방식 사용했음

---

### 2. Header / Footer 반복

- 모든 페이지에 동일 문구 반복

예:
- OMB No.
- CUI (when filled in)
- PREVIOUS EDITION

👉 해결:
- 공통 cleaning 함수로 제거

---

## 🧹 Cleaning 전략

### 공통 제거

- OMB / CUI / Page 정보 제거했음
- PREVIOUS EDITION 제거했음
- DEFENSE HEALTH AGENCY 제거했음

---

### TRICARE 전용 처리

#### dd2642
- Prescribed by 제거
- TRICARE Manual 제거
- OMB approval expires 제거
- public reporting burden 제거

#### dd2527
- 행정 안내 문구 제거
- 제출 관련 안내 제거

👉 이유:
- 사용자 질의와 관련 없는 정보였음

---

### UHC 전용 처리

#### FAQ 문서
- cleaning 최소화했음
- Q&A 구조 유지했음

#### Guide 문서
- header 제거
- section 단위 분리 적용했음

#### Claim Form
- 입력 필드 제거
- 안내 문구만 유지했음

#### SOB (Schedule of Benefits)
- 표 구조 깨짐 발생했음
- 의미 단위 기준으로 재구성했음

👉 핵심:
- 문서 유형별 cleaning 전략 다르게 적용했음

---
## 🧠 핵심 설계

### 1. 파일별 Cleaning 분리

👉 이유:

- PDF 구조가 서로 달랐음  
- 동일 로직 적용 시 정보 손실 발생 가능했음  

---

### 2. Section 단위 분리

#### 📄 TRICARE

**dd2642:**
- claim_overview
- important_claim_instructions
- how_to_fill_out_form

**dd2527:**
- injury_form_instructions
- injury_general_information
- injury_type_and_cause
- injury_miscellaneous

👉 총 7개 section 구성했음  

---

#### 📄 UHC

문서별 구조 기준으로 분리했음:

- FAQ → 질문 단위  
- Guide → section 단위  
- Claim → 안내/설명 단위  
- SOB → 항목 단위  

👉 문서 유형별로 다른 기준 적용했음  

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

## 📤 결과

### 📄 TRICARE

- `outputs/json_docs/tricare_forms.json` 생성했음  
- 총 7개 section 구성했음  

---

### 📄 UHC

- `outputs/uhc/guide/*.json` 생성했음  
- `outputs/uhc/claim/*.json` 생성했음  

#### 📂 생성 파일 목록

- `business_travel_faq_chunks.json`  
- `program_guide_chunks.json`  
- `welcome_guide_chunks.json`  
- `behealthy_sob_chunks.json`  
- `uhc_claim_section_chunks.json`  

👉 문서 유형별 JSON 분리 구조로 저장했음  

---

## 🚀 다음 단계

- Section → Chunk 분리 예정이었음  
- Vector DB 구축 예정이었음  
- Retriever 연결 예정이었음  
- LangGraph 연동 예정이었음  

---

## 📌 UHC 전처리 특이사항

- SOB는 표 구조로 난이도 높았음  
- Claim Form은 RAG 활용도가 낮아 일부만 사용했음  

👉 핵심:
- 모든 문서를 동일하게 처리하지 않고
- 문서 유형별 전략을 분리했음


---

## 🎯 최종 요약

- TRICARE, UHC 모두 JSON 기반 전처리 완료했음  
- 문서 유형별 구조에 맞춘 전처리 설계 적용했음  
- RAG 적용을 위한 데이터 구조화 완료 상태였음  
