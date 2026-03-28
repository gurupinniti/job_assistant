# API Keys Setup Guide

Complete guide to get all API keys needed for QuickJob Applier.
Add all keys to `quick_job_backend/config.py`.

---

## Required (Minimum to run)

### Groq — Free LLM (the AI brain)
**Cost:** Free · **Limit:** 100k tokens/day · **Card needed:** No

1. Go to https://console.groq.com
2. Sign up with Google or email
3. Click **API Keys** in the left sidebar
4. Click **Create API Key**
5. Copy the key (starts with `gsk_...`)

```python
GROQ_API_KEY = "gsk_your_key_here"
```

---

## Recommended (Better job listings)

### Serper — Google Jobs search
**Cost:** Free tier · **Limit:** 2,500 searches/month · **Card needed:** No

1. Go to https://serper.dev
2. Click **Get Started Free**
3. Sign up with Google or email
4. Go to **Dashboard → API Key**
5. Copy your key

```python
SERPER_API_KEY = "your_serper_key_here"
```

> **What it enables:** Searches Google Jobs which aggregates LinkedIn, Indeed, Glassdoor, Naukri, Seek, JobStreet — all in one query filtered by your country.

---

### Adzuna — Direct job listings API
**Cost:** Free · **Limit:** 1,000 calls/day · **Card needed:** No

1. Go to https://developer.adzuna.com
2. Click **Register** (top right)
3. Fill in your details — select **Personal/Non-commercial** use
4. After registration, go to **Dashboard**
5. You will see your **Application ID** and **Application Key**

```python
ADZUNA_APP_ID  = "your_app_id_here"      # numeric e.g. "12345678"
ADZUNA_APP_KEY = "your_app_key_here"     # alphanumeric
```

> **What it enables:** Real job listings with company name, salary, full description, direct apply URL. Supports Singapore, India, Australia, UK, USA, Canada, Germany, UAE, Malaysia.
> **Country support:** sg, in, au, gb, us, ca, de, ae, my

---

## Optional (More LLM choices)

### Gemini — Google's LLM (fallback + embeddings)
**Cost:** Free tier · **Limit:** Generous free quota · **Card needed:** No

1. Go to https://aistudio.google.com
2. Sign in with Google account
3. Click **Get API Key** (top left)
4. Click **Create API Key**
5. Select a project or create a new one

```python
GEMINI_API_KEY = "AIza_your_key_here"
```

> **What it enables:** Primary LLM fallback if Groq hits limits. Also enables **Gemini embeddings** for the resume cache (better semantic matching than hash fallback).

---

### OpenAI — GPT-3.5 (fallback + best embeddings)
**Cost:** Pay per use · **Minimum:** $5 credit · **Card needed:** Yes

1. Go to https://platform.openai.com
2. Sign up and add a payment method
3. Go to **API Keys** → **Create new secret key**
4. Copy the key (starts with `sk-...`)

```python
OPENAI_API_KEY = "sk-your_key_here"
```

> **What it enables:** GPT-3.5-turbo as LLM fallback. **text-embedding-3-small** for the resume cache — the most accurate embedding model available, costs ~$0.00002 per query (essentially free).

---

### Anthropic Claude (fallback)
**Cost:** Pay per use · **Minimum:** $5 credit · **Card needed:** Yes

1. Go to https://console.anthropic.com
2. Sign up and add payment
3. Go to **API Keys** → **Create Key**

```python
CLAUDE_API_KEY = "sk-ant-your_key_here"
```

---

## Complete config.py template

```python
# quick_job_backend/config.py
# !! Never commit this file to git !!

# ── LLMs (at least one required) ─────────────────────────
GROQ_API_KEY   = "gsk_..."          # FREE — minimum required
GEMINI_API_KEY = ""                  # FREE — recommended for embeddings
OPENAI_API_KEY = ""                  # Paid — best embeddings
CLAUDE_API_KEY = ""                  # Paid — optional fallback

# ── Job search (highly recommended) ──────────────────────
SERPER_API_KEY = ""                  # FREE 2500/mo — Google Jobs search
ADZUNA_APP_ID  = ""                  # FREE 1000/day — direct listings
ADZUNA_APP_KEY = ""                  # FREE 1000/day — direct listings

# ── Weather (not needed for job apply) ───────────────────
OPENWEATHER_API_KEY = ""
```

---

## Priority order recommendation

| Priority | Key | Why |
|----------|-----|-----|
| **1st** | `GROQ_API_KEY` | Free LLM, no card, works immediately |
| **2nd** | `SERPER_API_KEY` | Enables Google Jobs — most job listings |
| **3rd** | `ADZUNA_APP_ID` + `ADZUNA_APP_KEY` | Real listings with salary, company, description |
| **4th** | `GEMINI_API_KEY` | Better resume cache embeddings |
| **5th** | `OPENAI_API_KEY` | Best quality LLM + best embeddings |

With just **Groq + Serper + Adzuna** (all free, no card), you get:
- AI-powered resume parsing, matching, tailoring
- 20–50 real job listings per search
- Full job descriptions with company, salary, location
- Direct apply links

---

## Verifying your keys work

After adding keys to `config.py`, restart the backend:
```bash
uvicorn job_apply_api:app --reload --port 8001
```

Check startup logs:
```
[Startup] Initialising QuickJob Agent...
  [1/4] Trying Gemini...
  [OK] Gemini (gemini-2.5-flash)       ← or whichever LLM is active
  [Startup] Resume cache: active — 0 entries
  [Startup] Ready.
```

Then test job search — you should see in logs:
```
  [Adzuna]  18 jobs in sg (Singapore)
  [Serper]  15 jobs for 'Data Scientist' in Singapore
  [JobSearcher] ✓ Total: 28 jobs found
```