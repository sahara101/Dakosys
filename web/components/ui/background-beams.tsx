"use client";

export function BackgroundBeams({ className }: { className?: string }) {
  return (
    <div
      className={`absolute inset-0 overflow-hidden pointer-events-none ${className ?? ""}`}
      aria-hidden="true"
    >
      <svg
        className="absolute inset-0 w-full h-full"
        xmlns="http://www.w3.org/2000/svg"
      >
        <defs>
          <radialGradient id="beamGradient" cx="50%" cy="0%" r="80%">
            <stop offset="0%" stopColor="rgba(124,58,237,0.15)" />
            <stop offset="100%" stopColor="rgba(124,58,237,0)" />
          </radialGradient>
          <linearGradient id="beam1" x1="0%" y1="0%" x2="100%" y2="100%">
            <stop offset="0%" stopColor="rgba(124,58,237,0.3)" />
            <stop offset="100%" stopColor="rgba(99,102,241,0)" />
          </linearGradient>
          <linearGradient id="beam2" x1="100%" y1="0%" x2="0%" y2="100%">
            <stop offset="0%" stopColor="rgba(99,102,241,0.2)" />
            <stop offset="100%" stopColor="rgba(124,58,237,0)" />
          </linearGradient>
        </defs>
        <rect width="100%" height="100%" fill="url(#beamGradient)" />
        <line
          x1="20%" y1="0" x2="80%" y2="100%"
          stroke="url(#beam1)" strokeWidth="1" opacity="0.4"
        />
        <line
          x1="50%" y1="0" x2="10%" y2="100%"
          stroke="url(#beam2)" strokeWidth="1" opacity="0.3"
        />
        <line
          x1="70%" y1="0" x2="30%" y2="100%"
          stroke="url(#beam1)" strokeWidth="0.5" opacity="0.2"
        />
      </svg>
    </div>
  );
}
