# QuickJob Applier — Product Requirements Document

**Version:** 2.0  
**Author:** Pinniti Gurunaidu  
**Status:** In Development  
**Last Updated:** March 2026

---

## 1. Problem Statement

Job searching is a time-intensive, repetitive process. For each job posting a candidate must:

- Manually tailor their resume to match the JD keywords
- Write a personalised cover letter from scratch
- Research the company and role
- Navigate multiple job portals with different UIs
- Fill out application forms with the same information repeatedly

This consumes **2–4 hours per application**. A senior professional applying to 20 jobs spends 40–80 hours on administrative work instead of learning and growing.

**Goal:** Automate the entire job application workflow so the candidate spends their time on what matters — learning, preparing, and interviewing — not on form-filling.

### Target User
A working professional with an existing PDF resume who wants to apply to multiple jobs efficiently without sacrificing the quality of each application.

---

## 2. User Flow

```
1. Upload PDF resume
      ↓
2. AI suggests job titles from resume (0 tokens if cached)
   User confirms/edits titles + selects portals in one screen
      ↓
3. System searches live job listings across selected portals
   Results filtered by country + seniority (no internships for experienced candidates)
      ↓
4. User reviews job cards (JD, company, salary, applicant count, match score)
   Clicks "Preview Tailored Resume" on any job → 4-tab modal:
     • Enhanced Resume (PDF, surgically edited — same format as original)
     • Cover Letter (personalised per company)
     • What Changed (before/after diff with reasons)
     • Study Plan (topics to learn, company overview, skills gap)
      ↓
5. User selects jobs to apply to
      ↓
6. System applies via RPA (Playwright):
   • Tier 1 portals: fully automated
   • Tier 2/3 portals: browser opened, pre-filled, human assists if needed
      ↓
7. Live status tracking per job
   Download tailored resume + cover letter per job
```

---

## 3. Functional Requirements

### 3.1 Resume Upload & Parsing

| ID | Requirement | Priority |
|----|-------------|----------|
| F01 | Accept PDF resume upload via drag-and-drop or file picker | Must |
| F02 | Preview uploaded PDF inline in the browser before proceeding | Must |
| F03 | Extract structured data: name, email, phone, skills, experience, education, certifications | Must |
| F04 | Extract hyperlinks from PDF (LinkedIn, GitHub, portfolio) and preserve them in output | Must |
| F05 | Fall back to minimal extraction if LLM fails (name, email, phone via regex) | Must |
| F06 | Support multiple PDF extraction libraries: pdfplumber → pypdf → PyMuPDF | Should |

### 3.2 Dynamic Job Title Suggestions

| ID | Requirement | Priority |
|----|-------------|----------|
| F07 | Suggest job titles ordered by: current/most recent role first → synonyms → taxonomy matches | Must |
| F08 | Use skill taxonomy to resolve titles without LLM when skills match known categories | Must |
| F09 | Cache title suggestions per resume fingerprint (name + email + skills + companies) | Must |
| F10 | Allow user to add custom job titles with free-text input | Must |
| F11 | Auto-correct common misspellings in custom titles client-side | Must |
| F12 | Show spell-correction hints inline before submission | Must |
| F13 | Show synonym suggestions for each selected title | Should |
| F14 | Display source badge: ⚡ From cache / 📋 From skills / 🤖 AI suggested | Should |

### 3.3 Portal Selection

| ID | Requirement | Priority |
|----|-------------|----------|
| F15 | Show portal selection in Step 1 (same screen as resume upload) | Must |
| F16 | Order portals by ease of apply: Tier 1 (no login) → Tier 2 → Tier 3 | Must |
| F17 | Allow select-all per tier | Must |
| F18 | Show portal description and restriction notice | Must |
| F19 | Pre-select sensible defaults for the chosen country | Should |

### 3.4 Job Search

| ID | Requirement | Priority |
|----|-------------|----------|
| F20 | Search Adzuna API (free, 1000/day) with country code for location-accurate results | Must |
| F21 | Search Serper Google Jobs API with explicit country filter | Must |
| F22 | Search RemoteOK, Arbeitnow, TheMuse free APIs | Should |
| F23 | Filter out internships/trainee roles for candidates with >2 years experience | Must |
| F24 | Filter out articles, guides, blog posts (not real job postings) | Must |
| F25 | Deduplicate results by URL across all sources | Must |
| F26 | Score each job by keyword match against candidate skills | Must |
| F27 | Show per job: title, company, location, salary, posted date, applicant count, JD (10–15 lines) | Must |
| F28 | Filter by portal and sort by match score, company, portal, title | Should |

### 3.5 Resume Enhancement

| ID | Requirement | Priority |
|----|-------------|----------|
| F29 | Surgically edit the original PDF using PyMuPDF — preserve all formatting | Must |
| F30 | Rewrite ONLY the bullet points of the 2 most recent experience entries | Must |
| F31 | Reorder skills section — matched skills to top, add relevant missing skills | Must |
| F32 | Preserve ALL original formatting: fonts, colours, columns, hyperlinks, photos | Must |
| F33 | No watermarks, no extra pages, no "Tailored Resume" headers | Must |
| F34 | Output must look fully human-generated | Must |
| F35 | Score ATS before saving — minimum 90% required | Must |
| F36 | If below 90%, automatically improve and rescore (one retry) | Must |
| F37 | Generate an edit summary: before/after diff with reason for each changed bullet | Must |
| F38 | Save .txt alongside PDF for fast text preview in the browser | Must |

### 3.6 Cover Letter Generation

| ID | Requirement | Priority |
|----|-------------|----------|
| F39 | Generate personalised cover letter per job (not generic template) | Must |
| F40 | Use candidate's actual achievements from resume, not fabricated ones | Must |
| F41 | 3-paragraph structure: hook → specific achievements → confident close | Must |
| F42 | Never start with "I am writing to apply" or similar openers | Must |
| F43 | Save as PDF and .txt | Must |

### 3.7 Study Plan

| ID | Requirement | Priority |
|----|-------------|----------|
| F44 | Generate ordered list of topics to learn (most important first) for each job | Must |
| F45 | Show company overview (2–3 sentences), industry, company size | Must |
| F46 | Show skills gap between candidate profile and JD requirements | Must |
| F47 | Provide free learning resources per topic (Coursera, YouTube, etc.) | Should |
| F48 | Show role highlights (key things about this specific role) | Should |

### 3.8 Preview Modal

| ID | Requirement | Priority |
|----|-------------|----------|
| F49 | Show actual PDF inline (not plain text) using iframe for PDF serving | Must |
| F50 | Four tabs: Enhanced Resume, Cover Letter, What Changed, Study Plan | Must |
| F51 | Show ATS score + JD match % + verdict in score bar | Must |
| F52 | Show matched skills (green) and missing skills (red) as chips | Must |
| F53 | Show ⚡ Cached badge when loaded from ChromaDB | Should |
| F54 | Fall back to plain text if PDF fails to load | Must |

### 3.9 Application Automation (RPA)

| ID | Requirement | Priority |
|----|-------------|----------|
| F55 | Use Playwright to automate form filling per portal | Must |
| F56 | Fill: name, email, phone, LinkedIn URL, cover letter summary | Must |
| F57 | Upload tailored resume PDF to file input fields | Must |
| F58 | Submit where possible; leave browser open for human assist otherwise | Must |
| F59 | Auto-close browser after: successful submit, user closes window, or 2-minute timeout | Must |
| F60 | Status per job: pending → applying → success/partial/manual_required/restricted/error | Must |
| F61 | Reuse pre-generated preview documents during apply — no re-generation | Must |

### 3.10 Generated Files Management

| ID | Requirement | Priority |
|----|-------------|----------|
| F62 | List all generated resume folders with company name and date | Must |
| F63 | Preview any generated PDF inline from the management panel | Must |
| F64 | Delete individual resume folders | Must |
| F65 | Download individual resume or cover letter | Must |

---

## 4. Non-Functional Requirements

### 4.1 Token Efficiency

| ID | Requirement |
|----|-------------|
| NF01 | All LLM calls routed through 3-layer cache: memory → ChromaDB → LLM |
| NF02 | Cold session token budget: < 15,000 tokens |
| NF03 | Warm session token budget: < 3,000 tokens |
| NF04 | Context compaction: all prompts truncated to task-specific max before LLM call |
| NF05 | Rule-based ATS scoring for clear-cut cases (match > 80% or < 30%) |

### 4.2 Performance

| Metric | Target |
|--------|--------|
| Backend startup | < 10 seconds |
| Job search results | < 20 seconds |
| Resume preview (cache hit) | < 1 second |
| Resume preview (cache miss) | < 60 seconds |
| PDF generation | < 5 seconds |
| UI initial load | < 3 seconds |

### 4.3 Reliability

- Backend restart must not corrupt existing generated files
- Cache must survive backend restarts (ChromaDB persistent)
- Sessions reset on restart by design (privacy) — user must re-upload
- Graceful fallback at every LLM call (retry with smaller model)

### 4.4 Security

- API keys stored only in `config.py` — never committed to git
- `config.py` and `vector_db/` in `.gitignore`
- CORS restricted to localhost in development
- No user data sent to third parties beyond the LLM API calls

### 4.5 Portability

- Runs on Windows (VirtualBox), Linux, macOS
- Python 3.10+ required
- No GPU required
- Node.js 18+ for frontend

---

## 5. Supported Countries & Portals

### Countries
Singapore · India · Australia · USA · UK · Malaysia · UAE · Germany · Canada

### Portal Tiers

| Tier | Portals | Auth | Apply Method |
|------|---------|------|--------------|
| 1 — No login | Adzuna, RemoteOK, Arbeitnow, TheMuse, Jobsdb | None | Fully automated |
| 2 — Optional | Indeed, JobStreet, Naukri, Seek, Reed | Optional | Automated + human assist |
| 3 — Login required | LinkedIn, MyCareersFuture, Glassdoor | Required | Browser opened, human applies |

---

## 6. API Keys Required

| Key | Provider | Cost | Purpose |
|-----|----------|------|---------|
| `GROQ_API_KEY` | Groq | Free (100k tokens/day) | Primary LLM |
| `SERPER_API_KEY` | Serper | Free (2,500/month) | Google Jobs search |
| `ADZUNA_APP_ID` + `ADZUNA_APP_KEY` | Adzuna | Free (1,000/day) | Direct job listings |
| `GEMINI_API_KEY` | Google | Free tier | LLM fallback + embeddings |
| `OPENAI_API_KEY` | OpenAI | ~$5 minimum | Best embeddings + LLM fallback |
| `CLAUDE_API_KEY` | Anthropic | ~$5 minimum | LLM fallback |

---

## 7. Out of Scope (Future Roadmap)

- LinkedIn OAuth integration for Easy Apply
- Email/SMS notifications when applications are submitted
- Interview preparation module (common questions per role)
- Salary negotiation coaching
- Multi-language resume support
- Calendar integration for interview scheduling
- Cloud deployment (currently localhost only)
- Mobile application
- Resume version history management
- Analytics dashboard (applications sent, response rate, ATS score trends)