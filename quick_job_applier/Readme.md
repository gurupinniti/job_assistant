# QuickJob Applier

AI-powered job application agent with a React UI and FastAPI backend.
Upload your resume, pick job titles and a country, confirm portals, and let the AI apply for you.

---

## Folder Structure

```
quick_job_ui/          ← React frontend
├── src/
│   ├── App.jsx                 # Main app, all 3 steps
│   ├── App.css                 # Full design system
│   ├── index.js                # Entry point
│   ├── api/client.js           # All API calls
│   ├── hooks/useJobApply.js    # State + logic hook
│   └── components/
│       ├── StepIndicator.jsx   # Progress bar
│       ├── ResumeDropzone.jsx  # Drag & drop upload
│       ├── JobTitleSelector.jsx# Searchable multi-select chips
│       ├── CountrySearch.jsx   # Searchable country dropdown
│       └── PortalCard.jsx      # Confirm + status cards
└── package.json

quick_job_backend/     ← FastAPI backend
├── job_apply_api.py            # All endpoints
├── agent.py                    # LLM factory + pipeline
├── requirements.txt
└── tools/
    ├── resume_parser.py        # PDF/DOCX → structured JSON
    ├── job_identifier.py       # Country → portals + title enrichment
    ├── jd_matcher.py           # Resume vs JD scoring
    ├── resume_builder.py       # Tailored resume + cover letter
    └── job_applier.py          # Playwright automation per portal
```

---

## Setup

### Backend
```bash
cd quick_job_backend
pip install -r requirements.txt
playwright install chromium

# Create config.py (never commit)
# GEMINI_API_KEY / OPENAI_API_KEY / CLAUDE_API_KEY / GROQ_API_KEY

uvicorn job_apply_api:app --reload --port 8001
```

### Frontend
```bash
cd quick_job_ui
npm install
npm start        # runs on http://localhost:3000
```

---

## User Flow

| Step | What happens |
|------|-------------|
| **1 — Resume & Preferences** | Upload PDF/DOCX · select job titles (searchable chips) · choose country |
| **2 — Confirm Portals** | Agent parses resume → shows matched portals with Easy Apply badges and restriction warnings · user unchecks anything to skip |
| **3 — Live Status** | Per-portal status updates every 3 seconds · download tailored resume + cover letter when done |

---

## Portal Status Values

| Status | Meaning |
|--------|---------|
| `pending` | Queued, not started yet |
| `success` | Application submitted |
| `partial` | Reached form but needs manual completion (login required) |
| `restricted` | Cannot automate (e.g. SingPass, account required) |
| `error` | Unexpected failure |

---

## LLM Fallback
```
Gemini → OpenAI → Claude → Groq (free)
```

---

## .gitignore
```
quick_job_backend/uploads/
quick_job_backend/job_apply_output/
quick_job_backend/config.py
**/node_modules/
**/__pycache__/
**/*.pyc
.env
```