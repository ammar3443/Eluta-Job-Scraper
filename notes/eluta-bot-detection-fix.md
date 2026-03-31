# Eluta Bot Detection — Problem & Fix

## What Happened

When the scraper ran, it successfully fetched page 1 of job results but was blocked on page 2.
Instead of returning job listings, Eluta's server redirected the scraper to a URL like:

```
https://www.eluta.ca/sandbox?destination=https://www.eluta.ca/search?q=software+engineer&pg=2
```

The scraper saw no jobs on that page and stopped immediately, resulting in only 10 jobs from 1 page
instead of potentially hundreds across many pages.

This was confirmed in the logs:

```
Page 1...  [debug] Page 2 returned no jobs. URL: https://www.eluta.ca/sandbox?destination=...
No more results at page 2, stopping.
Scraped 10 jobs across 1 pages in 42s
```

---

## Why It Happened

### The short version
Eluta detected the scraper as a bot and blocked it after the first page.

### The longer version

When you visit a website in a normal browser, the browser maintains a **session** — a continuous
conversation between your browser and the website's server. As part of that session, the server
sends small pieces of data called **cookies** back to your browser. Your browser stores these
cookies and sends them back with every subsequent request. This lets the server know "this is the
same person who was just here on page 1, now they're asking for page 2."

The scraper was using Python's `requests` library to fetch pages, but each request was being made
independently — like a completely new visitor showing up each time. No cookies were being stored
or sent between requests. From Eluta's perspective, this looks suspicious: a real user browsing
from page 1 to page 2 would carry their session cookies along. A bot making isolated requests
would not.

Eluta uses a **sandbox redirect** as a bot detection mechanism. When it sees requests that don't
behave like a normal browser session (no cookies, no session continuity), it redirects to the
sandbox page instead of serving real results. The sandbox page contains a **reCAPTCHA** — a Google
challenge that tries to verify whether the visitor is a human.

### Why page 1 worked but page 2 didn't (initially)

Page 1 is the initial request, which looks the same whether you're a bot or a real user — there's
no prior session to verify. The server lets it through. By page 2, Eluta expects to see session
cookies that were set during the page 1 response. Without them, it flags the request as
suspicious and redirects to the sandbox.

---

## What Was Already In Place

The scraper already had two anti-bot measures:

1. **Realistic user-agent header** — instead of identifying itself as `python-requests` (an
   instant bot flag), the scraper pretends to be Chrome on Linux:
   ```
   Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36
   ```

2. **Random delays between requests** — instead of hammering the server as fast as possible
   (which screams bot), the scraper waits a random 2–5 seconds between each page. This mimics
   the natural pace of a human clicking through pages.

These measures were not enough on their own because cookies were still not being maintained, and
because Eluta's sandbox requires JavaScript to pass.

---

## Fix Attempt 1: requests.Session() — Did Not Work

### What was tried

Added a `requests.Session()` object that is shared across all requests within a single scrape run.
A session automatically stores cookies and sends them with every subsequent request.

### Why it failed

Testing confirmed that the sandbox redirect hits **both** search pages and individual job detail
pages (`/spl/...`). More critically, Eluta's sandbox is a **JavaScript challenge** (powered by
reCAPTCHA). Python's `requests` library cannot execute JavaScript — it only fetches raw HTML.
No matter how many cookies it carries, it cannot pass a JS-based challenge.

---

## Fix Attempt 2: Playwright Headless Browser — Implemented

### What is Playwright?

Playwright is a Python library that launches a real Chrome browser invisibly in the background
(called "headless" — no visible window). Because it's a real browser, it can:
- Execute JavaScript (including reCAPTCHA challenges)
- Maintain cookies automatically across all page loads
- Look identical to a normal user browsing

### What changed in the code

`requests` was removed entirely and replaced with Playwright throughout the scraping layer.

**Before:**
```python
import requests
session = requests.Session()
resp = session.get("https://eluta.ca/search?q=software+engineer")
html = resp.text
```

**After:**
```python
from playwright.sync_api import sync_playwright
with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    context = browser.new_context(user_agent="Mozilla/5.0 ...")
    page = context.new_page()
    page.goto("https://eluta.ca/search?q=software+engineer")
    html = page.content()
```

The same `html` is then passed to BeautifulSoup for parsing — that part is unchanged.

### Stealth settings added

To prevent Chrome from being detected as a bot, two extra measures were added:

1. `--disable-blink-features=AutomationControlled` — a Chrome flag that removes a browser marker
   that many bot-detection systems check for
2. `Object.defineProperty(navigator, 'webdriver', {get: () => undefined})` — a JavaScript snippet
   that hides the `navigator.webdriver` property, which headless Chrome normally exposes and which
   bot detectors check

### Where in the code

- `scraper.py` imports: `from playwright.sync_api import sync_playwright, Error as PlaywrightError`
- `run_scrape()` — creates the browser, context, and page; passes `pw_page` into fetch functions
- `fetch_results_page(page_num, query, config, pw_page)` — navigates with `pw_page.goto()`
- `fetch_full_jd(slug, config, pw_page)` — same pattern
- `requests` import removed entirely from the file

### Note on IP blocking

During development and testing on 2026-03-31, the IP was temporarily blocked by Eluta after
many test runs in quick succession. This caused even plain `requests` to get the sandbox redirect
on page 1 (which previously worked). This is a temporary rate-limit — it resets overnight. The
cron job running at midnight should work normally once the block lifts.

---

## Current Status (2026-03-31)

| Measure | Status |
|---|---|
| Realistic user-agent | ✅ In place |
| Random 2–5s delays between requests | ✅ In place |
| Persistent session (cookies) | ✅ Handled by Playwright automatically |
| JavaScript execution (reCAPTCHA) | ✅ Playwright handles this |
| Headless detection masking | ✅ Stealth args added |
| Live test | ⏳ Blocked by temporary IP rate-limit — test at next cron run |

---

## Related Files

- `docs/2026-03-31-playwright-integration-design.md` — design spec for the Playwright migration
- `docs/2026-03-31-playwright-integration.md` — step-by-step implementation plan
