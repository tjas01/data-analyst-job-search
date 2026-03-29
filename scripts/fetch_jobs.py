# -*- coding: utf-8 -*-
"""
Job Feed Aggregator - Tejas Vyasam
Fetches BC analyst jobs from 9 sources, scores against profile using
Python keyword scoring + Gemini AI, and writes top 10 matches:
  - Section 1: top 5 jobs with timestamps (posted in last 24h)
  - Section 2: top 5 jobs without timestamps (ATS open roles)

Sources:
  1. Canada Job Bank (RSS)         - Government/verified CA jobs
  2. Remotive (JSON API)           - Remote tech/data jobs globally
  3. We Work Remotely (RSS)        - Remote-first jobs
  4. Jobicy (RSS)                  - Remote jobs, Canada region
  5. Greenhouse (JSON API)         - BC tech companies
  6. Lever (JSON API)              - BC tech companies
  7. Ashby (JSON API)              - BC startups/scaleups
  8. WorkBC (JSON API)             - BC provincial job board
  9. BC Public Service (Workday)   - BC government jobs

Outputs:
  - JOBS.md                  (top 10 scored matches, repo root)
  - data/jobs_history.json   (rolling 25-day log)
"""

import feedparser
import requests
import json
import hashlib
import re
import os
from datetime import datetime, timezone, timedelta
from pathlib import Path
from email.utils import parsedate_to_datetime

REPO_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = REPO_ROOT / "data"
DATA_DIR.mkdir(exist_ok=True)
HISTORY_FILE = DATA_DIR / "jobs_history.json"
JOBS_MD = REPO_ROOT / "JOBS.md"

HISTORY_MAX_DAYS = 25
RECENCY_HOURS = 24
TOP_N = 5

TITLE_KEYWORDS = [
    "data analyst",
    "business intelligence",
    "bi analyst",
    "bi developer",
    "business analyst",
    "business systems analyst",
    "systems analyst",
    "erp analyst",
    "sap analyst",
    "inventory analyst",
    "supply chain analyst",
    "analytics engineer",
    "reporting analyst",
    "operations analyst",
]

CANDIDATE_PROFILE = """
Target roles (priority order):
1. Business Systems Analyst (BSA)
2. Business Analyst (BA)
3. ERP Business Analyst / SAP Analyst
4. Data Analyst / Reporting Analyst
5. Supply Chain Analyst / Operations Analyst

Background: MBA in Business Analytics (GPA 3.71), Power BI PL-300 certified, 5+ years
experience across supply chain, SaaS, and IT.
Tools: SAP S/4HANA, Power BI, SQL, Microsoft Fabric, Power Automate, n8n, Tableau,
Python, Azure DP-900.

Location: Metro Vancouver / Surrey / BC only. On-site or hybrid preferred.
Remote-only is lower priority but include if strong match.
Contract or permanent both acceptable.

Strong match signals (score higher):
- SAP S/4HANA or any ERP system
- Requirements gathering, process mapping, stakeholder documentation
- Power BI, SQL, data reporting, KPI development
- Supply chain, manufacturing, logistics, retail, government, healthcare domains
- Agile/Scrum environment

Weak match (include but rank lower):
- Pure finance domain with no supply chain angle
- Roles requiring D365/NetSuite as primary tool with no SAP
- Pure software development roles
- Roles requiring 5+ years domain-specific experience

Hard exclude (score must be 0 -- do not surface):
- Roles outside BC
- Roles requiring Canadian citizenship or security clearance
- Roles below 2 years experience requirement
"""

seen_urls: set = set()


def normalize_title(title: str) -> bool:
    t = title.lower()
    return any(kw in t for kw in TITLE_KEYWORDS)


def make_id(url: str) -> str:
    return hashlib.md5(url.encode()).hexdigest()[:12]


def clean_html(raw: str) -> str:
    return re.sub(r"<[^>]+>", "", raw or "").strip()[:500]


# ------------------------------------------------------------------
# BC LOCATION FILTER
# ------------------------------------------------------------------

_BC_KEEP = re.compile(
    r"british columbia|vancouver|surrey|burnaby|richmond|coquitlam|langley|"
    r"abbotsford|kelowna|victoria|nanaimo|delta|new westminster|port moody|"
    r"maple ridge|north vancouver|west vancouver|white rock|chilliwack|kamloops|"
    r"remote|canada|anywhere|worldwide",
    re.IGNORECASE,
)
_NON_BC = re.compile(
    r"ontario|alberta|quebec|manitoba|saskatchewan|nova scotia|new brunswick|"
    r"newfoundland|prince edward|yukon|nunavut|northwest territories|"
    r"toronto|ottawa|montreal|calgary|edmonton|winnipeg|"
    r"united states|\busa?\b|new york|california|texas|washington,? d|"
    r"seattle|san francisco|los angeles|chicago|boston|austin|denver|"
    r"europe|germany|united kingdom|\buk\b|australia|india|asia",
    re.IGNORECASE,
)


def is_bc_eligible(location: str) -> bool:
    loc = location.strip()
    if not loc or loc.lower() in ("unknown", ""):
        return True  # no location info -- pass through, let Gemini decide
    if re.search(r"\bbc\b", loc, re.IGNORECASE):
        return True
    if _BC_KEEP.search(loc):
        return True
    if _NON_BC.search(loc):
        return False
    return True  # unrecognised location -- pass through


def parse_date(pub: str):
    if not pub:
        return None
    try:
        if "T" in pub:
            dt = datetime.fromisoformat(pub.replace("Z", "+00:00"))
        else:
            dt = parsedate_to_datetime(pub)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except Exception:
        return None


# ------------------------------------------------------------------
# SOURCE 1: Canada Job Bank (RSS)
# ------------------------------------------------------------------

JOBBANK_SEARCHES = [
    "data analyst",
    "business intelligence",
    "business analyst",
    "supply chain analyst",
    "inventory analyst",
    "business systems analyst",
    "reporting analyst",
]


def fetch_jobbank() -> list:
    jobs = []
    for keyword in JOBBANK_SEARCHES:
        q = keyword.replace(" ", "+")
        url = (
            "https://www.jobbank.gc.ca/jobsearch/rss"
            "?searchstring={}&locationstring=British+Columbia&sort=M".format(q)
        )
        try:
            feed = feedparser.parse(url)
            for entry in feed.entries:
                title = entry.get("title", "")
                link = entry.get("link", "")
                if not link or link in seen_urls:
                    continue
                if not normalize_title(title):
                    continue
                seen_urls.add(link)
                jobs.append({
                    "id": make_id(link),
                    "title": title,
                    "company": entry.get("author", "Unknown"),
                    "location": "British Columbia, CA",
                    "url": link,
                    "source": "Canada Job Bank",
                    "published": entry.get("published", ""),
                    "description": clean_html(entry.get("summary", "")),
                    "contract_type": "Unknown",
                })
        except Exception as e:
            print("[JobBank] Error for '{}': {}".format(keyword, e))
    print("[Job Bank] {} jobs".format(len(jobs)))
    return jobs


# ------------------------------------------------------------------
# SOURCE 2: Remotive (free public JSON API)
# ------------------------------------------------------------------

REMOTIVE_CATEGORIES = ["data", "management"]


def fetch_remotive() -> list:
    jobs = []
    for cat in REMOTIVE_CATEGORIES:
        url = "https://remotive.com/api/remote-jobs?category={}&limit=50".format(cat)
        try:
            r = requests.get(url, timeout=15)
            data = r.json()
            for job in data.get("jobs", []):
                title = job.get("title", "")
                link = job.get("url", "")
                if not link or link in seen_urls:
                    continue
                if not normalize_title(title):
                    continue
                seen_urls.add(link)
                jobs.append({
                    "id": make_id(link),
                    "title": title,
                    "company": job.get("company_name", "Unknown"),
                    "location": job.get("candidate_required_location", "Remote"),
                    "url": link,
                    "source": "Remotive",
                    "published": job.get("publication_date", ""),
                    "description": clean_html(job.get("description", "")),
                    "contract_type": job.get("job_type", "Unknown"),
                })
        except Exception as e:
            print("[Remotive] Error for category '{}': {}".format(cat, e))
    print("[Remotive] {} jobs".format(len(jobs)))
    return jobs


# ------------------------------------------------------------------
# SOURCE 3: We Work Remotely (RSS)
# ------------------------------------------------------------------

WWR_FEEDS = [
    "https://weworkremotely.com/categories/remote-data-jobs.rss",
    "https://weworkremotely.com/categories/remote-management-and-finance-jobs.rss",
    "https://weworkremotely.com/remote-jobs/search.rss?term=data+analyst",
    "https://weworkremotely.com/remote-jobs/search.rss?term=business+analyst",
    "https://weworkremotely.com/remote-jobs/search.rss?term=business+intelligence",
]


def fetch_weworkremotely() -> list:
    jobs = []
    for url in WWR_FEEDS:
        try:
            feed = feedparser.parse(url)
            for entry in feed.entries:
                title = entry.get("title", "")
                link = entry.get("link", "")
                if not link or link in seen_urls:
                    continue
                if not normalize_title(title):
                    continue
                seen_urls.add(link)
                jobs.append({
                    "id": make_id(link),
                    "title": title,
                    "company": entry.get("author", "Unknown"),
                    "location": "Remote",
                    "url": link,
                    "source": "We Work Remotely",
                    "published": entry.get("published", ""),
                    "description": clean_html(entry.get("summary", "")),
                    "contract_type": "Unknown",
                })
        except Exception as e:
            print("[WWR] Error for {}: {}".format(url, e))
    print("[We Work Remotely] {} jobs".format(len(jobs)))
    return jobs


# ------------------------------------------------------------------
# SOURCE 4: Jobicy (RSS)
# ------------------------------------------------------------------

JOBICY_FEEDS = [
    "https://jobicy.com/?feed=job_feed&job_categories=data-science&search_keywords=analyst&search_region=Canada",
    "https://jobicy.com/?feed=job_feed&job_categories=data-science&search_keywords=business+intelligence",
    "https://jobicy.com/?feed=job_feed&job_categories=data-science&search_keywords=supply+chain",
]


def fetch_jobicy() -> list:
    jobs = []
    for url in JOBICY_FEEDS:
        try:
            feed = feedparser.parse(url)
            for entry in feed.entries:
                title = entry.get("title", "")
                link = entry.get("link", "")
                if not link or link in seen_urls:
                    continue
                if not normalize_title(title):
                    continue
                seen_urls.add(link)
                jobs.append({
                    "id": make_id(link),
                    "title": title,
                    "company": entry.get("author", "Unknown"),
                    "location": "Remote",
                    "url": link,
                    "source": "Jobicy",
                    "published": entry.get("published", ""),
                    "description": clean_html(entry.get("summary", "")),
                    "contract_type": "Unknown",
                })
        except Exception as e:
            print("[Jobicy] Error for {}: {}".format(url, e))
    print("[Jobicy] {} jobs".format(len(jobs)))
    return jobs


# ------------------------------------------------------------------
# SOURCE 5: Greenhouse (public API, no auth)
# ------------------------------------------------------------------

GREENHOUSE_COMPANIES = [
    "hootsuite", "lululemon", "finning", "bchydro", "telus",
    "absolute", "freshworks", "d2l", "sophos", "pivotal",
    "bench", "slack", "clio", "tasktop", "trulioo",
    "bestbuy", "paladin", "visier", "demonware", "finger-food",
    "haventec", "beanworks", "klue", "procurify", "unbounce",
    "thinkific", "vendasta", "intapp", "jobber", "coconut",
]


def fetch_greenhouse() -> list:
    jobs = []
    for company in GREENHOUSE_COMPANIES:
        url = "https://api.greenhouse.io/v1/boards/{}/jobs?content=true".format(company)
        try:
            r = requests.get(url, timeout=10)
            if r.status_code != 200:
                continue
            data = r.json()
            for job in data.get("jobs", []):
                title = job.get("title", "")
                link = job.get("absolute_url", "")
                if not link or link in seen_urls:
                    continue
                if not normalize_title(title):
                    continue
                location = (
                    job.get("location", {}).get("name", "")
                    if isinstance(job.get("location"), dict)
                    else ""
                )
                loc_lower = location.lower()
                if not any(kw in loc_lower for kw in ["british columbia", "bc", "vancouver", "canada", "remote", "anywhere"]):
                    continue
                seen_urls.add(link)
                jobs.append({
                    "id": make_id(link),
                    "title": title,
                    "company": company.capitalize(),
                    "location": location or "Canada",
                    "url": link,
                    "source": "Greenhouse",
                    "published": "",  # updated_at is unreliable; treat as undated so active jobs always pass the recency filter
                    "description": clean_html(job.get("content", "")),
                    "contract_type": "Unknown",
                })
        except Exception as e:
            print("[Greenhouse] Error for {}: {}".format(company, e))
    print("[Greenhouse] {} jobs".format(len(jobs)))
    return jobs


# ------------------------------------------------------------------
# SOURCE 6: Lever (public API, no auth)
# ------------------------------------------------------------------

LEVER_COMPANIES = [
    "miovision", "zymeworks", "kabam", "traction-on-demand",
    "dyndrite", "tipalti", "fiix", "push-operations", "swiftly",
    "switchboard", "arcurve", "boast-capital", "bravura",
    "cgi", "elasticpath", "galvanize", "geomechanica",
    "lymbix", "mineraltree", "pagerduty", "pivotal",
    "questrade", "richtree", "xactly", "zoho",
    "kontrol-solutions", "hyivy-health", "deepform",
]


def fetch_lever() -> list:
    jobs = []
    for company in LEVER_COMPANIES:
        url = "https://api.lever.co/v0/postings/{}?mode=json".format(company)
        try:
            r = requests.get(url, timeout=10)
            if r.status_code != 200:
                continue
            postings = r.json()
            if not isinstance(postings, list):
                continue
            for job in postings:
                title = job.get("text", "")
                link = job.get("hostedUrl", "")
                if not link or link in seen_urls:
                    continue
                if not normalize_title(title):
                    continue
                categories = job.get("categories", {})
                location = categories.get("location", "")
                commitment = categories.get("commitment", "")
                seen_urls.add(link)
                created_ms = job.get("createdAt", 0)
                published = (
                    datetime.fromtimestamp(created_ms / 1000, tz=timezone.utc).isoformat()
                    if created_ms
                    else ""
                )
                jobs.append({
                    "id": make_id(link),
                    "title": title,
                    "company": company.replace("-", " ").title(),
                    "location": location or commitment or "Remote/Canada",
                    "url": link,
                    "source": "Lever",
                    "published": "",  # createdAt is original post date but old open roles should still surface; use history for dedup
                    "description": clean_html(
                        job.get("descriptionPlain", "") or job.get("description", "")
                    ),
                    "contract_type": commitment or "Unknown",
                })
        except Exception as e:
            print("[Lever] Error for {}: {}".format(company, e))
    print("[Lever] {} jobs".format(len(jobs)))
    return jobs


# ------------------------------------------------------------------
# SOURCE 7: Ashby (public API, no auth)
# ------------------------------------------------------------------

ASHBY_COMPANIES = [
    "1password", "dapper-labs", "axiom", "lattice",
    "rewind", "secureframe", "hightouch", "census",
    "transform", "lightdash", "metabase", "preset",
    "modeanalytics", "hex", "deepnote", "count",
    "glean", "mosaic", "pigment", "ramp",
    "dbt-labs", "anomalo", "monte-carlo", "acceldata",
]


def fetch_ashby() -> list:
    jobs = []
    for company in ASHBY_COMPANIES:
        url = "https://api.ashbyhq.com/posting-api/job-board/{}?includeCompensation=true".format(company)
        try:
            r = requests.get(url, timeout=10)
            if r.status_code != 200:
                continue
            data = r.json()
            for job in data.get("jobs", []):
                title = job.get("title", "")
                link = job.get("jobUrl", "")
                if not link or link in seen_urls:
                    continue
                if not normalize_title(title):
                    continue
                location = job.get("location", "")
                is_remote = job.get("isRemote", False)
                loc_lower = location.lower()
                if not is_remote and not any(
                    kw in loc_lower for kw in ["british columbia", "bc", "vancouver", "canada", "remote"]
                ):
                    continue
                seen_urls.add(link)
                jobs.append({
                    "id": make_id(link),
                    "title": title,
                    "company": company.replace("-", " ").title(),
                    "location": ("Remote" if is_remote else location) or "Remote",
                    "url": link,
                    "source": "Ashby",
                    "published": "",  # treat as undated so active open roles always pass the recency filter
                    "description": clean_html(
                        job.get("descriptionPlain", "") or job.get("descriptionHtml", "")
                    ),
                    "contract_type": job.get("employmentType", "Unknown"),
                })
        except Exception as e:
            print("[Ashby] Error for {}: {}".format(company, e))
    print("[Ashby] {} jobs".format(len(jobs)))
    return jobs


# ------------------------------------------------------------------
# SOURCE 8: WorkBC (JSON API)
# ------------------------------------------------------------------

WORKBC_KEYWORDS = [
    "data analyst",
    "business analyst",
    "business intelligence",
    "supply chain analyst",
    "reporting analyst",
    "systems analyst",
]


def fetch_workbc() -> list:
    jobs = []
    for keyword in WORKBC_KEYWORDS:
        url = "https://www.workbc.ca/api/jobsearch"
        params = {
            "keyword": keyword,
            "location": "British Columbia",
            "page": 1,
            "perPage": 25,
        }
        try:
            r = requests.get(
                url,
                params=params,
                timeout=15,
                headers={"Accept": "application/json", "User-Agent": "Mozilla/5.0"},
            )
            if r.status_code != 200:
                continue
            data = r.json()
            # WorkBC may return a list directly or wrap it
            job_list = data if isinstance(data, list) else data.get("jobs", data.get("results", []))
            if not isinstance(job_list, list):
                continue
            for job in job_list:
                title = job.get("title", job.get("JobTitle", ""))
                link = job.get("url", job.get("JobURL", job.get("applyUrl", "")))
                if not link or link in seen_urls:
                    continue
                if not normalize_title(title):
                    continue
                seen_urls.add(link)
                jobs.append({
                    "id": make_id(link),
                    "title": title,
                    "company": job.get("employer", job.get("company", job.get("EmployerName", "Unknown"))),
                    "location": job.get("location", job.get("city", "British Columbia")),
                    "url": link,
                    "source": "WorkBC",
                    "published": job.get("datePosted", job.get("postDate", job.get("PublishDate", ""))),
                    "description": clean_html(job.get("description", job.get("summary", ""))),
                    "contract_type": job.get("employmentType", job.get("jobType", "Unknown")),
                })
        except Exception as e:
            print("[WorkBC] Error for '{}': {}".format(keyword, e))
    print("[WorkBC] {} jobs".format(len(jobs)))
    return jobs


# ------------------------------------------------------------------
# SOURCE 9: BC Public Service (Workday REST API)
# ------------------------------------------------------------------

BCPS_BASE_URL = "https://bcpublicservice.wd3.myworkdayjobs.com"
BCPS_API = "{}/wday/cxs/bcpublicservice/BC_Params/jobs".format(BCPS_BASE_URL)
BCPS_SEARCHES = ["analyst", "business systems", "supply chain", "data", "reporting"]


def _parse_workday_posted_on(posted_on: str) -> str:
    """Convert Workday 'Posted X Days Ago' to ISO date string."""
    if not posted_on:
        return ""
    if re.search(r"today|just posted", posted_on, re.IGNORECASE):
        return datetime.now(timezone.utc).isoformat()
    m = re.search(r"(\d+)\s+day", posted_on, re.IGNORECASE)
    if m:
        days_ago = int(m.group(1))
        return (datetime.now(timezone.utc) - timedelta(days=days_ago)).isoformat()
    return ""


def fetch_bc_public_service() -> list:
    jobs = []
    seen_paths: set = set()
    for keyword in BCPS_SEARCHES:
        payload = {"appliedFacets": {}, "limit": 20, "offset": 0, "searchText": keyword}
        try:
            r = requests.post(
                BCPS_API,
                json=payload,
                timeout=15,
                headers={
                    "Accept": "application/json",
                    "Content-Type": "application/json",
                    "User-Agent": "Mozilla/5.0",
                },
            )
            if r.status_code != 200:
                continue
            data = r.json()
            for job in data.get("jobPostings", []):
                title = job.get("title", "")
                ext_path = job.get("externalPath", "")
                if not ext_path or ext_path in seen_paths:
                    continue
                if not normalize_title(title):
                    continue
                seen_paths.add(ext_path)
                link = "{}/en-US/BC_Params{}".format(BCPS_BASE_URL, ext_path)
                if link in seen_urls:
                    continue
                seen_urls.add(link)
                jobs.append({
                    "id": make_id(link),
                    "title": title,
                    "company": "BC Public Service",
                    "location": job.get("locationsText", "British Columbia"),
                    "url": link,
                    "source": "BC Public Service",
                    "published": _parse_workday_posted_on(job.get("postedOn", "")),
                    "description": clean_html(job.get("jobDescription", "")),
                    "contract_type": job.get("timeType", "Unknown"),
                })
        except Exception as e:
            print("[BC Public Service] Error for '{}': {}".format(keyword, e))
    print("[BC Public Service] {} jobs".format(len(jobs)))
    return jobs


# ------------------------------------------------------------------
# DATE FILTERING
# ------------------------------------------------------------------

def filter_recent(jobs: list, hours: int = 24) -> list:
    cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)
    recent = []
    undated = []
    for job in jobs:
        dt = parse_date(job.get("published", ""))
        if dt is None:
            job["_dated"] = False
            undated.append(job)
        elif dt >= cutoff:
            job["_dated"] = True
            recent.append(job)
        # jobs with parseable dates older than cutoff are dropped entirely
    print("  Dated+recent: {}, Undated (pass-through): {}".format(len(recent), len(undated)))
    return recent + undated


# ------------------------------------------------------------------
# HISTORY MANAGEMENT
# ------------------------------------------------------------------

def load_history() -> dict:
    if HISTORY_FILE.exists():
        with open(HISTORY_FILE, encoding="utf-8") as f:
            return json.load(f)
    return {}


def save_history(history: dict) -> dict:
    cutoff = datetime.now(timezone.utc) - timedelta(days=HISTORY_MAX_DAYS)
    pruned = {}
    for k, v in history.items():
        date_seen = v.get("date_seen", "")
        try:
            dt = datetime.fromisoformat(date_seen)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            if dt >= cutoff:
                pruned[k] = v
        except Exception:
            pruned[k] = v  # keep entries with unparseable dates
    removed = len(history) - len(pruned)
    if removed:
        print("[History] Pruned {} entries older than {} days".format(removed, HISTORY_MAX_DAYS))
    with open(HISTORY_FILE, "w", encoding="utf-8") as f:
        json.dump(pruned, f, indent=2)
    return pruned


# ------------------------------------------------------------------
# PYTHON KEYWORD SCORER (baseline / Gemini fallback)
# ------------------------------------------------------------------

def python_score(job: dict) -> int:
    title = job.get("title", "").lower()
    desc = job.get("description", "").lower()
    loc = job.get("location", "").lower()
    score = 4  # neutral baseline

    # --- Title signals ---
    if any(k in title for k in ["business systems analyst", "bsa"]):
        score += 4
    elif any(k in title for k in ["erp analyst", "sap analyst"]):
        score += 3
    elif any(k in title for k in ["business analyst", "business intelligence"]):
        score += 2
    elif any(k in title for k in ["supply chain analyst", "reporting analyst", "data analyst"]):
        score += 2
    elif any(k in title for k in ["operations analyst", "analytics engineer", "bi analyst"]):
        score += 1

    # --- Description signals (strong match) ---
    if any(k in desc for k in ["sap", "s/4hana", "s4hana", "erp"]):
        score += 2
    if any(k in desc for k in ["power bi", "powerbi"]):
        score += 1
    if "sql" in desc:
        score += 1
    if any(k in desc for k in ["requirements gathering", "process mapping", "stakeholder"]):
        score += 1
    if any(k in desc for k in ["supply chain", "logistics", "manufacturing", "procurement"]):
        score += 1

    # --- Location bonus ---
    if any(k in loc for k in ["vancouver", "surrey", "burnaby", "british columbia", " bc"]):
        score += 1
    elif re.search(r"\bbc\b", loc, re.IGNORECASE):
        score += 1

    # --- Penalties ---
    if any(k in title for k in ["data scientist", "machine learning", "ml engineer", "software engineer", "developer"]):
        score -= 3
    if any(k in desc for k in ["security clearance", "citizenship required", "citizens only"]):
        score -= 4
    if any(k in desc for k in ["10+ years", "15+ years", "20+ years"]):
        score -= 2

    return max(0, min(10, score))


# ------------------------------------------------------------------
# GEMINI SCORING
# ------------------------------------------------------------------

SCORE_PROMPT = """\
You are scoring a job posting against a candidate profile to determine fit.

CANDIDATE PROFILE:
{profile}

JOB POSTING:
Title: {title}
Company: {company}
Location: {location}
Description: {description}

Score this job 0-10 for how well it matches the candidate.
Apply hard excludes strictly: if the role is outside BC, requires Canadian citizenship or \
security clearance, or requires more than 2 years of highly specific domain experience the \
candidate clearly lacks, return score 0.

Reply in exactly this format (no other text):
score: X
reason: 2-3 sentences explaining specifically why this role fits or does not fit the candidate.\
"""


GEMINI_API_URL = (
    "https://generativelanguage.googleapis.com/v1beta/models/"
    "gemini-1.5-flash:generateContent"
)


def score_job(job: dict):
    """Score a job using Gemini AI. Falls back to Python keyword scorer on any failure."""
    py_score = python_score(job)
    api_key = os.environ.get("GEMINI_API_KEY", "")
    if not api_key:
        print("[Score] No API key -- using Python score ({}/10)".format(py_score))
        return (py_score, _python_reason(job, py_score))
    try:
        prompt = SCORE_PROMPT.format(
            profile=CANDIDATE_PROFILE.strip(),
            title=job.get("title", ""),
            company=job.get("company", ""),
            location=job.get("location", ""),
            description=job.get("description", "")[:400],
        )
        payload = {"contents": [{"parts": [{"text": prompt}]}]}
        r = requests.post(
            GEMINI_API_URL,
            json=payload,
            params={"key": api_key},
            timeout=30,
        )
        r.raise_for_status()
        text = r.json()["candidates"][0]["content"]["parts"][0]["text"]
        score_match = re.search(r"score:\s*(\d+)", text, re.IGNORECASE)
        reason_match = re.search(r"reason:\s*(.+)", text, re.IGNORECASE | re.DOTALL)
        if not score_match:
            raise ValueError("No score found in response: {}".format(text[:200]))
        score = int(score_match.group(1))
        score = min(max(score, 0), 10)
        reason = reason_match.group(1).strip() if reason_match else text.strip()[:400]
        reason = re.sub(r"\s+", " ", reason)
        return (score, reason)
    except Exception as e:
        print("[Gemini] Error for '{}': {} -- falling back to Python score ({}/10)".format(
            job.get("title", ""), e, py_score))
        return (py_score, _python_reason(job, py_score))


def _python_reason(job: dict, score: int) -> str:
    """Generate a brief human-readable reason from the Python scorer signals."""
    title = job.get("title", "").lower()
    desc = job.get("description", "").lower()
    signals = []
    if any(k in title for k in ["business systems analyst", "bsa"]):
        signals.append("title is a top-priority BSA role")
    elif any(k in title for k in ["business analyst", "erp", "sap"]):
        signals.append("title aligns with BA/ERP target roles")
    elif any(k in title for k in ["supply chain", "reporting", "data analyst"]):
        signals.append("title matches target analyst roles")
    if any(k in desc for k in ["sap", "s/4hana", "erp"]):
        signals.append("SAP/ERP mentioned in description")
    if any(k in desc for k in ["power bi", "powerbi"]):
        signals.append("Power BI mentioned")
    if any(k in desc for k in ["supply chain", "logistics"]):
        signals.append("supply chain domain")
    if any(k in desc for k in ["requirements gathering", "stakeholder"]):
        signals.append("requirements/stakeholder work mentioned")
    if not signals:
        signals.append("partial keyword match on title")
    label = "Strong" if score >= 7 else ("Moderate" if score >= 5 else "Weak")
    return "{} keyword match (Python scorer, Gemini unavailable). Signals: {}.".format(
        label, "; ".join(signals)
    )


# ------------------------------------------------------------------
# JOBS.MD OUTPUT
# ------------------------------------------------------------------

def _job_lines(jobs: list, start_rank: int = 1) -> list:
    lines = []
    for i, job in enumerate(jobs, start_rank):
        title = job.get("title", "Unknown")
        company = job.get("company", "Unknown")
        location = job.get("location", "Unknown")
        contract_type = job.get("contract_type", "Unknown")
        posted = (job.get("published", "") or "")[:10] or "Unknown"
        url = job.get("url", "")
        source = job.get("source", "Unknown")
        score = job.get("score", "?")
        reason = job.get("reason", "")
        link_str = url if url else "Apply via {}".format(source)
        lines.append("**{}. {} | {} | {} | {}**".format(i, title, company, location, contract_type))
        lines.append("- Posted: {}".format(posted))
        lines.append("- Link: {}".format(link_str))
        lines.append("- Match score: {}/10".format(score))
        lines.append("- Why this fits: {}".format(reason))
        lines.append("")
    return lines


def _get_timestamp() -> str:
    try:
        from zoneinfo import ZoneInfo
        return datetime.now(ZoneInfo("America/Vancouver")).strftime("%Y-%m-%d %I:%M %p PST")
    except Exception:
        return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")


def write_jobs_md(dated: list, undated: list):
    timestamp = _get_timestamp()
    lines = ["# Job Matches \u2014 Last updated: {}".format(timestamp), ""]

    lines.append("## Postings from the last 24 hours")
    lines.append("")
    if dated:
        lines += _job_lines(dated, start_rank=1)
    else:
        lines.append("*No new dated postings in the last 24 hours.*")
        lines.append("")

    lines.append("## Open roles (no timestamp available)")
    lines.append("")
    if undated:
        lines += _job_lines(undated, start_rank=1)
    else:
        lines.append("*No undated roles found.*")
        lines.append("")

    with open(JOBS_MD, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    print("[JOBS.md] Written: {} dated, {} undated".format(len(dated), len(undated)))


# ------------------------------------------------------------------
# README.MD JOBS SECTION
# ------------------------------------------------------------------

README_FILE = REPO_ROOT / "README.md"
JOBS_MARKER_START = "<!-- JOBS_START -->"
JOBS_MARKER_END = "<!-- JOBS_END -->"


def write_readme_section(dated: list, undated: list):
    """Replace the jobs section in README.md between marker comments."""
    if not README_FILE.exists():
        return
    with open(README_FILE, "r", encoding="utf-8") as f:
        content = f.read()
    if JOBS_MARKER_START not in content or JOBS_MARKER_END not in content:
        return

    timestamp = _get_timestamp()
    lines = ["", "*Last updated: {}*".format(timestamp), ""]

    lines.append("### Postings from the last 24 hours")
    lines.append("")
    if dated:
        lines += _job_lines(dated, start_rank=1)
    else:
        lines.append("*No new dated postings in the last 24 hours.*")
        lines.append("")

    lines.append("### Open roles (no timestamp available)")
    lines.append("")
    if undated:
        lines += _job_lines(undated, start_rank=1)
    else:
        lines.append("*No undated roles found.*")
        lines.append("")

    new_section = "{}\n{}\n{}".format(JOBS_MARKER_START, "\n".join(lines), JOBS_MARKER_END)
    updated = re.sub(
        r"{}.*?{}".format(re.escape(JOBS_MARKER_START), re.escape(JOBS_MARKER_END)),
        new_section,
        content,
        flags=re.DOTALL,
    )
    with open(README_FILE, "w", encoding="utf-8") as f:
        f.write(updated)
    print("[README.md] Jobs section updated: {} dated, {} undated".format(len(dated), len(undated)))


# ------------------------------------------------------------------
# MAIN
# ------------------------------------------------------------------

def main():
    print("=" * 60)
    print("Job Feed Aggregator: {}".format(datetime.now(timezone.utc).isoformat()))
    print("=" * 60)

    all_jobs = []
    all_jobs += fetch_jobbank()
    all_jobs += fetch_remotive()
    all_jobs += fetch_weworkremotely()
    all_jobs += fetch_jobicy()
    all_jobs += fetch_greenhouse()
    all_jobs += fetch_lever()
    all_jobs += fetch_ashby()
    all_jobs += fetch_workbc()
    all_jobs += fetch_bc_public_service()

    print("\nTotal fetched: {}".format(len(all_jobs)))

    # BC-only filter
    bc_jobs = [j for j in all_jobs if is_bc_eligible(j.get("location", ""))]
    print("After BC filter: {} (dropped {})".format(len(bc_jobs), len(all_jobs) - len(bc_jobs)))

    # Filter to last 24h; tags each job with _dated=True/False
    recent = filter_recent(bc_jobs, hours=RECENCY_HOURS)
    print("After {}h filter: {}".format(RECENCY_HOURS, len(recent)))

    # Skip already-seen jobs
    history = load_history()
    new_jobs = [j for j in recent if j["id"] not in history]
    print("New jobs (not in history): {}".format(len(new_jobs)))

    if not new_jobs:
        print("No new jobs to score. JOBS.md not updated.")
        return

    # Score each job (Gemini with Python fallback)
    print("\nScoring {} jobs...".format(len(new_jobs)))
    for job in new_jobs:
        score, reason = score_job(job)
        job["score"] = score
        job["reason"] = reason
        print("  [{}/10] {} @ {}".format(score, job["title"], job.get("company", "")))

    # Split into dated and undated, drop score-0 hard excludes, top 5 each
    def top5(jobs):
        kept = [j for j in jobs if j.get("score", 0) > 0]
        kept.sort(key=lambda j: j.get("score", 0), reverse=True)
        return kept[:TOP_N]

    top_dated = top5([j for j in new_jobs if j.get("_dated")])
    top_undated = top5([j for j in new_jobs if not j.get("_dated")])

    print("\nSelected: {} dated, {} undated".format(len(top_dated), len(top_undated)))

    # Update history with all scored jobs
    now_iso = datetime.now(timezone.utc).isoformat()
    for job in new_jobs:
        history[job["id"]] = {
            "title": job["title"],
            "company": job.get("company", ""),
            "url": job.get("url", ""),
            "date_seen": now_iso,
            "score": job.get("score", 0),
            "dated": job.get("_dated", False),
        }
    save_history(history)

    # Write JOBS.md and update README.md jobs section
    write_jobs_md(top_dated, top_undated)
    write_readme_section(top_dated, top_undated)
    print("\nDone.")


if __name__ == "__main__":
    main()
