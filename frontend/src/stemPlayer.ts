import { stemUrl } from "./api";
import { correlation, elapsedAt, gainsFor, orderParts, partNames } from "./stems";

export type StemPlayer = {
  names: string[];
  duration: number;
  playing(): boolean;
  elapsed(): number;
  play(from?: number): void;
  pause(): void;
  seek(seconds: number): void;
  applyGains(enabled: ReadonlySet<string>): void;
  destroy(): void;
};

/**
 * Average channels into one.
 *
 * Six stereo buffers cost roughly 508MB for a four minute song; mono halves
 * that, and practice does not need stereo. A double-tracked guitar is the one
 * exception — its channels are kept as two separate mono parts, so it costs
 * what it did before the fold, and the total is seven mono buffers rather
 * than six.
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

/** One channel on its own, as its own mono buffer. */
function channelOf(
  context: AudioContext, buffer: AudioBuffer, channel: number,
): AudioBuffer {
  const one = context.createBuffer(1, buffer.length, buffer.sampleRate);
  one.getChannelData(0).set(buffer.getChannelData(channel));
  return one;
}

/**
 * Split a decoded stem into the parts you can actually hear separately.
 *
 * A doubled rhythm guitar is two performances hard-panned apart, so the takes
 * are already in separate channels — mixing them to mono was throwing the
 * second guitarist away. When the channels turn out to be one take, this falls
 * back to the mono fold and nothing is offered that isn't there.
 */
function partsOf(
  context: AudioContext, stem: string, decoded: AudioBuffer,
): [string, AudioBuffer][] {
  const corr = decoded.numberOfChannels >= 2
    ? correlation(decoded.getChannelData(0), decoded.getChannelData(1))
    : 1;
  const names = partNames(stem, decoded.numberOfChannels, corr);
  if (names.length === 1) return [[names[0], toMono(context, decoded)]];
  return names.map(
    (name, channel) => [name, channelOf(context, decoded, channel)]);
}

export async function createStemPlayer(
  trackId: string, names: string[], onEnded?: () => void,
): Promise<StemPlayer> {
  const context = new AudioContext();
  const buffers = new Map<string, AudioBuffer>();
  const gains = new Map<string, GainNode>();

  await Promise.all(names.map(async (stem) => {
    const response = await fetch(stemUrl(trackId, stem));
    const decoded = await context.decodeAudioData(await response.arrayBuffer());
    for (const [part, buffer] of partsOf(context, stem, decoded)) {
      buffers.set(part, buffer);
      const gain = context.createGain();
      gain.connect(context.destination);
      gains.set(part, gain);
    }
  }));

  // Not the stems that were asked for: a double-tracked guitar became two
  // parts, so the fetch list and the fader list are no longer the same thing.
  // Ordered here because Promise.all finished them in whatever order they
  // decoded.
  const parts = orderParts([...buffers.keys()]);
  const duration = Math.max(...[...buffers.values()].map((b) => b.duration));
  let sources: AudioBufferSourceNode[] = [];
  let startedAt: number | null = null;
  let offset = 0;
  // Bumped on every start and stop. `stop()` schedules its ended event rather
  // than firing it, so a seek — which pauses then plays — would otherwise have
  // the old run's handler arrive after the new one started and kill it.
  let run = 0;

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
    names: parts,
    duration,
    playing: () => startedAt !== null,
    elapsed: () => elapsedAt(context.currentTime, startedAt, offset, duration),

    play(from) {
      if (startedAt !== null) return;
      if (from !== undefined) offset = from;
      // Playing again after the end should start the song over, not start at
      // the end and produce silence.
      if (offset >= duration - 0.05) offset = 0;
      void context.resume();
      // One start time for every source, so they cannot drift apart.
      const at = context.currentTime + 0.05;
      sources = parts.map((name) => {
        const source = context.createBufferSource();
        source.buffer = buffers.get(name)!;
        source.connect(gains.get(name)!);
        source.start(at, offset);
        return source;
      });
      startedAt = at;

      // Web Audio fires nothing when playback simply runs out, so without this
      // the transport stays stuck reading "Pause" over a finished song.
      const thisRun = ++run;
      sources[0].onended = () => {
        if (thisRun !== run) return;  // superseded by a later play or pause
        stopSources();
        startedAt = null;
        offset = duration;
        onEnded?.();
      };
    },

    pause() {
      if (startedAt === null) return;
      run++;
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

    applyGains(enabled) {
      const values = gainsFor(parts, enabled);
      for (const [name, gain] of gains) {
        // A short ramp instead of a jump: an instantaneous gain change on a
        // running signal is audible as a click.
        gain.gain.setTargetAtTime(values[name], context.currentTime, 0.015);
      }
    },

    destroy() {
      run++;
      stopSources();
      void context.close();
    },
  };

  // Everything on to start with: the song as recorded, before you take it apart.
  player.applyGains(new Set(parts));
  return player;
}
