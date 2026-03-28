"""
Job Search Cache — filesystem + in-memory cache for job listings.

Strategy:
  Key  = SHA-256(sorted_titles + country + sorted_portals)
  TTL  = 24 hours (job listings go stale quickly)
  Store= JSON files in vector_db/job_cache/

On hit:
  - Return cached jobs instantly (0 API calls, 0 LLM tokens)
  - Filter/merge with any new job titles not yet in cache

On miss:
  - Run live search, store result

Benefits:
  - Same search (same titles + country) never hits APIs twice in 24h
  - New titles added to existing search = filter from cache + small incremental fetch
  - Completely LLM-free — pure HTTP API caching
"""

import json
import hashlib
import time
from pathlib import Path
from typing import Optional

CACHE_DIR = Path("vector_db/job_cache")
TTL_SECONDS = 86400   # 24 hours

_mem_cache: dict = {}   # in-process memory cache for current server session


def _make_key(titles: list, country: str, portals: list) -> str:
    raw = f"{sorted(titles)}|{country.lower()}|{sorted(portals)}"
    return hashlib.sha256(raw.encode()).hexdigest()[:24]


def _cache_path(key: str) -> Path:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    return CACHE_DIR / f"{key}.json"


def _is_fresh(cached_at: float) -> bool:
    return (time.time() - cached_at) < TTL_SECONDS


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def lookup(titles: list, country: str, portals: list) -> Optional[list]:
    """
    Return cached job listings if available and fresh.
    Returns None on cache miss or stale cache.
    """
    key = _make_key(titles, country, portals)

    # 1. In-memory (fastest — survives within same server process)
    if key in _mem_cache:
        entry = _mem_cache[key]
        if _is_fresh(entry["cached_at"]):
            age_min = int((time.time() - entry["cached_at"]) / 60)
            print(f"  [JobCache] Memory hit: {len(entry['jobs'])} jobs "
                  f"({age_min}m old) for {titles[:2]}")
            return entry["jobs"]
        else:
            del _mem_cache[key]

    # 2. Filesystem (survives backend restarts)
    path = _cache_path(key)
    if path.exists():
        try:
            entry = json.loads(path.read_text(encoding="utf-8"))
            if _is_fresh(entry["cached_at"]):
                age_min = int((time.time() - entry["cached_at"]) / 60)
                print(f"  [JobCache] File hit: {len(entry['jobs'])} jobs "
                      f"({age_min}m old) for {titles[:2]}")
                _mem_cache[key] = entry   # promote to memory
                return entry["jobs"]
            else:
                path.unlink(missing_ok=True)
                print(f"  [JobCache] Stale — refetching for {titles[:2]}")
        except Exception as e:
            print(f"  [JobCache] Read error: {e}")

    return None


def store(titles: list, country: str, portals: list, jobs: list) -> None:
    """Store job listings in both memory and filesystem cache."""
    if not jobs:
        return
    key   = _make_key(titles, country, portals)
    entry = {
        "titles":    titles,
        "country":   country,
        "portals":   portals,
        "jobs":      jobs,
        "cached_at": time.time(),
        "count":     len(jobs),
    }
    _mem_cache[key] = entry
    try:
        _cache_path(key).write_text(json.dumps(entry, indent=2), encoding="utf-8")
        print(f"  [JobCache] Stored {len(jobs)} jobs for {titles[:2]}")
    except Exception as e:
        print(f"  [JobCache] Store error: {e}")


def lookup_partial(titles: list, country: str, portals: list) -> Optional[dict]:
    """
    Try to serve from cache even when titles differ from cache key.
    Looks for any cached search for the same country + portals,
    then filters to jobs matching the requested titles.

    Returns: {"jobs": [...], "cached_titles": [...], "missing_titles": [...]}
    or None if no useful cache found.
    """
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    titles_lower = {t.lower() for t in titles}

    # Check all cached files for same country
    best_match = None
    best_overlap = 0

    for f in CACHE_DIR.glob("*.json"):
        try:
            entry = json.loads(f.read_text(encoding="utf-8"))
            if entry.get("country", "").lower() != country.lower():
                continue
            if not _is_fresh(entry.get("cached_at", 0)):
                f.unlink(missing_ok=True)
                continue

            # Check portal overlap
            cached_portals = set(entry.get("portals", []))
            req_portals    = set(portals)
            portal_overlap = len(cached_portals & req_portals)
            if portal_overlap == 0:
                continue

            # Check title overlap
            cached_titles_lower = {t.lower() for t in entry.get("titles", [])}
            title_overlap = len(titles_lower & cached_titles_lower)

            if title_overlap > best_overlap:
                best_overlap = title_overlap
                best_match   = entry

        except Exception:
            continue

    if not best_match or best_overlap == 0:
        return None

    # Filter cached jobs to those matching requested titles
    cached_titles_set = {t.lower() for t in best_match.get("titles", [])}
    missing_titles    = [t for t in titles if t.lower() not in cached_titles_set]

    # Return all jobs — caller can filter further if needed
    age_min = int((time.time() - best_match["cached_at"]) / 60)
    print(f"  [JobCache] Partial hit: {len(best_match['jobs'])} jobs "
          f"({age_min}m old, {best_overlap} title overlap)")
    return {
        "jobs":            best_match["jobs"],
        "cached_titles":   best_match["titles"],
        "missing_titles":  missing_titles,
        "cached_at":       best_match["cached_at"],
    }


def stats() -> dict:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    files   = list(CACHE_DIR.glob("*.json"))
    fresh   = 0
    total_j = 0
    for f in files:
        try:
            e = json.loads(f.read_text())
            if _is_fresh(e.get("cached_at", 0)):
                fresh   += 1
                total_j += e.get("count", 0)
        except Exception:
            pass
    return {
        "cached_searches": fresh,
        "stale_searches":  len(files) - fresh,
        "total_jobs":      total_j,
        "ttl_hours":       TTL_SECONDS // 3600,
    }


def clear_stale() -> int:
    """Remove stale cache files. Returns count removed."""
    removed = 0
    for f in CACHE_DIR.glob("*.json"):
        try:
            e = json.loads(f.read_text())
            if not _is_fresh(e.get("cached_at", 0)):
                f.unlink()
                removed += 1
        except Exception:
            f.unlink(missing_ok=True)
            removed += 1
    return removed