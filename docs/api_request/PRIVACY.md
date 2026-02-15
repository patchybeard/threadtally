# ThreadTally — Privacy & Data Handling (Local Tool)

**Effective date:** 2026-01-25  
**Project:** ThreadTally (local-only web application)

## Summary
ThreadTally is a local tool that analyzes public Reddit threads selected by the user to summarize product/model recommendations. It does not operate as a hosted service.

## What data ThreadTally accesses
- Public post title/body text for user-selected Reddit threads
- Public comment text for those threads
- Public metadata required for scoring (e.g., comment score)

## What data ThreadTally does NOT access
- Private messages or modmail
- Private subreddit content
- Any content beyond the user-provided thread URLs
- Non-public user information

## How data is used
- Extract product/model mentions from text
- Normalize naming variants (punctuation/dash/spacing) to reduce fragmentation
- Produce aggregated summaries (Top N ranked models)

## Storage and retention
- Data is stored locally on the user’s machine only (not sent to a third party)
- The user may delete local data files at any time
- The tool does not provide a public API or redistribution channel for raw Reddit content

## Sharing and resale
- ThreadTally does not resell data
- ThreadTally does not redistribute raw Reddit content as a dataset or feed

## Tracking and profiling
- ThreadTally does not build profiles of Reddit users
- ThreadTally does not perform ad targeting or cross-thread user tracking

## Contact (u/MarketOstrich)
- Reddit username: u/MarketOstrich
- Email: matthew.beigel@gmail.com
