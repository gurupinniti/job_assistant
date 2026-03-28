import json
from typing import Any
from langchain_core.messages import HumanMessage, SystemMessage, AIMessage
from langgraph.prebuilt import create_react_agent

from tools.resume_parser  import ResumeParserTool
from tools.job_identifier import JobIdentifierTool
from tools.job_searcher   import JobSearcherTool
from tools.jd_matcher     import JDMatcherTool
from tools.resume_builder import ResumeBuilderTool
from tools.job_applier    import JobApplierTool

# ---------------------------------------------------------------------------
# LLM factory
# ---------------------------------------------------------------------------

from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_openai import ChatOpenAI
from langchain_anthropic import ChatAnthropic
from langchain_groq import ChatGroq
from google.api_core.exceptions import ResourceExhausted
from openai import RateLimitError as OpenAIRateLimitError
from anthropic import RateLimitError as AnthropicRateLimitError
import sys, os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config
import gemini_models

WIDTH = 60

def log_fallback(frm: str, reason: str, to: str):
    print(f"\n{'!' * WIDTH}\n  [FALLBACK] {frm} → {to}\n  Reason: {reason}\n{'!' * WIDTH}")

def create_llm():
    """
    LLM fallback chain — order: Groq → OpenAI → Gemini → Claude
    Groq is free (100k tokens/day) and tried first.
    Paid providers are fallbacks only.
    """

    # ── 1. Groq llama-3.3-70b (free, primary) ────────────────────────────────
    print("  [1/4] Trying Groq (llama-3.3-70b-versatile)...")
    try:
        model = ChatGroq(model="llama-3.3-70b-versatile", api_key=config.GROQ_API_KEY, temperature=0.1)
        model.invoke([HumanMessage(content="hi")])
        print("  [OK] Groq llama-3.3-70b-versatile")
        return model
    except Exception as e:
        if "rate_limit_exceeded" in str(e) or "429" in str(e):
            log_fallback("Groq llama-3.3-70b", "Daily token limit (100k/day). Trying smaller model...", "Groq llama-3.1-8b")
        else:
            log_fallback("Groq llama-3.3-70b", str(e), "Groq llama-3.1-8b")

    # ── 1b. Groq llama-3.1-8b (free, smaller — separate quota) ───────────────
    print("  [1b/4] Trying Groq (llama-3.1-8b-instant)...")
    try:
        model = ChatGroq(model="llama-3.1-8b-instant", api_key=config.GROQ_API_KEY, temperature=0.1)
        model.invoke([HumanMessage(content="hi")])
        print("  [OK] Groq llama-3.1-8b-instant")
        return model
    except Exception as e:
        if "rate_limit_exceeded" in str(e) or "429" in str(e):
            log_fallback("Groq llama-3.1-8b", "Daily limit also reached. Falling back to paid providers.", "OpenAI")
        else:
            log_fallback("Groq llama-3.1-8b", str(e), "OpenAI")

    # ── 2. OpenAI gpt-3.5-turbo (paid fallback) ──────────────────────────────
    print("  [2/4] Trying OpenAI...")
    try:
        if getattr(config, "OPENAI_API_KEY", ""):
            model = ChatOpenAI(model="gpt-3.5-turbo", api_key=config.OPENAI_API_KEY, temperature=0.1)
            model.invoke([HumanMessage(content="hi")])
            print("  [OK] OpenAI gpt-3.5-turbo")
            return model
        else:
            print("  [SKIP] OpenAI — OPENAI_API_KEY not set")
    except OpenAIRateLimitError as e:
        log_fallback("OpenAI", str(e), "Gemini")
    except Exception as e:
        log_fallback("OpenAI", str(e), "Gemini")

    # ── 3. Gemini (paid/free fallback) ───────────────────────────────────────
    print("  [3/4] Trying Gemini...")
    try:
        if getattr(config, "GEMINI_API_KEY", ""):
            available  = gemini_models.get_gemini_models()
            model_name = gemini_models.select_gemini_model(available)
            model = ChatGoogleGenerativeAI(model=model_name, google_api_key=config.GEMINI_API_KEY, temperature=0.1)
            model.invoke([HumanMessage(content="hi")])
            print(f"  [OK] Gemini ({model_name})")
            return model
        else:
            print("  [SKIP] Gemini — GEMINI_API_KEY not set")
    except ResourceExhausted as e:
        log_fallback("Gemini", str(e), "Claude")
    except Exception as e:
        log_fallback("Gemini", str(e), "Claude")

    # ── 4. Claude (paid fallback) ─────────────────────────────────────────────
    print("  [4/4] Trying Claude...")
    try:
        if getattr(config, "CLAUDE_API_KEY", ""):
            model = ChatAnthropic(model="claude-3-5-sonnet-20241022", anthropic_api_key=config.CLAUDE_API_KEY, temperature=0.1)
            model.invoke([HumanMessage(content="hi")])
            print("  [OK] Claude claude-3-5-sonnet")
            return model
        else:
            print("  [SKIP] Claude — CLAUDE_API_KEY not set")
    except AnthropicRateLimitError as e:
        log_fallback("Claude", str(e), "none")
    except Exception as e:
        log_fallback("Claude", str(e), "none")

    raise RuntimeError(
        "All LLM providers exhausted.\n"
        "Primary: Groq free tier (100k tokens/day) — resets on a rolling 24h window.\n"
        "Options:\n"
        "  1. Wait for Groq quota to reset (check time in the error above)\n"
        "  2. Add OPENAI_API_KEY to config.py (paid)\n"
        "  3. Add GEMINI_API_KEY to config.py (free at aistudio.google.com)\n"
        "  4. Upgrade Groq at console.groq.com/settings/billing"
    )

# ---------------------------------------------------------------------------
# Singletons
# ---------------------------------------------------------------------------

_llm   = None
_agent = None

def get_llm():
    global _llm
    if _llm is None:
        _llm = create_llm()
    return _llm

def get_agent():
    global _agent
    if _agent is None:
        llm = get_llm()
        tools = [
            ResumeParserTool(llm=llm),
            JobIdentifierTool(llm=llm),
            JobSearcherTool(llm=llm, serper_api_key=getattr(config, 'SERPER_API_KEY', '')),
            JDMatcherTool(llm=llm),
            ResumeBuilderTool(llm=llm),
            JobApplierTool(),
        ]
        _agent = create_react_agent(model=llm, tools=tools)
    return _agent

# ---------------------------------------------------------------------------
# Pipeline Step A: Parse resume + identify portals (called on upload)
# ---------------------------------------------------------------------------

def parse_and_identify(resume_path: str, job_titles: list, country: str) -> dict:
    """
    Called by POST /upload-resume.
    Returns parsed resume + portal list for Step 1 UI confirmation.

    Rate-limit safe: if all LLMs are exhausted, resume parsing falls back to
    regex extraction and portal list falls back to country defaults.
    """
    from groq import RateLimitError as GroqRateLimitError

    print(f"\n{'=' * WIDTH}\n  PARSE & IDENTIFY\n{'=' * WIDTH}")

    # ── Step 1: Parse resume ─────────────────────────────────────────────────
    try:
        llm         = get_llm()
        resume_json = ResumeParserTool(llm=llm)._run(resume_path)
    except (GroqRateLimitError, RuntimeError) as rate_err:
        # All LLMs exhausted — use regex-only extraction (0 tokens)
        print(f"  [ParseAndIdentify] LLM unavailable ({rate_err.__class__.__name__}) — using regex fallback")
        resume_json = ResumeParserTool(llm=None)._run_regex_only(resume_path)
        llm         = None

    resume = json.loads(resume_json)

    # ── Step 1b: Immediately check title cache BEFORE calling JobIdentifier ──
    # This prevents any LLM call if same/similar resume was seen before.
    import memory_manager as mm
    cached_titles = mm.lookup_titles_cache(resume_json)
    if cached_titles:
        print(f"  [ParseAndIdentify] Title cache hit — skipping JobIdentifier LLM")
        # Still need portal list — get from country defaults (0 tokens)
        from tools.job_searcher import COUNTRY_PORTALS, PORTAL_CATALOGUE
        key     = country.lower().strip()
        portals = COUNTRY_PORTALS.get(key, COUNTRY_PORTALS["default"])
        job_info = {
            "country":            country,
            "portals":            [
                {
                    "name":        p,
                    "url":         PORTAL_CATALOGUE.get(p, {}).get("url", ""),
                    "easy_apply":  PORTAL_CATALOGUE.get(p, {}).get("easy_apply", False),
                    "restriction": PORTAL_CATALOGUE.get(p, {}).get("restriction"),
                    "tier":        PORTAL_CATALOGUE.get(p, {}).get("tier", 2),
                    "auth":        PORTAL_CATALOGUE.get(p, {}).get("auth", "optional"),
                    "description": PORTAL_CATALOGUE.get(p, {}).get("description", ""),
                }
                for p in portals
            ],
            "primary_titles":     job_titles or cached_titles["primary_titles"],
            "all_titles":         cached_titles["all_titles"],
            "search_variants":    cached_titles["primary_titles"],
            "keywords":           resume.get("skills", [])[:8],
            "seniority":          cached_titles["seniority"],
            "exp_years":          cached_titles["exp_years"],
            "title_source":       "cache",
        }
        return {"resume_json": resume_json, "resume": resume, "job_info": job_info}

    # ── Step 2: Identify portals + titles ────────────────────────────────────
    try:
        if llm is None:
            raise RuntimeError("LLM not available — using fallback portal list")
        job_info_json = JobIdentifierTool(llm=llm)._run(resume_json, job_titles, country)
        job_info      = json.loads(job_info_json)
    except Exception as e:
        # Fallback: build portal list from COUNTRY_PORTALS dict (0 tokens, always works)
        print(f"  [ParseAndIdentify] JobIdentifier failed ({e}) — using country defaults")
        from tools.job_searcher import COUNTRY_PORTALS, PORTAL_CATALOGUE
        key     = country.lower().strip()
        portals = COUNTRY_PORTALS.get(key, COUNTRY_PORTALS["default"])
        job_info = {
            "country":        country,
            "portals":        [
                {
                    "name":        p,
                    "url":         PORTAL_CATALOGUE.get(p, {}).get("url", ""),
                    "easy_apply":  PORTAL_CATALOGUE.get(p, {}).get("easy_apply", False),
                    "restriction": PORTAL_CATALOGUE.get(p, {}).get("restriction"),
                    "tier":        PORTAL_CATALOGUE.get(p, {}).get("tier", 2),
                    "auth":        PORTAL_CATALOGUE.get(p, {}).get("auth", "optional"),
                    "description": PORTAL_CATALOGUE.get(p, {}).get("description", ""),
                }
                for p in portals
            ],
            "primary_titles":  job_titles or [resume.get("experience", [{}])[0].get("title", "Professional")],
            "all_titles":      job_titles,
            "search_variants": job_titles,
            "keywords":        resume.get("skills", [])[:8],
            "seniority":       "mid",
            "exp_years":       resume.get("total_experience_years", 0),
            "title_source":    "fallback",
        }

    return {
        "resume_json": resume_json,
        "resume":      resume,
        "job_info":    job_info,
    }

# ---------------------------------------------------------------------------
# Pipeline Step B: Search jobs (called after portal confirmation)
# ---------------------------------------------------------------------------

def search_jobs(resume_json: str, job_titles: list, location: str, confirmed_portals: list) -> dict:
    """
    Called by POST /search-jobs.
    Check job search cache first — only hit APIs on true miss.
    Cache key: sorted titles + country + sorted portals (24h TTL).
    """
    import job_search_cache

    print(f"\n{'=' * WIDTH}\n  SEARCHING JOBS\n{'=' * WIDTH}")

    # ── 1. Exact cache hit ───────────────────────────────────────────────────
    cached = job_search_cache.lookup(job_titles, location, confirmed_portals)
    if cached:
        print(f"  [Search] Cache hit — {len(cached)} jobs served instantly")
        return {
            "total":     len(cached),
            "location":  location,
            "titles":    job_titles,
            "jobs":      cached,
            "from_cache": True,
        }

    # ── 2. Partial cache hit — filter from broader cached search ─────────────
    partial = job_search_cache.lookup_partial(job_titles, location, confirmed_portals)
    if partial and not partial["missing_titles"]:
        # All titles covered by cache — no API call needed
        jobs = partial["jobs"]
        print(f"  [Search] Partial cache hit — {len(jobs)} jobs, all titles covered")
        return {
            "total":     len(jobs),
            "location":  location,
            "titles":    job_titles,
            "jobs":      jobs,
            "from_cache": True,
        }

    # ── 3. Live search — cache miss or new titles ────────────────────────────
    try:
        llm = get_llm()
    except Exception as e:
        # If all LLMs exhausted, still try search (scoring is keyword-based, not LLM)
        print(f"  [Search] LLM unavailable ({e}) — proceeding with keyword scoring")
        llm = None

    searcher     = JobSearcherTool(llm=llm, serper_api_key=getattr(config, 'SERPER_API_KEY', ''))
    results_json = searcher._run(resume_json, job_titles, location, confirmed_portals)
    results      = json.loads(results_json)

    # Filter jobs to only those whose portal matches confirmed_portals
    confirmed_portals_set = set([p.lower() for p in confirmed_portals])
    filtered_jobs = [j for j in results.get("jobs", []) if j.get("portal", "").lower() in confirmed_portals_set]
    results["jobs"] = filtered_jobs

    # Store in cache for next time
    if filtered_jobs:
        job_search_cache.store(job_titles, location, confirmed_portals, filtered_jobs)

    results["from_cache"] = False
    return results

# ---------------------------------------------------------------------------
# Pipeline Step C: Apply to selected jobs
# ---------------------------------------------------------------------------

def apply_to_jobs(resume_json: str, selected_jobs: list, original_filename: str = "resume", original_pdf_path: str = "", previews: dict = None) -> dict:
    """
    Called by POST /apply-jobs.
    Applies to each user-selected job: match JD → build docs → apply.
    Returns per-job status.
    """
    llm     = get_llm()
    resume  = json.loads(resume_json)
    matcher = JDMatcherTool(llm=llm)
    builder = ResumeBuilderTool(llm=llm)
    applier = JobApplierTool()

    results = []

    for job in selected_jobs:
        job_id      = job.get("id", "unknown")
        portal      = job.get("portal", "")
        job_title   = job.get("title", "")
        company     = job.get("company", portal)
        job_url     = job.get("url", "")
        jd_text     = job.get("snippet", f"{job_title} at {company}")

        print(f"\n{'=' * WIDTH}\n  APPLYING: {job_title} @ {company} [{portal}]\n{'=' * WIDTH}")

        job_result = {
            "id":      job_id,
            "title":   job_title,
            "company": company,
            "portal":  portal,
            "url":     job_url,
            "status":  "pending",
        }

        try:
            # ── Use pre-generated preview if available (saves LLM tokens) ──
            if job_id in previews:
                print(f"  [ApplyPipeline] Reusing preview docs for {job_title} @ {company}")
                p = previews[job_id]
                job_result["resume_path"] = p.get("resume_path", "")
                job_result["cover_path"]  = p.get("cover_letter_path", "")
            else:
                # Match resume to JD
                match_json   = matcher._run(resume_json, jd_text, job_title)
                match        = json.loads(match_json)
                job_result["match_score"] = match.get("match_score")
                job_result["verdict"]     = match.get("verdict")

                if not match.get("recommended_to_apply", True) and match.get("match_score", 100) < 30:
                    job_result["status"]  = "skipped"
                    job_result["message"] = f"Low match score ({match.get('match_score')}%) — skipped"
                    results.append(job_result)
                    continue

                # Build tailored resume + cover letter
                build_json = builder._run(
                    resume_json         = resume_json,
                    match_json          = match_json,
                    job_title           = job_title,
                    company_name        = company,
                    job_description     = jd_text,
                    original_file_name  = original_filename,
                    original_pdf_path   = original_pdf_path,
                )
                build = json.loads(build_json)
                job_result["resume_path"] = build.get("resume_path")
                job_result["cover_path"]  = build.get("cover_letter_path")

            # Apply via Playwright — use job_result paths set above
            resume_path_for_apply = job_result.get("resume_path", "")
            cover_path_for_apply  = job_result.get("cover_path", "")
            apply_json   = applier._run(
                portal             = portal,
                job_url            = job_url,
                resume_path        = resume_path_for_apply,
                cover_letter_path  = cover_path_for_apply,
                resume_json        = resume_json,
            )
            apply_result = json.loads(apply_json)

            job_result["status"]     = apply_result.get("status")
            job_result["message"]    = apply_result.get("message") or apply_result.get("reason")
            job_result["screenshot"] = apply_result.get("screenshot")

        except Exception as e:
            job_result["status"]  = "error"
            job_result["message"] = str(e)

        results.append(job_result)

    return {
        "total":    len(results),
        "success":  sum(1 for r in results if r["status"] == "success"),
        "partial":  sum(1 for r in results if r["status"] == "partial"),
        "skipped":  sum(1 for r in results if r["status"] == "skipped"),
        "error":    sum(1 for r in results if r["status"] == "error"),
        "jobs":     results,
    }