"use client";

import { useState, useEffect, useRef, useCallback } from "react";
import { Button } from "@nextui-org/react";
import { api } from "@/lib/api";
import type { ServiceName } from "@/types/api";

const SERVICE_DESCRIPTIONS: Record<ServiceName, string> = {
  anime_episode_type:
    "Fetches episode lists from AnimeFillerList, matches them with Trakt.tv episodes, and updates Filler / Canon / Mixed lists. Generates Kometa overlay YAML files.",
  tv_status_tracker:
    "Scans your Plex libraries, fetches current show status from Trakt, updates Kometa overlay files, and sends Discord notifications for any status changes.",
  size_overlay:
    "Calculates file sizes for all media in your Plex libraries, generates size overlay YAML files for Kometa, and reports changes since the last run.",
};

function storageKey(service: ServiceName) {
  return `dakosys_running_${service}`;
}

function isStoredRunning(service: ServiceName): boolean {
  if (typeof window === "undefined") return false;
  try {
    const raw = localStorage.getItem(storageKey(service));
    if (!raw) return false;
    const { ts } = JSON.parse(raw) as { ts: number };
    if (Date.now() - ts > 2 * 60 * 60 * 1000) {
      localStorage.removeItem(storageKey(service));
      return false;
    }
    return true;
  } catch {
    return false;
  }
}

function colorLine(line: string): string {
  if (/\[ERROR\]|❌/.test(line)) return "text-red-400";
  if (/\[WARNING\]|⚠️/.test(line)) return "text-yellow-400";
  if (/\[INFO\]|✓/.test(line)) return "text-green-300";
  return "text-zinc-400";
}

interface RunServiceButtonProps {
  service: ServiceName;
  label?: string;
  onComplete?: () => void;
}

export function RunServiceButton({ service, label, onComplete }: RunServiceButtonProps) {
  const [running, setRunning] = useState<boolean>(() => isStoredRunning(service));
  const [message, setMessage] = useState<string | null>(null);
  const [logLines, setLogLines] = useState<string[]>([]);
  const logContainerRef = useRef<HTMLDivElement>(null);
  const prevLogTail = useRef("");

  const displayLabel =
    label ?? service.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());

  useEffect(() => {
    if (!isStoredRunning(service)) return;
    api.getRunStatus(service)
      .then((s) => {
        if (!s.running) {
          setRunning(false);
          localStorage.removeItem(storageKey(service));
        }
      })
      .catch(() => {
      });
  }, [service]);

  useEffect(() => {
    if (!running) return;
    const interval = setInterval(async () => {
      try {
        const s = await api.getRunStatus(service);
        if (!s.running) {
          setRunning(false);
          localStorage.removeItem(storageKey(service));
          setMessage("Completed");
          onComplete?.();
          setTimeout(() => setMessage(null), 4000);
        }
      } catch {
      }
    }, 2000);
    return () => clearInterval(interval);
  }, [running, service, onComplete]);

  const fetchLogTail = useCallback(async () => {
    try {
      const res = await api.getLogs(service, 40);
      const lines = res.lines;
      if (lines.length === 0) return;
      const tail = lines[lines.length - 1];
      if (tail === prevLogTail.current) return;
      prevLogTail.current = tail;
      setLogLines(lines.filter((l) => !/\[DEBUG\]|🔍/.test(l)));
    } catch {
    }
  }, [service]);

  useEffect(() => {
    if (!running) return;
    fetchLogTail();
    const interval = setInterval(fetchLogTail, 3000);
    return () => clearInterval(interval);
  }, [running, fetchLogTail]);

  useEffect(() => {
    const el = logContainerRef.current;
    if (el) el.scrollTop = el.scrollHeight;
  }, [logLines]);

  const handleRun = async () => {
    try {
      setMessage(null);
      setLogLines([]);
      prevLogTail.current = "";
      const res = await api.triggerRun(service);
      if (res.started) {
        setRunning(true);
        localStorage.setItem(storageKey(service), JSON.stringify({ ts: Date.now() }));
      } else {
        setMessage(res.message);
      }
    } catch (e: unknown) {
      setMessage(e instanceof Error ? e.message : "Error starting run");
    }
  };

  return (
    <div className="w-full">
      <div className="flex items-center gap-3">
        <Button
          size="sm"
          color="secondary"
          variant="flat"
          isLoading={running}
          onPress={handleRun}
          className="font-medium"
        >
          {running ? "Running…" : `Run ${displayLabel}`}
        </Button>
        {message && !running && (
          <span className="text-xs text-green-400">{message}</span>
        )}
      </div>

      {running && (
        <div className="mt-3 rounded-lg border border-violet-800/40 bg-violet-950/20 overflow-hidden">
          <div className="px-4 py-2 border-b border-violet-800/30 flex items-center gap-2">
            <span className="inline-block w-2 h-2 rounded-full bg-violet-400 animate-pulse" />
            <span className="text-xs text-violet-300 font-medium">Running — what this does:</span>
          </div>
          <p className="px-4 py-2 text-xs text-zinc-400 border-b border-violet-800/20">
            {SERVICE_DESCRIPTIONS[service]}
          </p>
          <div ref={logContainerRef} className="px-3 py-2 max-h-40 overflow-y-auto font-mono text-xs space-y-0.5">
            {logLines.length === 0 ? (
              <p className="text-zinc-600 italic">Waiting for log output…</p>
            ) : (
              logLines.map((line, i) => (
                <div key={i} className={colorLine(line)}>{line || "\u00a0"}</div>
              ))
            )}
          </div>
        </div>
      )}
    </div>
  );
}
