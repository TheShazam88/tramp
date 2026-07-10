import { useState } from "react";

import type { IntegrationAcquisitionGuide } from "@/api/types";

interface CredentialGuideProps {
  providerName: string;
  guide?: IntegrationAcquisitionGuide;
}

export function CredentialGuide({
  providerName,
  guide,
}: CredentialGuideProps) {
  const [isOpen, setIsOpen] = useState(false);

  if (!guide) {
    return null;
  }

  return (
    <details
      className="form-disclosure credential-guide"
      onToggle={(event) => setIsOpen(event.currentTarget.open)}
    >
      <summary
        className="credential-guide-summary"
        aria-expanded={isOpen}
        tabIndex={0}
        onKeyDown={(event) => {
          if (event.key !== "Enter" && event.key !== " ") {
            return;
          }
          event.preventDefault();
          const disclosure = event.currentTarget.parentElement;
          if (disclosure instanceof HTMLDetailsElement) {
            disclosure.open = !disclosure.open;
            setIsOpen(disclosure.open);
          }
        }}
      >
        <span>How to get {providerName} credentials</span>
        <span className="credential-guide-state">
          <span
            className={`credential-guide-chevron ${
              isOpen ? "credential-guide-chevron-open" : ""
            }`}
            aria-hidden="true"
          >
            ▸
          </span>
          <span>{isOpen ? "Hide setup guide" : "Show setup guide"}</span>
        </span>
      </summary>
      <div className="stack-tight form-grid-gap-top">
        <div className="panel-actions">
          {guide.links.map((link) => (
            <a
              key={`${link.label}-${link.url}`}
              className="helper-link"
              href={link.url}
              target="_blank"
              rel="noreferrer"
            >
              {link.label}
            </a>
          ))}
        </div>

        <div>
          <p className="field-label">Account requirements</p>
          <ul className="info-list">
            {guide.accountRequirements.map((requirement) => (
              <li key={requirement}>{requirement}</li>
            ))}
          </ul>
        </div>

        <div>
          <p className="field-label">Setup steps</p>
          <ol className="info-list">
            {guide.steps.map((step) => (
              <li key={step}>{step}</li>
            ))}
          </ol>
        </div>

        <div>
          <p className="field-label">Test and live notes</p>
          <ul className="info-list">
            {guide.environmentNotes.map((note) => (
              <li key={note}>{note}</li>
            ))}
          </ul>
        </div>

        <div>
          <p className="field-label">Capabilities</p>
          <ul className="info-list">
            {guide.enables.map((capability) => (
              <li key={capability}>{capability}</li>
            ))}
          </ul>
        </div>
      </div>
    </details>
  );
}
