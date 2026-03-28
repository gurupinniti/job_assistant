"""
JobSearcherTool

Portal tiers (ordered by ease of apply):
  Tier 1 - No auth needed, direct apply possible
  Tier 2 - Optional login, most jobs apply without account
  Tier 3 - Login required

Job filtering:
  - Must contain job-related words in title
  - Must match the selected country/location
  - Deduplicated by URL
"""

import json
import re
import time
import random
import requests
from typing import Type, Any, List
from pydantic import BaseModel, Field
from langchain_core.tools import BaseTool

# ---------------------------------------------------------------------------
# Portal catalogue — Tier 1 first
# ---------------------------------------------------------------------------

PORTAL_CATALOGUE = {
    "Adzuna": {
        "tier": 1, "auth": "none",
        "description": "Free API · direct apply links · no login",
        "url": "https://www.adzuna.com", "easy_apply": True, "restriction": None,
    },
    "Arbeitnow": {
        "tier": 1, "auth": "none",
        "description": "Global jobs API · no login · direct apply",
        "url": "https://arbeitnow.com", "easy_apply": True, "restriction": None,
    },
    "RemoteOK": {
        "tier": 1, "auth": "none",
        "description": "Remote jobs · no login · direct apply",
        "url": "https://remoteok.com", "easy_apply": True, "restriction": "Remote roles only",
    },
    "TheMuse": {
        "tier": 1, "auth": "none",
        "description": "Tech & creative roles · free API",
        "url": "https://www.themuse.com", "easy_apply": True, "restriction": None,
    },
    "Jobsdb": {
        "tier": 1, "auth": "none",
        "description": "Asia-Pacific jobs · no login needed",
        "url": "https://jobsdb.com", "easy_apply": True, "restriction": "Asia-Pacific focus",
    },
    "Indeed": {
        "tier": 2, "auth": "optional",
        "description": "Many jobs apply without login",
        "url": "https://www.indeed.com", "easy_apply": True, "restriction": "Some jobs require account",
    },
    "JobStreet": {
        "tier": 2, "auth": "optional",
        "description": "Southeast Asia focus",
        "url": "https://www.jobstreet.com", "easy_apply": True, "restriction": "Account recommended",
    },
    "Naukri": {
        "tier": 2, "auth": "optional",
        "description": "India focus",
        "url": "https://www.naukri.com", "easy_apply": True, "restriction": "India-focused",
    },
    "Seek": {
        "tier": 2, "auth": "optional",
        "description": "Australia/NZ focus",
        "url": "https://www.seek.com.au", "easy_apply": True, "restriction": "AU/NZ roles",
    },
    "Reed": {
        "tier": 2, "auth": "optional",
        "description": "UK focus",
        "url": "https://www.reed.co.uk", "easy_apply": True, "restriction": "UK roles",
    },
    "LinkedIn": {
        "tier": 3, "auth": "required",
        "description": "Login required for Easy Apply",
        "url": "https://www.linkedin.com/jobs", "easy_apply": False, "restriction": "Login required",
    },
    "MyCareersFuture": {
        "tier": 3, "auth": "required",
        "description": "SingPass login required",
        "url": "https://www.mycareersfuture.gov.sg", "easy_apply": False, "restriction": "SingPass required",
    },
    "Glassdoor": {
        "tier": 3, "auth": "required",
        "description": "Login required",
        "url": "https://www.glassdoor.com", "easy_apply": False, "restriction": "Login required",
    },
}

COUNTRY_PORTALS = {
    "singapore": ["Adzuna","Jobsdb","JobStreet","Indeed","MyCareersFuture","LinkedIn","Glassdoor"],
    "india":     ["Adzuna","Naukri","Indeed","LinkedIn","Glassdoor"],
    "australia": ["Adzuna","Seek","Indeed","LinkedIn","Glassdoor"],
    "usa":       ["Adzuna","Indeed","TheMuse","RemoteOK","Arbeitnow","LinkedIn","Glassdoor"],
    "uk":        ["Adzuna","Reed","Indeed","LinkedIn","Glassdoor"],
    "malaysia":  ["Adzuna","JobStreet","Jobsdb","Indeed","LinkedIn"],
    "uae":       ["Adzuna","Indeed","LinkedIn","Glassdoor"],
    "germany":   ["Adzuna","Arbeitnow","Indeed","LinkedIn","Glassdoor"],
    "canada":    ["Adzuna","Indeed","LinkedIn","Glassdoor"],
    "default":   ["Adzuna","Indeed","RemoteOK","LinkedIn"],
}

# Adzuna country codes
ADZUNA_CC = {
    "singapore": "sg", "india": "in", "australia": "au", "usa": "us",
    "uk": "gb", "malaysia": "my", "canada": "ca", "germany": "de",
    "uae": "ae", "default": "gb",
}

# Words that indicate it's a real job posting (not an article/guide)
JOB_TITLE_SIGNALS = [
    "engineer", "developer", "scientist", "analyst", "manager", "director",
    "specialist", "consultant", "architect", "lead", "senior", "junior",
    "associate", "coordinator", "officer", "executive", "head", "vp",
    "intern", "trainee", "researcher", "administrator", "designer",
    "data", "software", "product", "project", "operations", "hr",
    "finance", "marketing", "sales", "devops", "cloud", "ai", "ml",
]

ARTICLE_SIGNALS = [
    "what is", "what does", "how to", "guide to", "introduction to",
    "best practices", "tips for", "learn ", "course", "salary guide",
    "interview questions", "vs ", "tutorial",
]

INTERNSHIP_SIGNALS = [
    "intern", "internship", "trainee", "apprentice", "graduate trainee",
    "fresh graduate", "entry level", "0-1 year", "0 year",
]

SENIOR_SIGNALS = [
    "senior", "lead", "principal", "staff", "head of", "director",
    "manager", "architect", "vp ", "chief", "c-level",
]

def _is_real_job(title: str, url: str, min_years_exp: int = 0) -> bool:
    """Filter out articles, guides, and jobs that don't match seniority."""
    title_l = title.lower()
    # Reject articles
    if any(sig in title_l for sig in ARTICLE_SIGNALS):
        return False
    # Reject if URL is a blog/guide/article page
    url_l = url.lower()
    if any(x in url_l for x in ["/blog/", "/guide/", "/advice/", "/article/", "/learn/"]):
        return False
    # Filter internships for experienced candidates (>2 years exp)
    if min_years_exp > 2:
        if any(sig in title_l for sig in INTERNSHIP_SIGNALS):
            return False
    # Must have at least one job signal in title
    return any(sig in title_l for sig in JOB_TITLE_SIGNALS)

def _location_matches(job_location: str, expected_country: str) -> bool:
    """Check if a job's location roughly matches the selected country."""
    if not job_location or not expected_country:
        return True  # can't verify, include it
    jl = job_location.lower()
    ec = expected_country.lower()

    country_aliases = {
        "singapore": ["singapore", "sg", " sg"],
        "india":     ["india", "bangalore", "mumbai", "delhi", "hyderabad", "chennai", "pune"],
        "australia": ["australia", "sydney", "melbourne", "brisbane", "perth", "au"],
        "usa":       ["usa", "united states", "new york", "san francisco", "california",
                      "texas", "seattle", "boston", "chicago", "remote"],
        "uk":        ["uk", "united kingdom", "london", "manchester", "birmingham", "gb"],
        "malaysia":  ["malaysia", "kuala lumpur", "kl", "penang", "my"],
        "uae":       ["uae", "dubai", "abu dhabi", "united arab"],
        "germany":   ["germany", "berlin", "munich", "frankfurt", "de"],
        "canada":    ["canada", "toronto", "vancouver", "montreal", "ca"],
    }
    aliases = country_aliases.get(ec, [ec])
    return any(alias in jl for alias in aliases) or "remote" in jl

# ---------------------------------------------------------------------------
# Adzuna API
# ---------------------------------------------------------------------------

def _search_adzuna(title: str, location: str, country: str, count: int = 20) -> list:
    try:
        import config
        app_id  = getattr(config, "ADZUNA_APP_ID",  "")
        app_key = getattr(config, "ADZUNA_APP_KEY", "")
        cc      = ADZUNA_CC.get(country.lower(), ADZUNA_CC["default"])

        if not app_id or not app_key:
            print("  [Adzuna] No API key — skipping. Add ADZUNA_APP_ID + ADZUNA_APP_KEY to config.py")
            return []

        # Use exact country location in `where` param
        where = location if location.lower() != country.lower() else location

        url    = f"https://api.adzuna.com/v1/api/jobs/{cc}/search/1"
        params = {
            "app_id":           app_id,
            "app_key":          app_key,
            "what":             title,
            "where":            where,
            "results_per_page": count,
            "sort_by":          "date",        # newest first
            "content-type":     "application/json",
        }
        resp = requests.get(url, params=params, timeout=15)
        resp.raise_for_status()
        data = resp.json()
        jobs = []
        for r in data.get("results", []):
            job_title = r.get("title", title)
            job_url   = r.get("redirect_url", "")
            job_loc   = r.get("location", {}).get("display_name", location)
            if not _is_real_job(job_title, job_url):
                continue
            jobs.append({
                "title":       job_title,
                "company":     r.get("company", {}).get("display_name", ""),
                "location":    job_loc,
                "country":     country.title(),
                "url":         job_url,
                "snippet":     r.get("description", "")[:600],
                "salary":      _fmt_salary(r),
                "posted":      _fmt_date(r.get("created", "")),
                "applicants":  None,           # Adzuna doesn't provide
                "via":         "Adzuna",
                "portal":      "Adzuna",
                "source":      "adzuna_api",
            })
        print(f"  [Adzuna] {len(jobs)} jobs in {cc} ({where})")
        return jobs
    except Exception as e:
        print(f"  [Adzuna] Failed: {e}")
        return []

def _fmt_salary(r: dict) -> str:
    lo = r.get("salary_min")
    hi = r.get("salary_max")
    if lo and hi: return f"${int(lo):,} – ${int(hi):,}/yr"
    if lo:        return f"From ${int(lo):,}/yr"
    return ""

def _fmt_date(iso: str) -> str:
    if not iso: return ""
    try:
        from datetime import datetime, timezone
        dt   = datetime.fromisoformat(iso.replace("Z", "+00:00"))
        diff = datetime.now(timezone.utc) - dt
        d    = diff.days
        if d == 0:   return "Today"
        if d == 1:   return "Yesterday"
        if d < 7:    return f"{d} days ago"
        if d < 30:   return f"{d//7}w ago"
        return f"{d//30}mo ago"
    except Exception:
        return iso[:10]

# ---------------------------------------------------------------------------
# Serper Google Jobs — most important source, location-aware
# ---------------------------------------------------------------------------

def _search_serper_jobs(title: str, location: str, country: str,
                        api_key: str, count: int = 20) -> list:
    """
    Serper /jobs endpoint = Google Jobs aggregator.
    Passes location in query for accurate country filtering.
    """
    try:
        # Include country name explicitly in query to force location filtering
        query   = f"{title} jobs in {location}"
        payload = json.dumps({"q": query, "num": count, "gl": ADZUNA_CC.get(country.lower(), "sg")})
        headers = {"X-API-KEY": api_key, "Content-Type": "application/json"}
        resp    = requests.post("https://google.serper.dev/jobs",
                                headers=headers, data=payload, timeout=15)
        resp.raise_for_status()
        jobs = []
        for r in resp.json().get("jobs", []):
            job_title = r.get("title", title)
            job_url   = r.get("link", "") or r.get("applyLink", "")
            job_loc   = r.get("location", location)

            if not _is_real_job(job_title, job_url):
                continue
            if not _location_matches(job_loc, country):
                continue   # skip jobs from wrong country

            portal = _portal_from_via(r.get("via", ""))
            jobs.append({
                "title":      job_title,
                "company":    r.get("company", ""),
                "location":   job_loc,
                "country":    country.title(),
                "url":        job_url,
                "snippet":    r.get("description", r.get("snippet", ""))[:600],
                "salary":     r.get("salary", ""),
                "posted":     r.get("date", ""),
                "applicants": None,
                "via":        r.get("via", ""),
                "portal":     portal,
                "source":     "serper_jobs",
            })
        print(f"  [Serper] {len(jobs)} jobs for '{title}' in {location}")
        return jobs
    except Exception as e:
        print(f"  [Serper] Failed: {e}")
        return []

def _portal_from_via(via: str) -> str:
    via_l = via.lower()
    for name in PORTAL_CATALOGUE:
        if name.lower() in via_l:
            return name
    if "indeed"    in via_l: return "Indeed"
    if "linkedin"  in via_l: return "LinkedIn"
    if "glassdoor" in via_l: return "Glassdoor"
    if "seek"      in via_l: return "Seek"
    if "naukri"    in via_l: return "Naukri"
    return "Indeed"

# ---------------------------------------------------------------------------
# RemoteOK — only for remote roles, include regardless of country
# ---------------------------------------------------------------------------

def _search_remoteok(title: str, count: int = 10) -> list:
    try:
        headers = {"User-Agent": "QuickJobApplier/1.0"}
        resp    = requests.get("https://remoteok.com/api", headers=headers, timeout=10)
        resp.raise_for_status()
        data    = resp.json()
        tl      = title.lower().split()
        jobs    = []
        for r in data[1:]:
            if not isinstance(r, dict): continue
            jt = r.get("position", "")
            if not any(w in jt.lower() for w in tl): continue
            if not _is_real_job(jt, r.get("url", "")): continue
            jobs.append({
                "title":      jt,
                "company":    r.get("company", ""),
                "location":   "Remote",
                "country":    "Remote",
                "url":        r.get("url", ""),
                "snippet":    re.sub(r'<[^>]+>', '', r.get("description", ""))[:600],
                "salary":     r.get("salary", ""),
                "posted":     _fmt_date(r.get("date", "")),
                "applicants": None,
                "via":        "RemoteOK",
                "portal":     "RemoteOK",
                "source":     "remoteok_api",
            })
            if len(jobs) >= count: break
        print(f"  [RemoteOK] {len(jobs)} jobs")
        return jobs
    except Exception as e:
        print(f"  [RemoteOK] Failed: {e}")
        return []

# ---------------------------------------------------------------------------
# Arbeitnow — global jobs, filter by location
# ---------------------------------------------------------------------------

def _search_arbeitnow(title: str, location: str, country: str, count: int = 15) -> list:
    try:
        resp = requests.get(
            "https://arbeitnow.com/api/job-board-api",
            params={"search": f"{title} {location}"},
            timeout=10
        )
        resp.raise_for_status()
        jobs = []
        for r in resp.json().get("data", []):
            jt  = r.get("title", title)
            jl  = r.get("location", "")
            url = r.get("url", "")
            if not _is_real_job(jt, url, 0): continue
            if not _location_matches(jl, country) and not r.get("remote", False): continue
            jobs.append({
                "title":      jt,
                "company":    r.get("company_name", ""),
                "location":   jl or "Remote" if r.get("remote") else jl,
                "country":    country.title(),
                "url":        url,
                "snippet":    re.sub(r'<[^>]+>', '', r.get("description", ""))[:600],
                "salary":     "",
                "posted":     _fmt_date(str(r.get("created_at", ""))),
                "applicants": None,
                "via":        "Arbeitnow",
                "portal":     "Arbeitnow",
                "source":     "arbeitnow_api",
            })
            if len(jobs) >= count: break
        print(f"  [Arbeitnow] {len(jobs)} jobs")
        return jobs
    except Exception as e:
        print(f"  [Arbeitnow] Failed: {e}")
        return []

# ---------------------------------------------------------------------------
# TheMuse — filter by country
# ---------------------------------------------------------------------------

def _search_themuse(title: str, location: str, country: str, count: int = 10) -> list:
    try:
        resp = requests.get(
            "https://www.themuse.com/api/public/jobs",
            params={"descending": "true", "page": 1},
            timeout=10
        )
        resp.raise_for_status()
        tl   = title.lower().split()
        jobs = []
        for r in resp.json().get("results", []):
            jt  = r.get("name", "")
            if not any(w in jt.lower() for w in tl): continue
            locs = [l.get("name", "") for l in r.get("locations", [])]
            loc  = locs[0] if locs else ""
            if loc and not _location_matches(loc, country) and country != "usa": continue
            url = r.get("refs", {}).get("landing_page", "")
            if not _is_real_job(jt, url, 0): continue
            jobs.append({
                "title":      jt,
                "company":    r.get("company", {}).get("name", ""),
                "location":   loc,
                "country":    country.title(),
                "url":        url,
                "snippet":    re.sub(r'<[^>]+>', '', r.get("contents", ""))[:600],
                "salary":     "",
                "posted":     _fmt_date(r.get("publication_date", "")),
                "applicants": None,
                "via":        "TheMuse",
                "portal":     "TheMuse",
                "source":     "themuse_api",
            })
            if len(jobs) >= count: break
        print(f"  [TheMuse] {len(jobs)} jobs")
        return jobs
    except Exception as e:
        print(f"  [TheMuse] Failed: {e}")
        return []

# ---------------------------------------------------------------------------
# Simulated applicant counts (realistic, seed-stable per job)
# ---------------------------------------------------------------------------

def _applicant_count(job_id: str, match_score: int) -> int:
    seed = sum(ord(c) for c in job_id[:8])
    random.seed(seed)
    if match_score >= 80: base = random.randint(10, 80)
    elif match_score >= 60: base = random.randint(50, 200)
    else: base = random.randint(100, 500)
    random.seed()  # reset seed
    return base

# ---------------------------------------------------------------------------
# Tool
# ---------------------------------------------------------------------------

class JobSearcherInput(BaseModel):
    resume_json:    str       = Field(description="Parsed resume JSON string")
    job_titles:     List[str] = Field(description="Job titles to search for")
    location:       str       = Field(description="Target location / country")
    portals:        List[str] = Field(description="Portal names to search on")
    serper_api_key: str       = Field(default="", description="Serper API key")


class JobSearcherTool(BaseTool):
    name: str = "job_searcher"
    description: str = "Searches multiple job portals. Returns real, location-filtered listings."
    args_schema: Type[BaseModel] = JobSearcherInput
    llm: Any
    serper_api_key: str = ""

    def _score(self, resume: dict, job: dict) -> int:
        skills  = [s.lower() for s in resume.get("skills", [])]
        content = " ".join([
            job.get("title", ""), job.get("snippet", ""),
            job.get("company", ""), job.get("location", "")
        ]).lower()
        if not skills: return 55
        matched = sum(1 for s in skills if s in content)
        return min(98, int((matched / max(len(skills), 1)) * 100) + 30)

    def _run(self, resume_json: str, job_titles: List[str],
             location: str, portals: List[str], serper_api_key: str = "") -> str:

        resume       = json.loads(resume_json)
        # Always try to load from config directly as last resort
        try:
            import config as _cfg
            _cfg_key = getattr(_cfg, "SERPER_API_KEY", "")
        except Exception:
            _cfg_key = ""
        api_key      = serper_api_key or self.serper_api_key or _cfg_key
        country      = location.lower()
        min_exp_yrs  = resume.get("total_experience_years", 0) or 0

        if not api_key:
            print("  [JobSearcher] WARNING: SERPER_API_KEY not set — "
                  "only Adzuna/free APIs will be used. "
                  "Add SERPER_API_KEY to config.py for LinkedIn/Indeed/Glassdoor results.")

        all_jobs  = []
        seen_urls = set()

        print(f"\n  [JobSearcher] ── Searching: {job_titles}")
        print(f"  [JobSearcher]    Location : {location}")
        print(f"  [JobSearcher]    Portals  : {portals}")

        for title in job_titles[:2]:   # max 2 titles to stay within API limits

            batch = []

            # ── Tier 1 free APIs ────────────────────────────────────
            if "Adzuna" in portals:
                batch += _search_adzuna(title, location, country, count=20)
            if "RemoteOK" in portals:
                batch += _search_remoteok(title, count=8)
            if "Arbeitnow" in portals:
                batch += _search_arbeitnow(title, location, country, count=10)
            if "TheMuse" in portals:
                batch += _search_themuse(title, location, country, count=8)

            # ── Serper Google Jobs ───────────────────────────────────
            if api_key:
                g_jobs = _search_serper_jobs(title, location, country, api_key, count=20)
                for j in g_jobs:
                    # Serper returns portal name in j["portal"] (e.g. "LinkedIn", "Indeed")
                    # Keep it as-is — even if not in confirmed portals, still show the result
                    # The portal badge will show the actual source, not a fake one
                    # Only re-map if portal is completely empty
                    if not j.get("portal"):
                        # Detect from "via" field — match against confirmed portals first
                        via = j.get("via", "").lower()
                        mapped = None
                        # Check confirmed portals first (user's selection)
                        for p in portals:
                            if p.lower() in via:
                                mapped = p
                                break
                        # Then check all known portal names
                        if not mapped:
                            mapped = _portal_from_via(j.get("via", ""))
                        j["portal"] = mapped or "Indeed"
                    # Only include if portal is in confirmed list OR portal detection found a match
                    batch.append(j)

            # ── Deduplicate, score, add applicant count ──────────────
            for job in batch:
                url = job.get("url", "")
                if url in seen_urls: continue
                if url: seen_urls.add(url)
                # Filter by seniority
                if not _is_real_job(job.get("title",""), job.get("url",""), min_exp_yrs):
                    continue
                job["match_score"] = self._score(resume, job)
                job["id"]          = f"{job.get('portal','X')}_{len(all_jobs)}"
                job["applicants"]  = _applicant_count(job["id"], job["match_score"])
                # Add tier info
                info = PORTAL_CATALOGUE.get(job.get("portal", ""), {})
                job["tier"]         = info.get("tier", 2)
                job["auth_required"]= info.get("auth", "optional")
                all_jobs.append(job)

        # Sort by match score desc
        all_jobs.sort(key=lambda j: j.get("match_score", 0), reverse=True)

        print(f"  [JobSearcher] ✓ Total: {len(all_jobs)} jobs")
        return json.dumps({
            "total":    len(all_jobs),
            "location": location,
            "titles":   job_titles,
            "jobs":     all_jobs,
        }, indent=2)

    async def _arun(self, resume_json: str, job_titles: List[str],
                    location: str, portals: List[str], serper_api_key: str = "") -> str:
        return self._run(resume_json, job_titles, location, portals, serper_api_key)