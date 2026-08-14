import { stemUrl } from "./api";
import { elapsedAt, gainsFor } from "./stems";

export type StemPlayer = {
  names: string[];
  duration: number;
  playing(): boolean;
  elapsed(): number;
  play(from?: number): void;
  pause(): void;
  seek(seconds: number): void;
  applyGains(muted: ReadonlySet<string>, soloed: ReadonlySet<string>): void;
  destroy(): void;
};

/**
 * Average channels into one.
 *
 * Six stereo buffers cost roughly 508MB for a four minute song; mono halves
 * that, and practice does not need stereo.
 */
function toMono(context: AudioContext, buffer: AudioBuffer): AudioBuffer {
  if (buffer.numberOfChannels === 1) return buffer;
  const mono = context.createBuffer(1, buffer.length, buffer.sampleRate);
  const out = mono.getChannelData(0);
  for (let c = 0; c < buffer.numberOfChannels; c++) {
    const data = buffer.getChannelData(c);
    for (let i = 0; i < data.length; i++) {
      out[i] += data[i] / buffer.numberOfChannels;
    }
  }
  return mono;
}

export async function createStemPlayer(
  trackId: string, names: string[],
): Promise<StemPlayer> {
  const context = new AudioContext();
  const buffers = new Map<string, AudioBuffer>();
  const gains = new Map<string, GainNode>();

  await Promise.all(names.map(async (name) => {
    const response = await fetch(stemUrl(trackId, name));
    const decoded = await context.decodeAudioData(await response.arrayBuffer());
    buffers.set(name, toMono(context, decoded));
    const gain = context.createGain();
    gain.connect(context.destination);
    gains.set(name, gain);
  }));

  const duration = Math.max(...[...buffers.values()].map((b) => b.duration));
  let sources: AudioBufferSourceNode[] = [];
  let startedAt: number | null = null;
  let offset = 0;

  const stopSources = () => {
    for (const source of sources) {
      try {
        source.stop();
      } catch {
        /* already stopped */
      }
      source.disconnect();
    }
    sources = [];
  };

  const player: StemPlayer = {
    names,
    duration,
    playing: () => startedAt !== null,
    elapsed: () => elapsedAt(context.currentTime, startedAt, offset, duration),

    play(from) {
      if (startedAt !== null) return;
      if (from !== undefined) offset = from;
      void context.resume();
      // One start time for every source, so they cannot drift apart.
      const at = context.currentTime + 0.05;
      sources = names.map((name) => {
        const source = context.createBufferSource();
        source.buffer = buffers.get(name)!;
        source.connect(gains.get(name)!);
        source.start(at, offset);
        return source;
      });
      startedAt = at;
    },

    pause() {
      if (startedAt === null) return;
      offset = player.elapsed();
      stopSources();
      startedAt = null;
    },

    seek(seconds) {
      const wasPlaying = startedAt !== null;
      player.pause();
      offset = Math.min(duration, Math.max(0, seconds));
      if (wasPlaying) player.play();
    },

    applyGains(muted, soloed) {
      const values = gainsFor(names, muted, soloed);
      for (const [name, gain] of gains) {
        // A short ramp instead of a jump: an instantaneous gain change on a
        // running signal is audible as a click.
        gain.gain.setTargetAtTime(values[name], context.currentTime, 0.015);
      }
    },

    destroy() {
      stopSources();
      void context.close();
    },
  };

  player.applyGains(new Set(), new Set());
  return player;
}
