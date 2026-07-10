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
import { integrationData as demoIntegrationData } from "@/api/mockData";
import { travelWatchApi } from "@/api/travelWatchApi";
import { AdminIntegrationsPage } from "@/pages/AdminIntegrationsPage";

const acquisitionGuide: IntegrationAcquisitionGuide = {
  links: [
    { label: "Duffel flights getting started", url: "https://duffel.example/setup" },
    { label: "Amadeus quick start", url: "https://amadeus.example/setup" },
    {
      label: "Kiwi invitation-only partnership announcement",
      url: "https://kiwi.example/partners",
    },
    { label: "Hotelbeds getting started", url: "https://hotelbeds.example/setup" },
    { label: "Booking.com Demand API", url: "https://booking.example/demand" },
  ],
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
          { key: "api_key", label: "Hotelbeds API key", sensitive: true },
          { key: "api_secret", label: "Hotelbeds API secret", sensitive: true },
        ],
      }),
      fieldName: "Hotelbeds API key",
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
          { key: "access_token", label: "Duffel access token", sensitive: true },
          { key: "client_id", label: "Amadeus Client ID", sensitive: true },
          { key: "client_secret", label: "Amadeus Client secret", sensitive: true },
          { key: "api_key", label: "Kiwi Tequila API key", sensitive: true },
        ],
      }),
      fieldName: "Duffel access token",
      guideProviderName: "Duffel",
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
    async ({ category, provider, fieldName, guideProviderName }) => {
      renderCategory(category, [provider]);

      const providerHeading = await screen.findByRole("heading", {
        name: provider.name,
      });
      const providerCard = providerHeading.closest(".watch-card");

      expect(providerCard).not.toBeNull();
      expectGuideImmediatelyBeforeField(
        providerCard as HTMLElement,
        guideProviderName ?? provider.name,
        fieldName,
      );
    },
  );

  it.each([
    {
      providerKey: "duffel",
      providerLabel: "Duffel",
      visibleFields: ["Duffel access token"],
      hiddenFields: ["Amadeus Client ID", "Amadeus Client secret", "Kiwi Tequila API key"],
      linkName: "Duffel flights getting started",
    },
    {
      providerKey: "amadeus",
      providerLabel: "Amadeus",
      visibleFields: ["Amadeus Client ID", "Amadeus Client secret"],
      hiddenFields: ["Duffel access token", "Kiwi Tequila API key"],
      linkName: "Amadeus quick start",
    },
    {
      providerKey: "kiwi",
      providerLabel: "Kiwi",
      visibleFields: ["Kiwi Tequila API key"],
      hiddenFields: ["Duffel access token", "Amadeus Client ID", "Amadeus Client secret"],
      linkName: "Kiwi invitation-only partnership announcement",
    },
  ])(
    "renders only $providerLabel direct booking credentials and links",
    async ({
      providerKey,
      providerLabel,
      visibleFields,
      hiddenFields,
      linkName,
    }) => {
      const provider = buildProvider({
        key: "booking",
        name: "Booking",
        category: "booking",
        supportsSharedProfile: true,
        compatibleProfileProviderKeys: ["duffel", "amadeus", "kiwi"],
        credentialsMasked: { provider: providerKey },
        credentialFields: [
          { key: "provider", label: "Provider", sensitive: false },
          { key: "access_token", label: "Duffel access token", sensitive: true },
          { key: "client_id", label: "Amadeus Client ID", sensitive: true },
          { key: "client_secret", label: "Amadeus Client secret", sensitive: true },
          { key: "api_key", label: "Kiwi Tequila API key", sensitive: true },
        ],
      });
      renderCategory("booking", [provider]);

      const heading = await screen.findByRole("heading", { name: "Booking" });
      const card = heading.closest(".watch-card") as HTMLElement;
      const cardQueries = within(card);

      for (const fieldName of visibleFields) {
        expect(cardQueries.getByLabelText(fieldName, { exact: false })).toBeInTheDocument();
      }
      for (const fieldName of hiddenFields) {
        expect(cardQueries.queryByLabelText(fieldName, { exact: false })).not.toBeInTheDocument();
      }
      expect(
        cardQueries.getByText(`How to get ${providerLabel} credentials`),
      ).toBeInTheDocument();
      expect(
        cardQueries.getByRole("link", { name: linkName, hidden: true }),
      ).toBeInTheDocument();
      expect(card.querySelectorAll(".credential-guide a")).toHaveLength(1);
    },
  );

  it("renders complete Hotelbeds fields and labeled provider destinations", async () => {
    const provider = buildProvider({
      key: "hotels",
      name: "Hotels",
      category: "hotels",
      credentialsMasked: { provider: "hotelbeds" },
      credentialFields: [
        { key: "provider", label: "Provider", sensitive: false },
        { key: "api_key", label: "Hotelbeds API key", sensitive: true },
        { key: "api_secret", label: "Hotelbeds API secret", sensitive: true },
      ],
    });
    renderCategory("hotels", [provider]);

    const heading = await screen.findByRole("heading", { name: "Hotels" });
    const card = heading.closest(".watch-card") as HTMLElement;
    const cardQueries = within(card);

    expect(cardQueries.getByLabelText("Hotelbeds API key")).toBeInTheDocument();
    expect(cardQueries.getByLabelText("Hotelbeds API secret")).toBeInTheDocument();
    expect(
      cardQueries.getByRole("link", {
        name: "Hotelbeds getting started",
        hidden: true,
      }),
    ).toBeInTheDocument();
    expect(
      cardQueries.getByRole("link", {
        name: "Booking.com Demand API",
        hidden: true,
      }),
    ).toBeInTheDocument();
  });

  it("labels unsupported non-Hotelbeds credential shapes", async () => {
    const provider = buildProvider({
      key: "hotels",
      name: "Hotels",
      category: "hotels",
      credentialsMasked: { provider: "booking" },
      credentialFields: [
        { key: "provider", label: "Provider", sensitive: false },
        { key: "api_key", label: "Hotelbeds API key", sensitive: true },
        { key: "api_secret", label: "Hotelbeds API secret", sensitive: true },
      ],
    });
    renderCategory("hotels", [provider]);

    const heading = await screen.findByRole("heading", { name: "Hotels" });
    const card = heading.closest(".watch-card") as HTMLElement;
    const cardQueries = within(card);

    expect(
      cardQueries.getByText(
        "TRAMP does not define a Booking credential shape in this connector.",
      ),
    ).toBeInTheDocument();
    expect(cardQueries.queryByLabelText("Hotelbeds API key")).not.toBeInTheDocument();
    expect(cardQueries.queryByLabelText("Hotelbeds API secret")).not.toBeInTheDocument();
  });

  it("does not duplicate a flight guide when a shared profile hides direct fields", async () => {
    const provider = buildProvider({
      key: "flights_amadeus",
      name: "Flights · Amadeus",
      category: "flights",
      providerKey: "amadeus",
      supportsSharedProfile: true,
      compatibleProfileProviderKeys: ["amadeus"],
      credentialProfileId: "profile-amadeus",
      credentialFields: [
        { key: "client_id", label: "Client ID", sensitive: true },
      ],
    });
    renderCategory("flights", [provider], [
      {
        id: "profile-amadeus",
        providerKey: "amadeus",
        label: "Amadeus profile",
        credentialsMasked: {},
        usageIntegrationKeys: ["flights_amadeus"],
      },
    ]);

    const heading = await screen.findByRole("heading", {
      name: "Flights · Amadeus",
    });
    const connectorCard = heading.closest(".watch-card") as HTMLElement;

    expect(connectorCard.querySelector(".credential-guide")).toBeNull();
    expect(within(connectorCard).queryByLabelText("Client ID")).not.toBeInTheDocument();
    expect(document.querySelectorAll(".credential-guide")).toHaveLength(1);
  });

  it("does not duplicate a booking guide when a shared profile hides direct fields", async () => {
    const bookingProvider = buildProvider({
      key: "booking",
      name: "Booking",
      category: "booking",
      supportsSharedProfile: true,
      compatibleProfileProviderKeys: ["duffel", "amadeus", "kiwi"],
      credentialProfileId: "profile-duffel",
      credentialFields: [
        { key: "provider", label: "Provider", sensitive: false },
        { key: "access_token", label: "Duffel access token", sensitive: true },
      ],
    });
    const duffelTemplate = buildProvider({
      key: "flights_duffel",
      name: "Flights · Duffel",
      category: "flights",
      providerKey: "duffel",
      supportsSharedProfile: true,
      compatibleProfileProviderKeys: ["duffel"],
      credentialFields: [
        { key: "access_token", label: "Duffel access token", sensitive: true },
      ],
    });
    renderCategory("booking", [bookingProvider, duffelTemplate], [
      {
        id: "profile-duffel",
        providerKey: "duffel",
        label: "Duffel profile",
        credentialsMasked: {},
        usageIntegrationKeys: ["booking"],
      },
    ]);

    const heading = await screen.findByRole("heading", { name: "Booking" });
    const connectorCard = heading.closest(".watch-card") as HTMLElement;

    expect(connectorCard.querySelector(".credential-guide")).toBeNull();
    expect(
      within(connectorCard).queryByLabelText("Duffel access token"),
    ).not.toBeInTheDocument();
    expect(document.querySelectorAll(".credential-guide")).toHaveLength(1);
  });

  it.each([
    {
      category: "hotels",
      provider: buildProvider({
        key: "hotels",
        name: "Hotels",
        category: "hotels",
        credentialsMasked: { provider: "hotelbeds" },
        credentialFields: [
          { key: "provider", label: "Provider", sensitive: false },
          { key: "api_key", label: "Hotelbeds API key", sensitive: true },
          { key: "api_secret", label: "Hotelbeds API secret", sensitive: true },
        ],
      }),
      expected:
        "Environment selection stores configuration intent only. Current hotel runtime remains deterministic and simulated until a real provider adapter is implemented.",
    },
    {
      category: "booking",
      provider: buildProvider({
        key: "booking",
        name: "Booking",
        category: "booking",
        credentialsMasked: { provider: "duffel" },
        credentialFields: [
          { key: "provider", label: "Provider", sensitive: false },
          { key: "access_token", label: "Duffel access token", sensitive: true },
        ],
      }),
      expected:
        "Credentials can be configured for test or live environments, but current booking execution remains simulated and local-safe.",
    },
    {
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
      expected:
        "Credentials can be configured for test or live environments, but current flight search remains deterministic and simulated until a real provider adapter is implemented.",
    },
  ])(
    "describes the current $category runtime without implying live provider execution",
    async ({ category, provider, expected }) => {
      renderCategory(category, [provider]);

      expect(await screen.findByText(expected)).toBeInTheDocument();
      expect(document.body).not.toHaveTextContent(/live wiring|live-ready/i);
    },
  );

  it("keeps demo integration summaries explicit about simulated runtimes", () => {
    const providers = Object.fromEntries(
      demoIntegrationData.providers.map((provider) => [provider.key, provider]),
    );
    const demoCopy = [
      ...demoIntegrationData.categories.map((category) => category.description),
      ...demoIntegrationData.providers.map((provider) => provider.detail),
      ...demoIntegrationData.featureFlags.map((flag) => flag.label),
      ...demoIntegrationData.healthNotes,
    ].join(" ");

    expect(providers.flights_amadeus.detail).toMatch(/deterministic and simulated/i);
    expect(providers.flights_duffel.detail).toMatch(/deterministic and simulated/i);
    expect(providers.hotels.detail).toMatch(/deterministic and simulated/i);
    expect(providers.booking.detail).toMatch(/simulated and local-safe/i);
    expect(providers.hotels.environment).toBe("test");
    expect(demoCopy).not.toMatch(
      /live wiring|live-ready|degraded latency|failover still healthy|auto-book available/i,
    );
  });
});
