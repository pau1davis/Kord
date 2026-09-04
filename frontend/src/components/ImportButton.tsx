import { useRef, useState } from "react";
import { ApiError, importFile, type TrackSummary } from "../api";

/** For music no catalogue has — unreleased songs, your own band, a rehearsal
 *  tape. Secondary to search by design: most people have a title in mind. */
export function ImportButton({ onPick }: { onPick: (t: TrackSummary) => void }) {
  const input = useRef<HTMLInputElement | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function send(file: File) {
    setBusy(true);
    setError(null);
    try {
      const created = await importFile(file);
      onPick({ id: created.id, title: created.title, artist: "Imported",
               album: null, duration_ms: 0, image: null });
    } catch (e) {
      // A non-2xx response (an empty file, a broken upload) has no `id` —
      // opening a track that cannot exist is worse than saying what failed.
      setError(e instanceof ApiError ? e.message : "Couldn't read that file.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <>
      <button className="sep" disabled={busy}
              onClick={() => input.current?.click()}>
        {busy ? "Reading…" : "Open a file"}
      </button>
      <input
        ref={input} type="file" accept="audio/*" hidden
        onChange={(e) => { const f = e.target.files?.[0]; if (f) void send(f); }}
      />
      {error && <p className="hint">Couldn't import that file: {error}</p>}
    </>
  );
}
