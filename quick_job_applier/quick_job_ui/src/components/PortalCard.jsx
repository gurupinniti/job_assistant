import React from 'react';
import { ExternalLink, AlertTriangle, Zap, MousePointer, Lock } from 'lucide-react';

const TIER_CONFIG = {
  1: { label: 'No login',  color: '#00D68F', icon: <Zap size={10}/> },
  2: { label: 'Optional',  color: '#F7C948', icon: <MousePointer size={10}/> },
  3: { label: 'Login req', color: '#FF6090', icon: <Lock size={10}/> },
};

export function PortalConfirmCard({ portal, checked, onToggle }) {
  const tier   = portal.tier || 2;
  const tConf  = TIER_CONFIG[tier] || TIER_CONFIG[2];

  return (
    <div
      className={`portal-card ${checked ? 'checked' : ''}`}
      onClick={() => onToggle(portal.name)}
    >
      <div className="portal-check">
        <div className={`checkbox ${checked ? 'checked' : ''}`}>
          {checked && '✓'}
        </div>
      </div>

      <div className="portal-body">
        <div className="portal-header-row">
          <span className="portal-name">{portal.name}</span>
          <div className="portal-badges">
            <span className="badge" style={{
              background: tConf.color + '22',
              color: tConf.color,
              border: `1px solid ${tConf.color}44`,
            }}>
              {tConf.icon} Tier {tier} · {tConf.label}
            </span>
          </div>
        </div>
        {portal.description && (
          <div className="portal-description">{portal.description}</div>
        )}
        <a className="portal-url" href={portal.url} target="_blank" rel="noreferrer"
          onClick={e => e.stopPropagation()}>
          {portal.url} <ExternalLink size={11}/>
        </a>
        {portal.restriction && (
          <div className="restriction-note">
            <AlertTriangle size={12}/> {portal.restriction}
          </div>
        )}
      </div>
    </div>
  );
}

export function PortalStatusCard({ name, status, message, matchScore }) {
  return (
    <div className="portal-status-card">
      <div className="status-body">
        <span className="status-portal-name">{name}</span>
        {matchScore && <span className="match-score">Match: {matchScore}%</span>}
        <div className="status-message">{message || status}</div>
      </div>
    </div>
  );
}