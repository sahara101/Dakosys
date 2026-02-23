// API response types for DAKOSYS web dashboard

export interface ServiceStatus {
  enabled: boolean;
  running: boolean;
  next_run: string | null;
}

export interface StatusStats {
  total_shows: number;
  total_libraries: number;
  total_size_gb: number;
}

export interface StatusResponse {
  services: {
    anime_episode_type: ServiceStatus;
    tv_status_tracker: ServiceStatus;
    size_overlay: ServiceStatus;
  };
  stats: StatusStats;
  config_missing?: boolean;
}

export interface TVShow {
  title: string;
  status: string;
  date: string;
  text: string;
}

export interface TVStatusResponse {
  shows: TVShow[];
}

export interface LibraryItem {
  title: string;
  size_gb: number;
  episode_count?: number;
}

export interface Library {
  name: string;
  total_size_gb: number;
  item_count: number;
  episode_count: number | null;
  last_updated: string;
  items: LibraryItem[];
}

export interface LibrariesResponse {
  libraries: Library[];
}

export interface ConfigResponse {
  config: string;
  error?: string;
}

export interface LogsResponse {
  lines: string[];
  service: string;
}

export interface RunResponse {
  started: boolean;
  message: string;
}

export interface RunStatusResponse {
  service: string;
  running: boolean;
}

export type ServiceName = "anime_episode_type" | "tv_status_tracker" | "size_overlay";

export interface AnimeEntry {
  afl_name: string;
  display_name: string;
}

export interface AnimeScheduleResponse {
  anime: AnimeEntry[];
  count: number;
}

export interface TraktList {
  id: number;
  name: string;
  anime_name: string;
  plex_name: string;
  episode_type: "filler" | "manga canon" | "anime canon" | "mixed canon/filler";
  item_count: number;
}

export interface TraktListsResponse {
  lists: TraktList[];
  total: number;
  error: string | null;
  trakt_username?: string;
}

export interface PlexShowsResponse {
  shows: string[];
  error: string | null;
}

export interface AflSearchResponse {
  shows: string[];
  error: string | null;
}

export interface AflEpisodeCounts {
  [episodeType: string]: number;
}

export interface AflEpisodesResponse {
  afl_name: string;
  counts: AflEpisodeCounts;
  total: number;
  error: string | null;
}

export interface AddAnimeResponse {
  success: boolean;
  afl_name: string;
  plex_name: string;
}

export interface FailedEpisodeDetail {
  number: number | null;
  name: string;
}

export interface MappingError {
  anime_name: string;
  episode_type: string;
  plex_name: string;
  failed_episodes: string[];
  failed_episode_details: FailedEpisodeDetail[];
  details: string[];
  timestamp: string;
}

export interface MappingErrorsResponse {
  errors: MappingError[];
  count: number;
  error?: string;
}

export interface FixMappingResponse {
  success: boolean;
  saved: number;
}

export interface TitleMappingEntry {
  plex_title: string;
  trakt_title: string;
}

export interface TitleMappingGroup {
  anime_name: string;
  matches: TitleMappingEntry[];
}

export interface TitleMappingsResponse {
  mappings: TitleMappingGroup[];
  count: number;
  error?: string;
}

export interface NextAiringShow {
  rank: number;
  title: string;
  trakt_slug: string;
  trakt_id: number | null;
  poster_url: string | null;
  status: string;
  date: string;
  text: string;
}

export interface NextAiringResponse {
  shows: NextAiringShow[];
  count: number;
  tmdb_key_missing?: boolean;
  error?: string;
}

export interface PlexLibrarySection {
  title: string;
  type: "show" | "movie";
}

export interface PlexLibrariesSetupResponse {
  libraries: PlexLibrarySection[];
  error: string | null;
}

export interface TraktDeviceCodeResponse {
  device_code: string;
  user_code: string;
  verification_url: string;
  expires_in: number;
  interval: number;
}

export interface TraktDevicePollResponse {
  authorized: boolean;
  pending?: boolean;
  access_token?: string;
  error?: string;
}

export interface SetupResponse {
  success: boolean;
}
