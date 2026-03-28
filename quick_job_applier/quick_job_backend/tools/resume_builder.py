"""
ResumeBuilderTool

1. Extract original PDF text + hyperlinks
2. LLM enhances Experience + Skills only
3. ATS score gate (90%)
4. Save as valid PDF via reportlab + .txt fallback
"""

import json
import re
from pathlib import Path
from typing import Type, Any
from pydantic import BaseModel, Field
from langchain_core.tools import BaseTool
from langchain_core.messages import HumanMessage, SystemMessage
from datetime import datetime

OUTPUT_DIR        = Path("job_apply_output")
ATS_MINIMUM_SCORE = 90


def _safe_filename(name: str, max_len: int = 40) -> str:
    name = re.sub(r'[^\w\s-]', '', name).strip()
    name = re.sub(r'\s+', '_', name)
    return name[:max_len] or "resume"


def _clean_text(text: str) -> str:
    """Normalise Unicode punctuation to ASCII and strip non-printable chars."""
    text = (text
        .replace('\u2013', '-').replace('\u2014', '-')
        .replace('\u2018', "'").replace('\u2019', "'")
        .replace('\u201c', '"').replace('\u201d', '"')
        .replace('\u2022', '-').replace('\u00b7', '-')
        .replace('\u2026', '...')
    )
    return re.sub(r'[^\x20-\x7E\n]', '', text)


def _is_valid_pdf(path: Path) -> bool:
    """Return True only if the file exists, is non-trivial, and starts with %PDF."""
    try:
        if not path.exists() or path.stat().st_size < 200:
            return False
        with open(path, "rb") as f:
            return f.read(4) == b"%PDF"
    except Exception:
        return False


def _extract_pdf_text_and_links(path: str):
    """Extract text and hyperlinks from the original PDF."""
    text, links = "", []
    try:
        import pdfplumber
        with pdfplumber.open(path) as pdf:
            for page in pdf.pages:
                text += (page.extract_text() or "") + "\n"
                for ann in (page.annots or []):
                    uri = ann.get("uri", "")
                    if uri:
                        links.append(uri)
        print(f"  [ResumeBuilder] Extracted {len(text)} chars, {len(links)} links")
        return text, list(set(links))
    except Exception as e:
        print(f"  [ResumeBuilder] pdfplumber failed: {e}")

    try:
        import pypdf
        reader = pypdf.PdfReader(path)
        for page in reader.pages:
            text += (page.extract_text() or "") + "\n"
        print(f"  [ResumeBuilder] Extracted via pypdf: {len(text)} chars")
    except Exception as e:
        print(f"  [ResumeBuilder] pypdf failed: {e}")

    return text, links


def _build_pdf(text: str, output_path: Path, links: list = None) -> bool:
    """
    Generate a valid PDF from resume plain-text using reportlab Platypus.
    Returns True on success, False on any failure.
    Never writes non-PDF bytes to a .pdf path — on failure the file is removed.
    """
    try:
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
        from reportlab.lib.units import mm
        from reportlab.lib import colors
        from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, HRFlowable
        from reportlab.lib.enums import TA_LEFT

        MARGIN = 18 * mm
        ACCENT = colors.HexColor("#5B4FE9")
        DARK   = colors.HexColor("#1E1E1E")
        MID    = colors.HexColor("#3C3C3C")

        styles = getSampleStyleSheet()

        style_header = ParagraphStyle(
            "ResumeHeader",
            parent=styles["Normal"],
            fontName="Helvetica-Bold",
            fontSize=11,
            textColor=DARK,
            spaceBefore=8,
            spaceAfter=1,
        )
        style_normal = ParagraphStyle(
            "ResumeNormal",
            parent=styles["Normal"],
            fontName="Helvetica",
            fontSize=10,
            textColor=MID,
            spaceAfter=2,
            leading=14,
        )
        style_bullet = ParagraphStyle(
            "ResumeBullet",
            parent=styles["Normal"],
            fontName="Helvetica",
            fontSize=9,
            textColor=MID,
            leftIndent=10,
            spaceAfter=1,
            leading=13,
        )
        style_link = ParagraphStyle(
            "ResumeLink",
            parent=styles["Normal"],
            fontName="Helvetica",
            fontSize=8,
            textColor=colors.blue,
            spaceAfter=1,
        )

        doc = SimpleDocTemplate(
            str(output_path),
            pagesize=A4,
            leftMargin=MARGIN, rightMargin=MARGIN,
            topMargin=MARGIN,  bottomMargin=MARGIN,
        )

        story = []

        for raw_line in text.split("\n"):
            line = _clean_text(raw_line).strip()

            if not line:
                story.append(Spacer(1, 3))
                continue

            # Escape ReportLab XML special chars
            safe = (line
                .replace("&", "&amp;")
                .replace("<", "&lt;")
                .replace(">", "&gt;")
            )

            # ALL CAPS short line -> section header + divider
            if line.isupper() and 2 < len(line) < 60:
                story.append(Spacer(1, 4))
                story.append(Paragraph(safe, style_header))
                story.append(HRFlowable(
                    width="100%", thickness=0.5,
                    color=ACCENT, spaceAfter=2,
                ))

            # Bullet line
            elif line.startswith(("-", "*", "•")):
                bullet_text = "- " + line.lstrip("-*• ").strip()
                bullet_safe = (bullet_text
                    .replace("&", "&amp;")
                    .replace("<", "&lt;")
                    .replace(">", "&gt;")
                )
                story.append(Paragraph(bullet_safe, style_bullet))

            # Normal text
            else:
                story.append(Paragraph(safe, style_normal))

        # Links section
        if links:
            story.append(Spacer(1, 6))
            story.append(Paragraph("LINKS", style_header))
            story.append(HRFlowable(width="100%", thickness=0.5, color=ACCENT, spaceAfter=2))
            for link in links[:10]:
                safe_link = (link
                    .replace("&", "&amp;")
                    .replace("<", "&lt;")
                    .replace(">", "&gt;")
                )
                story.append(Paragraph(
                    f'<link href="{safe_link}" color="blue">{safe_link}</link>',
                    style_link,
                ))

        doc.build(story)

        if not _is_valid_pdf(output_path):
            raise ValueError("reportlab output failed PDF validity check")

        size = output_path.stat().st_size
        print(f"  [ResumeBuilder] PDF saved: {output_path.name} ({size:,} bytes)")
        return True

    except Exception as e:
        print(f"  [ResumeBuilder] PDF build failed: {e}")
        # Remove any partial/corrupt file so callers detect failure cleanly
        try:
            output_path.unlink(missing_ok=True)
        except Exception:
            pass
        return False


class ResumeBuilderInput(BaseModel):
    resume_json:        str = Field(description="Parsed resume JSON string")
    match_json:         str = Field(description="JD match analysis JSON string")
    job_title:          str = Field(description="Job title")
    company_name:       str = Field(description="Company name")
    job_description:    str = Field(description="Full job description")
    original_file_name: str = Field(default="resume")
    original_pdf_path:  str = Field(default="")


class ResumeBuilderTool(BaseTool):
    name: str = "resume_builder"
    description: str = "Enhances original resume for a specific JD, scores ATS, saves PDF."
    args_schema: Type[BaseModel] = ResumeBuilderInput
    llm: Any

    def _enhance_resume(self, original_text, resume, match, job_title, company, jd):
        prompt = (
            "You are an expert resume writer. ENHANCE the resume below for the target job.\n\n"
            "STRICT RULES:\n"
            "1. Keep ALL contact info EXACTLY as-is (name, email, phone, LinkedIn, GitHub URLs)\n"
            "2. Keep education, certifications, languages EXACTLY as-is\n"
            "3. ONLY modify: Experience bullet points and Skills section\n"
            "4. Strengthen action verbs, add quantified achievements, weave in matched keywords\n"
            "5. Do NOT invent fake experience, degrees or credentials\n"
            "6. Keep same section headers and structure\n"
            "7. Use only ASCII/latin characters — no Unicode bullets, em-dashes, or special chars\n"
            "8. Return the COMPLETE enhanced resume as plain text only\n\n"
            f"Target: {job_title} at {company}\n"
            f"Emphasise skills: {match.get('matched_skills', [])}\n"
            f"Weave in naturally: {match.get('missing_keywords', [])[:6]}\n"
            f"JD: {jd[:600]}\n\n"
            f"ORIGINAL RESUME:\n{original_text[:4000]}\n\n"
            "Return enhanced resume text only. Use plain ASCII dashes (-) for bullets."
        )
        resp = self.llm.invoke([
            SystemMessage(content="Resume enhancement expert. Return plain ASCII text only. No Unicode special characters."),
            HumanMessage(content=prompt),
        ])
        return resp.content if isinstance(resp.content, str) else str(resp.content)

    def _cover_letter(self, resume, job_title, company, jd, match):
        prompt = (
            f"Write a cover letter for {resume.get('name','Candidate')}.\n"
            f"Role: {job_title} at {company}\n"
            f"Strengths: {match.get('strengths', [])}\n"
            f"Experience: {resume.get('total_experience_years', 0)} years\n"
            f"JD: {jd[:500]}\n\n"
            "Rules: 3 paragraphs. No 'I am writing to apply'. Address to Hiring Manager. "
            "Plain ASCII text only. No Unicode dashes or bullets."
        )
        resp = self.llm.invoke([
            SystemMessage(content="Cover letter expert. Plain ASCII text only."),
            HumanMessage(content=prompt),
        ])
        return resp.content if isinstance(resp.content, str) else str(resp.content)

    def _score_ats(self, text, jd, match):
        prompt = (
            "Score this resume against the JD as an ATS system.\n"
            "Return ONLY valid JSON — no markdown:\n"
            '{"ats_score":85,"keyword_match_pct":78,"format_score":90,"improvements":["tip1","tip2"]}\n\n'
            f"Keywords to check: {match.get('matched_keywords',[]) + match.get('missing_keywords',[])}\n"
            f"Resume (2000 chars):\n{text[:2000]}\n"
            f"JD:\n{jd[:600]}"
        )
        try:
            resp = self.llm.invoke([
                SystemMessage(content="ATS expert. Return ONLY valid JSON."),
                HumanMessage(content=prompt),
            ])
            raw = resp.content if isinstance(resp.content, str) else str(resp.content)
            raw = re.sub(r'^```(?:json)?\s*', '', raw.strip())
            raw = re.sub(r'\s*```$', '', raw).strip()
            m = re.search(r'\{.*\}', raw, re.DOTALL)
            if m:
                return json.loads(m.group(0))
        except Exception as e:
            print(f"  [ResumeBuilder] ATS scoring error: {e}")
        return {"ats_score": 0, "keyword_match_pct": 0, "format_score": 0, "improvements": []}

    def _run(
        self,
        resume_json:        str,
        match_json:         str,
        job_title:          str,
        company_name:       str,
        job_description:    str,
        original_file_name: str = "resume",
        original_pdf_path:  str = "",
    ) -> str:
        print(f"  [ResumeBuilder] Building for: {job_title} @ {company_name}")
        resume = json.loads(resume_json)
        match  = json.loads(match_json)

        # ── Extract original text + links ─────────────────────
        original_text, links = "", []
        if original_pdf_path and Path(original_pdf_path).exists():
            original_text, links = _extract_pdf_text_and_links(original_pdf_path)

        if not original_text.strip():
            exp_lines = []
            for e in resume.get("experience", []):
                exp_lines.append(f"{e.get('title')} at {e.get('company')} ({e.get('duration')})")
                exp_lines.append(e.get("description", ""))
            original_text = (
                f"{resume.get('name','')}\n"
                f"{resume.get('email','')} | {resume.get('phone','')} | {resume.get('location','')}\n"
                f"{resume.get('linkedin','')}\n\n"
                f"SUMMARY\n{resume.get('summary','')}\n\n"
                f"SKILLS\n{', '.join(resume.get('skills',[]))}\n\n"
                "EXPERIENCE\n" + "\n".join(exp_lines) + "\n\n"
                "EDUCATION\n" + "\n".join(
                    f"{e.get('degree')} - {e.get('institution')} ({e.get('year')})"
                    for e in resume.get("education", [])
                )
            )

        # ── Enhance via LLM ───────────────────────────────────
        enhanced = _clean_text(self._enhance_resume(
            original_text, resume, match, job_title, company_name, job_description
        ))

        # ── ATS score ─────────────────────────────────────────
        ats       = self._score_ats(enhanced, job_description, match)
        ats_score = ats.get("ats_score", 0)
        print(f"  [ResumeBuilder] ATS: {ats_score}% (min: {ATS_MINIMUM_SCORE}%)")

        if ats_score < ATS_MINIMUM_SCORE:
            print(f"  [ResumeBuilder] Improving...")
            tips = "\n".join(f"- {t}" for t in ats.get("improvements", []))
            try:
                resp = self.llm.invoke([
                    SystemMessage(content="Resume improvement expert. Plain ASCII text only."),
                    HumanMessage(
                        content=f"Score was {ats_score}% (need {ATS_MINIMUM_SCORE}%).\n"
                                f"Apply:\n{tips}\n\nResume:\n{enhanced[:3000]}\n\n"
                                "Return improved text only. Use plain ASCII only."
                    ),
                ])
                enhanced  = _clean_text(resp.content if isinstance(resp.content, str) else str(resp.content))
                ats2      = self._score_ats(enhanced, job_description, match)
                ats_score = ats2.get("ats_score", ats_score)
                ats       = ats2
                print(f"  [ResumeBuilder] ATS after improvement: {ats_score}%")
            except Exception as e:
                print(f"  [ResumeBuilder] Improvement failed: {e}")

        # ── Cover letter ──────────────────────────────────────
        cover = _clean_text(self._cover_letter(resume, job_title, company_name, job_description, match))

        # ── Save files ────────────────────────────────────────
        # Preserve original filename WITHOUT truncation to maintain user's naming convention
        orig_name = Path(original_file_name).stem or "resume"
        # Only truncate company name for folder path (filesystem compatibility)
        co_safe   = _safe_filename(company_name, max_len=40)
        ts        = datetime.now().strftime("%Y%m%d_%H%M%S")
        folder    = OUTPUT_DIR / f"{ts}_{co_safe}"
        folder.mkdir(parents=True, exist_ok=True)

        resume_pdf = folder / f"{orig_name}_{co_safe}.pdf"
        cover_pdf  = folder / f"CoverLetter_{co_safe}.pdf"
        resume_txt = folder / f"{orig_name}_{co_safe}.txt"
        cover_txt  = folder / f"CoverLetter_{co_safe}.txt"

        # Always save .txt first — guaranteed readable fallback
        resume_txt.write_text(enhanced, encoding="utf-8")
        cover_txt.write_text(cover,    encoding="utf-8")

        # ── Attempt surgical editing first to preserve original template ──
        pdf_ok = False
        if original_pdf_path and Path(original_pdf_path).exists():
            try:
                print(f"  [ResumeBuilder] Attempting surgical edit to preserve original template...")
                from resume_enhancer import enhance_resume
                result = enhance_resume(
                    self.llm, resume_json, match_json, job_title, company_name,
                    job_description, original_pdf_path, original_file_name
                )
                result_dict = json.loads(result) if isinstance(result, str) else result
                if result_dict.get("pdf_valid"):
                    # Copy the surgically-edited resume from enhance_resume back to our folder
                    import shutil
                    src_resume = Path(result_dict["resume_path"])
                    if src_resume.exists():
                        shutil.copy2(src_resume, resume_pdf)
                        pdf_ok = True
                        print("  [ResumeBuilder] Surgical edit successful — original template preserved")
            except Exception as e:
                print(f"  [ResumeBuilder] Surgical edit failed: {e} — falling back to reportlab")
                pdf_ok = False

        # Build PDF fallback using reportlab if surgical edit didn't work
        if not pdf_ok:
            pdf_ok = _build_pdf(enhanced, resume_pdf, links=links)
            if not pdf_ok:
                print("  [ResumeBuilder] Resume PDF failed — .txt fallback is available")
        
        pdf_ok2 = _build_pdf(cover, cover_pdf)
        if not pdf_ok2:
            print("  [ResumeBuilder] Cover letter PDF failed — .txt fallback is available")

        return json.dumps({
            "status":            "success",
            "output_folder":     str(folder),
            "resume_path":       str(resume_pdf)  if pdf_ok  else str(resume_txt),
            "cover_letter_path": str(cover_pdf)   if pdf_ok2 else str(cover_txt),
            "resume_txt_path":   str(resume_txt),
            "cover_txt_path":    str(cover_txt),
            "ats_score":         ats_score,
            "ats_details":       ats,
            "links_preserved":   len(links),
            "pdf_valid":         pdf_ok,
        }, indent=2)

    async def _arun(self, resume_json, match_json, job_title,
                    company_name, job_description,
                    original_file_name="resume", original_pdf_path=""):
        return self._run(resume_json, match_json, job_title,
                         company_name, job_description,
                         original_file_name, original_pdf_path)