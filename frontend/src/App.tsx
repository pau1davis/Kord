import { useCallback, useEffect, useRef, useState } from "react";
import { getTrack, type TrackResponse, type TrackSummary } from "./api";
import { chartTime, loopTarget, type LoopRange } from "./chart";
import { usePlayhead } from "./hooks/usePlayhead";
import { songInView } from "./navigation";
import { createPlayer, type Player } from "./player";
import { AnalysisProgress } from "./components/AnalysisProgress";
import { ChordSheet } from "./components/ChordSheet";
import { Home } from "./components/Home";
import { MoodRing } from "./components/MoodRing";
import { NowPlaying } from "./components/NowPlaying";
import { PlayAlong } from "./components/PlayAlong";
import { SearchBar } from "./components/SearchBar";
import { SongMap } from "./components/SongMap";
import { StemMixer } from "./components/StemMixer";
import { TheoryPanel } from "./components/TheoryPanel";
import "./styles.css";

export default function App() {
  const [picked, setPicked] = useState<TrackSummary | null>(null);
  const [data, setData] = useState<TrackResponse | null>(null);

  useEffect(() => {
    // Leaving for the dashboard drops the analysis with the song: keeping it
    // would leave a finished response describing a song no longer on screen.
    if (!picked) {
      setData(null);
      return;
    }
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

  const [player, setPlayer] = useState<Player | null>(null);
  const [loop, setLoop] = useState<LoopRange | null>(null);
  // Single source of truth for the playhead: PlayAlong and SongMap must advance
  // together, and a hook owned by a child would only re-render that child.
  const { currentTime, playing } = usePlayhead(player);
  const loopRef = useRef<LoopRange | null>(null);
  loopRef.current = loop;

  // Create a player once the song has audio; tear it down when the song changes.
  useEffect(() => {
    if (!picked || data?.status !== "done" || !data.has_audio) return;
    const p = createPlayer(picked.id);
    setPlayer(p);
    return () => {
      p.destroy();
      setPlayer(null);
      setLoop(null);
    };
  }, [picked, data?.status, data?.has_audio]);

  // Loop enforcement. Sample-accurate, so no seek guard is needed.
  useEffect(() => {
    if (!player) return;
    const offsetS = (data?.sync_offset_ms ?? 0) / 1000;
    let frame = 0;
    const tick = () => {
      const target = loopTarget(
        chartTime(player.el.currentTime, data?.sync_offset_ms ?? 0),
        loopRef.current, offsetS);
      if (target !== null) player.seek(target);
      frame = requestAnimationFrame(tick);
    };
    frame = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(frame);
  }, [player, data?.sync_offset_ms]);

  // The mixer owns its own AudioContext, so the two must never sound at once.
  const [stemsActive, setStemsActive] = useState(false);
  // Stable identity: the mixer tears down its player in a cleanup keyed on
  // this prop, so a new function each render would destroy it every render.
  const handleStemsActive = useCallback((active: boolean) => {
    setStemsActive(active);
  }, []);

  useEffect(() => {
    if (stemsActive) player?.pause();
  }, [stemsActive, player]);

  const seekToChart = (t: number) =>
    player?.seek(t + (data?.sync_offset_ms ?? 0) / 1000);

  const track = songInView(picked, data);

  return (
    <>
      <div className="masthead">
        <button
          className="wordmark"
          onClick={() => setPicked(null)}
          title="Back to your music"
        >
          Kord<span>.</span>
        </button>
        <SearchBar onPick={setPicked} />
      </div>

      {!picked && <Home onPick={setPicked} />}

      {track && (
        <main>
          <MoodRing stops={data?.palette ?? []}>
            <NowPlaying
              track={track}
              theory={data?.status === "done" ? data.theory : undefined}
              chordCount={data?.chart?.length ?? 0}
              player={player}
              playing={playing}
              currentTime={currentTime}
            />
          </MoodRing>

          {data && data.status !== "done" && (
            <AnalysisProgress status={data.status} error={data.error} />
          )}

          {data?.status === "done" && data.chart && data.theory && (
            <>
              {player && (
                <PlayAlong
                  chart={data.chart}
                  syncOffsetMs={data.sync_offset_ms ?? 0}
                  beats={data.beats ?? []}
                  currentTime={currentTime}
                />
              )}
              {!data.has_audio && (
                <p className="state detail" style={{ paddingTop: 0 }}>
                  Audio isn't stored for this song yet — re-analyse it to play along.
                </p>
              )}
              <SongMap
                sections={data.sections ?? []}
                now={chartTime(currentTime, data.sync_offset_ms ?? 0)}
                loop={loop}
                onSeek={seekToChart}
                onLoopChange={setLoop}
              />
              <div className="song-body">
                <TheoryPanel
                  theory={data.theory}
                  flags={data.flags ?? []}
                  tuning={data.tuning}
                />
              </div>
              <ChordSheet entries={data.chart} onSeek={seekToChart} />
              <StemMixer trackId={track.id} onActiveChange={handleStemsActive} />
            </>
          )}
        </main>
      )}
    </>
  );
}
