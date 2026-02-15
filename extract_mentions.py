from __future__ import annotations
import re
import sys
from pathlib import Path
import pandas as pd

REPO_ROOT = Path(__file__).resolve().parent
PROCESSED_DIR = REPO_ROOT / "data" / "processed"
REF_DIR = REPO_ROOT / "data" / "reference"
DOCS_CSV = PROCESSED_DIR / "reddit_docs.csv"
OUT_CSV = PROCESSED_DIR / "mentions.csv"
ALIASES_CSV = REF_DIR / "model_aliases.csv"

def die(msg: str, code: int = 1):
    print(msg, file=sys.stderr)
    raise SystemExit(code)

# A practical list to reduce noise. Add/remove freely.
BRANDS = [
    "KEF","ELAC","POLK","SVS","KLIPSCH","JBL","SONY","YAMAHA","DENON","MARANTZ","ONKYO","PIONEER",
    "WHARFEDALE","FOCAL","DALI","PARADIGM","EMOTIVA","FLUANCE","MICCA","EDIFIER","MONOPRICE",
    "B&W","BW","BOWERS","WILKINS","Q ACOUSTICS","QACOUSTICS","JAMO","NEUMI","RSL","HSU"
]

# Regex intent:
# - look for a brand then a model token that includes at least one digit
# - allow separators like space, hyphen
# - allow model parts like "B6.2", "Q150", "S15", "R-51M"
BRAND_RE = r"(?:%s)" % "|".join(sorted(set(map(re.escape, BRANDS)), key=len, reverse=True))
MODEL_TOKEN_RE = r"[A-Z]?[A-Z0-9][A-Z0-9\.\-]{1,20}\d[A-Z0-9\.\-]{0,20}"

MENTION_RE = re.compile(
    rf"(?<!\w)({BRAND_RE})\s+({MODEL_TOKEN_RE})(?!\w)",
    flags=re.IGNORECASE
)

# Some brands show up like "Q Acoustics 3020i" (brand has space)
# We'll normalize brand spacing.
def norm_space(s: str) -> str:
    return re.sub(r"\s+", " ", s.strip())

def normalize_model(brand: str, model: str) -> str:
    b = norm_space(brand).upper()
    m = norm_space(model).upper()
    # Common cleanup
    b = b.replace("QACOUSTICS", "Q ACOUSTICS")
    if b in ("BW", "BOWERS"):
        b = "B&W"
    return f"{b} {m}".strip()

def load_alias_map() -> dict[str, str]:
    if not ALIASES_CSV.exists():
        return {}
    try:
        df = pd.read_csv(ALIASES_CSV, comment="#")
    except Exception:
        return {}

    if not {"alias", "canonical"}.issubset(set(map(str.lower, df.columns))):
        # tolerate weird headers by trying first two cols
        if df.shape[1] >= 2:
            df.columns = ["alias", "canonical"] + list(df.columns[2:])
        else:
            return {}

    # force exact column names
    df = df.rename(columns={c: c.strip().lower() for c in df.columns})
    amap = {}
    for _, row in df.iterrows():
        a = str(row.get("alias", "")).strip()
        c = str(row.get("canonical", "")).strip()
        if a and c:
            amap[a.lower()] = c
    return amap

def apply_aliases(found: str, amap: dict[str, str]) -> str:
    # Try exact match first
    key = found.lower().strip()
    if key in amap:
        return amap[key]
    return found

def main():
    if not DOCS_CSV.exists():
        die(f"Missing {DOCS_CSV}. Run parse_reddit_json.py first.")

    docs = pd.read_csv(DOCS_CSV)
    if "text" not in docs.columns:
        die("reddit_docs.csv missing 'text' column.")

    amap = load_alias_map()

    rows = []
    for _, r in docs.iterrows():
        text = str(r.get("text", "") or "")
        if not text.strip():
            continue

        for m in MENTION_RE.finditer(text):
            brand = m.group(1)
            model = m.group(2)
            canonical = normalize_model(brand, model)
            canonical = apply_aliases(canonical, amap)

            rows.append({
                "canonical_model": canonical,
                "brand": norm_space(str(brand)).upper(),
                "found_text": m.group(0),
                "doc_kind": r.get("doc_kind"),
                "doc_id": r.get("doc_id"),
                "thread_id": r.get("thread_id"),
                "subreddit": r.get("subreddit"),
                "score": r.get("score"),
                "created_utc": r.get("created_utc"),
                "source_file": r.get("source_file"),
                "run_id": r.get("run_id"),
            })

    df = pd.DataFrame(rows)

    if df.empty:
        df.to_csv(OUT_CSV, index=False)
        print(f"Wrote: {OUT_CSV} (0 rows) — no mentions matched the default patterns.")
        print("Tip: add aliases in data/reference/model_aliases.csv or expand BRANDS in extract_mentions.py")
        return

    # normalize score to numeric
    df["score"] = pd.to_numeric(df["score"], errors="coerce").fillna(0)

    df.to_csv(OUT_CSV, index=False)
    print(f"Wrote: {OUT_CSV} rows={len(df)}")
    print("Unique models:", df["canonical_model"].nunique())

if __name__ == "__main__":
    main()
