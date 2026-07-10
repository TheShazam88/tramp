/// <reference types="node" />

import { readFileSync } from "node:fs";
import { resolve } from "node:path";

import { act, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import {
  TrampStampBadge,
  TrampStampButterfly,
} from "@/components/rewards/TrampStampButterfly";

const globalCss = readFileSync(resolve(process.cwd(), "src/theme/global.css"), "utf8");

function stubReducedMotion(matches: boolean) {
  return installMotionPreference(matches);
}

function installMotionPreference(initialMatches: boolean) {
  let matches = initialMatches;
  const listeners = new Set<(event: MediaQueryListEvent) => void>();
  const addEventListener = vi.fn(
    (eventName: string, listener: (event: MediaQueryListEvent) => void) => {
      if (eventName === "change") {
        listeners.add(listener);
      }
    },
  );
  const removeEventListener = vi.fn(
    (eventName: string, listener: (event: MediaQueryListEvent) => void) => {
      if (eventName === "change") {
        listeners.delete(listener);
      }
    },
  );
  const mediaQuery = {
    get matches() {
      return matches;
    },
    media: "(prefers-reduced-motion: reduce)",
    onchange: null,
    addEventListener,
    removeEventListener,
    addListener: vi.fn(),
    removeListener: vi.fn(),
    dispatchEvent: vi.fn(),
  } as unknown as MediaQueryList;
  vi.stubGlobal(
    "matchMedia",
    vi.fn().mockImplementation(() => mediaQuery),
  );

  return {
    addEventListener,
    removeEventListener,
    listenerCount: () => listeners.size,
    setMatches(nextMatches: boolean) {
      matches = nextMatches;
      const event = {
        matches,
        media: mediaQuery.media,
      } as MediaQueryListEvent;
      listeners.forEach((listener) => listener(event));
    },
  };
}

describe("TrampStampButterfly", () => {
  afterEach(() => {
    vi.useRealTimers();
    vi.unstubAllGlobals();
  });

  it("announces the award and updated balance accessibly", () => {
    stubReducedMotion(false);
    render(<TrampStampButterfly active balance={4} onComplete={vi.fn()} />);

    const status = screen.getByRole("status", {
      name: "One TRAMP-Stamp awarded. Balance: 4 TRAMP-Stamps.",
    });
    expect(status).toHaveAttribute("aria-live", "polite");
    expect(status).toHaveAttribute("aria-atomic", "true");
    expect(screen.getByTestId("tramp-stamp-flight")).toHaveClass(
      "tramp-stamp-sequence-strict",
    );
    expect(screen.getByText("+1 TRAMP-Stamp")).toBeVisible();
    expect(screen.getByText("4 TRAMP-Stamps")).toBeVisible();
  });

  it("completes once for each activation", () => {
    vi.useFakeTimers();
    stubReducedMotion(false);
    const onComplete = vi.fn();
    const { rerender } = render(
      <TrampStampButterfly active balance={4} onComplete={onComplete} />,
    );

    act(() => {
      vi.advanceTimersByTime(5000);
      vi.advanceTimersByTime(5000);
    });
    expect(onComplete).toHaveBeenCalledTimes(1);

    rerender(<TrampStampButterfly active={false} balance={4} onComplete={onComplete} />);
    rerender(<TrampStampButterfly active balance={5} onComplete={onComplete} />);
    act(() => {
      vi.advanceTimersByTime(5000);
    });
    expect(onComplete).toHaveBeenCalledTimes(2);
  });

  it("does not reset completion when the motion preference changes", () => {
    vi.useFakeTimers();
    const motionPreference = installMotionPreference(false);
    const onComplete = vi.fn();
    const { rerender } = render(
      <TrampStampButterfly active balance={4} onComplete={onComplete} />,
    );

    act(() => {
      vi.advanceTimersByTime(1000);
      motionPreference.setMatches(true);
    });
    expect(screen.getByRole("status")).toHaveAttribute("data-motion", "reduced");
    act(() => {
      vi.advanceTimersByTime(1600);
    });
    expect(onComplete).toHaveBeenCalledTimes(1);

    act(() => {
      motionPreference.setMatches(false);
    });
    expect(screen.getByRole("status")).toHaveAttribute("data-motion", "animated");
    act(() => {
      vi.advanceTimersByTime(5000);
      fireEvent.animationEnd(screen.getByTestId("tramp-stamp-flight"));
    });
    expect(onComplete).toHaveBeenCalledTimes(1);

    rerender(<TrampStampButterfly active={false} balance={4} onComplete={onComplete} />);
    rerender(<TrampStampButterfly active balance={5} onComplete={onComplete} />);
    act(() => {
      vi.advanceTimersByTime(5000);
    });
    expect(onComplete).toHaveBeenCalledTimes(2);
  });

  it("calls onComplete once when animation and timer completion race", () => {
    vi.useFakeTimers();
    stubReducedMotion(false);
    const onComplete = vi.fn();
    render(<TrampStampButterfly active balance={4} onComplete={onComplete} />);
    const flight = screen.getByTestId("tramp-stamp-flight");

    act(() => {
      vi.advanceTimersByTime(4999);
      fireEvent.animationEnd(flight);
      vi.advanceTimersByTime(1);
      fireEvent.animationEnd(flight);
    });

    expect(onComplete).toHaveBeenCalledTimes(1);
  });

  it("cleans up its timer and motion listener on unmount", () => {
    vi.useFakeTimers();
    const motionPreference = installMotionPreference(false);
    const onComplete = vi.fn();
    const { unmount } = render(
      <TrampStampButterfly active balance={4} onComplete={onComplete} />,
    );

    expect(motionPreference.addEventListener).toHaveBeenCalledTimes(1);
    expect(motionPreference.listenerCount()).toBe(1);
    unmount();
    expect(motionPreference.removeEventListener).toHaveBeenCalledTimes(1);
    expect(motionPreference.listenerCount()).toBe(0);
    act(() => {
      vi.runAllTimers();
    });
    expect(onComplete).not.toHaveBeenCalled();
  });

  it("shows a static final pose for reduced motion before completing", () => {
    vi.useFakeTimers();
    stubReducedMotion(true);
    const onComplete = vi.fn();
    render(<TrampStampButterfly active balance={1} onComplete={onComplete} />);

    expect(screen.getByRole("status")).toHaveAttribute("data-motion", "reduced");
    expect(screen.getByRole("status")).toHaveClass("tramp-stamp-viewport-safe");
    expect(screen.getByTestId("tramp-stamp-flight")).toHaveClass(
      "tramp-stamp-flight-reduced",
    );
    expect(screen.getByText("1 TRAMP-Stamp")).toBeVisible();

    act(() => {
      vi.runAllTimers();
    });
    expect(onComplete).toHaveBeenCalledTimes(1);
  });

  it("uses unique SVG definition IDs across persistent and active instances", () => {
    stubReducedMotion(true);
    const { container } = render(
      <>
        <TrampStampBadge balance={0} />
        <TrampStampBadge balance={2} />
        <TrampStampButterfly active balance={3} onComplete={vi.fn()} />
      </>,
    );

    const ids = Array.from(
      container.querySelectorAll<SVGElement>("[id]"),
      (element) => element.id,
    );
    expect(ids.length).toBeGreaterThan(0);
    expect(new Set(ids).size).toBe(ids.length);
  });

  it("keeps zero and nonzero persistent badge artwork completely static", () => {
    const { container, rerender } = render(<TrampStampBadge balance={0} />);

    expect(screen.getByLabelText("0 TRAMP-Stamps in your balance")).toBeVisible();
    expect(container.querySelector(".tramp-stamp-artwork-static")).toBeInTheDocument();
    expect(container.querySelector(".tramp-stamp-wing")).not.toBeInTheDocument();
    expect(container.querySelector(".tramp-stamp-body")).not.toBeInTheDocument();
    expect(container.querySelectorAll(".tramp-stamp-static-wing")).toHaveLength(2);
    expect(container.querySelector(".tramp-stamp-static-body")).toBeInTheDocument();
    expect(globalCss).toMatch(
      /\.tramp-stamp-artwork-static\s*\{[^}]*animation:\s*none/s,
    );

    rerender(<TrampStampBadge balance={1} />);
    expect(
      screen.getByLabelText("1 TRAMP-Stamp in your balance"),
    ).toHaveTextContent("1 TRAMP-Stamp");

    rerender(<TrampStampBadge balance={2} />);
    expect(
      screen.getByLabelText("2 TRAMP-Stamps in your balance"),
    ).toHaveTextContent("2 TRAMP-Stamps");
  });

  it("defines a strict three beat, settle, two flutter, hold, reveal, fade timeline", () => {
    const section = (startMarker: string, endMarker: string) =>
      globalCss.slice(
        globalCss.indexOf(startMarker),
        globalCss.indexOf(endMarker),
      );
    const descent = section(
      "@keyframes trampStampDescent",
      "@keyframes trampStampWingSequence",
    );
    const wings = section(
      "@keyframes trampStampWingSequence",
      "@keyframes trampStampBodySettle",
    );
    const body = section(
      "@keyframes trampStampBodySettle",
      "@keyframes trampStampCopyReveal",
    );
    const copy = section(
      "@keyframes trampStampCopyReveal",
      ".tramp-stamp-flight-reduced",
    );

    expect(descent).toMatch(/48%\s*\{[^}]*translateY\(0\)/s);
    expect(wings).toMatch(
      /4%,\s*14%,\s*24%\s*\{\s*transform:\s*scaleX\(0\.24\)/,
    );
    expect(wings).toMatch(
      /54%,\s*62%\s*\{\s*transform:\s*scaleX\(0\.72\)/,
    );
    expect(wings).toMatch(/66%,\s*100%\s*\{\s*transform:\s*scaleX\(1\)/);
    expect(body).toMatch(/48%,\s*100%\s*\{\s*transform:\s*rotate\(0\)/);
    expect(copy).toMatch(/0%,\s*76%\s*\{\s*opacity:\s*0/);
    expect(copy).toMatch(/82%,\s*92%\s*\{\s*opacity:\s*1/);
  });

  it("constrains the overlay by dvh for short landscape and reduced-motion views", () => {
    const butterflyRule =
      globalCss.match(/\.tramp-stamp-butterfly\s*\{([^}]*)\}/s)?.[1] ?? "";
    const shortLandscapeRule = globalCss.slice(
      globalCss.indexOf(
        "@media (max-height: 420px) and (orientation: landscape)",
      ),
      globalCss.indexOf("@media (prefers-reduced-motion: reduce)"),
    );

    expect(butterflyRule).toContain("100dvh");
    expect(butterflyRule).toContain("max-height");
    expect(shortLandscapeRule).toContain(".tramp-stamp-flight");
    expect(shortLandscapeRule).toContain(".tramp-stamp-butterfly");
    expect(shortLandscapeRule).toContain("100dvh");
  });
});
