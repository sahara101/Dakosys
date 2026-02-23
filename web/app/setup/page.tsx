"use client";

import { useState, useEffect, useRef, useCallback } from "react";
import { useRouter } from "next/navigation";
import { Button, Input, Switch, Spinner, Chip } from "@nextui-org/react";
import { api } from "@/lib/api";
import type { PlexLibrarySection } from "@/types/api";

type ScheduleType = "daily" | "hourly" | "weekly" | "monthly";

interface ServiceSchedule {
  enabled: boolean;
  schedule_type: ScheduleType;
  schedule_times: string[];
  schedule_minute: number;
  schedule_days: string[];
  schedule_time: string;
  schedule_dates: number[];
  libraries?: string[];
  movie_libraries?: string[];
  tv_libraries?: string[];
  anime_libraries?: string[];
}

interface WizardState {
  timezone: string;
  date_format: "DD/MM" | "MM/DD";
  plex_url: string;
  plex_token: string;
  anime_libs: string[];
  tv_libs: string[];
  movie_libs: string[];
  anime_episode_type: ServiceSchedule;
  tv_status_tracker: ServiceSchedule;
  size_overlay: ServiceSchedule & { movie_libraries: string[]; tv_libraries: string[]; anime_libraries: string[] };
  kometa_yaml_output: string;
  kometa_collections: string;
  kometa_font_dir: string;
  kometa_asset_dir: string;
  tmdb_api_key: string;
  trakt_client_id: string;
  trakt_client_secret: string;
  trakt_username: string;
  trakt_authed: boolean;
  notif_enabled: boolean;
  discord_webhook: string;
  list_privacy: "private" | "public";
}

const defaultSchedule = (defaults: Partial<ServiceSchedule> = {}): ServiceSchedule => ({
  enabled: false,
  schedule_type: "daily",
  schedule_times: ["03:00"],
  schedule_minute: 0,
  schedule_days: ["monday"],
  schedule_time: "03:00",
  schedule_dates: [1],
  libraries: [],
  ...defaults,
});

const TOTAL_STEPS = 8;

function LibTagInput({
  label,
  placeholder,
  values,
  onChange,
}: {
  label: string;
  placeholder: string;
  values: string[];
  onChange: (v: string[]) => void;
}) {
  const [input, setInput] = useState("");

  const add = () => {
    const trimmed = input.trim();
    if (trimmed && !values.includes(trimmed)) {
      onChange([...values, trimmed]);
    }
    setInput("");
  };

  return (
    <div>
      <p className="text-sm text-zinc-400 mb-1">{label}</p>
      <div className="flex gap-2 mb-2">
        <Input
          size="sm"
          placeholder={placeholder}
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => { if (e.key === "Enter") { e.preventDefault(); add(); } }}
          classNames={{ input: "text-white", inputWrapper: "bg-zinc-800 border-zinc-700" }}
        />
        <Button size="sm" variant="bordered" onPress={add}>Add</Button>
      </div>
      <div className="flex flex-wrap gap-1">
        {values.map((v) => (
          <Chip
            key={v}
            size="sm"
            onClose={() => onChange(values.filter((x) => x !== v))}
            classNames={{ base: "bg-violet-900/40 border-violet-700/50 border", content: "text-violet-200 text-xs" }}
          >
            {v}
          </Chip>
        ))}
      </div>
    </div>
  );
}

function ScheduleConfig({
  value,
  onChange,
}: {
  value: ServiceSchedule;
  onChange: (v: ServiceSchedule) => void;
}) {
  const update = (patch: Partial<ServiceSchedule>) => onChange({ ...value, ...patch });
  const days = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"];

  return (
    <div className="space-y-3 pl-4 border-l border-zinc-700">
      <div>
        <p className="text-xs text-zinc-500 mb-1">Schedule type</p>
        <div className="flex gap-2 flex-wrap">
          {(["daily", "hourly", "weekly", "monthly"] as ScheduleType[]).map((t) => (
            <button
              key={t}
              onClick={() => update({ schedule_type: t })}
              className={`px-3 py-1 rounded text-xs font-medium border transition-all ${
                value.schedule_type === t
                  ? "bg-violet-600 border-violet-500 text-white"
                  : "bg-zinc-800 border-zinc-700 text-zinc-400 hover:border-zinc-500"
              }`}
            >
              {t.charAt(0).toUpperCase() + t.slice(1)}
            </button>
          ))}
        </div>
      </div>

      {value.schedule_type === "daily" && (
        <Input
          size="sm"
          label="Time (HH:MM)"
          value={value.schedule_times[0]}
          onChange={(e) => update({ schedule_times: [e.target.value] })}
          classNames={{ input: "text-white", inputWrapper: "bg-zinc-800 border-zinc-700" }}
        />
      )}
      {value.schedule_type === "hourly" && (
        <Input
          size="sm"
          type="number"
          label="Minute (0-59)"
          value={String(value.schedule_minute)}
          onChange={(e) => update({ schedule_minute: parseInt(e.target.value) || 0 })}
          classNames={{ input: "text-white", inputWrapper: "bg-zinc-800 border-zinc-700" }}
        />
      )}
      {value.schedule_type === "weekly" && (
        <div className="space-y-2">
          <div className="flex gap-1 flex-wrap">
            {days.map((d) => (
              <button
                key={d}
                onClick={() => {
                  const cur = value.schedule_days;
                  update({ schedule_days: cur.includes(d) ? cur.filter((x) => x !== d) : [...cur, d] });
                }}
                className={`px-2 py-1 rounded text-xs border transition-all ${
                  value.schedule_days.includes(d)
                    ? "bg-violet-600 border-violet-500 text-white"
                    : "bg-zinc-800 border-zinc-700 text-zinc-400"
                }`}
              >
                {d.slice(0, 3)}
              </button>
            ))}
          </div>
          <Input
            size="sm"
            label="Time (HH:MM)"
            value={value.schedule_time}
            onChange={(e) => update({ schedule_time: e.target.value })}
            classNames={{ input: "text-white", inputWrapper: "bg-zinc-800 border-zinc-700" }}
          />
        </div>
      )}
      {value.schedule_type === "monthly" && (
        <div className="space-y-2">
          <Input
            size="sm"
            type="number"
            label="Day of month (1-31)"
            value={String(value.schedule_dates[0])}
            onChange={(e) => update({ schedule_dates: [parseInt(e.target.value) || 1] })}
            classNames={{ input: "text-white", inputWrapper: "bg-zinc-800 border-zinc-700" }}
          />
          <Input
            size="sm"
            label="Time (HH:MM)"
            value={value.schedule_time}
            onChange={(e) => update({ schedule_time: e.target.value })}
            classNames={{ input: "text-white", inputWrapper: "bg-zinc-800 border-zinc-700" }}
          />
        </div>
      )}
    </div>
  );
}

export default function SetupPage() {
  const router = useRouter();
  const [step, setStep] = useState(1);
  const [saving, setSaving] = useState(false);
  const [saveError, setSaveError] = useState<string | null>(null);

  const [traktDeviceInfo, setTraktDeviceInfo] = useState<{
    device_code: string; user_code: string; verification_url: string; interval: number; expires_in: number;
  } | null>(null);
  const [traktPolling, setTraktPolling] = useState(false);
  const [traktError, setTraktError] = useState<string | null>(null);
  const pollIntervalRef = useRef<ReturnType<typeof setInterval> | null>(null);

  type LibAssignment = { asAnime: boolean; asTV: boolean; asMovie: boolean };
  const [fetchedLibs, setFetchedLibs] = useState<PlexLibrarySection[] | null>(null);
  const [libsLoading, setLibsLoading] = useState(false);
  const [libsFetchError, setLibsFetchError] = useState<string | null>(null);
  const [libAssignments, setLibAssignments] = useState<Record<string, LibAssignment>>({});

  const [w, setW] = useState<WizardState>({
    timezone: "UTC",
    date_format: "DD/MM",
    plex_url: "http://localhost:32400",
    plex_token: "",
    anime_libs: [],
    tv_libs: [],
    movie_libs: [],
    anime_episode_type: defaultSchedule({ enabled: false, schedule_times: ["03:00"] }),
    tv_status_tracker: defaultSchedule({ enabled: false, schedule_times: ["04:00"] }),
    size_overlay: {
      ...defaultSchedule({ enabled: false, schedule_times: ["03:30"] }),
      movie_libraries: [],
      tv_libraries: [],
      anime_libraries: [],
    },
    kometa_yaml_output: "/kometa/config/overlays",
    kometa_collections: "/kometa/config/collections",
    kometa_font_dir: "config/fonts",
    kometa_asset_dir: "config/assets",
    tmdb_api_key: "",
    trakt_client_id: "",
    trakt_client_secret: "",
    trakt_username: "",
    trakt_authed: false,
    notif_enabled: false,
    discord_webhook: "",
    list_privacy: "private",
  });

  const update = (patch: Partial<WizardState>) => setW((prev) => ({ ...prev, ...patch }));

  const applyAssignments = useCallback((assignments: Record<string, LibAssignment>) => {
    const anime_libs = Object.entries(assignments).filter(([, a]) => a.asAnime).map(([t]) => t);
    const tv_libs    = Object.entries(assignments).filter(([, a]) => a.asTV).map(([t]) => t);
    const movie_libs = Object.entries(assignments).filter(([, a]) => a.asMovie).map(([t]) => t);
    update({ anime_libs, tv_libs, movie_libs });
  }, []);

  const toggleAssignment = (title: string, key: keyof LibAssignment) => {
    setLibAssignments((prev) => {
      const cur = prev[title] ?? { asAnime: false, asTV: false, asMovie: false };
      const next = { ...prev, [title]: { ...cur, [key]: !cur[key] } };
      applyAssignments(next);
      return next;
    });
  };

  const fetchPlexLibraries = useCallback(async () => {
    if (!w.plex_url || !w.plex_token) return;
    setLibsLoading(true);
    setLibsFetchError(null);
    try {
      const res = await api.getPlexLibrariesForSetup(w.plex_url, w.plex_token);
      if (res.error) {
        setLibsFetchError(res.error);
      } else {
        setFetchedLibs(res.libraries);
        const defaults: Record<string, LibAssignment> = {};
        for (const lib of res.libraries) {
          const lowerTitle = lib.title.toLowerCase();
          defaults[lib.title] = {
            asAnime: lib.type === "show" && lowerTitle.includes("anime"),
            asTV:    lib.type === "show" && !lowerTitle.includes("anime"),
            asMovie: lib.type === "movie",
          };
        }
        setLibAssignments(defaults);
        applyAssignments(defaults);
      }
    } catch (e: unknown) {
      setLibsFetchError(e instanceof Error ? e.message : "Failed to connect to Plex");
    } finally {
      setLibsLoading(false);
    }
  }, [w.plex_url, w.plex_token, applyAssignments]);

  useEffect(() => {
    if (step === 3 && fetchedLibs === null && !libsLoading) {
      fetchPlexLibraries();
    }
  }, [step, fetchedLibs, libsLoading, fetchPlexLibraries]);

  useEffect(() => {
    return () => { if (pollIntervalRef.current) clearInterval(pollIntervalRef.current); };
  }, []);

  const startTraktAuth = async () => {
    setTraktError(null);
    try {
      const res = await api.getTraktDeviceCode(w.trakt_client_id);
      setTraktDeviceInfo(res);
      setTraktPolling(true);

      pollIntervalRef.current = setInterval(async () => {
        try {
          const poll = await api.pollTraktDeviceToken(res.device_code, w.trakt_client_id, w.trakt_client_secret);
          if (poll.authorized) {
            clearInterval(pollIntervalRef.current!);
            setTraktPolling(false);
            update({ trakt_authed: true });
          } else if (!poll.pending) {
            clearInterval(pollIntervalRef.current!);
            setTraktPolling(false);
            setTraktError(poll.error ?? "Authorization failed or expired");
          }
        } catch {
        }
      }, (res.interval + 1) * 1000);

      setTimeout(() => {
        if (pollIntervalRef.current) {
          clearInterval(pollIntervalRef.current);
          setTraktPolling(false);
        }
      }, res.expires_in * 1000);
    } catch (e: unknown) {
      setTraktError(e instanceof Error ? e.message : "Failed to get device code");
    }
  };

  const handleSave = async () => {
    setSaving(true);
    setSaveError(null);
    try {
      const payload = {
        timezone: w.timezone,
        date_format: w.date_format,
        plex_url: w.plex_url,
        plex_token: w.plex_token,
        libraries: { anime: w.anime_libs, tv: w.tv_libs, movie: w.movie_libs },
        services: {
          anime_episode_type: {
            enabled: w.anime_episode_type.enabled,
            libraries: w.anime_episode_type.libraries ?? w.anime_libs,
            schedule_type: w.anime_episode_type.schedule_type,
            schedule_times: w.anime_episode_type.schedule_times,
            schedule_minute: w.anime_episode_type.schedule_minute,
            schedule_days: w.anime_episode_type.schedule_days,
            schedule_time: w.anime_episode_type.schedule_time,
            schedule_dates: w.anime_episode_type.schedule_dates,
          },
          tv_status_tracker: {
            enabled: w.tv_status_tracker.enabled,
            libraries: w.tv_status_tracker.libraries ?? [],
            schedule_type: w.tv_status_tracker.schedule_type,
            schedule_times: w.tv_status_tracker.schedule_times,
            schedule_minute: w.tv_status_tracker.schedule_minute,
            schedule_days: w.tv_status_tracker.schedule_days,
            schedule_time: w.tv_status_tracker.schedule_time,
            schedule_dates: w.tv_status_tracker.schedule_dates,
          },
          size_overlay: {
            enabled: w.size_overlay.enabled,
            movie_libraries: w.size_overlay.movie_libraries,
            tv_libraries: w.size_overlay.tv_libraries,
            anime_libraries: w.size_overlay.anime_libraries,
            schedule_type: w.size_overlay.schedule_type,
            schedule_times: w.size_overlay.schedule_times,
            schedule_minute: w.size_overlay.schedule_minute,
            schedule_days: w.size_overlay.schedule_days,
            schedule_time: w.size_overlay.schedule_time,
            schedule_dates: w.size_overlay.schedule_dates,
          },
        },
        kometa: {
          yaml_output_dir: w.kometa_yaml_output,
          collections_dir: w.kometa_collections,
          font_directory: w.kometa_font_dir,
          asset_directory: w.kometa_asset_dir,
        },
        trakt: {
          client_id: w.trakt_client_id,
          client_secret: w.trakt_client_secret,
          username: w.trakt_username,
          redirect_uri: "urn:ietf:wg:oauth:2.0:oob",
        },
        notifications: {
          enabled: w.notif_enabled,
          discord_webhook: w.discord_webhook,
        },
        list_privacy: w.list_privacy,
        tmdb_api_key: w.tmdb_api_key,
      };
      await api.runSetup(payload);
      router.replace("/dashboard");
    } catch (e: unknown) {
      setSaveError(e instanceof Error ? e.message : "Setup failed");
    } finally {
      setSaving(false);
    }
  };

  const COMMON_TIMEZONES = [
    "UTC", "America/New_York", "America/Chicago", "America/Denver", "America/Los_Angeles",
    "Europe/London", "Europe/Paris", "Europe/Berlin", "Europe/Amsterdam",
    "Asia/Tokyo", "Asia/Seoul", "Asia/Singapore", "Australia/Sydney",
  ];

  const stepContent = () => {
    switch (step) {
      case 1:
        return (
          <div className="space-y-6">
            <div>
              <h2 className="text-xl font-semibold text-white mb-1">Basic Settings</h2>
              <p className="text-zinc-400 text-sm">Timezone and display preferences</p>
            </div>

            <div className="space-y-4">
              <div>
                <label className="text-sm text-zinc-400 block mb-1">Timezone</label>
                <Input
                  value={w.timezone}
                  onChange={(e) => update({ timezone: e.target.value })}
                  placeholder="e.g. Europe/London"
                  classNames={{ input: "text-white", inputWrapper: "bg-zinc-800 border-zinc-700" }}
                />
                <div className="flex flex-wrap gap-1 mt-2">
                  {COMMON_TIMEZONES.map((tz) => (
                    <button
                      key={tz}
                      onClick={() => update({ timezone: tz })}
                      className={`text-xs px-2 py-1 rounded border transition-all ${
                        w.timezone === tz
                          ? "bg-violet-600/30 border-violet-500 text-violet-300"
                          : "bg-zinc-800/60 border-zinc-700 text-zinc-500 hover:text-zinc-300"
                      }`}
                    >
                      {tz}
                    </button>
                  ))}
                </div>
              </div>

              <div>
                <label className="text-sm text-zinc-400 block mb-2">Date format</label>
                <div className="flex gap-3">
                  {(["DD/MM", "MM/DD"] as const).map((fmt) => (
                    <button
                      key={fmt}
                      onClick={() => update({ date_format: fmt })}
                      className={`px-4 py-2 rounded-lg border text-sm font-medium transition-all ${
                        w.date_format === fmt
                          ? "bg-violet-600 border-violet-500 text-white"
                          : "bg-zinc-800 border-zinc-700 text-zinc-400 hover:border-zinc-500"
                      }`}
                    >
                      {fmt}
                    </button>
                  ))}
                </div>
              </div>
            </div>
          </div>
        );

      case 2:
        return (
          <div className="space-y-6">
            <div>
              <h2 className="text-xl font-semibold text-white mb-1">Plex Connection</h2>
              <p className="text-zinc-400 text-sm">
                Your Plex server URL and authentication token.{" "}
                <a
                  href="https://support.plex.tv/articles/204059436-finding-an-authentication-token/"
                  target="_blank"
                  rel="noopener noreferrer"
                  className="text-violet-400 hover:text-violet-300"
                >
                  How to find your token
                </a>
              </p>
            </div>
            <div className="space-y-4">
              <Input
                label="Plex server URL"
                value={w.plex_url}
                onChange={(e) => update({ plex_url: e.target.value })}
                placeholder="http://localhost:32400"
                classNames={{ input: "text-white", inputWrapper: "bg-zinc-800 border-zinc-700", label: "text-zinc-400" }}
              />
              <Input
                label="Plex authentication token"
                value={w.plex_token}
                onChange={(e) => update({ plex_token: e.target.value })}
                type="password"
                classNames={{ input: "text-white", inputWrapper: "bg-zinc-800 border-zinc-700", label: "text-zinc-400" }}
              />
            </div>
          </div>
        );

      case 3:
        return (
          <div className="space-y-6">
            <div>
              <h2 className="text-xl font-semibold text-white mb-1">Plex Libraries</h2>
              <p className="text-zinc-400 text-sm">
                Select which libraries to use and assign their type. Show libraries can be Anime, TV, or both.
              </p>
            </div>

            {libsLoading && (
              <div className="flex items-center gap-3 text-zinc-400 text-sm py-6 justify-center">
                <Spinner size="sm" color="secondary" />
                Connecting to Plex…
              </div>
            )}

            {libsFetchError && (
              <div className="space-y-3">
                <div className="bg-red-950/40 border border-red-800 rounded-lg p-3 text-sm text-red-400">
                  Could not reach Plex: {libsFetchError}
                </div>
                <Button size="sm" variant="bordered" onPress={fetchPlexLibraries} className="border-zinc-700 text-zinc-400">
                  Retry
                </Button>
                {/* Manual fallback */}
                <div className="space-y-4 pt-2">
                  <LibTagInput label="Anime libraries" placeholder="Anime" values={w.anime_libs} onChange={(v) => update({ anime_libs: v })} />
                  <LibTagInput label="TV show libraries" placeholder="TV Shows" values={w.tv_libs} onChange={(v) => update({ tv_libs: v })} />
                  <LibTagInput label="Movie libraries" placeholder="Movies" values={w.movie_libs} onChange={(v) => update({ movie_libs: v })} />
                </div>
              </div>
            )}

            {fetchedLibs && !libsLoading && (
              <div className="space-y-3">
                {fetchedLibs.map((lib) => {
                  const a = libAssignments[lib.title] ?? { asAnime: false, asTV: false, asMovie: false };
                  return (
                    <div
                      key={lib.title}
                      className="flex items-center justify-between bg-zinc-900 border border-zinc-800 rounded-lg px-4 py-3"
                    >
                      <div className="flex items-center gap-3">
                        <span className="text-lg">{lib.type === "movie" ? "🎬" : "📺"}</span>
                        <div>
                          <p className="text-white text-sm font-medium">{lib.title}</p>
                          <p className="text-zinc-500 text-xs capitalize">{lib.type === "show" ? "TV/Show" : "Movie"}</p>
                        </div>
                      </div>
                      <div className="flex gap-2">
                        {lib.type === "show" ? (
                          <>
                            <button
                              onClick={() => toggleAssignment(lib.title, "asAnime")}
                              className={`px-3 py-1 text-xs rounded-full border font-medium transition-all ${
                                a.asAnime
                                  ? "bg-violet-600 border-violet-500 text-white"
                                  : "bg-zinc-800 border-zinc-700 text-zinc-400 hover:border-zinc-500"
                              }`}
                            >
                              Anime
                            </button>
                            <button
                              onClick={() => toggleAssignment(lib.title, "asTV")}
                              className={`px-3 py-1 text-xs rounded-full border font-medium transition-all ${
                                a.asTV
                                  ? "bg-blue-600 border-blue-500 text-white"
                                  : "bg-zinc-800 border-zinc-700 text-zinc-400 hover:border-zinc-500"
                              }`}
                            >
                              TV Shows
                            </button>
                          </>
                        ) : (
                          <button
                            onClick={() => toggleAssignment(lib.title, "asMovie")}
                            className={`px-3 py-1 text-xs rounded-full border font-medium transition-all ${
                              a.asMovie
                                ? "bg-amber-600 border-amber-500 text-white"
                                : "bg-zinc-800 border-zinc-700 text-zinc-400 hover:border-zinc-500"
                            }`}
                          >
                            Movies
                          </button>
                        )}
                      </div>
                    </div>
                  );
                })}

                <div className="flex items-center justify-between pt-1">
                  <p className="text-zinc-600 text-xs">
                    {w.anime_libs.length > 0 && `Anime: ${w.anime_libs.join(", ")} · `}
                    {w.tv_libs.length > 0 && `TV: ${w.tv_libs.join(", ")} · `}
                    {w.movie_libs.length > 0 && `Movies: ${w.movie_libs.join(", ")}`}
                  </p>
                  <Button size="sm" variant="light" onPress={fetchPlexLibraries} className="text-zinc-500">
                    Refresh
                  </Button>
                </div>
              </div>
            )}
          </div>
        );

      case 4:
        return (
          <div className="space-y-6">
            <div>
              <h2 className="text-xl font-semibold text-white mb-1">Services</h2>
              <p className="text-zinc-400 text-sm">Enable the services you want to use and configure their schedules.</p>
            </div>

            {/* Anime Episode Type */}
            <div className="bg-zinc-900 rounded-lg p-4 border border-zinc-800 space-y-4">
              <div className="flex items-center justify-between">
                <div>
                  <p className="text-white font-medium">Anime Episode Type</p>
                  <p className="text-zinc-500 text-xs">Creates Trakt lists by episode type (filler, canon, etc.)</p>
                </div>
                <Switch
                  isSelected={w.anime_episode_type.enabled}
                  onValueChange={(v) => update({ anime_episode_type: { ...w.anime_episode_type, enabled: v } })}
                  color="secondary"
                />
              </div>
              {w.anime_episode_type.enabled && (
                <>
                  <div>
                    <p className="text-xs text-zinc-500 mb-1">Anime libraries to scan</p>
                    <div className="flex flex-wrap gap-1">
                      {w.anime_libs.map((lib) => (
                        <button
                          key={lib}
                          onClick={() => {
                            const cur = w.anime_episode_type.libraries ?? [];
                            update({ anime_episode_type: { ...w.anime_episode_type, libraries: cur.includes(lib) ? cur.filter((x) => x !== lib) : [...cur, lib] } });
                          }}
                          className={`px-2 py-1 text-xs rounded border transition-all ${
                            (w.anime_episode_type.libraries ?? []).includes(lib)
                              ? "bg-violet-600/30 border-violet-500 text-violet-200"
                              : "bg-zinc-800 border-zinc-700 text-zinc-400"
                          }`}
                        >
                          {lib}
                        </button>
                      ))}
                      {w.anime_libs.length === 0 && <p className="text-zinc-600 text-xs">Add anime libraries in step 3</p>}
                    </div>
                  </div>
                  <ScheduleConfig
                    value={w.anime_episode_type}
                    onChange={(v) => update({ anime_episode_type: v })}
                  />
                </>
              )}
            </div>

            {/* TV Status Tracker */}
            <div className="bg-zinc-900 rounded-lg p-4 border border-zinc-800 space-y-4">
              <div className="flex items-center justify-between">
                <div>
                  <p className="text-white font-medium">TV/Anime Status Tracker</p>
                  <p className="text-zinc-500 text-xs">Kometa overlays for airing status, finales, etc.</p>
                </div>
                <Switch
                  isSelected={w.tv_status_tracker.enabled}
                  onValueChange={(v) => update({ tv_status_tracker: { ...w.tv_status_tracker, enabled: v } })}
                  color="secondary"
                />
              </div>
              {w.tv_status_tracker.enabled && (
                <>
                  <div>
                    <p className="text-xs text-zinc-500 mb-1">Libraries to scan</p>
                    <div className="flex flex-wrap gap-1">
                      {[...w.anime_libs, ...w.tv_libs].map((lib) => (
                        <button
                          key={lib}
                          onClick={() => {
                            const cur = w.tv_status_tracker.libraries ?? [];
                            update({ tv_status_tracker: { ...w.tv_status_tracker, libraries: cur.includes(lib) ? cur.filter((x) => x !== lib) : [...cur, lib] } });
                          }}
                          className={`px-2 py-1 text-xs rounded border transition-all ${
                            (w.tv_status_tracker.libraries ?? []).includes(lib)
                              ? "bg-violet-600/30 border-violet-500 text-violet-200"
                              : "bg-zinc-800 border-zinc-700 text-zinc-400"
                          }`}
                        >
                          {lib}
                        </button>
                      ))}
                    </div>
                  </div>
                  <ScheduleConfig
                    value={w.tv_status_tracker}
                    onChange={(v) => update({ tv_status_tracker: v })}
                  />
                </>
              )}
            </div>

            {/* Size Overlay */}
            <div className="bg-zinc-900 rounded-lg p-4 border border-zinc-800 space-y-4">
              <div className="flex items-center justify-between">
                <div>
                  <p className="text-white font-medium">Size Overlay</p>
                  <p className="text-zinc-500 text-xs">Overlay file sizes on movies and shows</p>
                </div>
                <Switch
                  isSelected={w.size_overlay.enabled}
                  onValueChange={(v) => update({ size_overlay: { ...w.size_overlay, enabled: v } })}
                  color="secondary"
                />
              </div>
              {w.size_overlay.enabled && (
                <>
                  <div className="space-y-2">
                    {w.movie_libs.length > 0 && (
                      <div>
                        <p className="text-xs text-zinc-500 mb-1">Movie libraries</p>
                        <div className="flex flex-wrap gap-1">
                          {w.movie_libs.map((lib) => (
                            <button
                              key={lib}
                              onClick={() => {
                                const cur = w.size_overlay.movie_libraries;
                                update({ size_overlay: { ...w.size_overlay, movie_libraries: cur.includes(lib) ? cur.filter((x) => x !== lib) : [...cur, lib] } });
                              }}
                              className={`px-2 py-1 text-xs rounded border transition-all ${
                                w.size_overlay.movie_libraries.includes(lib)
                                  ? "bg-violet-600/30 border-violet-500 text-violet-200"
                                  : "bg-zinc-800 border-zinc-700 text-zinc-400"
                              }`}
                            >
                              {lib}
                            </button>
                          ))}
                        </div>
                      </div>
                    )}
                    {w.tv_libs.length > 0 && (
                      <div>
                        <p className="text-xs text-zinc-500 mb-1">TV libraries</p>
                        <div className="flex flex-wrap gap-1">
                          {w.tv_libs.map((lib) => (
                            <button
                              key={lib}
                              onClick={() => {
                                const cur = w.size_overlay.tv_libraries;
                                update({ size_overlay: { ...w.size_overlay, tv_libraries: cur.includes(lib) ? cur.filter((x) => x !== lib) : [...cur, lib] } });
                              }}
                              className={`px-2 py-1 text-xs rounded border transition-all ${
                                w.size_overlay.tv_libraries.includes(lib)
                                  ? "bg-violet-600/30 border-violet-500 text-violet-200"
                                  : "bg-zinc-800 border-zinc-700 text-zinc-400"
                              }`}
                            >
                              {lib}
                            </button>
                          ))}
                        </div>
                      </div>
                    )}
                    {w.anime_libs.length > 0 && (
                      <div>
                        <p className="text-xs text-zinc-500 mb-1">Anime libraries</p>
                        <div className="flex flex-wrap gap-1">
                          {w.anime_libs.map((lib) => (
                            <button
                              key={lib}
                              onClick={() => {
                                const cur = w.size_overlay.anime_libraries;
                                update({ size_overlay: { ...w.size_overlay, anime_libraries: cur.includes(lib) ? cur.filter((x) => x !== lib) : [...cur, lib] } });
                              }}
                              className={`px-2 py-1 text-xs rounded border transition-all ${
                                w.size_overlay.anime_libraries.includes(lib)
                                  ? "bg-violet-600/30 border-violet-500 text-violet-200"
                                  : "bg-zinc-800 border-zinc-700 text-zinc-400"
                              }`}
                            >
                              {lib}
                            </button>
                          ))}
                        </div>
                      </div>
                    )}
                  </div>
                  <ScheduleConfig
                    value={w.size_overlay}
                    onChange={(v) => update({ size_overlay: { ...v, movie_libraries: w.size_overlay.movie_libraries, tv_libraries: w.size_overlay.tv_libraries, anime_libraries: w.size_overlay.anime_libraries } })}
                  />
                </>
              )}
            </div>
          </div>
        );

      case 5:
        return (
          <div className="space-y-6">
            <div>
              <h2 className="text-xl font-semibold text-white mb-1">Kometa Paths</h2>
              <p className="text-zinc-400 text-sm">Paths where DAKOSYS will write overlay and collection YAML files for Kometa.</p>
            </div>
            <div className="space-y-4">
              <Input
                label="Overlay YAML output directory"
                value={w.kometa_yaml_output}
                onChange={(e) => update({ kometa_yaml_output: e.target.value })}
                classNames={{ input: "text-white", inputWrapper: "bg-zinc-800 border-zinc-700", label: "text-zinc-400" }}
              />
              <Input
                label="Collections directory"
                value={w.kometa_collections}
                onChange={(e) => update({ kometa_collections: e.target.value })}
                classNames={{ input: "text-white", inputWrapper: "bg-zinc-800 border-zinc-700", label: "text-zinc-400" }}
              />
              <Input
                label="Font directory (relative to Kometa config)"
                value={w.kometa_font_dir}
                onChange={(e) => update({ kometa_font_dir: e.target.value })}
                classNames={{ input: "text-white", inputWrapper: "bg-zinc-800 border-zinc-700", label: "text-zinc-400" }}
              />
              <Input
                label="Asset directory (relative to Kometa config)"
                value={w.kometa_asset_dir}
                onChange={(e) => update({ kometa_asset_dir: e.target.value })}
                classNames={{ input: "text-white", inputWrapper: "bg-zinc-800 border-zinc-700", label: "text-zinc-400" }}
              />
            </div>
          </div>
        );

      case 6:
        return (
          <div className="space-y-6">
            {/* TMDB */}
            <div>
              <h2 className="text-xl font-semibold text-white mb-1">API Keys</h2>
            </div>
            <div className="bg-zinc-900 rounded-lg p-4 border border-zinc-800 space-y-3">
              <div>
                <p className="text-white text-sm font-medium">TMDB API Key</p>
                <p className="text-zinc-500 text-xs mb-2">
                  Used for poster images on the Next Airing page. Get one free at{" "}
                  <a href="https://www.themoviedb.org/settings/api" target="_blank" rel="noopener noreferrer" className="text-violet-400 hover:text-violet-300">
                    themoviedb.org →
                  </a>
                </p>
                <Input
                  placeholder="Optional — leave blank to skip poster images"
                  value={w.tmdb_api_key}
                  onChange={(e) => update({ tmdb_api_key: e.target.value })}
                  classNames={{ input: "text-white", inputWrapper: "bg-zinc-800 border-zinc-700" }}
                />
              </div>
            </div>

            {/* Trakt */}
            <div>
              <h2 className="text-xl font-semibold text-white mb-1">Trakt Configuration</h2>
              <p className="text-zinc-400 text-sm">
                Create an API application at{" "}
                <a href="https://trakt.tv/oauth/applications" target="_blank" rel="noopener noreferrer" className="text-violet-400 hover:text-violet-300">
                  trakt.tv/oauth/applications
                </a>{" "}
                then enter your credentials below.
              </p>
              <div className="mt-2 bg-zinc-900 rounded-lg p-3 border border-zinc-800 text-xs text-zinc-400 space-y-1">
                <p>When creating the Trakt application:</p>
                <p>• Redirect URI: <code className="text-violet-300">urn:ietf:wg:oauth:2.0:oob</code></p>
                <p>• Check <span className="text-white">Skip authorization (single user)</span></p>
                <p>• Enable <span className="text-white">Auto-refresh token</span></p>
              </div>
            </div>

            <div className="space-y-4">
              <Input
                label="Client ID"
                value={w.trakt_client_id}
                onChange={(e) => update({ trakt_client_id: e.target.value, trakt_authed: false })}
                classNames={{ input: "text-white", inputWrapper: "bg-zinc-800 border-zinc-700", label: "text-zinc-400" }}
              />
              <Input
                label="Client Secret"
                value={w.trakt_client_secret}
                onChange={(e) => update({ trakt_client_secret: e.target.value, trakt_authed: false })}
                type="password"
                classNames={{ input: "text-white", inputWrapper: "bg-zinc-800 border-zinc-700", label: "text-zinc-400" }}
              />
              <Input
                label="Trakt username"
                value={w.trakt_username}
                onChange={(e) => update({ trakt_username: e.target.value })}
                classNames={{ input: "text-white", inputWrapper: "bg-zinc-800 border-zinc-700", label: "text-zinc-400" }}
              />
            </div>

            {/* Device auth */}
            {!w.trakt_authed && (
              <div className="bg-zinc-900 rounded-lg p-4 border border-zinc-800 space-y-3">
                <p className="text-sm text-zinc-300 font-medium">Authenticate with Trakt</p>
                {!traktDeviceInfo ? (
                  <Button
                    color="secondary"
                    size="sm"
                    isDisabled={!w.trakt_client_id || !w.trakt_client_secret}
                    onPress={startTraktAuth}
                  >
                    Start Authorization
                  </Button>
                ) : (
                  <div className="space-y-3">
                    <p className="text-xs text-zinc-400">
                      1. Visit{" "}
                      <a href={traktDeviceInfo.verification_url} target="_blank" rel="noopener noreferrer" className="text-violet-400 hover:text-violet-300 font-medium">
                        {traktDeviceInfo.verification_url}
                      </a>
                    </p>
                    <p className="text-xs text-zinc-400">
                      2. Enter code:{" "}
                      <span className="font-mono text-lg font-bold text-white tracking-widest bg-zinc-800 px-3 py-1 rounded">
                        {traktDeviceInfo.user_code}
                      </span>
                    </p>
                    {traktPolling && (
                      <div className="flex items-center gap-2 text-xs text-zinc-500">
                        <Spinner size="sm" color="secondary" />
                        Waiting for authorization...
                      </div>
                    )}
                  </div>
                )}
                {traktError && <p className="text-red-400 text-xs">{traktError}</p>}
              </div>
            )}

            {w.trakt_authed && (
              <div className="bg-green-950/40 border border-green-800 rounded-lg p-3 flex items-center gap-2">
                <span className="text-green-400 text-lg">OK</span>
                <p className="text-green-300 text-sm font-medium">Trakt authorized successfully!</p>
              </div>
            )}

            <p className="text-zinc-600 text-xs">You can skip authorization and authenticate later by running the container manually.</p>
          </div>
        );

      case 7:
        return (
          <div className="space-y-6">
            <div>
              <h2 className="text-xl font-semibold text-white mb-1">Notifications & Privacy</h2>
              <p className="text-zinc-400 text-sm">Optional Discord notifications and Trakt list privacy settings.</p>
            </div>

            <div className="bg-zinc-900 rounded-lg p-4 border border-zinc-800 space-y-4">
              <div className="flex items-center justify-between">
                <div>
                  <p className="text-white font-medium">Discord notifications</p>
                  <p className="text-zinc-500 text-xs">Send updates and errors to Discord</p>
                </div>
                <Switch
                  isSelected={w.notif_enabled}
                  onValueChange={(v) => update({ notif_enabled: v })}
                  color="secondary"
                />
              </div>
              {w.notif_enabled && (
                <Input
                  label="Discord webhook URL"
                  value={w.discord_webhook}
                  onChange={(e) => update({ discord_webhook: e.target.value })}
                  placeholder="https://discord.com/api/webhooks/..."
                  classNames={{ input: "text-white", inputWrapper: "bg-zinc-800 border-zinc-700", label: "text-zinc-400" }}
                />
              )}
            </div>

            <div>
              <p className="text-sm text-zinc-400 mb-2">Default Trakt list privacy</p>
              <div className="flex gap-3">
                {(["private", "public"] as const).map((p) => (
                  <button
                    key={p}
                    onClick={() => update({ list_privacy: p })}
                    className={`px-4 py-2 rounded-lg border text-sm font-medium transition-all ${
                      w.list_privacy === p
                        ? "bg-violet-600 border-violet-500 text-white"
                        : "bg-zinc-800 border-zinc-700 text-zinc-400 hover:border-zinc-500"
                    }`}
                  >
                    {p.charAt(0).toUpperCase() + p.slice(1)}
                  </button>
                ))}
              </div>
            </div>
          </div>
        );

      case 8:
        return (
          <div className="space-y-6">
            <div>
              <h2 className="text-xl font-semibold text-white mb-1">Review & Save</h2>
              <p className="text-zinc-400 text-sm">Check your configuration, then click Save to create config.yaml.</p>
            </div>

            <div className="space-y-3 text-sm">
              <ReviewRow label="Timezone" value={w.timezone} />
              <ReviewRow label="Date format" value={w.date_format} />
              <ReviewRow label="Plex URL" value={w.plex_url} />
              <ReviewRow label="Plex token" value={w.plex_token ? "set" : "Not set"} warn={!w.plex_token} />
              <ReviewRow label="Anime libraries" value={w.anime_libs.join(", ") || "None"} />
              <ReviewRow label="TV libraries" value={w.tv_libs.join(", ") || "None"} />
              <ReviewRow label="Movie libraries" value={w.movie_libs.join(", ") || "None"} />
              <ReviewRow label="Anime Episode Type" value={w.anime_episode_type.enabled ? "Enabled" : "Disabled"} />
              <ReviewRow label="TV Status Tracker" value={w.tv_status_tracker.enabled ? "Enabled" : "Disabled"} />
              <ReviewRow label="Size Overlay" value={w.size_overlay.enabled ? "Enabled" : "Disabled"} />
              <ReviewRow label="TMDB API key" value={w.tmdb_api_key ? "Set" : "Not set (posters disabled)"} />
              <ReviewRow label="Trakt client ID" value={w.trakt_client_id ? "Set" : "Not set"} warn={!w.trakt_client_id} />
              <ReviewRow label="Trakt auth" value={w.trakt_authed ? "Authorized" : "Not yet authorized"} warn={!w.trakt_authed} />
              <ReviewRow label="Notifications" value={w.notif_enabled ? (w.discord_webhook ? "Discord enabled" : "Enabled (no webhook)") : "Disabled"} />
              <ReviewRow label="List privacy" value={w.list_privacy} />
            </div>

            {saveError && (
              <div className="bg-red-950/50 border border-red-800 rounded-lg p-3">
                <p className="text-red-400 text-sm">{saveError}</p>
              </div>
            )}

            <Button
              color="secondary"
              size="lg"
              fullWidth
              isLoading={saving}
              onPress={handleSave}
            >
              Save Configuration & Open Dashboard
            </Button>
          </div>
        );

      default:
        return null;
    }
  };

  const stepTitles = [
    "Basic Settings", "Plex", "Libraries", "Services",
    "Kometa", "Trakt", "Notifications", "Review",
  ];

  return (
    <div className="max-w-2xl mx-auto py-4">
      {/* Header */}
      <div className="mb-8">
        <div className="flex items-center gap-3 mb-2">
          <div className="w-9 h-9 rounded-lg bg-gradient-to-br from-violet-600 to-indigo-600 flex items-center justify-center text-white font-bold text-sm">
            D
          </div>
          <h1 className="text-2xl font-bold text-white">DAKOSYS Setup</h1>
        </div>
        <p className="text-zinc-500 text-sm">Configure your services to get started</p>
      </div>

      {/* Progress */}
      <div className="flex items-center gap-1 mb-8">
        {stepTitles.map((title, i) => {
          const n = i + 1;
          const done = n < step;
          const current = n === step;
          return (
            <div key={n} className="flex items-center flex-1">
              <div className="flex flex-col items-center min-w-0 flex-1">
                <div
                  className={`w-7 h-7 rounded-full flex items-center justify-center text-xs font-bold border-2 transition-all ${
                    done
                      ? "bg-violet-600 border-violet-500 text-white"
                      : current
                      ? "bg-zinc-800 border-violet-500 text-violet-300"
                      : "bg-zinc-900 border-zinc-700 text-zinc-600"
                  }`}
                >
                  {done ? "+" : n}
                </div>
                <p className={`text-xs mt-1 hidden sm:block truncate w-full text-center ${current ? "text-violet-300" : done ? "text-zinc-400" : "text-zinc-700"}`}>
                  {title}
                </p>
              </div>
              {i < stepTitles.length - 1 && (
                <div className={`h-px flex-1 mx-1 mb-4 transition-all ${done ? "bg-violet-600" : "bg-zinc-800"}`} />
              )}
            </div>
          );
        })}
      </div>

      {/* Step content */}
      <div className="bg-zinc-950 border border-zinc-800 rounded-xl p-6 mb-6">
        {stepContent()}
      </div>

      {/* Navigation */}
      <div className="flex justify-between">
        <Button
          variant="bordered"
          isDisabled={step === 1}
          onPress={() => setStep((s) => s - 1)}
          className="border-zinc-700 text-zinc-400"
        >
          Back
        </Button>
        {step < TOTAL_STEPS ? (
          <Button color="secondary" onPress={() => setStep((s) => s + 1)}>
            Next
          </Button>
        ) : null}
      </div>
    </div>
  );
}

function ReviewRow({ label, value, warn }: { label: string; value: string; warn?: boolean }) {
  return (
    <div className="flex justify-between items-center py-2 border-b border-zinc-800/60">
      <span className="text-zinc-400">{label}</span>
      <span className={warn ? "text-yellow-400" : "text-white"}>{value}</span>
    </div>
  );
}
