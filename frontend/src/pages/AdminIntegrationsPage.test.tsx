import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, within } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";

import type {
  IntegrationAcquisitionGuide,
  IntegrationCredentialProfile,
  IntegrationData,
  IntegrationProvider,
} from "@/api/types";
import { travelWatchApi } from "@/api/travelWatchApi";
import { AdminIntegrationsPage } from "@/pages/AdminIntegrationsPage";

const acquisitionGuide: IntegrationAcquisitionGuide = {
  signupUrl: "https://provider.example/setup",
  applicationUrl: "https://provider.example/apply",
  accountRequirements: ["Provider account"],
  steps: ["Create credentials", "Save the credentials"],
  environmentNotes: ["Start in test"],
  enables: ["Provider configuration"],
};

function buildProvider(
  overrides: Partial<IntegrationProvider> &
    Pick<IntegrationProvider, "key" | "name" | "category">,
): IntegrationProvider {
  return {
    providerKey: undefined,
    supportsSharedProfile: false,
    compatibleProfileProviderKeys: [],
    environment: "test",
    status: "connected",
    detail: "Provider configuration.",
    enabled: true,
    guide: acquisitionGuide,
    credentialState: {
      configured: false,
      label: "Not set",
    },
    credentialFields: [],
    credentialsMasked: {},
    featureFlags: [],
    featureFlagDefinitions: [],
    ...overrides,
  };
}

function integrationData(
  category: string,
  providers: IntegrationProvider[],
  credentialProfiles: IntegrationCredentialProfile[] = [],
): IntegrationData {
  return {
    categories: [
      {
        id: category,
        title: category,
        description: `${category} integrations`,
      },
    ],
    providers,
    credentialProfiles,
    featureFlags: [],
    healthNotes: [],
    runtimeSettings: {
      mockDataEnabled: true,
      liveInventoryAvailable: false,
      currentInventoryMode: "mock",
    },
  };
}

function renderCategory(
  category: string,
  providers: IntegrationProvider[],
  credentialProfiles: IntegrationCredentialProfile[] = [],
) {
  vi.spyOn(travelWatchApi, "getIntegrations").mockResolvedValue(
    integrationData(category, providers, credentialProfiles),
  );
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: { retry: false },
      mutations: { retry: false },
    },
  });

  render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={[`/admin/integrations/${category}`]}>
        <Routes>
          <Route
            path="/admin/integrations/:categoryId"
            element={<AdminIntegrationsPage />}
          />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

function expectGuideImmediatelyBeforeField(
  card: HTMLElement,
  providerName: string,
  fieldName: string,
) {
  const cardQueries = within(card);
  const summary = cardQueries.getByText(
    `How to get ${providerName} credentials`,
  );
  const input = cardQueries.getByLabelText(fieldName, { exact: false });

  expect(card.querySelectorAll(".credential-guide")).toHaveLength(1);
  expect(
    summary.compareDocumentPosition(input) & Node.DOCUMENT_POSITION_FOLLOWING,
  ).toBeTruthy();
}

describe("AdminIntegrationsPage credential guide placement", () => {
  it("renders the guide before credential fields in a shared profile card", async () => {
    const provider = buildProvider({
      key: "flights_amadeus",
      name: "Flights · Amadeus",
      category: "flights",
      providerKey: "amadeus",
      supportsSharedProfile: true,
      compatibleProfileProviderKeys: ["amadeus"],
      credentialFields: [
        {
          key: "client_id",
          label: "Client ID",
          sensitive: true,
        },
      ],
    });
    renderCategory("flights", [provider], [
      {
        id: "profile-amadeus",
        providerKey: "amadeus",
        label: "Amadeus profile",
        credentialsMasked: {},
        usageIntegrationKeys: [],
      },
    ]);

    const profileHeading = await screen.findByRole("heading", {
      name: "Amadeus profile",
    });
    const profileCard = profileHeading.closest(".inset-card");

    expect(profileCard).not.toBeNull();
    expectGuideImmediatelyBeforeField(
      profileCard as HTMLElement,
      "Flights · Amadeus",
      "Client ID",
    );
  });

  it.each([
    {
      label: "flight",
      category: "flights",
      provider: buildProvider({
        key: "flights_amadeus",
        name: "Flights · Amadeus",
        category: "flights",
        providerKey: "amadeus",
        supportsSharedProfile: true,
        compatibleProfileProviderKeys: ["amadeus"],
        credentialFields: [
          { key: "client_id", label: "Client ID", sensitive: true },
        ],
      }),
      fieldName: "Client ID",
    },
    {
      label: "hotel",
      category: "hotels",
      provider: buildProvider({
        key: "hotels",
        name: "Hotels",
        category: "hotels",
        credentialsMasked: { provider: "hotelbeds" },
        credentialFields: [
          { key: "provider", label: "Provider", sensitive: false },
          { key: "api_key", label: "API key", sensitive: true },
        ],
      }),
      fieldName: "API key",
    },
    {
      label: "booking",
      category: "booking",
      provider: buildProvider({
        key: "booking",
        name: "Booking",
        category: "booking",
        credentialsMasked: { provider: "duffel" },
        credentialFields: [
          { key: "provider", label: "Provider", sensitive: false },
          { key: "access_token", label: "Access token", sensitive: true },
        ],
      }),
      fieldName: "Access token",
    },
    {
      label: "messaging",
      category: "messaging",
      provider: buildProvider({
        key: "notifications",
        name: "Notifications",
        category: "messaging",
        credentialsMasked: { delivery_mode: "smtp_dev" },
        credentialFields: [
          { key: "delivery_mode", label: "Delivery mode", sensitive: false },
          { key: "smtp_host", label: "SMTP host", sensitive: false },
        ],
      }),
      fieldName: "SMTP host",
    },
    {
      label: "calendar",
      category: "calendar",
      provider: buildProvider({
        key: "calendar",
        name: "Calendar",
        category: "calendar",
        credentialsMasked: { delivery_mode: "google_calendar" },
        credentialFields: [
          { key: "delivery_mode", label: "Delivery mode", sensitive: false },
          { key: "calendar_id", label: "Calendar ID", sensitive: false },
          { key: "access_token", label: "Access token", sensitive: true },
        ],
      }),
      fieldName: "Calendar ID",
    },
    {
      label: "generic",
      category: "general",
      provider: buildProvider({
        key: "generic",
        name: "Generic connector",
        category: "general",
        credentialFields: [
          { key: "api_key", label: "Generic API key", sensitive: true },
        ],
      }),
      fieldName: "Generic API key",
    },
  ])(
    "renders one guide before the $label connector credential fields",
    async ({ category, provider, fieldName }) => {
      renderCategory(category, [provider]);

      const providerHeading = await screen.findByRole("heading", {
        name: provider.name,
      });
      const providerCard = providerHeading.closest(".watch-card");

      expect(providerCard).not.toBeNull();
      expectGuideImmediatelyBeforeField(
        providerCard as HTMLElement,
        provider.name,
        fieldName,
      );
    },
  );
});
