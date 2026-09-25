# 🔎 Job Scraper Agent

An automated agent that scans the career sites of **company** (Germany) for new job postings and emails you a digest of only
the **new** ones — no repeats, no manual checking.

Built as a config-driven scraping framework (not four one-off scripts), with
deduplication, a scheduler, and CI so it can run unattended every day.

---

## How it works

```
config/sites.yaml          --> which sites to scrape + CSS selectors
        |
        v
scraper/site_scraper.py    --> Playwright loads each page (headless Chromium,
                                handles JS-rendered job lists), extracts
                                title / link / location per job
        |
        v
scraper/models.py          --> each job gets a stable hash ID (company + URL)
        |
        v
scraper/storage.py         --> SQLite table of every job ever seen;
                                new run is diffed against it
        |
        v
scraper/mailer.py          --> builds an HTML digest of just the new jobs
                                and sends it over SMTP
        |
        v
scraper/run.py             --> orchestrates the above, CLI entrypoint
```

**Why this design, not four hard-coded scrapers?**
Infineon, BASF, Statista and ZEISS each run on a different Applicant
Tracking System (Eightfold, SAP SuccessFactors, custom platforms, etc.), and
these systems change their HTML/class names on every redeploy. Hard-coded
scrapers break silently. Here, each company is just a URL + a handful of
CSS selectors in `config/sites.yaml`, so a broken selector is a 2-minute
DevTools fix, not a rewrite.

**Why Playwright instead of `requests` + BeautifulSoup?**
All four of these career portals render their job lists with JavaScript
after the initial page load. `requests` only sees the empty HTML shell;
Playwright runs a real (headless) browser, so it sees what a candidate
sees. This is slower per-page but far more reliable.

---

## ⚠️ Before you run this: selectors need a quick check

Corporate career sites redesign their pages often, and I built the selectors
in `config/sites.yaml` from the current public structure of each site as of
the time this was written — I could **not** verify every selector against a
live headless browser render (no network access to those specific domains
during development). **Budget 10–15 minutes** the first time you run this to
verify/fix selectors per site. It's a normal, expected step for any scraper
project, not a sign something is broken — see the walkthrough below.

### How to fix a selector (same process for all 4 sites)

1. Run one site in dry-run mode so you can see what it currently finds:
   ```bash
   python -m scraper.run --site infineon --dry-run
   ```
2. If it prints 0 jobs or garbage titles, open the `search_url` from
   `config/sites.yaml` for that company in your normal browser.
3. Right-click a job title in the results list → **Inspect**.
4. Find the repeating element that wraps each job (usually an `<a>` or
   `<div>` with a class like `job-card`, `position-title`, etc.).
5. Update that company's `job_card`, `title`, `link_attr`, and `location`
   values in `config/sites.yaml` to match.
6. Re-run the dry-run command until it prints real job titles.

This is genuinely how job-scraping tools are maintained in production —
selectors are config, not code, specifically so this fix doesn't require
touching Python.

---

## Setup (in Cursor / any IDE)

### 1. Clone and install

```bash
git clone <your-repo-url>
cd job-scraper-agent
python -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate
pip install -r requirements.txt
python -m playwright install chromium
```

### 2. Configure email

```bash
cp .env.example .env
```

Edit `.env`:
- If using Gmail: turn on 2-Factor Authentication, then create an
  [App Password](https://myaccount.google.com/apppasswords) and use that
  as `SMTP_PASSWORD` (not your real Gmail password).
- Set `EMAIL_TO` to wherever you want the digest sent.

### 3. Run it

```bash
# Test one site without emailing or writing to the DB
python -m scraper.run --site infineon --dry-run

# Full run across all 4 sites, saves to DB, sends email if new jobs found
python -m scraper.run

# Scrape + save but skip the email (e.g. for testing storage)
python -m scraper.run --no-email
```

The first real run will typically email you a large digest (everything
counts as "new"). Every run after that only includes genuinely new
postings, because seen jobs are tracked in `data/seen_jobs.db`.

### 4. Run the tests

```bash
pytest
```

---

## Automating it (so you don't have to run it manually)

### Option A — GitHub Actions (recommended, free, no server needed)

This repo includes `.github/workflows/daily-job-scan.yml`, which runs the
scraper every day at 07:00 UTC using GitHub's own infrastructure.

1. Push this repo to GitHub.
2. Go to **Settings → Secrets and variables → Actions → Secrets** and add:
   `SMTP_HOST`, `SMTP_PORT`, `SMTP_USERNAME`, `SMTP_PASSWORD`, `EMAIL_FROM`,
   `EMAIL_TO`.
3. (Optional) Under **Variables**, add `SITES`, `KEYWORD_FILTER`,
   `SEND_EMPTY_DIGEST` to override defaults without touching code.
4. Go to the **Actions** tab → **Daily Job Scan** → **Run workflow** to test
   it manually, or just wait for the schedule.

The workflow caches `data/seen_jobs.db` between runs so deduplication
persists day to day.

### Option B — cron on your own machine / server

```cron
0 7 * * * cd /path/to/job-scraper-agent && venv/bin/python -m scraper.run >> data/cron.log 2>&1
```

### Option C — `schedule` library, long-running process

If you'd rather keep a Python process running instead of using cron/Actions,
add `schedule` to `requirements.txt` and wrap `scraper.run.main()` in a loop
— happy to add this variant if you'd prefer it over the two options above.

---

## Project structure

```
job-scraper-agent/
├── config/
│   └── sites.yaml              # per-company URLs + CSS selectors
├── scraper/
│   ├── models.py                # JobPosting dataclass + stable ID/hash logic
│   ├── site_scraper.py          # Playwright-based generic scraper
│   ├── storage.py               # SQLite dedup store
│   ├── mailer.py                # HTML digest + SMTP sending
│   └── run.py                   # CLI entrypoint / orchestration
├── tests/
│   └── test_models_and_storage.py
├── .github/workflows/
│   └── daily-job-scan.yml       # scheduled automation via GitHub Actions
├── data/                        # seen_jobs.db + run.log (gitignored)
├── .env.example
├── requirements.txt
└── README.md
```

## Configuration reference (`.env`)

| Variable | Purpose |
|---|---|
| `SMTP_HOST` / `SMTP_PORT` | Your email provider's SMTP server |
| `SMTP_USERNAME` / `SMTP_PASSWORD` | Login for sending mail |
| `EMAIL_FROM` / `EMAIL_TO` | Sender / recipient addresses |
| `SITES` | Comma-separated site keys to scrape (default: all 4) |
| `KEYWORD_FILTER` | Only email jobs whose title/location contains one of these (comma-separated). Leave blank for all new jobs |
| `SEND_EMPTY_DIGEST` | `true` to get a "no new jobs" email each run (useful as a heartbeat check) |

## Possible extensions

- Add more companies: copy a block in `config/sites.yaml`, no Python changes needed.
- Swap SMTP for a transactional email API (SendGrid, Resend, Postmark).
- Add a Slack/Telegram notifier alongside or instead of email in `scraper/mailer.py`.
- Add a `--summarize` flag that sends each job description through an LLM
  to produce a one-line "why this might fit you" — natural next step if you
  want to lean further into the "AI agent" framing for your portfolio.

## Disclaimer

This tool automates visiting public career pages, similar to what a browser
does when you check them manually. Scraping frequency is kept low (one page
load per company per run, once a day by default) and a descriptive User-Agent
is set. Review each site's Terms of Service before running this regularly,
and adjust `request_delay_seconds` in `config/sites.yaml` if you scrape more
often.
