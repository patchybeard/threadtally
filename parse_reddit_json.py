from __future__ import annotations
import json
import sys
from pathlib import Path
from datetime import datetime, timezone
import pandas as pd

REPO_ROOT = Path(__file__).resolve().parent
RAW_DIR = REPO_ROOT / "data" / "raw"
PROCESSED_DIR = REPO_ROOT / "data" / "processed"
PROCESSED_DIR.mkdir(parents=True, exist_ok=True)

def die(msg: str, code: int = 1):
    print(msg, file=sys.stderr)
    raise SystemExit(code)

def find_raw_files(all_files: bool) -> list[Path]:
    files = sorted(RAW_DIR.glob("*.json"), key=lambda p: p.stat().st_mtime)
    if not files:
        die(f"No JSON files found in {RAW_DIR}. Import JSON or run scrape first.")
    return files if all_files else [files[-1]]

def safe_get(d: dict, key: str, default=None):
    return d.get(key, default) if isinstance(d, dict) else default

def parse_one_file(path: Path):
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception as e:
        die(f"Failed to read/parse JSON: {path}\n{e}")

    threads = data.get("threads")
    if not isinstance(threads, list):
        die(f"JSON missing 'threads' list: {path}")

    meta = data.get("meta", {})
    meta_run_id = safe_get(meta, "run_id", path.stem)
    fetched_at = safe_get(meta, "fetched_at_utc", None)

    thread_rows = []
    comment_rows = []
    doc_rows = []

    for t in threads:
        thread_id = safe_get(t, "id")
        if not thread_id:
            continue

        subreddit = safe_get(t, "subreddit")
        title = safe_get(t, "title", "") or ""
        selftext = safe_get(t, "selftext", "") or ""
        url = safe_get(t, "url")
        permalink = safe_get(t, "permalink")
        created_utc = safe_get(t, "created_utc")
        score = safe_get(t, "score")
        author = safe_get(t, "author")

        thread_rows.append({
            "run_id": meta_run_id,
            "source_file": path.name,
            "subreddit": subreddit,
            "thread_id": thread_id,
            "title": title,
            "selftext": selftext,
            "url": url,
            "permalink": permalink,
            "created_utc": created_utc,
            "score": score,
            "author": author,
            "fetched_at_utc": fetched_at,
        })

        # One "doc" row for the post (title + body)
        post_text = (title + "\n\n" + selftext).strip()
        doc_rows.append({
            "run_id": meta_run_id,
            "source_file": path.name,
            "doc_kind": "post",
            "doc_id": f"t3_{thread_id}",
            "thread_id": thread_id,
            "subreddit": subreddit,
            "created_utc": created_utc,
            "score": score,
            "author": author,
            "text": post_text,
            "url": url,
            "permalink": permalink,
        })

        comments = safe_get(t, "comments", []) or []
        if not isinstance(comments, list):
            comments = []

        for c in comments:
            cid = safe_get(c, "id")
            if not cid:
                continue

            c_author = safe_get(c, "author")
            c_body = safe_get(c, "body", "") or ""
            c_created = safe_get(c, "created_utc")
            c_score = safe_get(c, "score")
            parent_id = safe_get(c, "parent_id")
            link_id = safe_get(c, "link_id")

            comment_rows.append({
                "run_id": meta_run_id,
                "source_file": path.name,
                "subreddit": subreddit,
                "thread_id": thread_id,
                "comment_id": cid,
                "author": c_author,
                "body": c_body,
                "created_utc": c_created,
                "score": c_score,
                "parent_id": parent_id,
                "link_id": link_id,
                "fetched_at_utc": fetched_at,
            })

            doc_rows.append({
                "run_id": meta_run_id,
                "source_file": path.name,
                "doc_kind": "comment",
                "doc_id": f"t1_{cid}",
                "thread_id": thread_id,
                "subreddit": subreddit,
                "created_utc": c_created,
                "score": c_score,
                "author": c_author,
                "text": c_body,
                "url": url,
                "permalink": permalink,
            })

    return thread_rows, comment_rows, doc_rows

def main():
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--all", action="store_true", help="Parse all JSON files in data/raw and combine")
    args = ap.parse_args()

    files = find_raw_files(all_files=args.all)

    all_threads = []
    all_comments = []
    all_docs = []

    for f in files:
        trows, crows, drows = parse_one_file(f)
        all_threads.extend(trows)
        all_comments.extend(crows)
        all_docs.extend(drows)

    df_threads = pd.DataFrame(all_threads)
    df_comments = pd.DataFrame(all_comments)
    df_docs = pd.DataFrame(all_docs)

    # Normalize types a bit
    for df in (df_threads, df_comments, df_docs):
        if "created_utc" in df.columns:
            df["created_utc"] = pd.to_numeric(df["created_utc"], errors="coerce")
        if "score" in df.columns:
            df["score"] = pd.to_numeric(df["score"], errors="coerce")

    out_threads = PROCESSED_DIR / "reddit_threads.csv"
    out_comments = PROCESSED_DIR / "reddit_comments.csv"
    out_docs = PROCESSED_DIR / "reddit_docs.csv"

    df_threads.to_csv(out_threads, index=False)
    df_comments.to_csv(out_comments, index=False)
    df_docs.to_csv(out_docs, index=False)

    print(f"Wrote: {out_docs}  rows={len(df_docs)}")
    print(f"Wrote: {out_threads}  rows={len(df_threads)}")
    print(f"Wrote: {out_comments}  rows={len(df_comments)}")
    print(f"Parsed files: {len(files)} (use --all to combine all)")

if __name__ == "__main__":
    main()
