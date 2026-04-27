# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# graph/nodes/generate_node.py
# 역할 : RAG 검색 결과를 바탕으로 최종 답변을 생성한다 (공통 생성 노드)
#
# 파이프라인: ④ 절차 안내에서 retrieve_node 다음에 호출
#             (① ② ③ ⑤ ⑥ 는 각 노드가 내부적으로 직접 생성)
#
# 진입 조건 : retrieve_node 다음 (intent == "procedure")
# 다음 노드  : END
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

from __future__ import annotations

import os

from openai import OpenAI

from utils.schemas import InsuranceState

# ──────────────────────────────────────────────────────────────
# 상수
# ──────────────────────────────────────────────────────────────
_GENERATE_SYSTEM_PROMPT = """You are a helpful health insurance assistant.
Answer the user's question based ONLY on the provided reference documents.
If the documents do not contain enough information, say so clearly.
Always cite which document your answer is based on.
Keep your answer concise and structured."""

_LANGUAGE_INSTRUCTION = {
    "ko": "반드시 한국어로 답변하세요.",
    "en": "Please respond in English.",
    "ja": "必ず日本語で回答してください。",
    "zh": "请用中文回答。",
    "fr": "Répondez en français.",
    "de": "Bitte antworten Sie auf Deutsch.",
    "es": "Por favor, responda en español.",
}


# ──────────────────────────────────────────────────────────────
# 노드 함수
# ──────────────────────────────────────────────────────────────

def generate(state: InsuranceState) -> dict:
    """
    [공통 생성] retrieved_docs 를 기반으로 LLM 답변을 생성한다.

    읽는 state 필드:
        user_message   : 사용자 원문 질의
        language       : 응답 언어 코드
        retrieved_docs : retrieve_node 가 반환한 문서 리스트
        slots          : 추출된 슬롯 (추가 컨텍스트로 활용)

    반환 dict (InsuranceState 업데이트):
        answer : 생성된 최종 응답 텍스트
    """
    answer = call_llm_with_docs(
        user_query     = state["user_message"],
        retrieved_docs = state.get("retrieved_docs", []),
        language       = state.get("language", "en"),
        extra_context  = state.get("slots", {}),
    )
    return {"answer": answer}


# ──────────────────────────────────────────────────────────────
# 공개 헬퍼 — 다른 노드에서도 직접 호출 가능
# ──────────────────────────────────────────────────────────────

def call_llm_with_docs(
    user_query    : str,
    retrieved_docs: list[dict],
    language      : str,
    extra_context : dict | None = None,
    system_prompt : str | None  = None,
) -> str:
    """
    검색된 문서를 컨텍스트로 LLM 을 호출해 답변을 생성한다.

    모든 파이프라인 노드가 최종 답변 생성 시 이 함수를 사용한다.

    Args:
        user_query     : 사용자 원문 질의
        retrieved_docs : [{"content": str, "metadata": dict}, ...] 문서 리스트
        language       : 응답 언어 코드 (예: "ko", "en")
        extra_context  : 추가 컨텍스트 dict (슬롯 정보 등)
        system_prompt  : 커스텀 시스템 프롬프트 (None 이면 기본값 사용)

    Returns:
        LLM 생성 답변 텍스트. 오류 시 오류 안내 메시지 반환.
    """
    # ── 언어 지시문 ────────────────────────────────────────────
    lang_inst = _LANGUAGE_INSTRUCTION.get(language, "Please respond in English.")

    # ── 시스템 프롬프트 조립 ───────────────────────────────────
    sys_prompt = (system_prompt or _GENERATE_SYSTEM_PROMPT) + f"\n\n{lang_inst}"

    # ── 참조 문서 블록 조립 ─────────────────────────────────────
    if retrieved_docs:
        doc_blocks = []
        for i, doc in enumerate(retrieved_docs[:7], start=1):  # 최대 7개 사용
            meta   = doc.get("metadata", {})
            source = _format_source(meta)
            doc_blocks.append(f"[문서 {i} | {source}]\n{doc['content']}")
        context_str = "\n\n".join(doc_blocks)
    else:
        context_str = "(검색된 문서 없음)"

    # ── 추가 컨텍스트 (슬롯 정보) ─────────────────────────────
    context_note = ""
    if extra_context:
        context_note = f"\n\n추가 정보: {extra_context}"

    # ── LLM 호출 ───────────────────────────────────────────────
    user_content = (
        f"참조 문서:\n{context_str}"
        f"{context_note}\n\n"
        f"질문: {user_query}"
    )

    try:
        client   = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
        response = client.chat.completions.create(
            model       = "gpt-4o",
            messages    = [
                {"role": "system", "content": sys_prompt},
                {"role": "user",   "content": user_content},
            ],
            max_tokens  = 1500,
            temperature = 0.3,
        )
        return response.choices[0].message.content.strip()

    except Exception as e:
        return (
            f"죄송합니다. 응답 생성 중 오류가 발생했습니다. 잠시 후 다시 시도해 주세요.\n"
            f"Sorry, an error occurred while generating a response. Please try again.\n"
            f"(Error: {type(e).__name__})"
        )


# ──────────────────────────────────────────────────────────────
# 내부 함수
# ──────────────────────────────────────────────────────────────

def _format_source(metadata: dict) -> str:
    """메타데이터를 간결한 출처 표기 문자열로 변환한다."""
    source_type = metadata.get("source_type", "")
    if source_type == "web":
        return f"Web | {metadata.get('topic', '')} | {metadata.get('url', '')}"
    if source_type in ("pdf", "pdf_table"):
        page = metadata.get("page", "")
        return f"PDF | {metadata.get('file_name', '')} | p.{page}"
    return metadata.get("file_name", "unknown")
