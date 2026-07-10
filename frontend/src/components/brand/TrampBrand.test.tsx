import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { TrampBrand } from "@/components/brand/TrampBrand";
import indexHtml from "../../../index.html?raw";

describe("TrampBrand", () => {
  it("renders the shared Editorial Gold wordmark", () => {
    const { container } = render(<TrampBrand compact />);

    expect(screen.getByText("TRAMP")).toHaveClass("brand-wordmark");
    expect(screen.getByText("TRAVEL AMPLIFIER")).toHaveClass("brand-expansion");
    expect(container.firstElementChild).toHaveClass("tramp-brand-compact");
    expect(container.querySelector("img")).not.toBeInTheDocument();
  });

  it("preserves installed app icon links", () => {
    expect(indexHtml).toContain('rel="icon" type="image/svg+xml" href="/tramp-app-icon.svg"');
    expect(indexHtml).toContain('rel="apple-touch-icon" href="/tramp-app-icon.png"');
    expect(indexHtml).toContain('rel="manifest" href="/tramp.webmanifest"');
  });
});
