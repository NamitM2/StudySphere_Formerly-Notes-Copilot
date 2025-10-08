// Guaranteed API base (works even if index.html override is missing)
window.__API_BASE =
  window.__API_BASE ||
  (import.meta?.env?.VITE_API_BASE) ||
  "https://notes-copilot.onrender.com/api";

import React from 'react';
import ReactDOM from 'react-dom/client';
import { BrowserRouter, Routes, Route } from 'react-router-dom';
import App from './App';
import './index.css';
import ErrorBoundary from './ErrorBoundary';
import SignIn from './SignIn';
import Library from './Library';

ReactDOM.createRoot(document.getElementById('root')).render(
  <React.StrictMode>
    <ErrorBoundary>
      <BrowserRouter>
        <Routes>
          <Route path="/" element={<App />} />
          <Route path="/login" element={<SignIn />} />
          <Route path="/library" element={<Library />} />
        </Routes>
      </BrowserRouter>
    </ErrorBoundary>
  </React.StrictMode>
);
