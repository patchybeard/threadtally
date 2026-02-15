import os
import json
import time
import sys
import traceback
from pathlib import Path
from datetime import datetime, timezone

import praw

REPO_ROOT = Path(__file__).resolve().parent
RAW_DIR = REPO_ROOT / "data" / "raw"
RAW_DIR.mkdir(parents=True, exist_ok=True)

def get_reddit():
    cid = os.getenv("REDDIT_CLIENT_ID")
    secret = os.getenv("REDDIT_CLIENT_SECRET")
    ua = os.getenv("REDDIT_USER_AGENT")

    if cid and secret:
        return praw.Reddit(
            client_id=cid,
            client_secret=secret,
            user_agent=ua or "ThreadTally (local webapp)",
        )

    return praw.Reddit("default")

def serialize_submission(s):
    return {
        "id": s.id,
        "title": s.title,
        "selftext": s.selftext or "",
        "url": s.url,
        "permalink": s.permalink,
        "created_utc": getattr(s, "created_utc", None),
        "score": getattr(s, "score", None),
        "num_comments": getattr(s, "num_comments", None),
        "subreddit": str(s.subreddit),
        "author": str(s.author) if s.author else None,
    }

def fetch_threads(subreddit: str, query: str | None, limit: int):
    reddit = get_reddit()
    sub = reddit.subreddit(subreddit)

    submissions = []
    if query and query.strip():
        for s in sub.search(query.strip(), sort="new", limit=limit):
            submissions.append(s)
    else:
        for s in sub.new(limit=limit):
            submissions.append(s)

    return submissions

def fetch_comments(reddit, submission):
    submission.comments.replace_more(limit=None)
    comments = []
    for c in submission.comments.list():
        comments.append({
            "id": c.id,
            "author": str(c.author) if c.author else None,
            "body": c.body,
            "created_utc": getattr(c, "created_utc", None),
            "score": getattr(c, "score", None),
            "parent_id": getattr(c, "parent_id", None),
            "link_id": getattr(c, "link_id", None),
        })
    return comments

def main():
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--subreddit", default="BudgetAudiophile")
    ap.add_argument("--query", default="")
    ap.add_argument("--limit", type=int, default=25)
    ap.add_argument("--sleep", type=float, default=0.25)
    ap.add_argument("--debug", action="store_true")
    args = ap.parse_args()

    if args.debug:
        cid = os.getenv("REDDIT_CLIENT_ID", "")
        secret = os.getenv("REDDIT_CLIENT_SECRET", "")
        ua = os.getenv("REDDIT_USER_AGENT", "")
        print("[debug] REDDIT_CLIENT_ID_len =", len(cid))
        print("[debug] REDDIT_CLIENT_SECRET_len =", len(secret))
        print("[debug] REDDIT_USER_AGENT_len =", len(ua))

    reddit = get_reddit()

    # early request: forces auth errors immediately
    list(reddit.subreddit(args.subreddit).hot(limit=1))

    threads = fetch_threads(args.subreddit, args.query, args.limit)

    run_id = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    out = {
        "meta": {
            "project": "ThreadTally",
            "run_id": run_id,
            "subreddit": args.subreddit,
            "query": args.query,
            "limit": args.limit,
            "fetched_at_utc": datetime.now(timezone.utc).isoformat(),
        },
        "threads": [],
    }

    for s in threads:
        info = serialize_submission(s)
        submission = reddit.submission(id=s.id)
        info["comments"] = fetch_comments(reddit, submission)
        out["threads"].append(info)
        time.sleep(args.sleep)

    outfile = RAW_DIR / f"scrape_{args.subreddit}_{run_id}.json"
    outfile.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"Wrote: {outfile}")
    print(f"Threads: {len(out['threads'])}")
    total_comments = sum(len(t["comments"]) for t in out["threads"])
    print(f"Comments: {total_comments}")

if __name__ == "__main__":
    try:
        main()
    except Exception:
        traceback.print_exc()
        raise
