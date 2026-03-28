import React from 'react';
import ReactDOM from 'react-dom/client';
import App from './App';
import BackendGate from './components/BackendGate';

const root = ReactDOM.createRoot(document.getElementById('root'));
root.render(
  <React.StrictMode>
    <BackendGate>
      <App />
    </BackendGate>
  </React.StrictMode>
);