import React, { useState, useEffect } from 'react';
import { Trash2, FileText, Eye, RefreshCw } from 'lucide-react';
import { listAppliedResumes, deleteAppliedResume, getGeneratedPdfUrl } from '../api/client';
import PdfViewer from './PdfViewer';

export default function AppliedResumesPanel({ onClose }) {
  const [folders,     setFolders]     = useState([]);
  const [loading,     setLoading]     = useState(true);
  const [deleting,    setDeleting]    = useState(null);
  const [previewUrl,  setPreviewUrl]  = useState(null);
  const [previewType, setPreviewType] = useState('resume');

  const load = async () => {
    setLoading(true);
    try {
      const data = await listAppliedResumes();
      setFolders(data.folders || []);
    } catch (e) {
      console.error(e);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { load(); }, []);

  const handleDelete = async (folderName) => {
    if (!window.confirm(`Delete ${folderName}?`)) return;
    setDeleting(folderName);
    try {
      await deleteAppliedResume(folderName);
      setFolders(f => f.filter(x => x.folder !== folderName));
    } catch (e) {
      alert('Delete failed: ' + e.message);
    } finally {
      setDeleting(null);
    }
  };

  const handlePreview = (folderName, type) => {
    setPreviewType(type);
    setPreviewUrl(getGeneratedPdfUrl(folderName, type));
  };

  // Parse folder name: 20250321_143022_Grab → "Grab · 21 Mar 2025 14:30"
  const parseFolder = (name) => {
    const m = name.match(/^(\d{4})(\d{2})(\d{2})_(\d{2})(\d{2})(\d{2})_(.+)$/);
    if (m) {
      const [,y,mo,d,h,min,,company] = m;
      return {
        company: company.replace(/_/g, ' '),
        date: `${d}/${mo}/${y} ${h}:${min}`,
      };
    }
    return { company: name, date: '' };
  };

  return (
    <>
      <div className="applied-panel-overlay" onClick={onClose}>
        <div className="applied-panel" onClick={e => e.stopPropagation()}>
          <div className="applied-panel-header">
            <div>
              <h2 className="applied-panel-title">📁 Generated Resumes</h2>
              <p className="applied-panel-sub">{folders.length} folder{folders.length !== 1 ? 's' : ''}</p>
            </div>
            <div style={{display:'flex',gap:8}}>
              <button className="pdf-ctrl-btn" onClick={load} title="Refresh">
                <RefreshCw size={16}/>
              </button>
              <button className="pdf-close-btn" onClick={onClose}>✕</button>
            </div>
          </div>

          <div className="applied-panel-body">
            {loading ? (
              <div className="pdf-loading"><div className="spinner"/>Loading...</div>
            ) : folders.length === 0 ? (
              <div className="applied-empty">No generated resumes yet. Preview a job to generate one.</div>
            ) : (
              folders.map(f => {
                const { company, date } = parseFolder(f.folder);
                return (
                  <div key={f.folder} className="applied-folder-item">
                    <div className="applied-folder-icon">
                      <FileText size={20}/>
                    </div>
                    <div className="applied-folder-info">
                      <div className="applied-folder-company">{company}</div>
                      <div className="applied-folder-date">{date}</div>
                      <div className="applied-folder-files">{f.files.length} files</div>
                    </div>
                    <div className="applied-folder-actions">
                      {f.resume && (
                        <button
                          className="applied-action-btn view"
                          onClick={() => handlePreview(f.folder, 'resume')}
                          title="Preview resume"
                        >
                          <Eye size={13}/> Resume
                        </button>
                      )}
                      {f.cover && (
                        <button
                          className="applied-action-btn view"
                          onClick={() => handlePreview(f.folder, 'cover')}
                          title="Preview cover letter"
                        >
                          <Eye size={13}/> Cover
                        </button>
                      )}
                      <button
                        className="applied-action-btn delete"
                        onClick={() => handleDelete(f.folder)}
                        disabled={deleting === f.folder}
                        title="Delete"
                      >
                        {deleting === f.folder
                          ? <><div className="spinner-sm"/>...</>
                          : <><Trash2 size={13}/> Delete</>
                        }
                      </button>
                    </div>
                  </div>
                );
              })
            )}
          </div>
        </div>
      </div>

      {previewUrl && (
        <PdfViewer
          url={previewUrl}
          title={previewType === 'resume' ? 'Tailored Resume' : 'Cover Letter'}
          onClose={() => setPreviewUrl(null)}
        />
      )}
    </>
  );
}