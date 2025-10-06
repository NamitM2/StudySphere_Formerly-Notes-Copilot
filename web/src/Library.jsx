// web/src/Library.jsx
// Path: web/src/Library.jsx
import React, { useEffect, useState } from 'react';
import { getJSON } from './lib/api';
import { getAuthHeader, loadToken } from './lib/auth';

export default function Library() {
  const [rows, setRows] = useState([]);
  const [err, setErr] = useState(null);
  const hasToken = !!loadToken();

  useEffect(() => {
    if (!hasToken) return;
    (async () => {
      try {
        const data = await getJSON('/files/list', getAuthHeader());
        setRows(Array.isArray(data) ? data : []);
      } catch (e) {
        setErr(String(e));
      }
    })();
  }, [hasToken]);

  if (!hasToken) {
    return <div className="max-w-3xl mx-auto mt-10 card">Sign in to view your library.</div>;
  }

  return (
    <div className="max-w-4xl mx-auto mt-8">
      <h2 className="text-xl font-semibold mb-3">Your Library</h2>
      {err && <div className="text-red-400 text-sm mb-2">Error: {err}</div>}
      <div className="grid gap-2">
        {rows.map(f => (
          <div key={f.id} className="p-3 rounded-xl border border-zinc-800 flex justify-between">
            <div>
              <div className="font-medium">{f.name}</div>
              <div className="text-xs opacity-70">
                {((f.size ?? 0)/1024).toFixed(1)} KB • {f.created_at ? new Date(f.created_at).toLocaleString() : ''}
              </div>
            </div>
            <a className="text-sm underline" href={`/files/${encodeURIComponent(f.id)}`} target="_blank" rel="noreferrer">Download</a>
          </div>
        ))}
        {!rows.length && <div className="opacity-70 text-sm">No files yet. Upload one!</div>}
      </div>
    </div>
  );
}
