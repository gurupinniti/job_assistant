import axios from 'axios';

const BASE = process.env.REACT_APP_API_URL || 'http://localhost:8001';
const api  = axios.create({ baseURL: BASE });

export const getJobTitles   = () => api.get('/job-titles').then(r => r.data.job_titles);

export const getStudyPlan = (sessionId, job) =>
  api.post('/study-plan', { session_id: sessionId, job }).then(r => r.data);

export const getResumeTitles = (resumeFile, country = 'singapore') => {
  const fd = new FormData();
  fd.append('resume', resumeFile);
  fd.append('country', country);
  return api.post('/resume-job-titles', fd, {
    headers: { 'Content-Type': 'multipart/form-data' },
  }).then(r => r.data);
};
export const getCountries   = () => api.get('/countries').then(r => r.data);

export const uploadResume   = (formData) =>
  api.post('/upload-resume', formData, {
    headers: { 'Content-Type': 'multipart/form-data' },
  }).then(r => r.data);

export const searchJobs     = (sessionId, confirmedPortals, confirmedJobTitles = []) =>
  api.post('/search-jobs', {
    session_id:            sessionId,
    confirmed_portals:     confirmedPortals,
    confirmed_job_titles:  confirmedJobTitles,   // user final title selection
  }).then(r => r.data);

export const getSearchStatus = (sessionId) =>
  api.get(`/search-status/${sessionId}`).then(r => r.data);

export const selectJobs     = (sessionId, selectedJobs) =>
  api.post('/select-jobs', {
    session_id:    sessionId,
    selected_jobs: selectedJobs,
  }).then(r => r.data);

export const applyJobs      = (sessionId) =>
  api.post('/apply', { session_id: sessionId }).then(r => r.data);

export const getApplyStatus = (sessionId) =>
  api.get(`/apply-status/${sessionId}`).then(r => r.data);

export const previewResume  = (sessionId, job) =>
  api.post('/preview-resume', { session_id: sessionId, job }).then(r => r.data);

export const getTailoredPdfUrl   = (sessionId, jobId, doc = "resume") =>
  `${BASE}/preview-resume-pdf/${sessionId}/${encodeURIComponent(jobId)}?doc=${doc}`;

export const getResumePdfUrl     = (sessionId) =>
  `${BASE}/resume-pdf/${sessionId}`;

export const listAppliedResumes  = () =>
  api.get('/applied-resumes').then(r => r.data);

export const deleteAppliedResume = (folderName) =>
  api.delete(`/applied-resumes/${folderName}`).then(r => r.data);

export const getGeneratedPdfUrl  = (folderName, type = 'resume') =>
  `${BASE}/applied-resumes/${folderName}/pdf?type=${type}`;

export const getDownloadUrl = (sessionId, jobId, fileType) =>
  `${BASE}/download/${sessionId}/${jobId}/${fileType}`;