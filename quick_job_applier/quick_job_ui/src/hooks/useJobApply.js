import { useState, useEffect, useRef, useCallback } from 'react';
import {
  getJobTitles, getCountries,
  uploadResume, searchJobs, getSearchStatus,
  selectJobs, applyJobs, getApplyStatus,
  getDownloadUrl, previewResume, getResumeTitles,
} from '../api/client';

// Fallback data — shown immediately without backend
const FALLBACK_TITLES = [
  'Software Engineer', 'Senior Software Engineer', 'Full Stack Developer',
  'Frontend Developer', 'Backend Developer', 'DevOps Engineer',
  'Data Engineer', 'Data Scientist', 'Machine Learning Engineer',
  'AI Engineer', 'Cloud Architect', 'Site Reliability Engineer',
  'Mobile Developer', 'iOS Developer', 'Android Developer',
  'Product Manager', 'Engineering Manager', 'CTO',
  'Financial Analyst', 'Investment Banker', 'Risk Analyst',
  'Accountant', 'CFO', 'Auditor',
  'Digital Marketing Manager', 'SEO Specialist', 'Content Strategist',
  'Brand Manager', 'Social Media Manager',
  'HR Manager', 'Talent Acquisition', 'People Operations',
  'Project Manager', 'Business Analyst', 'Operations Manager',
  'Sales Manager', 'Customer Success Manager', 'UX Designer',
  'Nurse', 'Doctor', 'Pharmacist', 'Healthcare Administrator',
];

const FALLBACK_COUNTRIES = {
  Singapore: [], India: [], Australia: [], Usa: [],
  Uk: [], Malaysia: [], Uae: [], Germany: [], Canada: [],
};

export function useJobApply() {
  // ── Static data ──────────────────────────────────────────
  const [jobTitles,       setJobTitles]       = useState(FALLBACK_TITLES);
  const [countries,       setCountries]       = useState(FALLBACK_COUNTRIES);

  // ── Portal selection (Step 1) ───────────────────────────────
  const [step1Portals,   setStep1Portals]   = useState(['Adzuna','Indeed','JobStreet','LinkedIn']);
  const toggleStep1Portal = useCallback((name) =>
    setStep1Portals(prev =>
      prev.includes(name) ? prev.filter(p => p !== name) : [...prev, name]
    ), []);

  // ── Dynamic title loading ───────────────────────────────────
  const [titleSource,    setTitleSource]    = useState('static');
  const [titleSeniority, setTitleSeniority] = useState('');
  const [titlesLoading,  setTitlesLoading]  = useState(false);

  // ── Step 1: Resume + preferences ─────────────────────────
  const [step,            setStep]            = useState(1);
  const [resumeFile,      setResumeFile]      = useState(null);
  const [selectedTitles,  setSelectedTitles]  = useState([]);
  const [selectedCountry, setSelectedCountry] = useState(null);

  // ── Step 2: Portal confirmation + job search ─────────────
  const [sessionData,     setSessionData]     = useState(null);
  const [confirmedPortals,setConfirmedPortals]= useState([]);
  const [searchStatus,    setSearchStatus]    = useState(null); // 'searching' | 'done'
  const [jobListings,     setJobListings]     = useState([]);

  // ── Step 3: Job selection ─────────────────────────────────
  const [selectedJobs,    setSelectedJobs]    = useState(new Set());

  // ── Step 3b: Resume preview ───────────────────────────────
  const [previewJob,      setPreviewJob]      = useState(null);
  const [previewData,     setPreviewData]     = useState(null);
  const [previewLoading,  setPreviewLoading]  = useState(false);

  // ── Step 4: Apply + status ───────────────────────────────
  const [applyStatus,     setApplyStatus]     = useState(null);
  const [jobStatuses,     setJobStatuses]     = useState({});
  const [applyResult,     setApplyResult]     = useState(null);

  // ── Shared ───────────────────────────────────────────────
  const [loading,         setLoading]         = useState(false);
  const [error,           setError]           = useState(null);

  const searchPollRef = useRef(null);
  const applyPollRef  = useRef(null);
  const sessionId     = useRef(null);

  // Load static data on mount
  useEffect(() => {
    getJobTitles()
      .then(t => { if (t?.length) setJobTitles(t); })
      .catch(() => {});
    getCountries()
      .then(d => { if (Object.keys(d || {}).length) setCountries(d); })
      .catch(() => {});
  }, []);

  useEffect(() => () => {
    clearInterval(searchPollRef.current);
    clearInterval(applyPollRef.current);
  }, []);

  // Stable key = filename + size. Same file won't re-trigger title fetch.
  const lastTitleKeyRef = useRef(null);

  // Auto-fetch titles when a NEW file is uploaded (keyed by name+size, not object ref)
  useEffect(() => {
    if (!resumeFile) return;
    const fileKey = `${resumeFile.name}-${resumeFile.size}`;
    if (fileKey === lastTitleKeyRef.current) return;   // same file — skip
    lastTitleKeyRef.current = fileKey;
    fetchResumeTitles(resumeFile, selectedCountry);
  }, [resumeFile]); // eslint-disable-line

  // ── Step 1 actions ───────────────────────────────────────

  // Fetch dynamic job titles when resume is uploaded
  const fetchResumeTitles = useCallback(async (file, country) => {
    if (!file) return;
    setTitlesLoading(true);
    try {
      const countryVal = country?.value || country || 'singapore';
      const data = await getResumeTitles(file, countryVal);
      if (data.titles?.length) {
        setJobTitles(data.titles);
        // Auto-select the primary suggested titles
        if (data.primary?.length) {
          setSelectedTitles(data.primary.slice(0, 3));
        }
        setTitleSource(data.source || 'llm');
        setTitleSeniority(data.seniority || '');
        console.log(`[Titles] Loaded ${data.titles.length} from ${data.source}`);
      }
    } catch (e) {
      console.warn('[Titles] Failed to load dynamic titles:', e.message);
    } finally {
      setTitlesLoading(false);
    }
  }, []);

  const toggleTitle = useCallback((title) => {
    setSelectedTitles(prev =>
      prev.includes(title) ? prev.filter(t => t !== title) : [...prev, title]
    );
  }, []);

  const analyseResume = useCallback(async () => {
    if (!resumeFile || !selectedTitles.length || !selectedCountry) return;
    setLoading(true); setError(null);
    try {
      const fd = new FormData();
      fd.append('resume',           resumeFile);
      fd.append('job_titles',       selectedTitles.join(','));
      fd.append('country',          selectedCountry.value);
      fd.append('selected_portals', step1Portals.join(','));   // tell backend which portals user chose
      const data = await uploadResume(fd);
      sessionId.current = data.session_id;
      setSessionData(data);
      // Set confirmedPortals directly from what user selected in Step 1.
      // No backend intersection — step1Portals is the source of truth.
      setConfirmedPortals([...step1Portals]);
      setStep(2);
    } catch (e) {
      setError(e.response?.data?.detail || e.message);
    } finally {
      setLoading(false);
    }
  }, [resumeFile, selectedTitles, selectedCountry, step1Portals]);

  // ── Step 2 actions ───────────────────────────────────────

  const togglePortal = useCallback((name) => {
    setConfirmedPortals(prev =>
      prev.includes(name) ? prev.filter(p => p !== name) : [...prev, name]
    );
  }, []);

  const startSearch = useCallback(async () => {
    if (!confirmedPortals.length) return;
    setLoading(true); setError(null); setSearchStatus('searching'); setJobListings([]);
    try {
      // Pass the user's confirmed title selection so the backend searches exactly what the user chose
      await searchJobs(sessionId.current, confirmedPortals, selectedTitles);
      // Poll for results
      searchPollRef.current = setInterval(async () => {
        try {
          const s = await getSearchStatus(sessionId.current);
          if (s.status === 'awaiting_job_selection') {
            clearInterval(searchPollRef.current);
            setJobListings(s.jobs || []);
            setSearchStatus('done');
            setStep(3);
          } else if (s.status === 'error') {
            clearInterval(searchPollRef.current);
            setSearchStatus('error');
            setError(s.error);
          }
        } catch {}
      }, 2000);
    } catch (e) {
      setError(e.response?.data?.detail || e.message);
      setSearchStatus('error');
    } finally {
      setLoading(false);
    }
  }, [confirmedPortals, selectedTitles]);

  // ── Step 3 actions ───────────────────────────────────────

  const toggleJob = useCallback((jobId) => {
    setSelectedJobs(prev => {
      const next = new Set(prev);
      next.has(jobId) ? next.delete(jobId) : next.add(jobId);
      return next;
    });
  }, []);

  const selectAllJobs = useCallback(() => {
    setSelectedJobs(new Set(jobListings.map(j => j.id)));
  }, [jobListings]);

  const clearAllJobs = useCallback(() => {
    setSelectedJobs(new Set());
  }, []);

  const confirmJobSelection = useCallback(async () => {
    const jobs = jobListings.filter(j => selectedJobs.has(j.id));
    if (!jobs.length) return;
    setLoading(true); setError(null);
    try {
      await selectJobs(sessionId.current, jobs);
      setStep(4);
    } catch (e) {
      setError(e.response?.data?.detail || e.message);
    } finally {
      setLoading(false);
    }
  }, [jobListings, selectedJobs]);

  // ── Step 4 actions ───────────────────────────────────────

  const startApplying = useCallback(async () => {
    setLoading(true); setError(null); setApplyStatus('applying');
    try {
      await applyJobs(sessionId.current);
      applyPollRef.current = setInterval(async () => {
        try {
          const s = await getApplyStatus(sessionId.current);
          setJobStatuses(s.job_statuses || {});
          if (s.status === 'completed' || s.status === 'error') {
            clearInterval(applyPollRef.current);
            setApplyStatus(s.status);
            setApplyResult(s);
          }
        } catch {}
      }, 3000);
    } catch (e) {
      setError(e.response?.data?.detail || e.message);
      setApplyStatus('error');
    } finally {
      setLoading(false);
    }
  }, []);

  const openPreview = useCallback(async (job) => {
    setPreviewJob(job);
    setPreviewData(null);
    setPreviewLoading(true);

    const sid = sessionId.current;
    if (!sid) {
      setPreviewData({ error: "Session expired — please go back to Step 1 and re-upload your resume." });
      setPreviewLoading(false);
      return;
    }

    try {
      const data = await previewResume(sid, job);
      // Attach sessionId and jobId so the modal can build the PDF URL
      data.sessionId = sid;
      data.jobId     = job.id || job.title;
      // If LLM failed, mark the job so the apply step can warn user
      if (data.requires_confirmation) {
        data._requiresConfirmation = true;
      }
      setPreviewData(data);
    } catch (e) {
      const msg = e.response?.data?.detail || e.message;
      if (e.response?.status === 404) {
        setPreviewData({ error: "Session not found on server (session_id: " + sid + "). The backend may have restarted — please go back to Step 1 and re-upload your resume." });
      } else {
        setPreviewData({ error: msg });
      }
    } finally {
      setPreviewLoading(false);
    }
  }, []);

  const closePreview = useCallback(() => {
    setPreviewJob(null);
    setPreviewData(null);
  }, []);

  const downloadFile = useCallback((jobId, type) => {
    window.open(getDownloadUrl(sessionId.current, jobId, type));
  }, []);

  const goToStep = useCallback((n) => {
    // Only allow going back — never skip forward
    if (n < step) setStep(n);
  }, [step]);

  const reset = useCallback(() => {
    clearInterval(searchPollRef.current);
    clearInterval(applyPollRef.current);
    sessionId.current      = null;
    lastTitleKeyRef.current = null;   // allow title re-fetch on next upload
    setStep(1); setResumeFile(null); setSelectedTitles([]);
    setJobTitles(FALLBACK_TITLES);    // restore static list
    setTitleSource('static'); setTitleSeniority('');
    setStep1Portals(['Adzuna','Indeed','JobStreet','LinkedIn']); // reset portal selection
    setSelectedCountry(null); setSessionData(null);
    setConfirmedPortals([]); setSearchStatus(null); setJobListings([]);
    setSelectedJobs(new Set()); setApplyStatus(null);
    setJobStatuses({}); setApplyResult(null); setError(null);
    setPreviewJob(null); setPreviewData(null);
  }, []);

  return {
    // data
    step, jobTitles, countries,
    // step 1
    resumeFile, setResumeFile,
    selectedTitles, toggleTitle,
    selectedCountry, setSelectedCountry,
    // step 2
    sessionData, confirmedPortals, togglePortal,
    searchStatus, jobListings,
    // step 3
    selectedJobs, toggleJob, selectAllJobs, clearAllJobs,
    // step 4
    applyStatus, jobStatuses, applyResult,
    // shared
    loading, error,
    // actions
    sessionId: sessionId.current,
    analyseResume, startSearch,
    confirmJobSelection, startApplying,
    downloadFile, reset, goToStep,
    step1Portals, toggleStep1Portal,
    titleSource, titleSeniority, titlesLoading, fetchResumeTitles,
    previewJob, previewData, previewLoading,
    openPreview, closePreview,
  };
}