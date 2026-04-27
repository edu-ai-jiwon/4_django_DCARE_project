# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# utils/comparison.py
# 역할 : 보험사/플랜 비교표 데이터 조립 헬퍼
#
# 사용처:
#   - within_node.py  (① 보험 내 플랜 비교)
#   - compare_node.py (② 보험사 간 비교)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

from __future__ import annotations

# ──────────────────────────────────────────────────────────────
# 공개 API
# ──────────────────────────────────────────────────────────────

def build_comparison_prompt(
    docs_by_subject: dict[str, list[str]],
    user_query: str,
    language: str,
) -> str:
    """
    RAG 검색 결과를 비교표 생성용 LLM 프롬프트로 조립한다.

    Args:
        docs_by_subject: 비교 대상별 검색 문서 리스트
                         예) {"UHCG Gold": ["doc1", "doc2"], "Cigna": ["doc3"]}
        user_query     : 사용자 원문 질의 (컨텍스트 유지)
        language       : 응답 언어 코드 (예: "ko", "en")

    Returns:
        LLM user 메시지로 전달할 비교 프롬프트 문자열
    """
    lang_instruction = _language_instruction(language)

    # 비교 대상별 문서 블록 조립
    context_blocks = []
    for subject, docs in docs_by_subject.items():
        combined = "\n---\n".join(docs[:5])  # 대상당 최대 5개 문서 사용
        context_blocks.append(f"[{subject}]\n{combined}")

    context_str = "\n\n".join(context_blocks)

    prompt = f"""{lang_instruction}

다음은 비교 대상별로 검색된 보험 문서입니다:

{context_str}

사용자 질의: {user_query}

위 문서를 바탕으로 비교표를 작성해 주세요.
반드시 다음 항목을 포함하세요:
- 보장 범위 (Covered Benefits)
- 보장 한도 (Coverage Limit)
- 제외 항목 (Exclusions)
- 본인부담금 구조 (Cost Sharing)
- 특이 사항 (Notes)

각 항목에 대해 문서에 명시된 내용만 사용하고, 불확실한 경우 "정보 없음"으로 표시하세요.
응답 마지막에 출처 문서 요약을 한 줄씩 추가해 주세요."""

    return prompt


def merge_docs_for_comparison(
    results_by_subject: dict[str, dict],
) -> dict[str, list[str]]:
    """
    ChromaDB 멀티 컬렉션 검색 결과를 비교표 빌더 형식으로 변환한다.

    Args:
        results_by_subject: {subject: chromadb_query_result}
                            chromadb_query_result 형식:
                            {"documents": [[doc1, doc2, ...]], "metadatas": [[meta1, ...]]}

    Returns:
        {subject: [doc_text_list]}
    """
    merged: dict[str, list[str]] = {}
    for subject, result in results_by_subject.items():
        docs = result.get("documents", [[]])[0]  # 첫 번째 쿼리 결과만 사용
        merged[subject] = [d for d in docs if d and d.strip()]
    return merged


def rerank_by_relevance(
    docs: list[str],
    metadatas: list[dict],
    top_k: int = 5,
) -> list[dict]:
    """
    ChromaDB 검색 결과를 메타데이터 기준으로 정렬한다.

    현재 전략: source_type=="pdf_table" 을 우선 배치
    (표 데이터가 구조화돼 있어 비교에 더 유리)

    Args:
        docs     : 문서 텍스트 리스트
        metadatas: 각 문서의 메타데이터 리스트
        top_k    : 반환할 최대 문서 수

    Returns:
        [{"content": str, "metadata": dict}, ...] (정렬 후 top_k 개)
    """
    paired = [
        {"content": doc, "metadata": meta}
        for doc, meta in zip(docs, metadatas)
        if doc and doc.strip()
    ]

    # pdf_table 우선 정렬 → 나머지는 원래 순서(ChromaDB cosine 점수 순) 유지
    tables  = [p for p in paired if p["metadata"].get("source_type") == "pdf_table"]
    others  = [p for p in paired if p["metadata"].get("source_type") != "pdf_table"]

    return (tables + others)[:top_k]


# ──────────────────────────────────────────────────────────────
# 내부 함수
# ──────────────────────────────────────────────────────────────

def _language_instruction(language: str) -> str:
    """언어 코드 → LLM 응답 언어 지시문"""
    instructions = {
        "ko": "반드시 한국어로 답변하세요.",
        "en": "Please respond in English.",
        "ja": "必ず日本語で回答してください。",
        "zh": "请用中文回答。",
        "fr": "Répondez en français.",
        "de": "Bitte antworten Sie auf Deutsch.",
        "es": "Por favor, responda en español.",
    }
    return instructions.get(language, "Please respond in English.")
