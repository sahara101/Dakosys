"use client";

import { useEffect, useRef, useState } from "react";
import { Button, Card, CardBody, Chip, Input, Spinner, Switch } from "@nextui-org/react";
import { Spotlight } from "@/components/ui/spotlight";
import { api } from "@/lib/api";
import type { AflEpisodeCounts, AnimeEntry, StatusResponse } from "@/types/api";
import { RunServiceButton } from "@/components/shared/RunServiceButton";

const EPISODE_TYPES = ["filler", "manga canon", "anime canon", "mixed canon/filler"] as const;
type EpisodeType = (typeof EPISODE_TYPES)[number];

function findBestPlexMatch(aflName: string, shows: string[]): { show: string; score: number } | null {
  const aflWords = aflName.toLowerCase().split("-").filter((w) => w.length >= 2);
  let best: { show: string; score: number } | null = null;
  for (const show of shows) {
    const showWords = show.toLowerCase().replace(/[^a-z0-9]+/g, " ").trim().split(/\s+/);
    const score = aflWords.filter((w) => showWords.includes(w)).length;
    if (score > 0 && (!best || score > best.score)) best = { show, score };
  }
  return best;
}

const TYPE_COLORS: Record<EpisodeType, string> = {
  filler: "text-red-400",
  "manga canon": "text-blue-400",
  "anime canon": "text-green-400",
  "mixed canon/filler": "text-yellow-400",
};

export default function AnimePage() {
  const [status, setStatus] = useState<StatusResponse | null>(null);
  const [anime, setAnime] = useState<AnimeEntry[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const [plexShows, setPlexShows] = useState<string[]>([]);
  const [searchQuery, setSearchQuery] = useState("");
  const [searchResults, setSearchResults] = useState<string[]>([]);
  const [searching, setSearching] = useState(false);
  const [searched, setSearched] = useState(false);
  const [selectedAfl, setSelectedAfl] = useState<string | null>(null);
  const [aflCounts, setAflCounts] = useState<AflEpisodeCounts | null>(null);
  const [aflTotal, setAflTotal] = useState(0);
  const [loadingCounts, setLoadingCounts] = useState(false);
  const [plexFilter, setPlexFilter] = useState("");
  const [selectedPlex, setSelectedPlex] = useState("");
  const [addToSchedule, setAddToSchedule] = useState(true);
  const [adding, setAdding] = useState(false);
  const [runningAdd, setRunningAdd] = useState(false);
  const [addDone, setAddDone] = useState(false);
  const [addError, setAddError] = useState<string | null>(null);
  const [confirmRemoveAfl, setConfirmRemoveAfl] = useState<string | null>(null);
  const [removingAfl, setRemovingAfl] = useState<string | null>(null);
  const [runningScheduled, setRunningScheduled] = useState<Record<string, boolean>>({});
  const runPollRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const scheduledPollRefs = useRef<Record<string, ReturnType<typeof setInterval>>>({});

  const fetchData = async () => {
    try {
      const [s, a] = await Promise.all([api.getStatus(), api.getAnimeSchedule()]);
      setStatus(s);
      setAnime(a.anime);
      setError(null);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Failed to load");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchData();
    api.getPlexShows().then((r) => setPlexShows(r.shows)).catch(() => {});
  }, []); 

  useEffect(() => {
    if (!runningAdd || !selectedAfl) return;
    const afl = selectedAfl;
    runPollRef.current = setInterval(async () => {
      try {
        const s = await api.getAnimeRunStatus(afl);
        if (!s.running) {
          clearInterval(runPollRef.current!);
          setRunningAdd(false);
          setAddDone(true);
          fetchData();
        }
      } catch {
        clearInterval(runPollRef.current!);
        setRunningAdd(false);
      }
    }, 2000);
    return () => {
      if (runPollRef.current) clearInterval(runPollRef.current);
    };
  }, [runningAdd]); 

  const handleSearch = async () => {
    if (!searchQuery.trim()) return;
    setSearching(true);
    setSearched(false);
    setSearchResults([]);
    setSelectedAfl(null);
    setAflCounts(null);
    setAddDone(false);
    setAddError(null);
    try {
      const r = await api.searchAfl(searchQuery.trim());
      setSearchResults(r.shows);
      setSearched(true);
    } catch (e: unknown) {
      setAddError(e instanceof Error ? e.message : "Search failed");
    } finally {
      setSearching(false);
    }
  };

  const handleSelectAfl = async (aflName: string) => {
    setSelectedAfl(aflName);
    setAflCounts(null);
    setLoadingCounts(true);
    setAddDone(false);
    setAddError(null);
    setSelectedPlex("");
    const match = findBestPlexMatch(aflName, plexShows);
    const aflWordCount = aflName.split("-").filter((w) => w.length >= 2).length;
    if (match && match.score >= 2 && match.score >= Math.ceil(aflWordCount * 0.5)) {
      setSelectedPlex(match.show);
      setPlexFilter(match.show);
    } else if (match && match.score >= 1) {
      setPlexFilter(match.show);
    } else {
      setPlexFilter("");
    }
    try {
      const r = await api.getAflEpisodes(aflName);
      setAflCounts(r.counts);
      setAflTotal(r.total);
    } catch (e: unknown) {
      setAddError(e instanceof Error ? e.message : "Failed to fetch episode counts");
    } finally {
      setLoadingCounts(false);
    }
  };

  const handleAdd = async () => {
    if (!selectedAfl || !selectedPlex) return;
    setAdding(true);
    setAddError(null);
    try {
      await api.addAnime(selectedAfl, selectedPlex, addToSchedule);
      await api.triggerAnimeRun(selectedAfl);
      setRunningAdd(true);
    } catch (e: unknown) {
      setAddError(e instanceof Error ? e.message : "Failed to add anime");
    } finally {
      setAdding(false);
    }
  };

  const handleRunScheduled = async (aflName: string) => {
    if (runningScheduled[aflName]) return;
    try {
      await api.triggerAnimeRun(aflName);
      setRunningScheduled((p) => ({ ...p, [aflName]: true }));
      scheduledPollRefs.current[aflName] = setInterval(async () => {
        try {
          const s = await api.getAnimeRunStatus(aflName);
          if (!s.running) {
            clearInterval(scheduledPollRefs.current[aflName]);
            delete scheduledPollRefs.current[aflName];
            setRunningScheduled((p) => ({ ...p, [aflName]: false }));
          }
        } catch {
          clearInterval(scheduledPollRefs.current[aflName]);
          delete scheduledPollRefs.current[aflName];
          setRunningScheduled((p) => ({ ...p, [aflName]: false }));
        }
      }, 2000);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Failed to trigger run");
    }
  };

  const handleRemoveFromSchedule = async (aflName: string) => {
    setRemovingAfl(aflName);
    setConfirmRemoveAfl(null);
    try {
      await api.removeFromSchedule(aflName);
      fetchData();
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Failed to remove from schedule");
    } finally {
      setRemovingAfl(null);
    }
  };

  const resetAddFlow = () => {
    setSearchQuery("");
    setSearchResults([]);
    setSearched(false);
    setSelectedAfl(null);
    setAflCounts(null);
    setSelectedPlex("");
    setPlexFilter("");
    setAddDone(false);
    setAddError(null);
    setAddToSchedule(true);
  };

  const filteredPlex = plexShows.filter((s) =>
    s.toLowerCase().includes(plexFilter.toLowerCase()),
  );

  const svc = status?.services.anime_episode_type;

  function formatNextRun(iso: string | null): string {
    if (!iso) return "—";
    try {
      return new Date(iso).toLocaleString();
    } catch {
      return iso;
    }
  }

  return (
    <div>
      <Spotlight className="rounded-2xl mb-4 p-6 bg-zinc-900/50 border border-zinc-800">
        <div className="flex flex-col gap-4">
          <div className="flex items-center justify-between">
            <div>
              <h1 className="text-3xl font-bold text-white">Anime Episode Types</h1>
              <p className="text-zinc-400 mt-1">Filler / canon categorisation via Trakt.tv lists</p>
            </div>
            {svc && (
              <Chip
                color={svc.running ? "warning" : svc.enabled ? "success" : "default"}
                variant="flat"
              >
                {svc.running ? "Running" : svc.enabled ? "Active" : "Disabled"}
              </Chip>
            )}
          </div>
          <RunServiceButton service="anime_episode_type" label="Anime Episode Type" onComplete={fetchData} />
        </div>
      </Spotlight>

      {svc && (
        <Card className="bg-zinc-900 border border-zinc-800 mb-6">
          <CardBody className="p-4">
            <div className="flex items-center justify-between">
              <Switch
                isSelected={svc.enabled}
                onValueChange={async (val) => {
                  await api.setServiceEnabled("anime_episode_type", val);
                  fetchData();
                }}
                color="success"
                size="sm"
              >
                <span className={`text-sm font-semibold ${svc.enabled ? "text-green-400" : "text-zinc-500"}`}>
                  {svc.enabled ? "Enabled" : "Disabled"}
                </span>
              </Switch>
              <div className="text-right">
                <p className="text-zinc-400 text-xs uppercase tracking-wider mb-1">Next Run</p>
                <p className="text-violet-300 font-semibold">{formatNextRun(svc.next_run)}</p>
              </div>
            </div>
          </CardBody>
        </Card>
      )}

      {loading && (
        <div className="flex justify-center h-40 items-center">
          <Spinner color="secondary" />
        </div>
      )}

      {error && (
        <div className="bg-red-950/50 border border-red-800 rounded-lg p-4 mb-4">
          <p className="text-red-400 text-sm">{error}</p>
        </div>
      )}

      {svc && (
        <div className="space-y-4">
          {/* Scheduled anime list */}
          {anime.length > 0 && (
            <Card className="bg-zinc-900 border border-zinc-800">
              <CardBody className="p-6">
                <div className="flex items-center justify-between mb-4">
                  <h2 className="font-semibold text-white">Scheduled Anime</h2>
                  <Chip size="sm" variant="flat" color="secondary">
                    {anime.length} titles
                  </Chip>
                </div>
                <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-2">
                  {anime.map((a) => (
                    <div
                      key={a.afl_name}
                      className="flex items-center gap-2 bg-zinc-800/50 rounded-lg px-3 py-2"
                    >
                      <span className="text-base shrink-0">🎌</span>
                      <div className="min-w-0 flex-1">
                        <p className="text-sm text-white font-medium truncate">{a.display_name}</p>
                        <p className="text-xs text-zinc-500 truncate">{a.afl_name}</p>
                      </div>
                      {removingAfl === a.afl_name ? (
                        <Spinner size="sm" color="danger" className="shrink-0" />
                      ) : runningScheduled[a.afl_name] ? (
                        <Spinner size="sm" color="secondary" className="shrink-0" />
                      ) : confirmRemoveAfl === a.afl_name ? (
                        <div className="flex items-center gap-1 shrink-0">
                          <button
                            onClick={() => handleRemoveFromSchedule(a.afl_name)}
                            className="text-xs text-red-400 hover:text-red-300 font-medium"
                          >
                            Confirm
                          </button>
                          <button
                            onClick={() => setConfirmRemoveAfl(null)}
                            className="text-xs text-zinc-500 hover:text-zinc-300 ml-1"
                          >
                            ✕
                          </button>
                        </div>
                      ) : (
                        <div className="flex items-center gap-1 shrink-0">
                          <button
                            onClick={() => handleRunScheduled(a.afl_name)}
                            className="text-zinc-600 hover:text-violet-400 transition-colors"
                            title="Run now"
                          >
                            <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
                                d="M14.752 11.168l-3.197-2.132A1 1 0 0010 9.87v4.263a1 1 0 001.555.832l3.197-2.132a1 1 0 000-1.664z" />
                              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
                                d="M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
                            </svg>
                          </button>
                          <button
                            onClick={() => setConfirmRemoveAfl(a.afl_name)}
                            className="text-zinc-600 hover:text-red-400 transition-colors"
                            title="Remove from schedule"
                          >
                            <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
                                d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
                            </svg>
                          </button>
                        </div>
                      )}
                    </div>
                  ))}
                </div>
              </CardBody>
            </Card>
          )}

          {/* Add Anime card */}
          <Card className="bg-zinc-900 border border-zinc-800">
            <CardBody className="p-6">
              <div className="flex items-center justify-between mb-4">
                <h2 className="font-semibold text-white">Add Anime</h2>
                {(selectedAfl || searchResults.length > 0 || addDone) && (
                  <Button size="sm" variant="light" color="default" onPress={resetAddFlow}>
                    Reset
                  </Button>
                )}
              </div>

              {addDone ? (
                <div className="text-center py-6">
                  <p className="text-green-400 font-semibold text-lg mb-2">Done!</p>
                  <p className="text-zinc-400 text-sm mb-4">
                    {addToSchedule ? (
                      <>
                        <span className="text-white font-mono">{selectedAfl}</span> added to
                        schedule — Trakt lists are being created.
                      </>
                    ) : (
                      <>
                        Mapping saved for{" "}
                        <span className="text-white font-mono">{selectedAfl}</span>. Not added to
                        schedule.
                      </>
                    )}
                  </p>
                  <Button size="sm" color="secondary" variant="flat" onPress={resetAddFlow}>
                    Add another
                  </Button>
                </div>
              ) : (
                <>
                  {/* Step 1: Search AFL */}
                  <div className="flex gap-2 mb-4">
                    <Input
                      size="sm"
                      placeholder="Search AnimeFillerList (e.g. zexal)"
                      value={searchQuery}
                      onValueChange={setSearchQuery}
                      onKeyDown={(e) => {
                        if (e.key === "Enter") handleSearch();
                      }}
                      classNames={{
                        inputWrapper: "bg-zinc-800 border-zinc-700",
                        input: "text-white",
                      }}
                    />
                    <Button
                      size="sm"
                      color="secondary"
                      variant="flat"
                      onPress={handleSearch}
                      isLoading={searching}
                      isDisabled={!searchQuery.trim() || searching}
                    >
                      Search
                    </Button>
                  </div>

                  {/* Search results */}
                  {searchResults.length > 0 && !selectedAfl && (
                    <div className="mb-4">
                      <p className="text-xs text-zinc-500 mb-2">
                        {searchResults.length} results — click to select
                      </p>
                      <div className="max-h-48 overflow-y-auto space-y-1 pr-1">
                        {searchResults.map((slug) => (
                          <div key={slug} className="flex items-center gap-1">
                            <button
                              onClick={() => handleSelectAfl(slug)}
                              className="flex-1 text-left px-3 py-2 rounded-lg bg-zinc-800/50 hover:bg-zinc-700/70 text-sm text-zinc-300 hover:text-white transition-colors font-mono"
                            >
                              {slug}
                            </button>
                            <a
                              href={`https://www.animefillerlist.com/shows/${slug}`}
                              target="_blank"
                              rel="noopener noreferrer"
                              className="p-2 text-zinc-600 hover:text-zinc-300 transition-colors shrink-0"
                              title="Open on AnimeFillerList"
                            >
                              <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M10 6H6a2 2 0 00-2 2v10a2 2 0 002 2h10a2 2 0 002-2v-4M14 4h6m0 0v6m0-6L10 14" />
                              </svg>
                            </a>
                          </div>
                        ))}
                      </div>
                    </div>
                  )}

                  {searched && searchResults.length === 0 && !searching && !selectedAfl && (
                    <p className="text-zinc-500 text-sm mb-4">No results found</p>
                  )}

                  {/* Step 2: Selected AFL + episode counts preview */}
                  {selectedAfl && (
                    <div className="mb-4 p-3 bg-zinc-800/50 rounded-lg">
                      <div className="flex items-center justify-between mb-2">
                        <div className="flex items-center gap-2">
                          <p className="text-sm font-medium text-white font-mono">{selectedAfl}</p>
                          <a
                            href={`https://www.animefillerlist.com/shows/${selectedAfl}`}
                            target="_blank"
                            rel="noopener noreferrer"
                            className="text-zinc-600 hover:text-zinc-300 transition-colors"
                            title="Open on AnimeFillerList"
                          >
                            <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M10 6H6a2 2 0 00-2 2v10a2 2 0 002 2h10a2 2 0 002-2v-4M14 4h6m0 0v6m0-6L10 14" />
                            </svg>
                          </a>
                        </div>
                        <button
                          onClick={() => {
                            setSelectedAfl(null);
                            setAflCounts(null);
                            setSelectedPlex("");
                            setPlexFilter("");
                          }}
                          className="text-xs text-zinc-500 hover:text-zinc-300"
                        >
                          change
                        </button>
                      </div>
                      {loadingCounts ? (
                        <div className="flex items-center gap-2 text-zinc-500 text-sm">
                          <Spinner size="sm" color="secondary" />
                          <span>Loading episode data…</span>
                        </div>
                      ) : aflCounts ? (
                        <div className="grid grid-cols-2 gap-x-6 gap-y-1">
                          {EPISODE_TYPES.map((t) => (
                            <div key={t} className="flex justify-between text-xs">
                              <span className="text-zinc-400 capitalize">{t}</span>
                              <span className={`font-semibold ${TYPE_COLORS[t]}`}>
                                {aflCounts[t] ?? 0} ep
                              </span>
                            </div>
                          ))}
                          <div className="col-span-2 border-t border-zinc-700 mt-1 pt-1 flex justify-between text-xs">
                            <span className="text-zinc-500">Total</span>
                            <span className="text-white font-semibold">{aflTotal} episodes</span>
                          </div>
                        </div>
                      ) : null}
                    </div>
                  )}

                  {/* Step 3: Plex show selector */}
                  {selectedAfl && (
                    <div className="mb-4">
                      <p className="text-xs text-zinc-500 mb-1">Match to Plex show</p>
                      <Input
                        size="sm"
                        placeholder="Type to filter your Plex library…"
                        value={plexFilter}
                        onValueChange={(v) => {
                          setPlexFilter(v);
                          setSelectedPlex("");
                        }}
                        classNames={{
                          inputWrapper: "bg-zinc-800 border-zinc-700",
                          input: "text-white",
                        }}
                      />
                      {plexFilter && !selectedPlex && filteredPlex.length > 0 && (
                        <div className="mt-1 max-h-40 overflow-y-auto border border-zinc-700 rounded-lg bg-zinc-900">
                          {filteredPlex.slice(0, 20).map((show) => (
                            <button
                              key={show}
                              onClick={() => {
                                setSelectedPlex(show);
                                setPlexFilter(show);
                              }}
                              className="w-full text-left px-3 py-1.5 text-sm text-zinc-300 hover:bg-zinc-800 hover:text-white transition-colors"
                            >
                              {show}
                            </button>
                          ))}
                          {filteredPlex.length > 20 && (
                            <p className="text-xs text-zinc-600 px-3 py-1.5">
                              {filteredPlex.length - 20} more…
                            </p>
                          )}
                        </div>
                      )}
                      {selectedPlex && (
                        <p className="text-xs text-green-400 mt-1">Selected: {selectedPlex}</p>
                      )}
                    </div>
                  )}

                  {/* Step 4: Schedule toggle + Add button */}
                  {selectedAfl && selectedPlex && (
                    <div className="space-y-3">
                      <label className="flex items-center gap-2 cursor-pointer select-none">
                        <input
                          type="checkbox"
                          checked={addToSchedule}
                          onChange={(e) => setAddToSchedule(e.target.checked)}
                          className="w-4 h-4 accent-violet-500"
                        />
                        <span className="text-sm text-zinc-300">Add to scheduled anime</span>
                      </label>
                      <Button
                        color="secondary"
                        variant="flat"
                        size="sm"
                        onPress={handleAdd}
                        isLoading={adding || runningAdd}
                        isDisabled={adding || runningAdd}
                        className="w-full"
                      >
                        {runningAdd
                          ? "Creating Trakt lists…"
                          : "Create Lists"}
                      </Button>
                    </div>
                  )}

                  {addError && <p className="text-red-400 text-sm mt-2">{addError}</p>}
                </>
              )}
            </CardBody>
          </Card>

          {/* How it works */}
          <Card className="bg-zinc-900 border border-zinc-800">
            <CardBody className="p-6">
              <h2 className="font-semibold text-white mb-3">How it works</h2>
              <ul className="space-y-2 text-sm text-zinc-400">
                <li className="flex items-start gap-2">
                  <span className="text-violet-400 mt-0.5">→</span>Reads anime from your Plex
                  library
                </li>
                <li className="flex items-start gap-2">
                  <span className="text-violet-400 mt-0.5">→</span>Looks up episode types on
                  AnimeFillerList
                </li>
                <li className="flex items-start gap-2">
                  <span className="text-violet-400 mt-0.5">→</span>Creates/updates Trakt lists:
                  Filler, Manga Canon, Anime Canon, Mixed
                </li>
                <li className="flex items-start gap-2">
                  <span className="text-violet-400 mt-0.5">→</span>Generates Kometa overlay YAML
                  files
                </li>
              </ul>
            </CardBody>
          </Card>
        </div>
      )}
    </div>
  );
}
