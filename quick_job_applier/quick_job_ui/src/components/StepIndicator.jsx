import React from 'react';
import { Check } from 'lucide-react';

const STEPS = [
  { n: 1, label: 'Resume & Preferences' },
  { n: 2, label: 'Confirm Portals'      },
  { n: 3, label: 'Select Jobs'          },
  { n: 4, label: 'Apply & Status'       },
];

export default function StepIndicator({ current, onGoToStep }) {
  return (
    <div className="step-indicator">
      {STEPS.map((s, i) => {
        const isDone   = current > s.n;
        const isActive = current === s.n;
        const canClick = isDone && onGoToStep; // only completed steps are clickable

        return (
          <React.Fragment key={s.n}>
            <div
              className={`step-item ${isActive ? 'active' : ''} ${isDone ? 'done' : ''} ${canClick ? 'clickable' : ''}`}
              onClick={() => canClick && onGoToStep(s.n)}
              title={canClick ? `Go back to ${s.label}` : ''}
            >
              <div className="step-circle">
                {isDone ? <Check size={14} strokeWidth={3}/> : s.n}
              </div>
              <span className="step-label">{s.label}</span>
            </div>
            {i < STEPS.length - 1 && (
              <div className={`step-line ${current > s.n + 1 || current === s.n + 1 ? 'done' : ''}`} />
            )}
          </React.Fragment>
        );
      })}
    </div>
  );
}