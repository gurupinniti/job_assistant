import React, { useCallback } from 'react';
import { useDropzone } from 'react-dropzone';
import { UploadCloud, FileText, X } from 'lucide-react';

export default function ResumeDropzone({ file, onFile }) {
  const onDrop = useCallback(accepted => {
    if (accepted[0]) onFile(accepted[0]);
  }, [onFile]);

  const { getRootProps, getInputProps, isDragActive } = useDropzone({
    onDrop,
    accept: { 'application/pdf': ['.pdf'] },
    maxFiles: 1,
    maxSize: 10 * 1024 * 1024,
  });

  return (
    <div {...getRootProps()} className={`dropzone ${isDragActive ? 'drag-active' : ''} ${file ? 'has-file' : ''}`}>
      <input {...getInputProps()} />
      {file ? (
        <div className="file-preview">
          <FileText size={32} className="file-icon" />
          <div className="file-details">
            <span className="file-name">{file.name}</span>
            <span className="file-size">{(file.size / 1024).toFixed(0)} KB</span>
          </div>
          <button className="file-remove" onClick={e => { e.stopPropagation(); onFile(null); }}>
            <X size={16} />
          </button>
        </div>
      ) : (
        <div className="dropzone-empty">
          <UploadCloud size={40} className="upload-icon" />
          <p className="dropzone-title">{isDragActive ? 'Drop it here!' : 'Drag & drop your resume'}</p>
          <p className="dropzone-sub">PDF only · Max 10MB · <span className="browse-link">Browse files</span></p>
        </div>
      )}
    </div>
  );
}