import React from 'react';

const TIER_CONFIG = {
  1: { color: '#00D68F', label: 'No login' },
  2: { color: '#F7C948', label: 'Optional' },
  3: { color: '#FF6090', label: 'Login req' },
};

// All portals grouped by tier for quick selection before country analysis
const DEFAULT_PORTALS = [
  { name: 'Adzuna',          tier: 1, description: 'Global · no login · salary data' },
  { name: 'RemoteOK',        tier: 1, description: 'Remote roles · no login' },
  { name: 'Arbeitnow',       tier: 1, description: 'Global · no login' },
  { name: 'TheMuse',         tier: 1, description: 'Tech & creative · no login' },
  { name: 'Jobsdb',          tier: 1, description: 'Asia-Pacific · no login' },
  { name: 'Indeed',          tier: 2, description: 'Many jobs apply without login' },
  { name: 'JobStreet',       tier: 2, description: 'Southeast Asia' },
  { name: 'Naukri',          tier: 2, description: 'India focus' },
  { name: 'Seek',            tier: 2, description: 'AU / NZ focus' },
  { name: 'Reed',            tier: 2, description: 'UK focus' },
  { name: 'LinkedIn',        tier: 3, description: 'Login required' },
  { name: 'MyCareersFuture', tier: 3, description: 'SingPass required' },
  { name: 'Glassdoor',       tier: 3, description: 'Login required' },
];

export default function PortalMultiSelect({ selected, onToggle }) {
  const tiers = [1, 2, 3];

  const handleSelectTier = (tier) => {
    const tierPortals = DEFAULT_PORTALS.filter(p => p.tier === tier).map(p => p.name);
    const allSelected = tierPortals.every(n => selected.includes(n));
    tierPortals.forEach(n => {
      const isSelected = selected.includes(n);
      if (allSelected && isSelected) onToggle(n);      // deselect all
      else if (!allSelected && !isSelected) onToggle(n); // select missing
    });
  };

  return (
    <div className="portal-multiselect">
      <p className="portal-ms-hint">
        Select portals to search. Tier 1 (no login) are fastest to apply to.
      </p>
      {tiers.map(tier => {
        const tc      = TIER_CONFIG[tier];
        const portals = DEFAULT_PORTALS.filter(p => p.tier === tier);
        const allSel  = portals.every(p => selected.includes(p.name));
        return (
          <div key={tier} className="portal-ms-tier">
            <div className="portal-ms-tier-header">
              <span className="portal-ms-tier-badge"
                style={{ background: tc.color + '22', color: tc.color,
                         border: `1px solid ${tc.color}44` }}>
                Tier {tier} · {tc.label}
              </span>
              <button className="portal-ms-select-all"
                onClick={() => handleSelectTier(tier)}>
                {allSel ? 'Deselect all' : 'Select all'}
              </button>
            </div>
            <div className="portal-ms-chips">
              {portals.map(p => {
                const checked = selected.includes(p.name);
                return (
                  <button key={p.name}
                    className={`portal-ms-chip ${checked ? 'selected' : ''}`}
                    style={checked ? {
                      background: tc.color + '18',
                      borderColor: tc.color + '66',
                      color: tc.color,
                    } : {}}
                    onClick={() => onToggle(p.name)}
                    title={p.description}>
                    {checked && <span className="portal-ms-check">✓</span>}
                    {p.name}
                  </button>
                );
              })}
            </div>
          </div>
        );
      })}
      <p className="portal-ms-count">
        {selected.length} portal{selected.length !== 1 ? 's' : ''} selected
      </p>
    </div>
  );
}