from __future__ import annotations

import argparse
import math
import re
import sys
from pathlib import Path

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parent
PROCESSED_DIR = REPO_ROOT / "data" / "processed"

DEFAULT_MENTIONS_V2 = PROCESSED_DIR / "mentions_v2.csv"
DEFAULT_MENTIONS_V1 = PROCESSED_DIR / "mentions.csv"
OUT_CSV = PROCESSED_DIR / "votes_v2.csv"

TRAILING_PUNCT_RE = re.compile(r"[\.\,\;\:\!\?\)\]\}]+$")


def die(msg: str, code: int = 1):
    print(msg, file=sys.stderr)
    raise SystemExit(code)


def vote_weight(score: float, doc_kind: str) -> float:
    """
    Convert Reddit score to a vote weight.
    - Base vote: 1.0
    - Additional boost/penalty: log1p(abs(score)) with sign
    - Posts slightly higher influence than comments
    """
    s = float(score or 0.0)
    base = 1.0

    boost = math.log1p(abs(s))
    if s < 0:
        boost = -boost

    kind_mult = 1.35 if str(doc_kind).lower() == "post" else 1.0
    return (base + boost) * kind_mult


def resolve_mentions_path(cli_path: str | None) -> Path:
    if cli_path:
        return Path(cli_path).expanduser()

    # Prefer v2 if it exists
    if DEFAULT_MENTIONS_V2.exists():
        return DEFAULT_MENTIONS_V2
    return DEFAULT_MENTIONS_V1


def _collapse_ws(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "").strip())


def canonical_key_from_model(canonical_model: str) -> str:
    """
    Build a stable grouping key so that cosmetic differences don't split models:
      - uppercases
      - strips trailing punctuation
      - splits by LAST token (model token has no spaces in your pipeline)
      - normalizes brand lightly
      - normalizes model token aggressively (alphanumerics only)
    """
    cm = _collapse_ws(str(canonical_model)).upper()
    cm = TRAILING_PUNCT_RE.sub("", cm)

    parts = cm.split(" ")
    if len(parts) < 2:
        return re.sub(r"[^A-Z0-9]+", "", cm)

    model_tok = parts[-1]
    brand = " ".join(parts[:-1])

    # Light brand normalization (keep it conservative)
    brand = _collapse_ws(brand).upper()
    brand = brand.replace("QACOUSTICS", "Q ACOUSTICS")
    if brand in {"BW", "BOWERS"}:
        brand = "B&W"
    brand = re.sub(r"[^A-Z0-9& ]+", "", brand).strip()

    # Aggressive model token normalization: RP-600M == RP600M; DBR62. == DBR62
    model_norm = re.sub(r"[^A-Z0-9]+", "", model_tok.upper())

    return f"{brand} {model_norm}".strip()


def clean_display_model(canonical_model: str) -> str:
    """
    Clean only obvious noise for display (keep hyphens/dots if people used them),
    but remove trailing punctuation so 'ES15.' becomes 'ES15'.
    """
    cm = _collapse_ws(str(canonical_model)).upper()
    cm = TRAILING_PUNCT_RE.sub("", cm)
    return cm


def pick_best_display(series: pd.Series) -> str:
    """
    Choose a representative canonical_model for the merged group:
      1) most frequent cleaned display
      2) tie-break: prefer strings that contain a hyphen in the model token
      3) tie-break: fewer punctuation overall
      4) then shortest, then lexicographic
    """
    vc = series.value_counts()
    top = vc.max()
    cands = vc[vc == top].index.tolist()

    def score(s: str):
        s = str(s)
        parts = s.split(" ")
        model_tok = parts[-1] if parts else s
        has_hyphen = 0 if "-" in model_tok else 1  # prefer hyphen => smaller is better
        punct = len(re.findall(r"[^A-Z0-9 ]", s))
        return (has_hyphen, punct, len(s), s)

    return sorted(cands, key=score)[0]


def variants_summary(series: pd.Series, max_items: int = 6) -> str:
    """
    Helpful debug column: shows the most common original spellings.
    """
    vc = series.value_counts().head(max_items)
    return " | ".join([f"{idx} ({cnt})" for idx, cnt in vc.items()])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--mentions", default="", help="Path to mentions CSV (defaults to mentions_v2.csv if present).")
    args = ap.parse_args()

    mentions_path = resolve_mentions_path(args.mentions or None)

    if not mentions_path.exists():
        die(
            f"Missing {mentions_path}. "
            f"Run extract_mentions_v2.py (writes {DEFAULT_MENTIONS_V2.name}) or extract_mentions.py (writes {DEFAULT_MENTIONS_V1.name})."
        )

    m = pd.read_csv(mentions_path)
    if m.empty:
        m.to_csv(OUT_CSV, index=False)
        print(f"Read:  {mentions_path}")
        print(f"Wrote: {OUT_CSV} (0 rows) — no mentions to score.")
        return

    required = {"canonical_model", "thread_id", "score", "doc_kind"}
    missing = required - set(m.columns)
    if missing:
        die(f"{mentions_path.name} missing columns: {sorted(missing)}")

    # Clean + normalize
    m["canonical_model_raw"] = m["canonical_model"].astype(str)
    m["canonical_model_display"] = m["canonical_model_raw"].map(clean_display_model)
    m["canonical_key"] = m["canonical_model_raw"].map(canonical_key_from_model)

    m["score"] = pd.to_numeric(m["score"], errors="coerce").fillna(0)
    m["doc_kind"] = m["doc_kind"].fillna("comment")

    m["vote_w"] = [vote_weight(s, k) for s, k in zip(m["score"].tolist(), m["doc_kind"].tolist())]

    agg = (
        m.groupby("canonical_key", as_index=False)
        .agg(
            canonical_model=("canonical_model_display", pick_best_display),
            mentions=("canonical_key", "size"),
            unique_threads=("thread_id", "nunique"),
            vote_score=("vote_w", "sum"),
            avg_vote=("vote_w", "mean"),
            avg_doc_score=("score", "mean"),
            variants=("canonical_model_raw", variants_summary),
        )
    )

    agg = agg.sort_values("vote_score", ascending=False)

    # Keep the original column name expected by downstream steps,
    # but retain canonical_key + variants for debugging.
    agg.to_csv(OUT_CSV, index=False)

    print(f"Read:  {mentions_path}")
    print(f"Wrote: {OUT_CSV} rows={len(agg)}")
    print("Top 10 by vote_score:")
    print(agg.head(10).to_string(index=False))


if __name__ == "__main__":
    main()
