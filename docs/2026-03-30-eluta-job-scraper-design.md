# Eluta Job Scraper — Design Spec
**Date:** 2026-03-30

---

## Problem Statement

Searching "software engineer" on eluta.ca surfaces irrelevant results (civil engineers, millwrights, electricians) because Eluta matches on description keywords. Additionally, lead/staff/team lead roles add noise for a candidate not yet qualified for those levels. Manual filtering is tedious and misses relevant postings with non-obvious titles (e.g. "Platform Engineer", "Controls Software Engineer").

---

## Goals

- Scrape eluta.ca job results and filter to software-adjacent roles only
- Classify each job into a category (backend, frontend, firmware, etc.)
- Extract years-of-experience requirements from the job description
- Produce a clean XLSX of accepted jobs per run with color-coding and auto-filters
- Produce a review file for borderline jobs and a filtered file for disputed hard-filter decisions
- Get smarter over time via human feedback without requiring model retraining

---

## Non-Goals

- Multi-site scraping (hiring.cafe and others deferred to future iteration)
- Real-time / continuous scraping (runs on-demand)
- GUI or web dashboard

---

## Architecture

Single Python script (`scraper.py`) driven by `config.yaml`. Three supporting data files grow over time.

```
JobScraper/
├── scraper.py                        # all logic
├── config.yaml                       # user settings
├── feedback.json                     # learned decisions from human review
├── output/
│   ├── eluta_YYYY-MM-DD.xlsx         # accepted jobs (color-coded, auto-filters)
│   ├── review_YYYY-MM-DD.xlsx        # borderline jobs awaiting confirm/reject
│   └── filtered_YYYY-MM-DD.json      # hard-filtered jobs, check for false positives
```

---

## Scraping Layer

**Technology:** `requests` + `BeautifulSoup` — no Playwright or headless browser needed.

**How Eluta works (confirmed via inspection):**
- Search results are server-rendered HTML, 10 `organic-job` elements per page
- Pagination: `https://www.eluta.ca/search?q=<query>&page=<N>`
- Each job card has a `data-url` attribute containing the slug for the full JD page
- Full JD available at `https://www.eluta.ca/spl/<slug>` — plain HTML, no JS
- Full description lives in `div.description div.short-text`
- Unique job ID: the hash embedded in the slug (e.g. `d46b145bbcc78f3ebfdc6d584e74f6e7`)

**Scrape flow:**
1. Fetch results page → extract 10 job cards (title, company, date, ID, spl slug)
2. If job passes hard filter → fetch `eluta.ca/spl/<slug>` for full JD
3. Hard-filtered jobs are never fetched (saves requests)
4. Stop condition: page returns 0 `organic-job` elements OR `max_pages` reached OR duplicate job IDs start appearing

**Rate limiting:**
- Random delay between requests: `delay_min` to `delay_max` seconds (configurable)
- Respects `robots.txt`
- No concurrent requests

---

## Pipeline

```
[1] Fetch results page (10 jobs)
        │
        ▼
[2] Hard Filter  ──────────────────────────────────────────► filtered_YYYY-MM-DD.json
    ├─ Seniority blocklist: lead, staff, team lead, principal
    └─ Non-technical blocklist: millwright, electrician, civil engineer,
       plumber, HVAC, welder, machinist, pipefitter, ironworker, etc.
    └─ Ambiguous list (titles escalated from past disputes) → skip to Claude
        │
        ▼
[3] Fetch full JD from eluta.ca/spl/<slug>
        │
        ▼
[4] Classifier (Flow D)
    ├─ Step 1: feedback.json exact/fuzzy title match → use stored decision (free)
    ├─ Step 2: keyword match against config categories → assign category (free)
    └─ Step 3: borderline → Claude API (Haiku)
                  Input: few-shot examples from feedback.json + title + full JD
                  Output: { relevant, category, confidence, yoe }
                  confidence < threshold → flag for review_YYYY-MM-DD.csv
        │
        ▼
[5] YOE Extraction (regex on full JD)
    Patterns: "X years", "X+ years", "X-Y years", "new grad", "entry level", "internship"
    Categories: 0-1yr / 2-3yr / 4-5yr / 5+yr / unknown
        │
        ▼
[6] Export to eluta_YYYY-MM-DD.csv
```

---

## Classifier Detail (Flow D)

### Step 1 — Feedback lookup
Check `feedback.json` for exact or fuzzy match on job title. If found, use stored decision directly. No Claude call.

### Step 2 — Keyword match
Check job title against category keyword lists from `config.yaml`. If a clear match is found, assign category. No Claude call.

When in doubt, do NOT keyword-match — let it fall through to Claude. The goal is zero missed relevant jobs.

### Step 3 — Claude (Haiku) for borderline cases
**Model:** `claude-haiku-4-5-20251001`

**Prompt structure:**
```
You are classifying job postings for a software engineering job search.

Past decisions (few-shot examples):
- "Embedded C Developer" → relevant, category: firmware [confirmed by user]
- "Process Control Engineer" → NOT relevant [user: "industrial automation, not software"]
- "Platform Engineer" → relevant, category: cloud_devops [confirmed by user]

Categories: backend, frontend, fullstack, ai_ml, firmware, cloud_devops, mobile, data, analyst, general_swe

Rules:
- When in doubt about category, use general_swe — do not miss a relevant posting
- Non-technical roles (civil, mechanical, industrial) → relevant: false
- Read the full job description for technology keywords (AWS, Python, Terraform, etc.)
- Return only JSON, no explanation

Job title: <title>
Job description: <full JD text>

Reply with exactly:
{"relevant": true/false, "category": "<category>", "confidence": 0.0-1.0, "yoe": "0-1|2-3|4-5|5+|unknown"}
```

**Confidence threshold:** `0.60` (configurable). Below this → flagged to `review_YYYY-MM-DD.xlsx`. Raise to 0.65-0.70 if review batches become too large.

**Token efficiency:**
- Claude only called for borderline jobs (not keyword-matched, not in feedback)
- Few-shot examples capped at `max_few_shot_examples` (default: 15) from feedback.json
- Full JD sent (needed for keyword signals like AWS, Terraform, Python, etc.)

---

## Cold Start Behaviour

On first run, `feedback.json` is empty. Claude uses its base knowledge to classify and score confidence. Ambiguous titles produce more review flags than later runs — this is intentional. The first batch of reviews bootstraps the feedback file quickly.

After the first `--ingest-feedback` run, Claude receives real examples from your decisions and accuracy improves.

---

## Feedback Loop

### Reviewing borderline jobs (`review_YYYY-MM-DD.xlsx`)
Open the file in Excel or Google Sheets, fill in the pre-added `confirm` (yes/no) and `reason` columns. Save, then:
```bash
python scraper.py --ingest-feedback review_2026-03-30.xlsx
```
- Confirmed jobs → added to `feedback.json` as positive examples
- Rejected jobs → added to `feedback.json` as negative examples
- Both fed as few-shot examples to Claude on next run

### Disputing filtered jobs (`filtered_YYYY-MM-DD.json`)
Open the file, find the incorrectly filtered job, add two fields:
```json
{
  "job_id": "abc123",
  "title": "Controls Engineer",
  "dispute": true,
  "reason": "Software controls role — Python and PLC experience required"
}
```
Then:
```bash
python scraper.py --ingest-feedback filtered_2026-03-30.json
```
The ingester auto-detects file type by extension (`.xlsx` → read with openpyxl, `.json` → parse directly).
```
- Title pattern moved to **ambiguous list** (goes to Claude next run instead of hard discard)
- Specific job added to feedback.json as a positive few-shot example
- Does NOT whitelist the title — Claude still evaluates each "Controls Engineer" individually on its description

---

## Output

### `eluta_YYYY-MM-DD.xlsx`
| field | description |
|---|---|
| `job_id` | Eluta unique hash ID |
| `title` | Job title as listed |
| `company` | Company name |
| `date_posted` | Date as shown on Eluta |
| `category` | backend / frontend / fullstack / ai_ml / firmware / cloud_devops / mobile / data / analyst / general_swe |
| `yoe_required` | 0-1 / 2-3 / 4-5 / 5+ / unknown |
| `url` | `https://www.eluta.ca/spl/<slug>` (clickable hyperlink) |
| `confidence` | Claude confidence score (blank for keyword-matched jobs) |

**Formatting:**
- Auto-filters on all columns (filter by category, YOE, date instantly)
- Frozen header row
- Rows color-coded by category (e.g. backend=blue, ai_ml=purple, firmware=orange, etc.)
- URL column rendered as clickable hyperlink
- Dependency: `openpyxl`

### `review_YYYY-MM-DD.xlsx`
Same schema as above, plus empty `confirm` (yes/no) and `reason` columns pre-added for user to fill in.

### `filtered_YYYY-MM-DD.json`
```json
[
  {
    "job_id": "abc123",
    "title": "Controls Engineer",
    "company": "Acme Corp",
    "date_posted": "2026-03-30",
    "snippet": "Preview text from search results page (hard-filtered jobs are never fetched for full JD)",
    "filter_reason": "non-technical blocklist match: 'engineer'",
    "url": "https://www.eluta.ca/spl/..."
  }
]
```

---

## Terminal Summary
```
Scraped 847 jobs across 43 pages
  Accepted:        312
  Hard filtered:   487  → check output/filtered_2026-03-30.json
  Flagged review:   28  → check output/review_2026-03-30.csv
  Duplicate skip:   20

Saved → output/eluta_2026-03-30.xlsx
```

---

## Configuration (`config.yaml`)

```yaml
sites:
  eluta:
    enabled: true
    query: "software engineer"
    max_pages: 100

categories:
  backend:
    - backend developer
    - server-side engineer
    - api engineer
    - software engineer backend
  frontend:
    - frontend developer
    - ui engineer
    - web developer
    - react developer
    - angular developer
  fullstack:
    - full stack developer
    - fullstack developer
    - full-stack engineer
  ai_ml:
    - ai engineer
    - ml engineer
    - machine learning engineer
    - nlp engineer
    - computer vision engineer
    - data scientist
  firmware:
    - firmware engineer
    - embedded software engineer
    - embedded systems engineer
    - rtos engineer
  cloud_devops:
    - cloud engineer
    - devops engineer
    - site reliability engineer
    - sre
    - infrastructure engineer
    - platform engineer
  mobile:
    - ios developer
    - android developer
    - mobile developer
    - react native developer
  data:
    - data engineer
    - analytics engineer
    - etl developer
  analyst:
    - business analyst
    - systems analyst
    - technical analyst
  general_swe: []  # catch-all for ambiguous technical roles

filters:
  seniority_blocklist:
    - " lead"
    - " staff"
    - "team lead"
    - "principal engineer"
    - "engineering manager"
  non_technical_blocklist:
    - millwright
    - electrician
    - civil engineer
    - plumber
    - hvac
    - welder
    - machinist
    - pipefitter
    - ironworker
    - carpenter
    - sheet metal

classifier:
  confidence_threshold: 0.60
  claude_model: claude-haiku-4-5-20251001
  max_few_shot_examples: 15

scraper:
  delay_min: 2
  delay_max: 5
  respect_robots_txt: true
```

---

## Key Design Decisions

1. **Single-file script** — all logic in `scraper.py`. Simpler to run and share. Config externalised to `config.yaml`.
2. **Full JD fetched for all non-hard-filtered jobs** — needed for YOE extraction and Claude keyword reading. Hard-filtered jobs never fetched (saves requests).
3. **Dispute → ambiguous list, not whitelist** — a disputed title moves to Claude evaluation, not blanket inclusion. Claude still judges each instance on its description.
4. **Haiku for classification** — structured JSON output task, no complex reasoning needed. ~10x cheaper than Sonnet at scale.
5. **No deduplication across runs** — deduplication is within a single run only (by job ID). Re-runs may surface the same job if it's still posted.
6. **`requests` only, no Playwright** — confirmed via inspection that Eluta serves full JDs as server-rendered HTML at `/spl/<slug>`.
