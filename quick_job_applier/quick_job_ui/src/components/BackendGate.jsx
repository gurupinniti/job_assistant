import React, { useState, useEffect, useCallback } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { Briefcase, RefreshCw, Wifi, WifiOff, CheckCircle } from 'lucide-react';

const API = process.env.REACT_APP_API_URL || 'http://localhost:8001';
const POLL_INTERVAL = 3000;   // check every 3s when offline
const RETRY_FAST    = 1000;   // check every 1s just after reconnect

export default function BackendGate({ children }) {
  const [status, setStatus]   = useState('checking');  // 'checking' | 'offline' | 'online'
  const [attempt, setAttempt] = useState(0);
  const [elapsed, setElapsed] = useState(0);

  const check = useCallback(async () => {
    try {
      const res = await fetch(`${API}/`, { signal: AbortSignal.timeout(4000) });
      if (res.ok) {
        setStatus('online');
        return true;
      }
    } catch {}
    setStatus(prev => prev === 'checking' ? 'offline' : 'offline');
    return false;
  }, []);

  // Initial check + polling while offline
  useEffect(() => {
    let timer;
    let elapsed = 0;
    let elapsedTimer;

    const poll = async () => {
      setAttempt(a => a + 1);
      const ok = await check();
      if (!ok) {
        timer = setTimeout(poll, POLL_INTERVAL);
      }
    };

    poll();

    // Elapsed seconds counter shown on the screen
    elapsedTimer = setInterval(() => {
      elapsed += 1;
      setElapsed(elapsed);
    }, 1000);

    return () => {
      clearTimeout(timer);
      clearInterval(elapsedTimer);
    };
  }, [check]);

  const retry = async () => {
    setStatus('checking');
    setAttempt(0);
    setElapsed(0);
    await check();
  };

  // Already online — render children with fade-in
  if (status === 'online') {
    return (
      <AnimatePresence mode="wait">
        <motion.div
          key="app"
          initial={{ opacity: 0, y: 10 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.5, ease: 'easeOut' }}
        >
          {children}
        </motion.div>
      </AnimatePresence>
    );
  }

  // Gate screen
  return (
    <div className="gate-screen">
      <div className="bg-mesh" />

      <motion.div
        className="gate-card"
        initial={{ opacity: 0, scale: 0.95 }}
        animate={{ opacity: 1, scale: 1 }}
        transition={{ duration: 0.4 }}
      >
        {/* Logo */}
        <div className="gate-logo">
          <Briefcase size={28} strokeWidth={2} />
          <span>QuickJob<span className="logo-dot">Applier</span></span>
        </div>

        {/* Status icon */}
        <div className="gate-icon-wrap">
          {status === 'checking' ? (
            <motion.div
              animate={{ rotate: 360 }}
              transition={{ repeat: Infinity, duration: 1, ease: 'linear' }}
            >
              <RefreshCw size={40} className="gate-icon-spin" />
            </motion.div>
          ) : (
            <motion.div
              animate={{ scale: [1, 1.1, 1] }}
              transition={{ repeat: Infinity, duration: 2 }}
            >
              <WifiOff size={40} className="gate-icon-offline" />
            </motion.div>
          )}
        </div>

        {/* Message */}
        {status === 'checking' && (
          <>
            <h2 className="gate-title">Connecting to backend...</h2>
            <p className="gate-sub">
              Waiting for the API server at<br />
              <code className="gate-url">{API}</code>
            </p>
            {elapsed >= 3 && elapsed < 20 && (
              <div className="gate-startup-hint">
                <span className="gate-hint-icon">💡</span>
                Backend initialisation typically takes <strong>10–15 seconds</strong> on first boot
                while the LLM chain and caches are loading.
              </div>
            )}
          </>
        )}

        {status === 'offline' && (
          <>
            <h2 className="gate-title">Backend not reachable</h2>
            <p className="gate-sub">
              Cannot connect to<br />
              <code className="gate-url">{API}</code>
            </p>
            <div className="gate-startup-hint">
              <span className="gate-hint-icon">💡</span>
              If you just started the server, wait <strong>10–15 seconds</strong> — the LLM
              chain and ChromaDB caches take a moment to initialise on first boot.
            </div>

            <div className="gate-instructions">
              <p>Start the backend in a terminal:</p>
              <pre className="gate-code">
                cd ~/quick_job_backend{'\n'}
                uvicorn job_apply_api:app --reload --port 8001
              </pre>
            </div>
          </>
        )}

        {/* Stats */}
        <div className="gate-stats">
          <div className="gate-stat">
            <span className="gate-stat-val">{attempt}</span>
            <span className="gate-stat-lbl">attempts</span>
          </div>
          <div className="gate-stat-divider" />
          <div className="gate-stat">
            <span className="gate-stat-val">{elapsed}s</span>
            <span className="gate-stat-lbl">elapsed</span>
          </div>
          <div className="gate-stat-divider" />
          <div className="gate-stat">
            <span className="gate-stat-val">{POLL_INTERVAL / 1000}s</span>
            <span className="gate-stat-lbl">retry interval</span>
          </div>
        </div>

        {/* Pulse dots — live retry indicator */}
        <div className="gate-pulse-row">
          {[0, 1, 2].map(i => (
            <motion.div
              key={i}
              className="gate-pulse-dot"
              animate={{ opacity: [0.2, 1, 0.2] }}
              transition={{ repeat: Infinity, duration: 1.5, delay: i * 0.3 }}
            />
          ))}
        </div>

        {status === 'offline' && (
          <button className="gate-retry-btn" onClick={retry}>
            <RefreshCw size={15} /> Retry now
          </button>
        )}

        <p className="gate-footer">
          Retrying automatically every {POLL_INTERVAL / 1000} seconds
        </p>
      </motion.div>
    </div>
  );
}