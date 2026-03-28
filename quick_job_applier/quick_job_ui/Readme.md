# QuickJob Applier — Frontend

React SPA for QuickJob Applier. Four-step guided workflow: upload resume → select portals + titles → browse jobs → apply and track.

---

## Quick Start

```bash
# Must be run from native filesystem (not VirtualBox shared drive)
cd ~/quick_job_ui
npm install
npm start
# Opens at http://localhost:3000
# Backend must be running at http://localhost:8001
```

---

## Folder Structure

```
quick_job_ui/src/
├── App.jsx                          # Root — all 4 steps
├── App.css                          # Complete design system
├── index.js                         # Entry — wraps App in BackendGate
│
├── api/
│   └── client.js                    # All axios API calls
│
├── hooks/
│   └── useJobApply.js               # All state + async logic
│
└── components/
    ├── BackendGate.jsx              # Blocks UI until backend reachable
    ├── StepIndicator.jsx            # Clickable step progress (back nav)
    ├── ResumeDropzone.jsx           # PDF drag-and-drop upload
    ├── JobTitleSelector.jsx         # Dynamic titles + custom input + spell check
    ├── PortalMultiSelect.jsx        # Portal selection in Step 1, grouped by tier
    ├── CountrySearch.jsx            # Country picker with flag + portal count
    ├── PortalCard.jsx               # Portal confirm cards with tier badges
    ├── JobListings.jsx              # Job cards + 4-tab preview modal
    ├── PdfViewer.jsx                # react-pdf inline viewer
    └── AppliedResumesPanel.jsx      # Browse / preview / delete generated files
```

---

## User Flow

### Step 1 — Upload + Preferences (one screen)
- Drag-and-drop PDF upload + inline preview
- Job titles suggested automatically from resume:
  - `⚡ From cache` — same resume before (0 tokens)
  - `📋 From skills` — taxonomy match (0 tokens)
  - `🤖 AI suggested` — LLM (cached for reuse)
  - Top titles auto-selected, add custom titles with spell correction
- Portal selection (Tier 1 → 2 → 3, grouped with select-all per tier)
- Country selection

### Step 2 — Confirm Portals
- Filtered by country, sorted Tier 1 first
- Confirm which portals to search

### Step 3 — Select Jobs
Each card shows: match score ring, company, location, salary, posted date, applicants, full JD.

**Preview Tailored Resume** opens a 4-tab modal:
| Tab | Content |
|-----|---------|
| Enhanced Resume | PDF inline — same format as original, bullets updated |
| Cover Letter | Personalised per company, PDF inline |
| What Changed | Before/after diff of every changed bullet with reason |
| Study Plan | Ordered topics to learn, skills gap, company overview |

### Step 4 — Apply + Track
- Playwright opens a browser per job
- Tier 1: fully automated, closes on success
- Tier 2/3: pre-filled browser, user assists, auto-closes after 2 min
- Live status per job

---

## Component Notes

**`JobTitleSelector`**
- Shows AI-suggested titles pinned at top with a "Suggested from your resume" label
- Custom title input: press Enter or click Add
- Spell correction fires as you type — click suggestion to apply
- Synonym groups expanded automatically

**`PortalMultiSelect`**
- Grouped by tier (1/2/3) with colour-coded badges
- "Select all" per tier button
- Shows restriction notes (e.g. "SingPass required")

**`BackendGate`**
- Polls `GET /` every 3 seconds
- Shows attempt count, elapsed time, startup command
- Fades app in on connection

**`useJobApply` hook**
- `resumeFile` change triggers `fetchResumeTitles()` automatically
- `openPreview()` checks `sessionId` first — shows clear message if expired
- `sessionId` is a `useRef` — never stale, always reads current value

---

## API Client (`src/api/client.js`)

| Function | Endpoint |
|----------|----------|
| `getResumeTitles(file, country)` | `POST /resume-job-titles` |
| `uploadResume(formData)` | `POST /upload-resume` |
| `searchJobs(sessionId, portals)` | `POST /search-jobs` |
| `getSearchStatus(sessionId)` | `GET /search-status/{id}` |
| `previewResume(sessionId, job)` | `POST /preview-resume` |
| `getTailoredPdfUrl(sid, jid, doc)` | URL builder |
| `getResumePdfUrl(sessionId)` | URL builder |
| `applyJobs(sessionId)` | `POST /apply` |
| `getApplyStatus(sessionId)` | `GET /apply-status/{id}` |
| `listAppliedResumes()` | `GET /applied-resumes` |
| `deleteAppliedResume(folder)` | `DELETE /applied-resumes/{folder}` |

---

## Design Tokens

```css
--bg:       #07070E   --surface:  #0F0F1C
--accent:   #5B4FE9   --green:    #00D68F
--yellow:   #F7C948   --red:      #F0364C
--text:     #EEEEF5   --text-2:   #9999BB
```

---

## Known Gotchas

- `npm install` must run from native filesystem (`~/quick_job_ui`), not VirtualBox shared drives
- No `"proxy"` in `package.json` — axios uses full URL `http://localhost:8001`
- Session expires on backend restart — re-upload resume to continue
- PDF viewer uses CDN worker (`cdnjs.cloudflare.com`) — requires internet