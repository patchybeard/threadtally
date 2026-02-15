# ThreadTally — Architecture Overview

## High-level diagram (ASCII)

User (local browser)
    |
    |  (localhost UI)
    v
Flask Web App (ThreadTally)
  - Tabs:
    - Authorized (OAuth/PRAW, read-only)
    - Offline (user-provided JSON import)
    - Run Pipeline (local processing)
    |
    | writes/reads local files only
    v
Local Data Store (disk)
  - data/raw/        (combined JSON from user imports or fetched threads)
  - data/processed/  (CSV outputs: docs, mentions, votes, ranked models)
  - charts/          (top N chart image)

## Modes

### 1) Authorized (OAuth/PRAW)
- User runs ThreadTally locally
- App fetches **public posts/comments** for user-selected threads (and optionally a limited search query)
- Throttling + backoff applied
- Outputs saved locally

### 2) Offline (No-API Helper)
- User pastes thread URLs
- Tool generates the equivalent `.json` URLs
- User opens them in browser and saves JSON files
- User uploads JSON files into ThreadTally
- App merges/dedupes and saves combined raw file locally

### 3) Run Pipeline
- Parses JSON into normalized CSV tables
- Extracts model mentions
- Computes vote-weighted scores
- Produces ranked model list + chart
- Displays Top N in the UI

## Data minimization principles
- Only fetch/analyze what the user explicitly supplies (thread URLs)
- Store locally, user-controlled retention
- No redistribution, no external hosting
