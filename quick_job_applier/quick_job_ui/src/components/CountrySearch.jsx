import React, { useState, useMemo, useRef, useEffect } from 'react';
import { Globe, ChevronDown } from 'lucide-react';

const COUNTRY_FLAGS = {
  Singapore: '🇸🇬', India: '🇮🇳', Australia: '🇦🇺', Usa: '🇺🇸',
  Uk: '🇬🇧', Malaysia: '🇲🇾', Uae: '🇦🇪', Germany: '🇩🇪', Canada: '🇨🇦',
};

export default function CountrySearch({ countries, selected, onSelect }) {
  const [query,  setQuery]  = useState('');
  const [open,   setOpen]   = useState(false);
  const ref = useRef(null);

  const countryList = useMemo(() =>
    Object.keys(countries).map(c => ({
      value:  c.toLowerCase(),
      label:  c,
      flag:   COUNTRY_FLAGS[c] || '🌍',
      portals: (countries[c] || []).length,
    })).filter(c => c.label.toLowerCase().includes(query.toLowerCase())),
    [countries, query]
  );

  useEffect(() => {
    const handler = e => { if (!ref.current?.contains(e.target)) setOpen(false); };
    document.addEventListener('mousedown', handler);
    return () => document.removeEventListener('mousedown', handler);
  }, []);

  return (
    <div className="country-search" ref={ref}>
      <div className={`country-trigger ${open ? 'open' : ''}`} onClick={() => setOpen(o => !o)}>
        <Globe size={18} className="globe-icon" />
        {selected
          ? <span className="selected-country">{COUNTRY_FLAGS[selected.label] || '🌍'} {selected.label}</span>
          : <span className="placeholder">Select target country...</span>
        }
        <ChevronDown size={16} className={`chevron ${open ? 'rotate' : ''}`} />
      </div>

      {open && (
        <div className="country-dropdown">
          <input
            className="country-filter"
            placeholder="Search country..."
            value={query}
            onChange={e => setQuery(e.target.value)}
            autoFocus
          />
          <div className="country-list">
            {countryList.map(c => (
              <div
                key={c.value}
                className={`country-option ${selected?.value === c.value ? 'active' : ''}`}
                onClick={() => { onSelect(c); setOpen(false); setQuery(''); }}
              >
                <span className="country-flag">{c.flag}</span>
                <span className="country-name">{c.label}</span>
                <span className="portal-count">{c.portals} portals</span>
              </div>
            ))}
            {countryList.length === 0 && <p className="no-results">No countries found</p>}
          </div>
        </div>
      )}
    </div>
  );
}