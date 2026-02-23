// API client — all calls use relative URLs (same origin as FastAPI)
import type {
  StatusResponse,
  TVStatusResponse,
  LibrariesResponse,
  ConfigResponse,
  LogsResponse,
  RunResponse,
  RunStatusResponse,
  ServiceName,
  AnimeScheduleResponse,
  TraktListsResponse,
  PlexShowsResponse,
  AflSearchResponse,
  AflEpisodesResponse,
  AddAnimeResponse,
  MappingErrorsResponse,
  FixMappingResponse,
  TitleMappingsResponse,
  NextAiringResponse,
  TraktDeviceCodeResponse,
  TraktDevicePollResponse,
  SetupResponse,
  PlexLibrariesSetupResponse,
} from "@/types/api";

async function apiFetch<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(path, init);
  if (!res.ok) {
    const text = await res.text().catch(() => res.statusText);
    throw new Error(`API error ${res.status}: ${text}`);
  }
  return res.json() as Promise<T>;
}

export const api = {
  getStatus: () => apiFetch<StatusResponse>("/api/status"),

  getTVStatus: () => apiFetch<TVStatusResponse>("/api/tv-status"),

  getNextAiring: () => apiFetch<NextAiringResponse>("/api/tv-status/next-airing"),

  getLibraries: () => apiFetch<LibrariesResponse>("/api/libraries"),

  getConfig: () => apiFetch<ConfigResponse>("/api/config"),

  updateConfig: (config: string) =>
    apiFetch<{ success: boolean }>("/api/config", {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ config }),
    }),

  getLogs: (service: ServiceName | "main", lines = 200) =>
    apiFetch<LogsResponse>(`/api/logs/${service}?lines=${lines}`),

  triggerRun: (service: ServiceName) =>
    apiFetch<RunResponse>(`/api/run/${service}`, { method: "POST" }),

  getRunStatus: (service: ServiceName) =>
    apiFetch<RunStatusResponse>(`/api/run/${service}/status`),

  setServiceEnabled: (service: ServiceName, enabled: boolean) =>
    apiFetch<{ success: boolean; service: string; enabled: boolean }>(
      `/api/services/${service}`,
      { method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ enabled }) },
    ),

  getAnimeSchedule: () => apiFetch<AnimeScheduleResponse>("/api/anime-schedule"),

  getTraktLists: () => apiFetch<TraktListsResponse>("/api/trakt/lists"),

  deleteTraktList: (listId: number) =>
    apiFetch<{ success: boolean }>(`/api/trakt/lists/${listId}`, { method: "DELETE" }),

  syncTraktCollections: () =>
    apiFetch<{ started: boolean; message?: string }>("/api/trakt/sync", { method: "POST" }),

  getSyncStatus: () => apiFetch<{ running: boolean }>("/api/trakt/sync/status"),

  getPlexShows: () => apiFetch<PlexShowsResponse>("/api/plex/shows"),

  triggerAnimeRun: (aflName: string) =>
    apiFetch<{ started: boolean; message?: string }>(
      `/api/run/anime/${encodeURIComponent(aflName)}`,
      { method: "POST" },
    ),

  getAnimeRunStatus: (aflName: string) =>
    apiFetch<{ afl_name: string; running: boolean }>(
      `/api/run/anime/${encodeURIComponent(aflName)}/status`,
    ),

  searchAfl: (q: string) =>
    apiFetch<AflSearchResponse>(`/api/afl/search?q=${encodeURIComponent(q)}`),

  getAflEpisodes: (aflName: string) =>
    apiFetch<AflEpisodesResponse>(`/api/afl/episodes/${encodeURIComponent(aflName)}`),

  addAnime: (aflName: string, plexName: string, addToSchedule: boolean) =>
    apiFetch<AddAnimeResponse>("/api/anime/add", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ afl_name: aflName, plex_name: plexName, add_to_schedule: addToSchedule }),
    }),

  removeFromSchedule: (aflName: string) =>
    apiFetch<{ success: boolean; afl_name: string }>(
      `/api/anime/schedule/${encodeURIComponent(aflName)}`,
      { method: "DELETE" },
    ),

  getMappingErrors: () => apiFetch<MappingErrorsResponse>("/api/mappings/errors"),

  fixMappings: (animeName: string, episodeType: string, mappings: Record<string, string>) =>
    apiFetch<FixMappingResponse>("/api/mappings/fix", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ anime_name: animeName, episode_type: episodeType, mappings }),
    }),

  getTitleMappings: () => apiFetch<TitleMappingsResponse>("/api/mappings/title"),

  updateTitleMapping: (animeName: string, plexTitle: string, traktTitle: string) =>
    apiFetch<FixMappingResponse>("/api/mappings/fix", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ anime_name: animeName, episode_type: "", mappings: { [plexTitle]: traktTitle } }),
    }),

  deleteTitleMapping: (animeName: string, plexTitle: string) =>
    apiFetch<{ success: boolean }>("/api/mappings/title", {
      method: "DELETE",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ anime_name: animeName, plex_title: plexTitle }),
    }),

  getPlexLibrariesForSetup: (url: string, token: string) =>
    apiFetch<PlexLibrariesSetupResponse>("/api/setup/plex/libraries", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ url, token }),
    }),

  getTraktDeviceCode: (clientId: string) =>
    apiFetch<TraktDeviceCodeResponse>("/api/setup/trakt/device-code", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ client_id: clientId }),
    }),

  pollTraktDeviceToken: (deviceCode: string, clientId: string, clientSecret: string) =>
    apiFetch<TraktDevicePollResponse>("/api/setup/trakt/device-poll", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ device_code: deviceCode, client_id: clientId, client_secret: clientSecret }),
    }),

  runSetup: (payload: object) =>
    apiFetch<SetupResponse>("/api/setup", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    }),
};
