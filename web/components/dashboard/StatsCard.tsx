"use client";

import { Card, CardBody } from "@nextui-org/react";
import { NumberTicker } from "@/components/ui/number-ticker";

interface StatsCardProps {
  label: string;
  value: number;
  unit?: string;
  decimals?: number;
  icon: string;
  subtitle?: string;
}

export function StatsCard({ label, value, unit, decimals = 0, icon, subtitle }: StatsCardProps) {
  return (
    <Card className="bg-zinc-900 border border-zinc-800">
      <CardBody className="p-5">
        <div className="flex items-center justify-between">
          <div>
            <p className="text-zinc-400 text-xs font-medium uppercase tracking-wider mb-1">
              {label}
            </p>
            <div className="flex items-baseline gap-1">
              <NumberTicker
                value={value}
                decimals={decimals}
                className="text-3xl font-bold text-white"
              />
              {unit && <span className="text-sm text-zinc-400">{unit}</span>}
            </div>
            {subtitle && <p className="text-zinc-500 text-xs mt-1">{subtitle}</p>}
          </div>
          <div className="text-4xl opacity-50">{icon}</div>
        </div>
      </CardBody>
    </Card>
  );
}
