import type { TrackStatus } from "../api";

export function AnalysisProgress({
  status,
  error,
}: {
  status: TrackStatus;
  error?: string;
}) {
  if (status === "pending") {
    return (
      <div className="state working" role="status">
        <p>
          <span className="pulse" />
          Working out the chords.
        </p>
        <p className="detail">First listen takes under a minute. Later views are instant.</p>
      </div>
    );
  }

  if (status === "unavailable") {
    return (
      <div className="state" role="status">
        <p>Couldn't find audio that matches this recording.</p>
        <p className="detail">
          Kord matches on track length so it doesn't analyse a live cut or a cover by
          mistake. {error}
        </p>
      </div>
    );
  }

  if (status === "failed") {
    return (
      <div className="state" role="status">
        <p>Analysis didn't finish.</p>
        <p className="detail">{error}</p>
      </div>
    );
  }

  return null;
}
