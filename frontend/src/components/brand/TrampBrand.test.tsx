/// <reference types="node" />

import { readFileSync } from "node:fs";
import { resolve } from "node:path";

import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { TrampBrand } from "@/components/brand/TrampBrand";
import indexHtml from "../../../index.html?raw";

const globalCss = readFileSync(resolve(process.cwd(), "src/theme/global.css"), "utf8");

describe("TrampBrand", () => {
  it("renders the shared Editorial Gold wordmark", () => {
    const { container } = render(<TrampBrand compact />);

    expect(screen.getByText("TRAMP")).toHaveClass("brand-wordmark");
    expect(screen.getByText("TRAVEL AMPLIFIER")).toHaveClass("brand-expansion");
    expect(container.firstElementChild).toHaveClass("tramp-brand-compact");
    expect(container.querySelector("img")).not.toBeInTheDocument();
  });

  it("uses the existing blue value token for the subtitle", () => {
    const expansionRule = globalCss.match(/\.brand-expansion\s*\{([^}]*)\}/s)?.[1];

    expect(expansionRule).toContain("color: var(--value);");
    expect(expansionRule).not.toContain("var(--muted)");
  });

  it("preserves installed app icon links", () => {
    expect(indexHtml).toContain('rel="icon" type="image/svg+xml" href="/tramp-app-icon.svg"');
    expect(indexHtml).toContain('rel="apple-touch-icon" href="/tramp-app-icon.png"');
    expect(indexHtml).toContain('rel="manifest" href="/tramp.webmanifest"');
  });
});
