import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";

import type { IntegrationAcquisitionGuide } from "@/api/types";
import { CredentialGuide } from "@/components/admin/CredentialGuide";

const guide: IntegrationAcquisitionGuide = {
  links: [
    {
      label: "Example Air developer guide",
      url: "https://provider.example/setup",
    },
    {
      label: "Example Air live access application",
      url: "https://provider.example/apply",
    },
  ],
  accountRequirements: ["A developer account", "Approval for live access"],
  steps: ["Create an application", "Copy the test credentials"],
  environmentNotes: ["Start in test", "Request live access separately"],
  enables: ["Local configuration checks", "Future live provider wiring"],
};

describe("CredentialGuide", () => {
  it("renders an accessible credential acquisition disclosure", () => {
    render(<CredentialGuide providerName="Example Air" guide={guide} />);

    const summaryText = screen.getByText("How to get Example Air credentials");
    const summary = summaryText.closest("summary");
    const disclosure = summaryText.closest("details");

    expect(summary?.tagName).toBe("SUMMARY");
    expect(summary).toBeVisible();
    expect(summary).toHaveClass("credential-guide-summary");
    expect(summary).toHaveAttribute("aria-expanded", "false");
    expect(screen.getByText("Show setup guide")).toBeVisible();
    expect(disclosure).not.toHaveAttribute("open");
    expect(screen.getByText("Account requirements")).toBeInTheDocument();
    expect(screen.getByText("Setup steps")).toBeInTheDocument();
    expect(screen.getByText("Test and live notes")).toBeInTheDocument();
    expect(screen.getByText("Capabilities")).toBeInTheDocument();
    expect(screen.getByText("A developer account")).toBeInTheDocument();
    expect(screen.getByText("Copy the test credentials")).toBeInTheDocument();
    expect(disclosure?.querySelectorAll("ol > li")).toHaveLength(2);
  });

  it("uses named official links that open safely in a new tab", () => {
    render(<CredentialGuide providerName="Example Air" guide={guide} />);

    const setupLink = screen.getByRole("link", {
      name: "Example Air developer guide",
      hidden: true,
    });
    const applicationLink = screen.getByRole("link", {
      name: "Example Air live access application",
      hidden: true,
    });

    expect(setupLink).toHaveAttribute("href", guide.links[0].url);
    expect(applicationLink).toHaveAttribute("href", guide.links[1].url);
    for (const link of [setupLink, applicationLink]) {
      expect(link).toHaveAttribute("target", "_blank");
      expect(link).toHaveAttribute("rel", "noreferrer");
    }
  });

  it("toggles with the keyboard and exposes visible disclosure state", async () => {
    const user = userEvent.setup();
    render(<CredentialGuide providerName="Example Air" guide={guide} />);

    const summaryText = screen.getByText("How to get Example Air credentials");
    const summary = summaryText.closest("summary");
    const disclosure = summaryText.closest("details");

    await user.tab();
    expect(summary).toHaveFocus();

    await user.keyboard("{Enter}");
    expect(disclosure).toHaveAttribute("open");
    expect(summary).toHaveAttribute("aria-expanded", "true");
    expect(screen.getByText("Hide setup guide")).toBeVisible();
  });

  it("renders nothing when the provider has no guide", () => {
    const { container } = render(
      <CredentialGuide providerName="Example Air" guide={undefined} />,
    );

    expect(container).toBeEmptyDOMElement();
  });
});
