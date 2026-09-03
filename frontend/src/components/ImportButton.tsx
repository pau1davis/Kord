import { useRef, useState } from "react";
import type { TrackSummary } from "../api";

/** For music no catalogue has — unreleased songs, your own band, a rehearsal
 *  tape. Secondary to search by design: most people have a title in mind. */
export function ImportButton({ onPick }: { onPick: (t: TrackSummary) => void }) {
  const input = useRef<HTMLInputElement | null>(null);
  const [busy, setBusy] = useState(false);

  async function send(file: File) {
    setBusy(true);
    try {
      const body = new FormData();
      body.append("file", file);
      const response = await fetch("/api/import", { method: "POST", body });
      const created = await response.json();
      onPick({ id: created.id, title: created.title, artist: "Imported",
               album: null, duration_ms: 0, image: null });
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
    </>
  );
}
