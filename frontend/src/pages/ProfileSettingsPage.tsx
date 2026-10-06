import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useMemo, useState } from "react";

import { ApiError } from "@/api/client";
import { queryKeys, travelWatchApi } from "@/api/travelWatchApi";
import { PaymentMethodForm, TemplateForm, TravelerForm } from "@/components/profile/ProfileForms";
import { Badge, Button, PillRow, SectionHeading, Surface } from "@/components/ui/primitives";

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

function formatTravelerMeta({
  relationship,
  nationality,
  passportExpiry,
  loyaltyProgramCode,
}: {
  relationship: string;
  nationality: string;
  passportExpiry: string;
  loyaltyProgramCode: string;
}) {
  const parts = [
    relationship ? relationship.replace(/_/g, " ") : "",
    nationality ? `${nationality} passport profile` : "",
    passportExpiry ? `passport exp. ${passportExpiry}` : "",
    loyaltyProgramCode ? `${loyaltyProgramCode} preferred` : "",
  ].filter(Boolean);

  return parts.join(" · ");
}

export function ProfileSettingsPage() {
  const queryClient = useQueryClient();
  const [editingTravelerId, setEditingTravelerId] = useState<string | "new" | null>(null);
  const [editingPaymentId, setEditingPaymentId] = useState<string | "new" | null>(null);
  const [editingTemplateId, setEditingTemplateId] = useState<string | "new" | null>(null);

  const { data } = useQuery({
    queryKey: queryKeys.profile,
    queryFn: travelWatchApi.getProfileWorkspace,
  });
  const isAdmin = data?.currentUser?.role === "admin";
  const { data: integrationData } = useQuery({
    queryKey: queryKeys.integrations,
    queryFn: travelWatchApi.getIntegrations,
    enabled: isAdmin,
  });

  const refreshWorkspace = async () => {
    await Promise.all([
      queryClient.invalidateQueries({ queryKey: queryKeys.profile }),
      queryClient.invalidateQueries({ queryKey: ["watch-draft"] }),
    ]);
  };

  const saveTravelerMutation = useMutation({
    mutationFn: travelWatchApi.saveTraveler,
    onSuccess: async () => {
      setEditingTravelerId(null);
      await refreshWorkspace();
    },
  });

  const deleteTravelerMutation = useMutation({
    mutationFn: travelWatchApi.deleteTraveler,
    onSuccess: refreshWorkspace,
  });

  const savePaymentMethodMutation = useMutation({
    mutationFn: travelWatchApi.savePaymentMethod,
    onSuccess: async () => {
      setEditingPaymentId(null);
      await refreshWorkspace();
    },
  });

  const deletePaymentMethodMutation = useMutation({
    mutationFn: travelWatchApi.deletePaymentMethod,
    onSuccess: refreshWorkspace,
  });

  const saveTemplateMutation = useMutation({
    mutationFn: travelWatchApi.saveTemplate,
    onSuccess: async () => {
      setEditingTemplateId(null);
      await refreshWorkspace();
    },
  });

  const deleteTemplateMutation = useMutation({
    mutationFn: travelWatchApi.deleteTemplate,
    onSuccess: refreshWorkspace,
  });

  const editingTraveler = useMemo(
    () =>
      editingTravelerId && editingTravelerId !== "new"
        ? data?.travelers.find((traveler) => traveler.id === editingTravelerId)
        : undefined,
    [data?.travelers, editingTravelerId],
  );

  const editingPaymentMethod = useMemo(
    () =>
      editingPaymentId && editingPaymentId !== "new"
        ? data?.paymentMethods.find((paymentMethod) => paymentMethod.id === editingPaymentId)
        : undefined,
    [data?.paymentMethods, editingPaymentId],
  );

  const editingTemplate = useMemo(
    () =>
      editingTemplateId && editingTemplateId !== "new"
        ? data?.templates.find((template) => template.id === editingTemplateId)
        : undefined,
    [data?.templates, editingTemplateId],
  );
  const accountTraveler = useMemo(
    () => data?.travelers.find((traveler) => traveler.relationship === "self") ?? data?.travelers[0],
    [data?.travelers],
  );

  if (!data) {
    return (
      <div className="stack">
        <Surface>Loading profile settings...</Surface>
      </div>
    );
  }

  const calendarIntegration = integrationData?.providers.find((provider) => provider.key === "calendar");

  return (
    <div className="stack">
      <SectionHeading
        eyebrow="Household"
        title="Profile and settings"
        description="Travelers, defaults, payment methods, and starter templates live here so every new watch can stay lightweight."
        action={<Button to={data.currentUser?.totpEnabled ? "/onboarding" : "/setup/2fa"}>{data.currentUser?.totpEnabled ? "Review onboarding" : "Finish 2FA setup"}</Button>}
      />

      <Surface>
        <SectionHeading
          eyebrow="Rewards"
          title="TRAMP-Stamps"
          description="One stamp is awarded for each successful live booking. Simulated bookings do not earn a stamp."
        />
        {(data.stampHistory ?? []).length === 0 ? (
          <p className="item-copy">No stamps yet. A live booking adds one stamp to this list.</p>
        ) : (
          <div className="stack-tight">
            {(data.stampHistory ?? []).map((stamp) => (
              <div key={stamp.id} className="summary-row">
                <div>
                  <p className="item-title">{stamp.route}</p>
                  <p className="item-copy">
                    {stamp.provider} · {stamp.awardedAt ? new Date(stamp.awardedAt).toLocaleString() : "Awarded"}
                  </p>
                </div>
                <Badge tone="luxury">{stamp.amount} stamp</Badge>
              </div>
            ))}
          </div>
        )}
      </Surface>

      <Surface>
        <SectionHeading
          eyebrow="Account"
          title="Session and security"
          description="Account state, TOTP-backed session access, and the rest of the profile now come from the live backend profile workspace."
          action={
            data.currentUser ? (
              <Badge tone="value">Live backend session</Badge>
            ) : (
              <Badge tone="alert">No active session</Badge>
            )
          }
        />

        {data.currentUser ? (
          <>
            <div className="summary-grid">
              <Surface className="field-card">
                <p className="field-label">Email</p>
                <strong>{data.currentUser.email}</strong>
              </Surface>
              <Surface className="field-card">
                <p className="field-label">Role</p>
                <strong>{data.currentUser.role}</strong>
              </Surface>
              <Surface className="field-card">
                <p className="field-label">Default notify channel</p>
                <strong>{data.currentUser.defaultNotifyChannel}</strong>
              </Surface>
              <Surface className="field-card">
                <p className="field-label">Onboarding state</p>
                <strong>{data.currentUser.onboardingCompleted ? "Complete" : "In progress"}</strong>
              </Surface>
              <Surface className="field-card">
                <p className="field-label">2FA</p>
                <strong>{data.currentUser.totpEnabled ? "Enabled" : "Needs setup"}</strong>
              </Surface>
              <Surface className="field-card">
                <p className="field-label">Calendar sync</p>
                <strong>
                  {isAdmin
                    ? calendarIntegration
                      ? `${calendarIntegration.environment} / ${calendarIntegration.enabled ? "enabled" : "disabled"}`
                      : "Unavailable"
                    : "Managed by an admin"}
                </strong>
                {isAdmin && calendarIntegration?.validationHelp ? (
                  <p className="item-copy">{calendarIntegration.validationHelp}</p>
                ) : null}
              </Surface>
            </div>

            <Surface className="inset-card">
              <SectionHeading
                eyebrow="Account loyalty"
                title="Favorite earning profile"
                description="Multiple loyalty programs now live with your account traveler, and one favorite controls the default earning preference."
                action={
                  <Button variant="ghost" to="/onboarding/account">
                    Review onboarding account step
                  </Button>
                }
              />
              {accountTraveler ? (
                <div className="stack-tight">
                  <p className="item-copy">
                    Managing loyalty for <strong>{accountTraveler.displayName}</strong>.
                  </p>
                  {accountTraveler.loyaltyPrograms.length > 0 ? (
                    <ul className="info-list">
                      {accountTraveler.loyaltyPrograms.map((program) => (
                        <li key={`${program.programCode}-${program.accountNumber}`}>
                          {program.programCode} {program.accountNumber}
                          {program.statusTier ? ` · ${program.statusTier}` : ""}
                          {program.isFavorite ? " · favorite" : ""}
                        </li>
                      ))}
                    </ul>
                  ) : (
                    <p className="item-copy">
                      No loyalty programs saved yet. Add them in the onboarding account step or traveler editor.
                    </p>
                  )}
                </div>
              ) : (
                <p className="item-copy">
                  Add your own traveler profile first, then attach multiple airline loyalty programs to it.
                </p>
              )}
            </Surface>
          </>
        ) : (
          <div className="notice notice-alert">
            <p className="item-title">No backend session yet</p>
            <p className="item-copy">
              You can still shape travelers, defaults, payment methods, and templates locally, but sign-up and TOTP enrollment live on the onboarding screen.
            </p>
          </div>
        )}
      </Surface>

      <Surface>
        <SectionHeading
          eyebrow="Workspace"
          title="Household booking readiness"
          description="This is the single-account household control center: who can travel, which presets exist, and what still blocks fast booking."
          action={<Badge tone={data.householdSummary.setupWarnings.length === 0 ? "value" : "alert"}>{data.householdSummary.readinessLabel}</Badge>}
        />
        <div className="summary-grid">
          <Surface className="field-card">
            <p className="field-label">Travelers</p>
            <strong>{data.householdSummary.travelerCount}</strong>
          </Surface>
          <Surface className="field-card">
            <p className="field-label">Saved groups</p>
            <strong>{data.householdSummary.travelerGroupCount}</strong>
          </Surface>
          <Surface className="field-card">
            <p className="field-label">Payment methods</p>
            <strong>{data.householdSummary.paymentMethodCount}</strong>
          </Surface>
          <Surface className="field-card">
            <p className="field-label">Passport gaps</p>
            <strong>{data.householdSummary.passportGapCount}</strong>
          </Surface>
          <Surface className="field-card">
            <p className="field-label">2FA</p>
            <strong>{data.householdSummary.totpEnabled ? "Ready" : "Missing"}</strong>
          </Surface>
          <Surface className="field-card">
            <p className="field-label">Trip templates</p>
            <strong>{data.householdSummary.templateCount}</strong>
          </Surface>
        </div>
        {data.householdSummary.setupWarnings.length > 0 ? (
          <div className="notice notice-alert">
            <p className="item-title">Setup warnings</p>
            <ul className="info-list">
              {data.householdSummary.setupWarnings.map((warning) => (
                <li key={warning}>{warning}</li>
              ))}
            </ul>
          </div>
        ) : (
          <div className="notice notice-value">Your saved household is ready to support fast deal approval.</div>
        )}
      </Surface>

      <Surface>
        <SectionHeading
          eyebrow="Travelers"
          title="Household profiles"
          description="Legal, loyalty, and comfort details live here and feed future watch drafts."
          action={
            <Button type="button" variant="secondary" onClick={() => setEditingTravelerId("new")}>
              Add traveler
            </Button>
          }
        />

        <div className="stack-tight">
          {data.travelers.map((traveler) => (
            <Surface key={traveler.id} className="list-card inset-card">
              <div className="watch-topline">
                <div>
                  <div className="badge-row">
                    <h3>{traveler.displayName}</h3>
                    <Badge tone="value">Traveler</Badge>
                  </div>
                  <p className="item-copy">
                    {formatTravelerMeta({
                      relationship: traveler.relationship,
                      nationality: traveler.nationality,
                      passportExpiry: traveler.passportExpiry,
                      loyaltyProgramCode: traveler.loyaltyProgramCode,
                    })}
                  </p>
                </div>
                <div className="button-row">
                  <Button
                    type="button"
                    variant="secondary"
                    onClick={() => setEditingTravelerId(traveler.id)}
                  >
                    Edit
                  </Button>
                  <Button
                    type="button"
                    variant="ghost"
                    onClick={() => deleteTravelerMutation.mutate(traveler.id)}
                    disabled={deleteTravelerMutation.isPending}
                  >
                    Remove
                  </Button>
                </div>
              </div>
              <ul className="info-list">
                {traveler.knownTravelerNumber ? <li>Known traveler number saved.</li> : null}
                {traveler.redressNumber ? <li>Redress number saved.</li> : null}
                {traveler.accessibilityNeeds ? <li>{traveler.accessibilityNeeds}</li> : null}
                {traveler.preferredEarningForAlliance ? <li>Preferred for same-alliance earning.</li> : null}
              </ul>
            </Surface>
          ))}

          {data.travelers.length === 0 ? (
            <div className="muted-card">
              <p className="item-title">No travelers yet</p>
              <p className="item-copy">Start with one traveler so the watch editor can reuse real trip context.</p>
            </div>
          ) : null}
        </div>

        {editingTravelerId ? (
          <TravelerForm
            initialValue={editingTraveler}
            submitLabel={editingTraveler ? "Update traveler" : "Save traveler"}
            onSubmit={(value) => saveTravelerMutation.mutate(value)}
            onCancel={() => setEditingTravelerId(null)}
            disabled={saveTravelerMutation.isPending}
          />
        ) : null}

        {saveTravelerMutation.isError || deleteTravelerMutation.isError ? (
          <div className="notice notice-alert">
            {getErrorMessage(
              saveTravelerMutation.error ?? deleteTravelerMutation.error,
              "Unable to update traveler settings.",
            )}
          </div>
        ) : null}
      </Surface>

      <Surface>
        <SectionHeading
          eyebrow="Alerts"
          title="Notification delivery"
          description="Delivery method and user enablement now live on a dedicated page so users can link their own destinations without mixing it into travel presets."
          action={<Button variant="secondary" to="/profile/notifications">Open notification page</Button>}
        />
        <div className="summary-grid">
          <Surface className="field-card">
            <p className="field-label">Account channel</p>
            <strong>{data.currentUser?.defaultNotifyChannel || "email"}</strong>
          </Surface>
          <Surface className="field-card">
            <p className="field-label">New watch default</p>
            <strong>{data.preferences.defaultNotifyChannel || "inherit"}</strong>
          </Surface>
          <Surface className="field-card">
            <p className="field-label">Account email</p>
            <strong>{data.currentUser?.email || "Not signed in"}</strong>
          </Surface>
          <Surface className="field-card">
            <p className="field-label">Telegram destination</p>
            <strong>{data.currentUser?.telegramChatId || "Not linked"}</strong>
          </Surface>
        </div>
      </Surface>

      <Surface>
        <SectionHeading
          eyebrow="Defaults"
          title="Traveler groups and watch presets"
          description="Preset defaults now live on their own page so you can set them thoughtfully without editing them every time you visit your profile."
          action={<Button variant="secondary" to="/profile/presets">Open presets page</Button>}
        />
        <p className="field-label">Available traveler groups</p>
        <PillRow items={data.travelerGroups} selected={data.travelerGroups[0]} />
        <div className="summary-grid">
          <Surface className="field-card">
            <p className="field-label">Home airports</p>
            <strong>{data.preferences.homeAirports.join(", ") || "Not set"}</strong>
          </Surface>
          <Surface className="field-card">
            <p className="field-label">Quiet hours</p>
            <strong>
              {data.preferences.quietHoursStart && data.preferences.quietHoursEnd
                ? `${data.preferences.quietHoursStart} - ${data.preferences.quietHoursEnd} ${data.preferences.quietHoursTimezone || "UTC"}`
                : "Not set"}
            </strong>
          </Surface>
          <Surface className="field-card">
            <p className="field-label">Cabin default</p>
            <strong>{data.preferences.defaultCabin || "Not set"}</strong>
          </Surface>
          <Surface className="field-card">
            <p className="field-label">Preference scope</p>
            <strong>
              {data.preferences.preferredAirlines.length === 0 && data.preferences.preferredAlliances.length === 0
                ? "All airlines included"
                : "Soft airline preferences"}
            </strong>
          </Surface>
        </div>
        <p className="helper-copy">
          Preferred airlines and alliances do not exclude other carriers by default. Use avoided airlines only for true exclusions.
        </p>
      </Surface>

      <Surface>
        <SectionHeading
          eyebrow="Payments"
          title="Stored methods"
          description="Masked payment summaries live here so onboarding and booking approval stay out of the same moment."
          action={
            <Button type="button" variant="secondary" onClick={() => setEditingPaymentId("new")}>
              Add method
            </Button>
          }
        />

        <div className="stack-tight">
          {data.paymentMethods.map((paymentMethod) => (
            <Surface key={paymentMethod.id} className="list-card inset-card">
              <div className="watch-topline">
                <div>
                  <div className="badge-row">
                    <h3>{paymentMethod.label}</h3>
                    {paymentMethod.providerToken ? <Badge tone="luxury">Tokenized</Badge> : null}
                  </div>
                  <p className="item-copy">
                    {paymentMethod.brand || "Card"} ending {paymentMethod.last4 || "----"} · billing country {paymentMethod.billingCountry || "unset"}
                  </p>
                </div>
                <div className="button-row">
                  <Button
                    type="button"
                    variant="secondary"
                    onClick={() => setEditingPaymentId(paymentMethod.id)}
                  >
                    Edit
                  </Button>
                  <Button
                    type="button"
                    variant="ghost"
                    onClick={() => deletePaymentMethodMutation.mutate(paymentMethod.id)}
                    disabled={deletePaymentMethodMutation.isPending}
                  >
                    Remove
                  </Button>
                </div>
              </div>
            </Surface>
          ))}

          {data.paymentMethods.length === 0 ? (
            <div className="muted-card">
              <p className="item-title">No payment methods yet</p>
              <p className="item-copy">You can keep this empty until one-tap approval matters.</p>
            </div>
          ) : null}
        </div>

        {editingPaymentId ? (
          <PaymentMethodForm
            initialValue={editingPaymentMethod}
            submitLabel={editingPaymentMethod ? "Update method" : "Save method"}
            onSubmit={(value) => savePaymentMethodMutation.mutate(value)}
            onCancel={() => setEditingPaymentId(null)}
            disabled={savePaymentMethodMutation.isPending}
          />
        ) : null}

        {savePaymentMethodMutation.isError || deletePaymentMethodMutation.isError ? (
          <div className="notice notice-alert">
            {getErrorMessage(
              savePaymentMethodMutation.error ?? deletePaymentMethodMutation.error,
              "Unable to update payment methods.",
            )}
          </div>
        ) : null}
      </Surface>

      <Surface>
        <SectionHeading
          eyebrow="Templates"
          title="Reusable trip starters"
          description="These templates now flow into the existing watch editor scaffold so new watches start with real defaults."
          action={
            <Button type="button" variant="secondary" onClick={() => setEditingTemplateId("new")}>
              Add template
            </Button>
          }
        />

        <div className="stack-tight">
          {data.templates.map((template) => (
            <Surface key={template.id} className="list-card inset-card">
              <div className="watch-topline">
                <div>
                  <div className="badge-row">
                    <h3>{template.name}</h3>
                    <Badge tone="luxury">{template.travelerGroup}</Badge>
                  </div>
                  <p className="item-copy">
                    {template.origin || "Origins unset"}
                    {" -> "}
                    {template.destination || "Destination unset"}
                  </p>
                  <p className="item-copy">
                    {template.flightBudgetMax || "Flight budget unset"} · {template.hotelBudgetPerNightMax || "Hotel budget unset"}
                  </p>
                </div>
                <div className="button-row">
                  <Button
                    type="button"
                    variant="secondary"
                    onClick={() => setEditingTemplateId(template.id)}
                  >
                    Edit
                  </Button>
                  <Button
                    type="button"
                    variant="ghost"
                    onClick={() => deleteTemplateMutation.mutate(template.id)}
                    disabled={deleteTemplateMutation.isPending}
                  >
                    Remove
                  </Button>
                </div>
              </div>
              {template.notes ? <p className="item-copy">{template.notes}</p> : null}
            </Surface>
          ))}

          {data.templates.length === 0 ? (
            <div className="muted-card">
              <p className="item-title">No templates yet</p>
              <p className="item-copy">Save one recurring trip and the watch editor will stop feeling blank.</p>
            </div>
          ) : null}
        </div>

        {editingTemplateId ? (
          <TemplateForm
            initialValue={editingTemplate}
            travelerGroups={data.travelerGroups}
            submitLabel={editingTemplate ? "Update template" : "Save template"}
            onSubmit={(value) => saveTemplateMutation.mutate(value)}
            onCancel={() => setEditingTemplateId(null)}
            disabled={saveTemplateMutation.isPending}
          />
        ) : null}

        {saveTemplateMutation.isError || deleteTemplateMutation.isError ? (
          <div className="notice notice-alert">
            {getErrorMessage(
              saveTemplateMutation.error ?? deleteTemplateMutation.error,
              "Unable to update trip templates.",
            )}
          </div>
        ) : null}
      </Surface>
    </div>
  );
}
