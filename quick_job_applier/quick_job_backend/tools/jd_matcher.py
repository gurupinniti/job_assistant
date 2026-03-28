import json
from typing import Type, Any
from pydantic import BaseModel, Field
from langchain_core.tools import BaseTool
from langchain_core.messages import HumanMessage, SystemMessage


class JDMatcherInput(BaseModel):
    resume_json: str = Field(description="Parsed resume JSON string")
    job_description: str = Field(description="Full job description text")
    job_title: str = Field(description="Job title being applied for")


class JDMatcherTool(BaseTool):
    name: str = "jd_matcher"
    description: str = "Scores how well a resume matches a job description and identifies gaps."
    args_schema: Type[BaseModel] = JDMatcherInput
    llm: Any

    def _run(self, resume_json: str, job_description: str, job_title: str) -> str:
        print(f"  [JDMatcher] Matching resume to: {job_title}")
        resume = json.loads(resume_json)

        prompt = f"""
You are an expert recruiter and ATS specialist.

Compare this candidate's resume against the job description and return a detailed match analysis.

Candidate:
- Name: {resume.get('name')}
- Skills: {', '.join(resume.get('skills', [])[:25])}
- Experience: {resume.get('total_experience_years')} years
- Summary: {resume.get('summary', '')}
- Recent role: {resume.get('experience', [{}])[0].get('title', '') if resume.get('experience') else ''}

Job Title: {job_title}
Job Description:
{job_description[:3000]}

Return ONLY valid JSON:
{{
  "match_score": 85,
  "verdict": "Strong Match | Good Match | Partial Match | Weak Match",
  "matched_skills": ["skill1", "skill2"],
  "missing_skills": ["skill3", "skill4"],
  "matched_keywords": ["kw1", "kw2"],
  "missing_keywords": ["kw3"],
  "strengths": ["point1", "point2"],
  "gaps": ["gap1", "gap2"],
  "ats_tips": ["tip1", "tip2"],
  "recommended_to_apply": true
}}
"""
        response = self.llm.invoke([
            SystemMessage(content="You are an ATS and recruitment expert. Return ONLY valid JSON."),
            HumanMessage(content=prompt),
        ])
        raw = response.content if isinstance(response.content, str) else str(response.content)
        raw = raw.strip().lstrip("```json").lstrip("```").rstrip("```").strip()
        result = json.loads(raw)
        print(f"  [JDMatcher] Score: {result.get('match_score')}% | Verdict: {result.get('verdict')}")
        return json.dumps(result, indent=2)

    async def _arun(self, resume_json: str, job_description: str, job_title: str) -> str:
        return self._run(resume_json, job_description, job_title)
