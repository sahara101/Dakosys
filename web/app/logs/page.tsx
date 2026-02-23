"use client";

import { useEffect, useState, useRef, useCallback } from "react";
import { Button, Chip, Tab, Tabs } from "@nextui-org/react";
import { api } from "@/lib/api";
import type { ServiceName } from "@/types/api";

type LogService = ServiceName | "main";

const SERVICES: { key: LogService; label: string; tag: string }[] = [
  { key: "main",                label: "All Logs",       tag: "Anime"     },
  { key: "anime_episode_type",  label: "Anime Episodes", tag: "Anime"     },
  { key: "tv_status_tracker",   label: "TV Status",      tag: "TV Status" },
  { key: "size_overlay",        label: "Size Overlay",   tag: "Size"      },
];

const TAG_COLOR: Record<string, string> = {
  "Anime":     "text-violet-400",
  "TV Status": "text-blue-400",
  "Size":      "text-yellow-400",
};

// Services to fetch when "All Logs" is selected
const ALL_SERVICES: { key: ServiceName; tag: string }[] = [
  { key: "anime_episode_type", tag: "Anime"     },
  { key: "tv_status_tracker",  tag: "TV Status" },
  { key: "size_overlay",       tag: "Size"      },
];

interface TaggedLine {
  line: string;
  tag: string;
}

function parseTimestamp(line: string): number {
  const m = line.match(/^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})/);
  if (m) return new Date(m[1]).getTime();
  const m2 = line.match(/^(\d{2}:\d{2}:\d{2})/);
  if (m2) return new Date(`1970-01-01T${m2[1]}`).getTime();
  return 0;
}

function stripTimestamp(line: string): string {
  return line
    .replace(/^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}(,\d+)?\s*/, "")
    .replace(/^\d{2}:\d{2}:\d{2}(,\d+)?\s*/, "");
}

function colorLine(line: string): string {
  if (/\[ERROR\]|❌/.test(line)) return "text-red-400";
  if (/\[WARNING\]|⚠️/.test(line)) return "text-yellow-400";
  if (/\[INFO\]|✓/.test(line)) return "text-green-400";
  if (/\[DEBUG\]|🔍/.test(line)) return "text-zinc-500";
  return "text-zinc-300";
}

export default function LogsPage() {
  const [service, setService] = useState<LogService>("main");
  const [lines, setLines] = useState<TaggedLine[]>([]);
  const [newLineCount, setNewLineCount] = useState(0);
  const [initialLoading, setInitialLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [autoScroll, setAutoScroll] = useState(true);
  const [showTime, setShowTime] = useState(false);
  const [showService, setShowService] = useState(true);
  const [hideDebug, setHideDebug] = useState(true);
  const [copied, setCopied] = useState(false);

  const containerRef = useRef<HTMLDivElement>(null);
  const bottomRef = useRef<HTMLDivElement>(null);
  const prevTailRef = useRef<string>("");

  const isNearBottom = useCallback(() => {
    const el = containerRef.current;
    if (!el) return true;
    return el.scrollHeight - el.scrollTop - el.clientHeight < 80;
  }, []);

  const scrollToBottom = useCallback((behavior: ScrollBehavior = "smooth") => {
    bottomRef.current?.scrollIntoView({ behavior });
  }, []);

  const fetchLogs = useCallback(
    async (reset = false) => {
      try {
        let incoming: TaggedLine[];

        if (service === "main") {
          const results = await Promise.all(
            ALL_SERVICES.map((s) => api.getLogs(s.key, 1000).then((r) => ({ lines: r.lines, tag: s.tag })))
          );
          const merged = results.flatMap(({ lines: ls, tag }) => ls.map((line) => ({ line, tag })));
          merged.sort((a, b) => parseTimestamp(a.line) - parseTimestamp(b.line));
          incoming = merged;
        } else {
          const svc = SERVICES.find((s) => s.key === service)!;
          const res = await api.getLogs(service as ServiceName, 1000);
          incoming = res.lines.map((line) => ({ line, tag: svc.tag }));
        }

        const newTail = incoming[incoming.length - 1]?.line ?? "";
        if (!reset && newTail === prevTailRef.current) return;

        const added = reset ? 0 : Math.max(0, incoming.length - lines.length);
        prevTailRef.current = newTail;
        setLines(incoming);
        setError(null);

        if (!reset && added > 0) {
          setNewLineCount(added);
          setTimeout(() => setNewLineCount(0), 3000);
        }
      } catch (e: unknown) {
        setError(e instanceof Error ? e.message : "Failed to load logs");
      } finally {
        if (reset) setInitialLoading(false);
      }
    },
    [service]
  );

  useEffect(() => {
    setLines([]);
    setNewLineCount(0);
    prevTailRef.current = "";
    setInitialLoading(true);
    setError(null);

    fetchLogs(true);
    const interval = setInterval(() => fetchLogs(false), 3000);
    return () => clearInterval(interval);
  }, [service, fetchLogs]);

  useEffect(() => {
    if (lines.length === 0) return;
    if (autoScroll || initialLoading) {
      scrollToBottom(initialLoading ? "instant" : "smooth");
    }
  }, [lines, autoScroll, initialLoading, scrollToBottom]);

  const handleScroll = useCallback(() => {
    setAutoScroll(isNearBottom());
  }, [isNearBottom]);

  const visibleLines = hideDebug
    ? lines.filter(({ line }) => !/\[DEBUG\]|🔍/.test(line))
    : lines;

  const handleCopy = useCallback(() => {
    const text = visibleLines.map(({ line, tag }) => {
      const display = showTime ? line : stripTimestamp(line);
      return showService ? `[${tag}] ${display}` : display;
    }).join("\n");
    navigator.clipboard.writeText(text).then(() => {
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    });
  }, [visibleLines, showTime, showService]);

  return (
    <div>
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between mb-6 gap-3">
        <div>
          <h1 className="text-3xl font-bold text-white">Logs</h1>
          <p className="text-zinc-400 mt-1">Live tail · updates every 3s</p>
        </div>
        <div className="flex items-center gap-3 flex-wrap">
          {newLineCount > 0 && (
            <Chip size="sm" color="secondary" variant="flat">
              +{newLineCount} new
            </Chip>
          )}
          <label className="flex items-center gap-1.5 text-sm text-zinc-400 cursor-pointer select-none">
            <input
              type="checkbox"
              checked={showTime}
              onChange={(e) => setShowTime(e.target.checked)}
              className="accent-violet-500"
            />
            Time
          </label>
          <label className="flex items-center gap-1.5 text-sm text-zinc-400 cursor-pointer select-none">
            <input
              type="checkbox"
              checked={showService}
              onChange={(e) => setShowService(e.target.checked)}
              className="accent-violet-500"
            />
            Service
          </label>
          <label className="flex items-center gap-1.5 text-sm text-zinc-400 cursor-pointer select-none">
            <input
              type="checkbox"
              checked={hideDebug}
              onChange={(e) => setHideDebug(e.target.checked)}
              className="accent-violet-500"
            />
            Hide DEBUG
          </label>
          <label className="flex items-center gap-1.5 text-sm text-zinc-400 cursor-pointer select-none">
            <input
              type="checkbox"
              checked={autoScroll}
              onChange={(e) => setAutoScroll(e.target.checked)}
              className="accent-violet-500"
            />
            Auto-scroll
          </label>
          <Button
            size="sm"
            variant="flat"
            color="secondary"
            onPress={() => {
              prevTailRef.current = "";
              setAutoScroll(true);
              fetchLogs(true).then(() => scrollToBottom("instant"));
            }}
          >
            Reload
          </Button>
        </div>
      </div>

      <div className="overflow-x-auto">
        <Tabs
          aria-label="Log service selector"
          selectedKey={service}
          onSelectionChange={(k) => setService(k as LogService)}
          classNames={{
            tabList: "bg-zinc-900 border border-zinc-800",
            tab: "text-zinc-400",
            cursor: "bg-violet-600",
          }}
          className="mb-4"
        >
          {SERVICES.map((svc) => (
            <Tab key={svc.key} title={svc.label} />
          ))}
        </Tabs>
      </div>

      {error && (
        <div className="bg-red-950/50 border border-red-800 rounded-lg p-4 mb-4">
          <p className="text-red-400 text-sm">{error}</p>
        </div>
      )}

      <div className="relative">
        <button
          onClick={handleCopy}
          title={copied ? "Copied!" : "Copy logs"}
          className="absolute top-2 right-2 z-10 p-1.5 rounded text-zinc-500 hover:text-zinc-300 hover:bg-zinc-800 transition-colors"
        >
          {copied ? (
            <svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <polyline points="20 6 9 17 4 12" />
            </svg>
          ) : (
            <svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <rect x="9" y="9" width="13" height="13" rx="2" ry="2" />
              <path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1" />
            </svg>
          )}
        </button>
      <div
        ref={containerRef}
        onScroll={handleScroll}
        className="bg-zinc-950 border border-zinc-800 rounded-lg p-4 h-[68vh] overflow-y-auto font-mono text-xs"
      >
        {initialLoading ? (
          <p className="text-zinc-600 text-center mt-8">Loading…</p>
        ) : visibleLines.length === 0 ? (
          <p className="text-zinc-600 text-center mt-8">No log entries found.</p>
        ) : (
          visibleLines.map(({ line, tag }, i) => {
            const display = showTime ? line : stripTimestamp(line);
            return (
              <div key={i} className={`leading-5 ${colorLine(line)}`}>
                {showService && (
                  <span className={`${TAG_COLOR[tag] ?? "text-zinc-500"} mr-1.5 select-none`}>
                    [{tag}]
                  </span>
                )}
                {display || "\u00a0"}
              </div>
            );
          })
        )}
        <div ref={bottomRef} />
      </div>
      </div>
    </div>
  );
}
