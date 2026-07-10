import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import type { IntegrationAcquisitionGuide } from "@/api/types";
import { CredentialGuide } from "@/components/admin/CredentialGuide";

const guide: IntegrationAcquisitionGuide = {
  signupUrl: "https://provider.example/setup",
  applicationUrl: "https://provider.example/apply",
  accountRequirements: ["A developer account", "Approval for live access"],
  steps: ["Create an application", "Copy the test credentials"],
  environmentNotes: ["Start in test", "Request live access separately"],
  enables: ["Credential validation", "Future live provider wiring"],
};

describe("CredentialGuide", () => {
  it("renders an accessible credential acquisition disclosure", () => {
    render(<CredentialGuide providerName="Example Air" guide={guide} />);

    const summary = screen.getByText("How to get Example Air credentials");
    const disclosure = summary.closest("details");

    expect(summary.tagName).toBe("SUMMARY");
    expect(summary).toBeVisible();
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
      name: "Open official Example Air setup guide",
      hidden: true,
    });
    const applicationLink = screen.getByRole("link", {
      name: "Open official Example Air application guide",
      hidden: true,
    });

    expect(setupLink).toHaveAttribute("href", guide.signupUrl);
    expect(applicationLink).toHaveAttribute("href", guide.applicationUrl);
    for (const link of [setupLink, applicationLink]) {
      expect(link).toHaveAttribute("target", "_blank");
      expect(link).toHaveAttribute("rel", "noreferrer");
    }
  });

  it("renders nothing when the provider has no guide", () => {
    const { container } = render(
      <CredentialGuide providerName="Example Air" guide={undefined} />,
    );

    expect(container).toBeEmptyDOMElement();
  });
});
