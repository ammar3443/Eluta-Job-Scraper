# Next Steps If Playwright Still Gets Blocked

## Context

As of 2026-03-31, Eluta's reCAPTCHA is blocking the scraper even with Playwright headless Chrome
and stealth settings. This is likely a temporary IP-level block caused by many test runs in one
day. The cron job has been disabled temporarily.

**First: re-enable the cron job and wait.** If normal 6-hour intervals don't trigger the block,
no further action is needed. If blocking continues, try the options below in order.

---

## Option 1: Manual CAPTCHA solve + session persistence (IMPLEMENTED)

A three-part approach:

### 1. Increased delays (2-5s → 10-20s)

Bumped request delays in `config.yaml` to be more human-like. Reduces the chance of triggering
the rate-limit block in future runs.

### 2. Session persistence

Browser now saves its session state (cookies, localStorage) to `.eluta_session.json` after each run:
- First run with `--no-headless`: solve CAPTCHA manually, session is saved
- Subsequent runs: load saved session → CAPTCHA verification carries over (no re-prompt until it expires)

Saves ~2 minutes per run when session is valid.

### 3. Manual CAPTCHA solve on demand

Run with:

```bash
python scraper.py --no-headless
```

This:
1. Launches browser visibly
2. Shows the reCAPTCHA checkbox
3. You click "I'm not a robot"
4. Browser passes challenge, scraping continues automatically
5. Session saved for future runs

### How it works

Once you solve the CAPTCHA:
- Session state (authentication cookies) persists across runs
- Normal cron jobs (headless mode) reuse the saved session
- CAPTCHA won't appear again until the session expires (typically days to weeks)
- Slower request rate reduces likelihood of re-blocking

### Trade-off

- One-time manual action when the IP gets blocked
- Otherwise fully automated

---

## Option 2: CAPTCHA solving service (fully automated)

Services like **2captcha** or **CapSolver** solve reCAPTCHAs programmatically using human workers
or AI. They have Python SDKs and cost ~$1-3 per 1000 solves (essentially free for 4 runs/day).

How it works:
1. Send the service the reCAPTCHA site key + page URL
2. They return a `g-recaptcha-response` token (takes ~10-30 seconds)
3. Inject the token into the page using Playwright
4. The page accepts it and loads normally

This is fully automated and works in headless mode, but adds a paid API dependency.

---

## Option 3: Longer delays / fewer runs

If the IP block is triggered by run frequency, reducing from 4 runs/day to 2 runs/day (every 12
hours) may help. Change the crontab from `0 */6 * * *` to `0 */12 * * *`.
