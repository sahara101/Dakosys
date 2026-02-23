"use client";

import { useState } from "react";
import { usePathname } from "next/navigation";
import { Navbar } from "@/components/layout/Navbar";

export function ConditionalLayout({ children }: { children: React.ReactNode }) {
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false);
  const pathname = usePathname().replace(/\/$/, "") || "/";

  if (pathname === "/setup") {
    return <div className="min-h-screen p-4 sm:p-6">{children}</div>;
  }

  return (
    <div className="flex min-h-screen">
      {/* Mobile top bar — only visible below md breakpoint */}
      <div className="fixed top-0 left-0 right-0 h-14 bg-zinc-950 border-b border-zinc-800 flex items-center px-4 gap-3 z-40 md:hidden">
        <button
          onClick={() => setMobileMenuOpen(true)}
          className="text-zinc-400 hover:text-white p-1 -ml-1"
          aria-label="Open menu"
        >
          <svg className="w-6 h-6" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 6h16M4 12h16M4 18h16" />
          </svg>
        </button>
        <div className="flex items-center gap-2">
          <div className="w-7 h-7 rounded-lg bg-gradient-to-br from-violet-600 to-indigo-600 flex items-center justify-center text-white font-bold text-xs">
            D
          </div>
          <span className="font-bold text-white text-sm">DAKOSYS</span>
        </div>
      </div>

      {/* Overlay backdrop when mobile menu is open */}
      {mobileMenuOpen && (
        <div
          className="fixed inset-0 bg-black/60 z-40 md:hidden"
          onClick={() => setMobileMenuOpen(false)}
        />
      )}

      <Navbar isOpen={mobileMenuOpen} onClose={() => setMobileMenuOpen(false)} />

      <main className="flex-1 ml-0 md:ml-64 pt-14 md:pt-0 p-4 md:p-6 min-w-0">
        {children}
      </main>
    </div>
  );
}
