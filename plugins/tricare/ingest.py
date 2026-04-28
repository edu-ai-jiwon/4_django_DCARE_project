# plugins/tricare/ingest.py
# Tricare PDF/CSV → 청킹 → tricare_plans 컬렉션 저장
# 실행: python scripts/ingest_all.py tricare
from __future__ import annotations

import csv, os, re
from pathlib import Path
from typing import Any

import fitz
import pdfplumber
import chromadb
from chromadb.config import Settings
from chromadb.utils.embedding_functions import SentenceTransformerEmbeddingFunction as STEmbedding
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent.parent
DATA_DIR = BASE_DIR / "data" / "tricare" / "guide"
load_dotenv(dotenv_path=BASE_DIR / ".env")

VECTORDB_PATH   = os.getenv("VECTORDB_PATH", str(BASE_DIR / "vectordb"))
COLLECTION_NAME = "tricare_plans"
MIN_CHUNK_CHARS = 80

MULTILINGUAL_EF = STEmbedding(model_name="paraphrase-multilingual-mpnet-base-v2")

# OCONUS 키워드 (해외/한국 관련 페이지 필터링용)
OCONUS_KEYWORDS = [
    "overseas", "oconus", "outside the continental",
    "south korea", "korea", "usfk",
    "outside the u.s.", "outside the united states",
    "international", "host nation",
    "tricare prime overseas", "tricare select overseas",
    "tricare prime remote overseas",
]

# PDF 파일 목록
PDF_FILES: list[dict[str, Any]] = [
    {"path": DATA_DIR / "Costs_Fees.pdf",                                                "location": "BOTH",   "table": True,  "doc_type": "cost_guide", "plan": "all"},
    {"path": DATA_DIR / "Overseas_HB(해외 프로그램 안내서).pdf",                          "location": "OCONUS", "table": False, "doc_type": "handbook",   "plan": "all"},
    {"path": DATA_DIR / "Pharmacy_HB(tricare 약국 프로그램 안내서).pdf",                  "location": "BOTH",   "table": True,  "doc_type": "handbook",   "plan": "all"},
    {"path": DATA_DIR / "TOP_Handbook_AUG_2023_FINAL_092223_508 (1).pdf",               "location": "OCONUS", "table": False, "doc_type": "handbook",   "plan": "TRICARE Overseas Program"},
    {"path": DATA_DIR / "NGR_HB(국가방위군 및 예비군을 위한 트라이케어 안내서).pdf",       "location": "BOTH",   "table": True,  "doc_type": "handbook",   "plan": "NGR"},
    {"path": DATA_DIR / "TFL_HB(평생 트라이케어).pdf",                                   "location": "BOTH",   "table": True,  "doc_type": "handbook",   "plan": "TRICARE For Life"},
    {"path": DATA_DIR / "TFL_HB(2022).pdf",                                             "location": "BOTH",   "table": True,  "doc_type": "handbook",   "plan": "TRICARE For Life"},
    {"path": DATA_DIR / "TRICARE_ADDP_HB_FINAL_508c(현역 군인 치과 프로그램 안내서).pdf", "location": "BOTH",   "table": False, "doc_type": "handbook",   "plan": "ADDP"},
    {"path": DATA_DIR / "ADDP_Brochure_FINAL_122624_508c.pdf",                          "location": "BOTH",   "table": False, "doc_type": "brochure",   "plan": "ADDP"},
    {"path": DATA_DIR / "Maternity_Br (1).pdf",                                         "location": "BOTH",   "table": False, "doc_type": "brochure",   "plan": "all"},
    {"path": DATA_DIR / "QLEs_FS (2).pdf",                                              "location": "BOTH",   "table": False, "doc_type": "fact_sheet", "plan": "all"},
    {"path": DATA_DIR / "Retiring_NGR_Br.pdf",                                          "location": "BOTH",   "table": False, "doc_type": "brochure",   "plan": "NGR"},
    {"path": DATA_DIR / "Plans_Overview_FS_1.pdf",                                      "location": "BOTH",   "table": False, "doc_type": "fact_sheet", "plan": "all"},
]

# CSV 파일 목록
CSV_FILES = {
    "plans":      DATA_DIR / "TricarePlans.csv",
    "costs":      DATA_DIR / "Health_Plan_Costs.csv",
    "mental":     DATA_DIR / "mental_health_services.csv",
    "exclusions": DATA_DIR / "tricare_exclusions.csv",
}


# 유틸리티

def _clean(text: str) -> str:
    text = text.replace("\xa0", " ").replace("​", " ")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _is_noise_line(line: str) -> bool:
    return any(re.match(p, line.lower().strip()) for p in [
        r"^visit www\.tricare",
        r"^for more information.*go to",
        r"^updated (january|february|march|april|may|june|july|august|"
        r"september|october|november|december)",
    ])


def _oconus_relevant(text: str) -> bool:
    return any(kw in text.lower() for kw in OCONUS_KEYWORDS)


def _norm_cell(cell: str) -> str:
    c = (cell or "").strip()
    if c in {"✓", "√", "v", "V", "●", "Yes", "yes", "Y"}:
        return "Covered"
    if c in {"✗", "×", "x", "X", "✘", "No", "no", "N"}:
        return "Not covered"
    return c or "N/A"


# 청킹 함수

def _pdf_chunks() -> tuple[list, list, list]:
    texts, metas, ids = [], [], []
    for fi in PDF_FILES:
        p: Path = fi["path"]
        if not p.exists():
            print(f"[SKIP] {p.name}")
            continue
        doc   = fitz.open(str(p))
        count = 0
        for i, page in enumerate(doc):
            raw = _clean(page.get_text("text"))
            if not raw:
                continue
            if fi["location"] == "BOTH" and not _oconus_relevant(raw):
                continue
            cleaned = "\n".join(ln for ln in raw.split("\n") if not _is_noise_line(ln))
            paras   = [pr.strip() for pr in cleaned.split("\n\n") if len(pr.strip()) >= MIN_CHUNK_CHARS]
            if not paras and len(cleaned.strip()) >= MIN_CHUNK_CHARS:
                paras = [cleaned.strip()]
            for j, para in enumerate(paras):
                texts.append(para)
                metas.append({
                    "insurer": "tricare", "source_type": "pdf",
                    "file_name": p.name, "page": i + 1,
                    "plan": fi["plan"], "doc_type": fi["doc_type"],
                    "location": fi["location"], "language": "en",
                    "year": "", "url": "", "topic": fi["doc_type"], "table_json": "",
                })
                ids.append(f"tc_pdf_{p.stem}_{i+1}_{j}")
                count += 1
        doc.close()
        print(f"[PDF] {p.name}: {count}청크")
    return texts, metas, ids


def _table_chunks() -> tuple[list, list, list]:
    texts, metas, ids = [], [], []
    for fi in PDF_FILES:
        if not fi.get("table"):
            continue
        p: Path = fi["path"]
        if not p.exists():
            continue
        count = 0
        with pdfplumber.open(str(p)) as pdf:
            for pg_i, page in enumerate(pdf.pages, start=1):
                for t_i, table in enumerate(page.extract_tables() or []):
                    if not table:
                        continue
                    tbl_text = "\n".join(
                        " | ".join(_norm_cell(str(c or "")) for c in row)
                        for row in table
                    )
                    if len(tbl_text.strip()) < 30:
                        continue
                    texts.append(tbl_text)
                    metas.append({
                        "insurer": "tricare", "source_type": "pdf_table",
                        "file_name": p.name, "page": pg_i,
                        "plan": fi["plan"], "doc_type": "cost_table",
                        "location": fi["location"], "language": "en",
                        "year": "", "url": "", "topic": "cost_table", "table_json": "",
                    })
                    ids.append(f"tc_tbl_{p.stem}_{pg_i}_{t_i}")
                    count += 1
        print(f"[TABLE] {p.name}: {count}표")
    return texts, metas, ids


def _csv_chunks() -> tuple[list, list, list]:
    texts, metas, ids = [], [], []
    for key, path in CSV_FILES.items():
        if not path.exists():
            print(f"[SKIP] {path.name}")
            continue
        count = 0
        with open(path, encoding="utf-8-sig", newline="") as f:
            for r_i, row in enumerate(csv.DictReader(f)):
                content = " | ".join(f"{k}: {v}" for k, v in row.items() if v and str(v).strip())
                if not content:
                    continue
                plan = row.get("plan_name", row.get("플랜명", "")).strip() if key == "plans" else "all"
                texts.append(content)
                metas.append({
                    "insurer": "tricare", "source_type": "pdf",
                    "file_name": path.name, "page": 0,
                    "plan": plan or "all", "doc_type": "csv_data",
                    "location": "BOTH", "language": "en",
                    "year": "", "url": "", "topic": key, "table_json": "",
                })
                ids.append(f"tc_csv_{key}_{r_i}")
                count += 1
        print(f"[CSV] {path.name}: {count}행")
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
        print(f"[tricare] 저장 {min(i + batch, len(texts))}/{len(texts)}")

    print(f"[tricare] {COLLECTION_NAME} 완료 ({collection.count()}개)")


def run() -> None:
    print(f"\n[tricare] 청킹 시작 → {COLLECTION_NAME}")

    all_texts, all_metas, all_ids = [], [], []
    for fn in [_pdf_chunks, _table_chunks, _csv_chunks]:
        t, m, i = fn()
        all_texts.extend(t)
        all_metas.extend(m)
        all_ids.extend(i)

    print(f"\n[tricare] 총 청크: {len(all_texts)}개")
    _save(all_texts, all_metas, all_ids)


if __name__ == "__main__":
    run()
