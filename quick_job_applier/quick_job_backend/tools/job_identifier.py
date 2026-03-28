"""
JobIdentifierTool

Resolution order (cheapest first):
1. Title cache (ChromaDB) — exact fingerprint or 92% similar resume → 0 tokens
2. Taxonomy (memory/job_title_taxonomy.json) — rule-based → 0 tokens
3. LLM enrichment (llm_cache checked first) → tokens only on true miss
"""

import json
import re
from typing import Type, Any, List
from pydantic import BaseModel, Field
from langchain_core.tools import BaseTool
from langchain_core.messages import HumanMessage
from tools.job_searcher import PORTAL_CATALOGUE, COUNTRY_PORTALS

# Re-export for API layer
PORTAL_INFO = {k: {
    "url":         v["url"],
    "easy_apply":  v["easy_apply"],
    "restriction": v["restriction"],
    "tier":        v["tier"],
    "auth":        v["auth"],
} for k, v in PORTAL_CATALOGUE.items()}


class JobIdentifierInput(BaseModel):
    resume_json: str       = Field(description="Parsed resume JSON string")
    job_titles:  List[str] = Field(description="User-selected job titles (may be empty)")
    country:     str       = Field(description="Target country")


class JobIdentifierTool(BaseTool):
    name: str = "job_identifier"
    description: str = "Identifies portals for a country and suggests job titles from resume."
    args_schema: Type[BaseModel] = JobIdentifierInput
    llm: Any

    def _enrich_with_llm(self, resume_json: str, job_titles: List[str],
                          existing: dict = None) -> dict:
        """
        Call LLM only when taxonomy/cache miss.
        Uses: system prompt from memory + llm_cache to avoid repeat calls.
        """
        import memory_manager
        import llm_cache

        try:
            resume = json.loads(resume_json)
        except Exception:
            resume = {}

        exp_years = resume.get("total_experience_years", 0)
        sys_prompt = memory_manager.get_system_prompt("job_title_extractor")

        prompt = (
            f"Candidate experience: {exp_years} years\n"
            f"Current skills: {', '.join(resume.get('skills', [])[:20])}\n"
            f"Current roles: {', '.join(e.get('title','') for e in resume.get('experience',[])[:3])}\n"
            f"User-selected titles: {job_titles}\n\n"
            "Return ONLY valid JSON:\n"
            '{"primary_titles":["t1","t2"],"all_titles":["t1","t2","t3","t4","t5","t6","t7","t8"],'
            '"search_variants":["v1","v2"],"keywords":["k1","k2"],'
            '"seniority":"mid","exp_years":0,"matched_categories":["cat"]}'
        )

        raw = llm_cache.cached_llm_call(
            self.llm,
            [type('S', (), {'content': sys_prompt})(), HumanMessage(content=prompt)],
            prompt_type="job_title_extractor",
        )
        raw = re.sub(r'^```(?:json)?\s*', '', raw.strip())
        raw = re.sub(r'\s*```$', '', raw).strip()
        m   = re.search(r'\{.*\}', raw, re.DOTALL)
        if m:
            return json.loads(m.group(0))
        return {}

    def _run(self, resume_json: str, job_titles: List[str], country: str) -> str:
        import memory_manager

        # ── 1. Title cache (0 tokens) ─────────────────────────────
        cached_titles = memory_manager.lookup_titles_cache(resume_json)
        if cached_titles:
            titles_result = cached_titles
            source = "cache"
        else:
            # ── 2. Taxonomy lookup (0 tokens) ─────────────────────
            taxonomy_result = memory_manager.resolve_job_titles_from_taxonomy(resume_json)
            if taxonomy_result:
                titles_result = taxonomy_result
                source = "taxonomy"
                # Store in title cache for next time
                memory_manager.store_titles_cache(resume_json, titles_result)
            else:
                # ── 3. LLM enrichment — only if user provided no titles ────
                # If user already selected titles, skip LLM entirely and use those
                if job_titles:
                    print(f"  [JobIdentifier] Taxonomy miss but user provided titles — skipping LLM")
                    try:
                        resume = json.loads(resume_json)
                        exp_years = int(resume.get("total_experience_years", 0) or 0)
                    except Exception:
                        exp_years = 0
                    llm_result = {
                        "primary_titles":     job_titles[:4],
                        "all_titles":         job_titles,
                        "search_variants":    job_titles,
                        "keywords":           [],
                        "seniority":          "mid",
                        "exp_years":          exp_years,
                        "matched_categories": [],
                    }
                    source = "user_selection"
                else:
                    # Only call LLM when user gave us nothing to work with
                    print(f"  [JobIdentifier] Taxonomy miss and no user titles — trying LLM")
                    try:
                        llm_result = self._enrich_with_llm(resume_json, job_titles)
                    except Exception as llm_err:
                        # Rate limit or any LLM error — use parsed resume data as fallback
                        print(f"  [JobIdentifier] LLM failed ({llm_err}) — using resume data fallback")
                        try:
                            resume = json.loads(resume_json)
                            exp    = resume.get("experience", [{}])
                            current_title = exp[0].get("title", "Professional") if exp else "Professional"
                            exp_years = int(resume.get("total_experience_years", 0) or 0)
                        except Exception:
                            current_title, exp_years = "Professional", 0
                        llm_result = {
                            "primary_titles":     [current_title],
                            "all_titles":         [current_title],
                            "search_variants":    [current_title],
                            "keywords":           [],
                            "seniority":          "mid",
                            "exp_years":          exp_years,
                            "matched_categories": [],
                        }

                    if not llm_result:
                        llm_result = {
                            "primary_titles": job_titles or ["Professional"],
                            "all_titles":     job_titles or ["Professional"],
                            "seniority":      "mid",
                            "exp_years":      0,
                            "matched_categories": [],
                        }
                    source = "llm"

                titles_result = llm_result
                memory_manager.store_titles_cache(resume_json, titles_result)

        # If user selected specific titles, those take priority
        if job_titles:
            primary = job_titles
            all_t   = list(dict.fromkeys(job_titles + titles_result.get("all_titles", [])))
        else:
            primary = titles_result.get("primary_titles", [])
            all_t   = titles_result.get("all_titles", primary)

        print(f"  [JobIdentifier] Titles from {source}: {primary}")

        # ── Portals for country ───────────────────────────────────
        key      = country.lower().strip()
        portals  = COUNTRY_PORTALS.get(key, COUNTRY_PORTALS["default"])
        portal_list = []
        for p in portals:
            info = PORTAL_CATALOGUE.get(p, {})
            portal_list.append({
                "name":        p,
                "url":         info.get("url", ""),
                "easy_apply":  info.get("easy_apply", False),
                "restriction": info.get("restriction"),
                "tier":        info.get("tier", 2),
                "auth":        info.get("auth", "optional"),
                "description": info.get("description", ""),
            })
        portal_list.sort(key=lambda x: x["tier"])

        return json.dumps({
            "country":           country,
            "portals":           portal_list,
            "primary_titles":    primary,
            "all_titles":        all_t,
            "search_variants":   titles_result.get("search_variants", primary),
            "keywords":          titles_result.get("keywords", []),
            "seniority":         titles_result.get("seniority", "mid"),
            "exp_years":         titles_result.get("exp_years", 0),
            "matched_categories":titles_result.get("matched_categories", []),
            "title_source":      source,
        }, indent=2)

    async def _arun(self, resume_json: str, job_titles: List[str], country: str) -> str:
        return self._run(resume_json, job_titles, country)