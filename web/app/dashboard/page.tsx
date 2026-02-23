"use client";

import { useEffect, useState, useCallback } from "react";
import { useRouter } from "next/navigation";
import { Card, CardBody, Spinner } from "@nextui-org/react";
import { api } from "@/lib/api";
import type { StatusResponse } from "@/types/api";
import { ServiceHealthCard } from "@/components/dashboard/ServiceHealthCard";
import { StatsCard } from "@/components/dashboard/StatsCard";
import { NumberTicker } from "@/components/ui/number-ticker";
import { BackgroundBeams } from "@/components/ui/background-beams";

const SERVICE_LABELS: Record<string, string> = {
  anime_episode_type: "Anime Episodes",
  tv_status_tracker: "TV Status",
  size_overlay: "Size Overlay",
};

export default function DashboardPage() {
  const router = useRouter();
  const [data, setData] = useState<StatusResponse | null>(null);
  const [animeCount, setAnimeCount] = useState(0);
  const [traktCount, setTraktCount] = useState(0);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  const fetchData = useCallback(async () => {
    try {
      const [res, animeRes, traktRes] = await Promise.all([
        api.getStatus(),
        api.getAnimeSchedule(),
        api.getTraktLists(),
      ]);
      if (res.config_missing) {
        router.replace("/setup");
        return;
      }
      setData(res);
      setAnimeCount(animeRes.count);
      setTraktCount(traktRes.total);
      setError(null);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Failed to load status");
    } finally {
      setLoading(false);
    }
  }, [router]);

  useEffect(() => {
    fetchData();
    const interval = setInterval(fetchData, 30000);
    return () => clearInterval(interval);
  }, [fetchData]);

  return (
    <div className="relative min-h-full">
      <BackgroundBeams className="opacity-40" />
      <div className="relative z-10">
        <div className="mb-8">
          <h1 className="text-3xl font-bold text-white">Dashboard</h1>
          <p className="text-zinc-400 mt-1">DAKOSYS service health and statistics</p>
        </div>

        {loading && (
          <div className="flex items-center justify-center h-40">
            <Spinner color="secondary" size="lg" />
          </div>
        )}

        {error && (
          <div className="bg-red-950/50 border border-red-800 rounded-lg p-4 mb-6">
            <p className="text-red-400 text-sm">{error}</p>
          </div>
        )}

        {data && (
          <>
            {/* Stats row */}
            <div className="grid grid-cols-1 sm:grid-cols-3 gap-4 mb-8">
              <StatsCard
                label="TV Shows Tracked"
                value={data.stats.total_shows}
                icon="📺"
              />
              <StatsCard
                label="Total Size"
                value={data.stats.total_size_gb}
                unit="GB"
                decimals={1}
                icon="💾"
                subtitle={`across ${data.stats.total_libraries} ${data.stats.total_libraries === 1 ? "library" : "libraries"}`}
              />
              <Card className="bg-zinc-900 border border-zinc-800">
                <CardBody className="p-5">
                  <div className="flex items-center justify-between">
                    <div className="flex-1">
                      <p className="text-zinc-400 text-xs font-medium uppercase tracking-wider mb-3">
                        Anime
                      </p>
                      <div className="flex items-center gap-6">
                        <div>
                          <NumberTicker value={animeCount} className="text-3xl font-bold text-white" />
                          <p className="text-zinc-500 text-xs mt-1">scheduled</p>
                        </div>
                        <div className="w-px h-8 bg-zinc-700" />
                        <div>
                          <NumberTicker value={traktCount} className="text-3xl font-bold text-white" />
                          <p className="text-zinc-500 text-xs mt-1">trakt lists</p>
                        </div>
                      </div>
                    </div>
                    <div className="text-4xl opacity-50">🎌</div>
                  </div>
                </CardBody>
              </Card>
            </div>

            {/* Services row */}
            <div className="mb-4">
              <h2 className="text-lg font-semibold text-white mb-4">Services</h2>
              <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
                {(["anime_episode_type", "tv_status_tracker", "size_overlay"] as const).map(
                  (key) => (
                    <ServiceHealthCard
                      key={key}
                      name={SERVICE_LABELS[key]}
                      serviceKey={key}
                      status={data.services[key]}
                      onRefresh={fetchData}
                    />
                  )
                )}
              </div>
            </div>
          </>
        )}
      </div>
    </div>
  );
}
