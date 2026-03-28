"""
Resume Cache — ChromaDB + LLM embeddings (no sentence-transformers).

Uses the same LLM provider already selected (Groq/Gemini/OpenAI/Claude)
to generate embeddings. Falls back to a simple TF-IDF hash if the LLM
doesn't support embeddings.

Cache lives in: quick_job_backend/vector_db/
"""

import os
import json
import hashlib
from pathlib import Path
from datetime import datetime

VECTOR_DB_DIR        = Path("vector_db")
CACHE_META_DIR       = VECTOR_DB_DIR / "meta"
SIMILARITY_THRESHOLD = 0.92

_chroma_client     = None
_chroma_collection = None
_embed_fn          = None     # set by init_cache(llm)


# ---------------------------------------------------------------------------
# Embedding function — uses whichever LLM is active
# ---------------------------------------------------------------------------

def _make_embedding_fn(llm):
    """
    Return a function that converts text → embedding vector.
    Tries LLM-specific embedding APIs in order.
    Falls back to deterministic TF-IDF style hash vector.
    """

    # 1. OpenAI embeddings
    try:
        from langchain_openai import OpenAIEmbeddings
        import config
        if getattr(config, "OPENAI_API_KEY", ""):
            embeddings = OpenAIEmbeddings(
                model="text-embedding-3-small",
                api_key=config.OPENAI_API_KEY,
            )
            def openai_embed(text: str) -> list:
                try:
                    return embeddings.embed_query(text)
                except Exception as e:
                    msg = str(e)
                    if 'billing_not_active' in msg or 'account is not active' in msg or '429' in msg:
                        print(f"  [ResumeCache] OpenAI error: {msg}\n  Falling back to Gemini or hash embedding.")
                        raise RuntimeError("OpenAI billing/account error")
                    else:
                        print(f"  [ResumeCache] OpenAI embedding error: {msg}")
                        raise
            print("  [ResumeCache] Using OpenAI embeddings (text-embedding-3-small)")
            return openai_embed
    except Exception as e:
        print(f"  [ResumeCache] OpenAI embedding setup failed: {e}")

    # 2. Google Generative AI embeddings
    try:
        from langchain_google_genai import GoogleGenerativeAIEmbeddings
        import config
        if getattr(config, "GEMINI_API_KEY", ""):
            embeddings = GoogleGenerativeAIEmbeddings(
                model="models/embedding-001",
                google_api_key=config.GEMINI_API_KEY,
            )
            def gemini_embed(text: str) -> list:
                return embeddings.embed_query(text)
            print("  [ResumeCache] Using Gemini embeddings (embedding-001)")
            return gemini_embed
    except Exception:
        pass

    # 3. Groq doesn't offer embeddings — use a deterministic hash vector fallback
    print("  [ResumeCache] No embedding API available — using hash-based fallback")
    print("  [ResumeCache] Tip: add OPENAI_API_KEY or GEMINI_API_KEY for semantic search")

    def hash_embed(text: str) -> list:
        """
        Deterministic 384-dim pseudo-embedding from word hashing.
        Not semantic but gives exact-match caching when hash matches.
        """
        import math
        words = text.lower().split()
        vec   = [0.0] * 384
        for w in words:
            h = int(hashlib.md5(w.encode()).hexdigest(), 16)
            for i in range(4):
                idx = (h >> (i * 8)) % 384
                vec[idx] += 1.0
        # L2 normalise
        norm = math.sqrt(sum(x*x for x in vec)) or 1.0
        return [x / norm for x in vec]

    return hash_embed


# ---------------------------------------------------------------------------
# ChromaDB setup
# ---------------------------------------------------------------------------

def _get_collection():
    global _chroma_client, _chroma_collection
    if _chroma_collection is None:
        try:
            import chromadb
            VECTOR_DB_DIR.mkdir(parents=True, exist_ok=True)
            CACHE_META_DIR.mkdir(parents=True, exist_ok=True)
            _chroma_client     = chromadb.PersistentClient(path=str(VECTOR_DB_DIR))
            _chroma_collection = _chroma_client.get_or_create_collection(
                name="resume_cache",
                metadata={"hnsw:space": "cosine"},
            )
            print(f"  [ResumeCache] ChromaDB ready — {_chroma_collection.count()} cached entries")
        except ImportError:
            print("  [ResumeCache] chromadb not installed — cache disabled. Run: pip install chromadb")
        except Exception as e:
            print(f"  [ResumeCache] ChromaDB init failed: {e}")
    return _chroma_collection


def init_cache(llm) -> None:
    """Call once at startup with the active LLM to set up embedding function."""
    global _embed_fn
    _embed_fn = _make_embedding_fn(llm)
    _get_collection()


# ---------------------------------------------------------------------------
# Cache key helpers
# ---------------------------------------------------------------------------

def _make_cache_key(resume_json: str, job_title: str, company: str, jd_text: str) -> str:
    raw = f"{resume_json[:2000]}|{job_title}|{company}|{jd_text[:500]}"
    return hashlib.sha256(raw.encode()).hexdigest()[:16]


def _make_embed_text(resume_json: str, job_title: str, company: str, jd_text: str) -> str:
    try:
        resume = json.loads(resume_json)
        skills = ", ".join(resume.get("skills", [])[:20])
        exp    = resume.get("total_experience_years", 0)
    except Exception:
        skills, exp = "", 0
    return (
        f"Job: {job_title} at {company}. "
        f"JD: {jd_text[:300]}. "
        f"Candidate skills: {skills}. "
        f"Experience: {exp} years."
    )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def lookup(resume_json: str, job_title: str, company: str, jd_text: str) -> dict | None:
    collection = _get_collection()
    if not collection or not _embed_fn:
        return None

    # 1. Exact hash — zero LLM calls
    cache_key = _make_cache_key(resume_json, job_title, company, jd_text)
    try:
        exact = collection.get(ids=[cache_key])
        if exact and exact["ids"]:
            meta        = exact["metadatas"][0]
            cached_path = Path(meta.get("resume_path", ""))
            if cached_path.exists():
                print(f"  [ResumeCache] ✓ Exact hit: '{job_title}' @ {company}")
                return _load_cached(meta)
    except Exception:
        pass

    # 2. Semantic similarity
    try:
        embed_text = _make_embed_text(resume_json, job_title, company, jd_text)
        embedding  = _embed_fn(embed_text)
        results    = collection.query(
            query_embeddings=[embedding],
            n_results=1,
            include=["metadatas", "distances"],
        )
        if results["ids"] and results["ids"][0]:
            distance   = results["distances"][0][0]
            similarity = 1 - distance
            meta       = results["metadatas"][0][0]
            print(f"  [ResumeCache] Nearest similarity: {similarity:.1%} for '{job_title}'")
            if similarity >= SIMILARITY_THRESHOLD and Path(meta.get("resume_path", "")).exists():
                print(f"  [ResumeCache] ✓ Semantic hit ({similarity:.1%}) — reusing")
                return _load_cached(meta)
    except Exception as e:
        print(f"  [ResumeCache] Lookup error: {e}")

    return None


def store(resume_json: str, job_title: str, company: str,
          jd_text: str, build: dict, match: dict,
          study_plan: dict = None, edit_summary: dict = None) -> None:
    collection = _get_collection()
    if not collection or not _embed_fn:
        return
    try:
        cache_key     = _make_cache_key(resume_json, job_title, company, jd_text)
        embed_text    = _make_embed_text(resume_json, job_title, company, jd_text)
        embedding     = _embed_fn(embed_text)

        resume_path   = build.get("resume_path", "")
        cover_path    = build.get("cover_letter_path", "")
        output_folder = build.get("output_folder", "")

        # Derive .txt paths — enhancer saves them alongside PDFs
        resume_txt = build.get("resume_txt_path",
                     str(Path(resume_path).with_suffix(".txt")) if resume_path else "")
        cover_txt  = build.get("cover_txt_path",
                     str(Path(cover_path).with_suffix(".txt"))  if cover_path  else "")

        # Store study_plan and edit_summary as JSON strings (ChromaDB meta = strings only)
        meta = {
            "job_title":       job_title,
            "company":         company,
            "resume_path":     resume_path,
            "cover_path":      cover_path,
            "resume_txt_path": resume_txt,
            "cover_txt_path":  cover_txt,
            "output_folder":   output_folder,
            "ats_score":       str(build.get("ats_score", 0)),
            "match_score":     str(match.get("match_score", 0)),
            "verdict":         match.get("verdict", ""),
            "matched_skills":  json.dumps(match.get("matched_skills", [])),
            "missing_skills":  json.dumps(match.get("missing_skills", [])),
            "study_plan":      json.dumps(study_plan or {}),
            "edit_summary":    json.dumps(edit_summary or {}),
            "cached_at":       datetime.now().isoformat(),
        }
        collection.upsert(ids=[cache_key], embeddings=[embedding],
                          metadatas=[meta], documents=[embed_text])
        print(f"  [ResumeCache] Stored: '{job_title}' @ {company} (ATS: {build.get('ats_score')}%)")
    except Exception as e:
        print(f"  [ResumeCache] Store error: {e}")


def _load_cached(meta: dict) -> dict:
    def read(p):
        p = Path(p)
        if p.exists():
            try:    return p.read_text(encoding="utf-8")
            except: return p.read_bytes().decode("latin-1", errors="replace")
        return ""

    def parse_json(s, default):
        try:    return json.loads(s) if s else default
        except: return default

    return {
        "from_cache":     True,
        "ats_score":      int(float(meta.get("ats_score", 0) or 0)),
        "match_score":    int(float(meta.get("match_score", 0) or 0)),
        "verdict":        meta.get("verdict", ""),
        "matched_skills": parse_json(meta.get("matched_skills"), []),
        "missing_skills": parse_json(meta.get("missing_skills"), []),
        "resume_text":    read(meta.get("resume_txt_path") or meta.get("resume_path", "")),
        "cover_text":     read(meta.get("cover_txt_path")  or meta.get("cover_path", "")),
        "resume_path":    meta.get("resume_path", ""),
        "cover_path":     meta.get("cover_path", ""),
        "output_folder":  meta.get("output_folder", ""),
        "study_plan":     parse_json(meta.get("study_plan"), {}),
        "edit_summary":   parse_json(meta.get("edit_summary"), {}),
        "cached_at":      meta.get("cached_at", ""),
    }


def stats() -> dict:
    collection = _get_collection()
    if not collection:
        return {"status": "disabled", "count": 0, "embed_fn": "none"}
    embed_name = getattr(_embed_fn, "__name__", "unknown") if _embed_fn else "not initialised"
    return {
        "status":    "active",
        "count":     collection.count(),
        "db_dir":    str(VECTOR_DB_DIR.absolute()),
        "threshold": SIMILARITY_THRESHOLD,
        "embed_fn":  embed_name,
    }