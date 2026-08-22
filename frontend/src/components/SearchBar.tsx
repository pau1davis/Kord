import { useEffect, useRef, useState } from "react";
import { ApiError, searchTracks, type TrackSummary } from "../api";

export function SearchBar({ onPick }: { onPick: (track: TrackSummary) => void }) {
  const [query, setQuery] = useState("");
  const [results, setResults] = useState<TrackSummary[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [needsAuth, setNeedsAuth] = useState(false);
  const container = useRef<HTMLDivElement>(null);

  useEffect(() => {
    function dismiss(event: MouseEvent) {
      if (!container.current?.contains(event.target as Node)) setResults([]);
    }
    document.addEventListener("mousedown", dismiss);
    return () => document.removeEventListener("mousedown", dismiss);
  }, []);

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    if (!query.trim()) return;
    setBusy(true);
    setError(null);
    setNeedsAuth(false);
    try {
      setResults(await searchTracks(query));
    } catch (e) {
      if (e instanceof ApiError && e.status === 401) {
        // Telling someone to connect without giving them the way to do it
        // leaves them to find /api/auth/login on their own.
        setNeedsAuth(true);
        setError("Connect your Spotify account, then search again.");
      } else if (e instanceof ApiError) {
        setError(e.message);
      } else {
        setError("Search failed.");
      }
    } finally {
      setBusy(false);
    }
  }

  function pick(track: TrackSummary) {
    onPick(track);
    setResults([]);
  }

  return (
    <div className="search" ref={container}>
      <form onSubmit={submit} role="search">
        <input
          value={query}
          onChange={(event) => setQuery(event.target.value)}
          placeholder="Search a song"
          aria-label="Search for a song"
        />
        <button type="submit" disabled={busy}>
          {busy ? "Searching" : "Search"}
        </button>
      </form>

      {error && (
        <ul className="results">
          <li className="detail" style={{ padding: "0.5rem" }}>
            {error}
            {needsAuth && <> <a href="/api/auth/login">Connect Spotify</a></>}
          </li>
        </ul>
      )}

      {results.length > 0 && (
        <ul className="results">
          {results.map((track) => (
            <li key={track.id}>
              <button onClick={() => pick(track)}>
                {track.image ? (
                  <img src={track.image} alt="" width={36} height={36} />
                ) : (
                  <span className="no-art" />
                )}
                <span>
                  <span className="title">{track.title}</span>
                  <br />
                  <span className="artist">{track.artist}</span>
                </span>
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
