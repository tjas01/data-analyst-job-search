# Data Analyst Job Search — BC

An automated job feed that fetches analyst postings from 9 sources every morning, scores each one against a specific candidate profile using **Gemini AI**, and surfaces the top 5 matches directly in this README — no email, no manual searching.

Built for: Business Analyst, Business Systems Analyst, Data Analyst, SAP/ERP Analyst, Supply Chain Analyst roles in **Metro Vancouver / BC**.

---

## Top 5 Job Matches

<!-- JOBS_START -->

*Run the workflow to populate.*

<!-- JOBS_END -->

---

## How It Works

```
GitHub Actions (8 AM PST daily)
        |
        v
fetch_jobs.py
        |
        +-- Canada Job Bank (RSS)
        +-- Remotive (JSON API)
        +-- We Work Remotely (RSS)
        +-- Jobicy (RSS)
        +-- Greenhouse (JSON API — 30 BC companies)
        +-- Lever (JSON API — 28 BC companies)
        +-- Ashby (JSON API — 24 BC companies)
        +-- WorkBC (JSON API)
        +-- BC Public Service (Workday API)
        |
        v
  Filter: last 48 hours (ATS sources pass through — they only serve open roles)
        |
        v
  Skip jobs already in data/jobs_history.json
        |
        v
  Score each new job with Gemini 1.5 Flash (0–10 + reason)
        |
        v
  Drop hard excludes (score 0), take top 5
        |
        v
  Write JOBS.md + update this README + commit back to repo
```

---

## Job Sources

| # | Source | Type | Coverage |
|---|--------|------|----------|
| 1 | Canada Job Bank | RSS | BC government-verified listings |
| 2 | Remotive | JSON API | Remote-first global, data + management |
| 3 | We Work Remotely | RSS | Remote-first, data/analytics + business |
| 4 | Jobicy | RSS | Remote, data-science, Canada region |
| 5 | Greenhouse | JSON API | 30 BC tech companies (Hootsuite, Lululemon, Clio, etc.) |
| 6 | Lever | JSON API | 28 BC tech companies (Kabam, Tipalti, CGI, etc.) |
| 7 | Ashby | JSON API | 24 BC startups (1Password, dbt Labs, Hightouch, etc.) |
| 8 | WorkBC | JSON API | BC provincial job board |
| 9 | BC Public Service | Workday API | BC government jobs |

All sources are free with no API keys required (except Gemini for scoring).

---

## Scoring Profile

Each job is scored 0–10 against this profile:

**Target roles:** Business Systems Analyst, Business Analyst, ERP/SAP Analyst, Data Analyst, Supply Chain Analyst

**Background:** MBA in Business Analytics, Power BI PL-300, 5+ years across supply chain, SaaS, IT

**Tools:** SAP S/4HANA, Power BI, SQL, Microsoft Fabric, Power Automate, Tableau, Python, Azure DP-900

**Location:** Metro Vancouver / Surrey / BC only

**Hard excludes (score 0):** Roles outside BC, roles requiring citizenship/security clearance

---

## Setup

1. Fork this repo
2. Go to **Settings → Secrets and variables → Actions → New repository secret**
3. Add `GEMINI_API_KEY` with your [Google AI Studio](https://aistudio.google.com/app/apikey) free-tier key
4. Go to **Actions → Daily Job Search → Run workflow** to test immediately

The workflow runs automatically every day at **8:00 AM PST**.

---

## Files

```
data-analyst-job-search/
├── .github/workflows/
│   └── job_search.yml         # Runs daily at 8am PST
├── scripts/
│   └── fetch_jobs.py          # All fetching, scoring, and output
├── data/
│   └── jobs_history.json      # Rolling 25-day log (auto-committed)
├── JOBS.md                    # Top 5 matches (auto-committed)
├── requirements.txt
└── README.md                  # This file — jobs section auto-updated
```

---

## History

`data/jobs_history.json` tracks every surfaced job. Jobs older than 25 days are automatically pruned on each run, preventing the same listing from being re-scored daily.

---

*Built by [Tejas Vyasam](https://linkedin.com/in/tejasvyasam)*
