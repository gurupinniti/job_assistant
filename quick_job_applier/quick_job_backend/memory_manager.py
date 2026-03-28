"""
MemoryManager — Central cache + knowledge coordinator.

Resolution order for every expensive operation (cheapest first):
  1. Memory files  (0 tokens, 0 API calls) — taxonomy, rules, templates
  2. ChromaDB cache (0 tokens) — exact hash or semantic similarity
  3. LLM via llm_cache (tokens only on true miss, then cached)

Context compaction: all prompts are stripped to minimal required tokens.
Long resume texts are truncated to the most relevant sections before
sending to LLM, reducing average prompt size by ~40%.
"""

import json
import re
import hashlib
import math
from pathlib import Path
from typing import Any, Optional
from datetime import datetime

MEMORY_DIR = Path("memory")

# ---------------------------------------------------------------------------
# Load memory files (lazy, cached in-process)
# ---------------------------------------------------------------------------

_mem: dict = {}


def _load(filename: str) -> dict:
    if filename not in _mem:
        path = MEMORY_DIR / filename
        if path.exists():
            try:
                _mem[filename] = json.loads(path.read_text(encoding="utf-8"))
            except Exception as e:
                print(f"  [Memory] Failed to load {filename}: {e}")
                _mem[filename] = {}
        else:
            _mem[filename] = {}
    return _mem[filename]


def get_system_prompt(key: str) -> str:
    return _load("system_prompts.json").get(key, "You are a helpful assistant.")


def get_taxonomy() -> dict:
    return _load("job_title_taxonomy.json")


def get_synonyms() -> dict:
    return _load("job_title_synonyms.json")


def get_ats_rules() -> dict:
    return _load("ats_rules.json")


def get_cover_template(seniority_years: int) -> dict:
    templates = _load("cover_letter_templates.json")
    if seniority_years >= 8:
        return templates.get("senior_roles", templates.get("standard", {}))
    return templates.get("standard", {})


# ---------------------------------------------------------------------------
# Spell correction (uses memory/job_title_synonyms.json, 0 tokens)
# ---------------------------------------------------------------------------

def correct_title_spelling(title: str) -> str:
    """Fix common misspellings in job titles using memory file."""
    misspellings = get_synonyms().get("common_misspellings", {})
    words = title.split()
    corrected = []
    for word in words:
        # Check exact match (case-insensitive)
        for wrong, right in misspellings.items():
            if word.lower() == wrong.lower():
                word = right
                break
        corrected.append(word)
    result = " ".join(corrected)
    if result != title:
        print(f"  [Memory] Spell-corrected: '{title}' → '{result}'")
    return result


def get_synonym_titles(title: str) -> list:
    """Return all synonym titles for a given job title."""
    title_lower = title.lower()
    groups = get_synonyms().get("groups", [])
    for group in groups:
        if any(t.lower() == title_lower for t in group):
            return [t for t in group if t.lower() != title_lower]
    return []


# ---------------------------------------------------------------------------
# Context compaction — reduce prompt size before LLM calls
# ---------------------------------------------------------------------------

def compact_resume_for_prompt(resume_json: str, focus: str = "all") -> str:
    """
    Compact resume JSON to only the fields needed for a given task.
    Reduces token usage by 30-50% vs sending full resume.

    focus options:
      "titles"     — name, current role, skills, exp_years only
      "experience" — last 3 jobs only (for rewriting bullets)
      "skills"     — skills + certifications only
      "match"      — skills + 2 most recent job titles + exp_years
      "all"        — full resume (only when truly needed)
    """
    try:
        r = json.loads(resume_json)
    except Exception:
        return resume_json[:1000]

    if focus == "titles":
        exp = r.get("experience", [{}])
        return json.dumps({
            "name":                   r.get("name", ""),
            "current_role":           exp[0].get("title", "") if exp else "",
            "current_company":        exp[0].get("company", "") if exp else "",
            "total_experience_years": r.get("total_experience_years", 0),
            "skills":                 r.get("skills", [])[:20],
        })

    if focus == "experience":
        return json.dumps({
            "name":     r.get("name", ""),
            "experience": r.get("experience", [])[:3],   # only last 3 jobs
        })

    if focus == "skills":
        return json.dumps({
            "skills":         r.get("skills", []),
            "certifications": r.get("certifications", []),
        })

    if focus == "match":
        exp = r.get("experience", [])
        return json.dumps({
            "total_experience_years": r.get("total_experience_years", 0),
            "skills":                 r.get("skills", [])[:25],
            "recent_titles":          [e.get("title", "") for e in exp[:2]],
        })

    # "all" — strip only truly unnecessary fields, keep descriptions short
    compact = dict(r)
    for job in compact.get("experience", []):
        desc = job.get("description", "")
        if len(desc) > 200:
            job["description"] = desc[:200] + "..."
    return json.dumps(compact)


def compact_jd(jd_text: str, max_chars: int = 800) -> str:
    """
    Extract the most token-efficient representation of a JD.
    Keeps: title, required skills, key responsibilities.
    Drops: company boilerplate, benefits, equal opportunity text.
    """
    if len(jd_text) <= max_chars:
        return jd_text

    # Remove common boilerplate patterns
    boilerplate = [
        r"(?i)we are an equal opportunity employer.*",
        r"(?i)we offer.*?(?=\n\n|\Z)",
        r"(?i)benefits include.*?(?=\n\n|\Z)",
        r"(?i)about (us|the company|our company).*?(?=\n\n|\Z)",
        r"(?i)compensation.*?(?=\n\n|\Z)",
        r"(?i)salary.*?(?=\n\n|\Z)",
    ]
    cleaned = jd_text
    for pat in boilerplate:
        cleaned = re.sub(pat, "", cleaned, flags=re.DOTALL)

    # Extract key sections
    sections = re.split(r'\n\n+', cleaned.strip())
    # Prioritise sections with skill/requirement keywords
    priority_keywords = ["require", "must have", "skill", "qualification",
                         "responsibilit", "you will", "experience with"]
    priority, rest = [], []
    for s in sections:
        sl = s.lower()
        if any(k in sl for k in priority_keywords):
            priority.append(s)
        else:
            rest.append(s)

    result = "\n\n".join(priority + rest)
    return result[:max_chars]


# ---------------------------------------------------------------------------
# Resume fingerprinting
# ---------------------------------------------------------------------------

def resume_fingerprint(resume_json: str) -> str:
    """
    Stable fingerprint keyed ONLY on identity fields that never change:
    name + email + company names (first 3).

    Deliberately excludes skills — the LLM parser extracts slightly
    different skills each run (even at low temperature), which would
    produce a different fingerprint and defeat caching.
    """
    try:
        r     = json.loads(resume_json)
        name  = (r.get("name", "") or "").lower().strip()
        email = (r.get("email", "") or "").lower().strip()
        # Use company names from experience — these are stable identifiers
        comps = sorted([
            (e.get("company", "") or "").lower().strip()
            for e in r.get("experience", []) if e.get("company")
        ])
        # Also use current job title — stable and highly specific
        current_title = ""
        exp = r.get("experience", [])
        if exp:
            current_title = (exp[0].get("title", "") or "").lower().strip()

        key = f"{name}|{email}|{current_title}|{','.join(comps[:3])}"
        return hashlib.sha256(key.encode()).hexdigest()[:20]
    except Exception:
        return hashlib.sha256(resume_json[:500].encode()).hexdigest()[:20]


# ---------------------------------------------------------------------------
# Job title resolution — taxonomy first, LLM only as fallback
# Orders by: current role → synonyms → category matches → other
# ---------------------------------------------------------------------------

def resolve_job_titles_from_taxonomy(resume_json: str) -> Optional[dict]:
    """
    Resolve job titles WITHOUT calling LLM.
    Title order: current/recent roles first → synonyms → category matches.
    """
    try:
        resume    = json.loads(resume_json)
        skills    = [s.lower() for s in resume.get("skills", [])]
        exp_years = int(resume.get("total_experience_years", 0) or 0)
        taxonomy  = get_taxonomy()
        categories = taxonomy.get("categories", {})

        # ── Step 1: Get current/recent job titles from resume ────────────
        experience = resume.get("experience", [])
        recent_titles = []
        for exp in experience[:3]:  # top 3 most recent jobs
            title = exp.get("title", "").strip()
            if title:
                recent_titles.append(title)

        # ── Step 2: Expand with synonyms ─────────────────────────────────
        synonym_titles = []
        for rt in recent_titles:
            synonyms = get_synonym_titles(rt)
            synonym_titles.extend(synonyms)

        # ── Step 3: Taxonomy skill matching ──────────────────────────────
        # Build a flat searchable text from all skills for substring matching.
        # This handles cases where resume has "PyTorch" but signal is "pytorch",
        # or resume has "ML Ops" but signal is "mlops".
        skills_text = " ".join(skills)   # full concatenated skills string

        matched_categories = []
        for cat_name, cat_data in categories.items():
            signals = [s.lower() for s in cat_data.get("skill_signals", [])]
            # Count how many signals appear anywhere in the skills text
            matches = sum(1 for sig in signals if sig in skills_text)
            # Also check each skill individually to catch multi-word skills
            matches += sum(
                1 for sig in signals
                if any(sig in skill for skill in skills)
                and sig not in skills_text  # avoid double-counting
            )
            # Threshold: 1 match always sufficient — taxonomy is now specific enough
            if matches >= 1:
                matched_categories.append((cat_name, matches, cat_data))

        if not matched_categories and not recent_titles:
            # Last resort: try matching job title text against category names
            for cat_name, cat_data in categories.items():
                signals = [s.lower() for s in cat_data.get("skill_signals", [])]
                title_text = " ".join(recent_titles).lower()
                title_matches = sum(1 for sig in signals if sig in title_text)
                if title_matches >= 1:
                    matched_categories.append((cat_name, title_matches, cat_data))

        if not matched_categories and not recent_titles:
            return None  # genuine taxonomy miss — LLM needed

        # Even with no category match, if we have recent_titles we can return them
        # with no taxonomy expansion — still 100% deterministic, 0 tokens
        if not matched_categories and recent_titles:
            print(f"  [Memory] No category match — returning recent titles only: {recent_titles[:2]}")

        # Seniority bracket
        bracket = "0-2"
        if exp_years >= 10:  bracket = "10+"
        elif exp_years >= 6: bracket = "6-9"
        elif exp_years >= 3: bracket = "3-5"

        # Taxonomy titles for this seniority
        taxonomy_titles = []
        matched_categories.sort(key=lambda x: x[1], reverse=True)
        for _, _, cat_data in matched_categories[:2]:
            by_years = cat_data.get("titles_by_years", {})
            taxonomy_titles.extend(by_years.get(bracket, by_years.get("3-5", [])))

        # ── Step 4: Build ordered list ───────────────────────────────────
        # Order: current title → synonyms of current → taxonomy matches
        seen, ordered = set(), []
        for t in recent_titles + synonym_titles + taxonomy_titles:
            if t and t not in seen:
                seen.add(t)
                ordered.append(t)

        if not ordered:
            return None

        result = {
            "primary_titles":     ordered[:4],
            "all_titles":         ordered[:12],
            "seniority":          bracket,
            "exp_years":          exp_years,
            "matched_categories": [c[0] for c in matched_categories[:2]],
            "source":             "taxonomy",
        }
        print(f"  [Memory] Titles resolved: {ordered[:3]} ({exp_years}yrs, bracket={bracket})")
        # Proactively store in title cache so next upload is instant (0 tokens)
        store_titles_cache(resume_json, result)
        return result

    except Exception as e:
        print(f"  [Memory] Taxonomy lookup failed: {e}")
        return None


# ---------------------------------------------------------------------------
# ATS quick-score (rule-based, 0 tokens)
# ---------------------------------------------------------------------------

def quick_ats_score(resume_json: str, jd_text: str, match: dict) -> Optional[dict]:
    """Rule-based ATS score for clear-cut cases. Returns None for LLM."""
    try:
        matched   = match.get("matched_skills", [])
        missing   = match.get("missing_skills", [])
        total     = len(matched) + len(missing)
        if total == 0:
            return None
        pct = int((len(matched) / total) * 100)
        if pct >= 80:
            return {"ats_score": min(98, 75 + pct // 5),
                    "keyword_match_pct": pct, "format_score": 85,
                    "improvements": ["Add more quantified achievements"],
                    "source": "rule_based"}
        if pct < 30:
            return {"ats_score": max(25, pct),
                    "keyword_match_pct": pct, "format_score": 70,
                    "improvements": [f"Add skills: {', '.join(missing[:4])}"],
                    "source": "rule_based"}
        return None
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Job title cache (ChromaDB)
# ---------------------------------------------------------------------------

_title_collection = None
_title_embed_fn   = None


def init_title_cache(llm: Any = None) -> None:
    global _title_collection, _title_embed_fn
    try:
        import chromadb
        db_dir = Path("vector_db/title_cache")
        db_dir.mkdir(parents=True, exist_ok=True)
        client = chromadb.PersistentClient(path=str(db_dir))
        _title_collection = client.get_or_create_collection(
            name="job_titles",
            metadata={"hnsw:space": "cosine"},
        )
        print(f"  [Memory] Title cache: {_title_collection.count()} entries")
        if llm:
            _title_embed_fn = _make_embed_fn(llm)
    except Exception as e:
        print(f"  [Memory] Title cache init failed: {e}")


def _make_embed_fn(llm):
    """
    Resolve embedding function. Tests each provider with a probe call
    so billing/auth errors are caught here, not silently at lookup time.
    Order: Gemini (free) → OpenAI → hash fallback
    """
    import config

    # ── 1. Gemini embeddings (free tier) ─────────────────────────────────────
    try:
        if getattr(config, "GEMINI_API_KEY", ""):
            from langchain_google_genai import GoogleGenerativeAIEmbeddings
            e = GoogleGenerativeAIEmbeddings(
                model="models/embedding-001",
                google_api_key=config.GEMINI_API_KEY,
            )
            e.embed_query("test")   # probe — catches billing/quota errors
            print("  [Memory] Embeddings: Gemini embedding-001")
            return lambda t: e.embed_query(t)
    except Exception as ex:
        print(f"  [Memory] Gemini embeddings failed ({ex.__class__.__name__}) — trying OpenAI")

    # ── 2. OpenAI embeddings (paid) ───────────────────────────────────────────
    try:
        if getattr(config, "OPENAI_API_KEY", ""):
            from langchain_openai import OpenAIEmbeddings
            e = OpenAIEmbeddings(model="text-embedding-3-small", api_key=config.OPENAI_API_KEY)
            e.embed_query("test")   # probe
            print("  [Memory] Embeddings: OpenAI text-embedding-3-small")
            return lambda t: e.embed_query(t)
    except Exception as ex:
        print(f"  [Memory] OpenAI embeddings failed ({ex.__class__.__name__}) — using hash fallback")

    # ── 3. Hash fallback (always works, exact-match only) ─────────────────────
    print("  [Memory] Embeddings: hash fallback (semantic search disabled)")
    return _hash_embed



def _hash_embed(text: str) -> list:
    words = text.lower().split()
    vec   = [0.0] * 256
    for w in words:
        h = int(hashlib.md5(w.encode()).hexdigest(), 16)
        for i in range(4):
            vec[(h >> (i * 8)) % 256] += 1.0
    norm = math.sqrt(sum(x * x for x in vec)) or 1.0
    return [x / norm for x in vec]


def _resume_embed_text(resume_json: str) -> str:
    """Compact embedding text — skills + roles only."""
    try:
        r     = json.loads(resume_json)
        exp   = r.get("experience", [{}])
        roles = " ".join(e.get("title", "") for e in exp[:3])
        skills = ", ".join(r.get("skills", [])[:15])
        return f"{roles} {skills} {r.get('total_experience_years', 0)}yrs"
    except Exception:
        return resume_json[:200]


def lookup_titles_cache(resume_json: str, threshold: float = 0.92) -> Optional[dict]:
    if not _title_collection:
        return None
    fp = resume_fingerprint(resume_json)
    # Exact fingerprint
    try:
        exact = _title_collection.get(ids=[fp])
        if exact and exact["ids"]:
            print(f"  [Memory] Title cache exact hit ({fp[:8]})")
            return _unpack_title_meta(exact["metadatas"][0])
    except Exception: pass
    # Semantic
    if not _title_embed_fn:
        return None
    try:
        emb  = _title_embed_fn(_resume_embed_text(resume_json))
        res  = _title_collection.query(query_embeddings=[emb], n_results=1,
                                        include=["metadatas", "distances"])
        if res["ids"] and res["ids"][0]:
            sim = 1 - res["distances"][0][0]
            if sim >= threshold:
                print(f"  [Memory] Title cache semantic hit ({sim:.1%})")
                return _unpack_title_meta(res["metadatas"][0][0])
            print(f"  [Memory] Title cache miss ({sim:.1%} < {threshold:.0%})")
    except Exception as e:
        print(f"  [Memory] Title cache error: {e}")
    return None


def store_titles_cache(resume_json: str, result: dict) -> None:
    if not _title_collection:
        return
    try:
        fp         = resume_fingerprint(resume_json)
        embed_text = _resume_embed_text(resume_json)
        emb        = _title_embed_fn(embed_text) if _title_embed_fn else [0.0]*256
        _title_collection.upsert(
            ids=[fp], embeddings=[emb],
            documents=[embed_text],
            metadatas=[{
                "primary_titles":     json.dumps(result.get("primary_titles", [])),
                "all_titles":         json.dumps(result.get("all_titles", [])),
                "seniority":          result.get("seniority", ""),
                "exp_years":          str(result.get("exp_years", 0)),
                "matched_categories": json.dumps(result.get("matched_categories", [])),
                "source":             result.get("source", "llm"),
                "stored_at":          datetime.now().isoformat(),
            }],
        )
        print(f"  [Memory] Title stored ({fp[:8]}): {result.get('primary_titles', [])[:2]}")
    except Exception as e:
        print(f"  [Memory] Title store error: {e}")


def _unpack_title_meta(m: dict) -> dict:
    def p(s, d):
        try: return json.loads(s) if s else d
        except: return d
    return {
        "primary_titles":     p(m.get("primary_titles"), []),
        "all_titles":         p(m.get("all_titles"), []),
        "seniority":          m.get("seniority", ""),
        "exp_years":          int(m.get("exp_years", 0) or 0),
        "matched_categories": p(m.get("matched_categories"), []),
        "source":             "cache",
    }