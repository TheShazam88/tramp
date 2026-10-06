import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useMemo, useState } from "react";
import { useParams } from "react-router-dom";

import { ApiError, apiClient } from "@/api/client";
import { queryKeys, travelWatchApi } from "@/api/travelWatchApi";
import type {
  IntegrationCategory,
  IntegrationCredentialProfile,
  IntegrationProvider,
} from "@/api/types";
import { CredentialGuide } from "@/components/admin/CredentialGuide";
import { PurgeTestDataPanel } from "@/components/admin/PurgeTestDataPanel";
import { Badge, Button, EmptyState, InfoList, SectionHeading, Surface } from "@/components/ui/primitives";

const toneByStatus = {
  connected: "value",
  attention: "alert",
  disabled: "muted",
  not_set: "muted",
} as const;

const environmentOptions = ["test", "live", "off"] as const;
const bookingProviderOptions = ["duffel", "amadeus", "kiwi"] as const;
const hotelProviderOptions = ["hotelbeds", "booking"] as const;
const messagingModeOptions = ["log_only", "smtp_dev", "telegram_bot"] as const;
const calendarModeOptions = ["log_only", "google_calendar"] as const;

type ConnectorDraft = {
  enabled: boolean;
  environment: string;
  credentialProfileId: string;
  credentials: Record<string, string>;
  featureFlags: Record<string, boolean>;
};

type ProfileDraft = {
  providerKey: string;
  label: string;
  credentials: Record<string, string>;
};

function getErrorMessage(error: unknown, fallback: string) {
  if (error instanceof ApiError && typeof error.payload === "object" && error.payload) {
    const detail = (error.payload as { detail?: unknown }).detail;
    if (typeof detail === "string") {
      return detail;
    }
  }

  if (error instanceof Error && error.message) {
    return error.message;
  }

  return fallback;
}

function formatTestedAt(value?: string) {
  if (!value) {
    return "";
  }

  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) {
    return value;
  }

  return new Intl.DateTimeFormat(undefined, {
    month: "short",
    day: "numeric",
    hour: "numeric",
    minute: "2-digit",
  }).format(parsed);
}

function titleize(value: string) {
  return value
    .split(/[_\s-]+/)
    .filter(Boolean)
    .map((part) => part[0].toUpperCase() + part.slice(1))
    .join(" ");
}

function buildConnectorDraft(provider: IntegrationProvider): ConnectorDraft {
  return {
    enabled: provider.enabled,
    environment: String(provider.environment),
    credentialProfileId: provider.credentialProfileId ?? "",
    credentials: provider.credentialFields.reduce<Record<string, string>>((accumulator, field) => {
      if (field.sensitive) {
        accumulator[field.key] = "";
      } else {
        accumulator[field.key] =
          typeof provider.credentialsMasked?.[field.key] === "string"
            ? String(provider.credentialsMasked[field.key] ?? "")
            : "";
      }
      return accumulator;
    }, {}),
    featureFlags: provider.featureFlagDefinitions.reduce<Record<string, boolean>>((accumulator, definition) => {
      const matched = provider.featureFlags.find((flag) => flag.label === definition.label);
      accumulator[definition.key] = matched?.enabled ?? definition.defaultEnabled ?? false;
      return accumulator;
    }, {}),
  };
}

function buildProfileDraft(
  profile: IntegrationCredentialProfile,
  providers: IntegrationProvider[],
): ProfileDraft {
  const template = providers.find((provider) => provider.providerKey === profile.providerKey);
  return {
    providerKey: profile.providerKey,
    label: profile.label,
    credentials: (template?.credentialFields ?? []).reduce<Record<string, string>>((accumulator, field) => {
      accumulator[field.key] = field.sensitive
        ? ""
        : typeof profile.credentialsMasked?.[field.key] === "string"
          ? String(profile.credentialsMasked[field.key] ?? "")
          : "";
      return accumulator;
    }, {}),
  };
}

function buildCredentialPayload(
  fields: IntegrationProvider["credentialFields"],
  credentials: Record<string, string>,
) {
  const payload: Record<string, string> = {};
  for (const field of fields) {
    const value = credentials[field.key] ?? "";
    if (field.sensitive && !value.trim()) {
      continue;
    }
    payload[field.key] = value;
  }
  return payload;
}

function getProfileTemplate(providers: IntegrationProvider[], providerKey: string) {
  return providers.find((provider) => provider.providerKey === providerKey);
}

function CredentialFieldList({
  fields,
  values,
  masked,
  idPrefix,
  onChange,
}: {
  fields: Array<{
    key: string;
    label: string;
    placeholder?: string;
    helpText?: string;
    sensitive?: boolean;
  }>;
  values: Record<string, string>;
  masked?: Record<string, unknown> | null;
  idPrefix: string;
  onChange: (key: string, value: string) => void;
}) {
  return (
    <>
      {fields.map((field) => (
        <label
          key={`${idPrefix}-${field.key}`}
          className={field.sensitive ? "field-stack field-span-full" : "field-stack"}
        >
          <span>{field.label}</span>
          <input
            className="text-input"
            type={field.sensitive ? "password" : "text"}
            value={values[field.key] ?? ""}
            placeholder={
              field.sensitive
                ? getSensitivePlaceholder(
                    masked?.[field.key],
                    field.placeholder || "Type a new value to replace",
                  )
                : field.placeholder
            }
            onChange={(event) => onChange(field.key, event.target.value)}
          />
          {field.helpText ? <p className="helper-copy">{field.helpText}</p> : null}
        </label>
      ))}
    </>
  );
}

function getSensitivePlaceholder(
  maskedValue: unknown,
  fallback: string,
) {
  return typeof maskedValue === "string" && maskedValue
    ? `${maskedValue} saved · type a new value to replace`
    : fallback;
}

function withCurrentOption(options: readonly string[], currentValue: string) {
  return currentValue && !options.includes(currentValue) ? [currentValue, ...options] : [...options];
}

function guideForProvider(
  guide: IntegrationProvider["guide"],
  providerKey: string,
) {
  if (!guide || !providerKey) {
    return undefined;
  }
  const linkNeedle = providerKey === "booking" ? "booking.com" : providerKey;
  const links = guide.links.filter((link) =>
    link.label.toLowerCase().includes(linkNeedle),
  );
  return links.length > 0 ? { ...guide, links } : undefined;
}

function compactJoin(values: string[]) {
  if (values.length === 0) {
    return "";
  }
  if (values.length === 1) {
    return values[0];
  }
  if (values.length === 2) {
    return `${values[0]} + ${values[1]}`;
  }
  return `${values[0]} + ${values[1]} + ${values.length - 2} more`;
}

export function AdminIntegrationsPage() {
  const { categoryId } = useParams();
  const queryClient = useQueryClient();
  const liveMode = apiClient.mode === "live";
  const [connectorDrafts, setConnectorDrafts] = useState<Record<string, ConnectorDraft>>({});
  const [advancedOverrideVisibility, setAdvancedOverrideVisibility] = useState<Record<string, boolean>>({});
  const [profileDrafts, setProfileDrafts] = useState<Record<string, ProfileDraft>>({});
  const [newProfileDraft, setNewProfileDraft] = useState<ProfileDraft>({
    providerKey: "",
    label: "",
    credentials: {},
  });
  const [connectionMessages, setConnectionMessages] = useState<
    Record<string, { tone: "value" | "alert"; message: string }>
  >({});
  const [batchNotice, setBatchNotice] = useState<{ tone: "value" | "alert"; message: string } | null>(null);
  const [mockDataEnabledDraft, setMockDataEnabledDraft] = useState(true);

  const { data, error } = useQuery({
    queryKey: queryKeys.integrations,
    queryFn: travelWatchApi.getIntegrations,
  });

  useEffect(() => {
    if (!data) {
      return;
    }
    setMockDataEnabledDraft(data.runtimeSettings.mockDataEnabled);
    setConnectorDrafts(
      Object.fromEntries(
        data.providers.map((provider) => [provider.key, buildConnectorDraft(provider)]),
      ),
    );
    setProfileDrafts(
      Object.fromEntries(
        data.credentialProfiles.map((profile) => [
          profile.id,
          buildProfileDraft(profile, data.providers),
        ]),
      ),
    );
  }, [data]);

  const saveIntegrationMutation = useMutation({
    mutationFn: travelWatchApi.saveIntegration,
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: queryKeys.integrations });
      setBatchNotice({ tone: "value", message: "Integration settings saved." });
    },
    onError: (mutationError) => {
      setBatchNotice({
        tone: "alert",
        message: getErrorMessage(mutationError, "Unable to save integration settings."),
      });
    },
  });

  const saveCredentialProfileMutation = useMutation({
    mutationFn: travelWatchApi.saveCredentialProfile,
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: queryKeys.integrations });
      setBatchNotice({ tone: "value", message: "Shared credential profile saved." });
    },
    onError: (mutationError) => {
      setBatchNotice({
        tone: "alert",
        message: getErrorMessage(mutationError, "Unable to save the shared credential profile."),
      });
    },
  });

  const deleteCredentialProfileMutation = useMutation({
    mutationFn: travelWatchApi.deleteCredentialProfile,
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: queryKeys.integrations });
      setBatchNotice({ tone: "value", message: "Shared credential profile deleted." });
    },
    onError: (mutationError) => {
      setBatchNotice({
        tone: "alert",
        message: getErrorMessage(mutationError, "Unable to delete the shared credential profile."),
      });
    },
  });

  const saveRuntimeSettingsMutation = useMutation({
    mutationFn: travelWatchApi.saveRuntimeSettings,
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: queryKeys.integrations });
      await queryClient.invalidateQueries({ queryKey: queryKeys.systemStatus });
      await queryClient.invalidateQueries({ queryKey: queryKeys.dashboard });
      await queryClient.invalidateQueries({ queryKey: queryKeys.bookings });
      setBatchNotice({
        tone: "value",
        message: mockDataEnabledDraft
          ? "Mock data is enabled. The product may show fallback mock inventory when live data is unavailable."
          : "Mock data is disabled. Provider-backed inventory appears only when a real connector supplies it; otherwise users see empty states.",
      });
    },
    onError: (mutationError) => {
      setBatchNotice({
        tone: "alert",
        message: getErrorMessage(mutationError, "Unable to save mock data runtime settings."),
      });
    },
  });

  const testConnectionMutation = useMutation({
    mutationFn: (provider: IntegrationProvider) => travelWatchApi.testIntegrationConnection(provider.key),
    onSuccess: (result, provider) => {
      const suffix = result.testedAt ? ` Last checked ${formatTestedAt(result.testedAt)}.` : "";
      setConnectionMessages((current) => ({
        ...current,
        [provider.key]: {
          tone: result.status === "connected" ? "value" : "alert",
          message: `${result.message}${suffix}`,
        },
      }));
      setBatchNotice(null);
    },
    onError: (mutationError, provider) => {
      setConnectionMessages((current) => ({
        ...current,
        [provider.key]: {
          tone: "alert",
          message: getErrorMessage(
            mutationError,
            `Unable to test ${provider.name} from the admin integrations API.`,
          ),
        },
      }));
      setBatchNotice(null);
    },
  });

  const categories = data?.categories ?? [];
  const activeCategory = categories.find((category) => category.id === categoryId);
  const categoryProviders = useMemo(
    () => (data?.providers ?? []).filter((provider) => provider.category === categoryId),
    [data, categoryId],
  );
  const categoryProfiles = useMemo(() => {
    const providerKeys = new Set(
      categoryProviders.flatMap((provider) => provider.compatibleProfileProviderKeys),
    );
    return (data?.credentialProfiles ?? []).filter((profile) => providerKeys.has(profile.providerKey));
  }, [data, categoryProviders]);
  const testableProviders = useMemo(
    () => categoryProviders.filter((provider) => connectorDrafts[provider.key]?.enabled),
    [categoryProviders, connectorDrafts],
  );

  const testAllMutation = useMutation({
    mutationFn: async (providers: IntegrationProvider[]) =>
      Promise.all(
        providers.map(async (provider) => {
          try {
            const result = await travelWatchApi.testIntegrationConnection(provider.key);
            return { provider, result, error: null };
          } catch (mutationError) {
            return { provider, result: null, error: mutationError };
          }
        }),
      ),
    onSuccess: (results) => {
      const nextMessages: Record<string, { tone: "value" | "alert"; message: string }> = {};
      let passed = 0;
      let failed = 0;

      for (const entry of results) {
        if (entry.result) {
          passed += entry.result.status === "connected" ? 1 : 0;
          failed += entry.result.status === "connected" ? 0 : 1;
          nextMessages[entry.provider.key] = {
            tone: entry.result.status === "connected" ? "value" : "alert",
            message: `${entry.result.message}${
              entry.result.testedAt ? ` Last checked ${formatTestedAt(entry.result.testedAt)}.` : ""
            }`,
          };
          continue;
        }

        failed += 1;
        nextMessages[entry.provider.key] = {
          tone: "alert",
          message: getErrorMessage(
            entry.error,
            `Unable to test ${entry.provider.name} from the admin integrations API.`,
          ),
        };
      }

      setConnectionMessages((current) => ({ ...current, ...nextMessages }));
      setBatchNotice({
        tone: failed > 0 ? "alert" : "value",
        message: `Test all complete: ${passed} passed, ${failed} failed.`,
      });
    },
  });

  if (!data) {
    return (
      <div className="stack">
        <Surface>{error ? getErrorMessage(error, "Unable to load admin integrations.") : "Loading admin integrations..."}</Surface>
      </div>
    );
  }

  const renderCategoryNav = () => (
    <div className="pill-row">
      {categories.map((category) => (
        <Button
          key={category.id}
          to={`/admin/integrations/${category.id}`}
          variant={category.id === categoryId ? "primary" : "secondary"}
        >
          {category.title}
        </Button>
      ))}
    </div>
  );

  const renderRuntimePage = () => (
    <div className="stack">
      <Surface>
        <SectionHeading
          eyebrow="Runtime mode"
          title="Mock data control"
          description="This switch controls whether TRAMP is allowed to show any fallback or simulated data anywhere in the product."
        />
        <div className="stack-tight">
          <div className="badge-row">
            <Badge tone={data.runtimeSettings.currentInventoryMode === "live" ? "value" : "alert"}>
              Inventory mode: {data.runtimeSettings.currentInventoryMode}
            </Badge>
            <Badge tone={data.runtimeSettings.liveInventoryAvailable ? "value" : "alert"}>
              {data.runtimeSettings.liveInventoryAvailable ? "live inventory available" : "no live inventory connected"}
            </Badge>
          </div>
          <label className="checkbox-row">
            <input
              type="checkbox"
              checked={mockDataEnabledDraft}
              onChange={(event) => setMockDataEnabledDraft(event.target.checked)}
            />
            <span>Allow fallback mock data anywhere in TRAMP</span>
          </label>
          <p className="helper-copy">
            Key unlock: {data.runtimeSettings.keyUnlockMode || "not reported"}. Master key source:{" "}
            {data.runtimeSettings.masterKeySource || "not reported"}. Integration inventory stays on this admin page. The public health check only reports whether the service is up and which inventory mode is active.
          </p>
          <div className={`notice ${mockDataEnabledDraft ? "notice-value" : "notice-alert"}`}>
            {mockDataEnabledDraft
              ? "ON: TRAMP may show simulated fallback data when live provider data is missing."
              : "OFF: TRAMP shows provider-backed inventory only when a real connector supplies it; otherwise users see empty states."}
          </div>
          <div className="panel-actions">
            <Button
              type="button"
              onClick={() => saveRuntimeSettingsMutation.mutate({ mockDataEnabled: mockDataEnabledDraft })}
              disabled={saveRuntimeSettingsMutation.isPending}
            >
              {saveRuntimeSettingsMutation.isPending ? "Saving..." : "Save runtime setting"}
            </Button>
          </div>
        </div>
      </Surface>

      <PurgeTestDataPanel />

      <Surface>
        <SectionHeading
          eyebrow="Diagnostics"
          title="Health notes"
          description="Persisted backend state for restart-safe operational diagnostics."
        />
        <InfoList items={data.healthNotes} />
      </Surface>
    </div>
  );

  const renderSharedProfiles = () => {
    if (categoryProfiles.length === 0 && categoryProviders.every((provider) => !provider.supportsSharedProfile)) {
      return null;
    }
    const availableProviderKeys = Array.from(
      new Set(categoryProviders.flatMap((provider) => provider.compatibleProfileProviderKeys)),
    );
    const newProfileTemplate = getProfileTemplate(data.providers, newProfileDraft.providerKey);
    return (
      <Surface className="stack-tight">
        <SectionHeading
          eyebrow="Shared credentials"
          title="Credential profiles"
          description="Save once, then link the same encrypted connection to Flights, Booking, and other compatible connectors."
        />
        {categoryProfiles.map((profile) => {
          const draft = profileDrafts[profile.id] ?? buildProfileDraft(profile, data.providers);
          const template = getProfileTemplate(data.providers, draft.providerKey);
          const linkedProviders = data.providers.filter((provider) =>
            profile.usageIntegrationKeys.includes(provider.key),
          );
          const linkedCategories = Array.from(
            new Set(
              linkedProviders
                .map((provider) => categories.find((category) => category.id === provider.category)?.title)
                .filter((value): value is string => Boolean(value)),
            ),
          );
          const linkedConnectorNames = linkedProviders.map((provider) => provider.name);
          const hasWideReuse = linkedCategories.length > 1 || linkedConnectorNames.length > 1;
          return (
            <Surface key={profile.id} className="inset-card list-card">
              <div className="watch-topline">
                <div>
                  <div className="badge-row">
                    <Badge tone="value">{titleize(profile.providerKey)}</Badge>
                    <Badge tone="muted">{profile.usageIntegrationKeys.length} linked</Badge>
                    {linkedCategories.length > 0 ? (
                      <Badge tone={hasWideReuse ? "alert" : "value"}>
                        Used by {compactJoin(linkedCategories)}
                      </Badge>
                    ) : null}
                  </div>
                  <h3>{profile.label}</h3>
                  <p className="helper-copy">
                    Used by: {linkedConnectorNames.length > 0 ? linkedConnectorNames.join(", ") : "not linked yet"}
                  </p>
                </div>
              </div>
              {hasWideReuse ? (
                <div className="notice notice-alert">
                  Editing this shared profile will immediately affect {compactJoin(linkedCategories)} and the linked connectors:{" "}
                  {linkedConnectorNames.join(", ")}.
                </div>
              ) : linkedConnectorNames.length === 1 ? (
                <div className="notice notice-value">
                  Changes here will affect {linkedConnectorNames[0]} because it is currently linked to this profile.
                </div>
              ) : (
                <div className="notice">
                  This profile is not linked yet. You can finish configuring it before attaching it to a connector.
                </div>
              )}
              <details className="multi-select">
                <summary className="multi-select-summary">Profile fields</summary>
                <div className="multi-select-panel">
                  {hasWideReuse ? (
                    <div className="profile-impact-card">
                      <p className="field-label">Cross-page reuse impact</p>
                      <p className="helper-copy">
                        Before saving, confirm that the new token or secret should be used across {compactJoin(linkedCategories)}.
                      </p>
                      <div className="pill-row">
                        {linkedConnectorNames.map((connectorName) => (
                          <span key={connectorName} className="pill">
                            {connectorName}
                          </span>
                        ))}
                      </div>
                    </div>
                  ) : null}
                  <label className="field-stack">
                    <span>Profile label</span>
                    <input
                      className="text-input"
                      value={draft.label}
                      onChange={(event) =>
                        setProfileDrafts((current) => ({
                          ...current,
                          [profile.id]: {
                            ...draft,
                            label: event.target.value,
                          },
                        }))
                      }
                    />
                  </label>
                  <CredentialGuide
                    providerName={template?.name ?? titleize(profile.providerKey)}
                    guide={template?.guide}
                  />
                  <CredentialFieldList
                    fields={template?.credentialFields ?? []}
                    values={draft.credentials}
                    masked={profile.credentialsMasked}
                    idPrefix={profile.id}
                    onChange={(key, value) =>
                      setProfileDrafts((current) => ({
                        ...current,
                        [profile.id]: {
                          ...draft,
                          credentials: {
                            ...draft.credentials,
                            [key]: value,
                          },
                        },
                      }))
                    }
                  />
                </div>
              </details>
              <div className="panel-actions">
                <Button
                  type="button"
                  onClick={() =>
                    saveCredentialProfileMutation.mutate({
                      id: profile.id,
                      providerKey: draft.providerKey,
                      label: draft.label,
                      credentials: buildCredentialPayload(template?.credentialFields ?? [], draft.credentials),
                    })
                  }
                  disabled={saveCredentialProfileMutation.isPending}
                >
                  {saveCredentialProfileMutation.isPending ? "Saving..." : "Save profile"}
                </Button>
                <Button
                  variant="secondary"
                  type="button"
                  onClick={() => deleteCredentialProfileMutation.mutate(profile.id)}
                  disabled={deleteCredentialProfileMutation.isPending}
                >
                  {deleteCredentialProfileMutation.isPending ? "Deleting..." : "Delete profile"}
                </Button>
              </div>
            </Surface>
          );
        })}

        <Surface className="inset-card list-card">
          <h3>Create shared profile</h3>
          <div className="stack-tight">
            <label className="field-stack">
              <span>Provider</span>
              <select
                className="text-input"
                value={newProfileDraft.providerKey}
                onChange={(event) =>
                  setNewProfileDraft({
                    providerKey: event.target.value,
                    label: "",
                    credentials: {},
                  })
                }
              >
                <option value="">Choose provider</option>
                {availableProviderKeys.map((providerKey) => (
                  <option key={providerKey} value={providerKey}>
                    {titleize(providerKey)}
                  </option>
                ))}
              </select>
            </label>
            <label className="field-stack">
              <span>Profile label</span>
              <input
                className="text-input"
                value={newProfileDraft.label}
                placeholder="Primary, Sandbox, Personal, Team"
                onChange={(event) =>
                  setNewProfileDraft((current) => ({
                    ...current,
                    label: event.target.value,
                  }))
                }
              />
            </label>
            <CredentialGuide
              providerName={newProfileTemplate?.name ?? titleize(newProfileDraft.providerKey)}
              guide={newProfileTemplate?.guide}
            />
            <CredentialFieldList
              fields={newProfileTemplate?.credentialFields ?? []}
              values={newProfileDraft.credentials}
              idPrefix="new-profile"
              onChange={(key, value) =>
                setNewProfileDraft((current) => ({
                  ...current,
                  credentials: {
                    ...current.credentials,
                    [key]: value,
                  },
                }))
              }
            />
          </div>
          <div className="panel-actions">
            <Button
              type="button"
              onClick={() =>
                saveCredentialProfileMutation.mutate({
                  providerKey: newProfileDraft.providerKey,
                  label: newProfileDraft.label,
                  credentials: buildCredentialPayload(
                    newProfileTemplate?.credentialFields ?? [],
                    newProfileDraft.credentials,
                  ),
                })
              }
              disabled={saveCredentialProfileMutation.isPending || !newProfileDraft.providerKey || !newProfileDraft.label}
            >
              {saveCredentialProfileMutation.isPending ? "Saving..." : "Create profile"}
            </Button>
          </div>
        </Surface>
      </Surface>
    );
  };

  const updateConnectorDraft = (
    providerKey: string,
    updater: (current: ConnectorDraft) => ConnectorDraft,
  ) => {
    setConnectorDrafts((current) => {
      const provider = data.providers.find((entry) => entry.key === providerKey);
      if (!provider) {
        return current;
      }
      const base = current[providerKey] ?? buildConnectorDraft(provider);
      return {
        ...current,
        [providerKey]: updater(base),
      };
    });
  };

  const renderConnectorHeader = (provider: IntegrationProvider, draft: ConnectorDraft) => (
    <>
      <div className="watch-topline">
        <div>
          <div className="badge-row">
            <Badge tone={toneByStatus[provider.status]}>{provider.status.replace(/_/g, " ")}</Badge>
            <Badge tone={draft.enabled ? "value" : "muted"}>{draft.enabled ? "enabled" : "disabled"}</Badge>
            <Badge tone={draft.environment === "live" ? "value" : draft.environment === "off" ? "muted" : "alert"}>
              {draft.environment}
            </Badge>
          </div>
          <h3>{provider.name}</h3>
          <p className="item-copy">
            Credential state: {provider.credentialState.label}
            {provider.credentialProfileLabel ? ` · linked to ${provider.credentialProfileLabel}` : ""}
          </p>
          {provider.updatedAt ? (
            <p className="helper-copy">
              Updated {formatTestedAt(provider.updatedAt)}
              {provider.updatedBy ? ` by ${provider.updatedBy}` : ""}.
            </p>
          ) : null}
        </div>
      </div>
      <p className="watch-insight">{provider.detail}</p>
      {provider.validationHelp ? <p className="helper-copy">{provider.validationHelp}</p> : null}
    </>
  );

  const renderConnectorFooter = (provider: IntegrationProvider, draft: ConnectorDraft) => (
    <>
      <div className="panel-actions-between">
        <Button
          type="button"
          onClick={() =>
            saveIntegrationMutation.mutate({
              key: provider.key,
              enabled: draft.enabled,
              environment: draft.environment,
              credentialProfileId: draft.credentialProfileId || null,
              credentials: buildCredentialPayload(provider.credentialFields, draft.credentials),
              featureFlags: draft.featureFlags,
            })
          }
          disabled={saveIntegrationMutation.isPending}
        >
          {saveIntegrationMutation.isPending ? "Saving..." : "Save settings"}
        </Button>
        <Button
          variant="secondary"
          type="button"
          onClick={() => testConnectionMutation.mutate(provider)}
          disabled={testConnectionMutation.isPending || testAllMutation.isPending}
        >
          {testConnectionMutation.isPending && testConnectionMutation.variables?.key === provider.key
            ? "Testing..."
            : "Test connection"}
        </Button>
      </div>

      {connectionMessages[provider.key] ? (
        <div
          className={`notice ${
            connectionMessages[provider.key].tone === "alert" ? "notice-alert" : "notice-value"
          }`}
        >
          {connectionMessages[provider.key].message}
        </div>
      ) : null}
    </>
  );

  const renderHotelConnectorCard = (provider: IntegrationProvider, draft: ConnectorDraft) => {
    const providerField = provider.credentialFields.find((field) => field.key === "provider");
    const providerValue = String(draft.credentials.provider ?? "").trim().toLowerCase();
    const hotelbedsFields = provider.credentialFields.filter(
      (field) => field.key === "api_key" || field.key === "api_secret",
    );
    const providerOptions = withCurrentOption(
      hotelProviderOptions,
      providerValue,
    );

    return (
      <Surface key={provider.key} className="watch-card">
        {renderConnectorHeader(provider, draft)}

        <div className="summary-grid">
          <Surface className="field-card">
            <p className="field-label">Connection mode</p>
            <strong>{titleize(draft.environment)}</strong>
            <p className="helper-copy">
              Environment selection stores configuration intent only. Current hotel runtime remains deterministic and simulated until a real provider adapter is implemented.
            </p>
          </Surface>
          <Surface className="field-card">
            <p className="field-label">Inventory source</p>
            <strong>{draft.credentials.provider || "Not set"}</strong>
            <p className="helper-copy">
              Select the provider credential shape represented by this simulated connector.
            </p>
          </Surface>
          <Surface className="field-card">
            <p className="field-label">API secret handling</p>
            <strong>{provider.credentialState.configured ? "Masked after save" : "Awaiting first key"}</strong>
            <p className="helper-copy">Stored hotel credentials never come back in plaintext.</p>
          </Surface>
        </div>

        <div className="form-shell">
          <p className="field-label">Connection controls</p>
          <div className="form-grid">
            <label className="field-stack">
              <span>Environment</span>
              <select
                className="text-input"
                value={draft.environment}
                onChange={(event) =>
                  updateConnectorDraft(provider.key, (current) => ({
                    ...current,
                    environment: event.target.value,
                  }))
                }
              >
                {environmentOptions.map((environment) => (
                  <option key={environment} value={environment}>
                    {environment}
                  </option>
                ))}
              </select>
            </label>
            <label className="field-stack">
              <span>Hotel provider</span>
              <select
                className="text-input"
                value={draft.credentials.provider ?? ""}
                onChange={(event) =>
                  updateConnectorDraft(provider.key, (current) => ({
                    ...current,
                    credentials: {
                      ...current.credentials,
                      provider: event.target.value,
                    },
                  }))
                }
              >
                <option value="">Choose provider</option>
                {providerOptions.map((option) => (
                  <option key={option} value={option}>
                    {option}
                  </option>
                ))}
              </select>
              {providerField?.helpText ? <p className="helper-copy">{providerField.helpText}</p> : null}
            </label>
            <label className="checkbox-row field-span-full">
              <input
                type="checkbox"
                checked={draft.enabled}
                onChange={(event) =>
                  updateConnectorDraft(provider.key, (current) => ({
                    ...current,
                    enabled: event.target.checked,
                  }))
                }
              />
              <span>Hotel connector enabled for watch search</span>
            </label>
          </div>
        </div>

        <div className="form-shell">
          <p className="field-label">API access</p>
          <CredentialGuide providerName={provider.name} guide={provider.guide} />
          {providerValue === "hotelbeds" ? (
            <div className="form-grid">
              <CredentialFieldList
                fields={hotelbedsFields}
                values={draft.credentials}
                masked={provider.credentialsMasked}
                idPrefix={provider.key}
                onChange={(key, value) =>
                  updateConnectorDraft(provider.key, (current) => ({
                    ...current,
                    credentials: {
                      ...current.credentials,
                      [key]: value,
                    },
                  }))
                }
              />
            </div>
          ) : providerValue ? (
            <div className="notice notice-alert">
              TRAMP does not define a {titleize(providerValue)} credential shape in this
              connector.
            </div>
          ) : (
            <div className="notice">Choose a hotel provider to see supported fields.</div>
          )}
        </div>

        {provider.featureFlagDefinitions.length > 0 ? (
          <div className="form-shell">
            <p className="field-label">Operational flags</p>
            <div className="stack-tight">
              {provider.featureFlagDefinitions.map((definition) => (
                <label key={definition.key} className="checkbox-row">
                  <input
                    type="checkbox"
                    checked={draft.featureFlags[definition.key] ?? false}
                    onChange={(event) =>
                      updateConnectorDraft(provider.key, (current) => ({
                        ...current,
                        featureFlags: {
                          ...current.featureFlags,
                          [definition.key]: event.target.checked,
                        },
                      }))
                    }
                  />
                  <span>{definition.label}</span>
                </label>
              ))}
            </div>
          </div>
        ) : null}

        {renderConnectorFooter(provider, draft)}
      </Surface>
    );
  };

  const renderMessagingConnectorCard = (provider: IntegrationProvider, draft: ConnectorDraft) => {
    const modeValue = draft.credentials.delivery_mode || "log_only";
    const showSmtpFields = modeValue === "smtp_dev";
    const showTelegramField = modeValue === "telegram_bot";

    return (
      <Surface key={provider.key} className="watch-card">
        {renderConnectorHeader(provider, draft)}

        <div className="summary-grid">
          <Surface className="field-card">
            <p className="field-label">Delivery mode</p>
            <strong>{titleize(modeValue)}</strong>
            <p className="helper-copy">Choose log-only dry runs, SMTP delivery, or Telegram bot delivery.</p>
          </Surface>
          <Surface className="field-card">
            <p className="field-label">Connection target</p>
            <strong>
              {showSmtpFields
                ? draft.credentials.smtp_host || "SMTP host needed"
                : showTelegramField
                  ? "Telegram bot"
                  : "Local logs only"}
            </strong>
            <p className="helper-copy">Only the credential fields for the active delivery path are shown.</p>
          </Surface>
          <Surface className="field-card">
            <p className="field-label">Notification scope</p>
            <strong>{provider.featureFlags.filter((flag) => flag.enabled).length || 0} active flags</strong>
            <p className="helper-copy">Booking and disruption notifications can be toggled separately.</p>
          </Surface>
        </div>

        <div className="form-shell">
          <p className="field-label">Delivery controls</p>
          <div className="form-grid">
            <label className="field-stack">
              <span>Environment</span>
              <select
                className="text-input"
                value={draft.environment}
                onChange={(event) =>
                  updateConnectorDraft(provider.key, (current) => ({
                    ...current,
                    environment: event.target.value,
                  }))
                }
              >
                {environmentOptions.map((environment) => (
                  <option key={environment} value={environment}>
                    {environment}
                  </option>
                ))}
              </select>
            </label>
            <label className="field-stack">
              <span>Delivery mode</span>
              <select
                className="text-input"
                value={modeValue}
                onChange={(event) =>
                  updateConnectorDraft(provider.key, (current) => ({
                    ...current,
                    credentials: {
                      ...current.credentials,
                      delivery_mode: event.target.value,
                    },
                  }))
                }
              >
                {messagingModeOptions.map((option) => (
                  <option key={option} value={option}>
                    {option}
                  </option>
                ))}
              </select>
            </label>
            <label className="checkbox-row field-span-full">
              <input
                type="checkbox"
                checked={draft.enabled}
                onChange={(event) =>
                  updateConnectorDraft(provider.key, (current) => ({
                    ...current,
                    enabled: event.target.checked,
                  }))
                }
              />
              <span>Messaging connector enabled</span>
            </label>
          </div>
        </div>

        <CredentialGuide providerName={provider.name} guide={provider.guide} />

        {showSmtpFields ? (
          <div className="form-shell">
            <p className="field-label">SMTP connection</p>
            <div className="form-grid">
              <CredentialFieldList
                fields={["smtp_host", "smtp_port", "smtp_from_address", "smtp_username", "smtp_password"].flatMap(
                  (fieldKey) => {
                    const field = provider.credentialFields.find((entry) => entry.key === fieldKey);
                    return field ? [field] : [];
                  },
                )}
                values={draft.credentials}
                masked={provider.credentialsMasked}
                idPrefix={provider.key}
                onChange={(key, value) =>
                  updateConnectorDraft(provider.key, (current) => ({
                    ...current,
                    credentials: { ...current.credentials, [key]: value },
                  }))
                }
              />
            </div>
          </div>
        ) : null}

        {showTelegramField ? (
          <div className="form-shell">
            <p className="field-label">Telegram bot connection</p>
            <div className="form-grid">
              <CredentialFieldList
                fields={provider.credentialFields.filter((field) => field.key === "telegram_bot_token")}
                values={draft.credentials}
                masked={provider.credentialsMasked}
                idPrefix={provider.key}
                onChange={(key, value) =>
                  updateConnectorDraft(provider.key, (current) => ({
                    ...current,
                    credentials: { ...current.credentials, [key]: value },
                  }))
                }
              />
            </div>
          </div>
        ) : null}

        {!showSmtpFields && !showTelegramField ? (
          <Surface className="inset-card">
            <p className="field-label">Local-safe mode</p>
            <p className="helper-copy">
              `log_only` keeps messaging fully localhost-safe. Notifications are recorded without sending them externally.
            </p>
          </Surface>
        ) : null}

        {provider.featureFlagDefinitions.length > 0 ? (
          <div className="form-shell">
            <p className="field-label">Notification coverage</p>
            <div className="stack-tight">
              {provider.featureFlagDefinitions.map((definition) => (
                <label key={definition.key} className="checkbox-row">
                  <input
                    type="checkbox"
                    checked={draft.featureFlags[definition.key] ?? false}
                    onChange={(event) =>
                      updateConnectorDraft(provider.key, (current) => ({
                        ...current,
                        featureFlags: {
                          ...current.featureFlags,
                          [definition.key]: event.target.checked,
                        },
                      }))
                    }
                  />
                  <span>{definition.label}</span>
                </label>
              ))}
            </div>
          </div>
        ) : null}

        {renderConnectorFooter(provider, draft)}
      </Surface>
    );
  };

  const renderBookingConnectorCard = (provider: IntegrationProvider, draft: ConnectorDraft) => {
    const providerValue = String(draft.credentials.provider ?? "").trim().toLowerCase();
    const providerOptions = withCurrentOption(bookingProviderOptions, providerValue);
    const profileOptions = data.credentialProfiles.filter((profile) =>
      provider.compatibleProfileProviderKeys.includes(profile.providerKey),
    );
    const linkedProfile = profileOptions.find((profile) => profile.id === draft.credentialProfileId);
    const usingSharedProfile = Boolean(draft.credentialProfileId);
    const effectiveProviderValue = usingSharedProfile
      ? linkedProfile?.providerKey ?? providerValue
      : providerValue;
    const directFieldKeys: Record<string, string[]> = {
      duffel: ["access_token", "account_id"],
      amadeus: ["client_id", "client_secret", "account_id"],
      kiwi: ["api_key", "account_id"],
    };
    const visibleDirectFields = provider.credentialFields.filter((field) =>
      (directFieldKeys[providerValue] ?? []).includes(field.key),
    );
    const directGuide = guideForProvider(provider.guide, providerValue);

    return (
      <Surface key={provider.key} className="watch-card">
        {renderConnectorHeader(provider, draft)}

        <div className="summary-grid">
          <Surface className="field-card">
            <p className="field-label">Execution mode</p>
            <strong>{titleize(draft.environment)}</strong>
            <p className="helper-copy">
              Credentials can be configured for test or live environments, but current booking execution remains simulated and local-safe.
            </p>
          </Surface>
          <Surface className="field-card">
            <p className="field-label">Provider family</p>
            <strong>{effectiveProviderValue || "Not set"}</strong>
            <p className="helper-copy">
              Select the credential shape to store or reuse. This does not enable live booking execution.
            </p>
          </Surface>
          <Surface className="field-card">
            <p className="field-label">Credential source</p>
            <strong>{usingSharedProfile ? `Shared profile: ${linkedProfile?.label ?? "linked"}` : "Connector overrides"}</strong>
            <p className="helper-copy">Shared profiles prevent re-pasting the same provider secrets across Flights and Booking.</p>
          </Surface>
        </div>

        <div className="form-shell">
          <p className="field-label">Provider and execution controls</p>
          <div className="form-grid">
            <label className="field-stack">
              <span>Environment</span>
              <select
                className="text-input"
                value={draft.environment}
                onChange={(event) =>
                  updateConnectorDraft(provider.key, (current) => ({
                    ...current,
                    environment: event.target.value,
                  }))
                }
              >
                {environmentOptions.map((environment) => (
                  <option key={environment} value={environment}>
                    {environment}
                  </option>
                ))}
              </select>
            </label>
            <label className="field-stack">
              <span>Booking provider</span>
              <select
                className="text-input"
                value={effectiveProviderValue}
                disabled={usingSharedProfile}
                onChange={(event) =>
                  updateConnectorDraft(provider.key, (current) => ({
                    ...current,
                    credentials: {
                      ...current.credentials,
                      provider: event.target.value,
                    },
                  }))
                }
              >
                <option value="">Choose provider</option>
                {providerOptions.map((option) => (
                  <option key={option} value={option}>
                    {option}
                  </option>
                ))}
              </select>
            </label>
            <label className="checkbox-row field-span-full">
              <input
                type="checkbox"
                checked={draft.enabled}
                onChange={(event) =>
                  updateConnectorDraft(provider.key, (current) => ({
                    ...current,
                    enabled: event.target.checked,
                  }))
                }
              />
              <span>Booking connector enabled</span>
            </label>
          </div>
        </div>

        <div className="form-shell">
          <p className="field-label">Shared credential profile</p>
          <div className="form-grid">
            <label className="field-stack field-span-full">
              <span>Linked profile</span>
              <select
                className="text-input"
                value={draft.credentialProfileId}
                onChange={(event) => {
                  const nextProfile = profileOptions.find(
                    (profile) => profile.id === event.target.value,
                  );
                  updateConnectorDraft(provider.key, (current) => ({
                    ...current,
                    credentialProfileId: event.target.value,
                    credentials: nextProfile
                      ? {
                          ...current.credentials,
                          provider: nextProfile.providerKey,
                        }
                      : current.credentials,
                  }));
                }}
              >
                <option value="">No shared profile</option>
                {profileOptions.map((profile) => (
                  <option key={profile.id} value={profile.id}>
                    {profile.label} ({titleize(profile.providerKey)})
                  </option>
                ))}
              </select>
            </label>
          </div>
          {usingSharedProfile ? (
            <p className="helper-copy">
              This booking connector uses the linked profile as its provider and credential source.
            </p>
          ) : (
            <p className="helper-copy">
              No shared profile is linked. Booking will rely only on the connector-specific credentials saved below.
            </p>
          )}
        </div>

        {!usingSharedProfile ? (
          <div className="form-shell">
            <p className="field-label">Direct provider credentials</p>
            {directGuide ? (
              <CredentialGuide
                providerName={titleize(providerValue)}
                guide={directGuide}
              />
            ) : null}
            {visibleDirectFields.length > 0 ? (
              <div className="form-grid">
                <CredentialFieldList
                  fields={visibleDirectFields}
                  values={draft.credentials}
                  masked={provider.credentialsMasked}
                  idPrefix={provider.key}
                  onChange={(key, value) =>
                    updateConnectorDraft(provider.key, (current) => ({
                      ...current,
                      credentials: { ...current.credentials, [key]: value },
                    }))
                  }
                />
              </div>
            ) : (
              <div className="notice notice-alert">
                Direct booking supports Duffel, Amadeus, or Kiwi. Choose one or link a
                matching shared profile.
              </div>
            )}
          </div>
        ) : (
          <Surface className="inset-card">
            <p className="field-label">Shared profile is the credential source</p>
            <p className="helper-copy">
              Direct fields and their setup guide are hidden. Edit the linked profile
              above to replace its provider credentials.
            </p>
          </Surface>
        )}

        <Surface className="inset-card">
          <p className="field-label">Execution notes</p>
          <p className="helper-copy">
            Sensitive keys remain write-only after save. `Account ID` and `Provider` support clearer routing and diagnostics, while tokens and secrets are never returned in plaintext.
          </p>
        </Surface>

        {provider.featureFlagDefinitions.length > 0 ? (
          <div className="form-shell">
            <p className="field-label">Operational flags</p>
            <div className="stack-tight">
              {provider.featureFlagDefinitions.map((definition) => (
                <label key={definition.key} className="checkbox-row">
                  <input
                    type="checkbox"
                    checked={draft.featureFlags[definition.key] ?? false}
                    onChange={(event) =>
                      updateConnectorDraft(provider.key, (current) => ({
                        ...current,
                        featureFlags: {
                          ...current.featureFlags,
                          [definition.key]: event.target.checked,
                        },
                      }))
                    }
                  />
                  <span>{definition.label}</span>
                </label>
              ))}
            </div>
          </div>
        ) : null}

        {renderConnectorFooter(provider, draft)}
      </Surface>
    );
  };

  const renderCalendarConnectorCard = (provider: IntegrationProvider, draft: ConnectorDraft) => {
    const modeValue = draft.credentials.delivery_mode || "log_only";
    const googleCalendarMode = modeValue === "google_calendar";

    return (
      <Surface key={provider.key} className="watch-card">
        {renderConnectorHeader(provider, draft)}

        <div className="summary-grid">
          <Surface className="field-card">
            <p className="field-label">Calendar mode</p>
            <strong>{titleize(modeValue)}</strong>
            <p className="helper-copy">Switch between local-safe logging and Google Calendar sync.</p>
          </Surface>
          <Surface className="field-card">
            <p className="field-label">Target calendar</p>
            <strong>{googleCalendarMode ? draft.credentials.calendar_id || "Calendar ID needed" : "No external calendar"}</strong>
            <p className="helper-copy">External calendar details are only needed when Google Calendar mode is active.</p>
          </Surface>
          <Surface className="field-card">
            <p className="field-label">Conflict checks</p>
            <strong>{draft.featureFlags.enable_conflict_check ? "Enabled" : "Disabled"}</strong>
            <p className="helper-copy">Use this to surface overlap advisories during validation.</p>
          </Surface>
        </div>

        <div className="form-shell">
          <p className="field-label">Calendar controls</p>
          <div className="form-grid">
            <label className="field-stack">
              <span>Environment</span>
              <select
                className="text-input"
                value={draft.environment}
                onChange={(event) =>
                  updateConnectorDraft(provider.key, (current) => ({
                    ...current,
                    environment: event.target.value,
                  }))
                }
              >
                {environmentOptions.map((environment) => (
                  <option key={environment} value={environment}>
                    {environment}
                  </option>
                ))}
              </select>
            </label>
            <label className="field-stack">
              <span>Delivery mode</span>
              <select
                className="text-input"
                value={modeValue}
                onChange={(event) =>
                  updateConnectorDraft(provider.key, (current) => ({
                    ...current,
                    credentials: {
                      ...current.credentials,
                      delivery_mode: event.target.value,
                    },
                  }))
                }
              >
                {calendarModeOptions.map((option) => (
                  <option key={option} value={option}>
                    {option}
                  </option>
                ))}
              </select>
            </label>
            <label className="checkbox-row field-span-full">
              <input
                type="checkbox"
                checked={draft.enabled}
                onChange={(event) =>
                  updateConnectorDraft(provider.key, (current) => ({
                    ...current,
                    enabled: event.target.checked,
                  }))
                }
              />
              <span>Calendar connector enabled</span>
            </label>
          </div>
        </div>

        <CredentialGuide providerName={provider.name} guide={provider.guide} />

        {googleCalendarMode ? (
          <div className="form-shell">
            <p className="field-label">Google Calendar connection</p>
            <div className="form-grid">
              <CredentialFieldList
                fields={provider.credentialFields.filter(
                  (field) => field.key === "calendar_id" || field.key === "access_token",
                )}
                values={draft.credentials}
                masked={provider.credentialsMasked}
                idPrefix={provider.key}
                onChange={(key, value) =>
                  updateConnectorDraft(provider.key, (current) => ({
                    ...current,
                    credentials: { ...current.credentials, [key]: value },
                  }))
                }
              />
            </div>
          </div>
        ) : (
          <Surface className="inset-card">
            <p className="field-label">Local-safe calendar mode</p>
            <p className="helper-copy">
              `log_only` keeps booking calendar activity internal to localhost. No external calendar is contacted until Google Calendar mode is selected and configured.
            </p>
          </Surface>
        )}

        {provider.featureFlagDefinitions.length > 0 ? (
          <div className="form-shell">
            <p className="field-label">Operational flags</p>
            <div className="stack-tight">
              {provider.featureFlagDefinitions.map((definition) => (
                <label key={definition.key} className="checkbox-row">
                  <input
                    type="checkbox"
                    checked={draft.featureFlags[definition.key] ?? false}
                    onChange={(event) =>
                      updateConnectorDraft(provider.key, (current) => ({
                        ...current,
                        featureFlags: {
                          ...current.featureFlags,
                          [definition.key]: event.target.checked,
                        },
                      }))
                    }
                  />
                  <span>{definition.label}</span>
                </label>
              ))}
            </div>
          </div>
        ) : null}

        {renderConnectorFooter(provider, draft)}
      </Surface>
    );
  };

  const renderFlightConnectorCard = (provider: IntegrationProvider, draft: ConnectorDraft) => {
    const profileOptions = data.credentialProfiles.filter((profile) =>
      provider.compatibleProfileProviderKeys.includes(profile.providerKey),
    );
    const linkedProfile = profileOptions.find((profile) => profile.id === draft.credentialProfileId);
    const usingSharedProfile = Boolean(draft.credentialProfileId);
    const showAdvancedOverrides = advancedOverrideVisibility[provider.key] ?? false;
    const providerFamilyLabel = titleize(provider.providerKey || provider.name || provider.key);

    const setCredentialMode = (mode: "shared" | "connector") => {
      if (mode === "shared") {
        updateConnectorDraft(provider.key, (current) => ({
          ...current,
          credentialProfileId: current.credentialProfileId || profileOptions[0]?.id || "",
        }));
        return;
      }

      setAdvancedOverrideVisibility((current) => ({
        ...current,
        [provider.key]: false,
      }));
      updateConnectorDraft(provider.key, (current) => ({
        ...current,
        credentialProfileId: "",
      }));
    };

    return (
      <Surface key={provider.key} className="watch-card">
        {renderConnectorHeader(provider, draft)}

        <div className="summary-grid">
          <Surface className="field-card">
            <p className="field-label">Connection mode</p>
            <strong>{titleize(draft.environment)}</strong>
            <p className="helper-copy">
              Credentials can be configured for test or live environments, but current flight search remains deterministic and simulated until a real provider adapter is implemented.
            </p>
          </Surface>
          <Surface className="field-card">
            <p className="field-label">Credential source</p>
            <strong>
              {usingSharedProfile
                ? `Reusable ${providerFamilyLabel} profile: ${linkedProfile?.label ?? "selected"}`
                : `${providerFamilyLabel} credentials saved on this connector`}
            </strong>
            <p className="helper-copy">
              Reusable {providerFamilyLabel} profiles are the recommended source because they can also be reused by Booking.
            </p>
          </Surface>
          <Surface className="field-card">
            <p className="field-label">Advanced overrides</p>
            <strong>{usingSharedProfile ? (showAdvancedOverrides ? "Visible" : "Hidden") : "Not needed"}</strong>
            <p className="helper-copy">
              Keep overrides hidden unless this connector must differ from the shared profile.
            </p>
          </Surface>
        </div>

        <div className="form-shell">
          <p className="field-label">Connection controls</p>
          <div className="form-grid">
            <label className="field-stack">
              <span>Environment</span>
              <select
                className="text-input"
                value={draft.environment}
                onChange={(event) =>
                  updateConnectorDraft(provider.key, (current) => ({
                    ...current,
                    environment: event.target.value,
                  }))
                }
              >
                {environmentOptions.map((environment) => (
                  <option key={environment} value={environment}>
                    {environment}
                  </option>
                ))}
              </select>
            </label>
            <label className="checkbox-row field-span-full">
              <input
                type="checkbox"
                checked={draft.enabled}
                onChange={(event) =>
                  updateConnectorDraft(provider.key, (current) => ({
                    ...current,
                    enabled: event.target.checked,
                  }))
                }
              />
              <span>Flight connector enabled</span>
            </label>
          </div>
        </div>

        <div className="form-shell">
          <p className="field-label">Choose one credential source</p>
          <div className="stack-tight">
            <label className="checkbox-row">
              <input
                type="radio"
                name={`${provider.key}-credential-mode`}
                checked={usingSharedProfile}
                onChange={() => setCredentialMode("shared")}
                disabled={profileOptions.length === 0}
              />
              <span>Use reusable {providerFamilyLabel} profile (recommended)</span>
            </label>
            <label className="checkbox-row">
              <input
                type="radio"
                name={`${provider.key}-credential-mode`}
                checked={!usingSharedProfile}
                onChange={() => setCredentialMode("connector")}
              />
              <span>Use {providerFamilyLabel} credentials on this connector only</span>
            </label>
          </div>

          {usingSharedProfile ? (
            <div className="stack-tight">
              <label className="field-stack">
                <span>Reusable {providerFamilyLabel} profile</span>
                <select
                  className="text-input"
                  value={draft.credentialProfileId}
                  onChange={(event) =>
                    updateConnectorDraft(provider.key, (current) => ({
                      ...current,
                      credentialProfileId: event.target.value,
                    }))
                  }
                >
                  {profileOptions.map((profile) => (
                    <option key={profile.id} value={profile.id}>
                      {profile.label} ({titleize(profile.providerKey)})
                    </option>
                  ))}
                </select>
              </label>
              <div className="notice notice-value">
                This reusable {providerFamilyLabel} profile is used by Flights and can also be reused by Booking.
              </div>
              <div className="panel-actions">
                <Button
                  type="button"
                  variant="secondary"
                  onClick={() =>
                    setAdvancedOverrideVisibility((current) => ({
                      ...current,
                      [provider.key]: !showAdvancedOverrides,
                    }))
                  }
                >
                  {showAdvancedOverrides
                    ? "Hide advanced overrides"
                    : "Use advanced overrides for this connector only"}
                </Button>
              </div>
              {showAdvancedOverrides ? (
                <div className="notice notice-alert">
                  Overrides below take priority over the shared profile for this connector only.
                </div>
              ) : null}
            </div>
          ) : profileOptions.length > 0 ? (
            <div className="notice">
              This connector will ignore reusable {providerFamilyLabel} profiles and use only the credentials entered below.
            </div>
          ) : (
            <div className="notice">
              Create a reusable {providerFamilyLabel} profile above if you want to share these credentials across Flights and Booking.
            </div>
          )}
        </div>

        {(!usingSharedProfile || showAdvancedOverrides) ? (
          <>
            <CredentialGuide providerName={provider.name} guide={provider.guide} />
            <div className="form-shell">
              <p className="field-label">
                {usingSharedProfile ? "Advanced connector-only overrides" : "Connector-specific credentials"}
              </p>
              <div className="form-grid">
                <CredentialFieldList
                  fields={provider.credentialFields}
                  values={draft.credentials}
                  masked={provider.credentialsMasked}
                  idPrefix={provider.key}
                  onChange={(key, value) =>
                    updateConnectorDraft(provider.key, (current) => ({
                      ...current,
                      credentials: { ...current.credentials, [key]: value },
                    }))
                  }
                />
              </div>
            </div>
          </>
        ) : null}

        {provider.featureFlagDefinitions.length > 0 ? (
          <details className="multi-select">
            <summary className="multi-select-summary">Advanced flags</summary>
            <div className="multi-select-panel">
              {provider.featureFlagDefinitions.map((definition) => (
                <label key={definition.key} className="checkbox-row">
                  <input
                    type="checkbox"
                    checked={draft.featureFlags[definition.key] ?? false}
                    onChange={(event) =>
                      updateConnectorDraft(provider.key, (current) => ({
                        ...current,
                        featureFlags: {
                          ...current.featureFlags,
                          [definition.key]: event.target.checked,
                        },
                      }))
                    }
                  />
                  <span>{definition.label}</span>
                </label>
              ))}
            </div>
          </details>
        ) : null}

        {renderConnectorFooter(provider, draft)}
      </Surface>
    );
  };

  const renderConnectorCard = (provider: IntegrationProvider) => {
    const draft = connectorDrafts[provider.key] ?? buildConnectorDraft(provider);
    if (provider.category === "booking") {
      return renderBookingConnectorCard(provider, draft);
    }
    if (provider.category === "calendar") {
      return renderCalendarConnectorCard(provider, draft);
    }
    if (provider.category === "hotels") {
      return renderHotelConnectorCard(provider, draft);
    }
    if (provider.category === "messaging") {
      return renderMessagingConnectorCard(provider, draft);
    }
    if (provider.category === "flights" && provider.supportsSharedProfile) {
      return renderFlightConnectorCard(provider, draft);
    }
    const profileOptions = data.credentialProfiles.filter((profile) =>
      provider.compatibleProfileProviderKeys.includes(profile.providerKey),
    );
    return (
      <Surface key={provider.key} className="watch-card">
        {renderConnectorHeader(provider, draft)}

        <details className="multi-select">
          <summary className="multi-select-summary">Connection settings</summary>
          <div className="multi-select-panel">
            <label className="field-stack">
              <span>Environment</span>
              <select
                className="text-input"
                value={draft.environment}
                onChange={(event) =>
                  updateConnectorDraft(provider.key, (current) => ({
                    ...current,
                    environment: event.target.value,
                  }))
                }
              >
                {environmentOptions.map((environment) => (
                  <option key={environment} value={environment}>
                    {environment}
                  </option>
                ))}
              </select>
            </label>
            <label className="checkbox-row">
              <input
                type="checkbox"
                checked={draft.enabled}
                onChange={(event) =>
                  updateConnectorDraft(provider.key, (current) => ({
                    ...current,
                    enabled: event.target.checked,
                  }))
                }
              />
              <span>Integration enabled</span>
            </label>
            {provider.supportsSharedProfile ? (
              <label className="field-stack">
                <span>Shared credential profile</span>
                <select
                  className="text-input"
                  value={draft.credentialProfileId}
                  onChange={(event) =>
                    updateConnectorDraft(provider.key, (current) => ({
                      ...current,
                      credentialProfileId: event.target.value,
                    }))
                  }
                >
                  <option value="">No shared profile</option>
                  {profileOptions.map((profile) => (
                    <option key={profile.id} value={profile.id}>
                      {profile.label} ({titleize(profile.providerKey)})
                    </option>
                  ))}
                </select>
              </label>
            ) : null}
          </div>
        </details>

        <CredentialGuide providerName={provider.name} guide={provider.guide} />

        <details className="multi-select">
          <summary className="multi-select-summary">Credential overrides</summary>
          <div className="multi-select-panel">
            {provider.credentialFields.length > 0 ? (
              <CredentialFieldList
                fields={provider.credentialFields}
                values={draft.credentials}
                masked={provider.credentialsMasked}
                idPrefix={provider.key}
                onChange={(key, value) =>
                  updateConnectorDraft(provider.key, (current) => ({
                    ...current,
                    credentials: { ...current.credentials, [key]: value },
                  }))
                }
              />
            ) : (
              <p className="helper-copy">This connector currently relies on its linked profile or provider defaults.</p>
            )}
          </div>
        </details>

        {provider.featureFlagDefinitions.length > 0 ? (
          <details className="multi-select">
            <summary className="multi-select-summary">Advanced flags</summary>
            <div className="multi-select-panel">
              {provider.featureFlagDefinitions.map((definition) => (
                <label key={definition.key} className="checkbox-row">
                  <input
                    type="checkbox"
                    checked={draft.featureFlags[definition.key] ?? false}
                    onChange={(event) =>
                      updateConnectorDraft(provider.key, (current) => ({
                        ...current,
                        featureFlags: {
                          ...current.featureFlags,
                          [definition.key]: event.target.checked,
                        },
                      }))
                    }
                  />
                  <span>{definition.label}</span>
                </label>
              ))}
            </div>
          </details>
        ) : null}

        {renderConnectorFooter(provider, draft)}
      </Surface>
    );
  };

  if (!categoryId) {
    return (
      <div className="stack">
        <SectionHeading
          eyebrow="Admin"
          title="Integration pages"
          description="Open a compact page for each integration domain. Shared credential profiles keep reusable APIs linked across compatible connectors."
        />
        {!liveMode ? (
          <div className="notice">
            Demo mode is still available, but these pages save persisted backend integration settings for localhost operation.
          </div>
        ) : (
          <div className="notice notice-value">
            Backend API mode is active. Integration changes are persisted and survive restart. This does not mean a provider connector performs live search or booking.
          </div>
        )}
        {error ? <div className="notice notice-alert">{getErrorMessage(error, "Unable to load admin integrations.")}</div> : null}
        {batchNotice ? <div className={`notice ${batchNotice.tone === "alert" ? "notice-alert" : "notice-value"}`}>{batchNotice.message}</div> : null}
        <div className="summary-grid">
          {categories.map((category) => (
            <Surface key={category.id} className="list-card">
              <h3>{category.title}</h3>
              <p className="item-copy">{category.description}</p>
              <Button to={`/admin/integrations/${category.id}`}>Open page</Button>
            </Surface>
          ))}
        </div>
      </div>
    );
  }

  if (!activeCategory) {
    return (
      <div className="stack">
        <EmptyState
          title="Unknown integration page"
          copy="This integration page does not exist yet. Return to the admin integrations landing page and choose one of the configured categories."
          action={<Button to="/admin/integrations">Back to integrations</Button>}
        />
      </div>
    );
  }

  return (
    <div className="stack">
      <SectionHeading
        eyebrow="Admin"
        title={activeCategory.title}
        description={activeCategory.description}
        action={
          activeCategory.id !== "runtime" ? (
            <Button
              variant="secondary"
              type="button"
              onClick={() => testAllMutation.mutate(testableProviders)}
              disabled={testAllMutation.isPending || testableProviders.length === 0}
            >
              {testAllMutation.isPending ? "Testing..." : "Test all on this page"}
            </Button>
          ) : undefined
        }
      />
      {renderCategoryNav()}
      {batchNotice ? <div className={`notice ${batchNotice.tone === "alert" ? "notice-alert" : "notice-value"}`}>{batchNotice.message}</div> : null}

      {activeCategory.id === "runtime" ? (
        renderRuntimePage()
      ) : (
        <>
          {renderSharedProfiles()}
          {categoryProviders.length === 0 ? (
            <EmptyState
              title="No connectors in this category"
              copy="This category page does not have any connectors yet."
            />
          ) : (
            <div className="stack">
              {categoryProviders.map(renderConnectorCard)}
            </div>
          )}
        </>
      )}
    </div>
  );
}
