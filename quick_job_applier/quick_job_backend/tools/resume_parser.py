import re
import json
from pathlib import Path
from typing import Type, Any
from pydantic import BaseModel, Field
from langchain_core.tools import BaseTool
from langchain_core.messages import HumanMessage, SystemMessage


def _clean_json(raw: str) -> str:
    """Strip markdown fences and any leading/trailing noise from LLM output."""
    raw = raw.strip()
    # Remove ```json ... ``` or ``` ... ```
    raw = re.sub(r'^```(?:json)?\s*', '', raw)
    raw = re.sub(r'\s*```$', '', raw)
    return raw.strip()


class ResumeParserInput(BaseModel):
    file_path: str = Field(description="Path to the uploaded resume PDF")


class ResumeParserTool(BaseTool):
    name: str = "resume_parser"
    description: str = "Parses a resume PDF and extracts structured information."
    args_schema: Type[BaseModel] = ResumeParserInput
    llm: Any

    # ------------------------------------------------------------------
    # Text extraction — tries multiple libraries
    # ------------------------------------------------------------------

    def _extract_text_pdfplumber(self, path: str) -> str:
        import pdfplumber
        with pdfplumber.open(path) as pdf:
            pages = [page.extract_text() or "" for page in pdf.pages]
        return "\n".join(pages)

    def _extract_text_pypdf(self, path: str) -> str:
        import pypdf
        reader = pypdf.PdfReader(path)
        return "\n".join(page.extract_text() or "" for page in reader.pages)

    def _extract_text_pymupdf(self, path: str) -> str:
        import fitz  # PyMuPDF
        doc = fitz.open(path)
        return "\n".join(page.get_text() for page in doc)

    def _extract_text(self, path: str) -> str:
        errors = []
        for fn in [self._extract_text_pdfplumber, self._extract_text_pypdf, self._extract_text_pymupdf]:
            try:
                text = fn(path)
                if text.strip():
                    print(f"  [ResumeParser] Extracted text via {fn.__name__} ({len(text)} chars)")
                    return text
            except ImportError as e:
                errors.append(f"{fn.__name__}: not installed ({e})")
            except Exception as e:
                errors.append(f"{fn.__name__}: {e}")

        print(f"  [ResumeParser] All extractors failed: {errors}")
        return ""

    # ------------------------------------------------------------------
    # LLM parsing
    # ------------------------------------------------------------------

    def _parse_with_llm(self, raw_text: str) -> dict:
        prompt = (
            "Extract structured information from this resume text.\n"
            "Return ONLY valid JSON — no markdown, no explanation, no code fences.\n\n"
            "Required JSON structure:\n"
            "{\n"
            '  "name": "full name",\n'
            '  "email": "email address",\n'
            '  "phone": "phone number",\n'
            '  "location": "city, country",\n'
            '  "linkedin": "linkedin url or empty string",\n'
            '  "summary": "professional summary in 2-3 sentences",\n'
            '  "skills": ["skill1", "skill2"],\n'
            '  "experience": [\n'
            '    {"title": "job title", "company": "company", "duration": "start-end", "description": "achievements"}\n'
            '  ],\n'
            '  "education": [\n'
            '    {"degree": "degree", "institution": "university", "year": "year"}\n'
            '  ],\n'
            '  "certifications": ["cert1"],\n'
            '  "languages": ["English"],\n'
            '  "total_experience_years": 0\n'
            "}\n\n"
            f"Resume text:\n{raw_text[:5000]}"
        )
        response = self.llm.invoke([
            SystemMessage(content="You are a resume parsing expert. Return ONLY valid JSON. No markdown fences."),
            HumanMessage(content=prompt),
        ])
        raw = response.content if isinstance(response.content, str) else str(response.content)
        raw = _clean_json(raw)

        # Find the JSON object even if there's surrounding text
        match = re.search(r'\{.*\}', raw, re.DOTALL)
        if match:
            raw = match.group(0)

        return json.loads(raw)

    # ------------------------------------------------------------------
    # Fallback: build minimal dict from raw text if LLM fails
    # ------------------------------------------------------------------

    def _extract_minimal(self, raw_text: str) -> dict:
        """Best-effort extraction without LLM."""
        lines  = [l.strip() for l in raw_text.splitlines() if l.strip()]
        emails = re.findall(r'[\w.+-]+@[\w-]+\.[a-zA-Z]+', raw_text)
        phones = re.findall(r'[\+\(]?[\d\s\-\(\)]{9,15}', raw_text)

        return {
            "name":                   lines[0] if lines else "Unknown",
            "email":                  emails[0] if emails else "",
            "phone":                  phones[0].strip() if phones else "",
            "location":               "",
            "linkedin":               "",
            "summary":                " ".join(lines[1:4]),
            "skills":                 [],
            "experience":             [],
            "education":              [],
            "certifications":         [],
            "languages":              [],
            "total_experience_years": 0,
        }

    # ------------------------------------------------------------------
    # Run
    # ------------------------------------------------------------------

    def _run_regex_only(self, file_path: str) -> str:
        """
        Parse resume using only regex — zero LLM tokens.
        Called when all LLMs are rate-limited.
        Returns best-effort structured JSON from text patterns.
        """
        print(f"  [ResumeParser] Regex-only parse (LLM unavailable): {file_path}")
        raw_text = self._extract_text(file_path)
        if not raw_text.strip():
            return json.dumps({
                "name": "Candidate", "email": "", "phone": "", "location": "",
                "linkedin": "", "summary": "", "skills": [], "experience": [],
                "education": [], "certifications": [], "languages": [],
                "total_experience_years": 0,
                "_parse_method": "regex_fallback_empty"
            })
        result = self._extract_minimal(raw_text)
        result["_parse_method"] = "regex_fallback"

        # Enhanced regex extraction
        # Email
        emails = re.findall(r'[\w.+-]+@[\w-]+\.[a-zA-Z]+', raw_text)
        if emails: result["email"] = emails[0]

        # Phone
        phones = re.findall(r'[\+\(]?[\d\s\-\(\)]{9,15}', raw_text)
        if phones: result["phone"] = phones[0].strip()

        # LinkedIn
        linkedin = re.findall(r'linkedin\.com/in/[\w\-]+', raw_text, re.IGNORECASE)
        if linkedin: result["linkedin"] = "https://" + linkedin[0]

        # Skills — look for common tech keywords
        common_skills = [
            "Python","Java","JavaScript","TypeScript","React","Node","SQL","AWS","Azure","GCP",
            "Docker","Kubernetes","Git","TensorFlow","PyTorch","Spark","Hadoop","Kafka",
            "FastAPI","Django","Flask","Spring","Machine Learning","Deep Learning","NLP",
            "Data Science","MLOps","DevOps","CI/CD","Agile","Scrum","Power BI","Tableau",
            "Excel","R","Scala","Go","Rust","C++","C#",".NET","MongoDB","PostgreSQL",
            "MySQL","Redis","Elasticsearch","Airflow","dbt","Databricks","Snowflake"
        ]
        found_skills = [s for s in common_skills if s.lower() in raw_text.lower()]
        if found_skills: result["skills"] = found_skills

        # Experience years — look for patterns like "8 years", "8+ years"
        years_match = re.search(r'(\d+)\+?\s*years?\s+(?:of\s+)?experience', raw_text, re.IGNORECASE)
        if years_match:
            result["total_experience_years"] = int(years_match.group(1))

        print(f"  [ResumeParser] Regex fallback: {result.get('name')} | {len(result.get('skills',[]))} skills")
        return json.dumps(result, indent=2)

    def _run(self, file_path: str) -> str:
        print(f"  [ResumeParser] Parsing: {file_path}")

        # Step 1: Extract text
        raw_text = self._extract_text(file_path)
        if not raw_text.strip():
            return json.dumps({
                "error": "Could not extract text from PDF. Make sure pdfplumber or pypdf is installed.",
                "fix":   "pip install pdfplumber pypdf"
            })

        # Step 2: Parse with LLM
        try:
            parsed = self._parse_with_llm(raw_text)
            print(f"  [ResumeParser] OK: {parsed.get('name')} | {parsed.get('total_experience_years')}yrs")
            return json.dumps(parsed, indent=2)
        except json.JSONDecodeError as e:
            print(f"  [ResumeParser] LLM returned invalid JSON: {e} — using minimal fallback")
            parsed = self._extract_minimal(raw_text)
            return json.dumps(parsed, indent=2)
        except Exception as e:
            print(f"  [ResumeParser] LLM failed: {e} — using minimal fallback")
            parsed = self._extract_minimal(raw_text)
            return json.dumps(parsed, indent=2)

    async def _arun(self, file_path: str) -> str:
        return self._run(file_path)