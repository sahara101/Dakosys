"use client";

import { Chip } from "@nextui-org/react";

type ChipColor = "success" | "default" | "danger" | "primary" | "secondary" | "warning";

const STATUS_CONFIG: Record<string, { color: ChipColor; label: string }> = {
  AIRING: { color: "success", label: "Airing" },
  ENDED: { color: "default", label: "Ended" },
  CANCELLED: { color: "danger", label: "Cancelled" },
  RETURNING: { color: "primary", label: "Returning" },
  SEASON_FINALE: { color: "secondary", label: "Season Finale" },
  MID_SEASON_FINALE: { color: "warning", label: "Mid-Season Finale" },
  FINAL_EPISODE: { color: "danger", label: "Final Episode" },
  SEASON_PREMIERE: { color: "success", label: "Season Premiere" },
};

export function StatusBadge({ status }: { status: string }) {
  const cfg = STATUS_CONFIG[status.toUpperCase()] ?? {
    color: "default" as ChipColor,
    label: status,
  };
  return (
    <Chip size="sm" color={cfg.color} variant="flat">
      {cfg.label}
    </Chip>
  );
}
