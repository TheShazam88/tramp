/// <reference types="node" />

import { readFileSync } from "node:fs";
import { resolve } from "node:path";

import { act, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import {
  TrampStampBadge,
  TrampStampButterfly,
} from "@/components/rewards/TrampStampButterfly";

const globalCss = readFileSync(resolve(process.cwd(), "src/theme/global.css"), "utf8");

function stubReducedMotion(matches: boolean) {
  vi.stubGlobal(
    "matchMedia",
    vi.fn().mockImplementation((query: string) => ({
      matches: query === "(prefers-reduced-motion: reduce)" && matches,
      media: query,
      onchange: null,
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
      addListener: vi.fn(),
      removeListener: vi.fn(),
      dispatchEvent: vi.fn(),
    })),
  );
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

  it("shows a static final pose for reduced motion before completing", () => {
    vi.useFakeTimers();
    stubReducedMotion(true);
    const onComplete = vi.fn();
    render(<TrampStampButterfly active balance={1} onComplete={onComplete} />);

    expect(screen.getByRole("status")).toHaveAttribute("data-motion", "reduced");
    expect(screen.getByTestId("tramp-stamp-flight")).toHaveClass(
      "tramp-stamp-flight-reduced",
    );
    expect(screen.getByText("1 TRAMP-Stamp")).toBeVisible();

    act(() => {
      vi.runAllTimers();
    });
    expect(onComplete).toHaveBeenCalledTimes(1);
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
});
