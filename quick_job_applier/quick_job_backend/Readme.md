# QuickJob Applier — Backend

FastAPI backend that automates the entire job application workflow. Upload a resume once — the system suggests matching job titles, searches live listings, surgically tailors your resume per job, generates a personalised cover letter and study plan, and applies via Playwright RPA.

---

## Quick Start

```bash
cd ~/quick_job_backend
pip install -r requirements.txt
python -m playwright install chromium
cp config.example.py config.py   # then add your API keys
uvicorn job_apply_api:app --reload --port 8001
```

---

## Folder Structure

```
quick_job_backend/
├── job_apply_api.py          # FastAPI app — all endpoints
├── agent.py                  # LLM fallback chain + pipeline functions
├── config.py                 # API keys (gitignored — NEVER commit)
├── memory_manager.py         # Memory coordinator + title cache
├── llm_cache.py              # Semantic cache for ALL LLM calls
├── resume_cache.py           # Per-job preview cache
├── requirements.txt
│
├── memory/                   # Zero-token knowledge base (versioned)
│   ├── system_prompts.json          # Reusable prompts for all LLM types
│   ├── job_title_taxonomy.json      # Skills → titles by seniority
│   ├── job_title_synonyms.json      # Title synonyms + spell corrections
│   ├── ats_rules.json               # Rule-based ATS scoring
│   └── cover_letter_templates.json  # Cover letter structure
│
├── tools/
│   ├── resume_parser.py      # PDF extraction (pdfplumber → pypdf → PyMuPDF)
│   ├── job_identifier.py     # Dynamic titles: cache → taxonomy → LLM
│   ├── job_searcher.py       # Multi-source search, seniority + location filter
│   ├── jd_matcher.py         # JD vs resume skill matching
│   ├── resume_enhancer.py    # Surgical PDF edit (PyMuPDF) + study plan
│   ├── resume_builder.py     # Clean PDF fallback (fpdf2)
│   └── job_applier.py        # Playwright RPA per portal
│
├── uploads/                  # Uploaded PDFs (auto-created, gitignored)
├── job_apply_output/         # Generated resumes + cover letters (gitignored)
└── vector_db/                # ChromaDB persistent cache (gitignored)
```

---

## API Keys

Create `config.py`:

```python
GROQ_API_KEY   = "gsk_..."    # Required — free at console.groq.com
SERPER_API_KEY = "..."         # Recommended — free 2,500/mo at serper.dev
ADZUNA_APP_ID  = "..."         # Recommended — free 1,000/day developer.adzuna.com
ADZUNA_APP_KEY = "..."
GEMINI_API_KEY = "AIza..."     # Optional — free embeddings + LLM fallback
OPENAI_API_KEY = "sk-..."      # Optional — best embeddings
CLAUDE_API_KEY = "sk-ant-..."  # Optional — LLM fallback
```

---

## Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET`  | `/` | Health check |
| `POST` | `/resume-job-titles` | Dynamic titles from resume (0 tokens if cached) |
| `POST` | `/upload-resume` | Parse resume + identify portals |
| `POST` | `/search-jobs` | Search live listings |
| `GET`  | `/search-status/{id}` | Poll search results |
| `POST` | `/select-jobs` | Save job selection |
| `POST` | `/preview-resume` | Generate tailored preview (cached) |
| `GET`  | `/preview-resume-pdf/{sid}/{jid}` | Serve tailored PDF inline |
| `POST` | `/apply` | Start RPA application |
| `GET`  | `/apply-status/{id}` | Poll per-job status |
| `GET`  | `/resume-pdf/{sid}` | Serve original PDF inline |
| `GET`  | `/applied-resumes` | List generated folders |
| `DELETE` | `/applied-resumes/{folder}` | Delete folder |
| `GET`  | `/cache-stats` | Cache statistics |

---

## Caching (3-layer stack)

```
Layer 1 — memory files          0 tokens always
  taxonomy → titles from skills without LLM
  ats_rules → score clear cases without LLM
  system_prompts → inject once, reuse everywhere

Layer 2 — ChromaDB              0 tokens on hit
  llm_cache/    88% similarity  all LLM responses
  title_cache/  92% similarity  per resume fingerprint
  resume cache  92% similarity  per job+resume combo

Layer 3 — LLM                   tokens only on true miss
  context compacted before sending
  response cached immediately after
```

Full details: `CACHING.md`

---

## Resume Enhancement

Surgical edit only — never rewrites from scratch:
- PyMuPDF locates exact bullet bounding boxes
- Only the 2 most recent jobs' bullets are replaced
- Skills section reordered (matched skills first)
- All fonts, colours, columns, hyperlinks preserved
- ATS scored; improved if below 90%
- Edit summary (before/after + reasons) saved separately

---

## LLM Fallback Chain

Gemini 2.5 → OpenAI GPT-3.5 → Claude Sonnet → Groq llama-3.3 (free) → Groq llama-3.1 (smaller, separate quota)

---

## Portal Tiers

| Tier | Portals | Auth |
|------|---------|------|
| 1 | Adzuna, RemoteOK, Arbeitnow, TheMuse | None — fully automated |
| 2 | Indeed, JobStreet, Naukri, Seek, Reed | Optional — human assist if needed |
| 3 | LinkedIn, MyCareersFuture, Glassdoor | Required — browser opened for user |

---

## Docs

- `CACHING.md` — complete caching architecture
- `docs/REQUIREMENTS.md` — full product requirements
- `docs/SYSTEM_DESIGN.md` — component design + data flow
- `docs/LLMOPS.md` — LLM management and tuning
- `docs/SDLC.md` — development workflow
- `docs/API_KEYS_GUIDE.md` — step-by-step key registration