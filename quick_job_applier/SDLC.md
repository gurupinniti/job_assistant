# QuickJob Applier — SDLC Guide

Software Development Lifecycle practices for this project.

---

## 1. Project Structure

```
quickjob-applier/                    ← git root
├── quick_job_backend/               ← Python FastAPI backend
│   ├── config.py                    ← API keys (gitignored)
│   ├── job_apply_api.py
│   ├── agent.py
│   ├── memory_manager.py
│   ├── llm_cache.py
│   ├── resume_cache.py
│   ├── requirements.txt
│   ├── memory/                      ← Knowledge base (versioned)
│   │   ├── system_prompts.json
│   │   ├── job_title_taxonomy.json
│   │   ├── job_title_synonyms.json
│   │   ├── ats_rules.json
│   │   └── cover_letter_templates.json
│   ├── tools/
│   │   ├── resume_parser.py
│   │   ├── job_identifier.py
│   │   ├── job_searcher.py
│   │   ├── jd_matcher.py
│   │   ├── resume_enhancer.py
│   │   ├── resume_builder.py
│   │   └── job_applier.py
│   ├── uploads/                     ← gitignored
│   ├── job_apply_output/            ← gitignored
│   └── vector_db/                   ← gitignored
│
├── quick_job_ui/                    ← React frontend
│   ├── package.json
│   ├── public/
│   └── src/
│       ├── App.jsx
│       ├── App.css
│       ├── api/client.js
│       ├── hooks/useJobApply.js
│       └── components/
│           ├── BackendGate.jsx
│           ├── StepIndicator.jsx
│           ├── ResumeDropzone.jsx
│           ├── JobTitleSelector.jsx
│           ├── PortalMultiSelect.jsx
│           ├── CountrySearch.jsx
│           ├── PortalCard.jsx
│           ├── JobListings.jsx
│           ├── PdfViewer.jsx
│           └── AppliedResumesPanel.jsx
│
├── docs/                            ← All documentation
│   ├── REQUIREMENTS.md
│   ├── SYSTEM_DESIGN.md
│   ├── LLMOPS.md
│   ├── SDLC.md
│   └── API_KEYS_GUIDE.md
│
├── CACHING.md                       ← Cache architecture guide
├── .gitignore
└── README.md                        ← Project overview
```

---

## 2. Environment Setup

### Prerequisites

| Tool | Version | Purpose |
|------|---------|---------|
| Python | 3.10+ | Backend runtime |
| Node.js | 18+ | Frontend build |
| npm | 9+ | Package management |
| Chromium | Latest | Playwright automation |

### First-time setup

```bash
# 1. Clone the repository
git clone <repo-url>
cd quickjob-applier

# 2. Backend setup
cd quick_job_backend
pip install -r requirements.txt
python -m playwright install chromium
python -m playwright install-deps chromium    # Linux only

# 3. Create config.py (copy from template)
cp config.example.py config.py
# Edit config.py — add your API keys

# 4. Frontend setup (must be on native filesystem, not shared drive)
cd ../quick_job_ui
npm install

# 5. Create memory directories (auto-created on first run, but good to verify)
mkdir -p quick_job_backend/vector_db
mkdir -p quick_job_backend/uploads
mkdir -p quick_job_backend/job_apply_output
```

### config.example.py template

```python
# quick_job_backend/config.example.py
# Copy to config.py and fill in your API keys

GROQ_API_KEY   = ""   # Required — free at console.groq.com
SERPER_API_KEY = ""   # Recommended — free at serper.dev
ADZUNA_APP_ID  = ""   # Recommended — free at developer.adzuna.com
ADZUNA_APP_KEY = ""   # Recommended — free at developer.adzuna.com
GEMINI_API_KEY = ""   # Optional — free at aistudio.google.com
OPENAI_API_KEY = ""   # Optional — paid at platform.openai.com
CLAUDE_API_KEY = ""   # Optional — paid at console.anthropic.com
OPENWEATHER_API_KEY = ""  # Not required for job apply feature
```

---

## 3. Running the Application

```bash
# Terminal 1 — Backend
cd ~/quick_job_backend
uvicorn job_apply_api:app --reload --port 8001

# Terminal 2 — Frontend
cd ~/quick_job_ui
npm start
# Opens at http://localhost:3000
```

### Expected startup logs (backend)

```
INFO:     Will watch for changes in these directories: ['/home/.../quick_job_backend']
INFO:     Uvicorn running on http://127.0.0.1:8001
[Startup] Initialising QuickJob Agent...
  [1/4] Trying Gemini...
  [OK] Gemini (gemini-2.5-flash)
  [LLMCache] Ready — 12 cached responses
  [Memory] Title cache: 3 entries
  [Memory] Loaded: system_prompts, taxonomy, synonyms, ats_rules, cover_templates
[Startup] Ready.
```

---

## 4. Development Workflow

### Making backend changes

```bash
# uvicorn --reload detects file changes automatically
# Just edit and save — no restart needed

# Exception: changes to config.py or memory/*.json require:
# Touch the main API file to trigger reload
touch job_apply_api.py
```

### Making frontend changes

```bash
# npm start watches for changes automatically
# Just edit and save — browser hot-reloads

# If hot-reload breaks: Ctrl+C then npm start again
# If still broken: rm -rf node_modules && npm install
```

### Adding a new job portal

1. Add portal to `PORTAL_CATALOGUE` in `tools/job_searcher.py`
2. Add to `COUNTRY_PORTALS` for relevant countries
3. Add a `_apply_{portal}` method in `tools/job_applier.py`
4. Add to `PORTAL_STRATEGIES` dict in `tools/job_applier.py`

### Adding a new career category

1. Edit `memory/job_title_taxonomy.json`
2. Add a new entry under `"categories"` with:
   - `skill_signals`: list of skills that indicate this category
   - `titles_by_years`: titles for each seniority bracket

No code changes needed. Memory files reload automatically.

### Tuning LLM prompts

1. Edit `memory/system_prompts.json`
2. Clear the LLM cache if old responses should be regenerated:
   ```bash
   rm -rf vector_db/llm_cache
   ```

---

## 5. Testing

### Manual testing checklist

**Before every commit:**

- [ ] Backend starts without errors
- [ ] Upload a test PDF resume → correct parsing
- [ ] Job titles suggested match candidate's actual current role
- [ ] Custom title input works, spell correction fires
- [ ] Portal selection persists when changing country
- [ ] Job search returns results for Singapore, filtered to correct country
- [ ] No internship results for candidates with >2 years experience
- [ ] Preview modal shows PDF (not just text)
- [ ] What Changed tab shows before/after bullets
- [ ] Study Plan tab loads with company info
- [ ] Cache stats endpoint returns sensible numbers
- [ ] Second preview of same job is instant (cache hit)

### API testing

```bash
# Health check
curl http://localhost:8001/

# Cache statistics
curl http://localhost:8001/cache-stats

# Job titles from resume (manual test)
curl -X POST http://localhost:8001/resume-job-titles \
  -F "resume=@/path/to/test_resume.pdf" \
  -F "country=singapore"

# Session check (after upload)
curl http://localhost:8001/session-check/{session_id}
```

### Common issues

| Issue | Cause | Fix |
|-------|-------|-----|
| `ModuleNotFoundError: No module named 'fitz'` | PyMuPDF not installed | `pip install pymupdf` |
| `RuntimeError: No LLM available` | All API keys exhausted | Wait for rate limit reset or add key |
| Job listings show wrong country | Adzuna API key missing | Add to `config.py` |
| PDF preview shows blank | fpdf2 version mismatch | `pip install --upgrade fpdf2` |
| `npm install` fails | Running from shared drive | Move to `~/quick_job_ui` on native FS |
| Session 404 on preview | Backend restarted | Re-upload resume (sessions are in-memory) |

---

## 6. Git Workflow

### Branch strategy

```
main          ← stable, tested
feature/xxx   ← new features
fix/xxx       ← bug fixes
```

### Commit message convention

```
feat: add portal multi-select to step 1
fix: correct internship filtering for senior candidates
docs: update CACHING.md with new title cache
refactor: move ATS scoring to memory layer
chore: update requirements.txt
```

### Before committing

```bash
# Verify no API keys in changed files
git diff --staged | grep -E "(API_KEY|APP_KEY|APP_ID)" | grep "^+" 
# Should return nothing

# Verify gitignore is working
git status --short | grep "config.py"
# Should return nothing (config.py must be untracked)
```

---

## 7. Release Checklist

- [ ] All manual tests pass
- [ ] `requirements.txt` updated with any new packages
- [ ] `memory/` JSON files are valid (run through json validator)
- [ ] `.gitignore` excludes `config.py`, `vector_db/`, `uploads/`, `job_apply_output/`
- [ ] `README.md` updated
- [ ] `docs/REQUIREMENTS.md` updated if features changed
- [ ] No hardcoded API keys anywhere in code
- [ ] `config.example.py` updated if new keys added

---

## 8. Known Constraints

| Constraint | Detail |
|-----------|--------|
| Sessions in-memory | Backend restart loses all active sessions |
| No authentication | Single-user, local only — no multi-user support |
| VirtualBox shared drive | `npm install` must run on native filesystem |
| Groq free tier | 100k tokens/day — warm cache essential |
| PyMuPDF surgical edit | Complex PDFs (scanned, image-based) may fall back to fpdf2 |
| LinkedIn automation | Requires manual login — cannot be fully automated |
| SingPass portals | MyCareersFuture cannot be automated at all |