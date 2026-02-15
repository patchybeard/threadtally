from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

from model_normalize import ModelNormalizer

REPO_ROOT = Path(__file__).resolve().parent
PROCESSED_DIR = REPO_ROOT / "data" / "processed"
REF_DIR = REPO_ROOT / "data" / "reference"

VOTES_CSV = PROCESSED_DIR / "votes_v2.csv"
OUT_CSV = PROCESSED_DIR / "ranked_models_v2.csv"
OUT_PNG = PROCESSED_DIR / "top15_score_v2.png"
ALIASES_CSV = REF_DIR / "model_aliases.csv"


def die(msg: str, code: int = 1):
    print(msg, file=sys.stderr)
    raise SystemExit(code)


def main():
    if not VOTES_CSV.exists():
        die(f"Missing {VOTES_CSV}. Run score_votes_v2.py first.")

    df = pd.read_csv(VOTES_CSV)
    if df.empty:
        df.to_csv(OUT_CSV, index=False)
        print(f"Wrote: {OUT_CSV} (0 rows) — nothing to rank.")
        return

    normalizer = ModelNormalizer(str(ALIASES_CSV))

    if "canonical_model" not in df.columns:
        die("votes_v2.csv missing 'canonical_model' column.")

    # Ensure numeric
    for c in ["mentions", "unique_threads", "vote_score", "avg_vote", "avg_doc_score"]:
        if c in df.columns:
            df[c] = pd.to_numeric(df[c], errors="coerce")

    df["mentions"] = df.get("mentions", 0).fillna(0)
    df["unique_threads"] = df.get("unique_threads", 0).fillna(0)
    df["vote_score"] = df.get("vote_score", 0).fillna(0)
    df["avg_vote"] = df.get("avg_vote", 0).fillna(0)
    df["avg_doc_score"] = df.get("avg_doc_score", 0).fillna(0)

    # Normalize/alias canonical_model and compute canonical_key (even if upstream didn't)
    norm_pairs = df["canonical_model"].astype(str).map(normalizer.normalize)
    df["canonical_key"] = norm_pairs.map(lambda t: t[0])
    df["canonical_model"] = norm_pairs.map(lambda t: t[1])

    # Aggregate by canonical_key to collapse residual variants
    # - vote_score: sum
    # - mentions: sum
    # - unique_threads: MAX (safer than sum)
    # - avg_vote / avg_doc_score: weighted avg by mentions
    def _pick_display(s: pd.Series) -> str:
        vals = [v for v in s.dropna().astype(str).tolist() if v.strip()]
        if not vals:
            return ""
        vc = s.value_counts()
        top_n = vc.max()
        cands = [v for v, c in vc.items() if c == top_n]
        cands.sort(key=lambda x: (-len(x), x))
        return cands[0]

    df["_avg_vote_wsum"] = df["avg_vote"] * df["mentions"]
    df["_avg_doc_wsum"] = df["avg_doc_score"] * df["mentions"]

    agg = df.groupby("canonical_key", as_index=False).agg(
        canonical_model=("canonical_model", _pick_display),
        vote_score=("vote_score", "sum"),
        mentions=("mentions", "sum"),
        unique_threads=("unique_threads", "max"),
        _avg_vote_wsum=("_avg_vote_wsum", "sum"),
        _avg_doc_wsum=("_avg_doc_wsum", "sum"),
    )

    denom = agg["mentions"].replace(0, 1)
    agg["avg_vote"] = agg["_avg_vote_wsum"] / denom
    agg["avg_doc_score"] = agg["_avg_doc_wsum"] / denom
    agg = agg.drop(columns=["_avg_vote_wsum", "_avg_doc_wsum"])

    # Final score formula (tunable)
    agg["score_v2"] = (
        agg["vote_score"]
        + 0.75 * agg["unique_threads"]
        + 0.10 * agg["mentions"]
    )

    agg = agg.sort_values("score_v2", ascending=False).reset_index(drop=True)
    agg["rank"] = agg.index + 1

    cols = ["rank", "canonical_model", "canonical_key", "score_v2", "vote_score", "unique_threads", "mentions", "avg_vote", "avg_doc_score"]
    agg = agg[cols]

    agg.to_csv(OUT_CSV, index=False)
    print(f"Wrote: {OUT_CSV} rows={len(agg)}")

    # Chart top 15
    top = agg.head(15).copy()

    try:
        import matplotlib.pyplot as plt
        plt.figure(figsize=(12, 7))
        plt.barh(top["canonical_model"][::-1], top["score_v2"][::-1])
        plt.xlabel("Score (v2)")
        plt.title("ThreadTally — Top 15 Models (v2)")
        plt.tight_layout()
        plt.savefig(OUT_PNG, dpi=150)
        plt.close()
        print(f"Wrote: {OUT_PNG}")
    except Exception as e:
        print("Chart not generated (matplotlib missing or failed):", e, file=sys.stderr)


if __name__ == "__main__":
    main()
