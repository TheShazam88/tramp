import { act, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import {
  TrampStampBadge,
  TrampStampButterfly,
} from "@/components/rewards/TrampStampButterfly";

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

  it("formats persistent badge balances as singular and plural", () => {
    const { rerender } = render(<TrampStampBadge balance={1} />);

    expect(
      screen.getByLabelText("1 TRAMP-Stamp in your balance"),
    ).toHaveTextContent("1 TRAMP-Stamp");

    rerender(<TrampStampBadge balance={2} />);
    expect(
      screen.getByLabelText("2 TRAMP-Stamps in your balance"),
    ).toHaveTextContent("2 TRAMP-Stamps");
  });
});
