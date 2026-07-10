import { useCallback, useEffect, useId, useRef, useState } from "react";

interface TrampStampButterflyProps {
  active: boolean;
  balance: number;
  onComplete: () => void;
}

interface TrampStampBadgeProps {
  balance: number;
}

const FULL_ANIMATION_MS = 5000;
const REDUCED_MOTION_HOLD_MS = 1600;

function stampBalanceLabel(balance: number) {
  return `${balance} ${balance === 1 ? "TRAMP-Stamp" : "TRAMP-Stamps"}`;
}

function normalizedBalance(balance: number) {
  return Number.isFinite(balance) ? Math.max(0, Math.trunc(balance)) : 0;
}

function usePrefersReducedMotion() {
  const [prefersReducedMotion, setPrefersReducedMotion] = useState(() =>
    typeof window !== "undefined" && typeof window.matchMedia === "function"
      ? window.matchMedia("(prefers-reduced-motion: reduce)").matches
      : false,
  );

  useEffect(() => {
    if (typeof window === "undefined" || typeof window.matchMedia !== "function") {
      return;
    }

    const mediaQuery = window.matchMedia("(prefers-reduced-motion: reduce)");
    const updatePreference = () => setPrefersReducedMotion(mediaQuery.matches);
    updatePreference();
    mediaQuery.addEventListener?.("change", updatePreference);
    return () => mediaQuery.removeEventListener?.("change", updatePreference);
  }, []);

  return prefersReducedMotion;
}

function ButterflyArtwork({
  className,
  variant,
}: {
  className: string;
  variant: "animated" | "static";
}) {
  const instanceId = useId().replaceAll(":", "");
  const blueGradientId = `${instanceId}-tramp-blue`;
  const blueGlowId = `${instanceId}-tramp-blue-glow`;
  const goldGradientId = `${instanceId}-tramp-gold`;
  const shadowId = `${instanceId}-tramp-shadow`;
  const leftWingClass =
    variant === "animated"
      ? "tramp-stamp-wing tramp-stamp-wing-left"
      : "tramp-stamp-static-wing";
  const rightWingClass =
    variant === "animated"
      ? "tramp-stamp-wing tramp-stamp-wing-right"
      : "tramp-stamp-static-wing";
  const bodyClass =
    variant === "animated" ? "tramp-stamp-body" : "tramp-stamp-static-body";

  const leftWing = (
    <>
      <path
        className="tramp-stamp-wing-surface"
        d="M158 147C137 122 128 83 98 53C74 29 39 25 21 47C2 70 18 108 52 131C79 149 119 154 158 147Z"
        fill={`url(#${blueGradientId})`}
        stroke={`url(#${goldGradientId})`}
        strokeWidth="5"
        strokeLinejoin="round"
      />
      <path
        className="tramp-stamp-wing-surface"
        d="M157 151C127 151 94 160 70 187C48 212 53 240 73 247C93 254 114 232 130 205C136 231 145 262 157 284C164 246 163 194 157 151Z"
        fill={`url(#${blueGradientId})`}
        stroke={`url(#${goldGradientId})`}
        strokeWidth="5"
        strokeLinejoin="round"
      />
      <path
        d="M143 140C124 121 122 91 96 69C78 53 53 47 38 59C25 70 29 91 44 107C62 126 94 137 143 140Z"
        fill={`url(#${blueGlowId})`}
        stroke="#e7bd62"
        strokeWidth="2.6"
        opacity="0.96"
      />
      <path
        d="M139 158C112 159 91 171 79 190C68 207 71 224 83 228C98 232 113 210 126 181"
        fill="none"
        stroke="#edc96f"
        strokeWidth="3.2"
        strokeLinecap="round"
      />
      <path
        d="M131 127C112 116 101 98 104 83C107 70 119 67 126 75C134 84 126 94 118 91C109 87 108 76 113 69"
        fill="none"
        stroke="#f1d27f"
        strokeWidth="3.2"
        strokeLinecap="round"
      />
      <path
        d="M78 131C61 122 51 110 53 98C55 88 64 84 71 90C78 97 72 105 66 103"
        fill="none"
        stroke="#dca94a"
        strokeWidth="2.7"
        strokeLinecap="round"
      />
      <path
        d="M112 164C101 174 98 188 105 195C111 201 121 197 123 188"
        fill="none"
        stroke="#dca94a"
        strokeWidth="2.8"
        strokeLinecap="round"
      />
      <path
        d="M91 76C83 70 73 69 65 74"
        fill="none"
        stroke="#f4dc99"
        strokeWidth="4"
        strokeLinecap="round"
      />
      <circle cx="88" cy="112" r="5.5" fill="#dba84a" stroke="#f8e5aa" strokeWidth="1.5" />
      <path
        d="M67 154C59 159 55 166 56 174"
        fill="none"
        stroke="#f0cd76"
        strokeWidth="3"
        strokeLinecap="round"
      />
    </>
  );

  return (
    <svg
      className={`${className} tramp-stamp-artwork-${variant}`}
      viewBox="0 0 320 300"
      aria-hidden="true"
      focusable="false"
    >
      <defs>
        <linearGradient id={blueGradientId} x1="0" y1="0" x2="1" y2="1">
          <stop offset="0" stopColor="#326eae" />
          <stop offset="0.42" stopColor="#174f8e" />
          <stop offset="1" stopColor="#082e5d" />
        </linearGradient>
        <radialGradient id={blueGlowId} cx="35%" cy="28%" r="78%">
          <stop offset="0" stopColor="#5d96cf" />
          <stop offset="0.46" stopColor="#2867a7" />
          <stop offset="1" stopColor="#0d3d77" />
        </radialGradient>
        <linearGradient id={goldGradientId} x1="0" y1="0" x2="1" y2="1">
          <stop offset="0" stopColor="#fff0b0" />
          <stop offset="0.3" stopColor="#d9a441" />
          <stop offset="0.68" stopColor="#a96b17" />
          <stop offset="1" stopColor="#f1cf76" />
        </linearGradient>
        <filter id={shadowId} x="-30%" y="-30%" width="160%" height="170%">
          <feDropShadow dx="0" dy="9" stdDeviation="8" floodColor="#08284d" floodOpacity="0.28" />
        </filter>
      </defs>

      <g filter={`url(#${shadowId})`}>
        <g className={leftWingClass}>{leftWing}</g>
        <g className={rightWingClass}>
          <g transform="translate(320 0) scale(-1 1)">{leftWing}</g>
        </g>

        <g className={bodyClass}>
          <path
            d="M157 39C150 24 140 18 129 17M163 39C170 24 180 18 191 17"
            fill="none"
            stroke="#c78f2d"
            strokeWidth="3.5"
            strokeLinecap="round"
          />
          <circle cx="128" cy="17" r="3.5" fill="#e7bd62" stroke="#164d83" strokeWidth="1.5" />
          <circle cx="192" cy="17" r="3.5" fill="#e7bd62" stroke="#164d83" strokeWidth="1.5" />
          <ellipse
            cx="160"
            cy="58"
            rx="13"
            ry="17"
            fill={`url(#${goldGradientId})`}
            stroke="#123f72"
            strokeWidth="3"
          />
          <path
            d="M160 70C174 84 172 129 164 166C162 177 158 177 156 166C148 129 146 84 160 70Z"
            fill={`url(#${goldGradientId})`}
            stroke="#123f72"
            strokeWidth="3.5"
          />
          <path
            d="M151 92H169M150 112H170M151 133H169M154 153H166"
            fill="none"
            stroke="#1b568f"
            strokeWidth="2.2"
            strokeLinecap="round"
          />
        </g>
      </g>
    </svg>
  );
}

export function TrampStampBadge({ balance }: TrampStampBadgeProps) {
  const value = normalizedBalance(balance);
  const label = stampBalanceLabel(value);

  return (
    <div className="tramp-stamp-badge" aria-label={`${label} in your balance`}>
      <ButterflyArtwork className="tramp-stamp-badge-mark" variant="static" />
      <span>{label}</span>
    </div>
  );
}

export function TrampStampButterfly({
  active,
  balance,
  onComplete,
}: TrampStampButterflyProps) {
  const prefersReducedMotion = usePrefersReducedMotion();
  const onCompleteRef = useRef(onComplete);
  const completedRef = useRef(false);
  onCompleteRef.current = onComplete;

  const complete = useCallback(() => {
    if (completedRef.current) {
      return;
    }
    completedRef.current = true;
    onCompleteRef.current();
  }, []);

  useEffect(() => {
    if (!active) {
      completedRef.current = false;
      return;
    }

    completedRef.current = false;
    const timeout = window.setTimeout(
      complete,
      prefersReducedMotion ? REDUCED_MOTION_HOLD_MS : FULL_ANIMATION_MS,
    );
    return () => window.clearTimeout(timeout);
  }, [active, complete, prefersReducedMotion]);

  if (!active) {
    return null;
  }

  const value = normalizedBalance(balance);
  const label = stampBalanceLabel(value);

  return (
    <div
      className="tramp-stamp-overlay"
      role="status"
      aria-live="polite"
      aria-atomic="true"
      aria-label={`One TRAMP-Stamp awarded. Balance: ${label}.`}
      data-motion={prefersReducedMotion ? "reduced" : "animated"}
    >
      <div
        className={
          prefersReducedMotion
            ? "tramp-stamp-flight tramp-stamp-sequence-strict tramp-stamp-flight-reduced"
            : "tramp-stamp-flight tramp-stamp-sequence-strict"
        }
        data-testid="tramp-stamp-flight"
        onAnimationEnd={() => {
          if (!prefersReducedMotion) {
            complete();
          }
        }}
      >
        <ButterflyArtwork className="tramp-stamp-butterfly" variant="animated" />
        <div className="tramp-stamp-award-copy">
          <strong>+1 TRAMP-Stamp</strong>
          <span>{label}</span>
        </div>
      </div>
    </div>
  );
}
