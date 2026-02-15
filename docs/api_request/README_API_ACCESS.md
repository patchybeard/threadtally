# ThreadTally — Reddit Data API Access Request Packet

**Project:** ThreadTally  
**Type:** Local-only web app (localhost), read-only analysis tool  
**Primary use case:** Summarize product/model recommendations inside a small, user-selected set of public Reddit threads (e.g., bookshelf speaker recommendations).  
**Target users:** Redditors doing research; personal/local use.

---

## 1) What ThreadTally does (plain English)

ThreadTally helps a user quickly understand *which models are being recommended* in a Reddit discussion without reading hundreds of comments.

A user provides one or more public Reddit thread URLs. The app retrieves the public post + public comments for those specific threads, extracts likely product model mentions (e.g., “KEF Q150”, “ELAC B6.2”), normalizes common variants (punctuation/dashes/spaces), and produces:

- A **Top N** ranked table of models (mentions + vote-weighted score)
- A simple chart of top results
- Locally saved CSV outputs for transparency/debugging

ThreadTally is **read-only**. It does **not** post, comment, vote, message users, moderate, or automate actions on Reddit.

---

## 2) Scope of data accessed

**Accessed (public only):**
- Public post title/body text for user-selected threads
- Public comment text for those threads
- Public metadata needed for ranking (e.g., comment score)

**Not accessed:**
- Private messages, modmail, drafts
- Private subreddit content
- Any content not reachable from the user-provided thread URLs
- Deleted/removed content recovery beyond what the API returns normally
- Personal data beyond what appears publicly in the thread content

---

## 3) Access pattern (important)

ThreadTally is intentionally **not a crawler**. It does not “discover” links or fetch the entire subreddit history.

**User-driven only:**
1) User supplies a thread URL list (typically 1–25 threads)
2) App fetches only those threads + their comments
3) App processes locally and displays aggregated results

Optional: If the user uses “Authorized” mode, it may run a *limited* search query to find a small set of threads matching a query, constrained by the UI “limit” field (e.g., 25). This is still **small-batch** and not bulk export.

---

## 4) Rate limiting and respectful use

ThreadTally will:
- Implement throttling to remain below published limits (e.g., <100 requests/minute per OAuth client id where applicable)
- Use exponential backoff on 429 responses
- Avoid parallel burst requests
- Include a clear User-Agent identifying the app name and contact U/MARKETOSTRICH

> **User-Agent example:** `ThreadTally/1.0 (by u/MARKETOSTRICH; contact: matthew.beigel@gmail.com)`

---

## 5) Storage, retention, and redistribution

- Data is stored **locally** on the user’s machine (not uploaded to third parties)
- Outputs are derived summaries (counts/scores) and locally generated CSVs
- The tool does **not** redistribute raw Reddit content and does **not** provide a third-party feed
- The user can delete local data files at any time

---

## 6) Why Devvit is not the right platform

Devvit is designed for apps that run inside Reddit’s hosted ecosystem. ThreadTally is a **local-only** tool that needs:

- Local file import (offline workflow)
- Local pipeline execution (multi-step parsing/scoring/ranking)
- Local CSV/chart generation and storage
- A localhost web UI not embedded in Reddit

These requirements are not a fit for Devvit’s hosted-in-Reddit model.

---

## 7) Compliance summary (checklist)

- ✅ Read-only
- ✅ User-driven scope (specific threads only; no bulk crawling)
- ✅ Public content only
- ✅ Throttled and respectful use
- ✅ No user profiling / ad targeting
- ✅ No resale / redistribution of raw content
- ✅ Local storage only; user-controlled deletion
- ✅ Clear contact/User-Agent (u/MarketOstrich)

---

## 8) What we can provide upon request

- Source code access (GitHub or zipped repository) with secrets removed
- A short screencast showing the UI + scope controls
- Logs demonstrating throttling/backoff behavior
