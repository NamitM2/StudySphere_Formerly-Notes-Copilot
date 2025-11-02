// web/src/Library.jsx
// Path: web/src/Library.jsx
import React, { useEffect, useState } from 'react';
import { getJSON } from './lib/api';
import { getAuthHeader, loadToken } from './lib/auth';
import LoadingLogo from './components/LoadingLogo';

export default function Library() {
  const [rows, setRows] = useState([]);
  const [err, setErr] = useState(null);
  const [loading, setLoading] = useState(false);
  const hasToken = !!loadToken();

  useEffect(() => {
    let cancelled = false;

    if (!hasToken) {
      setRows([]);
      setErr(null);
      setLoading(false);
      return;
    }

    const fetchRows = async () => {
      setLoading(true);
      setErr(null);

      try {
        const data = await getJSON('/files/list', { headers: getAuthHeader() });
        if (!cancelled) {
          setRows(Array.isArray(data) ? data : []);
        }
      } catch (e) {
        if (!cancelled) {
          setErr(String(e));
          setRows([]);
        }
      } finally {
        if (!cancelled) {
          setLoading(false);
        }
      }
    };

    fetchRows();

    return () => {
      cancelled = true;
    };
  }, [hasToken]);

  if (!hasToken) {
    return <div className="max-w-3xl mx-auto mt-10 card">Sign in to view your library.</div>;
  }

  return (
    <div className="max-w-4xl mx-auto mt-8">
      <h2 className="text-xl font-semibold mb-3">Your Library</h2>
      {err && <div className="text-red-400 text-sm mb-2">Error: {err}</div>}
      <div className="grid gap-2">
        {loading && (
          <div className="flex justify-center py-8">
            <LoadingLogo size="md" />
          </div>
        )}
        {!loading && rows.map((f) => (
          <div key={f.id} className="p-3 rounded-xl border border-zinc-800 flex justify-between">
            <div>
              <div className="font-medium">{f.name}</div>
              <div className="text-xs opacity-70">
                {((f.size ?? 0) / 1024).toFixed(1)} KB | {f.created_at ? new Date(f.created_at).toLocaleString() : ''}
              </div>
            </div>
            <a
              className="text-sm underline"
              href={`/files/${encodeURIComponent(f.id)}`}
              target="_blank"
              rel="noreferrer"
            >
              Download
            </a>
          </div>
        ))}
        {!loading && !rows.length && <div className="opacity-70 text-sm">No files yet. Upload one!</div>}
      </div>
    </div>
  );
}
