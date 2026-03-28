import aiohttp
import requests
from pydantic import BaseModel, Field
from langchain_core.tools import BaseTool
from typing import Optional, Type, Dict, Any
import json


class SerpersearchInput(BaseModel):
    query: str = Field(description="The search query")


class SerperSearchertool(BaseTool):
    name: str = "serper_tool"
    description: str = "Performs an internet search and returns structured results with titles, snippets and links."
    args_schema: Type[BaseModel] = SerpersearchInput

    api_key: str
    base_url: str = "https://google.serper.dev/search"  # ✅ fixed: was "google.server.dev" in _arun
    location: str = "Ang Mo Kio, Singapore"
    country: str = "sg"

    # ------------------------------------------------------------------
    # Structured output formatter
    # ------------------------------------------------------------------

    def _format_results(self, raw: Dict[str, Any]) -> str:
        """Convert raw Serper JSON into clean readable output."""
        if not raw:
            return "No results found."

        lines = []

        # Answer box (direct answer if available)
        if "answerBox" in raw:
            box = raw["answerBox"]
            answer = box.get("answer") or box.get("snippet", "")
            if answer:
                lines.append(f"Answer: {answer}\n")

        # Knowledge graph (entity info)
        if "knowledgeGraph" in raw:
            kg = raw["knowledgeGraph"]
            title = kg.get("title", "")
            desc  = kg.get("description", "")
            if title:
                lines.append(f"Knowledge Graph: {title} — {desc}\n")

        # Organic results
        organic = raw.get("organic", [])
        if organic:
            lines.append("Search Results:")
            for i, result in enumerate(organic[:5], 1):  # top 5 only
                title   = result.get("title", "No title")
                snippet = result.get("snippet", "No description")
                link    = result.get("link", "")
                lines.append(f"\n  {i}. {title}")
                lines.append(f"     {snippet}")
                lines.append(f"     URL: {link}")

        # Related searches
        related = raw.get("relatedSearches", [])
        if related:
            related_terms = ", ".join(r.get("query", "") for r in related[:5])
            lines.append(f"\nRelated: {related_terms}")

        return "\n".join(lines) if lines else "No results found."

    def _build_payload(self, query: str) -> str:
        return json.dumps({         # ✅ fixed: was json.dumpys (typo)
            "q": query,
            "location": self.location,
            "gl": self.country,
        })

    def _build_headers(self) -> Dict[str, str]:
        return {
            "X-API-KEY": self.api_key,
            "Content-Type": "application/json",  # ✅ fixed typo "applicaiton/json" in _arun
        }

    # ------------------------------------------------------------------
    # Sync
    # ------------------------------------------------------------------

    def _run(self, query: str) -> str:
        try:
            response = requests.post(
                self.base_url,
                headers=self._build_headers(),
                data=self._build_payload(query),
            )
            response.raise_for_status()
            return self._format_results(response.json())  # ✅ fixed: was not returning result
        except Exception as e:
            return f"Search failed: {e}"

    # ------------------------------------------------------------------
    # Async
    # ------------------------------------------------------------------

    async def _arun(self, query: str) -> str:
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    self.base_url,                          # ✅ fixed: was "google.server.dev"
                    headers=self._build_headers(),
                    data=self._build_payload(query),
                ) as response:
                    raw = await response.json()
                    return self._format_results(raw)
        except Exception as e:
            return f"Search failed: {e}"