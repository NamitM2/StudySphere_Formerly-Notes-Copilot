// web/src/SignIn.jsx
// Path: web/src/SignIn.jsx
import React, { useState } from 'react';
import { signIn, signUp } from './lib/auth';
import { useNavigate } from 'react-router-dom';

export default function SignIn() {
  const nav = useNavigate();
  const [email, setEmail] = useState('');
  const [pwd, setPwd]   = useState('');
  const [msg, setMsg]   = useState(null);
  const [busy, setBusy] = useState(false);

  async function doSignIn(e) {
    e.preventDefault();
    setBusy(true);
    try {
      await signIn(email, pwd);      // saves token + email to localStorage
      setMsg('Signed in!');
      nav('/');                      // back to home
    } catch (err) {
      setMsg(String(err));
    } finally {
      setBusy(false);
    }
  }

  async function doSignUp() {
    setBusy(true);
    try {
      await signUp(email, pwd);      // may require email confirm
      setMsg('Signed up. Check your email if confirmation is required.');
    } catch (err) {
      setMsg(String(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="max-w-md mx-auto mt-12 card">
      <h1 className="text-2xl font-semibold mb-4">Sign in</h1>
      <form className="space-y-3" onSubmit={doSignIn}>
        <input className="input" type="email" placeholder="you@illinois.edu" value={email} onChange={e=>setEmail(e.target.value)} required />
        <input className="input" type="password" placeholder="••••••••" value={pwd} onChange={e=>setPwd(e.target.value)} required />
        <div className="flex gap-2">
          <button className="btn" disabled={busy}>Sign in</button>
          <button onClick={doSignUp} className="btn" type="button" disabled={busy}>Sign up</button>
        </div>
      </form>
      {msg && <p className="mt-3 text-sm opacity-80 whitespace-pre-wrap">{msg}</p>}
    </div>
  );
}
