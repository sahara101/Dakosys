"use client";

import { useEffect, useState, useMemo } from "react";
import {
  Card,
  CardBody,
  Chip,
  Input,
  Spinner,
  Switch,
  Table,
  TableHeader,
  TableColumn,
  TableBody,
  TableRow,
  TableCell,
} from "@nextui-org/react";
import { api } from "@/lib/api";
import type { TVShow, StatusResponse } from "@/types/api";
import { StatusBadge } from "@/components/tv-status/StatusBadge";
import { Spotlight } from "@/components/ui/spotlight";
import { RunServiceButton } from "@/components/shared/RunServiceButton";

type SortKey = "title" | "status" | "date";

const STATUS_LABELS: Record<string, string> = {
  AIRING: "Airing",
  RETURNING: "Returning",
  SEASON_PREMIERE: "Season Premiere",
  SEASON_FINALE: "Season Finale",
  MID_SEASON_FINALE: "Mid-Season Finale",
  FINAL_EPISODE: "Final Episode",
  ENDED: "Ended",
  CANCELLED: "Cancelled",
};

function formatNextRun(iso: string | null): string {
  if (!iso) return "—";
  try { return new Date(iso).toLocaleString(); } catch { return iso; }
}

export default function TVStatusPage() {
  const [shows, setShows] = useState<TVShow[]>([]);
  const [status, setStatus] = useState<StatusResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [search, setSearch] = useState("");
  const [statusFilter, setStatusFilter] = useState<string | null>(null);
  const [sortKey, setSortKey] = useState<SortKey>("title");
  const [sortAsc, setSortAsc] = useState(true);

  const fetchData = async () => {
    try {
      const [res, s] = await Promise.all([api.getTVStatus(), api.getStatus()]);
      setShows(res.shows);
      setStatus(s);
      setError(null);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Failed to load TV status");
    } finally {
      setLoading(false);
    }
  };

  const svc = status?.services.tv_status_tracker;

  useEffect(() => {
    fetchData();
  }, []);

  const activeStatuses = useMemo(() => {
    const seen = new Set<string>();
    shows.forEach((s) => seen.add(s.status));
    return Array.from(seen).sort();
  }, [shows]);

  const filtered = useMemo(() => {
    const q = search.toLowerCase();
    return shows
      .filter((s) => {
        const matchesSearch =
          s.title.toLowerCase().includes(q) ||
          s.status.toLowerCase().includes(q);
        const matchesStatus = !statusFilter || s.status === statusFilter;
        return matchesSearch && matchesStatus;
      })
      .sort((a, b) => {
        const av = a[sortKey] ?? "";
        const bv = b[sortKey] ?? "";
        return sortAsc ? av.localeCompare(bv) : bv.localeCompare(av);
      });
  }, [shows, search, statusFilter, sortKey, sortAsc]);

  const toggleSort = (key: SortKey) => {
    if (sortKey === key) setSortAsc((v) => !v);
    else { setSortKey(key); setSortAsc(true); }
  };

  const headerCell = (key: SortKey, label: string) => (
    <button
      className="flex items-center gap-1 text-xs font-semibold uppercase tracking-wider text-zinc-400 hover:text-white transition-colors"
      onClick={() => toggleSort(key)}
    >
      {label}
      {sortKey === key && (
        <span className="text-violet-400">{sortAsc ? "↑" : "↓"}</span>
      )}
    </button>
  );

  return (
    <div>
      <Spotlight className="rounded-2xl mb-4 p-6 bg-zinc-900/50 border border-zinc-800">
        <div className="flex flex-col gap-4">
          <div className="flex items-center justify-between">
            <div>
              <h1 className="text-3xl font-bold text-white">TV Status</h1>
              <p className="text-zinc-400 mt-1">{shows.length} shows tracked</p>
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
          <RunServiceButton service="tv_status_tracker" label="Update TV Status" onComplete={fetchData} />
        </div>
      </Spotlight>

      {svc && (
        <Card className="bg-zinc-900 border border-zinc-800 mb-6">
          <CardBody className="p-4">
            <div className="flex items-center justify-between">
              <Switch
                isSelected={svc.enabled}
                onValueChange={async (val) => {
                  await api.setServiceEnabled("tv_status_tracker", val);
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

      <div className="flex flex-wrap gap-2 mb-3">
        {activeStatuses.map((s) => (
          <button
            key={s}
            onClick={() => setStatusFilter(statusFilter === s ? null : s)}
            className={`px-3 py-1 rounded-full text-xs font-medium border transition-all ${
              statusFilter === s
                ? "bg-violet-600 border-violet-500 text-white"
                : "bg-zinc-800 border-zinc-700 text-zinc-400 hover:text-white hover:border-zinc-500"
            }`}
          >
            {STATUS_LABELS[s] ?? s}
            <span className="ml-1.5 text-zinc-400 font-mono">
              {shows.filter((x) => x.status === s).length}
            </span>
          </button>
        ))}
      </div>

      <div className="mb-4">
        <Input
          placeholder="Search shows or status…"
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

      {loading && (
        <div className="flex justify-center h-40 items-center">
          <Spinner color="secondary" />
        </div>
      )}

      {error && (
        <div className="bg-red-950/50 border border-red-800 rounded-lg p-4">
          <p className="text-red-400 text-sm">{error}</p>
        </div>
      )}

      {!loading && !error && (
        <Table
          aria-label="TV shows status table"
          classNames={{
            wrapper: "bg-zinc-900 border border-zinc-800",
            th: "bg-zinc-800 text-zinc-400",
            td: "text-white",
          }}
        >
          <TableHeader>
            <TableColumn key="title">{headerCell("title", "Title")}</TableColumn>
            <TableColumn key="status">{headerCell("status", "Status")}</TableColumn>
          </TableHeader>
          <TableBody emptyContent="No shows found">
            {filtered.map((show) => (
              <TableRow key={show.title}>
                <TableCell className="font-medium">{show.title}</TableCell>
                <TableCell>
                  <div className="flex items-center gap-2">
                    <StatusBadge status={show.status} />
                    {show.date && (
                      <span className="text-zinc-500 text-xs">{show.date}</span>
                    )}
                  </div>
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      )}
    </div>
  );
}
