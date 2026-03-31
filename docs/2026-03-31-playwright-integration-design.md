# Playwright Integration Design

## Problem

Eluta.ca redirects all requests (both search pages and job detail pages) to a `/sandbox` URL
when it detects bot-like behaviour. Plain `requests` cannot pass this challenge because it
requires JavaScript execution. A shared `requests.Session()` was tried but also failed.

## Solution

Replace `requests` with Playwright's headless Chrome browser, which executes JavaScript exactly
like a real browser and automatically passes the sandbox challenge.

## Architecture

### What changes

| Location | Before | After |
|---|---|---|
| `run_scrape()` | `session = requests.Session()` | `browser`, `context`, `page` created via Playwright |
| `fetch_results_page()` | `session.get(url)` → `resp.text` | `page.goto(url)` → `page.content()` |
| `fetch_full_jd()` | `session.get(url)` → `resp.text` | `page.goto(url)` → `page.content()` |
| imports | `import requests` | `from playwright.sync_api import sync_playwright` |

### What stays the same

- BeautifulSoup HTML parsing (receives `page.content()` instead of `resp.text` — identical)
- `_polite_delay()` — still called before each navigation
- `_check_robots()` — uses `urllib.robotparser` directly, no `requests` dependency
- All classification, filtering, Excel output, and cron logic

### Shared page object

A single Playwright `Page` is created in `run_scrape()` and passed into both fetch functions.
Navigating one page sequentially maintains cookies and session state across all requests
(search pages and job detail pages), which is what passes the bot challenge.

### Function signatures

```python
def fetch_results_page(page_num: int, query: str, config: dict, pw_page: Page) -> list[dict]:
def fetch_full_jd(slug: str, config: dict, pw_page: Page) -> str:
```

The `session` parameter is removed entirely. `pw_page` is required (not optional) since there
is no fallback path — Playwright is the only HTTP layer.

### Error handling

`requests.RequestException` is replaced with Playwright's `Error` (covers navigation failures,
timeouts, etc.) from `playwright.sync_api`.

### Browser lifecycle

```
run_scrape() starts
  └── sync_playwright().__enter__()
        └── playwright.chromium.launch(headless=True)
              └── browser.new_context()
                    └── context.new_page()  ← shared pw_page
                          ├── fetch_results_page() calls
                          └── fetch_full_jd() calls
  └── browser closes on run_scrape() exit (via context manager)
```

### Dependency

Add to `docs/requirements.txt`:
```
playwright>=1.40.0
```

After install, browsers must be downloaded once:
```bash
playwright install chromium
```

## Testing

Existing tests mock `fetch_results_page` and `fetch_full_jd` at the call site — they do not
call into the functions directly with real HTTP. Those tests are unaffected.

Any tests that call the fetch functions directly will need to be updated to pass a mock
`pw_page` object instead of a `session`.
