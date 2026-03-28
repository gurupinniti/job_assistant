import React, { useState, useMemo } from 'react';
import { Search, X, Plus, CheckCircle } from 'lucide-react';

// Simple client-side spell corrections matching the backend memory file
const MISSPELLINGS = {
  engieer: 'Engineer', enginer: 'Engineer', developper: 'Developer',
  develper: 'Developer', scientest: 'Scientist', scienist: 'Scientist',
  analst: 'Analyst', anlayst: 'Analyst', manageer: 'Manager',
  mangager: 'Manager', archtiect: 'Architect', archetect: 'Architect',
  programer: 'Programmer', specilaist: 'Specialist', senoir: 'Senior',
  juinor: 'Junior', princpal: 'Principal', techincal: 'Technical',
  artifical: 'Artificial', intellegence: 'Intelligence',
  maching: 'Machine', lerning: 'Learning',
};

function correctSpelling(text) {
  return text.split(' ').map(w => {
    const fixed = MISSPELLINGS[w.toLowerCase()];
    return fixed || w;
  }).join(' ');
}

// Title-case helper
function toTitleCase(str) {
  const lower = ['a','an','the','and','but','or','for','nor','on','at',
                  'to','by','in','of','up','as','is'];
  return str.split(' ').map((w, i) =>
    i === 0 || !lower.includes(w.toLowerCase())
      ? w.charAt(0).toUpperCase() + w.slice(1)
      : w.toLowerCase()
  ).join(' ');
}

export default function JobTitleSelector({ titles, selected, onToggle, primaryTitles = [] }) {
  const [query,       setQuery]       = useState('');
  const [customInput, setCustomInput] = useState('');
  const [customTitles, setCustomTitles] = useState([]);
  const [spellHint,   setSpellHint]   = useState('');

  const allTitles = useMemo(() =>
    [...new Set([...titles, ...customTitles])],
    [titles, customTitles]
  );

  // Primary (AI-suggested) titles shown at top
  const primarySet = new Set(primaryTitles.map(t => t.toLowerCase()));

  const filtered = useMemo(() => {
    const q = query.toLowerCase();
    return allTitles.filter(t => t.toLowerCase().includes(q));
  }, [allTitles, query]);

  const pinnedFiltered = filtered.filter(t => primarySet.has(t.toLowerCase()));
  const restFiltered   = filtered.filter(t => !primarySet.has(t.toLowerCase()));

  // Handle custom title addition
  const handleAddCustom = () => {
    const raw       = customInput.trim();
    if (!raw) return;
    const corrected = toTitleCase(correctSpelling(raw));
    if (!allTitles.includes(corrected)) {
      setCustomTitles(prev => [...prev, corrected]);
    }
    onToggle(corrected);  // auto-select it
    setCustomInput('');
    setSpellHint('');
  };

  // Live spell hint as user types
  const handleCustomChange = (val) => {
    setCustomInput(val);
    const corrected = toTitleCase(correctSpelling(val));
    if (corrected !== toTitleCase(val) && val.trim().length > 2) {
      setSpellHint(corrected);
    } else {
      setSpellHint('');
    }
  };

  return (
    <div className="title-selector">

      {/* Search */}
      <div className="title-search-wrap">
        <Search size={16} className="search-icon"/>
        <input className="title-search"
          placeholder="Search job titles..."
          value={query}
          onChange={e => setQuery(e.target.value)}
        />
        {query && <button className="clear-search" onClick={() => setQuery('')}><X size={14}/></button>}
      </div>

      {/* Selected chips */}
      {selected.length > 0 && (
        <div className="selected-titles">
          {selected.map(t => (
            <span key={t} className="selected-chip" onClick={() => onToggle(t)}>
              {t} <X size={12}/>
            </span>
          ))}
        </div>
      )}

      {/* Titles grid */}
      <div className="titles-grid">
        {/* Primary (AI-suggested) first */}
        {!query && pinnedFiltered.length > 0 && (
          <>
            <div className="titles-section-label">
              <CheckCircle size={12}/> Suggested from your resume
            </div>
            {pinnedFiltered.map(t => (
              <button key={t}
                className={`title-chip primary-chip ${selected.includes(t) ? 'selected' : ''}`}
                onClick={() => onToggle(t)}>
                {t}
              </button>
            ))}
            {restFiltered.length > 0 && (
              <div className="titles-section-label" style={{marginTop: 8}}>
                More titles
              </div>
            )}
          </>
        )}

        {/* Rest of titles */}
        {(query ? filtered : restFiltered).map(t => (
          <button key={t}
            className={`title-chip ${selected.includes(t) ? 'selected' : ''}`}
            onClick={() => onToggle(t)}>
            {t}
          </button>
        ))}

        {filtered.length === 0 && !customInput && (
          <p className="no-results">No titles match "{query}" — add it below</p>
        )}
      </div>

      {/* Custom title input */}
      <div className="custom-title-wrap">
        <div className="custom-title-row">
          <input
            className="custom-title-input"
            placeholder="Add a custom job title..."
            value={customInput}
            onChange={e => handleCustomChange(e.target.value)}
            onKeyDown={e => e.key === 'Enter' && handleAddCustom()}
          />
          <button
            className="custom-title-btn"
            onClick={handleAddCustom}
            disabled={!customInput.trim()}
          >
            <Plus size={15}/> Add
          </button>
        </div>
        {spellHint && (
          <div className="spell-hint">
            Did you mean: <button className="spell-hint-btn"
              onClick={() => { setCustomInput(spellHint); setSpellHint(''); }}>
              {spellHint}
            </button>?
          </div>
        )}
        {customTitles.length > 0 && (
          <div className="custom-titles-list">
            {customTitles.map(t => (
              <span key={t} className="custom-title-tag">
                ✎ {t}
                <button onClick={() => {
                  setCustomTitles(c => c.filter(x => x !== t));
                  if (selected.includes(t)) onToggle(t);
                }}><X size={10}/></button>
              </span>
            ))}
          </div>
        )}
      </div>

      <p className="selection-count">
        {selected.length} title{selected.length !== 1 ? 's' : ''} selected
      </p>
    </div>
  );
}