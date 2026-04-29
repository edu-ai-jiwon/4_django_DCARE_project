# plugins/uhcg/ingest.py
# UHC guide + claim PDFs > 청킹 > uhcg_plans 컬렉션 저장
# 실행: python scripts/ingest_all.py uhcg
from __future__ import annotations

import os, re
from pathlib import Path

import fitz
import pdfplumber
import chromadb
from chromadb.config import Settings
from chromadb.utils.embedding_functions import SentenceTransformerEmbeddingFunction as STEmbedding
from dotenv import load_dotenv

BASE_DIR  = Path(__file__).resolve().parent.parent.parent
GUIDE_DIR = BASE_DIR / "data" / "uhc" / "guide"
CLAIM_DIR = BASE_DIR / "data" / "uhc" / "claim"
load_dotenv(dotenv_path=BASE_DIR / ".env")

VECTORDB_PATH   = os.getenv("VECTORDB_PATH", str(BASE_DIR / "vectordb"))
COLLECTION_NAME = "uhcg_plans"
MIN_CHUNK_CHARS = 50
INSURER         = "uhcg"

MULTILINGUAL_EF = STEmbedding(model_name="BAAI/bge-m3"
)


# 공통 유틸리티

def _clean(text: str) -> str:
    text = text.replace("\x0c", " ").replace("\xa0", " ")
    text = re.sub(r"©.*", "", text)
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _load_pages(path: Path) -> list[dict]:
    doc   = fitz.open(str(path))
    pages = [{"page": i + 1, "text": page.get_text("text")} for i, page in enumerate(doc)]
    doc.close()
    return pages


def _is_noise(text: str) -> bool:
    t = text.lower().strip()
    return len(text.strip()) < MIN_CHUNK_CHARS or any(
        kw in t for kw in ["explore the ways", "try a virtual visit", "customer support"]
    )


def _get_guide_file(keyword: str) -> Path | None:
    for f in GUIDE_DIR.glob("*.pdf"):
        if keyword in f.name:
            return f
    return None


# 1. Welcome Guide

_WELCOME_EXCLUDE     = {1, 15, 16}
_WELCOME_TABLE_PAGES = {8}
_COUNTRY_FALLBACK    = [
    "Africa",
    "Australia",
    "Bahrain, Jordan, Kuwait, Lebanon, Kingdom of Saudi Arabia, Oman, Qatar, UAE",
    "Canada",
    "Europe, plus Austria, Belgium and Luxembourg",
    "Japan",
    "India",
]


def _welcome_table_rows(path: Path, page_num: int) -> list[str]:
    header = [
        "When you are in",
        "The locally licensed insurer or administrator",
        "Carry the following ID cards",
        "For assistance, contact",
    ]
    rows_text = []
    with pdfplumber.open(str(path)) as pdf:
        page = pdf.pages[page_num - 1]
        for table in (page.extract_tables() or []):
            if not table or len(table) < 2:
                continue
            for r_idx, row in enumerate(table[1:], start=1):
                row = (list(row) + [""] * 4)[:4]
                if not row[0] and r_idx <= len(_COUNTRY_FALLBACK):
                    row[0] = _COUNTRY_FALLBACK[r_idx - 1]
                parts = [f"{h}: {str(c).strip()}" for h, c in zip(header, row) if c and str(c).strip()]
                if parts:
                    rows_text.append("\n".join(parts))
    return rows_text


def _welcome_chunks(path: Path) -> tuple[list, list, list]:
    texts, metas, ids = [], [], []
    base = {"insurer": INSURER, "file_name": path.name, "language": "en",
            "year": "", "url": "", "table_json": "", "plan": "", "doc_type": "member_guide"}
    for pg in _load_pages(path):
        p = pg["page"]
        if p in _WELCOME_EXCLUDE:
            continue
        if p in _WELCOME_TABLE_PAGES:
            for r_i, row_text in enumerate(_welcome_table_rows(path, p)):
                texts.append(row_text)
                metas.append({**base, "source_type": "pdf_table", "page": p, "topic": "network_table"})
                ids.append(f"uhcg_welcome_p{p}_r{r_i}")
        else:
            cleaned = _clean(pg["text"])
            if not _is_noise(cleaned):
                texts.append(cleaned)
                metas.append({**base, "source_type": "pdf", "page": p, "topic": "member_guide"})
                ids.append(f"uhcg_welcome_p{p}")
    return texts, metas, ids


# 2. BeHealthy SOB

def _sob_chunks(path: Path) -> tuple[list, list, list]:
    texts, metas, ids = [], [], []
    base = {"insurer": INSURER, "source_type": "pdf_table", "file_name": path.name,
            "language": "en", "year": "", "url": "", "table_json": "",
            "plan": "", "doc_type": "benefit_summary", "topic": "benefit_summary"}
    with pdfplumber.open(str(path)) as pdf:
        for pg_i, page in enumerate(pdf.pages, start=1):
            for t_i, table in enumerate(page.extract_tables() or []):
                if not table or len(table) < 2:
                    continue
                header = table[0]
                for r_i, row in enumerate(table[1:], start=1):
                    row = (list(row) + [""] * len(header))[:len(header)]
                    parts = [
                        f"{str(h).strip()}: {str(c).strip()}"
                        for h, c in zip(header, row) if h and c and str(c).strip()
                    ]
                    if parts:
                        texts.append("\n".join(parts))
                        metas.append({**base, "page": pg_i})
                        ids.append(f"uhcg_sob_p{pg_i}_t{t_i}_r{r_i}")
    return texts, metas, ids


# 3. Program Guide

_PROG_SECTIONS = [
    "GLOBAL EMERGENCY SERVICES", "PROGRAM GUIDELINES",
    "MEDICAL & SECURITY ASSISTANCE AND EVACUATION", "PROGRAM DESCRIPTION",
    "How To Use UnitedHealthcare Global Assistance Services",
    "MEDICAL ASSISTANCE SERVICES", "MEDICAL EVACUATION & REPATRIATION SERVICES",
    "WORLDWIDE DESTINATION INTELLIGENCE", "SECURITY AND POLITICAL EVACUATION SERVICES",
    "NATURAL DISASTER EVACUATION SERVICES", "TRAVEL ASSISTANCE SERVICES",
    "PROGRAM DEFINITIONS", "CONDITIONS AND LIMITATIONS",
]


def _program_chunks(path: Path) -> tuple[list, list, list]:
    texts, metas, ids = [], [], []
    pages     = _load_pages(path)
    full_text = "\n".join(pg["text"] for pg in pages)
    for b in ["", "", "▪", "●", "•", "◦", "·"]:
        full_text = full_text.replace(b, "-")
    full_text = re.sub(r"-\s*\n\s*", "- ", full_text)
    full_text = re.sub(r"\n{3,}", "\n\n", full_text)

    pattern = "|".join(re.escape(s) for s in _PROG_SECTIONS)
    parts   = re.split(f"({pattern})", full_text)

    base = {"insurer": INSURER, "source_type": "pdf", "file_name": path.name,
            "page": 0, "language": "en", "year": "", "url": "", "table_json": "",
            "plan": "", "doc_type": "program_guide"}

    for i in range(1, len(parts), 2):
        title   = parts[i].strip()
        content = (parts[i + 1].strip() if i + 1 < len(parts) else "")
        if len(content) >= 30:
            texts.append(f"{title}\n{content}")
            metas.append({**base, "topic": title[:80]})
            ids.append(f"uhcg_prog_sec{i // 2}")
    return texts, metas, ids


# 4. Business Travel FAQ

def _faq_chunks(path: Path) -> tuple[list, list, list]:
    texts, metas, ids = [], [], []
    pages     = _load_pages(path)
    full_text = "\n".join(_clean(pg["text"]) for pg in pages)
    full_text = re.sub(r"©.*", "", full_text)
    full_text = re.sub(r"\n{3,}", "\n\n", full_text)

    base = {"insurer": INSURER, "source_type": "pdf", "file_name": path.name,
            "page": 0, "language": "en", "year": "", "url": "", "table_json": "",
            "plan": "", "doc_type": "faq", "topic": "faq"}

    for i, block in enumerate(re.split(r"(?=^[A-Z][^\n?]+\?)", full_text, flags=re.MULTILINE)):
        block = block.strip()
        if "?" not in block:
            continue
        q, a = block.split("?", 1)
        q, a = q.strip() + "?", a.strip()
        if len(q) >= 10 and len(a) >= 20:
            texts.append(f"Question: {q}\nAnswer: {a}")
            metas.append({**base})
            ids.append(f"uhcg_faq_{i}")
    return texts, metas, ids


# 5. Claim Forms

def _claim_chunks(path: Path) -> tuple[list, list, list]:
    texts, metas, ids = [], [], []
    doc          = fitz.open(str(path))
    pages_text   = []
    for page in doc:
        blocks = sorted(page.get_text("blocks"), key=lambda b: (round(b[1], 1), round(b[0], 1)))
        pages_text.append("\n".join(b[4].strip() for b in blocks if b[4].strip()))
    doc.close()

    full_text = re.sub(r"\x0c", " ", "\n".join(pages_text))
    full_text = re.sub(r"\n+", "\n", full_text)
    full_text = re.sub(r"[ \t]+", " ", full_text)
    full_text = re.sub(r"continued", "", full_text, flags=re.IGNORECASE)

    sections = re.split(r"(section\s*[123].*?)", full_text, flags=re.IGNORECASE)
    base     = {"insurer": INSURER, "source_type": "pdf", "file_name": path.name,
                "page": 0, "language": "en", "year": "", "url": "", "table_json": "",
                "doc_type": "claim_form", "topic": "claim_form"}

    for i in range(1, len(sections), 2):
        title   = sections[i].strip()
        content = re.sub(r"[ \t]+", " ", (sections[i + 1] if i + 1 < len(sections) else "").strip())
        m       = re.search(r"section\s*([123])", title, flags=re.IGNORECASE)
        sec_num = int(m.group(1)) if m else 99
        if len(content) >= 20:
            texts.append(f"{title}\n{content}")
            metas.append({**base, "plan": path.stem})
            ids.append(f"uhcg_claim_{path.stem}_sec{sec_num}")
    return texts, metas, ids


# ChromaDB 저장

def _save(texts: list, metas: list, ids: list) -> None:
    client = chromadb.PersistentClient(
        path=VECTORDB_PATH,
        settings=Settings(anonymized_telemetry=False),
    )
    try:
        client.delete_collection(COLLECTION_NAME)
        print(f"[INFO] 기존 컬렉션 삭제: {COLLECTION_NAME}")
    except Exception:
        pass

    collection = client.create_collection(
        name=COLLECTION_NAME,
        embedding_function=MULTILINGUAL_EF,
    )

    batch = 100
    for i in range(0, len(texts), batch):
        collection.add(
            documents=texts[i:i + batch],
            metadatas=metas[i:i + batch],
            ids=ids[i:i + batch],
        )
        print(f"[uhcg] 저장 {min(i + batch, len(texts))}/{len(texts)}")

    print(f"[uhcg] {COLLECTION_NAME} 완료 ({collection.count()}개)")


def run() -> None:
    print(f"\n[uhcg] 청킹 시작 → {COLLECTION_NAME}")
    all_texts, all_metas, all_ids = [], [], []

    # guide 파일 디스패치 (키워드 -> 처리 함수, 중복 방지용 타입 키)
    dispatch = [
        ("Welcome Guide",               _welcome_chunks,  "welcome"),
        ("BeHealthy SOB",               _sob_chunks,      "sob"),
        ("SAL-EU",                      _sob_chunks,      "sob"),
        ("Program Guide",               _program_chunks,  "program"),
        ("Business Travel Member FAQs", _faq_chunks,      "faq"),
        ("MBR-BT",                      _faq_chunks,      "faq"),
    ]
    processed = set()
    for keyword, fn, ftype in dispatch:
        if ftype in processed:
            continue
        path = _get_guide_file(keyword)
        if path is None:
            continue
        t, m, i = fn(path)
        all_texts.extend(t); all_metas.extend(m); all_ids.extend(i)
        print(f"[guide] {path.name}: {len(t)}청크")
        processed.add(ftype)

    # claim 파일 전체 처리
    for claim_pdf in CLAIM_DIR.glob("*.pdf"):
        t, m, i = _claim_chunks(claim_pdf)
        all_texts.extend(t); all_metas.extend(m); all_ids.extend(i)
        print(f"[claim] {claim_pdf.name}: {len(t)}청크")

    print(f"\n[uhcg] 총 청크: {len(all_texts)}개")
    _save(all_texts, all_metas, all_ids)


if __name__ == "__main__":
    run()
