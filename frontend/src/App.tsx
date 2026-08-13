import { useEffect, useRef, useState } from "react";
import { getTrack, type TrackResponse, type TrackSummary } from "./api";
import { chartTime, loopTarget, type LoopRange } from "./chart";
import { usePlayhead } from "./hooks/usePlayhead";
import { createPlayer, type Player } from "./player";
import { AnalysisProgress } from "./components/AnalysisProgress";
import { ChordSheet } from "./components/ChordSheet";
import { MoodRing } from "./components/MoodRing";
import { PlayAlong } from "./components/PlayAlong";
import { SearchBar } from "./components/SearchBar";
import { SongMap } from "./components/SongMap";
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

  const seekToChart = (t: number) =>
    player?.seek(t + (data?.sync_offset_ms ?? 0) / 1000);

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
            <>
              {player && (
                <PlayAlong
                  player={player}
                  chart={data.chart}
                  syncOffsetMs={data.sync_offset_ms ?? 0}
                  beats={data.beats ?? []}
                  currentTime={currentTime}
                  playing={playing}
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
                <TheoryPanel theory={data.theory} flags={data.flags ?? []} />
              </div>
              <ChordSheet entries={data.chart} onSeek={seekToChart} />
            </>
          )}
        </main>
      )}
    </>
  );
}
