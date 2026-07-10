/// <reference types="node" />

import { readFileSync } from "node:fs";
import { resolve } from "node:path";

import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { TrampBrand } from "@/components/brand/TrampBrand";
import indexHtml from "../../../index.html?raw";

const globalCss = readFileSync(resolve(process.cwd(), "src/theme/global.css"), "utf8");
const accessibleGoldStops = ["#70460d", "#805515", "#76501a", "#694008"];
const badgeTextGold = "#68410a";
const lightBackgrounds = ["#ffffff", "#f6f3ec", "#f4ecdd"];

function relativeLuminance(hexColor: string) {
  const channels = hexColor
    .slice(1)
    .match(/.{2}/g)!
    .map((channel) => Number.parseInt(channel, 16) / 255)
    .map((channel) =>
      channel <= 0.04045
        ? channel / 12.92
        : ((channel + 0.055) / 1.055) ** 2.4,
    );
  return 0.2126 * channels[0] + 0.7152 * channels[1] + 0.0722 * channels[2];
}

function contrastRatio(foreground: string, background: string) {
  const foregroundLuminance = relativeLuminance(foreground);
  const backgroundLuminance = relativeLuminance(background);
  return (
    (Math.max(foregroundLuminance, backgroundLuminance) + 0.05) /
    (Math.min(foregroundLuminance, backgroundLuminance) + 0.05)
  );
}

describe("TrampBrand", () => {
  it("renders the shared Editorial Gold wordmark as a semantic heading", () => {
    const { container } = render(<TrampBrand compact as="h1" />);

    expect(screen.getByText("TRAMP")).toHaveClass("brand-wordmark");
    expect(screen.getByText("TRAVEL AMPLIFIER")).toHaveClass("brand-expansion");
    const heading = screen.getByRole("heading", { level: 1 });
    expect(heading).toHaveClass("tramp-brand-compact");
    expect(heading).not.toHaveAttribute("aria-label");
    expect(container.querySelector("img")).not.toBeInTheDocument();
  });

  it("uses the existing blue value token for the subtitle", () => {
    const expansionRule = globalCss.match(/\.brand-expansion\s*\{([^}]*)\}/s)?.[1];

    expect(expansionRule).toContain("color: var(--value);");
    expect(expansionRule).not.toContain("var(--muted)");
  });

  it("keeps final gold colors at WCAG AA contrast on light surfaces", () => {
    const wordmarkRule = globalCss.match(/\.brand-wordmark\s*\{([^}]*)\}/s)?.[1] ?? "";
    const badgeRule = globalCss.match(/\.tramp-stamp-badge\s*\{([^}]*)\}/s)?.[1] ?? "";

    for (const foreground of [...accessibleGoldStops, badgeTextGold]) {
      for (const background of lightBackgrounds) {
        expect(contrastRatio(foreground, background)).toBeGreaterThanOrEqual(4.5);
      }
    }
    for (const color of accessibleGoldStops) {
      expect(wordmarkRule).toContain(color);
    }
    expect(badgeRule).toContain(`color: ${badgeTextGold};`);
  });

  it("provides a forced-colors fallback for brand and reward text", () => {
    const forcedColorsRule = globalCss.slice(
      globalCss.indexOf("@media (forced-colors: active)"),
    );

    expect(forcedColorsRule).toContain(".brand-wordmark");
    expect(forcedColorsRule).toContain("-webkit-text-fill-color: CanvasText");
    expect(forcedColorsRule).toContain(".tramp-stamp-badge");
    expect(forcedColorsRule).toContain("color: CanvasText");
  });

  it("preserves installed app icon links", () => {
    expect(indexHtml).toContain('rel="icon" type="image/svg+xml" href="/tramp-app-icon.svg"');
    expect(indexHtml).toContain('rel="apple-touch-icon" href="/tramp-app-icon.png"');
    expect(indexHtml).toContain('rel="manifest" href="/tramp.webmanifest"');
  });
});
