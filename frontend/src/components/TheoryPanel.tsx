import type { Theory } from "../api";

export function TheoryPanel({ theory, flags }: { theory: Theory; flags: string[] }) {
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
