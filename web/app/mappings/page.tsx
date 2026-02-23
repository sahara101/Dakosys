"use client";

import { useCallback, useEffect, useState } from "react";
import { Button, Card, CardBody, Chip, Input, Spinner } from "@nextui-org/react";
import { api } from "@/lib/api";
import type { FailedEpisodeDetail, MappingError, TitleMappingGroup } from "@/types/api";

const TYPE_CHIP_COLOR: Record<string, "warning" | "primary" | "success" | "secondary" | "default"> = {
  FILLER: "warning",
  MANGA: "primary",
  ANIME: "success",
  MIXED: "secondary",
};

export default function MappingsPage() {
  const [errors, setErrors] = useState<MappingError[]>([]);
  const [loading, setLoading] = useState(true);
  const [fetchError, setFetchError] = useState<string | null>(null);

  const [fixes, setFixes] = useState<Record<string, Record<string, string>>>({});
  const [saving, setSaving] = useState<Record<string, boolean>>({});
  const [saved, setSaved] = useState<Record<string, boolean>>({});
  const [saveErrors, setSaveErrors] = useState<Record<string, string>>({});

  const [titleMappings, setTitleMappings] = useState<TitleMappingGroup[]>([]);
  const [editState, setEditState] = useState<Record<string, { plexTitle: string; traktTitle: string }>>({});
  const [editSaving, setEditSaving] = useState<Record<string, boolean>>({});
  const [deleting, setDeleting] = useState<Record<string, boolean>>({});
  const [confirmDelete, setConfirmDelete] = useState<string | null>(null);

  const groupKey = (e: MappingError) => `${e.anime_name}||${e.episode_type}`;
  const entryKey = (animeName: string, plexTitle: string) => `${animeName}||${plexTitle}`;

  const fetchAll = useCallback(async () => {
    setLoading(true);
    try {
      const [errRes, mapRes] = await Promise.all([
        api.getMappingErrors(),
        api.getTitleMappings(),
      ]);
      setErrors(errRes.errors);
      setFetchError(errRes.error ?? null);
      setTitleMappings(mapRes.mappings);
    } catch (e: unknown) {
      setFetchError(e instanceof Error ? e.message : "Failed to load");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { fetchAll(); }, [fetchAll]);

  function startEdit(animeName: string, plexTitle: string, traktTitle: string) {
    const k = entryKey(animeName, plexTitle);
    setEditState((p) => ({ ...p, [k]: { plexTitle, traktTitle } }));
    setConfirmDelete(null);
  }

  function cancelEdit(animeName: string, plexTitle: string) {
    const k = entryKey(animeName, plexTitle);
    setEditState((p) => { const n = { ...p }; delete n[k]; return n; });
  }

  async function saveEdit(animeName: string, origPlexTitle: string) {
    const k = entryKey(animeName, origPlexTitle);
    const edits = editState[k];
    if (!edits) return;
    setEditSaving((p) => ({ ...p, [k]: true }));
    try {
      if (edits.plexTitle !== origPlexTitle) {
        await api.deleteTitleMapping(animeName, origPlexTitle);
      }
      await api.updateTitleMapping(animeName, edits.plexTitle, edits.traktTitle);
      cancelEdit(animeName, origPlexTitle);
      const r = await api.getTitleMappings();
      setTitleMappings(r.mappings);
    } catch (e: unknown) {
      setFetchError(e instanceof Error ? e.message : "Save failed");
    } finally {
      setEditSaving((p) => ({ ...p, [k]: false }));
    }
  }

  async function handleDelete(animeName: string, plexTitle: string) {
    const k = entryKey(animeName, plexTitle);
    setDeleting((p) => ({ ...p, [k]: true }));
    setConfirmDelete(null);
    try {
      await api.deleteTitleMapping(animeName, plexTitle);
      const r = await api.getTitleMappings();
      setTitleMappings(r.mappings);
    } catch (e: unknown) {
      setFetchError(e instanceof Error ? e.message : "Delete failed");
    } finally {
      setDeleting((p) => ({ ...p, [k]: false }));
    }
  }

  function setFix(group: MappingError, episode: string, value: string) {
    const k = groupKey(group);
    setFixes((prev) => ({
      ...prev,
      [k]: { ...(prev[k] ?? {}), [episode]: value },
    }));
  }

  async function handleSave(group: MappingError) {
    const k = groupKey(group);
    const entries = fixes[k] ?? {};
    const nonEmpty = Object.fromEntries(
      Object.entries(entries).filter(([, v]) => v.trim() !== "")
    );
    if (Object.keys(nonEmpty).length === 0) return;

    setSaving((p) => ({ ...p, [k]: true }));
    setSaveErrors((p) => ({ ...p, [k]: "" }));
    try {
      await api.fixMappings(group.anime_name, group.episode_type, nonEmpty);
      setSaved((p) => ({ ...p, [k]: true }));
      setErrors((prev) =>
        prev
          .map((e) => {
            if (groupKey(e) !== k) return e;
            const remainingDetails = e.failed_episode_details.filter((ep) => !nonEmpty[ep.name]);
            const remainingNames = new Set(remainingDetails.map((ep) => ep.name));
            const remainingEps = e.failed_episodes.filter((s) => {
              const name = s.replace(/^Ep\.\d+ - /, "");
              return remainingNames.has(name) || remainingNames.has(s);
            });
            return { ...e, failed_episodes: remainingEps, failed_episode_details: remainingDetails };
          })
          .filter((e) => e.failed_episode_details.length > 0 || e.failed_episodes.length > 0)
      );
      setTimeout(() => setSaved((p) => ({ ...p, [k]: false })), 3000);
    } catch (e: unknown) {
      setSaveErrors((p) => ({
        ...p,
        [k]: e instanceof Error ? e.message : "Failed to save",
      }));
    } finally {
      setSaving((p) => ({ ...p, [k]: false }));
    }
  }

  return (
    <div>
      <div className="mb-6">
        <h1 className="text-3xl font-bold text-white">Fix Mappings</h1>
        <p className="text-zinc-400 mt-1">
          Resolve episode title mismatches between Plex and Trakt
        </p>
      </div>

      {loading && (
        <div className="flex justify-center h-40 items-center">
          <Spinner color="secondary" />
        </div>
      )}

      {fetchError && (
        <div className="bg-red-950/50 border border-red-800 rounded-lg p-4 mb-4">
          <p className="text-red-400 text-sm">{fetchError}</p>
        </div>
      )}

      {!loading && errors.length === 0 && !fetchError && (
        <Card className="bg-zinc-900 border border-zinc-800">
          <CardBody className="p-8 text-center">
            <p className="text-green-400 font-semibold mb-1">No mapping errors</p>
            <p className="text-zinc-500 text-sm">All episode titles matched successfully.</p>
          </CardBody>
        </Card>
      )}

      {!loading && errors.length > 0 && (
        <div className="space-y-6">
          <p className="text-zinc-400 text-sm">
            <span className="text-white font-semibold">{errors.length}</span>{" "}
            anime with unresolved episode title mismatches.
            Enter the correct Trakt episode title for each — leave blank to skip.
          </p>

          {errors.map((group) => {
            const k = groupKey(group);
            const groupFixes = fixes[k] ?? {};
            const filledCount = Object.values(groupFixes).filter((v) => v.trim()).length;

            return (
              <Card key={k} className="bg-zinc-900 border border-zinc-800">
                <CardBody className="p-6">
                  {/* Header */}
                  <div className="flex items-center justify-between mb-4">
                    <div className="flex items-center gap-3 min-w-0">
                      <span className="text-lg">{"\uD83C\uDF8C"}</span>
                      <span className="font-bold text-white text-lg">{group.plex_name ?? group.anime_name}</span>
                      <span className="text-zinc-600 text-xs">{group.anime_name}</span>
                      <Chip
                        size="sm"
                        variant="flat"
                        color={TYPE_CHIP_COLOR[group.episode_type] ?? "default"}
                      >
                        {group.episode_type}
                      </Chip>
                    </div>
                    <div className="flex items-center gap-2 shrink-0">
                      <a
                        href={`https://trakt.tv/search?query=${encodeURIComponent(group.plex_name ?? group.anime_name)}`}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="text-xs text-zinc-500 hover:text-violet-400 transition-colors"
                      >
                        {"Search Trakt \u2197"}
                      </a>
                    </div>
                  </div>

                  <p className="text-zinc-500 text-xs mb-4">
                    {(group.failed_episode_details?.length || group.failed_episodes.length)} failed episode{(group.failed_episode_details?.length || group.failed_episodes.length) !== 1 ? "s" : ""}{" "}
                    {"·"} last seen {group.timestamp}
                  </p>

                  {/* Episode rows */}
                  <div className="space-y-3 mb-5">
                    {(group.failed_episode_details?.length ? group.failed_episode_details : group.failed_episodes.map((e) => ({ number: null, name: e } as FailedEpisodeDetail))).map((ep) => (
                      <div key={ep.name} className="flex-1 min-w-0">
                        <p className="text-xs text-zinc-500 mb-1 truncate" title={ep.name}>
                          {ep.number != null ? <span className="text-zinc-400 font-mono mr-1">Ep.{ep.number}</span> : null}
                          AFL: {ep.name}
                        </p>
                        <Input
                          size="sm"
                          placeholder="Correct Trakt episode title…"
                          value={groupFixes[ep.name] ?? ""}
                          onValueChange={(v) => setFix(group, ep.name, v)}
                          classNames={{
                            inputWrapper: "bg-zinc-800 border-zinc-700",
                            input: "text-white text-sm",
                          }}
                        />
                      </div>
                    ))}
                  </div>

                  {/* Save row */}
                  <div className="flex items-center gap-3">
                    <Button
                      size="sm"
                      color="secondary"
                      variant="flat"
                      onPress={() => handleSave(group)}
                      isLoading={saving[k]}
                      isDisabled={filledCount === 0 || saving[k]}
                    >
                      {saved[k] ? "\u2713 Saved!" : `Save ${filledCount > 0 ? filledCount : ""} Fix${filledCount !== 1 ? "es" : ""}`}
                    </Button>
                    {saveErrors[k] && (
                      <p className="text-red-400 text-xs">{saveErrors[k]}</p>
                    )}
                    {saved[k] && (
                      <p className="text-green-400 text-xs">
                        Mappings saved — re-run the anime update to apply them.
                      </p>
                    )}
                  </div>
                </CardBody>
              </Card>
            );
          })}
        </div>
      )}
      {/* Saved Mappings */}
      {!loading && (
        <div className="mt-10">
          <div className="mb-4">
            <h2 className="text-xl font-bold text-white">Saved Mappings</h2>
            <p className="text-zinc-400 text-sm mt-1">
              Existing episode title mappings (Plex → Trakt). Click a row to edit.
            </p>
          </div>

          {titleMappings.length === 0 ? (
            <Card className="bg-zinc-900 border border-zinc-800">
              <CardBody className="p-8 text-center">
                <p className="text-zinc-500 text-sm">No saved mappings yet.</p>
              </CardBody>
            </Card>
          ) : (
            <div className="space-y-4">
              {titleMappings.map((group) => (
                <Card key={group.anime_name} className="bg-zinc-900 border border-zinc-800">
                  <CardBody className="p-5">
                    <p className="text-white font-semibold mb-3">{group.anime_name}</p>
                    <div className="space-y-2">
                      {group.matches.map((entry) => {
                        const k = entryKey(group.anime_name, entry.plex_title);
                        const isEditing = !!editState[k];
                        const isDeleting = deleting[k];
                        const isConfirming = confirmDelete === k;

                        return (
                          <div
                            key={entry.plex_title}
                            className={`rounded-lg bg-zinc-800/50 px-3 py-2 ${isEditing ? "flex flex-col gap-2" : "flex items-center gap-3"}`}
                          >
                            {isEditing ? (
                              <>
                                <div className="flex flex-col sm:flex-row gap-2">
                                  <Input
                                    size="sm"
                                    label="Plex title"
                                    value={editState[k].plexTitle}
                                    onValueChange={(v) =>
                                      setEditState((p) => ({ ...p, [k]: { ...p[k], plexTitle: v } }))
                                    }
                                    classNames={{
                                      inputWrapper: "bg-zinc-700 border-zinc-600",
                                      input: "text-white text-sm",
                                    }}
                                  />
                                  <Input
                                    size="sm"
                                    label="Trakt title"
                                    value={editState[k].traktTitle}
                                    onValueChange={(v) =>
                                      setEditState((p) => ({ ...p, [k]: { ...p[k], traktTitle: v } }))
                                    }
                                    classNames={{
                                      inputWrapper: "bg-zinc-700 border-zinc-600",
                                      input: "text-white text-sm",
                                    }}
                                  />
                                </div>
                                <div className="flex gap-2">
                                <Button
                                  size="sm"
                                  color="secondary"
                                  variant="flat"
                                  isLoading={editSaving[k]}
                                  onPress={() => saveEdit(group.anime_name, entry.plex_title)}
                                >
                                  Save
                                </Button>
                                <Button
                                  size="sm"
                                  variant="flat"
                                  onPress={() => cancelEdit(group.anime_name, entry.plex_title)}
                                >
                                  Cancel
                                </Button>
                                </div>
                              </>
                            ) : (
                              <>
                                <div className="flex flex-1 items-center gap-2 min-w-0 text-sm">
                                  <span className="text-zinc-300 truncate">{entry.plex_title}</span>
                                  <span className="text-zinc-600 shrink-0">→</span>
                                  <span className="text-violet-400 truncate">{entry.trakt_title}</span>
                                </div>
                                <Button
                                  size="sm"
                                  variant="light"
                                  className="text-zinc-400 hover:text-white shrink-0"
                                  onPress={() =>
                                    startEdit(group.anime_name, entry.plex_title, entry.trakt_title)
                                  }
                                >
                                  Edit
                                </Button>
                                {isConfirming ? (
                                  <>
                                    <Button
                                      size="sm"
                                      color="danger"
                                      variant="flat"
                                      isLoading={isDeleting}
                                      onPress={() => handleDelete(group.anime_name, entry.plex_title)}
                                    >
                                      Confirm
                                    </Button>
                                    <Button
                                      size="sm"
                                      variant="flat"
                                      onPress={() => setConfirmDelete(null)}
                                    >
                                      Cancel
                                    </Button>
                                  </>
                                ) : (
                                  <Button
                                    size="sm"
                                    variant="light"
                                    className="text-red-500 hover:text-red-400 shrink-0"
                                    isLoading={isDeleting}
                                    onPress={() => setConfirmDelete(k)}
                                  >
                                    Delete
                                  </Button>
                                )}
                              </>
                            )}
                          </div>
                        );
                      })}
                    </div>
                  </CardBody>
                </Card>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
