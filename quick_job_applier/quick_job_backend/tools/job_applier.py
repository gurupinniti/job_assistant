"""
JobApplierTool — RPA-style application automation

Browser stays open after navigation. Auto-closes after:
  - Successful submit
  - User closes window
  - MAX_OPEN_SECONDS timeout
"""

import json
import time
from pathlib import Path
from typing import Type, Any
from pydantic import BaseModel, Field
from langchain_core.tools import BaseTool

MAX_OPEN_SECONDS = 120   # auto-close browser after 2 minutes if no action

PORTAL_STRATEGIES = {
    "LinkedIn":        "_apply_linkedin",
    "Indeed":          "_apply_indeed",
    "JobStreet":       "_apply_jobstreet",
    "Adzuna":          "_apply_adzuna",
    "RemoteOK":        "_apply_generic_direct",
    "Arbeitnow":       "_apply_generic_direct",
    "TheMuse":         "_apply_generic_direct",
    "Jobsdb":          "_apply_generic_direct",
    "Naukri":          "_apply_naukri",
    "Seek":            "_apply_seek",
    "Reed":            "_apply_reed",
    "MyCareersFuture": "_apply_mcf",
    "default":         "_apply_generic_direct",
}


class JobApplierInput(BaseModel):
    portal:            str = Field(description="Portal name")
    job_url:           str = Field(description="Direct URL to the job listing")
    resume_path:       str = Field(description="Path to tailored resume PDF")
    cover_letter_path: str = Field(description="Path to cover letter PDF")
    resume_json:       str = Field(description="Parsed resume JSON")


class JobApplierTool(BaseTool):
    name: str = "job_applier"
    description: str = "RPA-style job application automation. Opens browser, fills forms, submits."
    args_schema: Type[BaseModel] = JobApplierInput
    credentials: dict = Field(default_factory=dict)

    def _get_browser(self):
        try:
            from playwright.sync_api import sync_playwright
            return sync_playwright
        except ImportError:
            return None

    def _fill_fields(self, page: Any, resume: dict):
        """Fill common form fields."""
        mapping = {
            'input[name*="name" i], input[placeholder*="name" i]':          resume.get("name", ""),
            'input[name*="email" i], input[type="email"]':                   resume.get("email", ""),
            'input[name*="phone" i], input[type="tel"]':                     resume.get("phone", ""),
            'input[name*="linkedin" i], input[placeholder*="linkedin" i]':   resume.get("linkedin", ""),
            'textarea[name*="cover" i], textarea[placeholder*="cover" i]':   self._cover_summary(resume),
        }
        for selector, value in mapping.items():
            if not value:
                continue
            try:
                for el in page.query_selector_all(selector):
                    if el.is_visible():
                        tag = el.evaluate("el => el.tagName.toLowerCase()")
                        if tag == "textarea":
                            el.fill(value[:1000])
                        else:
                            el.fill(value)
                        break
            except Exception:
                pass

    def _cover_summary(self, resume: dict) -> str:
        exp = resume.get("experience", [{}])
        role = exp[0].get("title", "") if exp else ""
        return (
            f"I am {resume.get('name', 'a candidate')} with "
            f"{resume.get('total_experience_years', 0)} years of experience as {role}. "
            f"Key skills: {', '.join(resume.get('skills', [])[:6])}."
        )

    def _upload_resume(self, page: Any, resume_path: str) -> bool:
        try:
            for sel in ['input[type="file"]', 'input[accept*="pdf" i]']:
                el = page.query_selector(sel)
                if el:
                    el.set_input_files(resume_path)
                    return True
        except Exception:
            pass
        return False

    def _wait_for_close_or_timeout(self, page: Any, timeout: int = MAX_OPEN_SECONDS) -> str:
        """Wait until user closes the window or timeout reached."""
        start = time.time()
        while time.time() - start < timeout:
            try:
                if page.is_closed():
                    return "user_closed"
                page.wait_for_timeout(2000)
            except Exception:
                return "user_closed"
        return "timeout"

    def _screenshot(self, page: Any, portal: str, resume_path: str) -> str:
        try:
            ss = Path(resume_path).parent / f"{portal}_screenshot.png"
            page.screenshot(path=str(ss), full_page=False)
            return str(ss)
        except Exception:
            return ""

    # ------------------------------------------------------------------
    # Portal methods
    # ------------------------------------------------------------------

    def _apply_adzuna(self, page, job_url, resume, resume_path, cover_path):
        """Adzuna redirects to company site — fill what we can."""
        page.goto(job_url, timeout=30000)
        page.wait_for_timeout(2000)
        # Click apply button
        for sel in ['a[href*="apply"]', 'button:has-text("Apply")', 'a:has-text("Apply")']:
            btn = page.query_selector(sel)
            if btn and btn.is_visible():
                btn.click()
                page.wait_for_timeout(2000)
                break
        self._fill_fields(page, resume)
        self._upload_resume(page, resume_path)
        # Try to submit
        for sel in ['button[type="submit"]', 'input[type="submit"]', 'button:has-text("Submit")']:
            btn = page.query_selector(sel)
            if btn and btn.is_visible():
                btn.click()
                page.wait_for_timeout(2000)
                return {"status": "success", "message": "Applied via Adzuna"}
        close_reason = self._wait_for_close_or_timeout(page)
        return {"status": "partial", "reason": f"Form opened — {close_reason}. Please verify."}

    def _apply_generic_direct(self, page, job_url, resume, resume_path, cover_path):
        """Generic RPA: navigate → find apply → fill → submit."""
        page.goto(job_url, timeout=30000)
        page.wait_for_timeout(2000)

        # Look for apply button
        apply_selectors = [
            'a[href*="apply"]', 'button:has-text("Apply Now")',
            'button:has-text("Apply")', 'a:has-text("Apply Now")',
            'a:has-text("Apply")', '[class*="apply-btn"]',
        ]
        clicked = False
        for sel in apply_selectors:
            btn = page.query_selector(sel)
            if btn and btn.is_visible():
                btn.click()
                page.wait_for_timeout(2000)
                clicked = True
                break

        self._fill_fields(page, resume)
        self._upload_resume(page, resume_path)

        # Try submit
        for sel in ['button[type="submit"]', 'input[type="submit"]',
                    'button:has-text("Submit")', 'button:has-text("Send Application")']:
            btn = page.query_selector(sel)
            if btn and btn.is_visible():
                btn.click()
                page.wait_for_timeout(2000)
                return {"status": "success", "message": f"Application submitted"}

        close_reason = self._wait_for_close_or_timeout(page)
        return {"status": "partial", "reason": f"Browser {'closed by user' if close_reason == 'user_closed' else 'timed out'}"}

    def _apply_linkedin(self, page, job_url, resume, resume_path, cover_path):
        title    = (resume.get("experience") or [{}])[0].get("title", "Software Engineer")
        location = resume.get("location", "Singapore")
        url      = (
            "https://www.linkedin.com/jobs/search/"
            f"?keywords={title.replace(' ', '%20')}"
            f"&location={location.replace(' ', '%20')}"
            "&f_LF=f_AL&sortBy=R"
        )
        page.goto(url, timeout=30000)
        page.wait_for_timeout(2000)

        # Check login wall
        if page.query_selector('input[name="session_key"], #username'):
            print("  [LinkedIn] Login required — waiting up to 60s for manual login...")
            for _ in range(20):
                page.wait_for_timeout(3000)
                if not page.query_selector('input[name="session_key"]'):
                    break
            else:
                return {"status": "manual_required",
                        "reason": "LinkedIn login needed. Resume saved — apply manually.",
                        "job_url": url}
            page.goto(url, timeout=30000)
            page.wait_for_timeout(3000)

        first = page.query_selector("li.jobs-search-results__list-item, .job-card-container")
        if not first:
            return {"status": "manual_required", "reason": "No Easy Apply jobs found", "job_url": url}
        first.click()
        page.wait_for_timeout(2000)

        ea = page.query_selector("button.jobs-apply-button, button[aria-label*='Easy Apply']")
        if not ea:
            close_reason = self._wait_for_close_or_timeout(page, 30)
            return {"status": "manual_required", "reason": "No Easy Apply button", "job_url": page.url}
        ea.click()
        page.wait_for_timeout(1500)

        for _ in range(10):
            self._fill_fields(page, resume)
            self._upload_resume(page, resume_path)
            page.wait_for_timeout(800)
            sub = page.query_selector('button[aria-label="Submit application"]')
            rev = page.query_selector('button[aria-label="Review your application"]')
            nxt = page.query_selector('button[aria-label="Continue to next step"]')
            if sub:
                sub.click()
                page.wait_for_timeout(2000)
                return {"status": "success", "message": "Submitted via LinkedIn Easy Apply"}
            elif rev:
                rev.click()
            elif nxt:
                nxt.click()
            else:
                break
            page.wait_for_timeout(1000)

        close_reason = self._wait_for_close_or_timeout(page)
        return {"status": "partial", "reason": "Easy Apply form opened — manual completion needed"}

    def _apply_indeed(self, page, job_url, resume, resume_path, cover_path):
        title    = (resume.get("experience") or [{}])[0].get("title", "Software Engineer")
        location = resume.get("location", "")
        url      = f"https://www.indeed.com/jobs?q={title.replace(' ', '+')}&l={location.replace(' ', '+')}"
        page.goto(url, timeout=30000)
        page.wait_for_timeout(3000)
        first = page.query_selector(".job_seen_beacon, .tapItem, [data-jk]")
        if not first:
            return {"status": "manual_required", "reason": "No Indeed jobs found", "job_url": url}
        first.click()
        page.wait_for_timeout(2000)
        btn = page.query_selector("button#indeedApplyButton, button[data-indeed-apply]")
        if not btn:
            return {"status": "manual_required", "reason": "No apply button", "job_url": page.url}
        btn.click()
        page.wait_for_timeout(2000)
        self._fill_fields(page, resume)
        self._upload_resume(page, resume_path)
        sub = page.query_selector('button[type="submit"]')
        if sub:
            sub.click()
            page.wait_for_timeout(2000)
            return {"status": "success", "message": "Submitted via Indeed"}
        close_reason = self._wait_for_close_or_timeout(page)
        return {"status": "partial", "reason": "Indeed form opened — manual completion needed"}

    def _apply_jobstreet(self, page, job_url, resume, resume_path, cover_path):
        page.goto(job_url, timeout=30000)
        page.wait_for_timeout(2000)
        btn = page.query_selector('a[data-automation="job-detail-apply"], button[class*="apply"]')
        if btn:
            btn.click()
            page.wait_for_timeout(2000)
            self._fill_fields(page, resume)
            self._upload_resume(page, resume_path)
        close_reason = self._wait_for_close_or_timeout(page)
        return {"status": "partial", "reason": "JobStreet opened — login may be needed"}

    def _apply_naukri(self, page, job_url, resume, resume_path, cover_path):
        page.goto(job_url, timeout=30000)
        page.wait_for_timeout(2000)
        btn = page.query_selector('button#apply-button, a.apply-button')
        if btn:
            btn.click()
            page.wait_for_timeout(1500)
            self._fill_fields(page, resume)
            self._upload_resume(page, resume_path)
            sub = page.query_selector('button[type="submit"]')
            if sub:
                sub.click()
                return {"status": "success", "message": "Applied via Naukri"}
        close_reason = self._wait_for_close_or_timeout(page)
        return {"status": "partial", "reason": "Naukri opened — manual completion needed"}

    def _apply_seek(self, page, job_url, resume, resume_path, cover_path):
        page.goto(job_url, timeout=30000)
        page.wait_for_timeout(2000)
        self._fill_fields(page, resume)
        self._upload_resume(page, resume_path)
        close_reason = self._wait_for_close_or_timeout(page)
        return {"status": "partial", "reason": "Seek opened — account login recommended"}

    def _apply_reed(self, page, job_url, resume, resume_path, cover_path):
        page.goto(job_url, timeout=30000)
        page.wait_for_timeout(2000)
        btn = page.query_selector('a[href*="apply"], button:has-text("Apply")')
        if btn:
            btn.click()
            page.wait_for_timeout(2000)
            self._fill_fields(page, resume)
            self._upload_resume(page, resume_path)
        sub = page.query_selector('button[type="submit"]')
        if sub:
            sub.click()
            return {"status": "success", "message": "Applied via Reed"}
        close_reason = self._wait_for_close_or_timeout(page)
        return {"status": "partial", "reason": "Reed form opened"}

    def _apply_mcf(self, page, job_url, resume, resume_path, cover_path):
        return {"status": "restricted", "reason": "MyCareersFuture requires SingPass — cannot automate"}

    # ------------------------------------------------------------------
    # Run
    # ------------------------------------------------------------------

    def _run(self, portal: str, job_url: str, resume_path: str,
             cover_letter_path: str, resume_json: str) -> str:
        print(f"  [JobApplier] {portal}: {job_url[:70]}")
        resume = json.loads(resume_json)

        sync_playwright = self._get_browser()
        if sync_playwright is None:
            return json.dumps({
                "portal": portal, "status": "manual_required",
                "reason": "Playwright not installed. Run: pip install playwright && python -m playwright install chromium",
                "job_url": job_url,
            })

        method = getattr(self, PORTAL_STRATEGIES.get(portal, "_apply_generic_direct"),
                         self._apply_generic_direct)

        result = {}
        try:
            with sync_playwright() as p:
                browser = p.chromium.launch(
                    headless=False,
                    args=["--no-sandbox", "--disable-dev-shm-usage"],
                )
                ctx  = browser.new_context()
                page = ctx.new_page()

                result = method(page, job_url, resume, resume_path, cover_letter_path)
                result["screenshot"] = self._screenshot(page, portal, resume_path)

                # Auto-close after terminal state
                if result.get("status") in ("success", "restricted"):
                    page.wait_for_timeout(2000)
                    browser.close()
                else:
                    # Leave open for user, close on window close or timeout
                    self._wait_for_close_or_timeout(page, MAX_OPEN_SECONDS)
                    try:
                        browser.close()
                    except Exception:
                        pass

        except Exception as e:
            result = {"status": "error", "reason": str(e)}

        result["portal"]  = portal
        result["job_url"] = job_url
        print(f"  [JobApplier] {portal} → {result.get('status')}: {result.get('reason') or result.get('message','')}")
        return json.dumps(result, indent=2)

    async def _arun(self, portal: str, job_url: str, resume_path: str,
                    cover_letter_path: str, resume_json: str) -> str:
        return self._run(portal, job_url, resume_path, cover_letter_path, resume_json)