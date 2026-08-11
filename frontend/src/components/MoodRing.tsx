import type { PaletteStop } from "../api";

/** Plain-language names for the spec section 7 hues, used for the accessible label. */
const MOOD_NAMES: Record<number, string> = {
  0: "heavy",
  30: "bluesy",
  40: "bright",
  170: "open",
  220: "melancholy",
  285: "tense",
};

export function describePalette(stops: PaletteStop[]): string {
  if (stops.length === 0) return "No harmony detected";
  return stops
    .map((stop) => `${Math.round(stop.weight * 100)}% ${MOOD_NAMES[stop.hue] ?? "unclassified"}`)
    .join(", ");
}

/**
 * The mood field is the page's ground, not a widget: Kord has no fixed accent
 * colour, so what you are looking at supplies the palette. Blob size and opacity
 * track each hue's share of playing time.
 */
export function MoodRing({ stops, children }: { stops: PaletteStop[]; children?: React.ReactNode }) {
  return (
    <header className="mood-field">
      {stops.map((stop, index) => (
        <span
          key={stop.hue}
          className="blob"
          aria-hidden="true"
          style={{
            background: `hsl(${stop.hue} 72% 50%)`,
            width: `${28 + stop.weight * 55}vw`,
            height: `${28 + stop.weight * 55}vw`,
            left: `${(index * 29) % 72}%`,
            top: `${-20 + ((index * 23) % 45)}%`,
            opacity: 0.22 + stop.weight * 0.5,
            animationDelay: `${index * -4.5}s`,
          }}
        />
      ))}
      <span className="veil" aria-hidden="true" />
      <span className="visually-hidden" role="img" aria-label={describePalette(stops)} />
      {children}
    </header>
  );
}
