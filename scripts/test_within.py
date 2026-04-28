# scripts/test_within.py
# within_node (보험 내 비교) 단독 실행 테스트
# 실행: python scripts/test_within.py
import os, sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dotenv import load_dotenv
load_dotenv()

from graph.nodes.within_node import within

_BASE_STATE = dict(
    language      = "ko",
    intent        = "within_compare",
    intents       = ["within_compare"],
    insurers      = [],
    slots         = {},
    missing_slots = [],
    retrieved_docs= [],
    calc_result   = {},
    nhis_step     = "eligibility_check",
    nhis_eligible = None,
    answer        = "",
)

TESTS = [
    {
        "name"        : "TRICARE 플랜 비교 (한국어)",
        "session_id"  : "test_tricare_01",
        "user_message": "TRICARE Prime와 TRICARE Select의 보장 범위와 비용 차이를 비교해줘",
        "language"    : "ko",
        "insurer"     : "tricare",
    },
    {
        "name"        : "UHC 플랜 비교 (영어)",
        "session_id"  : "test_uhcg_01",
        "user_message": "Compare the coverage and out-of-pocket costs of UHCG expat insurance plans",
        "language"    : "en",
        "insurer"     : "uhcg",
    },
]

for tc in TESTS:
    name = tc.pop("name")
    state = {**_BASE_STATE, **tc}

    print(f"\n{'='*60}")
    print(f"테스트: {name}")
    print(f"질문: {state['user_message']}")
    print("=" * 60)

    result = within(state)
    docs   = result.get("retrieved_docs", [])
    answer = result.get("answer", "")

    print(f"검색 문서 수: {len(docs)}개")
    if docs:
        print(f"상위 문서 출처: {docs[0].get('metadata', {}).get('file_name', 'N/A')}")
    print(f"\n[답변]\n{answer}")
