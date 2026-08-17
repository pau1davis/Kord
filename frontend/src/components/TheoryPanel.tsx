import type { Theory, Tuning } from "../api";
import { referenceCaveat, referenceLine } from "../tuning";

export function TheoryPanel({
  theory, flags, tuning,
}: {
  theory: Theory;
  flags: string[];
  tuning?: Tuning | null;
}) {
  const reference = referenceLine(tuning);
  const caveat = referenceCaveat(tuning, flags);

  return (
    <aside className="theory">
      <p className="section-label">Key</p>
      <h3>
        {theory.key}
        {theory.key_uncertain && (
          <span
            className="uncertain-mark"
            title="Two estimators disagreed on the key — treat it as a starting point"
          >
            {" ?"}
          </span>
        )}
      </h3>
      <p className="notes">{theory.scale.notes.join(" ")}</p>

      {(reference || caveat) && (
        <>
          <p className="section-label">Tuning</p>
          {reference && <p className="reference">{reference}</p>}
          {caveat && <p className="notes quiet">{caveat}</p>}
          {reference && (
            <p className="notes quiet">
              How far the record sits from A440. It doesn't say whether the band
              tuned down — a whole step down just sounds like a different key,
              which no measurement can separate from the song being written
              there.
            </p>
          )}
        </>
      )}

      <h4>Play over it</h4>
      <ul>
        {theory.scale.suggestions.map((suggestion) => (
          <li key={suggestion}>{suggestion}</li>
        ))}
      </ul>

      {flags.includes("speed_adjusted") && (
        <span className="flag">
          The source recording runs at a slightly different speed to the Spotify master.
          Timings are corrected; the key may sit a fraction of a semitone off.
        </span>
      )}
    </aside>
  );
}
