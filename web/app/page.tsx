"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";

export default function Home() {
  const router = useRouter();
  useEffect(() => {
    fetch("/api/status")
      .then((r) => r.json())
      .then((data) => {
        if (data?.config_missing) {
          router.replace("/setup");
        } else {
          router.replace("/dashboard");
        }
      })
      .catch(() => router.replace("/dashboard"));
  }, [router]);
  return null;
}
