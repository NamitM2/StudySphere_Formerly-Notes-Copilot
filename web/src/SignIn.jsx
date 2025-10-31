// web/src/SignIn.jsx
// Path: web/src/SignIn.jsx
import React, { useState } from 'react';
import { signIn, signUp } from './lib/auth';
import { useNavigate } from 'react-router-dom';
import Toast from './components/Toast';
import LoadingLogo from './components/LoadingLogo';

export default function SignIn() {
  const nav = useNavigate();
  const [email, setEmail] = useState('');
  const [pwd, setPwd]   = useState('');
  const [toast, setToast] = useState(null);
  const [busy, setBusy] = useState(false);

  async function doSignIn(e) {
    e.preventDefault();
    setBusy(true);
    try {
      await signIn(email, pwd);
      setToast({ message: 'Signed in successfully!', type: 'success' });
      setTimeout(() => nav('/'), 1000); // Give user time to see success message
    } catch (err) {
      console.error('Sign in error:', err);
      // Use the error message from auth.js (already user-friendly)
      setToast({ message: err.message || 'Sign in failed. Please try again.', type: 'error' });
    } finally {
      setBusy(false);
    }
  }

  async function doSignUp() {
    setBusy(true);
    try {
      await signUp(email, pwd);
      setToast({
        message: 'Account created! Check your email if confirmation is required.',
        type: 'success'
      });
    } catch (err) {
      // Show user-friendly error message
      const errorMsg = err.message?.includes('already')
        ? 'An account with this email already exists'
        : err.message?.includes('password')
        ? 'Password must be at least 6 characters'
        : err.message?.includes('email')
        ? 'Please enter a valid email address'
        : 'Sign up failed. Please try again.';

      setToast({ message: errorMsg, type: 'error' });
    } finally {
      setBusy(false);
    }
  }

  return (
    <>
      {toast && (
        <Toast
          message={toast.message}
          type={toast.type}
          onClose={() => setToast(null)}
        />
      )}
      <div className="max-w-md mx-auto mt-12 card">
        <div className="text-center mb-8">
          <h1 className="text-4xl font-bold mb-4 bg-gradient-to-r from-orange-400 via-amber-400 to-pink-400 bg-clip-text text-transparent">
            StudySphere
          </h1>
          <div className="flex justify-center mb-4">
            <LoadingLogo size="md" />
          </div>
          <p className="text-zinc-400 text-sm">
            Breeze through assignments and prepare for exams, powered completely by AI
          </p>
        </div>
        <form className="space-y-3" onSubmit={doSignIn}>
          <input className="input" type="email" placeholder="you@illinois.edu" value={email} onChange={e=>setEmail(e.target.value)} required />
          <input className="input" type="password" placeholder="••••••••" value={pwd} onChange={e=>setPwd(e.target.value)} required />
          <div className="flex gap-2">
            <button className="btn" disabled={busy}>Sign in</button>
            <button onClick={doSignUp} className="btn" type="button" disabled={busy}>Sign up</button>
          </div>
        </form>
      </div>
    </>
  );
}
