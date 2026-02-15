from __future__ import annotations

from flask import Flask, render_template, jsonify, request, send_from_directory
from pathlib import Path
import subprocess
import sys
import os
import json
from datetime import datetime, timezone
import traceback
import pandas as pd

# Optional .env loader
try:
    from dotenv import load_dotenv
except Exception:
    load_dotenv = None

BASE_DIR = Path(__file__).resolve().parent
REPO_ROOT = BASE_DIR.parent

if load_dotenv:
    load_dotenv(REPO_ROOT / ".env")

DATA_DIR = REPO_ROOT / "data"
RAW_DIR = DATA_DIR / "raw"
PROCESSED_DIR = DATA_DIR / "processed"

RAW_DIR.mkdir(parents=True, exist_ok=True)
PROCESSED_DIR.mkdir(parents=True, exist_ok=True)

app = Flask(
    __name__,
    template_folder=str(BASE_DIR / "templates"),
    static_folder=str(BASE_DIR / "static"),
    static_url_path="/static",
)

# ---------- helpers ----------

def run_cmd(cmd: list[str]) -> dict:
    """
    Run a command in the repo root and return rich debug info.
    """
    p = subprocess.run(
        cmd,
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
        env={**os.environ, "PYTHONUNBUFFERED": "1"},
    )
    stdout = p.stdout or ""
    stderr = p.stderr or ""
    combined = (stdout + ("\n" if stdout and stderr else "") + stderr).strip()

    return {
        "cmd": " ".join(cmd),
        "exit_code": p.returncode,
        "stdout": stdout,
        "stderr": stderr,
        "combined": combined,
    }

def safe_filename(name: str) -> str:
    return "".join(ch if ch.isalnum() or ch in "._-" else "_" for ch in (name or "upload.json"))

def reddit_native_to_threadtally(native, filename="upload.json") -> dict:
    """
    Convert Reddit's native thread JSON ([postListing, commentListing]) into
    ThreadTally's expected wrapper: {"meta":..., "threads":[...]}.
    """
    if not (isinstance(native, list) and len(native) >= 2):
        raise ValueError(f"{filename}: Expected Reddit native JSON list with 2 items.")

    post_listing = native[0]
    comment_listing = native[1]

    def get(d, *path, default=None):
        cur = d
        for p in path:
            if isinstance(cur, dict) and p in cur:
                cur = cur[p]
            else:
                return default
        return cur

    # Post
    children = get(post_listing, "data", "children", default=[])
    post_child = children[0] if isinstance(children, list) and children else None
    post = get(post_child, "data", default={}) if isinstance(post_child, dict) else {}
    if not isinstance(post, dict):
        post = {}

    thread_id = str(post.get("id") or "")
    subreddit = str(post.get("subreddit") or "")
    permalink = str(post.get("permalink") or "")
    url = str(post.get("url") or "")

    # Comments (flatten)
    flat_comments: list[dict] = []

    def walk(node):
        if not isinstance(node, dict):
            return
        kind = node.get("kind")
        data = node.get("data") if isinstance(node.get("data"), dict) else {}

        if kind == "t1":
            flat_comments.append({
                "id": data.get("id"),
                "author": data.get("author"),
                "body": data.get("body") or "",
                "created_utc": data.get("created_utc"),
                "score": data.get("score"),
                "parent_id": data.get("parent_id"),
                "link_id": data.get("link_id"),
            })

            replies = data.get("replies")
            if isinstance(replies, dict):
                rep_children = get(replies, "data", "children", default=[])
                if isinstance(rep_children, list):
                    for ch in rep_children:
                        walk(ch)

    com_children = get(comment_listing, "data", "children", default=[])
    if isinstance(com_children, list):
        for ch in com_children:
            walk(ch)

    thread_obj = {
        "id": thread_id,
        "title": post.get("title") or "",
        "selftext": post.get("selftext") or "",
        "url": url,
        "permalink": permalink,
        "created_utc": post.get("created_utc"),
        "score": post.get("score"),
        "num_comments": post.get("num_comments"),
        "subreddit": subreddit,
        "author": post.get("author"),
        "comments": flat_comments,
    }

    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    return {
        "meta": {
            "project": "ThreadTally",
            "run_id": f"native_{ts}",
            "fetched_at_utc": datetime.now(timezone.utc).isoformat(),
            "source_filename": filename,
            "note": "Converted from Reddit native thread JSON ([listing, listing]).",
        },
        "threads": [thread_obj],
    }

# ---------- routes ----------

@app.get("/")
def home():
    return render_template("index.html")

@app.get("/health")
def health():
    return {"status": "ok"}

@app.post("/api/run_pipeline")
def run_pipeline():
    """
    Runs pipeline:
      - parse_reddit_json.py --all
      - extract_mentions_v2.py (preferred) or extract_mentions.py fallback
      - score_votes_v2.py / rank_models_v2.py (or v1 if use_v2 is false)
    """
    use_v2 = bool(request.json.get("use_v2", True)) if request.is_json else True

    mention_script = "extract_mentions_v2.py" if use_v2 else "extract_mentions.py"

    steps = [
        ([sys.executable, "-u", "parse_reddit_json.py", "--all"], "parse_reddit_json.py --all"),
        ([sys.executable, "-u", mention_script], mention_script),
    ]

    if use_v2:
        steps += [
            ([sys.executable, "-u", "score_votes_v2.py", "--mentions", "data/processed/mentions_v2.csv"], "score_votes_v2.py"),
            ([sys.executable, "-u", "rank_models_v2.py"], "rank_models_v2.py"),
        ]
    else:
        steps += [
            ([sys.executable, "-u", "score_votes.py"], "score_votes.py"),
            ([sys.executable, "-u", "rank_models.py"], "rank_models.py"),
        ]

    full_log = []
    for cmd, label in steps:
        res = run_cmd(cmd)
        full_log.append(f"=== {label} ===\n{res['combined']}".strip())
        if res["exit_code"] != 0:
            return jsonify({
                "ok": False,
                "failed_step": label,
                "log": "\n\n".join(full_log),
                "debug": res,
            }), 500

    return jsonify({
        "ok": True,
        "log": "\n\n".join(full_log),
        "ranked_csv": "ranked_models_v2.csv" if use_v2 else "ranked_models.csv",
        "chart_png": "top15_score_v2.png" if use_v2 else "top15_score.png",
    })

@app.post("/api/scrape")
def scrape():
    payload = request.json or {}
    subreddit = (payload.get("subreddit") or "BudgetAudiophile").strip()
    query = (payload.get("query") or "").strip()
    limit = int(payload.get("limit") or 25)
    debug = bool(payload.get("debug") or False)

    cmd = [sys.executable, "-u", "scrape_reddit.py", "--subreddit", subreddit, "--limit", str(limit)]
    if query:
        cmd += ["--query", query]
    if debug:
        cmd += ["--debug"]

    res = run_cmd(cmd)

    resp = {
        "ok": res["exit_code"] == 0,
        "log": res["combined"],
        "debug": {
            **res,
            "env_lens": {
                "REDDIT_CLIENT_ID_len": len(os.getenv("REDDIT_CLIENT_ID", "")),
                "REDDIT_CLIENT_SECRET_len": len(os.getenv("REDDIT_CLIENT_SECRET", "")),
                "REDDIT_USER_AGENT_len": len(os.getenv("REDDIT_USER_AGENT", "")),
            },
        },
    }

    if res["exit_code"] != 0:
        app.logger.error("Scrape failed: %s\n%s", res["cmd"], res["combined"])
        return jsonify(resp), 500

    return jsonify(resp)

@app.post("/api/import_json")
def import_json():
    """
    Offline mode: upload JSON files into data/raw.
    Accepts either:
      A) ThreadTally wrapper dict: {"meta":..., "threads":[...]}
      B) Reddit native thread JSON: [postListing, commentListing] (converted automatically)
    Optionally merge + dedupe threads into a single combined raw file.
    """
    try:
        files = request.files.getlist("file")
        if not files:
            return jsonify({"ok": False, "error": "No files uploaded (expected multipart field 'file')."}), 400

        merge = (request.form.get("merge", "1") == "1")

        saved_paths: list[str] = []
        source_files: list[str] = []
        merged_by_id: dict[str, dict] = {}

        total_threads = 0
        total_comments = 0

        ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")

        for f in files:
            if not f.filename:
                continue

            raw = f.read()
            try:
                parsed = json.loads(raw)
            except Exception as e:
                return jsonify({"ok": False, "error": f"Invalid JSON in {f.filename}: {e}"}), 400

            if isinstance(parsed, list):
                parsed = reddit_native_to_threadtally(parsed, filename=f.filename)

            if not isinstance(parsed, dict):
                return jsonify({"ok": False, "error": f"Unsupported JSON shape in {f.filename}. Expected object or native list."}), 400

            threads = parsed.get("threads", [])
            if not isinstance(threads, list):
                threads = []

            total_threads += len(threads)
            for t in threads:
                if isinstance(t, dict):
                    cs = t.get("comments") or []
                    if isinstance(cs, list):
                        total_comments += len(cs)

            out_path = RAW_DIR / f"import_{ts}_{safe_filename(f.filename)}"
            out_path.write_text(json.dumps(parsed, ensure_ascii=False, indent=2), encoding="utf-8")
            saved_paths.append(str(out_path))
            source_files.append(out_path.name)

            if merge:
                for t in threads:
                    if isinstance(t, dict) and t.get("id"):
                        merged_by_id[str(t["id"])] = t

        combined_path = None
        counts_after = None

        if merge and merged_by_id:
            combined = {
                "meta": {
                    "project": "ThreadTally",
                    "run_id": f"combined_{ts}",
                    "fetched_at_utc": datetime.now(timezone.utc).isoformat(),
                    "sources": source_files,
                    "note": "Combined offline import (deduped by thread id).",
                },
                "threads": list(merged_by_id.values()),
            }
            combined_path = RAW_DIR / f"combined_{ts}.json"
            combined_path.write_text(json.dumps(combined, ensure_ascii=False, indent=2), encoding="utf-8")

            after_threads = len(combined["threads"])
            after_comments = 0
            for t in combined["threads"]:
                cs = t.get("comments") or []
                if isinstance(cs, list):
                    after_comments += len(cs)
            counts_after = {"threads": after_threads, "comments": after_comments}

        return jsonify({
            "ok": True,
            "raw_dir": str(RAW_DIR),
            "imported_files": len(saved_paths),
            "saved_paths": saved_paths,
            "merge_enabled": merge,
            "combined_path": str(combined_path) if combined_path else None,
            "counts_before_merge": {"threads": total_threads, "comments": total_comments},
            "counts_after_merge": counts_after if merge else None,
        })

    except Exception as e:
        return jsonify({
            "ok": False,
            "error": str(e),
            "trace": traceback.format_exc(),
        }), 500

@app.get("/api/top_models")
def top_models():
    # strict, defensive parsing
    try:
        n = int(request.args.get("n", 15))
    except Exception:
        n = 15

    # clamp to prevent weird UI / accidental huge payloads
    n = max(1, min(n, 200))

    use_v2 = request.args.get("v2", "1") != "0"

    csv_name = "ranked_models_v2.csv" if use_v2 else "ranked_models.csv"
    csv_path = PROCESSED_DIR / csv_name
    if not csv_path.exists():
        return jsonify({"ok": False, "error": f"Missing {csv_name}. Run the pipeline first."}), 404

    df = pd.read_csv(csv_path)

    # ensure deterministic order even if file isn't sorted for some reason
    if use_v2 and "score_v2" in df.columns:
        df = df.sort_values("score_v2", ascending=False)
    elif "score" in df.columns:
        df = df.sort_values("score", ascending=False)

    df = df.head(n)

    return jsonify({
        "ok": True,
        "n": n,
        "rows": df.to_dict(orient="records"),
        "columns": list(df.columns),
        "csv": csv_name,
    })

@app.get("/charts/<path:filename>")
def charts(filename):
    return send_from_directory(str(PROCESSED_DIR), filename)

if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5050, debug=True)
