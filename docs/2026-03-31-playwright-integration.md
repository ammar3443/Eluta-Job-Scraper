# Playwright Integration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace `requests` with Playwright headless Chrome so the scraper can pass Eluta's JavaScript-based bot detection on all pages.

**Architecture:** A single Playwright `Page` object is created in `run_scrape()` and shared across all HTTP calls. `fetch_results_page()` and `fetch_full_jd()` accept this page object, navigate to the target URL with `page.goto()`, and return `page.content()` to the existing BeautifulSoup parsing layer — which is unchanged.

**Tech Stack:** `playwright` (sync API), `playwright.sync_api.sync_playwright`, `playwright.sync_api.Error`

---

## File Map

| File | Change |
|---|---|
| `scraper.py` | Replace requests HTTP layer with Playwright; update imports, fetch functions, run_scrape |
| `docs/requirements.txt` | Add `playwright>=1.40.0` |
| `tests/test_scraper.py` | Update fetch function tests to mock pw_page; add sync_playwright mock to run_scrape tests |

---

### Task 1: Install Playwright

**Files:**
- Modify: `docs/requirements.txt`

- [ ] **Step 1: Add playwright to requirements.txt**

Open `docs/requirements.txt` and add:
```
playwright>=1.40.0
```

- [ ] **Step 2: Install the package**

```bash
source /home/ammar/Projects/JobScraper/venv/bin/activate && pip install playwright>=1.40.0
```

- [ ] **Step 3: Install Chromium browser**

```bash
source /home/ammar/Projects/JobScraper/venv/bin/activate && playwright install chromium
```

Expected output: `Downloading Chromium...` followed by a success message.

- [ ] **Step 4: Verify import works**

```bash
source /home/ammar/Projects/JobScraper/venv/bin/activate && python3 -c "from playwright.sync_api import sync_playwright, Error as PlaywrightError; print('OK')"
```

Expected: `OK`

- [ ] **Step 5: Commit**

```bash
cd /home/ammar/Projects/JobScraper && git add docs/requirements.txt && git commit -m "chore: add playwright dependency"
```

---

### Task 2: Update fetch_results_page

**Files:**
- Modify: `scraper.py`
- Modify: `tests/test_scraper.py`

The function currently takes `session: requests.Session | None = None` and calls `requester.get(url)`. It will instead take a required `pw_page` (a Playwright `Page`) and call `pw_page.goto(url)` then `pw_page.content()`.

The debug print currently uses `resp.url` — this becomes `pw_page.url`.
The `resp.raise_for_status()` call becomes a status check on the response returned by `goto()`.
URL construction moves from `requests` params dict to `urllib.parse.urlencode`.

- [ ] **Step 1: Write the failing tests**

Replace the three `fetch_results_page` tests in `tests/test_scraper.py` (lines ~403–467) with:

```python
def test_fetch_results_page_returns_jobs():
    from scraper import fetch_results_page
    from unittest.mock import MagicMock
    config = {"scraper": {"delay_min": 0, "delay_max": 0, "respect_robots_txt": False}}
    pw_page = MagicMock()
    pw_page.goto.return_value = MagicMock(status=200)
    pw_page.content.return_value = SAMPLE_RESULTS_HTML
    pw_page.url = "https://www.eluta.ca/search?q=software+engineer"
    jobs = fetch_results_page(1, "software engineer", config, pw_page)
    assert len(jobs) == 2
    assert jobs[0]["title"] == "Backend Developer"
    assert jobs[0]["company"] == "Acme Corp"
    assert jobs[0]["job_id"] == "d46b145bbcc78f3ebfdc6d584e74f6e7"
    assert jobs[0]["slug"] == "spl/backend-developer-d46b145bbcc78f3ebfdc6d584e74f6e7?imo=1"
    assert jobs[0]["url"] == "https://www.eluta.ca/spl/backend-developer-d46b145bbcc78f3ebfdc6d584e74f6e7"


def test_fetch_results_page_empty_returns_empty_list():
    from scraper import fetch_results_page
    from unittest.mock import MagicMock
    config = {"scraper": {"delay_min": 0, "delay_max": 0, "respect_robots_txt": False}}
    pw_page = MagicMock()
    pw_page.goto.return_value = MagicMock(status=200)
    pw_page.content.return_value = "<html><body></body></html>"
    pw_page.url = "https://www.eluta.ca/search?q=software+engineer"
    jobs = fetch_results_page(1, "software engineer", config, pw_page)
    assert jobs == []


def test_fetch_results_page_raises_on_http_error():
    from scraper import fetch_results_page
    from unittest.mock import MagicMock
    from playwright.sync_api import Error as PlaywrightError
    config = {"scraper": {"delay_min": 0, "delay_max": 0, "respect_robots_txt": False}}
    pw_page = MagicMock()
    pw_page.goto.side_effect = PlaywrightError("net::ERR_CONNECTION_REFUSED")
    with pytest.raises(PlaywrightError):
        fetch_results_page(1, "software engineer", config, pw_page)
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
source /home/ammar/Projects/JobScraper/venv/bin/activate && cd /home/ammar/Projects/JobScraper && pytest tests/test_scraper.py::test_fetch_results_page_returns_jobs tests/test_scraper.py::test_fetch_results_page_empty_returns_empty_list tests/test_scraper.py::test_fetch_results_page_raises_on_http_error -v
```

Expected: FAIL (function still uses requests)

- [ ] **Step 3: Update fetch_results_page in scraper.py**

Add `from urllib.parse import urlencode` to the imports at the top of `scraper.py`.

Then replace the `fetch_results_page` function (currently lines ~372–413) with:

```python
def fetch_results_page(page_num: int, query: str, config: dict, pw_page) -> list[dict]:
    """
    Fetch one search results page from Eluta.
    Returns list of job dicts: {title, company, snippet, date_posted, job_id, slug, url}
    """
    # Eluta uses "pg" for pagination; page 1 has no pg parameter, pages 2+ use pg=N
    params = {"q": query}
    if page_num > 1:
        params["pg"] = page_num
    url = f"{ELUTA_SEARCH}?{urlencode(params)}"
    _polite_delay(config)
    pw_page.goto(url, wait_until="domcontentloaded", timeout=30000)
    html = pw_page.content()
    soup = BeautifulSoup(html, "html.parser")

    jobs = []
    for card in soup.find_all(class_="organic-job"):
        title_tag = card.find("a", class_="lk-job-title")
        company_tag = card.find("a", class_="lk-employer")
        desc_tag = card.find("span", class_="description")
        date_tag = card.find("a", class_="lastseen")
        slug = card.get("data-url", "")

        if not title_tag or not slug:
            continue

        job_id = _extract_job_id(slug)
        jobs.append({
            "title": title_tag.get_text(strip=True),
            "company": company_tag.get_text(strip=True) if company_tag else "",
            "snippet": desc_tag.get_text(strip=True) if desc_tag else "",
            "date_posted": date_tag.get_text(strip=True) if date_tag else "",
            "job_id": job_id,
            "slug": slug,
            "url": f"{ELUTA_BASE}/{slug.split('?')[0]}",
        })

    if not jobs:
        print(f"  [debug] Page {page_num} returned no jobs. URL: {pw_page.url}")
        print(f"  [debug] Response snippet: {html[:500]}")

    return jobs
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
source /home/ammar/Projects/JobScraper/venv/bin/activate && cd /home/ammar/Projects/JobScraper && pytest tests/test_scraper.py::test_fetch_results_page_returns_jobs tests/test_scraper.py::test_fetch_results_page_empty_returns_empty_list tests/test_scraper.py::test_fetch_results_page_raises_on_http_error -v
```

Expected: all 3 PASS

- [ ] **Step 5: Commit**

```bash
cd /home/ammar/Projects/JobScraper && git add scraper.py tests/test_scraper.py docs/requirements.txt && git commit -m "feat: migrate fetch_results_page to Playwright"
```

---

### Task 3: Update fetch_full_jd

**Files:**
- Modify: `scraper.py`
- Modify: `tests/test_scraper.py`

Same pattern as Task 2: replace `requester.get()` with `pw_page.goto()` + `pw_page.content()`.

- [ ] **Step 1: Write the failing tests**

Replace the two `fetch_full_jd` tests in `tests/test_scraper.py` (lines ~432–455) with:

```python
def test_fetch_full_jd_returns_text():
    from scraper import fetch_full_jd
    from unittest.mock import MagicMock
    config = {"scraper": {"delay_min": 0, "delay_max": 0}}
    pw_page = MagicMock()
    pw_page.goto.return_value = MagicMock(status=200)
    pw_page.content.return_value = SAMPLE_SPL_HTML
    text = fetch_full_jd("spl/backend-developer-abc123def456?imo=1", config, pw_page)
    assert "Python" in text
    assert "Django" in text
    assert "3-5 years" in text


def test_fetch_full_jd_returns_empty_on_parse_failure():
    from scraper import fetch_full_jd
    from unittest.mock import MagicMock
    config = {"scraper": {"delay_min": 0, "delay_max": 0}}
    pw_page = MagicMock()
    pw_page.goto.return_value = MagicMock(status=200)
    pw_page.content.return_value = "<html><body><p>No description here.</p></body></html>"
    text = fetch_full_jd("spl/some-job?imo=1", config, pw_page)
    assert text == ""
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
source /home/ammar/Projects/JobScraper/venv/bin/activate && cd /home/ammar/Projects/JobScraper && pytest tests/test_scraper.py::test_fetch_full_jd_returns_text tests/test_scraper.py::test_fetch_full_jd_returns_empty_on_parse_failure -v
```

Expected: FAIL

- [ ] **Step 3: Update fetch_full_jd in scraper.py**

Replace the `fetch_full_jd` function (currently lines ~416–435) with:

```python
def fetch_full_jd(slug: str, config: dict, pw_page) -> str:
    """
    Fetch the full job description from the /spl/ page.
    Returns plain text of the description, or empty string on failure.
    """
    url = f"{ELUTA_BASE}/{slug}" if not slug.startswith("http") else slug
    _polite_delay(config)
    pw_page.goto(url, wait_until="domcontentloaded", timeout=30000)
    html = pw_page.content()
    soup = BeautifulSoup(html, "html.parser")

    desc = soup.find(class_="short-text")
    if not desc:
        desc = soup.find("div", class_="description")
    if not desc:
        return ""
    return desc.get_text(separator=" ", strip=True)
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
source /home/ammar/Projects/JobScraper/venv/bin/activate && cd /home/ammar/Projects/JobScraper && pytest tests/test_scraper.py::test_fetch_full_jd_returns_text tests/test_scraper.py::test_fetch_full_jd_returns_empty_on_parse_failure -v
```

Expected: both PASS

- [ ] **Step 5: Commit**

```bash
cd /home/ammar/Projects/JobScraper && git add scraper.py tests/test_scraper.py && git commit -m "feat: migrate fetch_full_jd to Playwright"
```

---

### Task 4: Update run_scrape — browser lifecycle and error handling

**Files:**
- Modify: `scraper.py`
- Modify: `tests/test_scraper.py`

`run_scrape()` must create the Playwright browser, context, and page; pass the page into both fetch functions; and close the browser when done. Error handling changes from `requests.RequestException` to `playwright.sync_api.Error`.

The `run_scrape` tests already mock `fetch_results_page` and `fetch_full_jd` at the function level, so those tests won't exercise the real Playwright code. They do need `sync_playwright` mocked to prevent actual Chrome launch.

- [ ] **Step 1: Add sync_playwright mock to all run_scrape tests**

In `tests/test_scraper.py`, find every `with patch("scraper.fetch_results_page")` block that also patches `scraper.fetch_full_jd` and add `patch("scraper.sync_playwright")` to the context manager. There are approximately 10 such blocks.

For each block, change from:
```python
with patch("scraper.fetch_results_page") as mock_page, \
     patch("scraper.fetch_full_jd") as mock_jd, \
     patch("scraper._check_robots"):
```

To:
```python
with patch("scraper.fetch_results_page") as mock_page, \
     patch("scraper.fetch_full_jd") as mock_jd, \
     patch("scraper._check_robots"), \
     patch("scraper.sync_playwright"):
```

- [ ] **Step 2: Run the run_scrape tests to verify they still pass (before changing run_scrape)**

```bash
source /home/ammar/Projects/JobScraper/venv/bin/activate && cd /home/ammar/Projects/JobScraper && pytest tests/test_scraper.py -k "pipeline" -v
```

Expected: all pass (sync_playwright mock has no effect yet since run_scrape doesn't use it yet)

- [ ] **Step 3: Update run_scrape in scraper.py**

Add this import at the top of `scraper.py`:
```python
from playwright.sync_api import sync_playwright, Error as PlaywrightError
```

Then in `run_scrape()`, replace:
```python
    network_error: str | None = None
    session = requests.Session()

    for page in range(1, max_pages + 1):
        try:
            page_jobs = fetch_results_page(page, query, config, session)
        except requests.RequestException as exc:
            network_error = str(exc)
            print(f"\n  Network error on page {page}: {exc}")
            print("  Saving results collected so far.")
            break
```

With:
```python
    network_error: str | None = None

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(user_agent=HEADERS["User-Agent"])
        pw_page = context.new_page()

        for page in range(1, max_pages + 1):
            try:
                page_jobs = fetch_results_page(page, query, config, pw_page)
            except PlaywrightError as exc:
                network_error = str(exc)
                print(f"\n  Network error on page {page}: {exc}")
                print("  Saving results collected so far.")
                break
```

Also replace the JD fetch error handler inside the job loop:
```python
            try:
                jd_text = fetch_full_jd(job["slug"], config)
            except requests.RequestException as exc:
                print(f"\n  Network error fetching JD for '{job['title']}': {exc} — skipping job.")
                continue
```

With:
```python
            try:
                jd_text = fetch_full_jd(job["slug"], config, pw_page)
            except PlaywrightError as exc:
                print(f"\n  Network error fetching JD for '{job['title']}': {exc} — skipping job.")
                continue
```

The `print()` and `return` at the end of `run_scrape` stay outside the `with` block — the browser closes automatically when the `with` exits, and the collected data in `accepted`, `review`, etc. is still available.

The full updated body of `run_scrape` after the variable setup should look like:
```python
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(user_agent=HEADERS["User-Agent"])
        pw_page = context.new_page()

        for page in range(1, max_pages + 1):
            try:
                page_jobs = fetch_results_page(page, query, config, pw_page)
            except PlaywrightError as exc:
                network_error = str(exc)
                print(f"\n  Network error on page {page}: {exc}")
                print("  Saving results collected so far.")
                break

            if not page_jobs:
                print(f"\n  No more results at page {page}, stopping.")
                break

            # Date cutoff
            if cutoff_days:
                page_jobs = [j for j in page_jobs
                             if _parse_days_ago(j.get("date_posted", "")) <= cutoff_days]
                if not page_jobs:
                    print(f"\n  Reached {cutoff_days}-day cutoff at page {page}, stopping.")
                    break

            pages_scraped += 1
            print(f"\r  Page {pages_scraped}...", end="", flush=True)

            for job in page_jobs:
                jid = job["job_id"]
                if jid in seen_ids:
                    duplicate_count += 1
                    continue
                seen_ids.add(jid)

                action, reason = hard_filter(job["title"], config, ambiguous_titles)

                if action == "filter":
                    filtered.append({**job, "filter_reason": reason})
                    continue

                try:
                    jd_text = fetch_full_jd(job["slug"], config, pw_page)
                except PlaywrightError as exc:
                    print(f"\n  Network error fetching JD for '{job['title']}': {exc} — skipping job.")
                    continue

                classified = classify_job(job, jd_text, feedback, config, is_ambiguous=(action == "ambiguous"))

                if not classified["relevant"]:
                    filtered.append({**job, "filter_reason": "Claude: not relevant"})
                    continue

                if classified.get("flagged_for_review"):
                    review.append(classified)
                else:
                    accepted.append(classified)

    print()  # newline after the inline page counter
    return accepted, review, filtered, duplicate_count, pages_scraped, network_error
```

- [ ] **Step 4: Run the full test suite**

```bash
source /home/ammar/Projects/JobScraper/venv/bin/activate && cd /home/ammar/Projects/JobScraper && pytest tests/test_scraper.py -v
```

Expected: all tests pass

- [ ] **Step 5: Commit**

```bash
cd /home/ammar/Projects/JobScraper && git add scraper.py tests/test_scraper.py && git commit -m "feat: add Playwright browser lifecycle to run_scrape, replace RequestException with PlaywrightError"
```

---

### Task 5: Remove requests import and do a live test

**Files:**
- Modify: `scraper.py`

`requests` is no longer used anywhere in scraper.py after the previous tasks. Remove the import. `urllib.robotparser` (used in `_check_robots`) is from stdlib and has no dependency on `requests`.

- [ ] **Step 1: Remove the requests import**

In `scraper.py`, remove the line:
```python
import requests
```

- [ ] **Step 2: Run the full test suite to confirm nothing broke**

```bash
source /home/ammar/Projects/JobScraper/venv/bin/activate && cd /home/ammar/Projects/JobScraper && pytest tests/test_scraper.py -v
```

Expected: all tests pass

- [ ] **Step 3: Run the scraper live**

```bash
. ~/.secrets/env && cd /home/ammar/Projects/JobScraper && /home/ammar/Projects/JobScraper/venv/bin/python scraper.py
```

Expected: scraper gets past page 2 without a sandbox redirect. Should see `Page 1... Page 2... Page 3...` etc.

- [ ] **Step 4: Commit**

```bash
cd /home/ammar/Projects/JobScraper && git add scraper.py && git commit -m "chore: remove requests import, fully replaced by Playwright"
```
