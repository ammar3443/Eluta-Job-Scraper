# Early Stop Options for Cross-Run Deduplication

## Background

The scraper uses `seen_jobs.json` to track job IDs across runs. Within a run, duplicates are
skipped before classification — so no Claude tokens are wasted on already-seen jobs regardless
of which stop strategy is used. The stop strategy only affects how many HTTP requests are made.

We previously had a rule: "stop when an entire page is all duplicates." This was removed because
as new jobs are posted on Eluta, older jobs shift to later pages — so no page is ever 100%
duplicates in practice. The rule never triggered.

---

## Current approach: Option A — Date cutoff only

**What it does:** Relies entirely on `cutoff_days: 3` in `config.yaml`. Stops when a full page
has only jobs older than 3 days. Individual duplicates within that window are still skipped via
`seen_jobs.json` before classification.

**Why we chose it:** Same Claude token cost as all other options (duplicates are skipped before
classify regardless). Simpler logic. The date cutoff is the semantically correct stop condition.

**Downside:** Fetches slightly more pages than necessary since it doesn't stop early on duplicate-heavy pages.

---

## Alternative options (not implemented)

### Option B — Duplicate ratio threshold
Stop when X% of a page's jobs are already in `seen_jobs.json` (e.g. 70%).

- Tolerant of page shifting (doesn't require 100% duplicates)
- Stops earlier than Option A when deep in already-processed content
- Requires tuning the threshold — too low and you miss new jobs, too high and it barely helps
- Same Claude token cost as A

### Option C — Consecutive new jobs counter
Track new jobs found across a rolling window of recent pages. Stop when the last N pages
combined yield fewer than M new jobs (e.g. last 3 pages yield fewer than 2 new jobs total).

- Adapts to how active the job board is
- Most resilient to page shifting
- More complex to implement and tune
- Same Claude token cost as A

### Option D — Consecutive seen jobs streak
Stop when you hit a streak of X seen jobs in a row (not per page, but sequentially across jobs).

- More granular than per-page checks
- Simple to implement
- Sensitive to job ordering within a page
- Same Claude token cost as A

---

## To switch strategies

All options have identical Claude token usage since duplicates are skipped before `classify_job`
is called. The tradeoff is purely in number of HTTP requests to Eluta.

To implement any of the above, modify the loop in `run_scrape()` in `scraper.py`.
