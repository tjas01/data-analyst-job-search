"""
Job Feed Aggregator - Tejas Vyasam
Pulls from:
  1. Indeed CA (RSS)         - Broad BC + Remote keyword search
  2. Canada Job Bank (RSS)   - Government/verified CA jobs via searchstring param
  3. Remotive (JSON API)     - Remote tech/data jobs globally, no key needed
  4. We Work Remotely (RSS)  - Remote-first jobs, data/analytics category
  5. Jobicy (RSS)            - Remote jobs, data-science category, Canada region
  6. Greenhouse (JSON API)   - BC tech companies, no auth needed
  7. Lever (JSON API)        - BC tech companies, no auth needed
  8. Ashby (JSON API)        - BC startups/scaleups, no auth needed

Outputs:
  - data/jobs_latest.json  (all jobs, deduped)
  - data/jobs_latest.csv   (same, CSV format)
  - data/jobs_latest.html  (readable digest)
  - data/jobs_digest.txt   (plain-text, newest first)
"""

import feedparser
import requests
import json
import csv
import hashlib
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from email.utils import parsedate_to_datetime

# -
# CONFIG
# -

OUTPUT_DIR = Path("data")
OUTPUT_DIR.mkdir(exist_ok=True)

# Job title keywords to match (case-insensitive, any one must match)
TITLE_KEYWORDS = [
    "data analyst",
    "business intelligence",
    "bi analyst",
    "bi developer",
    "business analyst",
    "inventory analyst",
    "supply chain analyst",
    "data engineer",
    "analytics engineer",
    "reporting analyst",
]

# Deduplicate seen job URLs
seen_urls = set()


def normalize_title(title: str) -> bool:
    """Return True if the job title matches our target keywords."""
    t = title.lower()
    return any(kw in t for kw in TITLE_KEYWORDS)


def make_id(url: str) -> str:
    return hashlib.md5(url.encode()).hexdigest()[:12]


def clean_html(raw: str) -> str:
    return re.sub(r"<[^>]+>", "", raw or "").strip()[:300]


# -
# SOURCE 1: Indeed CA RSS
# -

INDEED_SEARCHES = [
    ("Data Analyst", "British+Columbia"),
    ("Business Intelligence Analyst", "British+Columbia"),
    ("Business Intelligence Developer", "British+Columbia"),
    ("Business Analyst", "British+Columbia"),
    ("Inventory Analyst", "British+Columbia"),
    ("Supply Chain Analyst", "British+Columbia"),
    # Remote Canada searches
    ("Data Analyst", "Canada"),
    ("Business Intelligence Analyst", "Canada"),
    ("Business Analyst data", "Canada"),
]


def fetch_indeed() -> list[dict]:
    jobs = []
    for query, location in INDEED_SEARCHES:
        q = query.replace(" ", "+")
        url = f"https://rss.indeed.com/rss?q={q}&l={location}&sort=date&limit=25"
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
                pub = entry.get("published", "")
                jobs.append({
                    "id": make_id(link),
                    "title": title,
                    "company": entry.get("source", {}).get("title", "Unknown") if hasattr(entry.get("source", ""), "get") else "Unknown",
                    "location": entry.get("location", location.replace("+", " ")),
                    "url": link,
                    "source": "Indeed CA",
                    "published": pub,
                    "description": clean_html(entry.get("summary", "")),
                })
        except Exception as e:
            print(f"[Indeed] Error for '{query}' / '{location}': {e}")
    print(f"[Indeed] {len(jobs)} jobs")
    return jobs


# -
# SOURCE 2: Canada Job Bank (RSS via search URL)
# -

JOBBANK_SEARCHES = [
    "data analyst",
    "business intelligence",
    "business analyst",
    "supply chain analyst",
    "inventory analyst",
]


def fetch_jobbank() -> list[dict]:
    jobs = []
    for keyword in JOBBANK_SEARCHES:
        q = keyword.replace(" ", "+")
        url = f"https://www.jobbank.gc.ca/jobsearch/rss?searchstring={q}&locationstring=British+Columbia&sort=M"
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
                })
        except Exception as e:
            print(f"[JobBank] Error for '{keyword}': {e}")
    print(f"[Job Bank] {len(jobs)} jobs")
    return jobs


# -
# SOURCE 3: Remotive (free public JSON API)
# -

REMOTIVE_CATEGORIES = ["data", "management"]


def fetch_remotive() -> list[dict]:
    jobs = []
    for cat in REMOTIVE_CATEGORIES:
        url = f"https://remotive.com/api/remote-jobs?category={cat}&limit=50"
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
                })
        except Exception as e:
            print(f"[Remotive] Error for category '{cat}': {e}")
    print(f"[Remotive] {len(jobs)} jobs")
    return jobs


# -
# SOURCE 4: We Work Remotely (RSS)
# -

WWR_FEEDS = [
    "https://weworkremotely.com/categories/remote-data-jobs.rss",
    "https://weworkremotely.com/categories/remote-management-and-finance-jobs.rss",
    "https://weworkremotely.com/remote-jobs/search.rss?term=data+analyst",
    "https://weworkremotely.com/remote-jobs/search.rss?term=business+analyst",
    "https://weworkremotely.com/remote-jobs/search.rss?term=business+intelligence",
]


def fetch_weworkremotely() -> list[dict]:
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
                })
        except Exception as e:
            print(f"[WWR] Error for {url}: {e}")
    print(f"[We Work Remotely] {len(jobs)} jobs")
    return jobs


# -
# SOURCE 5: Jobicy (RSS - free public feed)
# -

JOBICY_FEEDS = [
    "https://jobicy.com/?feed=job_feed&job_categories=data-science&search_keywords=analyst&search_region=Canada",
    "https://jobicy.com/?feed=job_feed&job_categories=data-science&search_keywords=business+intelligence",
    "https://jobicy.com/?feed=job_feed&job_categories=data-science&search_keywords=supply+chain",
]


def fetch_jobicy() -> list[dict]:
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
                })
        except Exception as e:
            print(f"[Jobicy] Error for {url}: {e}")
    print(f"[Jobicy] {len(jobs)} jobs")
    return jobs


# -
# SOURCE 6: Greenhouse (public API, no auth)
# -

GREENHOUSE_COMPANIES = [
    "hootsuite", "lululemon", "finning", "bchydro", "telus",
    "absolute", "freshworks", "d2l", "sophos", "pivotal",
    "bench", "slack", "clio", "tasktop", "trulioo",
    "bestbuy", "paladin", "visier", "demonware", "finger-food",
    "haventec", "beanworks", "klue", "procurify", "unbounce",
    "thinkific", "vendasta", "intapp", "jobber", "coconut",
]


def fetch_greenhouse() -> list[dict]:
    jobs = []
    for company in GREENHOUSE_COMPANIES:
        url = f"https://api.greenhouse.io/v1/boards/{company}/jobs?content=true"
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
                location = job.get("location", {}).get("name", "") if isinstance(job.get("location"), dict) else ""
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
                    "published": job.get("updated_at", ""),
                    "description": clean_html(job.get("content", "")),
                })
        except Exception as e:
            print(f"[Greenhouse] Error for {company}: {e}")
    print(f"[Greenhouse] {len(jobs)} jobs")
    return jobs


# -
# SOURCE 7: Lever (public API, no auth)
# -

LEVER_COMPANIES = [
    "miovision", "zymeworks", "kabam", "traction-on-demand",
    "dyndrite", "tipalti", "fiix", "push-operations", "swiftly",
    "switchboard", "arcurve", "boast-capital", "bravura",
    "cgi", "elasticpath", "galvanize", "geomechanica",
    "lymbix", "mineraltree", "pagerduty", "pivotal",
    "questrade", "richtree", "xactly", "zoho",
    "kontrol-solutions", "hyivy-health", "deepform",
]


def fetch_lever() -> list[dict]:
    jobs = []
    for company in LEVER_COMPANIES:
        url = f"https://api.lever.co/v0/postings/{company}?mode=json"
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
                jobs.append({
                    "id": make_id(link),
                    "title": title,
                    "company": company.replace("-", " ").title(),
                    "location": location or commitment or "Remote/Canada",
                    "url": link,
                    "source": "Lever",
                    "published": datetime.fromtimestamp(
                        job.get("createdAt", 0) / 1000, tz=timezone.utc
                    ).isoformat() if job.get("createdAt") else "",
                    "description": clean_html(job.get("descriptionPlain", "") or job.get("description", "")),
                })
        except Exception as e:
            print(f"[Lever] Error for {company}: {e}")
    print(f"[Lever] {len(jobs)} jobs")
    return jobs


# -
# SOURCE 8: Ashby (public API, no auth)
# -

ASHBY_COMPANIES = [
    "1password", "dapper-labs", "axiom", "lattice",
    "rewind", "secureframe", "hightouch", "census",
    "transform", "lightdash", "metabase", "preset",
    "modeanalytics", "hex", "deepnote", "count",
    "glean", "mosaic", "pigment", "ramp",
    "dbt-labs", "anomalo", "monte-carlo", "acceldata",
]


def fetch_ashby() -> list[dict]:
    jobs = []
    for company in ASHBY_COMPANIES:
        url = f"https://api.ashbyhq.com/posting-api/job-board/{company}?includeCompensation=true"
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
                if not is_remote and not any(kw in loc_lower for kw in ["british columbia", "bc", "vancouver", "canada", "remote"]):
                    continue
                seen_urls.add(link)
                comp = job.get("compensation", {})
                salary = comp.get("compensationTierSummary", "") if comp else ""
                jobs.append({
                    "id": make_id(link),
                    "title": title,
                    "company": company.replace("-", " ").title(),
                    "location": ("Remote" if is_remote else location) or "Remote",
                    "url": link,
                    "source": "Ashby",
                    "published": job.get("publishedAt", ""),
                    "description": clean_html(job.get("descriptionPlain", "") or job.get("descriptionHtml", "")),
                    "salary": salary,
                })
        except Exception as e:
            print(f"[Ashby] Error for {company}: {e}")
    print(f"[Ashby] {len(jobs)} jobs")
    return jobs


# -
# SAVE OUTPUTS
# -

def save_json(jobs: list[dict]):
    path = OUTPUT_DIR / "jobs_latest.json"
    with open(path, "w") as f:
        json.dump({"fetched_at": datetime.now(timezone.utc).isoformat(), "count": len(jobs), "jobs": jobs}, f, indent=2)
    print(f"Saved {len(jobs)} jobs to {path}")


def save_csv(jobs: list[dict]):
    path = OUTPUT_DIR / "jobs_latest.csv"
    fields = ["id", "title", "company", "location", "source", "published", "url", "description", "salary"]
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(jobs)
    print(f"Saved CSV to {path}")


def save_html(jobs: list[dict]):
    path = OUTPUT_DIR / "jobs_latest.html"
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    source_colors = {
        "Indeed CA": "#2164f3",
        "Canada Job Bank": "#cc0000",
        "Remotive": "#0fa36a",
        "We Work Remotely": "#1a1a2e",
        "Jobicy": "#7c3aed",
        "Greenhouse": "#30a46c",
        "Lever": "#0057ff",
        "Ashby": "#e85d04",
    }

    rows = ""
    for j in jobs:
        color = source_colors.get(j["source"], "#555")
        salary = f" &nbsp;|&nbsp; <strong>{j.get('salary','')}</strong>" if j.get("salary") else ""
        rows += f"""
        <tr>
          <td><a href="{j['url']}" target="_blank"><strong>{j['title']}</strong></a></td>
          <td>{j['company']}</td>
          <td>{j['location']}</td>
          <td><span style="background:{color};color:#fff;padding:2px 7px;border-radius:4px;font-size:11px">{j['source']}</span></td>
          <td style="font-size:12px;color:#666">{j['published'][:10] if j['published'] else ''}{salary}</td>
        </tr>"""

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<title>Job Feed - Tejas Vyasam</title>
<style>
  body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; max-width: 1200px; margin: 40px auto; padding: 0 20px; color: #222; }}
  h1 {{ font-size: 22px; margin-bottom: 4px; }}
  .meta {{ color: #888; font-size: 13px; margin-bottom: 24px; }}
  table {{ width: 100%; border-collapse: collapse; font-size: 14px; }}
  th {{ background: #f5f5f5; padding: 10px 12px; text-align: left; border-bottom: 2px solid #ddd; font-size: 12px; text-transform: uppercase; letter-spacing: 0.5px; }}
  td {{ padding: 10px 12px; border-bottom: 1px solid #eee; vertical-align: top; }}
  tr:hover td {{ background: #fafafa; }}
  a {{ color: #1a6ef5; text-decoration: none; }}
  a:hover {{ text-decoration: underline; }}
</style>
</head>
<body>
<h1>Job Feed Digest</h1>
<div class="meta">Generated: {now} &nbsp;|&nbsp; {len(jobs)} jobs found</div>
<table>
  <thead>
    <tr><th>Title</th><th>Company</th><th>Location</th><th>Source</th><th>Date / Salary</th></tr>
  </thead>
  <tbody>
    {rows}
  </tbody>
</table>
</body>
</html>"""
    with open(path, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"Saved HTML to {path}")


def save_txt(jobs: list[dict]):
    path = OUTPUT_DIR / "jobs_digest.txt"
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    lines = [
        f"Job Feed Digest - {now}",
        f"{len(jobs)} jobs found",
        "=" * 70,
        "",
    ]
    for i, j in enumerate(jobs, 1):
        date = (j.get("published") or "")[:10]
        salary = f"  Salary: {j['salary']}" if j.get("salary") else ""
        lines.append(f"{):3}. {j['title']}")
        lines.append(f"     Company:  {j.get('company', '')}")
        lines.append(f"     Location: {j.get('location', '')}")
        lines.append(f"     Source:   {j['wource']}  |  Date: {date}{salary}")
        lines.append(f"     URL:      {j['url']}")
        lines.append("")
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    print(f"Saved digest to {path}")


def main():
    print("=" * 50)
    print(f"Job Feed Aggregator starting: {datetime.now().isoformat()}")
    print("=" * 50)

    all_jobs = []
    all_jobs += fetch_indeed()
    all_jobs += fetch_jobbank()
    all_jobs += fetch_remotive()
    all_jobs += fetch_weworkremotely()
    all_jobs += fetch_jobicy()
    all_jobs += fetch_greenhouse()
    all_jobs += fetch_lever()
    all_jobs += fetch_ashby()

    all_jobs.sort(key=lambda j: j.get("published", "") or "", reverse=True)

    print(f"\nTotal unique jobs: {len(all_jobs)}")

    save_json(all_jobs)
    save_csv(all_jobs)
    save_html(all_jobs)
    save_txt(all_jobs)

    print("Done.")


if __name__ == "__main__":
    main()
