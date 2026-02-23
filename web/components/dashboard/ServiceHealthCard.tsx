"use client";

import { Card, CardBody, Chip } from "@nextui-org/react";
import { RunServiceButton } from "@/components/shared/RunServiceButton";
import type { ServiceStatus, ServiceName } from "@/types/api";

interface ServiceHealthCardProps {
  name: string;
  serviceKey: ServiceName;
  status: ServiceStatus;
  onRefresh: () => void;
}

function formatNextRun(iso: string | null): string {
  if (!iso) return "—";
  try {
    const d = new Date(iso);
    const now = new Date();
    const diffMs = d.getTime() - now.getTime();
    if (diffMs < 0) return "Due now";
    const diffMin = Math.floor(diffMs / 60000);
    if (diffMin < 60) return `in ${diffMin}m`;
    const diffH = Math.floor(diffMin / 60);
    if (diffH < 24) return `in ${diffH}h ${diffMin % 60}m`;
    return d.toLocaleString();
  } catch {
    return iso;
  }
}

const SERVICE_ICONS: Record<ServiceName, string> = {
  anime_episode_type: "🎌",
  tv_status_tracker: "📺",
  size_overlay: "💾",
};

export function ServiceHealthCard({
  name,
  serviceKey,
  status,
  onRefresh,
}: ServiceHealthCardProps) {
  return (
    <Card className="bg-zinc-900 border border-zinc-800">
      <CardBody className="p-5">
        <div className="flex items-start justify-between mb-4">
          <div className="flex items-center gap-2">
            <span className="text-2xl">{SERVICE_ICONS[serviceKey]}</span>
            <div>
              <p className="font-semibold text-white text-sm">{name}</p>
              <p className="text-zinc-500 text-xs capitalize">{serviceKey.replace(/_/g, " ")}</p>
            </div>
          </div>
          <Chip
            size="sm"
            variant="flat"
            color={status.running ? "warning" : status.enabled ? "success" : "default"}
          >
            {status.running ? "Running" : status.enabled ? "Active" : "Disabled"}
          </Chip>
        </div>

        <div className="space-y-2 text-xs text-zinc-400 mb-4">
          <div className="flex justify-between">
            <span>Status</span>
            <span className={status.enabled ? "text-green-400" : "text-zinc-500"}>
              {status.enabled ? "Enabled" : "Disabled"}
            </span>
          </div>
          <div className="flex justify-between">
            <span>Next run</span>
            <span className="text-violet-400">{formatNextRun(status.next_run)}</span>
          </div>
        </div>

        {status.enabled && (
          <RunServiceButton service={serviceKey} label={name} onComplete={onRefresh} />
        )}
      </CardBody>
    </Card>
  );
}
