import { useEffect, useState } from "react";
import { getTrack, type TrackResponse, type TrackSummary } from "./api";
import { AnalysisProgress } from "./components/AnalysisProgress";
import { ChordChart } from "./components/ChordChart";
import { MoodRing } from "./components/MoodRing";
import { SearchBar } from "./components/SearchBar";
import { TheoryPanel } from "./components/TheoryPanel";
import "./styles.css";

export default function App() {
  const [picked, setPicked] = useState<TrackSummary | null>(null);
  const [data, setData] = useState<TrackResponse | null>(null);

  useEffect(() => {
    if (!picked) return;
    let live = true;
    let timer: number | undefined;

    async function poll(id: string) {
      try {
        const response = await getTrack(id);
        if (!live) return;
        setData(response);
        if (response.status === "pending") {
          timer = window.setTimeout(() => poll(id), 2500);
        }
      } catch {
        if (live) timer = window.setTimeout(() => poll(id), 5000);
      }
    }

    setData(null);
    poll(picked.id);
    return () => {
      live = false;
      window.clearTimeout(timer);
    };
  }, [picked]);

  const track = data?.track ?? picked;

  return (
    <>
      <div className="masthead">
        <h1 className="wordmark">
          Kord<span>.</span>
        </h1>
        <SearchBar onPick={setPicked} />
      </div>

      {!picked && (
        <div className="empty">
          <h2>See what a song is made of.</h2>
          <p>
            Search anything in your Spotify library. Kord works out the chords, the key
            and the scales that fit over it — then colours the page by the harmony.
          </p>
        </div>
      )}

      {track && (
        <main>
          <MoodRing stops={data?.palette ?? []}>
            <div className="now">
              <p className="eyebrow">Now showing</p>
              <h2>{track.title}</h2>
              <p className="artist">{track.artist}</p>
              {data?.status === "done" && data.theory && (
                <ul className="facts">
                  <li>
                    Key <b>{data.theory.key}</b>
                  </li>
                  <li>
                    Tempo <b>{Math.round(data.theory.tempo)}</b> BPM
                  </li>
                  <li>
                    <b>{data.chart?.length ?? 0}</b> chords
                  </li>
                </ul>
              )}
            </div>
          </MoodRing>

          {data && data.status !== "done" && (
            <AnalysisProgress status={data.status} error={data.error} />
          )}

          {data?.status === "done" && data.chart && data.theory && (
            <div className="song-body">
              <section>
                <p className="section-label">Progression</p>
                <ChordChart entries={data.chart} />
              </section>
              <TheoryPanel theory={data.theory} flags={data.flags ?? []} />
            </div>
          )}
        </main>
      )}
    </>
  );
}
