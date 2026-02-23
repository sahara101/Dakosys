"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Button, Card, CardBody, Chip, Input, Spinner } from "@nextui-org/react";
import { api } from "@/lib/api";
import type { AnimeEntry, TraktList } from "@/types/api";

type EpisodeType = TraktList["episode_type"];

interface Toast {
  msg: string;
  type: "success" | "error";
}

const EPISODE_TYPES: EpisodeType[] = [
  "filler",
  "manga canon",
  "anime canon",
  "mixed canon/filler",
];

const EPISODE_TYPE_LABELS: Record<EpisodeType, string> = {
  filler: "Filler",
  "manga canon": "Manga Canon",
  "anime canon": "Anime Canon",
  "mixed canon/filler": "Mixed Canon/Filler",
};

const CHIP_COLOR: Record<EpisodeType, "warning" | "primary" | "success" | "secondary"> = {
  filler: "warning",
  "manga canon": "primary",
  "anime canon": "success",
  "mixed canon/filler": "secondary",
};

export default function TraktListsPage() {
  const [lists, setLists] = useState<TraktList[]>([]);
  const [traktUsername, setTraktUsername] = useState<string | null>(null);
  const [schedule, setSchedule] = useState<AnimeEntry[]>([]);
  const [plexShows, setPlexShows] = useState<string[]>([]);
  const [plexError, setPlexError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const [confirmDeleteId, setConfirmDeleteId] = useState<number | null>(null);
  const [deletingId, setDeletingId] = useState<number | null>(null);

  const [syncing, setSyncing] = useState(false);
  const [syncDone, setSyncDone] = useState(false);

  const [runningAnime, setRunningAnime] = useState<string | null>(null);

  const [search, setSearch] = useState("");

  const [toast, setToast] = useState<Toast | null>(null);

  const syncDoneTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const toastTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const showToast = useCallback((msg: string, type: "success" | "error" = "success") => {
    setToast({ msg, type });
    if (toastTimerRef.current) clearTimeout(toastTimerRef.current);
    toastTimerRef.current = setTimeout(() => setToast(null), 3000);
  }, []);

  const fetchData = useCallback(async () => {
    try {
      const [listsData, scheduleData, plexData] = await Promise.all([
        api.getTraktLists(),
        api.getAnimeSchedule(),
        api.getPlexShows(),
      ]);

      if (listsData.error) {
        setError(listsData.error);
        setLists([]);
      } else {
        setLists(listsData.lists);
        setTraktUsername(listsData.trakt_username ?? null);
        setError(null);
      }

      setSchedule(scheduleData.anime);

      if (plexData.error) {
        setPlexShows([]);
        setPlexError(plexData.error);
      } else {
        setPlexShows(plexData.shows);
        setPlexError(null);
      }
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Failed to load data");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchData();
  }, []);

  useEffect(() => {
    if (!syncing) return;

    const interval = setInterval(async () => {
      try {
        const status = await api.getSyncStatus();
        if (!status.running) {
          setSyncing(false);
          setSyncDone(true);
          fetchData();
          syncDoneTimerRef.current = setTimeout(() => setSyncDone(false), 3000);
        }
      } catch {
      }
    }, 2000);

    return () => clearInterval(interval);
  }, [syncing, fetchData]);

  useEffect(() => {
    if (runningAnime === null) return;

    const aflName = runningAnime;

    const interval = setInterval(async () => {
      try {
        const status = await api.getAnimeRunStatus(aflName);
        if (!status.running) {
          setRunningAnime(null);
          fetchData();
        }
      } catch {
      }
    }, 2000);

    return () => clearInterval(interval);
  }, [runningAnime, fetchData]);

  useEffect(() => {
    return () => {
      if (syncDoneTimerRef.current) clearTimeout(syncDoneTimerRef.current);
      if (toastTimerRef.current) clearTimeout(toastTimerRef.current);
    };
  }, []);

  async function handleSync() {
    try {
      const res = await api.syncTraktCollections();
      if (res.started) {
        setSyncing(true);
        setSyncDone(false);
      } else {
        showToast(res.message ?? "Sync could not be started", "error");
      }
    } catch (e: unknown) {
      showToast(
        "Failed to start sync: " + (e instanceof Error ? e.message : String(e)),
        "error",
      );
    }
  }

  async function handleDelete(listId: number) {
    setDeletingId(listId);
    setConfirmDeleteId(null);
    try {
      await api.deleteTraktList(listId);
      setLists((prev) => prev.filter((l) => l.id !== listId));
      showToast("List deleted successfully");
    } catch (e: unknown) {
      showToast(
        "Failed to delete list: " + (e instanceof Error ? e.message : String(e)),
        "error",
      );
    } finally {
      setDeletingId(null);
    }
  }

  async function handleCreateAll(aflName: string) {
    try {
      const res = await api.triggerAnimeRun(aflName);
      if (res.started) {
        setRunningAnime(aflName);
      } else {
        showToast(res.message ?? "Could not start", "error");
      }
    } catch (e: unknown) {
      showToast("Failed: " + (e instanceof Error ? e.message : String(e)), "error");
    }
  }

  const plexShowsSet = useMemo(
    () => new Set(plexShows.map((s) => s.toLowerCase())),
    [plexShows],
  );

  const orphanedLists = useMemo(
    () => lists.filter((l) => !plexShowsSet.has(l.plex_name.toLowerCase())),
    [lists, plexShowsSet],
  );

  const unscheduledGroups = useMemo(() => {
    const scheduledSet = new Set(schedule.map((a) => a.afl_name));
    const groups = new Map<string, { plex_name: string; lists: TraktList[] }>();
    for (const list of lists) {
      if (!scheduledSet.has(list.anime_name) && plexShowsSet.has(list.plex_name.toLowerCase())) {
        if (!groups.has(list.anime_name)) {
          groups.set(list.anime_name, { plex_name: list.plex_name, lists: [] });
        }
        groups.get(list.anime_name)!.lists.push(list);
      }
    }
    return Array.from(groups.entries()).map(([anime_name, data]) => ({ anime_name, ...data }));
  }, [lists, schedule, plexShowsSet]);

  const plexAvailable = plexError === null && plexShows.length > 0;

  const q = search.toLowerCase();
  const filteredSchedule = schedule.filter(
    (a) => !q || a.display_name.toLowerCase().includes(q) || a.afl_name.toLowerCase().includes(q),
  );
  const filteredUnscheduled = unscheduledGroups.filter(
    (g) => !q || g.anime_name.toLowerCase().includes(q) || g.plex_name.toLowerCase().includes(q),
  );
  const filteredOrphaned = orphanedLists.filter(
    (l) => !q || l.name.toLowerCase().includes(q) || l.anime_name.toLowerCase().includes(q),
  );

  function findList(aflName: string, type: EpisodeType): TraktList | undefined {
    return lists.find((l) => l.anime_name === aflName && l.episode_type === type);
  }

  function traktListUrl(listName: string): string | null {
    if (!traktUsername) return null;
    const slug = listName.replace(/ /g, "-").replace(/\//g, "-");
    return `https://trakt.tv/users/${traktUsername}/lists/${slug}`;
  }

  const isTraktConfigError =
    error !== null &&
    (/not configured/i.test(error) || /auth/i.test(error));

  function renderDeleteButton(list: TraktList) {
    const isConfirming = confirmDeleteId === list.id;
    const isDeleting = deletingId === list.id;

    return (
      <Button
        size="sm"
        variant={isConfirming ? "solid" : "flat"}
        color="danger"
        isDisabled={deletingId !== null}
        isLoading={isDeleting}
        onPress={() => {
          if (isConfirming) {
            handleDelete(list.id);
          } else {
            setConfirmDeleteId(list.id);
          }
        }}
        onBlur={() => {
          if (isConfirming) setConfirmDeleteId(null);
        }}
      >
        {isConfirming ? "Confirm?" : "Delete"}
      </Button>
    );
  }

  function renderEpisodeRow(aflName: string, type: EpisodeType) {
    const list = findList(aflName, type);

    return (
      <div
        key={type}
        className="flex items-center gap-3 py-1.5"
      >
        <span className="text-sm text-zinc-300 w-28 sm:w-40 shrink-0">
          {EPISODE_TYPE_LABELS[type]}
        </span>

        <div className="flex-1">
          {list ? (() => {
            const url = traktListUrl(list.name);
            const chip = (
              <Chip size="sm" variant="flat" color={CHIP_COLOR[type]}>
                {list.item_count} {list.item_count === 1 ? "episode" : "episodes"}
              </Chip>
            );
            return url ? (
              <a href={url} target="_blank" rel="noopener noreferrer" className="inline-flex items-center gap-1 group">
                {chip}
                <svg className="w-3 h-3 text-zinc-600 group-hover:text-zinc-400 transition-colors" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M10 6H6a2 2 0 00-2 2v10a2 2 0 002 2h10a2 2 0 002-2v-4M14 4h6m0 0v6m0-6L10 14" />
                </svg>
              </a>
            ) : chip;
          })() : (
            <span className="text-zinc-600 text-sm">No list</span>
          )}
        </div>

        <div className="w-24 flex justify-end">
          {list && renderDeleteButton(list)}
        </div>
      </div>
    );
  }

  return (
    <div>
      {/* Toast */}
      {toast && (
        <div
          className={`fixed bottom-6 right-6 z-50 px-4 py-3 rounded-lg border text-sm font-medium shadow-lg ${
            toast.type === "success"
              ? "bg-green-950/80 border-green-800 text-green-300"
              : "bg-red-950/80 border-red-800 text-red-300"
          }`}
        >
          {toast.msg}
        </div>
      )}

      {/* Page header */}
      <div className="flex items-center justify-between mb-6 gap-4">
        <div className="min-w-0">
          <h1 className="text-3xl font-bold text-white">Trakt Lists</h1>
          <p className="text-zinc-400 mt-1">
            Manage Trakt.tv episode type lists for your scheduled anime
          </p>
        </div>

        <div className="flex gap-2 shrink-0">
          <Button
            color="secondary"
            variant="flat"
            isDisabled={syncing}
            onPress={handleSync}
          >
            {syncing ? (
              <>
                <Spinner size="sm" color="current" className="mr-2" />
                Syncing...
              </>
            ) : syncDone ? (
              "\u2713 Synced!"
            ) : (
              "Sync Collections"
            )}
          </Button>

          <Button
            variant="flat"
            color="default"
            isDisabled={loading}
            onPress={() => {
              setLoading(true);
              fetchData();
            }}
          >
            Refresh
          </Button>
        </div>
      </div>

      {/* Search */}
      <div className="mb-4">
        <Input
          placeholder="Search anime…"
          value={search}
          onValueChange={setSearch}
          variant="bordered"
          classNames={{
            inputWrapper: "bg-zinc-900 border-zinc-700",
            input: "text-white",
          }}
          startContent={
            <svg className="w-4 h-4 text-zinc-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
            </svg>
          }
        />
      </div>

      {/* Loading state */}
      {loading && (
        <div className="flex justify-center h-40 items-center">
          <Spinner color="secondary" />
        </div>
      )}

      {/* Trakt config error banner */}
      {isTraktConfigError && (
        <div className="bg-yellow-950/50 border border-yellow-800 rounded-lg p-4 mb-4">
          <p className="text-yellow-400 text-sm">
            Trakt is not configured or authentication failed. Check your config.
          </p>
        </div>
      )}

      {/* Generic error banner (non-config) */}
      {error && !isTraktConfigError && (
        <div className="bg-red-950/50 border border-red-800 rounded-lg p-4 mb-4">
          <p className="text-red-400 text-sm">{error}</p>
        </div>
      )}

      {!loading && (
        <>
          {/* Summary strip */}
          {lists.length > 0 && (
            <div className="bg-zinc-900 border border-zinc-800 p-4 rounded-lg mb-6">
              <p className="text-zinc-400">
                <span className="text-white font-semibold">{schedule.length + unscheduledGroups.length}</span> anime
                {" "}&middot;{" "}
                <span className="text-white font-semibold">{lists.length}</span> lists
              </p>
            </div>
          )}

          {/* Empty schedule */}
          {schedule.length === 0 && (
            <Card className="bg-zinc-900 border border-zinc-800">
              <CardBody className="p-6 text-center text-zinc-500">
                No anime scheduled. Add anime to your config to get started.
              </CardBody>
            </Card>
          )}

          {/* Scheduled anime cards */}
          {filteredSchedule.length > 0 && (
            <div className="space-y-4 mb-8">
              {filteredSchedule.map((anime) => (
                <Card key={anime.afl_name} className="bg-zinc-900 border border-zinc-800">
                  <CardBody className="p-5">
                    {/* Anime header */}
                    <div className="flex items-center justify-between mb-3">
                      <div className="flex items-center min-w-0">
                        <span className="text-lg mr-2">🎌</span>
                        <span className="font-bold text-white">{anime.display_name}</span>
                        <span className="text-zinc-500 text-xs ml-2">{anime.afl_name}</span>
                      </div>
                      {/* Create All only appears for anime with no lists yet */}
                      {EPISODE_TYPES.every((t) => !findList(anime.afl_name, t)) && (
                        <Button
                          size="sm"
                          variant="flat"
                          color="secondary"
                          isDisabled={runningAnime !== null}
                          isLoading={runningAnime === anime.afl_name}
                          onPress={() => handleCreateAll(anime.afl_name)}
                        >
                          {runningAnime === anime.afl_name ? "Running..." : "Create All"}
                        </Button>
                      )}
                    </div>

                    {/* Episode type rows */}
                    <div className="divide-y divide-zinc-800">
                      {EPISODE_TYPES.map((type) => renderEpisodeRow(anime.afl_name, type))}
                    </div>
                  </CardBody>
                </Card>
              ))}
            </div>
          )}

          {/* Unscheduled anime section (in Plex, not in schedule) */}
          {plexAvailable && filteredUnscheduled.length > 0 && (
            <div className="mb-8">
              <div className="mb-4">
                <h2 className="text-xl font-semibold text-white">Unscheduled Anime</h2>
                <p className="text-zinc-400 text-sm mt-1">
                  In your Plex library but not in the active schedule
                </p>
              </div>
              <div className="space-y-4">
                {filteredUnscheduled.map((group) => (
                  <Card key={group.anime_name} className="bg-zinc-900 border border-zinc-800">
                    <CardBody className="p-5">
                      <div className="flex items-center min-w-0 mb-3">
                        <span className="text-lg mr-2">🎌</span>
                        <span className="font-bold text-white">{group.plex_name}</span>
                        <span className="text-zinc-500 text-xs ml-2">{group.anime_name}</span>
                      </div>
                      <div className="divide-y divide-zinc-800">
                        {EPISODE_TYPES.map((type) => renderEpisodeRow(group.anime_name, type))}
                      </div>
                    </CardBody>
                  </Card>
                ))}
              </div>
            </div>
          )}

          {/* Orphaned lists section */}
          {plexAvailable && filteredOrphaned.length > 0 && (
            <div>
              <div className="mb-4">
                <h2 className="text-xl font-semibold text-white">Orphaned Lists</h2>
                <p className="text-zinc-400 text-sm mt-1">
                  These lists are on Trakt but the show is not in your Plex library
                </p>
              </div>

              <div className="space-y-2">
                {filteredOrphaned.map((list) => (
                  <div
                    key={list.id}
                    className="flex items-center justify-between bg-zinc-900 border border-zinc-800 rounded-lg px-4 py-3"
                  >
                    <div className="flex items-center gap-3">
                      {(() => {
                        const url = traktListUrl(list.name);
                        return url ? (
                          <a href={url} target="_blank" rel="noopener noreferrer" className="text-sm text-white font-medium hover:text-violet-400 transition-colors">
                            {list.name} ↗
                          </a>
                        ) : (
                          <span className="text-sm text-white font-medium">{list.name}</span>
                        );
                      })()}
                      <Chip size="sm" variant="flat" color={CHIP_COLOR[list.episode_type]}>
                        {EPISODE_TYPE_LABELS[list.episode_type]}
                      </Chip>
                      <span className="text-zinc-500 text-xs">
                        {list.item_count} {list.item_count === 1 ? "episode" : "episodes"}
                      </span>
                    </div>

                    {renderDeleteButton(list)}
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Plex unavailable note (orphaned detection disabled) */}
          {!plexAvailable && !loading && (
            <p className="text-zinc-600 text-sm mt-4">
              Plex library unavailable — orphaned detection disabled.
            </p>
          )}
        </>
      )}
    </div>
  );
}
