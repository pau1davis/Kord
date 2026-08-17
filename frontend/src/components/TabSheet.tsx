import { useEffect, useMemo, useRef, useState } from "react";
import {
  BASS_TUNINGS, getTab, getTabStatus, GUITAR_TUNINGS, requestTab,
  type TabState,
} from "../api";
import {
  barIndexAt, DIM_BELOW, stringLabels, timeOfBar, toBars,
  type TabResponse,
} from "../tab";

function isWorking(status: TabState): boolean {
  return status === "pending" || status === "running";
}

/** One bar of tab: a fret number per note, on the string it is played on. */
function Bar({
  strings, notes, current,
}: {
  strings: number;
  notes: TabResponse["notes"];
  current: boolean;
}) {
  const labels = stringLabels(strings);
  return (
    <div className={current ? "tab-bar now" : "tab-bar"}>
      {labels.map((_, index) => {
        const row = labels.length - 1 - index;   // highest string on top
        return (
          <div className="tab-line" key={row}>
            {notes.map((note, i) => (
              <span
                className={
                  note.string === row
                    ? (note.confidence < DIM_BELOW ? "fret unsure" : "fret")
                    : "gap"
                }
                key={i}
              >
                {note.string === row && note.fret !== null ? note.fret : ""}
              </span>
            ))}
          </div>
        );
      })}
    </div>
  );
}

export function TabSheet({
  trackId, currentTime, onSeek, playing, onPause,
}: {
  trackId: string;
  currentTime: number;
  onSeek: (seconds: number) => void;
  playing: boolean;
  onPause: () => void;
}) {
  const [status, setStatus] = useState<TabState>("none");
  const [available, setAvailable] = useState<string[]>([]);
  const [progress, setProgress] = useState(0);
  const [part, setPart] = useState<string | null>(null);
  const [tuning, setTuning] = useState<string | null>(null);
  const [tab, setTab] = useState<TabResponse | null>(null);
  const scroller = useRef<HTMLDivElement | null>(null);
  // Set while the component is scrolling itself, so its own scroll events can
  // be told apart from the reader's. This is the whole trick: without it the
  // sheet pauses the song the instant it starts following it.
  const selfScrolling = useRef(false);

  const working = isWorking(status);
  useEffect(() => {
    let live = true;
    let timer: number | undefined;
    async function poll() {
      try {
        const s = await getTabStatus(trackId);
        if (!live) return;
        setStatus(s.status);
        setAvailable(s.available);
        setProgress(s.progress);
        if (isWorking(s.status)) timer = window.setTimeout(poll, 3000);
      } catch {
        if (live) timer = window.setTimeout(poll, 8000);
      }
    }
    poll();
    return () => { live = false; window.clearTimeout(timer); };
  }, [trackId, working]);

  // Default to the first part available, which is bass when there is one.
  useEffect(() => {
    if (part === null && available.length) setPart(available[0]);
  }, [available, part]);

  useEffect(() => { setPart(null); setTuning(null); setTab(null); }, [trackId]);

  useEffect(() => {
    if (!part) return;
    let live = true;
    getTab(trackId, part, tuning ?? undefined)
      .then((t) => { if (live) { setTab(t); setTuning(t.tuning); } })
      .catch(() => { if (live) setTab(null); });
    return () => { live = false; };
  }, [trackId, part, tuning]);

  const bars = useMemo(
    () => (tab ? toBars(tab.notes, tab.bars) : []), [tab]);
  const currentBar = barIndexAt(bars, currentTime);

  // Follow the playhead. Marked as our own scrolling so the handler below does
  // not read it as the reader taking over and pause the song.
  useEffect(() => {
    const element = scroller.current?.querySelector<HTMLElement>(
      `[data-bar="${currentBar}"]`);
    if (!element || !playing) return;
    selfScrolling.current = true;
    element.scrollIntoView({ block: "nearest", inline: "center",
                             behavior: "smooth" });
    const done = window.setTimeout(() => { selfScrolling.current = false; }, 600);
    return () => window.clearTimeout(done);
  }, [currentBar, playing]);

  if (status === "none") {
    return (
      <section className="tabsheet">
        <button className="sep" onClick={() => { requestTab(trackId); setStatus("pending"); }}>
          Work out the tab
        </button>
        <p className="hint">
          Reads the notes off the separated parts. Bass is reliable; guitar is a
          starting point you should check by ear.
        </p>
      </section>
    );
  }

  if (working) {
    return (
      <section className="tabsheet">
        <div className="sep-progress">
          <div className="bar"><span style={{ width: `${Math.max(2, progress * 100)}%` }} /></div>
          <p className="hint">
            <span className="spinner" aria-hidden="true" />
            Working out the tab — {Math.round(progress * 100)}%
          </p>
        </div>
      </section>
    );
  }

  if (status === "failed" || status === "unavailable") {
    return (
      <section className="tabsheet">
        <p className="hint">
          Couldn't work out the tab. Separate the parts first — the tab is read
          off them.
        </p>
      </section>
    );
  }

  if (!tab || !part) return null;

  const tunings = part === "bass" ? BASS_TUNINGS : GUITAR_TUNINGS;

  return (
    <section className="tabsheet">
      <div className="tabhead">
        <div className="tabparts">
          {available.map((name) => (
            <button
              key={name}
              className={name === part ? "part on" : "part"}
              onClick={() => { setPart(name); setTuning(null); }}
            >
              {name}
            </button>
          ))}
        </div>

        <label className="tuningpick">
          <span className="visually-hidden">Tuning</span>
          <select value={tuning ?? ""} onChange={(e) => setTuning(e.target.value)}>
            {tunings.map((name) => <option key={name} value={name}>{name}</option>)}
          </select>
        </label>
      </div>

      <div
        className="tabscroll"
        ref={scroller}
        onScroll={() => {
          // Taking the scrollbar is an interruption: the record should not keep
          // running away from what you are looking at.
          if (selfScrolling.current) return;
          if (playing) onPause();
        }}
      >
        {bars.map((bar) => (
          <div
            className="tab-slot"
            key={bar.index}
            data-bar={bar.index}
            onClick={() => onSeek(timeOfBar(bars, bar.index))}
            title={`Play from bar ${bar.index + 1}`}
          >
            <Bar
              strings={tab.strings}
              notes={bar.notes}
              current={bar.index === currentBar}
            />
            <span className="tab-num">{bar.index + 1}</span>
          </div>
        ))}
      </div>

      <p className="hint quiet">
        {part === "bass"
          ? "Read off the isolated bass, which transcribes reliably."
          : "Read off the isolated guitar. Dimmed notes are ones the "
            + "transcriber was unsure of — high-gain power chords are the weak "
            + "case. Check it by ear."}
        {" Bars assume 4/4."}
        {tab.unplayable > 0
          && ` ${tab.unplayable} notes can't be played in ${tab.tuning} — try another tuning.`}
      </p>
    </section>
  );
}
