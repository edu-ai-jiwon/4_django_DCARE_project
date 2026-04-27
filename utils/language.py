# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# utils/language.py
# 역할 : 사용자 질의의 언어를 감지한다.
#
# 전략 : langdetect(빠름) → 신뢰도 낮으면 LLM fallback(정확)
# 지원 언어 : 한국어·영어·일본어·중국어·프랑스어·독일어·스페인어
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

from __future__ import annotations

import os
from langdetect import detect, detect_langs
from openai import OpenAI

# ──────────────────────────────────────────────────────────────
# 상수
# ──────────────────────────────────────────────────────────────

# 시스템이 지원하는 언어 코드 (langdetect 코드 기준)
SUPPORTED_LANGS = {"ko", "en", "ja", "zh-cn", "zh-tw", "fr", "de", "es"}

# langdetect 결과를 내부 코드로 정규화하는 매핑
LANG_NORMALIZE = {
    "zh-cn": "zh",
    "zh-tw": "zh",
}

# langdetect 신뢰도가 이 값 미만이면 LLM fallback 사용
CONFIDENCE_THRESHOLD = 0.85

# LLM fallback 에서 사용하는 분류 프롬프트
_LANG_SYSTEM_PROMPT = """You are a language detector.
Given a text, respond with ONLY one of these language codes:
ko (Korean), en (English), ja (Japanese), zh (Chinese),
fr (French), de (German), es (Spanish).
If uncertain, respond with "en".
Respond with the code only, no explanation."""


# ──────────────────────────────────────────────────────────────
# 공개 API
# ──────────────────────────────────────────────────────────────

def detect_language(text: str) -> str:
    """
    텍스트의 언어를 감지한다.

    1단계: langdetect 로 빠르게 감지 → 신뢰도 >= CONFIDENCE_THRESHOLD 이면 반환
    2단계: 신뢰도 낮거나 지원 언어가 아니면 LLM 으로 재감지

    Args:
        text: 언어를 감지할 원문 텍스트

    Returns:
        언어 코드 문자열 ("ko" | "en" | "ja" | "zh" | "fr" | "de" | "es")
        감지 실패 시 기본값 "en" 반환
    """
    if not text or not text.strip():
        return "en"

    # ── 1단계: langdetect ──────────────────────────────────────
    try:
        results = detect_langs(text)          # [(lang, prob), ...] 형태
        top     = results[0]
        lang    = LANG_NORMALIZE.get(top.lang, top.lang)
        prob    = top.prob

        # 지원 언어이면서 신뢰도가 충분하면 바로 반환
        if lang in SUPPORTED_LANGS and prob >= CONFIDENCE_THRESHOLD:
            return lang

    except Exception:
        pass  # langdetect 실패 시 LLM fallback 으로 이동

    # ── 2단계: LLM fallback ────────────────────────────────────
    return _llm_detect(text)


# ──────────────────────────────────────────────────────────────
# 내부 함수
# ──────────────────────────────────────────────────────────────

def _llm_detect(text: str) -> str:
    """
    OpenAI LLM 을 사용해 언어를 감지한다. (fallback)

    짧은 텍스트나 혼합 언어 처리에 langdetect 보다 정확하다.
    실패 시 기본값 "en" 을 반환한다.
    """
    try:
        client   = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
        response = client.chat.completions.create(
            model    = "gpt-4o-mini",   # 빠르고 저렴한 모델로 충분
            messages = [
                {"role": "system", "content": _LANG_SYSTEM_PROMPT},
                {"role": "user",   "content": text[:200]},  # 앞 200자만 사용
            ],
            max_tokens  = 5,
            temperature = 0,
        )
        lang = response.choices[0].message.content.strip().lower()

        # 반환값이 지원 언어 코드인지 검증
        if lang in {"ko", "en", "ja", "zh", "fr", "de", "es"}:
            return lang

    except Exception:
        pass

    return "en"
