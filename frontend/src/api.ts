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

export type SongSection = { start_s: number; end_s: number; label: string };

export type TrackResponse = {
  track: TrackSummary;
  status: TrackStatus;
  error?: string;
  chart?: ChartEntry[];
  palette?: PaletteStop[];
  flags?: string[];
  theory?: Theory;
  sync_offset_ms?: number;
  sections?: SongSection[];
  has_audio?: boolean;
  beats?: number[];
};

export class ApiError extends Error {
  status: number;

  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

async function json<T>(url: string, init?: RequestInit): Promise<T> {
  let response: Response;
  try {
    response = await fetch(url, init);
  } catch {
    // Only a genuine transport failure lands here — the server really is down.
    throw new ApiError(0, "Can't reach the Kord server. Is it running?");
  }
  if (!response.ok) {
    // Surface what the backend said. It passes Spotify's own wording through,
    // which is far more useful than a status code.
    const detail = await response
      .json()
      .then((body) => body?.detail)
      .catch(() => null);
    throw new ApiError(response.status, detail || `Request failed (${response.status})`);
  }
  return (await response.json()) as T;
}

export const authStatus = () => json<{ authenticated: boolean }>("/api/auth/status");

export const searchTracks = (q: string) =>
  json<TrackSummary[]>(`/api/search?q=${encodeURIComponent(q)}`);

export const getTrack = (id: string) => json<TrackResponse>(`/api/track/${id}`);

export const requestAnalysis = (id: string) =>
  json<{ job_id: number }>(`/api/track/${id}/analyze`, { method: "POST" });

export type StemState =
  | "none" | "pending" | "running" | "done" | "failed" | "unavailable";

export type StemStatus = {
  status: StemState;
  error: string | null;
  progress: number;
  available: string[];
};

export const getStems = (id: string) =>
  json<StemStatus>(`/api/track/${id}/stems`);

export const requestStems = (id: string) =>
  json<{ job_id: number; status: string }>(
    `/api/track/${id}/stems`, { method: "POST" });

export const stemUrl = (id: string, stem: string) =>
  `/api/track/${id}/stems/${stem}`;

export type Taste = {
  palette: PaletteStop[];
  analyzed: number;
  total: number;
};

export const getTopTracks = () => json<TrackSummary[]>("/api/me/top");
export const getTaste = () => json<Taste>("/api/me/taste");
export const analyzeTop = () =>
  json<{ queued: number; total: number }>(
    "/api/me/top/analyze", { method: "POST" });

export type LibraryKey = { key: string; count: number };

export type Library = {
  analyzed: number;
  with_audio: number;
  with_stems: number;
  keys: LibraryKey[];
  tempo: { min: number; median: number; max: number } | null;
  resume: {
    id: string; title: string; artist: string;
    key: string | null; tempo: number | null;
  } | null;
};

export const getLibrary = () => json<Library>("/api/me/library");
export const getRecent = () => json<TrackSummary[]>("/api/me/recent");
