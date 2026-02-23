"use client";

import { useEffect, useState } from "react";
import {
  Accordion,
  AccordionItem,
  Card,
  CardBody,
  Chip,
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
import type { Library, StatusResponse } from "@/types/api";
import { RunServiceButton } from "@/components/shared/RunServiceButton";
import { Spotlight } from "@/components/ui/spotlight";

function formatSize(gb: number): string {
  if (gb >= 1000) return `${(gb / 1024).toFixed(2)} TB`;
  return `${gb.toFixed(2)} GB`;
}

function formatDate(iso: string): string {
  if (!iso) return "—";
  try {
    return new Date(iso).toLocaleString();
  } catch {
    return iso;
  }
}

function LibraryCard({ lib }: { lib: Library }) {
  return (
    <Card className="bg-zinc-900 border border-zinc-800">
      <CardBody className="p-0">
        <Accordion>
          <AccordionItem
            key={lib.name}
            aria-label={lib.name}
            title={
              <div className="flex items-center justify-between w-full pr-4">
                <div>
                  <p className="font-semibold text-white">{lib.name}</p>
                  <p className="text-zinc-400 text-xs mt-0.5">
                    Updated {formatDate(lib.last_updated)}
                  </p>
                </div>
                <div className="flex items-center gap-3">
                  <Chip size="sm" variant="flat" color="secondary">
                    {lib.item_count} items
                  </Chip>
                  {lib.episode_count !== null && (
                    <Chip size="sm" variant="flat" color="primary">
                      {lib.episode_count} eps
                    </Chip>
                  )}
                  <span className="text-violet-300 font-semibold text-sm">
                    {formatSize(lib.total_size_gb)}
                  </span>
                </div>
              </div>
            }
            classNames={{
              title: "w-full",
              trigger: "px-5 py-4",
            }}
          >
            <div className="px-4 pb-4 overflow-x-auto">
              <Table
                aria-label={`Items in ${lib.name}`}
                classNames={{
                  wrapper: "bg-zinc-950 border border-zinc-800 shadow-none",
                  th: "bg-zinc-800 text-zinc-400",
                  td: "text-zinc-200",
                }}
              >
                <TableHeader>
                  <TableColumn key="title">Title</TableColumn>
                  <TableColumn key="size">Size</TableColumn>
                  {lib.episode_count !== null ? (
                    <TableColumn key="eps">Episodes</TableColumn>
                  ) : (
                    <TableColumn key="empty"> </TableColumn>
                  )}
                </TableHeader>
                <TableBody emptyContent="No items">
                  {lib.items.map((item) => (
                    <TableRow key={item.title}>
                      <TableCell className="font-medium">{item.title}</TableCell>
                      <TableCell className="text-violet-300">
                        {formatSize(item.size_gb)}
                      </TableCell>
                      <TableCell className="text-zinc-400">
                        {item.episode_count != null ? `${item.episode_count} eps` : "—"}
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </div>
          </AccordionItem>
        </Accordion>
      </CardBody>
    </Card>
  );
}

export default function LibrariesPage() {
  const [libraries, setLibraries] = useState<Library[]>([]);
  const [status, setStatus] = useState<StatusResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const fetchData = async () => {
    try {
      const [res, s] = await Promise.all([api.getLibraries(), api.getStatus()]);
      setLibraries(res.libraries);
      setStatus(s);
      setError(null);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Failed to load libraries");
    } finally {
      setLoading(false);
    }
  };

  const svc = status?.services.size_overlay;

  useEffect(() => {
    fetchData();
  }, []);

  const totalSize = libraries.reduce((sum, lib) => sum + lib.total_size_gb, 0);

  return (
    <div>
      <Spotlight className="rounded-2xl mb-4 p-6 bg-zinc-900/50 border border-zinc-800">
        <div className="flex flex-col gap-4">
          <div className="flex items-center justify-between">
            <div>
              <h1 className="text-3xl font-bold text-white">Libraries</h1>
              <p className="text-zinc-400 mt-1">
                {libraries.length} libraries · {formatSize(totalSize)} total
              </p>
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
          <RunServiceButton service="size_overlay" label="Update Size Overlay" onComplete={fetchData} />
        </div>
      </Spotlight>

      {svc && (
        <Card className="bg-zinc-900 border border-zinc-800 mb-6">
          <CardBody className="p-4">
            <div className="flex items-center justify-between">
              <Switch
                isSelected={svc.enabled}
                onValueChange={async (val) => {
                  await api.setServiceEnabled("size_overlay", val);
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
                <p className="text-violet-300 font-semibold">
                  {svc.next_run ? formatDate(svc.next_run) : "—"}
                </p>
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

      {!loading && !error && libraries.length === 0 && (
        <div className="text-center text-zinc-500 py-16">
          <p className="text-4xl mb-3">🗂️</p>
          <p>No library data found. Run the Size Overlay service first.</p>
        </div>
      )}

      <div className="space-y-4">
        {libraries.map((lib) => (
          <LibraryCard key={lib.name} lib={lib} />
        ))}
      </div>
    </div>
  );
}
