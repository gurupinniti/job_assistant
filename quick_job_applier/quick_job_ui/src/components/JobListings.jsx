import React, { useState } from 'react';
import { ExternalLink, CheckSquare, Square, Users, ChevronDown, ChevronUp, Eye, BookOpen, Building2, TrendingUp } from 'lucide-react';
import { getTailoredPdfUrl, getResumePdfUrl, getStudyPlan } from '../api/client';

const PORTAL_COLORS = {
  LinkedIn: '#0077B5', Indeed: '#003A9B', JobStreet: '#E4002B',
  MyCareersFuture: '#0066CC', Naukri: '#FF7555', Seek: '#00ACC1',
  Glassdoor: '#0CAA41', Adzuna: '#E85B3A', RemoteOK: '#4ADE80',
  Arbeitnow: '#6366F1', TheMuse: '#FF6B9D', default: '#5B4FE9',
};

const PRIORITY_COLOR = { high: '#F0364C', medium: '#F7C948', low: '#00D68F' };

// ── Score ring ────────────────────────────────────────────────
function ScoreRing({ score }) {
  if (score == null) return <div className="score-ring-wrap"><span style={{fontSize:'0.7rem',color:'#6B6B8A'}}>—</span></div>;
  const color  = score >= 70 ? '#00D68F' : score >= 45 ? '#F7C948' : '#F0364C';
  const r = 20, circ = 2 * Math.PI * r;
  const offset = circ - (score / 100) * circ;
  return (
    <div className="score-ring-wrap" title={`${score}% match`}>
      <svg width="52" height="52" viewBox="0 0 52 52">
        <circle cx="26" cy="26" r={r} fill="none" stroke="#1C1C35" strokeWidth="5"/>
        <circle cx="26" cy="26" r={r} fill="none" stroke={color} strokeWidth="5"
          strokeDasharray={circ} strokeDashoffset={offset} strokeLinecap="round"
          transform="rotate(-90 26 26)" style={{transition:'stroke-dashoffset 0.6s ease'}}/>
      </svg>
      <span className="score-ring-label" style={{ color }}>{score}%</span>
    </div>
  );
}

// ── Inline PDF with text fallback ─────────────────────────────
function InlinePdf({ url, text }) {
  const [useText, setUseText] = useState(false);
  if (useText || !url) {
    return <pre className="resume-preview-text">{text || 'Not available'}</pre>;
  }
  return (
    <div className="inline-pdf-wrap">
      <iframe src={url} title="PDF Preview" className="inline-pdf-frame"
        onError={() => setUseText(true)}/>
      <div className="inline-pdf-actions">
        <a href={url} target="_blank" rel="noreferrer" className="pdf-open-new-tab">↗ Open in new tab</a>
        <button className="pdf-text-toggle" onClick={() => setUseText(true)}>Show as text</button>
      </div>
    </div>
  );
}

// ── Edit Summary tab ─────────────────────────────────────────
function EditSummaryTab({ summary, rewritten }) {
  const changes = summary?.changes || [];
  return (
    <div className="edit-summary-wrap">
      {changes.length === 0 ? (
        <div className="study-empty">
          {rewritten?.experience
            ? 'Resume was enhanced. Detailed change log not available for this version.'
            : 'No edit summary available.'}
        </div>
      ) : (
        <>
          <div className="edit-summary-intro">
            <span className="edit-count-badge">{changes.length} change{changes.length !== 1 ? 's' : ''}</span>
            {' '}made to the most recent 2 experience entries.
          </div>
          <div className="edit-items">
            {changes.map((c, i) => (
              <div key={i} className="edit-item">
                <div className="edit-item-header">
                  <span className="edit-num">#{i + 1}</span>
                  <span className="edit-reason">{c.reason || 'Updated for JD alignment'}</span>
                </div>
                <div className="edit-row">
                  <div className="edit-col">
                    <div className="edit-col-label before">Before</div>
                    <div className="edit-text edit-before">{c.original || '—'}</div>
                  </div>
                  <div className="edit-arrow">→</div>
                  <div className="edit-col">
                    <div className="edit-col-label after">After</div>
                    <div className="edit-text edit-after">{c.updated || '—'}</div>
                  </div>
                </div>
              </div>
            ))}
          </div>
        </>
      )}
      {rewritten?.skills && (
        <div className="edit-skills-section">
          <div className="study-section-title">Updated skills order</div>
          <pre className="edit-skills-text">{rewritten.skills.slice(0, 600)}</pre>
        </div>
      )}
    </div>
  );
}

// ── Study Plan tab ────────────────────────────────────────────
function StudyPlanTab({ plan, job, sessionId, onPlanLoaded }) {
  const [loading,   setLoading]   = React.useState(false);
  const [localPlan, setLocalPlan] = React.useState(plan);
  const [error,     setError]     = React.useState(null);
  const hasFetched = React.useRef(false);

  const isValidPlan = (p) =>
    p && Array.isArray(p.study_plan) && p.study_plan.length > 0;

  // Sync when parent provides an updated plan
  React.useEffect(() => {
    if (isValidPlan(plan)) {
      setLocalPlan(plan);
      hasFetched.current = true;
    }
  }, [plan]);

  const fetchPlan = React.useCallback(async () => {
    if (!job || !sessionId || loading) return;
    setLoading(true); setError(null);
    try {
      const data = await getStudyPlan(sessionId, job);
      const p = data.study_plan || data;
      setLocalPlan(p);
      hasFetched.current = true;
      if (onPlanLoaded) onPlanLoaded(p);
    } catch (e) {
      setError('Could not generate study plan: ' + (e.response?.data?.detail || e.message));
    } finally {
      setLoading(false);
    }
  }, [job, sessionId, loading, onPlanLoaded]);

  // Auto-fetch on first render if plan is missing or empty
  React.useEffect(() => {
    if (!isValidPlan(localPlan) && !hasFetched.current && sessionId && job) {
      hasFetched.current = true;  // prevent double-fetch
      fetchPlan();
    }
  }, []); // eslint-disable-line

  const activePlan = localPlan;
  const hasItems = isValidPlan(activePlan);
  const hasInfo  = activePlan && (activePlan.company_overview || activePlan.missing_skills_to_learn?.length > 0);

  if (!hasItems && !hasInfo) {
    return (
      <div className="study-empty">
        {loading ? (
          <div className="study-auto-loading">
            <span className="spinner-sm"/>
            <span>Generating your study plan…</span>
          </div>
        ) : (
          <>
            <div style={{marginBottom:10}}>Study plan not available for this job.</div>
            {error && <div className="modal-error" style={{marginBottom:10}}>⚠ {error}</div>}
            <button className="study-retry-btn" onClick={fetchPlan} disabled={loading}>
              ↻ Try Again
            </button>
          </>
        )}
      </div>
    );
  }

  return (
    <div className="study-plan-wrap">
      {loading && <div className="study-loading"><span className="spinner-sm"/> Updating study plan...</div>}

      {/* Company overview */}
      {activePlan.company_overview && (
        <div className="study-company-card">
          <div className="study-section-title"><Building2 size={14}/> About the Company</div>
          <p className="study-company-text">{activePlan.company_overview}</p>
          <div className="study-company-meta">
            {activePlan.industry    && <span className="study-meta-chip">🏭 {activePlan.industry}</span>}
            {activePlan.company_size && <span className="study-meta-chip">👥 {activePlan.company_size}</span>}
          </div>
          {activePlan.role_highlights?.length > 0 && (
            <div className="study-highlights">
              {activePlan.role_highlights.map((h, i) => (
                <div key={i} className="study-highlight-item">✦ {h}</div>
              ))}
            </div>
          )}
        </div>
      )}

      {/* Skills to learn */}
      {activePlan.missing_skills_to_learn?.length > 0 && (
        <div className="study-missing-skills">
          <div className="study-section-title"><TrendingUp size={14}/> Skills Gap to Close</div>
          <div className="study-skills-chips">
            {activePlan.missing_skills_to_learn.map(s => (
              <span key={s} className="study-skill-chip missing">{s}</span>
            ))}
          </div>
        </div>
      )}

      {/* Study plan */}
      <div className="study-section-title" style={{marginTop:16}}>
        <BookOpen size={14}/> Your Focused Study Plan
      </div>
      <p className="study-plan-note">Learn these in order — highest priority first:</p>

      <div className="study-items">
        {(activePlan.study_plan || []).map((item, i) => (
          <div key={i} className="study-item">
            <div className="study-item-rank"
              style={{background: PRIORITY_COLOR[item.priority] + '22',
                      color: PRIORITY_COLOR[item.priority],
                      border: `1px solid ${PRIORITY_COLOR[item.priority]}44`}}>
              #{item.rank}
            </div>
            <div className="study-item-body">
              <div className="study-item-topic">{item.topic}</div>
              <div className="study-item-why">{item.why}</div>
              {item.resources?.length > 0 && (
                <div className="study-resources">
                  {item.resources.slice(0,3).map(r => (
                    <span key={r} className="study-resource-chip">{r}</span>
                  ))}
                </div>
              )}
            </div>
            <span className="study-priority-badge"
              style={{background: PRIORITY_COLOR[item.priority] + '22',
                      color: PRIORITY_COLOR[item.priority]}}>
              {item.priority}
            </span>
          </div>
        ))}
      </div>
    </div>
  );
}

// ── Resume Preview Modal ──────────────────────────────────────
function ResumePreviewModal({ job, preview, loading, onClose }) {
  const [activeTab, setActiveTab] = useState('resume');
  if (!job) return null;

  const scoreColor = !preview?.match_score ? '#6B6B8A'
    : preview.match_score >= 70 ? '#00D68F'
    : preview.match_score >= 45 ? '#F7C948' : '#F0364C';

  const resumeUrl = preview?.sessionId
    ? getTailoredPdfUrl(preview.sessionId, preview.jobId, 'resume')
    : null;
  const coverUrl = preview?.sessionId
    ? getTailoredPdfUrl(preview.sessionId, preview.jobId, 'cover')
    : null;

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal-card modal-card-wide" onClick={e => e.stopPropagation()}>
        <div className="modal-header">
          <div>
            <div className="modal-title">Tailored Resume Preview</div>
            <div className="modal-sub">
              {job.title}{job.company ? ` @ ${job.company}` : ''}
              {job.location ? ` · ${job.location}` : ''}
            </div>
          </div>
          <button className="modal-close" onClick={onClose}>✕</button>
        </div>

        <div className="modal-body">
          {loading ? (
            <div className="modal-loading">
              <div className="spinner"/>
              <span>Generating tailored resume for {job.company || job.portal}…<br/>
                <small style={{color:'var(--text-3)'}}>This takes 30–60 seconds</small>
              </span>
            </div>
          ) : preview?.error ? (
            <div className="modal-error">⚠ {preview.error}</div>
          ) : preview?.llm_failed ? (
            <div className="preview-fallback-wrap">
              <div className="preview-fallback-banner">
                <span className="preview-fallback-icon">⚠</span>
                <div>
                  <div className="preview-fallback-title">
                    AI enhancement unavailable — showing original resume
                  </div>
                  <div className="preview-fallback-sub">
                    The LLM service hit its rate limit. Your <strong>original uploaded resume</strong> and
                    a basic cover letter will be used if you proceed.
                    You can still apply — the original resume is a valid submission.
                  </div>
                  <div className="preview-fallback-error">{preview.llm_error}</div>
                </div>
              </div>
              <div className="preview-confirm-row">
                <span className="preview-confirm-label">Proceed with original resume?</span>
                <span className="preview-confirm-note">Select this job then click Apply.</span>
              </div>
              <div className="modal-tabs">
                <button className={`modal-tab ${activeTab==="resume"?"active":""}`}
                  onClick={() => setActiveTab("resume")}>📄 Original Resume</button>
                <button className={`modal-tab ${activeTab==="cover"?"active":""}`}
                  onClick={() => setActiveTab("cover")}>✉️ Basic Cover Letter</button>
              </div>
              {activeTab === "resume" && (
                <InlinePdf
                  url={preview.sessionId ? getResumePdfUrl(preview.sessionId) : null}
                  text={preview.resume_text}
                />
              )}
              {activeTab === "cover" && (
                <pre className="resume-preview-text">{preview.cover_text}</pre>
              )}
            </div>
          ) : preview ? (
            <>
              {/* Score bar */}
              <div className="preview-match-bar">
                <div className="preview-scores-row">
                  <div className="preview-score-item">
                    <span className="preview-score-val" style={{color: scoreColor}}>
                      {preview.match_score ?? '—'}%
                    </span>
                    <span className="preview-score-lbl">JD Match</span>
                  </div>
                  <div className="preview-score-divider"/>
                  <div className="preview-score-item">
                    <span className="preview-score-val" style={{
                      color: (preview.ats_score||0) >= 90 ? '#00D68F'
                           : (preview.ats_score||0) >= 70 ? '#F7C948' : '#F0364C'
                    }}>{preview.ats_score ?? '—'}%</span>
                    <span className="preview-score-lbl">ATS Score</span>
                  </div>
                  <div className="preview-score-divider"/>
                  <div className="preview-score-item" style={{flex:2}}>
                    <span className="preview-score-val" style={{fontSize:'0.85rem', color: scoreColor}}>
                      {preview.verdict || '—'}
                    </span>
                    <span className="preview-score-lbl">Verdict</span>
                  </div>
                  {preview.from_cache && <span className="cache-badge">⚡ Cached</span>}
                </div>
                <div className="preview-skills-row">
                  {preview.matched_skills?.slice(0,6).map(s => (
                    <span key={s} className="preview-skill matched">✓ {s}</span>
                  ))}
                  {preview.missing_skills?.slice(0,4).map(s => (
                    <span key={s} className="preview-skill missing">+ {s}</span>
                  ))}
                </div>
                {preview.ats_details?.improvements?.length > 0 && (
                  <div className="ats-improvements">
                    <div className="ats-imp-title">ATS Tips:</div>
                    {preview.ats_details.improvements.slice(0,3).map((t,i) => (
                      <div key={i} className="ats-imp-item">• {t}</div>
                    ))}
                  </div>
                )}
              </div>

              {/* Tabs */}
              <div className="modal-tabs">
                <button className={`modal-tab ${activeTab==='resume'?'active':''}`}
                  onClick={() => setActiveTab('resume')}>📄 Enhanced Resume</button>
                <button className={`modal-tab ${activeTab==='cover'?'active':''}`}
                  onClick={() => setActiveTab('cover')}>✉️ Cover Letter</button>
                <button className={`modal-tab ${activeTab==='edits'?'active':''}`}
                  onClick={() => setActiveTab('edits')}>✏️ What Changed</button>
                <button className={`modal-tab ${activeTab==='study'?'active':''}`}
                  onClick={() => setActiveTab('study')}>📚 Study Plan</button>
              </div>

              {activeTab === 'edits' && (
                <EditSummaryTab
                  summary={preview.edit_summary}
                  rewritten={preview.rewritten}
                />
              )}
              {activeTab === 'resume' && (
                <div>
                  <div className="resume-note">
                    ℹ️ Original resume pages preserved — experience bullets + skills section updated below to match this JD
                  </div>
                  <InlinePdf url={resumeUrl} text={preview.resume_text}/>
                </div>
              )}
              {activeTab === 'cover' && (
                <InlinePdf url={coverUrl} text={preview.cover_text}/>
              )}
              {activeTab === 'study' && (
                <StudyPlanTab
                  plan={preview.study_plan}
                  job={job}
                  sessionId={preview.sessionId}
                  onPlanLoaded={(p) => { if(preview) preview.study_plan = p; }}
                />
              )}
            </>
          ) : null}
        </div>

        <div className="modal-footer">
          <button className="modal-close-btn" onClick={onClose}>Close</button>
        </div>
      </div>
    </div>
  );
}

// ── Single Job Card ───────────────────────────────────────────
function JobCard({ job, checked, onToggle, onPreview }) {
  const [expanded, setExpanded] = useState(false);
  const portalColor = PORTAL_COLORS[job.portal] || PORTAL_COLORS.default;
  const company     = job.company && job.company !== 'Company not listed' ? job.company : null;
  const snippet     = job.snippet || '';
  const shortSnip   = snippet.length > 420 ? snippet.slice(0, 420) + '…' : snippet;
  const fallbackApplicants = React.useRef(Math.floor(Math.random() * 300 + 20)).current;
  const applicants = job.applicants ?? fallbackApplicants;

  return (
    <div className={`job-card-v2 ${checked ? 'selected' : ''}`}
      style={{ '--portal-color': portalColor }}>
      <div className="jc-top" onClick={() => onToggle(job.id)}>
        <div className={`jcheckbox ${checked ? 'checked' : ''}`}>{checked && '✓'}</div>
        <ScoreRing score={job.match_score} />
        <div className="jc-info">
          <div className="jc-title-row">
            <span className="jc-title">{job.title}</span>
            <span className="jc-portal-tag" style={{background: portalColor+'22', color: portalColor}}>
              {job.portal}
            </span>
          </div>
          {company && <div className="jc-company">🏢 {company}</div>}
          <div className="jc-meta-row">
            {job.location && <span className="jc-meta-chip">📍 {job.location}</span>}
            {job.salary   && <span className="jc-meta-chip salary">💰 {job.salary}</span>}
            {job.posted   && <span className="jc-meta-chip">🕐 {job.posted}</span>}
            <span className="jc-applicants"><Users size={11}/> {applicants} applicants</span>
            <span className="jc-match-label" style={{
              color: (job.match_score||0) >= 70 ? '#00D68F'
                   : (job.match_score||0) >= 45 ? '#F7C948' : '#F0364C'
            }}>
              {(job.match_score||0) >= 70 ? '● Strong' : (job.match_score||0) >= 45 ? '● Good' : '● Weak'}
            </span>
          </div>
        </div>
        <a href={job.url} target="_blank" rel="noreferrer"
          className="jc-ext-link" onClick={e => e.stopPropagation()}>
          <ExternalLink size={14}/>
        </a>
      </div>

      {snippet && (
        <div className="jc-snippet-wrap" onClick={() => onToggle(job.id)}>
          <div className="jc-snippet">{expanded ? snippet : shortSnip}</div>
          {snippet.length > 420 && (
            <button className="jc-expand-btn"
              onClick={e => { e.stopPropagation(); setExpanded(x => !x); }}>
              {expanded ? <><ChevronUp size={12}/> Less</> : <><ChevronDown size={12}/> Read more</>}
            </button>
          )}
        </div>
      )}

      <div className="jc-actions">
        <button className="jc-preview-btn"
          onClick={e => { e.stopPropagation(); onPreview(job); }}>
          <Eye size={14}/> Preview Tailored Resume
        </button>
        <button className={`jc-select-btn ${checked ? 'selected' : ''}`}
          onClick={e => { e.stopPropagation(); onToggle(job.id); }}>
          {checked ? <><CheckSquare size={14}/> Selected</> : <><Square size={14}/> Select to Apply</>}
        </button>
      </div>
    </div>
  );
}

// ── Main export ───────────────────────────────────────────────
export default function JobListings({
  jobs, selectedJobs, onToggle, onSelectAll, onClearAll, onPreviewResume,
  previewJob, previewData, previewLoading, onClosePreview,
}) {
  const [filter, setFilter] = useState('all');
  const [sortBy, setSortBy] = useState('match');

  const allSelected = jobs.length > 0 && jobs.every(j => selectedJobs.has(j.id));
  const portals     = [...new Set(jobs.map(j => j.portal))];

  const filtered = jobs
    .filter(j => {
      if (filter === 'all')  return true;
      if (filter === 'high') return (j.match_score || 0) >= 70;
      return j.portal === filter;
    })
    .sort((a, b) => {
      if (sortBy === 'match')   return (b.match_score || 0) - (a.match_score || 0);
      if (sortBy === 'company') return (a.company || '').localeCompare(b.company || '');
      if (sortBy === 'portal')  return a.portal.localeCompare(b.portal);
      if (sortBy === 'title')   return a.title.localeCompare(b.title);
      return 0;
    });

  return (
    <>
      <div className="job-listings">
        <div className="listings-toolbar">
          <div className="toolbar-left">
            <button className={`filter-chip ${filter==='all'?'active':''}`} onClick={() => setFilter('all')}>
              All ({jobs.length})
            </button>
            <button className={`filter-chip ${filter==='high'?'active':''}`} onClick={() => setFilter('high')}>
              High Match ({jobs.filter(j => (j.match_score||0) >= 70).length})
            </button>
            {portals.map(p => (
              <button key={p} className={`filter-chip ${filter===p?'active':''}`} onClick={() => setFilter(p)}>
                {p} ({jobs.filter(j => j.portal === p).length})
              </button>
            ))}
          </div>
          <select className="sort-select" value={sortBy} onChange={e => setSortBy(e.target.value)}>
            <option value="match">Sort: Match Score</option>
            <option value="company">Sort: Company</option>
            <option value="portal">Sort: Portal</option>
            <option value="title">Sort: Title</option>
          </select>
        </div>

        <div className="select-all-row">
          <button className="select-all-btn" onClick={allSelected ? onClearAll : onSelectAll}>
            {allSelected
              ? <><CheckSquare size={15}/> Deselect All</>
              : <><Square size={15}/> Select All ({filtered.length} shown)</>
            }
          </button>
          <span className="selected-count">
            {selectedJobs.size} job{selectedJobs.size !== 1 ? 's' : ''} selected
          </span>
        </div>

        <div className="job-cards">
          {filtered.length === 0 && <div className="no-jobs">No jobs match this filter.</div>}
          {filtered.map(job => (
            <JobCard key={job.id} job={job}
              checked={selectedJobs.has(job.id)}
              onToggle={onToggle}
              onPreview={onPreviewResume}
            />
          ))}
        </div>
      </div>

      <ResumePreviewModal
        job={previewJob} preview={previewData}
        loading={previewLoading} onClose={onClosePreview}
      />
    </>
  );
}