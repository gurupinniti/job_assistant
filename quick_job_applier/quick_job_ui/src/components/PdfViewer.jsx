import React, { useState } from 'react';
import { Document, Page, pdfjs } from 'react-pdf';
import 'react-pdf/dist/esm/Page/AnnotationLayer.css';
import 'react-pdf/dist/esm/Page/TextLayer.css';
import { ChevronLeft, ChevronRight, X, ZoomIn, ZoomOut } from 'lucide-react';

// Use CDN worker to avoid webpack config issues
pdfjs.GlobalWorkerOptions.workerSrc = `https://cdnjs.cloudflare.com/ajax/libs/pdf.js/${pdfjs.version}/pdf.worker.min.js`;

export default function PdfViewer({ url, title = "PDF Preview", onClose }) {
  const [numPages,    setNumPages]    = useState(null);
  const [currentPage, setCurrentPage] = useState(1);
  const [scale,       setScale]       = useState(1.2);
  const [error,       setError]       = useState(null);

  if (!url) return null;

  return (
    <div className="pdf-modal-overlay" onClick={onClose}>
      <div className="pdf-modal" onClick={e => e.stopPropagation()}>

        {/* Header */}
        <div className="pdf-modal-header">
          <span className="pdf-modal-title">{title}</span>
          <div className="pdf-controls">
            <button className="pdf-ctrl-btn" onClick={() => setScale(s => Math.max(0.6, s - 0.2))} title="Zoom out">
              <ZoomOut size={16}/>
            </button>
            <span className="pdf-scale-label">{Math.round(scale * 100)}%</span>
            <button className="pdf-ctrl-btn" onClick={() => setScale(s => Math.min(2.5, s + 0.2))} title="Zoom in">
              <ZoomIn size={16}/>
            </button>
            <div className="pdf-page-nav">
              <button className="pdf-ctrl-btn"
                disabled={currentPage <= 1}
                onClick={() => setCurrentPage(p => p - 1)}>
                <ChevronLeft size={16}/>
              </button>
              <span className="pdf-page-label">
                {currentPage} / {numPages || '?'}
              </span>
              <button className="pdf-ctrl-btn"
                disabled={currentPage >= (numPages || 1)}
                onClick={() => setCurrentPage(p => p + 1)}>
                <ChevronRight size={16}/>
              </button>
            </div>
            <button className="pdf-close-btn" onClick={onClose}><X size={18}/></button>
          </div>
        </div>

        {/* PDF content */}
        <div className="pdf-modal-body">
          {error ? (
            <div className="pdf-error">
              <p>Could not load PDF preview.</p>
              <a href={url} target="_blank" rel="noreferrer" className="pdf-open-link">
                Open in new tab ↗
              </a>
            </div>
          ) : (
            <Document
              file={url}
              onLoadSuccess={({ numPages }) => setNumPages(numPages)}
              onLoadError={(err) => { console.error(err); setError(true); }}
              loading={<div className="pdf-loading"><div className="spinner"/>Loading PDF...</div>}
            >
              <Page
                pageNumber={currentPage}
                scale={scale}
                renderTextLayer={true}
                renderAnnotationLayer={true}
              />
            </Document>
          )}
        </div>
      </div>
    </div>
  );
}