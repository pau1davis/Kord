import type { Library, TrackSummary } from "../api";

/**
 * The centre of the ring: what you were last working on and what your library
 * actually looks like. This sits where a headline would, because a headline
 * tells you nothing you can act on.
 */
export function Workbench({
  library, onResume,
}: {
  library: Library | null;
  onResume: (track: TrackSummary) => void;
}) {
  const resume = library?.resume ?? null;

  return (
    <div className="bench">
      <span className="strings" aria-hidden="true" />

      {resume ? (
        <>
          <p className="label">Pick up where you left off</p>
          <button
            className="resume"
            onClick={() => onResume({
              id: resume.id, title: resume.title, artist: resume.artist,
              album: null, duration_ms: 0, image: null,
            })}
          >
            <span className="song">{resume.title}</span>
            <span className="by">{resume.artist}</span>
          </button>
          {(resume.key || resume.tempo) && (
            <p className="spec">
              {resume.key}
              {resume.key && resume.tempo ? " · " : ""}
              {resume.tempo ? `${resume.tempo} BPM` : ""}
            </p>
          )}
        </>
      ) : (
        <>
          <p className="label">Nothing open yet</p>
          <p className="spec">Pick a sleeve, or search for a song to learn.</p>
        </>
      )}

      {library && library.analyzed > 0 && (
        <dl className="stats">
          <div>
            <dt>Analysed</dt>
            <dd>{library.analyzed}</dd>
          </div>
          <div>
            <dt>Playable</dt>
            <dd>{library.with_audio}</dd>
          </div>
          <div>
            <dt>Stems</dt>
            <dd>{library.with_stems}</dd>
          </div>
          {library.tempo && (
            <div>
              <dt>Tempo</dt>
              <dd>{library.tempo.min}–{library.tempo.max}</dd>
            </div>
          )}
          {library.keys[0] && (
            <div className="wide">
              <dt>Most in</dt>
              <dd>{library.keys[0].key}</dd>
            </div>
          )}
        </dl>
      )}
    </div>
  );
}
