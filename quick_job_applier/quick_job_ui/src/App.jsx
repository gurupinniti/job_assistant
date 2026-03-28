import React, { useState } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import {
  Briefcase, ChevronRight, RotateCcw, AlertCircle,
  Search, FolderOpen, Eye,
} from 'lucide-react';

import { useJobApply }        from './hooks/useJobApply';
import { getResumePdfUrl }    from './api/client';
import StepIndicator          from './components/StepIndicator';
import ResumeDropzone         from './components/ResumeDropzone';
import JobTitleSelector       from './components/JobTitleSelector';
import CountrySearch          from './components/CountrySearch';
import { PortalConfirmCard }  from './components/PortalCard';
import PortalMultiSelect    from './components/PortalMultiSelect';
import JobListings            from './components/JobListings';
import PdfViewer              from './components/PdfViewer';
import AppliedResumesPanel    from './components/AppliedResumesPanel';
import './App.css';

const slide = {
  initial:  { opacity: 0, x: 40 },
  animate:  { opacity: 1, x: 0, transition: { duration: 0.35, ease: 'easeOut' } },
  exit:     { opacity: 0, x: -40, transition: { duration: 0.25 } },
};

export default function App() {
  const {
    step, jobTitles, countries, sessionId,
    resumeFile, setResumeFile,
    selectedTitles, toggleTitle,
    selectedCountry, setSelectedCountry,
    sessionData, confirmedPortals, togglePortal,
    searchStatus, jobListings,
    selectedJobs, toggleJob, selectAllJobs, clearAllJobs,
    applyStatus, jobStatuses, applyResult,
    loading, error,
    analyseResume, startSearch,
    confirmJobSelection, startApplying,
    downloadFile, reset, goToStep,
    step1Portals, toggleStep1Portal,
    titleSource, titleSeniority, titlesLoading, fetchResumeTitles,
    previewJob, previewData, previewLoading,
    openPreview, closePreview,
  } = useJobApply();

  const [showPdfPreview,   setShowPdfPreview]   = useState(false);
  const [showResumesPanel, setShowResumesPanel] = useState(false);

  const canAnalyse = resumeFile && selectedTitles.length > 0 && selectedCountry;
  const isDone     = applyStatus === 'completed' || applyStatus === 'error';
  const isSearching = searchStatus === 'searching';

  return (
    <div className="app">
      <div className="bg-mesh" />
      <div className="layout">

        {/* Header */}
        <header className="header">
          <div className="header-row">
            <div className="logo">
              <Briefcase size={22} strokeWidth={2.5}/>
              <span>QuickJob<span className="logo-dot">Applier</span></span>
            </div>
            <button className="header-action-btn" onClick={() => setShowResumesPanel(true)}>
              <FolderOpen size={16}/> My Resumes
            </button>
          </div>
          <p className="tagline">AI-powered job applications. Upload once, apply everywhere.</p>
        </header>

        <StepIndicator current={step} onGoToStep={goToStep}/>

        {error && (
          <div className="error-banner"><AlertCircle size={16}/> {error}</div>
        )}

        <AnimatePresence mode="wait">

          {/* ── STEP 1 ── */}
          {step === 1 && (
            <motion.div key="step1" {...slide} className="step-content">
              <section className="card">
                <h2 className="card-title"><span className="card-num">01</span> Upload Resume</h2>
                <ResumeDropzone file={resumeFile} onFile={setResumeFile}/>
                {resumeFile && (
                  <button
                    className="preview-pdf-btn"
                    onClick={() => setShowPdfPreview(true)}
                  >
                    <Eye size={14}/> Preview uploaded PDF
                  </button>
                )}
              </section>

              <section className="card">
                <h2 className="card-title">
                  <span className="card-num">02</span> Job Titles
                  {titlesLoading && <span className="titles-loading"><span className="spinner-sm"/> Analysing resume...</span>}
                  {!titlesLoading && titleSource !== 'static' && (
                    <span className={`title-source-badge ${titleSource}`}>
                      {titleSource === 'cache' ? '⚡ From cache' : titleSource === 'taxonomy' ? '📋 From skills' : '🤖 AI suggested'}
                      {titleSeniority && ` · ${titleSeniority}`}
                    </span>
                  )}
                  {selectedTitles.length > 0 &&
                    <span className="card-count">{selectedTitles.length} selected</span>}
                </h2>
                {!titlesLoading && titleSource !== 'static' && (
                  <p className="card-sub">
                    Suggested based on your resume. Select all that apply — you can add more below.
                  </p>
                )}
                <JobTitleSelector titles={jobTitles} selected={selectedTitles} onToggle={toggleTitle} primaryTitles={jobTitles.slice(0, 4)}/>
              </section>

              <section className="card">
                <h2 className="card-title"><span className="card-num">03</span> Target Country</h2>
                <CountrySearch countries={countries} selected={selectedCountry} onSelect={setSelectedCountry}/>
              </section>

              <section className="card">
                <h2 className="card-title">
                  <span className="card-num">04</span> Select Portals
                  <span className="card-count">{step1Portals.length} selected</span>
                </h2>
                <PortalMultiSelect selected={step1Portals} onToggle={toggleStep1Portal}/>
              </section>

              <button
                className={`btn-primary ${loading ? 'loading' : ''}`}
                disabled={!canAnalyse || loading || step1Portals.length === 0}
                onClick={analyseResume}
              >
                {loading
                  ? <><span className="spinner"/> Analysing...</>
                  : <>Analyse & Find Portals <ChevronRight size={18}/></>
                }
              </button>
            </motion.div>
          )}

          {/* ── STEP 2 ── */}
          {step === 2 && sessionData && (
            <motion.div key="step2" {...slide} className="step-content">

              <section className="card candidate-card">
                <h2 className="card-title"><span className="card-num">👤</span> {sessionData.candidate}</h2>
                <div className="stat-row">
                  <div className="stat"><div className="stat-val">{sessionData.experience ?? '—'}</div><div className="stat-lbl">Years Exp</div></div>
                  <div className="stat"><div className="stat-val">{sessionData.skills_found?.length ?? 0}</div><div className="stat-lbl">Skills</div></div>
                  <div className="stat"><div className="stat-val">{sessionData.portals?.length ?? 0}</div><div className="stat-lbl">Portals</div></div>
                  <div className="stat"><div className="stat-val">{confirmedPortals.length}</div><div className="stat-lbl">Selected</div></div>
                </div>
                <div className="skill-tags">
                  {(sessionData.skills_found || []).map(s => <span key={s} className="skill-tag">{s}</span>)}
                </div>
              </section>

              <section className="card">
                <h2 className="card-title">
                  <span className="card-num">🌐</span> Confirm Portals
                  <span className="card-count">{confirmedPortals.length} selected</span>
                </h2>
                <p className="card-sub">Portals are ordered by ease of apply — Tier 1 requires no login.</p>
                <div className="portal-tier-legend">
                  <span className="tier-badge t1">Tier 1 — No login</span>
                  <span className="tier-badge t2">Tier 2 — Optional login</span>
                  <span className="tier-badge t3">Tier 3 — Login required</span>
                </div>
                <div className="portal-list">
                  {(sessionData.portals || [])
                    .filter(p => confirmedPortals.includes(p.name))  // only show user-selected
                    .map(p => (
                      <PortalConfirmCard
                        key={p.name}
                        portal={p}
                        checked={confirmedPortals.includes(p.name)}
                        onToggle={togglePortal}
                      />
                    ))
                  }
                  <p className="portal-step2-hint">
                    These are the portals you selected in Step 1.
                    Uncheck any you want to skip for this search.
                  </p>
                </div>
              </section>

              <button
                className={`btn-primary ${loading || isSearching ? 'loading' : ''}`}
                disabled={!confirmedPortals.length || loading || isSearching}
                onClick={startSearch}
              >
                {isSearching
                  ? <><span className="spinner"/> Searching Jobs...</>
                  : <><Search size={18}/> Search Jobs on {confirmedPortals.length} Portal{confirmedPortals.length !== 1 ? 's' : ''}</>
                }
              </button>
              {isSearching && (
                <div className="search-progress">
                  <div className="spinner-sm"/>
                  <span>Searching Adzuna, RemoteOK, Arbeitnow, Google Jobs... may take 10–20 seconds</span>
                </div>
              )}
            </motion.div>
          )}

          {/* ── STEP 3 ── */}
          {step === 3 && (
            <motion.div key="step3" {...slide} className="step-content">
              <section className="card">
                <h2 className="card-title">
                  <span className="card-num">🔍</span> Job Listings
                  <span className="card-count">{jobListings.length} found</span>
                </h2>
                <p className="card-sub">
                  Select jobs you want to apply to. Click <strong>Preview Tailored Resume</strong> to see your enhanced resume before applying.
                </p>
                {jobListings.length === 0 ? (
                  <div className="empty-state">No jobs found. Try different titles, portals, or add a SERPER_API_KEY to config.py.</div>
                ) : (
                  <JobListings
                    jobs={jobListings}
                    selectedJobs={selectedJobs}
                    onToggle={toggleJob}
                    onSelectAll={selectAllJobs}
                    onClearAll={clearAllJobs}
                    onPreviewResume={openPreview}
                    previewJob={previewJob}
                    previewData={previewData}
                    previewLoading={previewLoading}
                    onClosePreview={closePreview}
                  />
                )}
              </section>

              <button
                className={`btn-primary ${loading ? 'loading' : ''}`}
                disabled={selectedJobs.size === 0 || loading}
                onClick={confirmJobSelection}
              >
                {loading
                  ? <><span className="spinner"/> Saving...</>
                  : <>Apply to {selectedJobs.size} Job{selectedJobs.size !== 1 ? 's' : ''} →</>
                }
              </button>
            </motion.div>
          )}

          {/* ── STEP 4 ── */}
          {step === 4 && (
            <motion.div key="step4" {...slide} className="step-content">
              <section className="card">
                <h2 className="card-title">
                  <span className="card-num">🚀</span> Apply & Status
                  {applyStatus === 'applying' && <span className="live-badge">● LIVE</span>}
                  {isDone && <span className="done-badge">✓ Done</span>}
                </h2>

                {isDone && applyResult?.summary && (
                  <div className="stat-row" style={{ marginBottom: 20 }}>
                    <div className="stat"><div className="stat-val" style={{color:'var(--green)'}}>{applyResult.summary.success ?? 0}</div><div className="stat-lbl">Applied</div></div>
                    <div className="stat"><div className="stat-val" style={{color:'var(--yellow)'}}>{applyResult.summary.partial ?? 0}</div><div className="stat-lbl">Partial</div></div>
                    <div className="stat"><div className="stat-val" style={{color:'var(--text-2)'}}>{applyResult.summary.skipped ?? 0}</div><div className="stat-lbl">Skipped</div></div>
                    <div className="stat"><div className="stat-val" style={{color:'var(--red)'}}>{applyResult.summary.error ?? 0}</div><div className="stat-lbl">Error</div></div>
                  </div>
                )}

                {applyStatus === null && previewData?.requires_confirmation && (
                  <div className="apply-fallback-warning">
                    <span>⚠</span>
                    <div>
                      <strong>AI tailoring failed for one or more jobs.</strong>
                      Your original resume will be used as-is for those jobs.
                      Please confirm you are happy to proceed.
                    </div>
                  </div>
                )}
                {applyStatus === null && (
                  <div className="apply-prompt">
                    Ready to apply. A browser window will open for each job — the agent will fill forms automatically.
                    <br/><br/>
                    <strong>Tier 1 portals</strong> (Adzuna, RemoteOK etc.) apply automatically.
                    <br/>
                    <strong>Tier 2/3 portals</strong> open the browser for you to assist if login is needed.
                  </div>
                )}

                <div className="status-list">
                  {(applyResult?.jobs || Object.entries(jobStatuses).map(([id, status]) => ({ id, status }))).map(job => (
                    <div key={job.id || job.title} className="portal-status-card"
                      style={{ '--status-color': statusColor(job.status || jobStatuses[job.id]) }}>
                      <div className={`status-dot ${['pending','applying'].includes(job.status || jobStatuses[job.id]) ? 'pulse' : ''}`}
                        style={{ background: statusColor(job.status || jobStatuses[job.id]) }}/>
                      <div className="status-body">
                        <div className="status-header">
                          <span className="status-portal-name">{job.title || job.id}</span>
                          {job.company && <span className="match-score">{job.company}</span>}
                          {job.match_score && <span className="match-score">Match: {job.match_score}%</span>}
                          {job.ats_score  && <span className="match-score">ATS: {job.ats_score}%</span>}
                        </div>
                        <div className="status-message" style={{ color: statusColor(job.status || jobStatuses[job.id]) }}>
                          {job.message || job.reason || job.status || 'pending'}
                        </div>
                      </div>
                      <div className="status-badge"
                        style={{ background: statusColor(job.status || jobStatuses[job.id]) + '22',
                                 color: statusColor(job.status || jobStatuses[job.id]) }}>
                        {job.status || jobStatuses[job.id] || 'pending'}
                      </div>
                      {job.resume_path && (
                        <div className="job-dl-btns">
                          <button className="dl-btn" onClick={() => downloadFile(job.id, 'resume')} title="Download Resume">📄</button>
                          <button className="dl-btn" onClick={() => downloadFile(job.id, 'cover_letter')} title="Download Cover">✉️</button>
                        </div>
                      )}
                    </div>
                  ))}
                </div>

                {applyStatus === null && (
                  <button className="btn-primary" onClick={startApplying} disabled={loading}>
                    {loading ? <><span className="spinner"/> Starting...</> : <>🚀 Start Applying</>}
                  </button>
                )}
                {applyStatus === 'applying' && (
                  <div className="polling-note"><span className="spinner-sm"/> Checking every 3 seconds...</div>
                )}
              </section>

              <button className="btn-ghost" onClick={reset}>
                <RotateCcw size={16}/> Start New Application
              </button>
            </motion.div>
          )}

        </AnimatePresence>
      </div>

      {/* ── PDF preview of uploaded resume ── */}
      {showPdfPreview && resumeFile && (
        <PdfViewer
          url={URL.createObjectURL(resumeFile)}
          title={resumeFile.name}
          onClose={() => setShowPdfPreview(false)}
        />
      )}

      {/* ── Applied resumes management panel ── */}
      {showResumesPanel && (
        <AppliedResumesPanel onClose={() => setShowResumesPanel(false)}/>
      )}
    </div>
  );
}

function statusColor(status) {
  return {
    success:         '#00D68F',
    partial:         '#F7C948',
    manual_required: '#F7C948',
    restricted:      '#FF6090',
    error:           '#F0364C',
    failure:         '#F0364C',
    skipped:         '#6B6B8A',
    pending:         '#6B6B8A',
    applying:        '#5B4FE9',
  }[status] || '#6B6B8A';
}