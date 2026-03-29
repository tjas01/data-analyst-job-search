# Data Analyst Job Search — BC

An automated job feed that fetches analyst postings from 9 sources every morning, scores each one against a specific candidate profile using **Gemini AI**, and surfaces the top 5 matches directly in this README — no email, no manual searching.

Built for: Business Analyst, Business Systems Analyst, Data Analyst, SAP/ERP Analyst, Supply Chain Analyst roles in **Metro Vancouver / BC**.

---

## Top 10 Job Matches

<!-- JOBS_START -->

*Last updated: 2026-03-28 08:36 PM PST*

### Postings from the last 24 hours

*No new dated postings in the last 24 hours.*

### Open roles (no timestamp available)

**1. Business Systems Analyst/Admin | Ramp | Remote | FullTime**
- Posted: Unknown
- Link: https://jobs.ashbyhq.com/ramp/e675851d-b7f2-46b5-ad19-3e20d9cc0d87
- Match score: 8/10
- Why this fits: Strong keyword match (Python scorer, Gemini unavailable). Signals: title is a top-priority BSA role.

**2. Staff Data Analyst - Marketing & Revenue Analytics (GTM) | Hootsuite | Toronto, Ontario, Canada; Vancouver, British Columbia, Canada; Calgary, Alberta, Canada; Austin, Texas, United States; Atlanta, Georgia, United States; Seattle, Washington, United States | Unknown**
- Posted: Unknown
- Link: https://careers.hootsuite.com/job/?gh_jid=7471078
- Match score: 7/10
- Why this fits: Strong keyword match (Python scorer, Gemini unavailable). Signals: title matches target analyst roles.

**3. Principal Game Data Analyst | Kabam | Vancouver | Regular Full-time (RFT)**
- Posted: Unknown
- Link: https://jobs.lever.co/kabam/c20e2817-57fb-4df4-bcb4-915d43e46628
- Match score: 7/10
- Why this fits: Strong keyword match (Python scorer, Gemini unavailable). Signals: title matches target analyst roles.

**4. Analytics Engineering Advocate - Europe | Lightdash | Remote | FullTime**
- Posted: Unknown
- Link: https://jobs.ashbyhq.com/lightdash/309706bc-1081-48b6-89dc-f769bbe17e6d
- Match score: 5/10
- Why this fits: Moderate keyword match (Python scorer, Gemini unavailable). Signals: partial keyword match on title.

**5. Analytics Engineering Advocate - US (Eastern Time) | Lightdash | Remote | FullTime**
- Posted: Unknown
- Link: https://jobs.ashbyhq.com/lightdash/8cc71b90-7def-4cd7-9a0b-ba0bc83caef4
- Match score: 5/10
- Why this fits: Moderate keyword match (Python scorer, Gemini unavailable). Signals: partial keyword match on title.

<!-- JOBS_END -->

---

## How It Works

```
GitHub Actions (7 AM PST daily)
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
  Filter: last 24 hours (ATS sources pass through — they only serve open roles)
        |
        v
  Skip jobs already in data/jobs_history.json
        |
        v
  Score each new job with Gemini 1.5 Flash (0–10 + reason)
        |
        v
  BC location filter — drop non-BC roles
        |
        v
  Score with Python keywords + Gemini AI (Python used as fallback)
        |
        v
  Drop hard excludes (score 0), take top 5 dated + top 5 undated
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

The workflow runs automatically every day at **7:00 AM PST**.

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
