"""
ResumeEnhancer — Surgical in-place PDF enhancement

Approach:
  1. Open original PDF with PyMuPDF
  2. Find the EXACT bounding boxes of experience bullet text and skills text
  3. Redact (white-out) those specific spans
  4. Insert enhanced text at the same positions with matching font size
  5. Save — result looks identical to original except updated bullets/skills

No extra pages. No watermarks. No "Tailored Resume" headers.
Looks fully human-generated.
"""

import json
import re
from pathlib import Path
from typing import Any
from datetime import datetime

OUTPUT_DIR = Path("job_apply_output")
ATS_MIN    = 90


def _safe_fn(name: str, n: int = 40) -> str:
    return re.sub(r'\s+', '_', re.sub(r'[^\w\s-]', '', name).strip())[:n] or "resume"


def _clean_ascii(t: str) -> str:
    t = (t
        .replace('\u2013', '-').replace('\u2014', '-')
        .replace('\u2018', "'").replace('\u2019', "'")
        .replace('\u201c', '"').replace('\u201d', '"')
        .replace('\u2022', '-').replace('\u00b7', '-')
        .replace('\u2026', '...')
    )
    return re.sub(r'[^\x20-\x7E\n]', '', t)


def _is_valid_pdf(path: Path) -> bool:
    """Return True only if the file exists, is non-trivial, and starts with %PDF."""
    try:
        if not path.exists() or path.stat().st_size < 200:
            return False
        with open(path, "rb") as f:
            return f.read(4) == b"%PDF"
    except Exception:
        return False


# ---------------------------------------------------------------------------
# PDF surgical editor
# ---------------------------------------------------------------------------

class PDFSurgicalEditor:
    """
    Edits specific sections of a PDF in-place using PyMuPDF.
    Preserves all fonts, colors, images, layout.
    Only modifies targeted text spans.
    """

    def __init__(self, pdf_path: str):
        import fitz
        self.fitz = fitz
        self.doc  = fitz.open(pdf_path)
        self.path = pdf_path

    def close(self):
        try:
            self.doc.close()
        except Exception:
            pass

    def get_full_text(self) -> str:
        return "\n".join(page.get_text() for page in self.doc)

    def get_links(self) -> list:
        links = []
        for page in self.doc:
            for link in page.get_links():
                uri = link.get("uri", "")
                if uri:
                    links.append(uri)
        return list(set(links))

    def extract_section(self, section_keywords: list) -> dict:
        """
        Find which page + bounding boxes contain a section.
        Returns {header_page, header_bbox, content_spans: [{text, bbox, fontsize, page}]}
        """
        results = {"content_spans": []}
        in_section = False
        section_end_keywords = [
            "EDUCATION", "CERTIFICATIONS", "AWARDS", "PUBLICATIONS",
            "PROJECTS", "LANGUAGES", "REFERENCES", "CONTACT", "SUMMARY",
            "OBJECTIVE", "PROFESSIONAL OBJECTIVE",
        ]
        end_kw = [k for k in section_end_keywords
                  if not any(s.upper() in k for s in section_keywords)]
        
        # Collect all text found in PDF for debugging
        all_headers_found = []

        for page_num, page in enumerate(self.doc):
            blocks = page.get_text("dict")["blocks"]
            for block in blocks:
                if block.get("type") != 0:
                    continue
                for line in block.get("lines", []):
                    for span in line.get("spans", []):
                        text = span.get("text", "").strip()
                        if not text:
                            continue
                        upper = text.upper()

                        # Track all headers for debugging
                        if len(text) < 50 and text.isupper() and len(text.split()) <= 4:
                            all_headers_found.append(upper)

                        if any(kw.upper() in upper for kw in section_keywords):
                            in_section = True
                            results["header_page"] = page_num
                            results["header_bbox"]  = span["bbox"]
                            print(f"  [PDFEditor] Found section header on page {page_num}: {text}")
                            continue

                        if in_section:
                            if (any(kw in upper for kw in end_kw)
                                    and len(text) < 50
                                    and (span.get("flags", 0) & 2**4 or text.isupper())):
                                in_section = False
                                continue
                            results["content_spans"].append({
                                "text":     text,
                                "bbox":     span["bbox"],
                                "fontsize": span.get("size", 10),
                                "fontname": span.get("font", "Helvetica"),
                                "color":    span.get("color", 0),
                                "page":     page_num,
                            })
        
        # Log diagnostic info if section not found
        if not results["content_spans"]:
            print(f"  [PDFEditor] ⚠ Section not found: {section_keywords}")
            print(f"  [PDFEditor] Headers detected in PDF: {all_headers_found}")
            print(f"  [PDFEditor] Searching for: {[kw.upper() for kw in section_keywords]}")
        
        return results

    def replace_section_content(self, section_keywords: list,
                                 new_lines: list,
                                 experience_only_n_jobs: int = 2):
        """
        Surgically replace section content:
        1. Find all spans in section
        2. White-out (redact) them
        3. Insert new text at same positions
        Raises exception if section not found - NO FALLBACK.
        """
        section = self.extract_section(section_keywords)
        spans   = section.get("content_spans", [])
        if not spans:
            raise ValueError(
                f"[PDFEditor] Cannot find section keywords in PDF: {section_keywords}. "
                f"Resume template may be incompatible. Available text extraction may have failed."
            )

        is_experience = any("EXPERIENCE" in k.upper() or "WORK" in k.upper()
                            for k in section_keywords)

        if is_experience:
            self._replace_experience_bullets(spans, new_lines, experience_only_n_jobs)
        else:
            self._replace_skills_content(spans, new_lines)
        return True

    def _replace_experience_bullets(self, spans: list, new_lines: list, n_jobs: int):
        """Replace bullet points of the most recent N job entries."""
        job_starts = []
        for i, span in enumerate(spans):
            text = span["text"].strip()
            is_title = (
                len(text) < 80 and
                not text.startswith(('-', '\u2022', '*')) and
                (span.get("flags", 0) & 2**4
                 or any(kw in text for kw in [" at ", " | ", "Pte", "Ltd", "Inc", "Corp", "Co."]))
            )
            if is_title:
                job_starts.append(i)

        target_jobs = job_starts[:n_jobs] if len(job_starts) >= n_jobs else job_starts

        bullet_spans = []
        for ji, start_idx in enumerate(target_jobs):
            end_idx = job_starts[ji + 1] if ji + 1 < len(job_starts) else len(spans)
            for span in spans[start_idx + 1:end_idx]:
                if span["text"].strip().startswith(('-', '\u2022', '*', '\u2013')):
                    bullet_spans.append(span)

        if not bullet_spans:
            bullet_spans = [s for s in spans if s["text"].strip().startswith(('-', '\u2022', '*', '\u2013'))]

        new_bullets = [
            l.strip() for l in new_lines
            if l.strip().startswith(('-', '\u2022', '*', '\u2013',
                                      'Led', 'Built', 'Developed', 'Managed',
                                      'Improved', 'Created', 'Delivered', 'Drove'))
        ]
        if not new_bullets:
            new_bullets = [l.strip() for l in new_lines if l.strip() and len(l.strip()) > 20]

        print(f"  [PDFEditor] Replacing {len(bullet_spans)} bullets -> {len(new_bullets)} new")

        for i, span in enumerate(bullet_spans):
            page = self.doc[span["page"]]
            rect = self.fitz.Rect(span["bbox"])

            page.add_redact_annot(rect, fill=(1, 1, 1))
            page.apply_redactions()

            if i < len(new_bullets):
                new_text = "- " + new_bullets[i].lstrip('-\u2022*\u2013 ').strip()
                new_text = _clean_ascii(new_text)
                new_text_safe = new_text.encode("latin-1", errors="replace").decode("latin-1")
                page.insert_text(
                    (rect.x0, rect.y1 - 1),
                    new_text_safe,
                    fontsize=max(span["fontsize"] - 0.5, 8),
                    color=_int_to_rgb(span["color"]),
                )

    def _replace_skills_content(self, spans: list, new_lines: list):
        """Replace skills section content while preserving structure."""
        new_by_cat = {}
        current_cat = None
        for line in new_lines:
            t = line.strip()
            if not t:
                continue
            if len(t) < 50 and (t.endswith(':') or t.endswith('&') or
                                  not any(c in t for c in ',;') and len(t.split()) <= 5):
                current_cat = t.rstrip(':')
                new_by_cat[current_cat] = []
            elif current_cat:
                new_by_cat[current_cat].append(t)
            else:
                new_by_cat.setdefault('skills', []).append(t)

        all_new_text = []
        for cat, items in new_by_cat.items():
            all_new_text.append(cat)
            all_new_text.extend(items)

        for i, span in enumerate(spans):
            if i >= len(all_new_text):
                break
            page = self.doc[span["page"]]
            rect = self.fitz.Rect(span["bbox"])

            page.add_redact_annot(rect, fill=(1, 1, 1))
            page.apply_redactions()

            new_text = _clean_ascii(all_new_text[i])
            new_text_safe = new_text.encode("latin-1", errors="replace").decode("latin-1")
            page.insert_text(
                (rect.x0, rect.y1 - 1),
                new_text_safe,
                fontsize=span["fontsize"],
                color=_int_to_rgb(span["color"]),
            )

    def save(self, output_path: Path):
        """
        Save edited PDF to output_path.
        Uses incremental=True for surgical edits to the same file (PyMuPDF requirement).
        Uses garbage=0 with incremental=True (required by PyMuPDF), garbage=4 only with incremental=False (new file).
        Raises ValueError if the output is not a valid PDF.
        """
        # If saving to the same file, must use incremental=True and garbage=0
        # If saving to a new file, can use incremental=False and garbage=4
        output_path = Path(output_path)
        orig_path = Path(self.path)
        if output_path.resolve() == orig_path.resolve():
            # In-place edit: must use incremental=True, garbage=0
            self.doc.save(
                str(output_path),
                garbage=0,
                deflate=True,
                clean=True,
                incremental=True,
            )
        else:
            # New file: can use full garbage collection
            self.doc.save(
                str(output_path),
                garbage=4,
                deflate=True,
                clean=True,
                incremental=False,
            )
        self.doc.close()

        if not _is_valid_pdf(output_path):
            raise ValueError(f"Saved file is not a valid PDF: {output_path}")

        size = output_path.stat().st_size
        print(f"  [PDFEditor] Saved: {output_path.name} ({size:,}b)")
        return size


def _int_to_rgb(color_int: int) -> tuple:
    """Convert PyMuPDF integer color to RGB float tuple."""
    if not color_int:
        return (0, 0, 0)
    r = ((color_int >> 16) & 0xFF) / 255.0
    g = ((color_int >>  8) & 0xFF) / 255.0
    b = ((color_int >>  0) & 0xFF) / 255.0
    return (r, g, b)


# ---------------------------------------------------------------------------
# Cover letter PDF  (reportlab — same engine as resume_builder)
# ---------------------------------------------------------------------------

def _save_cover_pdf(text: str, output_path: Path, job_title: str, company: str) -> bool:
    """
    Build the cover letter PDF with reportlab Platypus.
    Returns True on success, False on failure.
    Never writes non-PDF bytes to the output path.
    """
    try:
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
        from reportlab.lib.units import mm
        from reportlab.lib import colors
        from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, HRFlowable

        MARGIN = 18 * mm
        ACCENT = colors.HexColor("#5B4FE9")
        DARK   = colors.HexColor("#1E1E1E")
        MID    = colors.HexColor("#3C3C3C")

        styles = getSampleStyleSheet()

        style_title = ParagraphStyle(
            "CLTitle",
            parent=styles["Normal"],
            fontName="Helvetica-Bold",
            fontSize=13,
            textColor=ACCENT,
            spaceAfter=4,
        )
        style_sub = ParagraphStyle(
            "CLSub",
            parent=styles["Normal"],
            fontName="Helvetica",
            fontSize=9,
            textColor=colors.grey,
            spaceAfter=2,
        )
        style_body = ParagraphStyle(
            "CLBody",
            parent=styles["Normal"],
            fontName="Helvetica",
            fontSize=10,
            textColor=MID,
            leading=15,
            spaceAfter=10,
        )

        doc = SimpleDocTemplate(
            str(output_path),
            pagesize=A4,
            leftMargin=MARGIN, rightMargin=MARGIN,
            topMargin=MARGIN,  bottomMargin=MARGIN,
        )

        def esc(s):
            return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

        story = [
            Paragraph(esc(job_title.upper()), style_title),
            Paragraph(esc(f"Cover Letter - {company}"), style_sub),
            HRFlowable(width="100%", thickness=0.5, color=ACCENT, spaceAfter=10),
        ]

        text = _clean_ascii(text)
        for para in text.split("\n\n"):
            para = para.strip()
            if para:
                story.append(Paragraph(esc(para), style_body))

        doc.build(story)

        if not _is_valid_pdf(output_path):
            raise ValueError("Cover letter output failed PDF validity check")

        print(f"  [CoverLetter] Saved: {output_path.name}")
        return True

    except Exception as e:
        print(f"  [CoverLetter] PDF failed: {e}")
        try:
            output_path.unlink(missing_ok=True)
        except Exception:
            pass
        return False


# ---------------------------------------------------------------------------
# LLM calls — all routed through cache
# ---------------------------------------------------------------------------

def _llm(llm, messages, prompt_type="general"):
    """Route all LLM calls through the semantic cache."""
    try:
        import llm_cache
        return llm_cache.cached_llm_call(llm, messages, prompt_type)
    except ImportError:
        resp = llm.invoke(messages)
        return resp.content if isinstance(resp.content, str) else str(resp.content)


def _rewrite_experience(llm, exp_original, job_title, company, jd, match) -> tuple:
    """Returns (rewritten_lines, edit_summary)"""
    from langchain_core.messages import HumanMessage, SystemMessage
    import memory_manager
    sys_prompt = memory_manager.get_system_prompt("experience_rewriter")
    prompt = (
        "You are a professional resume writer. Rewrite ONLY the bullet points "
        "of the TWO MOST RECENT jobs to align with the target role.\n\n"
        "STRICT RULES:\n"
        "1. Keep ALL company names, job titles, and dates EXACTLY as written\n"
        "2. Keep older jobs UNCHANGED - return them as-is\n"
        "3. For the 2 most recent jobs ONLY: rewrite each bullet point\n"
        "   - Use strong action verbs\n"
        "   - Add quantified results where plausible (%, $, x improvement)\n"
        "   - Naturally weave in the JD keywords\n"
        "4. Do NOT invent credentials, companies or dates\n"
        "5. Keep the SAME NUMBER of bullets per job\n"
        "6. Return the FULL experience section with ALL jobs\n"
        "7. After the experience section, append a JSON block like:\n"
        '   [EDITS]\n{"changes":[{"original":"old bullet","updated":"new bullet","reason":"why"}]}\n'
        "8. Plain ASCII only\n\n"
        f"Target: {job_title} at {company}\n"
        f"Emphasise: {', '.join(match.get('matched_skills', [])[:8])}\n"
        f"JD: {jd[:500]}\n\n"
        f"EXPERIENCE:\n{exp_original[:3500]}"
    )
    raw = _llm(llm, [SystemMessage(content=sys_prompt),
                      HumanMessage(content=prompt)], "experience_rewrite")
    raw = _clean_ascii(raw)

    if "[EDITS]" in raw:
        parts    = raw.split("[EDITS]", 1)
        exp_text = parts[0].strip()
        try:
            edits = json.loads(parts[1].strip())
        except Exception:
            edits = {"changes": []}
    else:
        exp_text = raw
        edits    = {"changes": []}

    return exp_text.split("\n"), edits


def _rewrite_skills(llm, skills_original, jd, match) -> list:
    from langchain_core.messages import HumanMessage, SystemMessage
    import memory_manager
    sys_prompt = memory_manager.get_system_prompt("skills_rewriter")
    prompt = (
        "Reorder and lightly update this skills section to match the JD better.\n\n"
        "RULES:\n"
        "1. Keep ALL existing skills\n"
        "2. Move the most JD-relevant skills to the top of each category\n"
        "3. You may add 1-2 genuinely applicable missing skills per category\n"
        "4. Keep the same category names and structure\n"
        "5. Return ONLY the updated skills section text\n"
        "6. Plain ASCII only\n\n"
        f"JD priority skills: {match.get('matched_skills', [])}\n"
        f"Skills to consider adding: {match.get('missing_skills', [])[:4]}\n\n"
        f"ORIGINAL:\n{skills_original[:1500]}"
    )
    raw = _llm(llm, [SystemMessage(content=sys_prompt),
                      HumanMessage(content=prompt)], "skills_rewrite")
    return _clean_ascii(raw).split("\n")


def _score_ats(llm, exp_text, skills_text, jd, match) -> dict:
    from langchain_core.messages import HumanMessage, SystemMessage
    combined = f"{exp_text[:1000]}\n{skills_text[:500]}"
    prompt = (
        "Score this resume content as an ATS system. Return ONLY valid JSON:\n"
        '{"ats_score":85,"keyword_match_pct":78,"format_score":90,"improvements":["tip1"]}\n\n'
        f"JD keywords: {match.get('matched_skills', []) + match.get('missing_skills', [])[:4]}\n"
        f"Content:\n{combined}\nJD:\n{jd[:400]}"
    )
    try:
        raw = _llm(llm, [SystemMessage(content="ATS expert. Return ONLY valid JSON."),
                          HumanMessage(content=prompt)], "ats_score")
        raw = re.sub(r'^```(?:json)?\s*', '', raw.strip())
        raw = re.sub(r'\s*```$', '', raw).strip()
        m   = re.search(r'\{.*\}', raw, re.DOTALL)
        if m:
            return json.loads(m.group(0))
    except Exception as e:
        print(f"  [ATS] {e}")
    return {"ats_score": 75, "keyword_match_pct": 65, "format_score": 85, "improvements": []}


def _study_plan(llm, job_title, company, jd, match, resume) -> dict:
    from langchain_core.messages import HumanMessage, SystemMessage
    import memory_manager
    sys_prompt_sp = memory_manager.get_system_prompt("study_plan_generator")
    prompt = (
        "Generate a focused study plan. Return ONLY valid JSON with this exact structure:\n"
        '{"study_plan":[{"rank":1,"topic":"Topic name","why":"Why critical for this role",'
        '"resources":["Resource 1","Resource 2"],"priority":"high"}],'
        '"company_overview":"2-3 sentence overview of the company.",'
        '"industry":"Industry name","company_size":"startup or mid or enterprise",'
        '"role_highlights":["Key point about this role"],'
        '"missing_skills_to_learn":["skill1","skill2"]}\n\n'
        f"Role: {job_title} at {company}\n"
        f"Candidate skills: {', '.join(resume.get('skills', [])[:15])}\n"
        f"Skills gap (missing from JD): {match.get('missing_skills', [])}\n"
        f"JD: {jd[:800]}"
    )
    company_ctx = _fetch_company_overview_serper(company, job_title)

    try:
        enriched_prompt = prompt + f"\n\nCompany context (from web search): {company_ctx}"
        raw = _llm(llm, [SystemMessage(content=sys_prompt_sp),
                          HumanMessage(content=enriched_prompt)], "study_plan")
        raw = re.sub(r'^```(?:json)?\s*', '', raw.strip())
        raw = re.sub(r'\s*```$', '', raw).strip()
        m   = re.search(r'\{.*\}', raw, re.DOTALL)
        if m:
            parsed = json.loads(m.group(0))
            if isinstance(parsed.get("study_plan"), list) and len(parsed["study_plan"]) > 0:
                if not parsed.get("company_overview") or len(parsed["company_overview"]) < 30:
                    parsed["company_overview"] = company_ctx
                return parsed
    except Exception as e:
        print(f"  [StudyPlan] LLM failed: {e}")

    fallback = _build_fallback_study_plan(job_title, company, jd, match, resume)
    if company_ctx and len(company_ctx) > 30:
        fallback["company_overview"] = company_ctx
    return fallback


def _fetch_company_overview_serper(company: str, job_title: str) -> str:
    try:
        import config
        api_key = getattr(config, "SERPER_API_KEY", "")
        if not api_key:
            return f"{company} is hiring for {job_title}."

        import requests as req
        resp = req.post(
            "https://google.serper.dev/search",
            headers={"X-API-KEY": api_key, "Content-Type": "application/json"},
            data=json.dumps({"q": f"{company} company overview", "gl": "sg", "num": 3}),
            timeout=8,
        )
        resp.raise_for_status()
        data = resp.json()

        kg = data.get("knowledgeGraph", {})
        if kg.get("description"):
            return kg["description"][:300]

        ab = data.get("answerBox", {})
        if ab.get("snippet"):
            return ab["snippet"][:300]

        organic = data.get("organic", [])
        if organic and organic[0].get("snippet"):
            return organic[0]["snippet"][:300]

    except Exception as e:
        print(f"  [Serper] Company overview fetch failed: {e}")

    return f"{company} is hiring for {job_title}."


def _build_fallback_study_plan(job_title: str, company: str, jd: str,
                                match: dict, resume: dict) -> dict:
    missing  = match.get("missing_skills", [])
    matched  = match.get("matched_skills", [])
    skills   = resume.get("skills", [])
    exp_yrs  = resume.get("total_experience_years", 0)

    jd_words  = set(re.findall(r'\b[A-Za-z][A-Za-z0-9+#.]{2,}\b', jd))
    skill_set = {s.lower() for s in skills}
    jd_gaps   = [w for w in jd_words if w.lower() not in skill_set
                 and len(w) > 3 and w[0].isupper()][:8]

    all_topics = list(dict.fromkeys(missing + jd_gaps))[:8]

    RESOURCE_MAP = {
        "python":     ["Python.org docs", "Real Python"],
        "sql":        ["SQLZoo", "Mode Analytics"],
        "aws":        ["AWS Free Tier", "AWS Training"],
        "azure":      ["Microsoft Learn", "Azure Free Account"],
        "gcp":        ["Google Cloud Skills Boost", "Qwiklabs"],
        "docker":     ["Docker Docs", "Play with Docker"],
        "kubernetes": ["Kubernetes.io Docs", "Katacoda"],
        "tensorflow": ["TensorFlow.org Tutorials", "DeepLearning.AI Coursera"],
        "pytorch":    ["PyTorch.org Tutorials", "fast.ai"],
        "spark":      ["Databricks Academy (free)", "Apache Spark Docs"],
        "java":       ["Oracle Java Docs", "Baeldung"],
        "react":      ["React.dev", "Scrimba React"],
        "default":    ["Coursera", "YouTube"],
    }

    def get_resources(topic: str) -> list:
        key = topic.lower()
        for k, v in RESOURCE_MAP.items():
            if k in key:
                return v
        return RESOURCE_MAP["default"]

    priority_order = ["high", "high", "high", "medium", "medium", "low", "low", "low"]
    fallback_items = []
    for i, topic in enumerate(all_topics):
        fallback_items.append({
            "rank":      i + 1,
            "topic":     topic,
            "why":       f"Required for {job_title} - mentioned in job description",
            "resources": get_resources(topic),
            "priority":  priority_order[i] if i < len(priority_order) else "low",
        })

    if not fallback_items:
        fallback_items = [{
            "rank":      1,
            "topic":     f"Core competencies for {job_title}",
            "why":       f"Strengthen your expertise for {job_title} roles",
            "resources": ["LinkedIn Learning", "Coursera", "YouTube"],
            "priority":  "high",
        }]

    company_sentences = [s.strip() for s in re.split(r'[.!?]', jd)
                         if company.lower() in s.lower() and len(s.strip()) > 20]
    overview = (". ".join(company_sentences[:2]) + ".") if company_sentences else f"{company} is hiring for {job_title}."

    return {
        "study_plan":              fallback_items,
        "company_overview":        overview,
        "industry":                "",
        "company_size":            "",
        "role_highlights":         [
            f"Role: {job_title} at {company}",
            f"Candidate experience: {exp_yrs} years",
            f"Skills matched: {len(matched)} of {len(matched) + len(missing)}",
        ],
        "missing_skills_to_learn": missing,
    }


def _cover_letter(llm, resume, job_title, company, jd, match) -> str:
    from langchain_core.messages import HumanMessage, SystemMessage
    prompt = (
        f"Write a cover letter for {resume.get('name', 'Candidate')}.\n"
        f"Role: {job_title} at {company}\n"
        f"Strengths: {match.get('matched_skills', [])[:5]}\n"
        f"Experience: {resume.get('total_experience_years', 0)} years\n"
        f"JD: {jd[:500]}\n\n"
        "Rules: 3 paragraphs. No 'I am writing to apply'. To: Hiring Manager. "
        "Specific achievements. Confident close. Plain ASCII."
    )
    return _clean_ascii(_llm(llm, [SystemMessage(content="Cover letter writer. Plain ASCII."),
                                    HumanMessage(content=prompt)], "cover_letter"))


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def enhance_resume(
    llm, resume_json, match_json, job_title, company_name,
    job_description, original_pdf_path, original_file_name="resume",
) -> dict:
    resume = json.loads(resume_json)
    match  = json.loads(match_json)

    print(f"\n  [ResumeEnhancer] {job_title} @ {company_name}")

    # ── Setup output ──────────────────────────────────────────
    # Preserve original filename WITHOUT truncation to maintain user's naming convention
    base = Path(original_file_name).stem or "resume"
    # Only truncate company name for folder path (filesystem compatibility)
    co   = _safe_fn(company_name, n=40)
    ts   = datetime.now().strftime("%Y%m%d_%H%M%S")
    folder = OUTPUT_DIR / f"{ts}_{co}"
    folder.mkdir(parents=True, exist_ok=True)

    resume_pdf = folder / f"{base}_{co}.pdf"
    cover_pdf  = folder / f"CoverLetter_{co}.pdf"
    resume_txt = folder / f"{base}_{co}.txt"
    cover_txt  = folder / f"CoverLetter_{co}.txt"
    plan_json  = folder / "study_plan.json"
    edits_json = folder / "edit_summary.json"

    # ── Open original PDF ─────────────────────────────────────
    pdf_valid       = False
    links           = []
    exp_original    = ""
    skills_original = ""
    editor          = None

    if original_pdf_path and Path(original_pdf_path).exists():
        try:
            editor          = PDFSurgicalEditor(original_pdf_path)
            full_text       = editor.get_full_text()
            links           = editor.get_links()
            sections        = _split_sections(full_text)
            exp_original    = sections.get("experience", "")
            skills_original = sections.get("skills", "")
        except Exception as e:
            print(f"  [ResumeEnhancer] PDF open failed: {e}")

    # Fallback text from parsed JSON
    if not exp_original:
        exp_original = "\n".join(
            f"{e.get('title')} at {e.get('company')} | {e.get('duration')}\n{e.get('description', '')}"
            for e in resume.get("experience", [])
        )
    if not skills_original:
        skills_original = "SKILLS\n" + ", ".join(resume.get("skills", []))

    # ── Rewrite sections ──────────────────────────────────────
    exp_lines, edit_summary = _rewrite_experience(
        llm, exp_original, job_title, company_name, job_description, match
    )
    skills_lines = _rewrite_skills(llm, skills_original, job_description, match)

    # ── Apply surgical edit to PDF copy ──────────────────────
    import shutil
    edit_editor = None
    
    if not original_pdf_path or not Path(original_pdf_path).exists():
        raise FileNotFoundError(
            f"Cannot perform surgical PDF edit: original resume PDF not found or provided. "
            f"Path: {original_pdf_path}"
        )
    
    print(f"  [ResumeEnhancer] Attempting surgical PDF edit (NO FALLBACK TO REPORTLAB)")

    try:
        shutil.copy2(original_pdf_path, str(resume_pdf))
        edit_editor = PDFSurgicalEditor(str(resume_pdf))

        print(f"    - Replacing EXPERIENCE section...")
        edit_editor.replace_section_content(
            ["WORK EXPERIENCE", "EXPERIENCE", "PROFESSIONAL EXPERIENCE", "EMPLOYMENT"],
            exp_lines,
            experience_only_n_jobs=2,
        )
        
        print(f"    - Replacing SKILLS section...")
        edit_editor.replace_section_content(
            ["SKILLS", "TECHNICAL SKILLS", "CORE COMPETENCIES"],
            skills_lines,
        )
        
        edit_editor.save(resume_pdf)  # uses incremental=False internally
        pdf_valid = _is_valid_pdf(resume_pdf)
        if not pdf_valid:
            raise ValueError(f"Surgical save produced invalid PDF: {resume_pdf}")
        
        print(f"  [ResumeEnhancer] ✓ Surgical PDF edit successful - template preserved")
        
    except Exception as e:
        # NO FALLBACK - must fail loud
        error_msg = f"Surgical PDF edit failed (MANDATORY MODE): {e}"
        print(f"  [ResumeEnhancer] ✗ {error_msg}")
        # Clean up corrupt file
        try:
            resume_pdf.unlink(missing_ok=True)
        except Exception:
            pass
        raise RuntimeError(error_msg)
    finally:
        if edit_editor:
            try:
                edit_editor.close()
            except Exception:
                pass

    # ── Save .txt preview ─────────────────────────────────────
    txt_content = "\n".join(exp_lines) + "\n\n" + "\n".join(skills_lines)
    resume_txt.write_text(txt_content, encoding="utf-8")

    # ── Cover letter ──────────────────────────────────────────
    cover_text  = _cover_letter(llm, resume, job_title, company_name, job_description, match)
    cover_ok    = _save_cover_pdf(cover_text, cover_pdf, job_title, company_name)
    cover_txt.write_text(cover_text, encoding="utf-8")

    # ── Study plan + ATS ─────────────────────────────────────
    study = _study_plan(llm, job_title, company_name, job_description, match, resume)
    ats   = _score_ats(llm, "\n".join(exp_lines), "\n".join(skills_lines), job_description, match)

    plan_json.write_text(json.dumps(study,        indent=2), encoding="utf-8")
    edits_json.write_text(json.dumps(edit_summary, indent=2), encoding="utf-8")

    print(f"  [ResumeEnhancer] Done - ATS: {ats.get('ats_score')}%")

    return {
        "status":            "success",
        "output_folder":     str(folder),
        "resume_path":       str(resume_pdf) if pdf_valid else str(resume_txt),
        "cover_letter_path": str(cover_pdf)  if cover_ok  else str(cover_txt),
        "resume_txt_path":   str(resume_txt),
        "cover_txt_path":    str(cover_txt),
        "ats_score":         ats.get("ats_score", 0),
        "ats_details":       ats,
        "study_plan":        study,
        "edit_summary":      edit_summary,
        "cover_text":        cover_text,
        "links_preserved":   len(links),
        "pdf_valid":         pdf_valid,
        "rewritten": {
            "experience": "\n".join(exp_lines),
            "skills":     "\n".join(skills_lines),
        },
    }


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _split_sections(text: str) -> dict:
    """Split resume text into named sections."""
    HEADERS = [
        (r"(?i)^(work experience|experience|professional experience|employment)", "experience"),
        (r"(?i)^(skills|technical skills|core competencies|key skills)",          "skills"),
        (r"(?i)^(education|academic background)",                                  "education"),
        (r"(?i)^(summary|professional summary|objective|professional objective|profile)", "summary"),
        (r"(?i)^(certifications?|awards?|publications?|projects?|languages?)",    "other"),
        (r"(?i)^(contact|personal)",                                               "contact"),
    ]
    sections, current, buf = {}, "header", []
    for line in text.split("\n"):
        matched = False
        for pat, key in HEADERS:
            if re.match(pat, line.strip()):
                sections[current] = "\n".join(buf).strip()
                current, buf = key, [line]
                matched = True
                break
        if not matched:
            buf.append(line)
    sections[current] = "\n".join(buf).strip()
    return sections


def _build_fallback_pdf(resume: dict, exp_lines: list,
                         skills_lines: list, links: list,
                         output_path: Path) -> bool:
    """
    Build a clean PDF from scratch using reportlab (same engine as resume_builder).
    Returns True on success, False on failure.
    Never writes non-PDF bytes to output_path.
    """
    try:
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
        from reportlab.lib.units import mm
        from reportlab.lib import colors
        from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, HRFlowable

        MARGIN = 18 * mm
        ACCENT = colors.HexColor("#5B4FE9")
        DARK   = colors.HexColor("#1E1E1E")
        MID    = colors.HexColor("#3C3C3C")

        styles = getSampleStyleSheet()
        style_header = ParagraphStyle("FBHeader", parent=styles["Normal"],
                                       fontName="Helvetica-Bold", fontSize=11,
                                       textColor=DARK, spaceBefore=8, spaceAfter=1)
        style_normal = ParagraphStyle("FBNormal", parent=styles["Normal"],
                                       fontName="Helvetica", fontSize=10,
                                       textColor=MID, spaceAfter=2, leading=14)
        style_bullet = ParagraphStyle("FBBullet", parent=styles["Normal"],
                                       fontName="Helvetica", fontSize=9,
                                       textColor=MID, leftIndent=10,
                                       spaceAfter=1, leading=13)

        def esc(s):
            return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

        # Build full text from resume dict + rewritten sections
        full_lines = (
            [
                resume.get("name", ""),
                f"{resume.get('email','')} | {resume.get('phone','')} | {resume.get('location','')}",
                resume.get("linkedin", ""),
                "",
                "PROFESSIONAL SUMMARY",
                resume.get("summary", ""),
                "",
            ]
            + skills_lines
            + ["", "EXPERIENCE", ""]
            + exp_lines
            + ["", "EDUCATION", ""]
            + [
                f"{e.get('degree')} - {e.get('institution')} ({e.get('year')})"
                for e in resume.get("education", [])
            ]
        )

        doc = SimpleDocTemplate(
            str(output_path),
            pagesize=A4,
            leftMargin=MARGIN, rightMargin=MARGIN,
            topMargin=MARGIN,  bottomMargin=MARGIN,
        )

        story = []
        for raw_line in full_lines:
            line = _clean_ascii(raw_line).strip()
            if not line:
                story.append(Spacer(1, 3))
                continue
            safe = esc(line)
            if line.isupper() and 2 < len(line) < 60:
                story.append(Spacer(1, 4))
                story.append(Paragraph(safe, style_header))
                story.append(HRFlowable(width="100%", thickness=0.5,
                                         color=ACCENT, spaceAfter=2))
            elif line.startswith(("-", "*", "•")):
                story.append(Paragraph("- " + esc(line.lstrip("-*• ").strip()), style_bullet))
            else:
                story.append(Paragraph(safe, style_normal))

        if links:
            story.append(Spacer(1, 6))
            story.append(Paragraph("LINKS", style_header))
            story.append(HRFlowable(width="100%", thickness=0.5, color=ACCENT, spaceAfter=2))
            link_style = ParagraphStyle("FBLink", parent=styles["Normal"],
                                         fontName="Helvetica", fontSize=8,
                                         textColor=colors.blue, spaceAfter=1)
            for link in links[:10]:
                safe_link = esc(link)
                story.append(Paragraph(
                    f'<link href="{safe_link}" color="blue">{safe_link}</link>',
                    link_style,
                ))

        doc.build(story)

        if not _is_valid_pdf(output_path):
            raise ValueError("Fallback PDF failed validity check")

        size = output_path.stat().st_size
        print(f"  [FallbackPDF] Saved: {output_path.name} ({size:,}b)")
        return True

    except Exception as e:
        print(f"  [FallbackPDF] Failed: {e}")
        try:
            output_path.unlink(missing_ok=True)
        except Exception:
            pass
        return False