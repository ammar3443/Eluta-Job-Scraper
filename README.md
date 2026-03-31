# Eluta Job Scraper

Scrapes eluta.ca for software engineering jobs, filters out irrelevant results, and exports a clean color-coded spreadsheet. Gets smarter over time as you give it feedback.

---

## Setup

### 1. Install dependencies

```bash
cd ~/Projects/JobScraper
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### 2. Set your Anthropic API key

The scraper uses Claude Haiku to classify borderline job titles. You need a separate API key from [console.anthropic.com](https://console.anthropic.com) (pay-as-you-go, not your Claude Pro subscription).

Add it permanently to your shell:

```bash
echo 'export ANTHROPIC_API_KEY=sk-ant-your-key-here' >> ~/.bashrc
source ~/.bashrc
```

---

## Running the scraper

```bash
cd ~/Projects/JobScraper
source venv/bin/activate
python scraper.py
```

Results are saved to the `output/` folder. A summary prints when done:

```
Scraped 847 jobs across 43 pages
  Accepted:        312
  Hard filtered:   487  → check output/filtered_2026-03-30.json
  Flagged review:   28  → check output/review_2026-03-30.xlsx
  Duplicate skip:   20

Saved → output/eluta_2026-03-30.xlsx
```

---

## Automating the scraper

You can schedule the scraper to run automatically using a single command.

**Turn on** (runs every 6 hours by default):

```bash
python scraper.py --schedule
```

**Custom interval** (e.g. every 12 hours):

```bash
python scraper.py --schedule --interval 12
```

**Turn off:**

```bash
python scraper.py --unschedule
```

When scheduled, output is logged to `logs/scraper.log` instead of the terminal. To check on recent runs:

```bash
tail -50 logs/scraper.log
```

---

## Output files

Three files are created per run in the `output/` folder:

### `eluta_YYYY-MM-DD.xlsx` — your main results

Open this in Excel or Google Sheets. Rows are color-coded by job category, with auto-filters on every column so you can filter by category, YOE, date, etc.

| Column | Description |
|---|---|
| `job_id` | Unique ID for this posting |
| `title` | Job title as listed |
| `company` | Company name |
| `date_posted` | Date posted as shown on Eluta |
| `category` | backend / frontend / fullstack / ai_ml / firmware / cloud_devops / mobile / data / analyst / general_swe |
| `yoe_required` | 0-1 / 2-3 / 4-5 / 5+ / unknown |
| `url` | Clickable link to the full job posting |
| `confidence` | Claude's confidence score (blank for keyword-matched jobs) |

### `review_YYYY-MM-DD.xlsx` — borderline jobs for you to confirm

Jobs Claude wasn't confident about (below 60% confidence). Open this file, fill in the `confirm` and `reason` columns, then ingest it to teach Claude for next time. See [Teaching Claude](#teaching-claude-to-filter-better) below.

### `filtered_YYYY-MM-DD.json` — hard-filtered jobs

Jobs automatically removed by the blocklist (non-technical roles, seniority titles). Check this occasionally for false positives. See [Disputing a filtered job](#2-disputing-a-filtered-job-filteredjson) below.

---

## How filtering works

Jobs go through two stages:

### Stage 1 — Hard filter (instant, no AI)

Immediately removes jobs whose titles match the blocklist in `config.yaml`:

**Seniority blocklist** (too senior):
- lead, staff, team lead, principal engineer, engineering manager, director

**Non-technical blocklist** (wrong field):
- millwright, electrician, civil engineer, plumber, HVAC, welder, machinist, pipefitter, ironworker, carpenter, sheet metal

To add more titles to either blocklist, edit `config.yaml`.

### Stage 2 — Classifier (AI-assisted)

Jobs that pass the hard filter go through the Flow D classifier in order:

1. **Feedback lookup** — if you've seen this title before and gave feedback, use that decision instantly (free, no AI call)
2. **Keyword match** — if the title clearly matches a category (e.g. "React Developer" → frontend), assign it instantly (free, no AI call)
3. **Claude Haiku** — borderline titles get sent to Claude with your past decisions as examples. Claude returns: relevant (yes/no), category, confidence score, and years of experience required

Jobs with confidence below 60% go to `review_YYYY-MM-DD.xlsx` for you to confirm.

---

## Teaching Claude to filter better

The scraper learns from two sources of feedback.

---

### 1. Reviewing borderline jobs (`review_YYYY-MM-DD.xlsx`)

After a run, open `output/review_YYYY-MM-DD.xlsx` in Excel or Google Sheets.

You'll see jobs Claude wasn't sure about, with two empty columns at the end:

| confirm | reason |
|---|---|
| *(fill in: yes or no)* | *(fill in: brief explanation)* |

**Fill in every row**, then save the file. Examples:

| title | confirm | reason |
|---|---|---|
| Platform Engineer | yes | Uses AWS and Kubernetes |
| Project Coordinator | no | Not a technical role |
| Controls Software Engineer | yes | Embedded/PLC software |

Then run:

```bash
python scraper.py --ingest-feedback output/review_2026-03-30.xlsx
```

- `yes` → added to Claude's examples as a positive match
- `no` → added to Claude's examples as a negative match

Next run, Claude uses your decisions as examples and gets more accurate.

---

### 2. Disputing a filtered job (`filtered_YYYY-MM-DD.json`)

If a job was incorrectly hard-filtered (e.g. "Controls Software Engineer" got blocked because it contains "engineer"), you can dispute it.

Open `output/filtered_YYYY-MM-DD.json`. Find the job and add two fields:

```json
{
  "job_id": "d46b145bbcc78f3ebfdc6d584e74f6e7",
  "title": "Controls Software Engineer",
  "company": "Acme Corp",
  "date_posted": "2026-03-30",
  "snippet": "Python and PLC experience required.",
  "filter_reason": "non-technical blocklist match: 'engineer'",
  "url": "https://www.eluta.ca/spl/...",
  "dispute": true,
  "reason": "Software controls role — Python and PLC experience required"
}
```

The two fields to add are `"dispute": true` and `"reason": "your explanation"`. Leave everything else as-is.

Then run:

```bash
python scraper.py --ingest-feedback output/filtered_2026-03-30.json
```

This does **not** whitelist the title. Instead:
- The title is added to the **ambiguous list** — next run it bypasses the hard filter and goes to Claude instead
- Claude evaluates each "Controls Software Engineer" individually based on its description
- The specific job is added as a positive example for Claude

---

## feedback.json format

`feedback.json` is auto-created on first run and updated by `--ingest-feedback`. You shouldn't need to edit it manually, but here's the format for reference:

```json
{
  "decisions": [
    {
      "title": "Platform Engineer",
      "relevant": true,
      "category": "cloud_devops",
      "reason": "Uses AWS and Kubernetes",
      "source": "review"
    },
    {
      "title": "Project Coordinator",
      "relevant": false,
      "category": null,
      "reason": "Not a technical role",
      "source": "review"
    },
    {
      "title": "Controls Engineer",
      "relevant": true,
      "category": "general_swe",
      "reason": "Software controls role — Python and PLC",
      "source": "dispute"
    }
  ],
  "ambiguous_titles": [
    "controls engineer"
  ]
}
```

- `decisions` — past accept/reject verdicts used as few-shot examples for Claude
- `ambiguous_titles` — titles disputed from `filtered.json` that bypass the hard filter and go straight to Claude
- `source: "review"` — came from a review xlsx, `source: "dispute"` — came from a filtered json dispute

---

## Configuration (`config.yaml`)

| Setting | Default | What it does |
|---|---|---|
| `sites.eluta.query` | `"software engineer"` | Search term used on Eluta |
| `sites.eluta.max_pages` | `100` | Hard cap on pages scraped per run (10 jobs/page = 1000 jobs max) |
| `scraper.cutoff_days` | `3` | Stop scraping when jobs are older than this many days. Set to `0` to disable and scrape all pages up to `max_pages` |
| `scraper.delay_min` / `delay_max` | `2` / `5` | Random delay in seconds between requests — be respectful to the server |
| `filters.seniority_blocklist` | see config | Job title fragments that get hard-filtered (e.g. "lead", "director") |
| `filters.non_technical_blocklist` | see config | Non-software job terms that get hard-filtered (e.g. "electrician", "welder") |
| `classifier.confidence_threshold` | `0.60` | Claude confidence below this → job goes to review file instead of accepted |
| `classifier.claude_model` | `claude-haiku-4-5-20251001` | Claude model used for classification — Haiku is cheapest |

---

## File structure

```
JobScraper/
├── scraper.py          # all logic
├── config.yaml         # settings (edit this)
├── feedback.json       # learned decisions (auto-updated by --ingest-feedback)
├── requirements.txt    # dependencies
├── output/
│   ├── eluta_YYYY-MM-DD.xlsx      # accepted jobs
│   ├── review_YYYY-MM-DD.xlsx     # borderline jobs — fill in confirm/reason
│   └── filtered_YYYY-MM-DD.json   # hard-filtered jobs — add dispute:true to contest
```
