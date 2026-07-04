// SPDX-License-Identifier: Apache-2.0
import { useEffect, useState } from "react";
import { useWS } from "../stores/ws";

interface SearchResult {
  session_id: string;
  snippet: string;
  score: number;
}

export function Memory() {
  const config = useWS((s) => s.config);
  const send = useWS((s) => s.send);
  const client = useWS((s) => s.client);

  const [query, setQuery] = useState("");
  const [results, setResults] = useState<SearchResult[] | null>(null);
  const [rememberOpen, setRememberOpen] = useState(false);
  const [rememberText, setRememberText] = useState("");
  const [modalSession, setModalSession] = useState<string | null>(null);

  useEffect(() => {
    return client?.on((msg) => {
      if (msg.type === "memory.search_results") {
        if (msg.query === query) {
          setResults(msg.results);
        }
      }
    });
  }, [client, query]);

  const handleSearch = (e: React.FormEvent) => {
    e.preventDefault();
    if (!query.trim()) {
      setResults(null);
      return;
    }
    send({ type: "memory.search", query: query.trim() });
  };

  const handleRememberSave = () => {
    const body = rememberText.trim();
    if (!body) return;
    send({ type: "memory.remember", body });
    setRememberText("");
    setRememberOpen(false);
  };

  const profile = (config?.user ?? config?.profile ?? {}) as Record<string, unknown>;
  const profileEntries = Object.entries(profile);

  const searching = results !== null;

  return (
    <div className="max-w-[720px] mx-auto px-8 py-10 flex flex-col gap-10">
      <header>
        <h1 className="font-display text-2xl font-semibold tracking-[-0.01em]">Memory</h1>
        <p className="text-text-muted">Everything FSAR remembers about you</p>
      </header>

      <form onSubmit={handleSearch} className="flex items-center gap-3">
        <input
          value={query}
          onChange={(e) => {
            setQuery(e.target.value);
            if (!e.target.value.trim()) setResults(null);
          }}
          onKeyDown={(e) => {
            if (e.key === "Escape") {
              setQuery("");
              setResults(null);
            }
          }}
          placeholder="🔍 Search memory (semantic + keyword)"
          className="flex-1 h-9 px-3 bg-surface border border-border rounded text-[13px]"
        />
        <button
          type="submit"
          className="px-3 h-9 rounded border border-border-strong text-[13px]"
        >
          ↵
        </button>
      </form>

      {searching ? (
        <section>
          <div className="font-display text-[10px] font-bold uppercase tracking-[0.1em] text-text-muted mb-3">
            Search results · {results!.length}
          </div>
          {results!.length === 0 ? (
            <p className="text-text-muted text-sm">No matches for &quot;{query}&quot;.</p>
          ) : (
            <ul className="flex flex-col divide-y divide-border">
              {results!.map((r, i) => (
                <li key={i} className="py-3 flex flex-col gap-1">
                  <div className="flex items-center gap-3">
                    <span className="font-mono text-xs text-text-muted">
                      score {(r.score * 100).toFixed(0)}%
                    </span>
                    {r.session_id && (
                      <button
                        onClick={() => setModalSession(r.session_id)}
                        className="font-mono text-xs text-text underline hover:opacity-80"
                      >
                        {r.session_id.slice(0, 16)}
                      </button>
                    )}
                  </div>
                  <p className="text-sm">{r.snippet}</p>
                </li>
              ))}
            </ul>
          )}
        </section>
      ) : (
        <>
          <section>
            <div className="font-display text-[10px] font-bold uppercase tracking-[0.1em] text-text-muted mb-3">
              Profile
            </div>
            {profileEntries.length === 0 ? (
              <p className="text-text-muted text-sm">No profile yet.</p>
            ) : (
              <div className="border border-border rounded p-4 text-[13px]">
                {profileEntries.map(([k, v]) => (
                  <span key={k} className="mr-3">
                    <span className="text-text-muted">{k}:</span> {String(v)}
                  </span>
                ))}
              </div>
            )}
          </section>

          <section>
            <div className="font-display text-[10px] font-bold uppercase tracking-[0.1em] text-text-muted mb-3">
              Sessions
            </div>
            <p className="text-text-muted text-sm">No sessions yet.</p>
          </section>

          <section>
            <div className="flex items-center justify-between mb-3">
              <div className="font-display text-[10px] font-bold uppercase tracking-[0.1em] text-text-muted">
                Facts
              </div>
              <button
                onClick={() => setRememberOpen((v) => !v)}
                className="px-3 h-7 rounded border border-border-strong text-[12px]"
              >
                + Remember
              </button>
            </div>
            {rememberOpen && (
              <div className="border border-border rounded p-3 mb-3 flex flex-col gap-2">
                <textarea
                  value={rememberText}
                  onChange={(e) => setRememberText(e.target.value)}
                  rows={3}
                  placeholder="A fact worth remembering…"
                  className="w-full px-2 py-1 bg-bg border border-border rounded text-[13px] resize-none"
                />
                <div className="flex gap-2 justify-end">
                  <button
                    onClick={() => {
                      setRememberOpen(false);
                      setRememberText("");
                    }}
                    className="px-3 h-7 rounded border border-border text-[12px]"
                  >
                    Cancel
                  </button>
                  <button
                    onClick={handleRememberSave}
                    className="px-3 h-7 rounded border border-border-strong bg-text text-surface text-[12px]"
                  >
                    Save
                  </button>
                </div>
              </div>
            )}
            <p className="text-text-muted text-sm">No facts yet.</p>
          </section>
        </>
      )}

      {modalSession && (
        <div
          className="fixed inset-0 bg-black/40 flex items-center justify-center z-50"
          onClick={() => setModalSession(null)}
        >
          <dialog
            open
            className="w-[80vw] max-w-[720px] max-h-[80vh] overflow-auto bg-surface border border-border rounded p-6"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="flex items-center justify-between mb-4">
              <h2 className="font-display text-lg font-semibold">Session {modalSession.slice(0, 16)}</h2>
              <button
                onClick={() => setModalSession(null)}
                className="px-2 h-7 rounded border border-border text-[12px]"
              >
                Close
              </button>
            </div>
            <p className="text-text-muted text-sm">Transcript not yet loaded.</p>
          </dialog>
        </div>
      )}
    </div>
  );
}