# ThreadTally — API Usage Overview (Template)

> Replace placeholders with your exact endpoints and patterns. This document is designed to help reviewers quickly validate scope.

## Endpoints used (typical)
- Retrieve a specific thread submission (public)
- Retrieve comments for that submission (public)
- Optional: limited search in a specific subreddit with a user-set limit (e.g., 25)

## Authentication
- OAuth "script app" (PRAW)
- Read-only scope
- User-Agent includes app name + contact

## Request volume (typical)
- Threads per run: [1–25]
- Runs per day: [X]
- Throttling: sleep between requests, exponential backoff on 429
- No parallel crawling

## Prohibited behaviors (explicitly not done)
- Bulk export of subreddits
- User profiling or tracking across threads
- Rehosting raw Reddit content as a dataset
