from __future__ import annotations

import re
import sys
from pathlib import Path
from collections import Counter, defaultdict

import pandas as pd

from model_normalize import ModelNormalizer

REPO_ROOT = Path(__file__).resolve().parent
PROCESSED_DIR = REPO_ROOT / "data" / "processed"
REF_DIR = REPO_ROOT / "data" / "reference"

DOCS_CSV = PROCESSED_DIR / "reddit_docs.csv"
OUT_CSV = PROCESSED_DIR / "mentions_v2.csv"
CAND_CSV = PROCESSED_DIR / "model_candidates.csv"
ALIASES_CSV = REF_DIR / "model_aliases.csv"


def die(msg: str, code: int = 1):
    print(msg, file=sys.stderr)
    raise SystemExit(code)


# Same starting brands list; expand over time.
BRANDS = [
    "KEF","ELAC","POLK","SVS","KLIPSCH","JBL","SONY","YAMAHA","DENON","MARANTZ","ONKYO","PIONEER",
    "WHARFEDALE","FOCAL","DALI","PARADIGM","EMOTIVA","FLUANCE","MICCA","EDIFIER","MONOPRICE",
    "B&W","BW","BOWERS","WILKINS","Q ACOUSTICS","QACOUSTICS","JAMO","NEUMI","RSL","HSU",
    "ASCEND","AR","AUDIOENGINE","CAMBRIDGE","CANTON","CERWIN","CHANE","DYNACO","DYNAUDIO",
    "GENELEC","HARBETH","INFINITY","MAGNEPAN","MISSION","MONITOR AUDIO","NHT","PSB","REVEL",
    "SALK","SENNHEISER","TANNOY","TEAC","TRIANGLE","VANDERSTEEN","VIENNA","YAMAHA"
]

# Speaker-ish context words that help disambiguate standalone tokens.
SPEAKER_CONTEXT = [
    "speaker","speakers","bookshelf","bookself","monitor","monitors","pair","pairs","stands",
    "nearfield","passive","amp","receiver","integrated","sub","subwoofer","stereo","2.0","2.1",
]

# Brand regex
BRAND_RE = r"(?:%s)" % "|".join(sorted(set(map(re.escape, BRANDS)), key=len, reverse=True))

# A "model token" that contains at least one digit and looks like typical model formatting.
MODEL_TOKEN_RE = r"[A-Z]?[A-Z0-9][A-Z0-9\.\-]{1,20}\d[A-Z0-9\.\-]{0,20}"

# Pass 1: explicit "BRAND <token>"
MENTION_RE_1 = re.compile(
    rf"(?<!\w)({BRAND_RE})\s+({MODEL_TOKEN_RE})(?!\w)",
    flags=re.IGNORECASE
)

# Pass 2: standalone model tokens
STANDALONE_RE = re.compile(
    rf"(?<!\w)({MODEL_TOKEN_RE})(?!\w)",
    flags=re.IGNORECASE
)

# Candidate filtering: avoid common numeric junk
BAD_TOKENS = set([
    "2.0","2.1","5.1","7.1","3.5","6.5","8.0","10.0","12.0","14.0",
    "1080","1440","4K","8K",
])


def norm_space(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "").strip())


def norm_brand(b: str) -> str:
    b = norm_space(b).upper()
    b = b.replace("QACOUSTICS", "Q ACOUSTICS")
    if b in ("BW", "BOWERS", "WILKINS"):
        b = "B&W"
    return b


def extract_context_words(text: str) -> set[str]:
    t = (text or "").lower()
    return {w for w in SPEAKER_CONTEXT if w in t}


def pick_brand_from_thread(thread_brands: Counter, doc_brands: Counter) -> str | None:
    if doc_brands:
        return doc_brands.most_common(1)[0][0]
    if thread_brands:
        return thread_brands.most_common(1)[0][0]
    return None


def looks_like_real_model(token: str) -> bool:
    t = token.upper().strip()
    if not t:
        return False
    if t in BAD_TOKENS:
        return False
    if len(t) < 2 or len(t) > 25:
        return False
    if re.fullmatch(r"[\d\.\-]+", t):
        return False
    return True


def _best_display_name(series: pd.Series) -> str:
    vals = [v for v in series.dropna().astype(str).tolist() if v.strip()]
    if not vals:
        return ""
    counts = Counter(vals)
    best_count = max(counts.values())
    candidates = [v for v, c in counts.items() if c == best_count]
    candidates.sort(key=lambda s: (-len(s), s))
    return candidates[0]


def main():
    if not DOCS_CSV.exists():
        die(f"Missing {DOCS_CSV}. Run parse_reddit_json.py first.")

    docs = pd.read_csv(DOCS_CSV)
    if "text" not in docs.columns:
        die("reddit_docs.csv missing 'text' column.")
    if "thread_id" not in docs.columns:
        die("reddit_docs.csv missing 'thread_id' column.")

    normalizer = ModelNormalizer(str(ALIASES_CSV))

    # 1) Build thread-level brand counts from explicit brand mentions (Pass 1)
    thread_brand_counts: dict[str, Counter] = defaultdict(Counter)
    for _, r in docs.iterrows():
        raw_text = str(r.get("text", "") or "")
        tid = str(r.get("thread_id", "") or "")
        if not raw_text.strip() or not tid:
            continue

        text = normalizer.prepare_text_for_matching(raw_text)
        for m in MENTION_RE_1.finditer(text):
            b = norm_brand(m.group(1))
            thread_brand_counts[tid][b] += 1

    rows = []
    candidate_counter = Counter()
    candidate_examples: dict[str, list[str]] = defaultdict(list)

    # 2) Extract mentions
    for _, r in docs.iterrows():
        raw_text = str(r.get("text", "") or "")
        if not raw_text.strip():
            continue

        text = normalizer.prepare_text_for_matching(raw_text)

        tid = str(r.get("thread_id", "") or "")
        kind = r.get("doc_kind")
        doc_id = r.get("doc_id")
        subreddit = r.get("subreddit")
        score = r.get("score")
        created_utc = r.get("created_utc")
        source_file = r.get("source_file")
        run_id = r.get("run_id")

        # Brand mentions inside this doc
        doc_brands = Counter()
        for m in MENTION_RE_1.finditer(text):
            doc_brands[norm_brand(m.group(1))] += 1

        speaker_ctx = extract_context_words(raw_text)

        # Pass 1: explicit brand+model
        for m in MENTION_RE_1.finditer(text):
            brand_raw = m.group(1) or ""
            model_raw = m.group(2) or ""

            model_tok = normalizer.normalize_display(model_raw).upper()
            brand_tok = norm_brand(brand_raw)

            combined_raw = f"{brand_tok} {model_tok}".strip()
            canonical_key, canonical_model = normalizer.normalize(combined_raw)

            out_brand = canonical_model.split(" ", 1)[0] if " " in canonical_model else brand_tok

            rows.append({
                "canonical_key": canonical_key,
                "canonical_model": canonical_model,
                "brand": out_brand,
                "model_token": model_tok,
                "found_text": m.group(0),
                "method": "brand_token",
                "confidence": 1.0,
                "doc_kind": kind,
                "doc_id": doc_id,
                "thread_id": tid,
                "subreddit": subreddit,
                "score": score,
                "created_utc": created_utc,
                "source_file": source_file,
                "run_id": run_id,
            })

        # Pass 2: standalone tokens
        thread_counts = thread_brand_counts.get(tid, Counter())

        for m in STANDALONE_RE.finditer(text):
            token_raw = (m.group(1) or "").strip()
            token_norm = normalizer.normalize_display(token_raw).upper()

            if not looks_like_real_model(token_norm):
                continue

            candidate_counter[token_norm] += 1
            if len(candidate_examples[token_norm]) < 3:
                snippet = (raw_text or "").replace("\n", " ")
                snippet = re.sub(r"\s+", " ", snippet).strip()
                candidate_examples[token_norm].append(snippet[:220])

            # Keep if token maps via aliases
            if normalizer.has_alias(token_norm):
                canonical_key, canonical_model = normalizer.normalize(token_norm)
                brand_guess = canonical_model.split(" ", 1)[0] if " " in canonical_model else ""

                rows.append({
                    "canonical_key": canonical_key,
                    "canonical_model": canonical_model,
                    "brand": norm_brand(brand_guess) if brand_guess else "",
                    "model_token": token_norm,
                    "found_text": token_norm,
                    "method": "alias_token",
                    "confidence": 0.95,
                    "doc_kind": kind,
                    "doc_id": doc_id,
                    "thread_id": tid,
                    "subreddit": subreddit,
                    "score": score,
                    "created_utc": created_utc,
                    "source_file": source_file,
                    "run_id": run_id,
                })
                continue

            # If no alias, attempt brand inference only with speaker context
            if not speaker_ctx:
                continue

            inferred_brand = pick_brand_from_thread(thread_counts, doc_brands)
            if not inferred_brand:
                continue

            combined_raw = f"{inferred_brand} {token_norm}".strip()
            canonical_key, canonical_model = normalizer.normalize(combined_raw)

            out_brand = canonical_model.split(" ", 1)[0] if " " in canonical_model else inferred_brand

            rows.append({
                "canonical_key": canonical_key,
                "canonical_model": canonical_model,
                "brand": out_brand,
                "model_token": token_norm,
                "found_text": token_norm,
                "method": "inferred_brand",
                "confidence": 0.65,
                "doc_kind": kind,
                "doc_id": doc_id,
                "thread_id": tid,
                "subreddit": subreddit,
                "score": score,
                "created_utc": created_utc,
                "source_file": source_file,
                "run_id": run_id,
            })

    df = pd.DataFrame(rows)

    # Always write candidates
    cand_rows = []
    for tok, cnt in candidate_counter.most_common():
        ex = " | ".join(candidate_examples.get(tok, [])[:3])
        cand_rows.append({"token": tok, "count": cnt, "examples": ex})
    pd.DataFrame(cand_rows).to_csv(CAND_CSV, index=False)

    if df.empty:
        df.to_csv(OUT_CSV, index=False)
        print(f"Wrote: {OUT_CSV} (0 rows) — no mentions matched.")
        print(f"Wrote: {CAND_CSV} rows={len(cand_rows)} (candidate tokens for review)")
        return

    if "score" in df.columns:
        df["score"] = pd.to_numeric(df["score"], errors="coerce").fillna(0)

    # Stable display per canonical_key
    display_map = df.groupby("canonical_key")["canonical_model"].apply(_best_display_name).to_dict()
    df["canonical_model"] = df["canonical_key"].map(display_map).fillna(df["canonical_model"])

    df.to_csv(OUT_CSV, index=False)

    print(f"Wrote: {OUT_CSV} rows={len(df)}")
    print("Unique canonical keys:", df["canonical_key"].nunique())
    print(f"Wrote: {CAND_CSV} rows={len(cand_rows)} (candidate tokens for review)")


if __name__ == "__main__":
    main()
