"""
LLM Response Cache — ChromaDB-backed semantic cache for ALL LLM calls.

Every LLM prompt/response pair is stored. Before calling LLM:
  1. Hash check (exact match) → return cached instantly
  2. Semantic similarity check → if >88% similar, return cached
  3. Only call LLM if no cache hit

This prevents token waste on repeated/similar prompts.
Stores: resume parsing, JD matching, ATS scoring, study plans, cover letters.
"""

import json
import hashlib
import re
from pathlib import Path
from datetime import datetime
from typing import Any, Optional

CACHE_DB_DIR         = Path("vector_db/llm_cache")
SIMILARITY_THRESHOLD = 0.88   # 88% similar → reuse cached response
_collection          = None
_embed_fn            = None


# ---------------------------------------------------------------------------
# Init
# ---------------------------------------------------------------------------

def init(llm: Any = None) -> None:
    global _collection, _embed_fn
    CACHE_DB_DIR.mkdir(parents=True, exist_ok=True)
    try:
        import chromadb
        client      = chromadb.PersistentClient(path=str(CACHE_DB_DIR))
        _collection = client.get_or_create_collection(
            name="llm_responses",
            metadata={"hnsw:space": "cosine"},
        )
        print(f"  [LLMCache] Ready — {_collection.count()} cached responses")
    except Exception as e:
        print(f"  [LLMCache] ChromaDB init failed: {e}")
        return

    if llm:
        _embed_fn = _make_embed_fn(llm)


def _make_embed_fn(llm):
    """Use OpenAI or Gemini embeddings if available, else hash fallback."""
    
    # Try OpenAI first
    try:
        import config
        if getattr(config, "OPENAI_API_KEY", ""):
            from langchain_openai import OpenAIEmbeddings
            emb = OpenAIEmbeddings(model="text-embedding-3-small", api_key=config.OPENAI_API_KEY)
            print("  [LLMCache] Embeddings: OpenAI text-embedding-3-small")
            
            def openai_embed_with_fallback(t: str) -> list:
                try:
                    return emb.embed_query(t)
                except Exception as e:
                    msg = str(e)
                    if 'billing_not_active' in msg or 'account is not active' in msg or '429' in msg:
                        print(f"  [LLMCache] OpenAI billing/quota error, falling back to Gemini or hash")
                        # Fall through to try Gemini or hash
                    else:
                        print(f"  [LLMCache] OpenAI embedding error: {msg}")
                    raise RuntimeError("OpenAI embedding failed")
            
            return openai_embed_with_fallback
    except Exception: 
        pass
    
    # Fall back to Gemini
    try:
        import config
        if getattr(config, "GEMINI_API_KEY", ""):
            from langchain_google_genai import GoogleGenerativeAIEmbeddings
            emb = GoogleGenerativeAIEmbeddings(model="models/embedding-001", google_api_key=config.GEMINI_API_KEY)
            print("  [LLMCache] Embeddings: Gemini embedding-001")
            
            def gemini_embed_with_fallback(t: str) -> list:
                try:
                    return emb.embed_query(t)
                except Exception as e:
                    print(f"  [LLMCache] Gemini embedding error: {e}, falling back to hash")
                    raise RuntimeError("Gemini embedding failed")
            
            return gemini_embed_with_fallback
    except Exception: 
        pass

    # Hash-based fallback
    import math
    def hash_embed(text: str) -> list:
        words = re.sub(r'[^\w\s]', ' ', text.lower()).split()
        vec   = [0.0] * 256
        for w in words:
            h = int(hashlib.md5(w.encode()).hexdigest(), 16)
            for i in range(4):
                vec[(h >> (i * 8)) % 256] += 1.0
        norm = math.sqrt(sum(x*x for x in vec)) or 1.0
        return [x / norm for x in vec]

    print("  [LLMCache] Embeddings: hash fallback (add OPENAI_API_KEY or GEMINI_API_KEY for semantic search)")
    return hash_embed


# ---------------------------------------------------------------------------
# Cache key
# ---------------------------------------------------------------------------

def _key(prompt: str) -> str:
    return hashlib.sha256(prompt.encode()).hexdigest()[:20]


def _short(text: str, n: int = 500) -> str:
    """Truncate for embedding — keeps most significant content."""
    return text[:n]


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def get(prompt: str, prompt_type: str = "general") -> Optional[str]:
    """
    Look up a prompt in cache.
    Returns cached response string if found, else None.
    """
    if not _collection or not _embed_fn:
        return None

    key = _key(prompt)

    # 1. Exact match
    try:
        exact = _collection.get(ids=[key])
        if exact and exact["ids"]:
            meta = exact["metadatas"][0]
            print(f"  [LLMCache] Exact hit: {prompt_type} ({meta.get('cached_at','')[:10]})")
            return exact["documents"][0] if exact.get("documents") else meta.get("response", "")
    except Exception:
        pass

    # 2. Semantic search
    try:
        emb     = _embed_fn(_short(prompt))
        results = _collection.query(
            query_embeddings=[emb],
            n_results=1,
            include=["documents", "metadatas", "distances"],
            where={"prompt_type": prompt_type} if prompt_type != "general" else None,
        )
        if results["ids"] and results["ids"][0]:
            dist       = results["distances"][0][0]
            similarity = 1 - dist
            if similarity >= SIMILARITY_THRESHOLD:
                meta = results["metadatas"][0][0]
                resp = results["documents"][0][0] if results.get("documents") else ""
                print(f"  [LLMCache] Semantic hit: {prompt_type} ({similarity:.1%} similar)")
                return resp
            else:
                print(f"  [LLMCache] Miss: {prompt_type} (best={similarity:.1%} < {SIMILARITY_THRESHOLD:.0%})")
    except RuntimeError as e:
        # Embedding provider failed (OpenAI billing, etc.) — use hash fallback
        print(f"  [LLMCache] Embedding provider failed ({e}), falling back to hash")
        try:
            # Try to get hash-based embedding again
            import hashlib, math, re
            words = re.sub(r'[^\w\s]', ' ', _short(prompt).lower()).split()
            vec   = [0.0] * 256
            for w in words:
                h = int(hashlib.md5(w.encode()).hexdigest(), 16)
                for i in range(4):
                    vec[(h >> (i * 8)) % 256] += 1.0
            norm = math.sqrt(sum(x*x for x in vec)) or 1.0
            hash_emb = [x / norm for x in vec]
            
            results = _collection.query(
                query_embeddings=[hash_emb],
                n_results=1,
                include=["documents", "metadatas", "distances"],
                where={"prompt_type": prompt_type} if prompt_type != "general" else None,
            )
            if results["ids"] and results["ids"][0]:
                dist       = results["distances"][0][0]
                similarity = 1 - dist
                if similarity >= SIMILARITY_THRESHOLD:
                    resp = results["documents"][0][0] if results.get("documents") else ""
                    print(f"  [LLMCache] Hash-based hit: {prompt_type} ({similarity:.1%} similar)")
                    return resp
        except Exception as hash_err:
            print(f"  [LLMCache] Hash fallback also failed: {hash_err}")
    except Exception as e:
        print(f"  [LLMCache] Lookup error: {e}")

    return None


def store(prompt: str, response: str, prompt_type: str = "general") -> None:
    """Store a prompt/response pair."""
    if not _collection or not _embed_fn:
        return
    try:
        key = _key(prompt)
        emb = _embed_fn(_short(prompt))
        _collection.upsert(
            ids=[key],
            embeddings=[emb],
            documents=[response],
            metadatas=[{
                "prompt_type": prompt_type,
                "prompt_preview": prompt[:200],
                "cached_at": datetime.now().isoformat(),
                "response_len": str(len(response)),
            }],
        )
    except Exception as e:
        print(f"  [LLMCache] Store error: {e}")


def _compact_messages(messages: list, prompt_type: str) -> list:
    """
    Context compaction: truncate large message content per prompt type.
    Reduces token usage before the LLM call and before caching the key.
    """
    MAX_CONTENT = {
        "experience_rewrite": 4000,
        "skills_rewrite":     2000,
        "ats_score":          2500,
        "cover_letter":       2000,
        "study_plan":         2000,
        "jd_match":           3000,
        "resume_parse":       6000,
        "job_title_extractor": 1500,
        "general":            4000,
    }
    max_len = MAX_CONTENT.get(prompt_type, 4000)
    compacted = []
    for m in messages:
        raw = m.content if hasattr(m, "content") else str(m)
        if isinstance(raw, str) and len(raw) > max_len:
            raw = raw[:max_len] + "\n[...truncated for token efficiency]"
            try:
                compacted.append(type(m)(content=raw))
            except Exception:
                compacted.append(m)
        else:
            compacted.append(m)
    return compacted


def cached_llm_call(llm: Any, messages: list, prompt_type: str = "general") -> str:
    """
    Drop-in LLM caller with automatic semantic caching.
    Accepts: LangChain message objects OR plain strings.
    
    Usage:
        from langchain_core.messages import SystemMessage, HumanMessage
        result = cached_llm_call(llm,
            [SystemMessage(content="..."), HumanMessage(content="...")],
            "ats_score"
        )
    """
    # Build cache key — extract content from message objects
    def _content(m):
        if hasattr(m, "content"):
            return m.content if isinstance(m.content, str) else str(m.content)
        return str(m)

    prompt_key = " | ".join(_content(m) for m in messages)

    cached = get(prompt_key, prompt_type)
    if cached:
        return cached

    # Handle SystemMessage-like objects that aren't proper LangChain types
    from langchain_core.messages import SystemMessage, HumanMessage
    lc_messages = []
    for m in messages:
        if isinstance(m, (SystemMessage, HumanMessage)):
            lc_messages.append(m)
        elif hasattr(m, "content"):
            # Duck-typed — try to determine role
            role = getattr(m, "role", "human")
            if role == "system" or "system" in type(m).__name__.lower():
                lc_messages.append(SystemMessage(content=_content(m)))
            else:
                lc_messages.append(HumanMessage(content=_content(m)))
        else:
            lc_messages.append(HumanMessage(content=str(m)))

    # Context compaction — reduce tokens before LLM call
    compacted = _compact_messages(lc_messages, prompt_type)
    resp = llm.invoke(compacted)
    text = resp.content if isinstance(resp.content, str) else str(resp.content)

    store(prompt_key, text, prompt_type)
    return text


def stats() -> dict:
    if not _collection:
        return {"status": "disabled", "count": 0}
    by_type = {}
    try:
        all_meta = _collection.get(include=["metadatas"])
        for m in (all_meta.get("metadatas") or []):
            pt = m.get("prompt_type", "unknown")
            by_type[pt] = by_type.get(pt, 0) + 1
    except Exception:
        pass
    return {
        "status":    "active",
        "count":     _collection.count(),
        "by_type":   by_type,
        "threshold": SIMILARITY_THRESHOLD,
    }