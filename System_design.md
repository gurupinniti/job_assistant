# QuickJob Applier — System Design

---

## 1. High-Level Architecture

The system is a two-process local application:

- **React SPA** (`localhost:3000`) — user interface
- **FastAPI backend** (`localhost:8001`) — AI pipeline, caching, RPA

All data stays local. No cloud services except LLM API calls and job search APIs.

```
Browser (React SPA)
       │  HTTP/REST
       ▼
FastAPI Backend ──► Job Search APIs  (Adzuna, Serper, RemoteOK, Arbeitnow)
       │
       ├──► Memory Layer     (memory/*.json — loaded at startup)
       ├──► ChromaDB Cache   (vector_db/ — persists across restarts)
       ├──► LLM Chain        (Gemini → GPT → Claude → Groq)
       ├──► PyMuPDF          (surgical PDF editing)
       └──► Playwright       (browser automation / RPA)
```

---

## 2. Component Design

### 2.1 FastAPI Backend (`job_apply_api.py`)

Single-file API layer. All business logic delegated to tools and managers.

**State management:** In-memory session dict (`sessions: dict`). Sessions hold:
- Parsed resume JSON
- Original PDF path
- Confirmed portals
- Job listings
- Selected jobs
- Preview outputs (paths to generated files)
- Apply status per job

Sessions are intentionally ephemeral — they reset on server restart for privacy. Generated files persist independently in `job_apply_output/`.

**Background tasks:** Job search and application run as FastAPI `BackgroundTask` instances. The UI polls status endpoints every 2–3 seconds.

---

### 2.2 LLM Factory (`agent.py`)

Implements a probe-first fallback chain. Before returning any LLM, a lightweight `model.invoke([HumanMessage("hi")])` test call is made. If it fails due to rate limiting or auth errors, the next provider is tried.

```python
def get_llm():
    # 1. Gemini 2.5 flash/pro
    # 2. OpenAI gpt-3.5-turbo
    # 3. Claude claude-3-5-sonnet
    # 4. Groq llama-3.3-70b-versatile
    # 4b. Groq llama-3.1-8b-instant (if 70b hits daily limit)
    # Raises RuntimeError if all providers exhausted
```

The LLM instance is cached in `_llm` module-level variable — only initialised once per server lifetime.

---

### 2.3 Memory Manager (`memory_manager.py`)

Coordinates all zero-token operations:

| Function | What it does | Tokens |
|----------|-------------|--------|
| `get_system_prompt(key)` | Returns prompt from `memory/system_prompts.json` | 0 |
| `resolve_job_titles_from_taxonomy(resume_json)` | Matches skills → titles by seniority | 0 |
| `get_synonym_titles(title)` | Returns synonym group for a title | 0 |
| `correct_title_spelling(title)` | Fixes misspellings from memory file | 0 |
| `compact_resume_for_prompt(resume_json, focus)` | Truncates resume to task-relevant fields | 0 |
| `compact_jd(jd_text)` | Strips boilerplate from JD text | 0 |
| `quick_ats_score(resume_json, jd, match)` | Rule-based ATS for clear-cut cases | 0 |
| `resume_fingerprint(resume_json)` | SHA-256 of stable resume fields | 0 |
| `lookup_titles_cache(resume_json)` | ChromaDB lookup for title suggestions | 0 |
| `store_titles_cache(resume_json, result)` | Store new title resolution in ChromaDB | 0 |

---

### 2.4 LLM Cache (`llm_cache.py`)

Universal semantic cache wrapping every LLM call in the system.

```
cached_llm_call(llm, messages, prompt_type)
    │
    ├── Build prompt_key = join(message.content for message in messages)
    ├── SHA-256 exact lookup in ChromaDB  →  hit: return (0 tokens)
    ├── Embed prompt_key  →  cosine similarity search
    │       similarity ≥ 0.88  →  return cached response (0 tokens)
    ├── _compact_messages(messages, prompt_type)  →  truncate to max_chars
    ├── llm.invoke(compacted_messages)  →  LLM called
    └── store(prompt_key, response, prompt_type)  →  cached for future
```

**Context compaction limits per prompt type:**

| Type | Max chars | Why this limit |
|------|-----------|---------------|
| `experience_rewrite` | 4,000 | Only last 3 jobs needed |
| `skills_rewrite` | 2,000 | Skills section only |
| `ats_score` | 2,500 | First 1k chars of content sufficient |
| `cover_letter` | 2,000 | JD highlights + top strengths |
| `study_plan` | 2,000 | JD + gap skills only |
| `job_title_extractor` | 1,500 | Current role + skills only |

---

### 2.5 Resume Cache (`resume_cache.py`)

Per-job preview cache. Stores complete preview output so the same job never triggers LLM calls twice.

**Cache key:** SHA-256 of `resume_json[:2000] + job_title + company + jd[:500]`  
**Semantic threshold:** 92% cosine similarity  
**Stored fields:** resume_path, cover_path, .txt paths, ats_score, match_score, verdict, matched_skills, missing_skills, study_plan JSON, edit_summary JSON

---

### 2.6 Resume Enhancer (`tools/resume_enhancer.py`)

The most complex tool. Implements surgical PDF editing using PyMuPDF.

**Algorithm:**

```
1. PDFSurgicalEditor.open(original_pdf)
   └── extract all text spans with bounding boxes (x, y, width, height, fontsize, color)

2. extract_section(["WORK EXPERIENCE", "EXPERIENCE", ...])
   └── walk spans, detect section header by font flags + ALL CAPS
   └── collect content spans until next section header found

3. identify_job_boundaries(experience_spans)
   └── title lines: short, bold OR contains "at"/"Ltd"/"Inc"
   └── returns indices of first N=2 job starts

4. replace_section_content(spans, new_lines)
   └── for each old bullet span:
       a. page.add_redact_annot(rect, fill=(1,1,1))  ← white-out
       b. page.apply_redactions()
       c. page.insert_text(position, new_text, fontsize=original_size, color=original_color)

5. doc.save(output_path, garbage=4, deflate=True, clean=True)
```

**Fallback chain:**
1. Surgical PyMuPDF edit (preferred — preserves original format)
2. Clean fpdf2 PDF from scratch (if PyMuPDF edit fails)
3. Plain text file with .pdf extension (if fpdf2 fails)

---

### 2.7 Job Searcher (`tools/job_searcher.py`)

Multi-source aggregator with location filtering and seniority gating.

**Sources (in priority order):**

| Source | API Type | Cost | Location accuracy |
|--------|----------|------|------------------|
| Adzuna | REST API with country code | Free (1k/day) | High — country-specific endpoint |
| Serper Google Jobs | `/jobs` endpoint | Paid (2.5k/mo free) | High — `gl` param + query |
| RemoteOK | Public JSON | Free | Remote only |
| Arbeitnow | REST API | Free | Medium |
| TheMuse | REST API | Free | Medium |

**Filtering pipeline:**

```
Raw results
    │
    ├── _is_real_job(title, url, min_years_exp)
    │       Rejects: articles, guides, blog posts
    │       Rejects: internships if candidate has > 2 years experience
    │
    ├── _location_matches(job_location, expected_country)
    │       Checks city/country aliases (e.g. "sg", "singapore", "Singapore")
    │       Passes: "Remote" always
    │
    └── Deduplicate by URL
            Score by skill keyword overlap
            Add stable applicant count (seeded random, consistent per job_id)
```

---

### 2.8 Job Applier (`tools/job_applier.py`)

RPA automation using Playwright synchronous API.

**Per-portal strategy:**

```python
PORTAL_STRATEGIES = {
    "Adzuna":    "_apply_adzuna",          # navigate → find apply btn → fill → submit
    "Indeed":    "_apply_indeed",          # find job card → click → fill → submit
    "LinkedIn":  "_apply_linkedin",        # login check → Easy Apply → multi-step form
    "JobStreet": "_apply_jobstreet",       # navigate → fill → partial
    ...
    "default":   "_apply_generic_direct"  # generic: apply btn → fill → submit
}
```

**Browser lifecycle:**

```
success/restricted   →  wait 2s → browser.close() automatically
partial/manual       →  wait_for_close_or_timeout(120s)
                        user can interact for up to 2 minutes
                        browser closes on window close or timeout
```

---

## 3. Data Flow — Resume Preview

The most token-expensive operation. Full flow with cache check points:

```
POST /preview-resume {session_id, job}
        │
        ├── [Cache check 1] resume_cache.lookup()
        │       hit (92% similar) → return cached data, serve PDF from disk
        │       0 tokens, < 100ms
        │
        └── [Cache miss] LLM pipeline:
                │
                ├── JDMatcherTool._run(resume_json, jd_text, job_title)
                │       compact_resume("match") → ~400 chars
                │       compact_jd() → ~800 chars
                │       llm_cache.cached_llm_call(llm, messages, "jd_match")
                │
                ├── resume_enhancer.enhance_resume(...)
                │       ├── PDFSurgicalEditor.open(original_pdf)
                │       ├── _rewrite_experience() → llm_cache("experience_rewrite")
                │       ├── _rewrite_skills()     → llm_cache("skills_rewrite")
                │       ├── _score_ats()
                │       │       quick_ats_score() → 0 tokens if clear-cut
                │       │       else → llm_cache("ats_score")
                │       ├── _cover_letter()       → llm_cache("cover_letter")
                │       ├── _study_plan()         → llm_cache("study_plan")
                │       └── rebuild_pdf() → save to job_apply_output/
                │
                └── resume_cache.store(all results)
                        → cached for next access
```

---

## 4. Database Design

No relational database. Three storage types:

### 4.1 In-Memory Sessions

```python
sessions[session_id] = {
    "resume_path":       str,        # path to uploaded PDF
    "resume_json":       str,        # parsed resume as JSON string
    "resume_data":       dict,       # parsed resume as dict
    "original_filename": str,        # original file stem (for output naming)
    "job_titles":        list,       # resolved title suggestions
    "country":           str,
    "portals":           list,
    "confirmed_portals": list,
    "status":            str,        # workflow state
    "job_listings":      list,
    "selected_jobs":     list,
    "previews":          dict,       # {job_id: {resume_path, cover_letter_path}}
    "job_statuses":      dict,       # {job_id: status_string}
    "apply_result":      dict,
}
```

### 4.2 File System

```
job_apply_output/
└── {YYYYMMDD_HHMMSS}_{CompanyName}/
    ├── {resume_name}_{company}.pdf     # tailored resume (surgically edited)
    ├── {resume_name}_{company}.txt     # plain text for fast preview
    ├── CoverLetter_{company}.pdf
    ├── CoverLetter_{company}.txt
    ├── study_plan.json
    └── edit_summary.json

uploads/
└── {session_id}_{original_filename}.pdf
```

### 4.3 ChromaDB Collections

```
vector_db/
├── llm_cache/              # collection: "llm_responses"
│   metadata fields: prompt_type, prompt_preview, cached_at, response_len
│   document: response text
│
├── title_cache/            # collection: "job_titles"
│   metadata fields: primary_titles, all_titles, seniority, exp_years,
│                    matched_categories, source, stored_at
│   document: resume embed text (roles + skills summary)
│
└── (root)                  # collection: "resume_cache"
    metadata fields: job_title, company, resume_path, cover_path,
                     resume_txt_path, cover_txt_path, output_folder,
                     ats_score, match_score, verdict,
                     matched_skills, missing_skills, study_plan, edit_summary
    document: embed text (job + candidate summary)
```

---

## 5. Error Handling Strategy

| Layer | Strategy |
|-------|----------|
| LLM calls | Probe → fallback chain → RuntimeError if all fail |
| PDF extraction | pdfplumber → pypdf → PyMuPDF → minimal regex fallback |
| PDF generation | Surgical edit → fpdf2 from scratch → plain text |
| ATS scoring | Rule-based → LLM → default score (75%) |
| Job title resolution | Title cache → taxonomy → LLM → static fallback list |
| ChromaDB operations | Try/except on every call — cache failure never blocks main flow |
| Playwright | Per-portal method → generic → status "error" with message |

All errors are logged to server console with full traceback. The UI shows user-friendly error messages, never raw stack traces.

---

## 6. Security Considerations

| Concern | Mitigation |
|---------|------------|
| API key exposure | `config.py` in `.gitignore`, never committed |
| Path traversal in delete endpoint | Validate path contains `job_apply_output` before deletion |
| CORS | `allow_origins=["*"]` in dev — restrict to `localhost:3000` in prod |
| PDF file serving | Only files within known output directories served |
| Session isolation | Session IDs are random 8-char hex — not guessable |
| LLM prompt injection | User input (resume text, JD) is embedded in prompts but not as system instructions |

---

## 7. Deployment (Local)

```
┌─────────────────────────────────┐  ┌─────────────────────────────────┐
│  Terminal 1 — Backend           │  │  Terminal 2 — Frontend           │
│                                 │  │                                  │
│  cd ~/quick_job_backend         │  │  cd ~/quick_job_ui               │
│  uvicorn job_apply_api:app      │  │  npm start                       │
│    --reload --port 8001         │  │                                  │
│                                 │  │  Opens: http://localhost:3000    │
│  API: http://localhost:8001     │  │  Calls: http://localhost:8001    │
└─────────────────────────────────┘  └─────────────────────────────────┘
```

No Docker, no cloud. Designed to run on a developer laptop or VM.