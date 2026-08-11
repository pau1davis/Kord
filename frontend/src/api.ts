export type TrackSummary = {
  id: string;
  title: string;
  artist: string;
  album: string | null;
  duration_ms: number;
  image: string | null;
};

export type ChartEntry = {
  start_s: number;
  end_s: number;
  label: string;
  quality: string;
  roman: string;
  hue: number;
  uncertain: boolean;
};

export type PaletteStop = { hue: number; weight: number };

export type Theory = {
  key: string;
  key_uncertain: boolean;
  tempo: number;
  scale: { notes: string[]; suggestions: string[] };
};

export type TrackStatus = "done" | "pending" | "failed" | "unavailable";

export type TrackResponse = {
  track: TrackSummary;
  status: TrackStatus;
  error?: string;
  chart?: ChartEntry[];
  palette?: PaletteStop[];
  flags?: string[];
  theory?: Theory;
  sync_offset_ms?: number;
};

async function json<T>(url: string, init?: RequestInit): Promise<T> {
  const response = await fetch(url, init);
  if (!response.ok) {
    throw new Error(`${response.status} ${response.statusText}`);
  }
  return (await response.json()) as T;
}

export const authStatus = () => json<{ authenticated: boolean }>("/api/auth/status");

export const searchTracks = (q: string) =>
  json<TrackSummary[]>(`/api/search?q=${encodeURIComponent(q)}`);

export const getTrack = (id: string) => json<TrackResponse>(`/api/track/${id}`);

export const requestAnalysis = (id: string) =>
  json<{ job_id: number }>(`/api/track/${id}/analyze`, { method: "POST" });
