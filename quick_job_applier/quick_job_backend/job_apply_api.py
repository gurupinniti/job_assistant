import json
import uuid
import shutil
import traceback
import config
from pathlib import Path
from typing import List, Optional
from contextlib import asynccontextmanager

from fastapi import FastAPI, File, Form, UploadFile, HTTPException, BackgroundTasks, Body
from fastapi.responses import FileResponse, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel

from agent import get_llm, parse_and_identify, search_jobs, apply_to_jobs
from tools.job_identifier import COUNTRY_PORTALS, PORTAL_INFO
from tools.jd_matcher import JDMatcherTool
from tools.resume_builder import ResumeBuilderTool
import resume_cache
import memory_manager

UPLOAD_DIR = Path("uploads").resolve()   # absolute path — safe regardless of cwd
UPLOAD_DIR.mkdir(exist_ok=True)

# ---------------------------------------------------------------------------
# Job titles catalogue
# ---------------------------------------------------------------------------

JOB_TITLES = sorted([
    "Software Engineer", "Senior Software Engineer", "Full Stack Developer",
    "Frontend Developer", "Backend Developer", "DevOps Engineer",
    "Data Engineer", "Data Scientist", "Machine Learning Engineer",
    "AI Engineer", "Cloud Architect", "Site Reliability Engineer",
    "Mobile Developer", "iOS Developer", "Android Developer",
    "Product Manager", "Engineering Manager", "CTO",
    "Financial Analyst", "Investment Banker", "Risk Analyst",
    "Accountant", "CFO", "Auditor",
    "Digital Marketing Manager", "SEO Specialist", "Content Strategist",
    "Brand Manager", "Social Media Manager",
    "HR Manager", "Talent Acquisition", "People Operations",
    "Project Manager", "Business Analyst", "Operations Manager",
    "Sales Manager", "Customer Success Manager", "UX Designer",
    "Nurse", "Doctor", "Pharmacist", "Healthcare Administrator",
])

# ---------------------------------------------------------------------------
# Session store
# ---------------------------------------------------------------------------

sessions: dict = {}

# ---------------------------------------------------------------------------
# Lifespan
# ---------------------------------------------------------------------------

@asynccontextmanager
async def lifespan(app: FastAPI):
    print("[Startup] Initialising QuickJob Agent...")
    get_llm()
    cache_info = resume_cache.stats()
    print(f"[Startup] Resume cache: {cache_info['status']} — {cache_info.get('count', 0)} entries")
    llm_instance = get_llm()
    resume_cache.init_cache(llm_instance)   # resume cache embeddings
    import llm_cache
    llm_cache.init(llm_instance)            # LLM response cache
    memory_manager.init_title_cache(llm_instance)  # job title cache
    import job_search_cache
    cleaned = job_search_cache.clear_stale()
    if cleaned:
        print(f"  [Startup] Cleared {cleaned} stale job cache entries")
    print(f"[Startup] Memory loaded: system_prompts, taxonomy, ats_rules, cover_templates")

    # ── API key audit ─────────────────────────────────────────────────────────
    key_status = []
    for key_name in ["SERPER_API_KEY", "ADZUNA_APP_ID", "GEMINI_API_KEY"]:
        val = getattr(config, key_name, "")
        status = "✓" if val else "✗ MISSING"
        key_status.append(f"{key_name}: {status}")
    print(f"[Startup] API keys: {' | '.join(key_status)}")
    if not getattr(config, "SERPER_API_KEY", ""):
        print("[Startup] ⚠  SERPER_API_KEY missing — job search will only return Adzuna results.")
        print("[Startup]    Get a free key at https://serper.dev (2500 searches/month free)")
    print("[Startup] LLM order: Groq (free) → OpenAI → Gemini → Claude")
    print("[Startup] Ready.")
    yield
    print("[Shutdown] Stopped.")

# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------

app = FastAPI(
    title="QuickJob Applier API",
    description="AI-powered job application agent.",
    version="2.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------

class PortalConfirmation(BaseModel):
    session_id:           str
    confirmed_portals:    List[str]
    confirmed_job_titles: List[str] = []   # user's final title selection from Step 1

class JobSelection(BaseModel):
    session_id:    str
    selected_jobs: List[dict]

class ApplyRequest(BaseModel):
    session_id: str

class PreviewRequest(BaseModel):
    session_id: str
    job:        dict

# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@app.get("/", summary="Health check")
def root():
    return {"status": "ok", "message": "QuickJob Applier API v2.1 is running."}

@app.get("/job-titles")
def get_job_titles():
    """Static fallback titles — used before resume is uploaded."""
    return {"job_titles": JOB_TITLES}


@app.post("/resume-job-titles", summary="Get job titles dynamically from uploaded resume")
async def resume_job_titles(
    resume:  UploadFile = File(...),
    country: str        = Form(default="singapore"),
):
    """
    Parse a resume and return suggested job titles based on its content.
    Uses: title cache → taxonomy → LLM (in that order).
    This endpoint is called right after resume upload for dynamic title suggestions.
    """
    import tempfile, shutil
    tmp = tempfile.NamedTemporaryFile(suffix=".pdf", delete=False)
    try:
        shutil.copyfileobj(resume.file, tmp)
        tmp.close()

        from tools.resume_parser import ResumeParserTool
        llm         = get_llm()
        resume_json = ResumeParserTool(llm=llm)._run(tmp.name)

        # Check title cache first
        cached = memory_manager.lookup_titles_cache(resume_json)
        if cached:
            return {
                "titles":    cached["all_titles"],
                "primary":   cached["primary_titles"],
                "seniority": cached["seniority"],
                "source":    "cache",
                "exp_years": cached["exp_years"],
            }

        # Try taxonomy
        taxonomy = memory_manager.resolve_job_titles_from_taxonomy(resume_json)
        if taxonomy:
            memory_manager.store_titles_cache(resume_json, taxonomy)
            return {
                "titles":    taxonomy["all_titles"],
                "primary":   taxonomy["primary_titles"],
                "seniority": taxonomy["seniority"],
                "source":    "taxonomy",
                "exp_years": taxonomy["exp_years"],
            }

        # LLM fallback (cached)
        from tools.job_identifier import JobIdentifierTool
        result_json = JobIdentifierTool(llm=llm)._run(resume_json, [], country)
        result      = json.loads(result_json)
        return {
            "titles":    result.get("all_titles", result.get("primary_titles", [])),
            "primary":   result.get("primary_titles", []),
            "seniority": result.get("seniority", "mid"),
            "source":    result.get("title_source", "llm"),
            "exp_years": result.get("exp_years", 0),
        }
    except Exception as e:
        print(f"[resume-job-titles] {e}")
        return {"titles": JOB_TITLES[:20], "primary": [], "seniority": "mid", "source": "fallback"}
    finally:
        import os
        try: os.unlink(tmp.name)
        except Exception: pass

@app.get("/countries")
def get_countries():
    result = {}
    for country, portals in COUNTRY_PORTALS.items():
        if country == "default":
            continue
        result[country.title()] = [
            {
                "name":        p,
                "url":         PORTAL_INFO.get(p, {}).get("url", ""),
                "easy_apply":  PORTAL_INFO.get(p, {}).get("easy_apply", False),
                "restriction": PORTAL_INFO.get(p, {}).get("restriction"),
            }
            for p in portals
        ]
    return result

@app.get("/session-check/{session_id}", summary="Check if session exists")
def session_check(session_id: str):
    session = sessions.get(session_id)
    if not session:
        return {"exists": False, "active_sessions": list(sessions.keys())}
    return {
        "exists":    True,
        "session_id": session_id,
        "status":     session.get("status"),
        "candidate":  session.get("resume_data", {}).get("name"),
    }


@app.get("/cache-stats", summary="Cache statistics")
def cache_stats():
    import llm_cache
    import job_search_cache
    return {
        "resume_cache": resume_cache.stats(),
        "llm_cache":    llm_cache.stats(),
        "job_cache":    job_search_cache.stats(),
    }

# ── STEP 1 ─────────────────────────────────────────────────────────────────

@app.post("/upload-resume")
async def upload_resume(
    resume:              UploadFile = File(...),
    job_titles:          str        = Form(...),
    country:             str        = Form(...),
    selected_portals:    str        = Form(default=""),   # comma-separated portals from Step 1
):
    if not resume.filename.lower().endswith(".pdf"):
        raise HTTPException(400, "Only PDF files are supported.")

    session_id  = str(uuid.uuid4())[:8]
    resume_path = UPLOAD_DIR / f"{session_id}_{resume.filename}"
    with open(resume_path, "wb") as f:
        shutil.copyfileobj(resume.file, f)

    titles = [t.strip() for t in job_titles.split(",") if t.strip()]

    try:
        parsed = parse_and_identify(str(resume_path), titles, country)
    except Exception as e:
        raise HTTPException(500, f"Resume parsing failed: {str(e)}\n{traceback.format_exc()}")

    resume_data = parsed["resume"]
    job_info    = parsed["job_info"]
    all_portals = job_info.get("portals", [])

    # Filter to only the portals the user pre-selected in Step 1
    user_portals = [p.strip() for p in selected_portals.split(",") if p.strip()]
    if user_portals:
        portal_list = [p for p in all_portals if p["name"] in user_portals]
        # If none matched (edge case), fall back to all
        if not portal_list:
            portal_list = all_portals
    else:
        portal_list = all_portals

    # IMPORTANT: store the user's own selected titles as the canonical list.
    # AI-suggested titles (primary_titles) are returned to the UI for display only
    # and are NEVER allowed to override what the user explicitly chose.
    sessions[session_id] = {
        "resume_path":           str(resume_path),
        "resume_json":           parsed["resume_json"],
        "resume_data":           resume_data,
        "original_filename":     Path(resume.filename).stem,
        "job_titles":            titles,              # user's selection — never overridden
        "ai_suggested_titles":   job_info.get("primary_titles", []),  # for display only
        "country":               country,
        "portals":               portal_list,
        "status":                "awaiting_portal_confirmation",
        "previews":              {},
    }

    return {
        "session_id":          session_id,
        "candidate":           resume_data.get("name"),
        "skills_found":        resume_data.get("skills", [])[:10],
        "experience":          resume_data.get("total_experience_years"),
        "job_titles":          titles,                             # user's confirmed selection
        "ai_suggested_titles": job_info.get("primary_titles", []),  # suggestions shown in UI
        "keywords":            job_info.get("keywords", []),
        "seniority":           job_info.get("seniority"),
        "country":             country,
        "portals":             portal_list,
    }

# ── STEP 2 ─────────────────────────────────────────────────────────────────

@app.post("/search-jobs")
async def search_jobs_endpoint(
    confirmation:     PortalConfirmation,
    background_tasks: BackgroundTasks,
):
    session = sessions.get(confirmation.session_id)
    if not session:
        raise HTTPException(404, "Session not found.")
    if not confirmation.confirmed_portals:
        raise HTTPException(400, "Select at least one portal.")

    session["confirmed_portals"] = confirmation.confirmed_portals
    session["status"]            = "searching"
    session["job_listings"]      = []

    def do_search():
        try:
            # Use the user's final confirmed titles if sent, otherwise session titles
            titles_to_search = (
                confirmation.confirmed_job_titles
                if confirmation.confirmed_job_titles
                else session["job_titles"]
            )
            # Save the confirmed titles back to session for any future reference
            session["job_titles"] = titles_to_search
            print(f"  [Search] Using job titles: {titles_to_search}")

            results = search_jobs(
                resume_json       = session["resume_json"],
                job_titles        = titles_to_search,
                location          = session["country"],
                confirmed_portals = confirmation.confirmed_portals,
            )
            session["job_listings"] = results.get("jobs", [])
            session["status"]       = "awaiting_job_selection"
        except Exception as e:
            session["status"] = "error"
            session["error"]  = str(e)
            print(f"[search error] {traceback.format_exc()}")

    background_tasks.add_task(do_search)
    return {"session_id": confirmation.session_id, "status": "searching"}

@app.get("/search-status/{session_id}")
def search_status(session_id: str):
    session = sessions.get(session_id)
    if not session:
        raise HTTPException(404, "Session not found.")
    response = {"session_id": session_id, "status": session["status"]}
    if session["status"] == "awaiting_job_selection":
        response["jobs"]  = session.get("job_listings", [])
        response["total"] = len(session.get("job_listings", []))
    if session["status"] == "error":
        response["error"] = session.get("error")
    return response

# ── STEP 3 ─────────────────────────────────────────────────────────────────

@app.post("/select-jobs")
def select_jobs(selection: JobSelection):
    session = sessions.get(selection.session_id)
    if not session:
        raise HTTPException(404, "Session not found.")
    if not selection.selected_jobs:
        raise HTTPException(400, "Select at least one job.")
    session["selected_jobs"] = selection.selected_jobs
    session["status"]        = "jobs_selected"
    return {
        "session_id":     selection.session_id,
        "selected_count": len(selection.selected_jobs),
    }

# ── PREVIEW (between step 3 and 4) ─────────────────────────────────────────

@app.post("/preview-resume", summary="Preview tailored resume for a job (uses cache)")
async def preview_resume(request: PreviewRequest):
    """
    Generate tailored resume + cover letter for a job.
    Checks ChromaDB cache first — reuses if ≥92% similar to avoid LLM token usage.
    """
    print(f"  [Preview] session_id received: '{request.session_id}'")
    print(f"  [Preview] active sessions: {list(sessions.keys())}")
    session = sessions.get(request.session_id)
    if not session:
        raise HTTPException(404, f"Session '{request.session_id}' not found. Active sessions: {list(sessions.keys())}")

    job       = request.job
    job_title = job.get("title", "Unknown Role")
    company   = job.get("company") or job.get("portal", "Company")
    jd_text   = job.get("snippet", "") or f"{job_title} role at {company}"
    job_id    = job.get("id", job_title)

    try:
        # ── 1. Check cache ────────────────────────────────────────────────
        cached = resume_cache.lookup(
            resume_json = session["resume_json"],
            job_title   = job_title,
            company     = company,
            jd_text     = jd_text,
        )
        if cached:
            print(f"  [Preview] Cache hit for '{job_title}' @ {company}")
            session["previews"][job_id] = {
                "resume_path":       cached.get("resume_path", ""),
                "cover_letter_path": cached.get("cover_path", ""),
            }
            cached["from_cache"] = True
            # Ensure session-level data is attached for PDF serving
            session["previews"][job_id] = {
                "resume_path":       cached.get("resume_path", ""),
                "cover_letter_path": cached.get("cover_path", ""),
            }
            return cached

        # ── 2. Generate fresh ─────────────────────────────────────────────
        print(f"  [Preview] Generating for '{job_title}' @ {company}")
        llm     = get_llm()
        matcher = JDMatcherTool(llm=llm)

        match_json_str = matcher._run(session["resume_json"], jd_text, job_title)
        match          = json.loads(match_json_str)

        # Use the new ResumeEnhancer — preserves original PDF format
        from tools.resume_enhancer import enhance_resume
        result = enhance_resume(
            llm                = llm,
            resume_json        = session["resume_json"],
            match_json         = match_json_str,
            job_title          = job_title,
            company_name       = company,
            job_description    = jd_text,
            original_pdf_path  = session.get("resume_path", ""),
            original_file_name = session.get("original_filename", "resume"),
        )

        if result.get("status") != "success":
            raise ValueError(f"Enhancement failed: {result}")

        # ── 3. Read text previews ─────────────────────────────────────────
        resume_text = _read_file(Path(result.get("resume_txt_path", "")))
        cover_text  = result.get("cover_text", "") or _read_file(Path(result.get("cover_txt_path", "")))

        # ── 4. Cache it ───────────────────────────────────────────────────
        resume_cache.store(
            resume_json  = session["resume_json"],
            job_title    = job_title,
            company      = company,
            jd_text      = jd_text,
            build        = {
                "resume_path":       result["resume_path"],
                "cover_letter_path": result["cover_letter_path"],
                "resume_txt_path":   result.get("resume_txt_path", ""),
                "cover_txt_path":    result.get("cover_txt_path", ""),
                "output_folder":     result.get("output_folder", ""),
                "ats_score":         result["ats_score"],
            },
            match        = match,
            study_plan   = result.get("study_plan"),
            edit_summary = result.get("edit_summary"),
        )

        # ── 5. Store in session ───────────────────────────────────────────
        session["previews"][job_id] = {
            "resume_path":       result["resume_path"],
            "cover_letter_path": result["cover_letter_path"],
        }

        return {
            "from_cache":     False,
            "match_score":    match.get("match_score"),
            "verdict":        match.get("verdict"),
            "matched_skills": match.get("matched_skills", []),
            "missing_skills": match.get("missing_skills", []),
            "resume_text":    resume_text,
            "cover_text":     cover_text,
            "resume_path":    result["resume_path"],
            "cover_path":     result["cover_letter_path"],
            "ats_score":      result.get("ats_score", 0),
            "ats_details":    result.get("ats_details", {}),
            "study_plan":     result.get("study_plan", {}),
            "edit_summary":   result.get("edit_summary", {}),
            "rewritten":      result.get("rewritten", {}),
        }

    except Exception as e:
        print(f"[preview error] {traceback.format_exc()}")
        # ── Graceful fallback: serve original PDF + generate cover letter without LLM ──
        try:
            print(f"  [Preview] LLM failed — falling back to original resume PDF")
            original_path = session.get("resume_path", "")
            resume_data   = session.get("resume_data", {})
            name          = resume_data.get("name", "Candidate")
            skills        = ", ".join(resume_data.get("skills", [])[:8])
            exp           = resume_data.get("total_experience_years", 0)

            # ── Generate cover letter PDF without LLM (PyMuPDF only) ──────────
            cover_text = (
                f"Dear Hiring Manager,\n\n"
                f"I am {name}, a professional with {exp} years of experience, "
                f"applying for the {job_title} position at {company}.\n\n"
                f"My key skills include: {skills}.\n\n"
                f"I would welcome the opportunity to discuss how my background "
                f"aligns with your requirements.\n\n"
                f"Best regards,\n{name}"
            )

            # Save cover letter as a real PDF so the iframe can render it
            from pathlib import Path as _Path
            import fitz
            cover_folder = _Path(original_path).parent if original_path else _Path("job_apply_output")
            cover_folder.mkdir(parents=True, exist_ok=True)
            cover_pdf_path = cover_folder / f"CoverLetter_fallback_{job_id[:12]}.pdf"

            if not cover_pdf_path.exists():
                doc  = fitz.open()
                page = doc.new_page(width=595, height=842)
                L, y = 50, 60
                page.insert_text((L, y), f"{job_title} — Cover Letter",
                                  fontsize=13, color=(0.36,0.31,0.91), fontname="helv")
                page.insert_text((L, y+18), company,
                                  fontsize=9, color=(0.5,0.5,0.5), fontname="helv")
                page.draw_line((L, y+30), (545, y+30), color=(0.36,0.31,0.91), width=0.5)
                y += 46
                for para in cover_text.split("\n\n"):
                    para = para.strip()
                    if not para: continue
                    words, line_buf = para.split(), ""
                    for w in words:
                        if len(line_buf + w) > 90:
                            safe = line_buf.rstrip().encode("latin-1","replace").decode("latin-1")
                            page.insert_text((L, y), safe, fontsize=10,
                                              color=(0.1,0.1,0.1), fontname="helv")
                            y += 14; line_buf = w + " "
                            if y > 800: break
                        else: line_buf += w + " "
                    if line_buf.strip() and y < 800:
                        safe = line_buf.rstrip().encode("latin-1","replace").decode("latin-1")
                        page.insert_text((L, y), safe, fontsize=10,
                                          color=(0.1,0.1,0.1), fontname="helv")
                        y += 14
                    y += 8
                doc.save(str(cover_pdf_path))
                doc.close()

            # ── Store paths so /preview-resume-pdf serves the right files ────
            session["previews"][job_id] = {
                "resume_path":       original_path,          # original PDF → renders perfectly
                "cover_letter_path": str(cover_pdf_path),   # real PDF cover letter
            }

            return {
                "from_cache":            False,
                "llm_failed":            True,
                "llm_error":             str(e),
                "fallback_used":         True,
                "match_score":           None,
                "verdict":               "Using original resume — AI enhancement unavailable",
                "matched_skills":        resume_data.get("skills", [])[:6],
                "missing_skills":        [],
                "resume_text":           "",       # empty — PDF iframe used instead
                "cover_text":            cover_text,
                "resume_path":           original_path,
                "cover_path":            str(cover_pdf_path),
                "ats_score":             None,
                "ats_details":           {},
                "study_plan":            {},
                "edit_summary":          {},
                "rewritten":             {},
                "requires_confirmation": True,
            }
        except Exception as fallback_err:
            print(f"[preview fallback error] {fallback_err}")
            raise HTTPException(500, f"Preview failed: {str(e)}")


@app.post("/study-plan", summary="Generate or regenerate study plan for a job")
async def get_study_plan(request: dict = Body(...)):
    """
    Generate a study plan for a specific job.
    Called when the Study Plan tab is empty in the preview modal.
    Checks llm_cache first — only calls LLM on true miss.
    """
    session_id = request.get("session_id", "")
    job        = request.get("job", {})

    session = sessions.get(session_id)
    if not session:
        raise HTTPException(404, "Session not found — please re-upload your resume.")

    job_title = job.get("title", "")
    company   = job.get("company") or job.get("portal", "Company")
    jd_text   = job.get("snippet", "") or f"{job_title} role at {company}"

    try:
        resume_data = session.get("resume_data", {})
        resume_json = session.get("resume_json", "{}")

        # Build a minimal match dict from resume skills vs JD keywords
        resume_skills = [s.lower() for s in resume_data.get("skills", [])]
        jd_lower      = jd_text.lower()
        matched = [s for s in resume_data.get("skills", []) if s.lower() in jd_lower]
        missing = []  # will be enriched by LLM if available

        match = {
            "matched_skills": matched[:10],
            "missing_skills": missing,
        }

        llm    = get_llm()
        resume = json.loads(resume_json)

        from tools.resume_enhancer import _study_plan
        plan = _study_plan(llm, job_title, company, jd_text, match, resume)

        # Update cached preview if it exists
        job_id   = job.get("id", job_title)
        previews = session.get("previews", {})
        if job_id in previews:
            # Update study_plan in resume cache
            pass  # cache update handled next preview call

        return {"study_plan": plan, "from_cache": False}

    except Exception as e:
        print(f"[study-plan] {e} — using LLM-free fallback")
        # Build a complete study plan from structured data — zero LLM tokens
        try:
            from tools.resume_enhancer import _build_fallback_study_plan, _fetch_company_overview_serper
            resume_data = session.get("resume_data", {})
            resume_json = session.get("resume_json", "{}")
            resume      = json.loads(resume_json)
            jd_lower    = jd_text.lower()
            matched     = [s for s in resume_data.get("skills", []) if s.lower() in jd_lower]
            all_skills  = resume_data.get("skills", [])
            missing     = [s for s in all_skills if s not in matched][:8]
            match       = {"matched_skills": matched[:10], "missing_skills": missing}
            plan        = _build_fallback_study_plan(job_title, company, jd_text, match, resume)
            # Enrich company overview via Serper web search (0 LLM tokens)
            company_ctx = _fetch_company_overview_serper(company, job_title)
            if company_ctx and len(company_ctx) > 30:
                plan["company_overview"] = company_ctx
        except Exception as fe:
            print(f"[study-plan fallback error] {fe}")
            plan = {
                "study_plan": [
                    {"rank": 1, "topic": f"Core skills for {job_title}",
                     "why": "Required for this role", "resources": ["Coursera", "YouTube"],
                     "priority": "high"}
                ],
                "company_overview": f"{company} is hiring for {job_title}.",
                "industry": "", "company_size": "",
                "role_highlights": [f"{job_title} at {company}"],
                "missing_skills_to_learn": [],
            }
        return {"study_plan": plan, "from_cache": False, "error": str(e)}


def _read_file(path: Path) -> str:
    """Safely read a file as text, trying utf-8 then latin-1."""
    try:
        if path.exists():
            try:
                return path.read_text(encoding="utf-8")
            except Exception:
                return path.read_bytes().decode("latin-1", errors="replace")
    except Exception as e:
        print(f"  [_read_file] Could not read {path}: {e}")
    return ""

# ── STEP 4 ─────────────────────────────────────────────────────────────────

@app.post("/apply")
async def apply(request: ApplyRequest, background_tasks: BackgroundTasks):
    session = sessions.get(request.session_id)
    if not session:
        raise HTTPException(404, "Session not found.")
    if not session.get("selected_jobs"):
        raise HTTPException(400, "No jobs selected.")

    session["status"]       = "applying"
    session["apply_result"] = None
    session["job_statuses"] = {
        j.get("id", j.get("title", str(i))): "pending"
        for i, j in enumerate(session["selected_jobs"])
    }

    def do_apply():
        try:
            result = apply_to_jobs(
                resume_json       = session["resume_json"],
                selected_jobs     = session["selected_jobs"],
                original_filename = session.get("original_filename", "resume"),
                original_pdf_path = session.get("resume_path", ""),
                previews          = session.get("previews", {}),
            )
            session["apply_result"] = result
            session["status"]       = "completed"
            for job in result.get("jobs", []):
                key = job.get("id", job.get("title"))
                session["job_statuses"][key] = job.get("status", "unknown")
        except Exception as e:
            session["status"] = "error"
            session["error"]  = str(e)
            print(f"[apply error] {traceback.format_exc()}")

    background_tasks.add_task(do_apply)
    return {"session_id": request.session_id, "status": "applying"}

@app.get("/apply-status/{session_id}")
def apply_status(session_id: str):
    session = sessions.get(session_id)
    if not session:
        raise HTTPException(404, "Session not found.")
    response = {
        "session_id":   session_id,
        "status":       session["status"],
        "job_statuses": session.get("job_statuses", {}),
    }
    if session["status"] == "completed":
        result = session.get("apply_result", {})
        response["summary"] = {k: result.get(k) for k in ["total","success","partial","skipped","error"]}
        response["jobs"]    = result.get("jobs", [])
    if session["status"] == "error":
        response["error"] = session.get("error")
    return response

@app.get("/download/{session_id}/{job_id}/{file_type}")
def download_file(session_id: str, job_id: str, file_type: str):
    session = sessions.get(session_id)
    if not session:
        raise HTTPException(404, "Session not found.")

    # Check previews first (user may not have applied yet)
    previews = session.get("previews", {})
    if job_id in previews:
        p    = previews[job_id]
        path = Path(p["resume_path"] if file_type == "resume" else p["cover_letter_path"])
        if path.exists():
            return FileResponse(str(path), filename=path.name)

    # Then check apply results
    if session.get("apply_result"):
        for job in session["apply_result"].get("jobs", []):
            if str(job.get("id")) == job_id or job.get("title") == job_id:
                path_str = job.get("resume_path") if file_type == "resume" else job.get("cover_path")
                if path_str:
                    path = Path(path_str)
                    if path.exists():
                        return FileResponse(str(path), filename=path.name)

    raise HTTPException(404, "File not found. Generate a preview first.")


# ── Serve tailored resume PDF for preview ──────────────────────────────────

@app.get("/preview-resume-pdf/{session_id}/{job_id}", summary="Serve tailored resume PDF inline")
def serve_tailored_pdf(session_id: str, job_id: str, doc: str = "resume"):
    """Serve the tailored resume or cover letter PDF for inline browser display."""
    session = sessions.get(session_id)
    if not session:
        raise HTTPException(404, "Session not found.")

    previews = session.get("previews", {})
    if job_id not in previews:
        raise HTTPException(404, "Preview not generated yet. Call POST /preview-resume first.")

    p        = previews[job_id]
    raw_path = p["resume_path"] if doc == "resume" else p.get("cover_letter_path", p["resume_path"])

    # Resolve to absolute — handles cases where backend was started from a different cwd
    path = None
    for candidate in [
        Path(raw_path),
        Path(raw_path).resolve(),
        Path(__file__).parent / raw_path,
    ]:
        if candidate.exists():
            path = candidate
            break

    if path is None:
        raise HTTPException(404, f"Preview file not found. Try regenerating the preview.")

    # Verify it's a valid PDF (starts with %PDF)
    with open(path, "rb") as f:
        header = f.read(4)
    if header != b"%PDF":
        # File exists but is text — serve the .txt file instead
        txt_path = path.with_suffix(".txt")
        if txt_path.exists():
            return FileResponse(str(txt_path), media_type="text/plain")
        raise HTTPException(422, "Generated file is not a valid PDF. Try regenerating.")

    return FileResponse(
        str(path),
        media_type="application/pdf",
        headers={"Content-Disposition": "inline; filename=" + path.name},
    )


# ── Resume preview (original PDF) ──────────────────────────────────────────

@app.get("/resume-pdf/{session_id}", summary="Serve original uploaded resume PDF")
def serve_resume_pdf(session_id: str):
    """Serve the original uploaded PDF for inline browser preview."""
    session = sessions.get(session_id)
    if not session:
        print(f"  [resume-pdf] Session not found: {session_id}")
        print(f"  [resume-pdf] Active sessions: {list(sessions.keys())}")
        raise HTTPException(404, "Session not found. The backend may have restarted — please re-upload your resume.")

    raw_path = session.get("resume_path", "")
    # Try as-is, then as absolute, then relative to backend dir
    for candidate in [
        Path(raw_path),
        Path(raw_path).resolve(),
        Path(__file__).parent / raw_path,
        UPLOAD_DIR / Path(raw_path).name,
    ]:
        if candidate.exists():
            print(f"  [resume-pdf] Serving: {candidate}")
            return FileResponse(
                str(candidate),
                media_type="application/pdf",
                headers={"Content-Disposition": "inline"},
            )

    print(f"  [resume-pdf] File not found at any path. raw={raw_path}")
    raise HTTPException(404, f"Resume file not found. It may have been deleted.")


# ── Applied resumes management ──────────────────────────────────────────────

@app.get("/applied-resumes", summary="List all generated resume folders")
def list_applied_resumes():
    """List all generated resume/cover letter folders."""
    output_dir = Path("job_apply_output")
    if not output_dir.exists():
        return {"folders": []}
    folders = []
    for folder in sorted(output_dir.iterdir(), reverse=True):
        if folder.is_dir():
            files = [f.name for f in folder.iterdir()]
            folders.append({
                "folder":   folder.name,
                "path":     str(folder),
                "files":    files,
                "resume":   next((str(folder/f) for f in files if f.endswith(".pdf") and "Cover" not in f), ""),
                "cover":    next((str(folder/f) for f in files if "Cover" in f and f.endswith(".pdf")), ""),
                "created":  folder.stat().st_mtime,
            })
    return {"folders": folders}


@app.delete("/applied-resumes/{folder_name}", summary="Delete a resume folder")
def delete_applied_resume(folder_name: str):
    """Delete a specific resume output folder."""
    import shutil
    folder = Path("job_apply_output") / folder_name
    if not folder.exists():
        raise HTTPException(404, "Folder not found.")
    # Safety check — only delete within job_apply_output
    if "job_apply_output" not in str(folder.resolve()):
        raise HTTPException(403, "Cannot delete outside job_apply_output.")
    shutil.rmtree(str(folder))
    return {"message": f"Deleted {folder_name}"}


@app.get("/applied-resumes/{folder_name}/pdf", summary="Serve generated PDF")
def serve_generated_pdf(folder_name: str, type: str = "resume"):
    """Serve a generated tailored resume or cover letter PDF inline."""
    folder = Path("job_apply_output") / folder_name
    if not folder.exists():
        raise HTTPException(404, "Folder not found.")
    for f in folder.iterdir():
        is_cover  = "Cover" in f.name
        is_resume = not is_cover and f.suffix == ".pdf"
        if type == "cover" and is_cover:
            return FileResponse(str(f), media_type="application/pdf",
                                headers={"Content-Disposition": "inline"})
        if type == "resume" and is_resume:
            return FileResponse(str(f), media_type="application/pdf",
                                headers={"Content-Disposition": "inline"})
    raise HTTPException(404, "PDF not found.")