# QuickJob Applier — LLMOps Guide

This document covers how LLM usage is managed, monitored, optimised, and maintained in production.

---

## 1. LLM Usage Philosophy

**Principle:** Every LLM call is a cost. Treat it like a database query — cache aggressively, compact inputs, and only call when no cheaper option exists.

**Token budget (Groq free tier):** 100,000 tokens/day  
**Target per session (cold):** < 15,000 tokens  
**Target per session (warm cache):** < 3,000 tokens

---

## 2. LLM Fallback Chain

The system uses a probe-first fallback pattern. Before returning any LLM, a lightweight test call (`"hi"`) is made. If it fails with a rate limit or auth error, the next provider is tried immediately.

```
get_llm() resolution order:
  1. Gemini 2.5 flash/pro      (GEMINI_API_KEY)
  2. OpenAI gpt-3.5-turbo      (OPENAI_API_KEY)
  3. Claude claude-3-5-sonnet  (CLAUDE_API_KEY)
  4a. Groq llama-3.3-70b       (GROQ_API_KEY)  — 100k tokens/day free
  4b. Groq llama-3.1-8b        (GROQ_API_KEY)  — separate quota, fallback
  ─────────────────────────────────────────────
  RuntimeError if all exhausted → clear error message to user
```

**When Groq 100k daily limit is hit:**
- Error message includes exact reset time
- Automatically falls back to llama-3.1-8b (separate quota)
- If both exhausted: prompts user to wait or add another API key

---

## 3. Prompt Management

All system prompts are stored in `memory/system_prompts.json`. This means:

- Prompts can be tuned without code changes
- Prompts are versioned with the JSON file (commit changes with git)
- All LLM call types have a named, reusable system prompt

### Prompt types

| Key | Used by | Purpose |
|-----|---------|---------|
| `resume_parser` | `ResumeParserTool` | Extract structured resume data |
| `job_title_extractor` | `JobIdentifierTool` | Suggest titles from resume |
| `jd_matcher` | `JDMatcherTool` | Score resume vs JD |
| `experience_rewriter` | `ResumeEnhancerTool` | Rewrite experience bullets |
| `skills_rewriter` | `ResumeEnhancerTool` | Reorder and update skills |
| `ats_scorer` | `ResumeEnhancerTool` | Score enhanced resume as ATS |
| `study_plan_generator` | `ResumeEnhancerTool` | Generate learning plan |
| `cover_letter_writer` | `ResumeEnhancerTool` | Write cover letter |

### Tuning prompts

Edit `memory/system_prompts.json` directly. No code restart required — prompts reload on the next API call.

Example — to make experience bullets more quantified:
```json
{
  "experience_rewriter": "You are a professional resume writer who specialises in quantified achievements. Every bullet point MUST include at least one number, percentage, or dollar amount. Be specific and credible..."
}
```

---

## 4. Context Compaction

Before any LLM call, `llm_cache._compact_messages()` truncates content to the minimum needed for that task. This reduces token usage on every cache miss.

### Resume compaction modes (`memory_manager.compact_resume_for_prompt`)

| Mode | Fields included | Approx tokens | Used for |
|------|----------------|---------------|---------|
| `titles` | name, current role, skills, exp_years | ~200 | Job title extraction |
| `experience` | last 3 jobs only | ~600 | Experience rewriting |
| `skills` | skills + certifications | ~200 | Skills rewriting |
| `match` | skills + 2 recent titles + exp_years | ~400 | JD matching |
| `all` | full resume (descriptions truncated at 200 chars) | ~1,500 | Resume parsing only |

### JD compaction (`memory_manager.compact_jd`)

Strips before sending to LLM:
- Equal opportunity employer boilerplate
- Benefits and compensation sections
- Company background ("About us") sections
- Remaining text capped at 800 characters

A 3,000-character JD typically compresses to 600–900 characters.

---

## 5. Semantic Cache Management

### LLM Response Cache

**Location:** `vector_db/llm_cache/`  
**Similarity threshold:** 88%  
**Key:** SHA-256 of full prompt content  

Every LLM response is stored. Future calls with ≥88% similar prompts return the cached response instantly.

**Monitoring cache health:**
```bash
curl http://localhost:8001/cache-stats
```

Expected response:
```json
{
  "llm_cache": {
    "status": "active",
    "count": 47,
    "by_type": {
      "experience_rewrite": 8,
      "cover_letter": 6,
      "ats_score": 12
    },
    "threshold": 0.88
  }
}
```

### Tuning similarity thresholds

Edit in `llm_cache.py`:
```python
SIMILARITY_THRESHOLD = 0.88   # lower = more cache hits, less accuracy
```

Edit in `resume_cache.py`:
```python
SIMILARITY_THRESHOLD = 0.92   # higher = stricter matching for previews
```

**Trade-off:**
- Too low (< 0.80): unrelated prompts return cached responses → incorrect output
- Too high (> 0.95): similar prompts always miss → no token savings
- Sweet spot: 0.85–0.92 depending on task sensitivity

---

## 6. Token Monitoring

### Groq rate limit errors

When Groq hits its 100k daily limit, the error message includes:
```
Rate limit reached on tokens per day (TPD): Limit 100000, Used 99903
Please try again in 12m55s
```

The system automatically falls back to `llama-3.1-8b-instant` which has a separate quota.

### Estimating session cost

| Operation | Cold cache | Warm cache |
|-----------|-----------|------------|
| Resume parse | ~2,000 | 0 |
| Job title extraction | 0 (taxonomy) | 0 |
| Job search | 0 (API calls) | 0 |
| JD match (per job) | ~400 | 0 |
| Experience rewrite | ~700 | 0 |
| Skills rewrite | ~400 | 0 |
| ATS score (clear cut) | 0 (rule-based) | 0 |
| ATS score (ambiguous) | ~500 | 0 |
| Cover letter | ~500 | 0 |
| Study plan | ~600 | 0 |
| **5 job previews total** | **~12,000** | **0–2,000** |

---

## 7. Embeddings Management

Embeddings are used for semantic similarity search in all three ChromaDB collections.

**Resolution order:**
1. OpenAI `text-embedding-3-small` — best quality, ~$0.00002/query
2. Gemini `models/embedding-001` — free tier, good quality
3. Hash-based fallback — free, exact match only (no semantic search)

**Which collections benefit from embeddings:**
- LLM cache: low importance (prompt keys are usually unique enough for hash)
- Resume preview cache: high importance (similar jobs from same company should match)
- Title cache: high importance (similar resumes should share title suggestions)

**Recommendation:** Add `GEMINI_API_KEY` (free) to get semantic similarity for resume and title caches.

---

## 8. Model Version Management

When a new model version is released (e.g. Groq releases llama-4):

1. Update `agent.py` in the fallback chain
2. Test with a probe call
3. Clear the LLM response cache if the new model gives significantly different outputs:
   ```bash
   rm -rf ~/quick_job_backend/vector_db/llm_cache
   ```

### Known model limitations

| Provider | Limitation | Mitigation |
|----------|-----------|------------|
| Groq | 100k tokens/day free | Fallback to llama-3.1-8b; caching |
| Groq | No embedding API | Hash fallback for semantic cache |
| Gemini | Context window varies | Compaction to 800–6000 chars |
| OpenAI | Cost | Only used as fallback |

---

## 9. Observability

All LLM calls print to the server console with cache hit/miss status:

```
  [LLMCache] Exact hit: experience_rewrite (2026-03-21)
  [LLMCache] Semantic hit: cover_letter (94.2% similar)
  [LLMCache] Miss: study_plan (best=72.1% < 88%) → calling LLM
  [ResumeCache] Exact hit: 'Senior Data Scientist' @ OCBC
  [Memory] Titles resolved from taxonomy: ['Senior Data Scientist', ...]
  [ATS] Rule-based score: 94% (match > 80%)
```

**To see token savings in real-time:** watch the server console during a session. Cache hits show "0 tokens consumed". The ratio of hits to misses tells you how warm the cache is.

---

## 10. Maintenance Tasks

### Weekly
- Check `curl http://localhost:8001/cache-stats` for cache growth
- Review server logs for any `RuntimeError: No LLM available` errors

### Monthly
- Review and update `memory/system_prompts.json` based on output quality
- Add new career categories to `memory/job_title_taxonomy.json`
- Add new title synonyms to `memory/job_title_synonyms.json`
- Clear stale cache entries if `vector_db/` grows beyond 500MB:
  ```bash
  rm -rf ~/quick_job_backend/vector_db/llm_cache
  ```

### When output quality degrades
1. Check if LLM provider changed their model (update `agent.py`)
2. Clear LLM cache (stale responses from old model may be returning)
3. Update system prompts in `memory/system_prompts.json`
4. Adjust context compaction limits in `llm_cache.py`