import type { IntegrationAcquisitionGuide } from "@/api/types";

interface CredentialGuideProps {
  providerName: string;
  guide?: IntegrationAcquisitionGuide;
}

export function CredentialGuide({
  providerName,
  guide,
}: CredentialGuideProps) {
  if (!guide) {
    return null;
  }

  return (
    <details className="form-disclosure credential-guide">
      <summary>How to get {providerName} credentials</summary>
      <div className="stack-tight form-grid-gap-top">
        <div className="panel-actions">
          <a
            className="helper-link"
            href={guide.signupUrl}
            target="_blank"
            rel="noreferrer"
          >
            Open official {providerName} setup guide
          </a>
          {guide.applicationUrl ? (
            <a
              className="helper-link"
              href={guide.applicationUrl}
              target="_blank"
              rel="noreferrer"
            >
              Open official {providerName} application guide
            </a>
          ) : null}
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
