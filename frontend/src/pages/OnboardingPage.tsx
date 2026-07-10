import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useMemo, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";

import { ApiError } from "@/api/client";
import type { TravelerProfile } from "@/api/types";
import { queryKeys, travelWatchApi } from "@/api/travelWatchApi";
import {
  LoyaltyProgramsEditor,
  PaymentMethodForm,
  PreferencesForm,
  TemplateForm,
  TravelerForm,
} from "@/components/profile/ProfileForms";
import { Badge, Button, EmptyState, SectionHeading, Surface } from "@/components/ui/primitives";

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

function hasPreferencesConfigured(homeAirports: string[], notifyChannel: string) {
  return homeAirports.length > 0 && Boolean(notifyChannel);
}

function summarizeTraveler(traveler: TravelerProfile) {
  return [
    traveler.relationship ? traveler.relationship.replace(/_/g, " ") : "",
    traveler.nationality ? `Nationality ${traveler.nationality}` : "",
    traveler.passportExpiry ? `Passport exp. ${traveler.passportExpiry}` : "",
  ]
    .filter(Boolean)
    .join(" · ");
}

export function OnboardingPage() {
  const queryClient = useQueryClient();
  const navigate = useNavigate();
  const { stepId } = useParams<{ stepId?: string }>();

  const { data } = useQuery({
    queryKey: queryKeys.profile,
    queryFn: travelWatchApi.getProfileWorkspace,
  });

  const refreshWorkspace = async () => {
    await Promise.all([
      queryClient.invalidateQueries({ queryKey: queryKeys.profile }),
      queryClient.invalidateQueries({ queryKey: ["watch-draft"] }),
    ]);
  };

  const saveTravelerMutation = useMutation({
    mutationFn: travelWatchApi.saveTraveler,
    onSuccess: async (traveler) => {
      setSelectedTravelerId(traveler?.id ?? "new");
      await refreshWorkspace();
    },
  });

  const deleteTravelerMutation = useMutation({
    mutationFn: travelWatchApi.deleteTraveler,
    onSuccess: async () => {
      setSelectedTravelerId("new");
      await refreshWorkspace();
    },
  });

  const savePreferencesMutation = useMutation({
    mutationFn: travelWatchApi.savePreferences,
    onSuccess: refreshWorkspace,
  });

  const savePaymentMethodMutation = useMutation({
    mutationFn: travelWatchApi.savePaymentMethod,
    onSuccess: refreshWorkspace,
  });

  const saveTemplateMutation = useMutation({
    mutationFn: travelWatchApi.saveTemplate,
    onSuccess: refreshWorkspace,
  });

  const completeOnboardingMutation = useMutation({
    mutationFn: travelWatchApi.completeOnboarding,
    onSuccess: async () => {
      await refreshWorkspace();
      navigate("/watches");
    },
  });

  const steps = useMemo(
    () => [
      { id: "account", title: "Account", shortTitle: "Account" },
      { id: "traveler", title: "Travelers", shortTitle: "Family" },
      { id: "preferences", title: "Defaults", shortTitle: "Defaults" },
      { id: "payment", title: "Payment", shortTitle: "Payment" },
      { id: "template", title: "Template", shortTitle: "Template" },
      { id: "summary", title: "Review", shortTitle: "Review" },
    ],
    [],
  );

  const activeStepId = steps.some((step) => step.id === stepId) ? stepId ?? "account" : "account";

  useEffect(() => {
    if (!stepId || !steps.some((step) => step.id === stepId)) {
      navigate("/onboarding/account", { replace: true });
    }
  }, [navigate, stepId, steps]);

  const stepStatus = useMemo(() => {
    if (!data) {
      return [];
    }

    const preferencesReady = hasPreferencesConfigured(
      data.preferences.homeAirports,
      data.preferences.defaultNotifyChannel,
    );

    return [
      {
        id: "account",
        title: "Account",
        detail: data.currentUser
          ? `Signed in as ${data.currentUser.email}.`
          : "Use the seeded admin login or your own credentials to unlock setup.",
        complete: Boolean(data.currentUser?.totpEnabled),
      },
      {
        id: "traveler",
        title: "Add your first traveler",
        detail: data.travelers.length
          ? `${data.travelers.length} traveler record${data.travelers.length > 1 ? "s" : ""} ready.`
          : "Legal name, date of birth, nationality, and comfort defaults first.",
        complete: data.travelers.length > 0,
      },
      {
        id: "preferences",
        title: "Set defaults",
        detail: preferencesReady
          ? "Watch defaults are ready to prefill the editor."
          : "Home airports, notify channel, and luxury dial anchor the experience.",
        complete: preferencesReady,
      },
      {
        id: "payment",
        title: "Add a payment method",
        detail: data.paymentMethods.length
          ? `${data.paymentMethods.length} payment method${data.paymentMethods.length > 1 ? "s" : ""} on file.`
          : "Keep booking approval one tap away without turning onboarding into checkout.",
        complete: data.paymentMethods.length > 0,
      },
      {
        id: "template",
        title: "Save a reusable template",
        detail: data.templates.length
          ? `${data.templates.length} travel template${data.templates.length > 1 ? "s" : ""} ready for reuse.`
          : "A starter trip template turns the first watch into a quick handoff.",
        complete: data.templates.length > 0,
      },
      {
        id: "summary",
        title: "Final review",
        detail: data.travelers.length
          ? "Confirm every traveler before closing onboarding."
          : "Traveler review unlocks after at least one family member is saved.",
        complete: false,
      },
    ];
  }, [data]);

  const completedSteps = stepStatus.filter((step) => step.complete).length;
  const progressLabel = `${completedSteps} of ${stepStatus.length} steps complete`;
  const canEditProfileSections = Boolean(data?.currentUser);
  const primaryTraveler =
    data?.travelers.find((traveler) => traveler.relationship === "self") ?? data?.travelers[0];
  const accountTraveler = primaryTraveler;
  const defaultPaymentMethod = data?.paymentMethods[0];
  const starterTemplate = data?.templates[0];
  const [selectedTravelerId, setSelectedTravelerId] = useState<string | "new">(
    primaryTraveler?.id ?? "new",
  );
  const activeStepIndex = steps.findIndex((step) => step.id === activeStepId);
  const previousStep = activeStepIndex > 0 ? steps[activeStepIndex - 1] : null;
  const nextStep = activeStepIndex < steps.length - 1 ? steps[activeStepIndex + 1] : null;
  const [loyaltyDraft, setLoyaltyDraft] = useState(accountTraveler?.loyaltyPrograms ?? []);
  const [travelerConfirmations, setTravelerConfirmations] = useState<Record<string, boolean>>({});

  useEffect(() => {
    setLoyaltyDraft(accountTraveler?.loyaltyPrograms ?? []);
  }, [accountTraveler]);

  useEffect(() => {
    if (!data?.travelers.length) {
      setSelectedTravelerId("new");
      return;
    }
    const stillExists = data.travelers.some((traveler) => traveler.id === selectedTravelerId);
    if (selectedTravelerId !== "new" && stillExists) {
      return;
    }
    setSelectedTravelerId(primaryTraveler?.id ?? data.travelers[0]?.id ?? "new");
  }, [data?.travelers, primaryTraveler?.id, selectedTravelerId]);

  useEffect(() => {
    if (!data?.travelers) {
      return;
    }
    setTravelerConfirmations((current) => {
      const next: Record<string, boolean> = {};
      for (const traveler of data.travelers) {
        next[traveler.id] = current[traveler.id] ?? false;
      }
      return next;
    });
  }, [data?.travelers]);

  const saveLoyaltyMutation = useMutation({
    mutationFn: async () => {
      if (!accountTraveler) {
        throw new Error("Add your traveler profile first before saving loyalty programs.");
      }
      await travelWatchApi.saveTraveler({
        ...accountTraveler,
        loyaltyPrograms: loyaltyDraft,
      });
    },
    onSuccess: refreshWorkspace,
  });

  const activeStepStatus = stepStatus.find((step) => step.id === activeStepId);

  if (!data) {
    return (
      <div className="stack">
        <Surface>Loading onboarding flow...</Surface>
      </div>
    );
  }
  const workspace = data;
  const travelersReady = workspace.travelers.length > 0;
  const preferencesReady = hasPreferencesConfigured(
    workspace.preferences.homeAirports,
    workspace.preferences.defaultNotifyChannel,
  );
  const selectedTraveler =
    selectedTravelerId === "new"
      ? undefined
      : workspace.travelers.find((traveler) => traveler.id === selectedTravelerId);
  const travelerReviewConfirmed =
    workspace.travelers.length > 0 &&
    workspace.travelers.every((traveler) => travelerConfirmations[traveler.id]);

  const stepMeta = stepStatus.map((step, index) => ({
    ...step,
    shortTitle: steps[index]?.shortTitle ?? step.title,
    href: `/onboarding/${step.id}`,
    active: step.id === activeStepId,
  }));

  function renderStepContent() {
    switch (activeStepId) {
      case "account":
        return (
          <Surface className="setup-stage">
            <SectionHeading
              eyebrow="Step 1"
              title="Account and loyalty setup"
              description="This is now a dedicated onboarding page for authentication, 2FA, and your saved earning programs."
              action={
                <Badge tone={activeStepStatus?.complete ? "value" : "luxury"}>
                  {activeStepStatus?.complete ? "Protected" : "Needs 2FA"}
                </Badge>
              }
            />

            {workspace.currentUser ? (
              <div className="stack">
                <div className={workspace.currentUser.totpEnabled ? "notice notice-value" : "notice notice-alert"}>
                  <strong>{workspace.currentUser.email}</strong>
                  <p className="item-copy">
                    {workspace.currentUser.role} account active.
                    {workspace.currentUser.totpEnabled
                      ? " TOTP is enabled for approval-sensitive actions."
                      : " TOTP still needs to be enabled before this step is considered complete."}
                  </p>
                </div>

                {workspace.currentUser.totpEnabled ? null : (
                  <Surface className="inset-card">
                    <SectionHeading
                      eyebrow="Security"
                      title="Finish the QR-based 2FA flow"
                      description="The authenticator setup now lives on smooth dedicated pages so you only do it once."
                    />
                    <div className="button-row">
                      <Button to="/setup/2fa">Continue to 2FA setup</Button>
                      <Button variant="ghost" to="/login">
                        Open login
                      </Button>
                    </div>
                  </Surface>
                )}

                <Surface className="inset-card">
                  <SectionHeading
                    eyebrow="Loyalty"
                    title="Multiple loyalty programs"
                    description="Attach all of your airline programs here and mark one favorite so TRAMP knows your default earning preference."
                  />
                  {accountTraveler ? (
                    <div className="stack-tight">
                      <p className="item-copy">
                        Programs are linked to <strong>{accountTraveler.displayName}</strong>.
                      </p>
                      <LoyaltyProgramsEditor
                        value={loyaltyDraft}
                        onChange={setLoyaltyDraft}
                        disabled={saveLoyaltyMutation.isPending}
                      />
                      <div className="panel-actions">
                        <Button
                          type="button"
                          onClick={() => saveLoyaltyMutation.mutate()}
                          disabled={saveLoyaltyMutation.isPending}
                        >
                          Save loyalty programs
                        </Button>
                        <Button
                          type="button"
                          variant="ghost"
                          onClick={() => setLoyaltyDraft(accountTraveler.loyaltyPrograms)}
                          disabled={saveLoyaltyMutation.isPending}
                        >
                          Reset
                        </Button>
                      </div>
                    </div>
                  ) : (
                    <div className="muted-card">
                      <p className="item-title">Add your traveler profile first</p>
                      <p className="item-copy">
                        We need your primary traveler record before we can attach loyalty programs.
                      </p>
                      <div className="panel-actions">
                        <Button to="/onboarding/traveler">Go to traveler step</Button>
                      </div>
                    </div>
                  )}
                </Surface>

                {saveLoyaltyMutation.isError ? (
                  <div className="notice notice-alert">
                    {getErrorMessage(saveLoyaltyMutation.error, "Unable to save loyalty programs.")}
                  </div>
                ) : null}
              </div>
            ) : (
              <div className="muted-card">
                <p className="item-title">Authentication required</p>
                <p className="item-copy">
                  Sign in before finishing onboarding, traveler setup, and authenticator enrollment.
                </p>
                <div className="panel-actions">
                  <Button to="/login">Open login</Button>
                </div>
              </div>
            )}
          </Surface>
        );

      case "traveler":
        return (
          <Surface className="setup-stage">
            <SectionHeading
              eyebrow="Step 2"
              title="Family traveler workspace"
              description="Add, review, and switch between family members from one place so larger households stay manageable."
              action={<Badge tone={travelersReady ? "value" : "muted"}>{workspace.travelers.length} traveler{workspace.travelers.length === 1 ? "" : "s"}</Badge>}
            />
            {canEditProfileSections ? (
              <div className="traveler-workspace">
                <Surface className="inset-card traveler-rail">
                  <div className="toolbar-row">
                    <div>
                      <p className="field-label">Family members</p>
                      <p className="helper-copy">
                        Keep each traveler separate so it is easy to spot mistakes before booking.
                      </p>
                    </div>
                    <Button
                      type="button"
                      variant="secondary"
                      onClick={() => setSelectedTravelerId("new")}
                    >
                      Add traveler
                    </Button>
                  </div>

                  <div className="stack-tight">
                    {workspace.travelers.map((traveler) => (
                      <button
                        key={traveler.id}
                        type="button"
                        className={[
                          "traveler-rail-item",
                          selectedTravelerId === traveler.id ? "traveler-rail-item-active" : "",
                        ]
                          .filter(Boolean)
                          .join(" ")}
                        onClick={() => setSelectedTravelerId(traveler.id)}
                      >
                        <div className="traveler-rail-topline">
                          <strong>{traveler.displayName}</strong>
                          {traveler.relationship === "self" ? <Badge tone="value">Primary</Badge> : null}
                        </div>
                        <p>{summarizeTraveler(traveler) || "Traveler details in progress."}</p>
                      </button>
                    ))}

                    {workspace.travelers.length === 0 ? (
                      <div className="muted-card">
                        <p className="item-title">No travelers yet</p>
                        <p className="item-copy">
                          Start with yourself, then keep adding partner, children, or other family members.
                        </p>
                      </div>
                    ) : null}
                  </div>
                </Surface>

                <div className="stack">
                  <Surface className="inset-card">
                    <SectionHeading
                      eyebrow={selectedTraveler ? "Edit traveler" : "New traveler"}
                      title={selectedTraveler ? selectedTraveler.displayName : "Add another traveler"}
                      description={
                        selectedTraveler
                          ? "Review one family member at a time so all booking details remain visible."
                          : "Create a new traveler record without losing the rest of the family list."
                      }
                    />
                    <TravelerForm
                      initialValue={selectedTraveler}
                      submitLabel={selectedTraveler ? "Update traveler" : "Save traveler"}
                      onSubmit={(value) => saveTravelerMutation.mutate(value)}
                      onCancel={selectedTraveler ? () => setSelectedTravelerId("new") : undefined}
                      disabled={saveTravelerMutation.isPending}
                    />
                    {selectedTraveler ? (
                      <div className="panel-actions">
                        <Button
                          type="button"
                          variant="ghost"
                          onClick={() => deleteTravelerMutation.mutate(selectedTraveler.id)}
                          disabled={deleteTravelerMutation.isPending}
                        >
                          Remove traveler
                        </Button>
                        <Button
                          type="button"
                          variant="secondary"
                          onClick={() => setSelectedTravelerId("new")}
                        >
                          Add another traveler
                        </Button>
                      </div>
                    ) : null}
                  </Surface>
                </div>
              </div>
            ) : (
              <div className="muted-card">
                <p className="item-title">Finish account setup first</p>
                <p className="item-copy">Traveler details open up as soon as you have a live session.</p>
              </div>
            )}
            {saveTravelerMutation.isError || deleteTravelerMutation.isError ? (
              <div className="notice notice-alert">
                {getErrorMessage(
                  saveTravelerMutation.error ?? deleteTravelerMutation.error,
                  "Unable to update traveler details.",
                )}
              </div>
            ) : null}
          </Surface>
        );

      case "preferences":
        return (
          <Surface className="setup-stage">
            <SectionHeading
              eyebrow="Step 3"
              title="Defaults and notifications"
              description="Home airports, airline preferences, quiet hours, and watch defaults live on their own page now."
              action={
                <Badge
                  tone={
                    hasPreferencesConfigured(
                      workspace.preferences.homeAirports,
                      workspace.preferences.defaultNotifyChannel,
                    )
                      ? "value"
                      : "muted"
                  }
                >
                  {hasPreferencesConfigured(
                    workspace.preferences.homeAirports,
                    workspace.preferences.defaultNotifyChannel,
                  )
                    ? "Ready"
                    : "Next"}
                </Badge>
              }
            />
            {canEditProfileSections ? (
              <PreferencesForm
                initialValue={workspace.preferences}
                submitLabel="Save defaults"
                onSubmit={(value) => savePreferencesMutation.mutate(value)}
                disabled={savePreferencesMutation.isPending}
              />
            ) : (
              <div className="muted-card">
                <p className="item-copy">Preferences unlock once an authenticated backend session exists.</p>
              </div>
            )}
            {savePreferencesMutation.isError ? (
              <div className="notice notice-alert">
                {getErrorMessage(savePreferencesMutation.error, "Unable to save preferences.")}
              </div>
            ) : null}
          </Surface>
        );

      case "payment":
        return (
          <Surface className="setup-stage">
            <SectionHeading
              eyebrow="Step 4"
              title="Payment method"
              description="Keep booking approval lightweight by storing one default card on its own onboarding page."
              action={
                <Badge tone={defaultPaymentMethod ? "value" : "muted"}>
                  {defaultPaymentMethod ? "Saved" : "Optional"}
                </Badge>
              }
            />
            {canEditProfileSections ? (
              <PaymentMethodForm
                initialValue={defaultPaymentMethod}
                submitLabel={defaultPaymentMethod ? "Update payment method" : "Add payment method"}
                onSubmit={(value) => savePaymentMethodMutation.mutate(value)}
                disabled={savePaymentMethodMutation.isPending}
              />
            ) : (
              <div className="muted-card">
                <p className="item-copy">Payment setup stays blocked until sign-in is complete.</p>
              </div>
            )}
            {savePaymentMethodMutation.isError ? (
              <div className="notice notice-alert">
                {getErrorMessage(savePaymentMethodMutation.error, "Unable to save payment method.")}
              </div>
            ) : null}
          </Surface>
        );

      case "template":
        return (
          <Surface className="setup-stage">
            <SectionHeading
              eyebrow="Step 5"
              title="Starter template"
              description="Save a reusable trip starter here, then move to the final review page for one last confirmation pass."
              action={<Badge tone={starterTemplate ? "value" : "muted"}>{starterTemplate ? "Saved" : "Next"}</Badge>}
            />
            {canEditProfileSections ? (
              <TemplateForm
                initialValue={starterTemplate}
                travelerGroups={workspace.travelerGroups}
                submitLabel={starterTemplate ? "Update template" : "Save template"}
                onSubmit={(value) => saveTemplateMutation.mutate(value)}
                disabled={saveTemplateMutation.isPending}
              />
            ) : (
              <div className="muted-card">
                <p className="item-copy">Trip templates become useful right after the first secure account is ready.</p>
              </div>
            )}
            {saveTemplateMutation.isError ? (
              <div className="notice notice-alert">
                {getErrorMessage(saveTemplateMutation.error, "Unable to save template.")}
              </div>
            ) : null}
          </Surface>
        );

      case "summary":
        return (
          <Surface className="setup-stage">
            <SectionHeading
              eyebrow="Step 6"
              title="Final review"
              description="Review every traveler and the main defaults one last time before marking onboarding complete."
              action={
                <Badge tone={travelerReviewConfirmed ? "value" : "luxury"}>
                  {travelerReviewConfirmed ? "Ready to confirm" : "Needs review"}
                </Badge>
              }
            />

            <div className="stack">
              <Surface className="inset-card">
                <SectionHeading
                  eyebrow="Account"
                  title="Security and loyalty"
                  description="Quick confirmation of the account state that controls future booking approvals."
                />
                <ul className="info-list">
                  <li>Email: {workspace.currentUser?.email ?? "Not signed in"}</li>
                  <li>2FA: {workspace.currentUser?.totpEnabled ? "Enabled" : "Still needs setup"}</li>
                  <li>
                    Favorite loyalty:{` `}
                    {accountTraveler?.loyaltyPrograms.find((program) => program.isFavorite)?.programCode ??
                      "Not set"}
                  </li>
                </ul>
              </Surface>

              <Surface className="inset-card">
                <SectionHeading
                  eyebrow="Travelers"
                  title="Confirm each traveler"
                  description="Each traveler needs one explicit confirmation so mistakes are easier to catch."
                />
                {workspace.travelers.length > 0 ? (
                  <div className="stack-tight">
                    {workspace.travelers.map((traveler) => (
                      <Surface key={traveler.id} className="list-card inset-card">
                        <div className="watch-topline">
                          <div>
                            <div className="badge-row">
                              <h3>{traveler.displayName}</h3>
                              <Badge tone={traveler.relationship === "self" ? "value" : "muted"}>
                                {traveler.relationship.replace(/_/g, " ")}
                              </Badge>
                            </div>
                            <p className="item-copy">{summarizeTraveler(traveler)}</p>
                          </div>
                          <Button
                            type="button"
                            variant="ghost"
                            onClick={() => {
                              setSelectedTravelerId(traveler.id);
                              navigate("/onboarding/traveler");
                            }}
                          >
                            Edit traveler
                          </Button>
                        </div>
                        <ul className="info-list">
                          <li>Legal name: {traveler.legalFirstName} {traveler.legalLastName}</li>
                          <li>Date of birth: {traveler.dob}</li>
                          <li>Residency: {traveler.residencyCountry || "Not set"}</li>
                          <li>
                            Loyalty programs: {traveler.loyaltyPrograms.length > 0 ? traveler.loyaltyPrograms.map((program) => program.programCode).join(", ") : "None"}
                          </li>
                        </ul>
                        <label className="checkbox-row">
                          <input
                            type="checkbox"
                            checked={travelerConfirmations[traveler.id] ?? false}
                            onChange={(event) =>
                              setTravelerConfirmations((current) => ({
                                ...current,
                                [traveler.id]: event.target.checked,
                              }))
                            }
                          />
                          <span>I confirm {traveler.displayName}'s details are correct.</span>
                        </label>
                      </Surface>
                    ))}
                  </div>
                ) : (
                  <div className="muted-card">
                    <p className="item-title">No travelers to review</p>
                    <p className="item-copy">
                      Add at least one traveler before finishing onboarding.
                    </p>
                  </div>
                )}
              </Surface>

              <Surface className="inset-card">
                <SectionHeading
                  eyebrow="Preferences"
                  title="Defaults summary"
                  description="A last glance at the defaults that will prefill watches."
                />
                <ul className="info-list">
                  <li>Home airports: {workspace.preferences.homeAirports.join(", ") || "Not set"}</li>
                  <li>Notify channel: {workspace.preferences.defaultNotifyChannel || "Not set"}</li>
                  <li>Preferred airlines: {workspace.preferences.preferredAirlines.join(", ") || "Not set"}</li>
                  <li>Payment methods on file: {workspace.paymentMethods.length}</li>
                  <li>Templates saved: {workspace.templates.length}</li>
                </ul>
              </Surface>

              <div className="panel-actions">
                <Button
                  type="button"
                  onClick={() => completeOnboardingMutation.mutate()}
                  disabled={!travelerReviewConfirmed || completeOnboardingMutation.isPending}
                >
                  Finish onboarding
                </Button>
                <Button variant="ghost" to="/profile">
                  Open full settings
                </Button>
              </div>

              {completeOnboardingMutation.isError ? (
                <div className="notice notice-alert">
                  {getErrorMessage(completeOnboardingMutation.error, "Unable to finish onboarding.")}
                </div>
              ) : null}
            </div>
          </Surface>
        );

      default:
        return null;
    }
  }

  return (
    <div className="stack">
      <div className="onboarding-shell">
        <Surface className="onboarding-sidebar">
          <div className="stack-tight">
            <div>
              <p className="eyebrow">Onboarding</p>
              <h2>Travel setup</h2>
              <p className="item-copy">
                Move through the setup in focused pages and keep the rest of the flow tucked away.
              </p>
            </div>
            <Badge tone="value">{progressLabel}</Badge>
          </div>

          <div className="stack-tight">
            {stepMeta.map((step, index) => (
              <button
                key={step.id}
                type="button"
                className={[
                  "sidebar-step",
                  step.active ? "sidebar-step-active" : "",
                  step.complete ? "sidebar-step-complete" : "",
                ]
                  .filter(Boolean)
                  .join(" ")}
                onClick={() => navigate(step.href)}
              >
                <span className="sidebar-step-dot" />
                <span className="sidebar-step-copy">
                  <strong>{index + 1}. {step.shortTitle}</strong>
                  <small>{step.detail}</small>
                </span>
              </button>
            ))}
          </div>

          <Surface className="inset-card">
            <p className="field-label">Readiness snapshot</p>
            <ul className="info-list">
              <li>{workspace.travelers.length} travelers saved</li>
              <li>{workspace.paymentMethods.length} payment methods</li>
              <li>{workspace.templates.length} templates ready</li>
              <li>{workspace.preferences.defaultNotifyChannel || "No"} default notify channel</li>
            </ul>
          </Surface>
        </Surface>

        <div className="stack">
          <Surface className="page-hero onboarding-hero">
            <SectionHeading
              eyebrow={`Step ${activeStepIndex + 1}`}
              title={stepMeta.find((step) => step.active)?.title ?? "Onboarding"}
              description="Each section is isolated so you can review details without scrolling through the entire setup."
              action={<Badge tone="value">{progressLabel}</Badge>}
            />
          </Surface>

          {renderStepContent()}

          <Surface className="inset-card">
            <div className="panel-actions panel-actions-between">
              {previousStep ? (
                <Button variant="ghost" to={`/onboarding/${previousStep.id}`}>
                  Back
                </Button>
              ) : (
                <span />
              )}
              {nextStep ? (
                <Button to={`/onboarding/${nextStep.id}`}>Next step</Button>
              ) : (
                <Button to="/watches/new">Create first watch</Button>
              )}
            </div>
          </Surface>
        </div>
      </div>

      <EmptyState
        title="Booking remains gated"
        copy="This flow speeds up setup, but approval still requires an authenticated session, TOTP, and the existing booking safeguards before any charge can happen."
        action={
          <div className="button-row">
            <Button to="/watches/new">Open watch editor</Button>
            <Button variant="secondary" to="/profile">
              Review full settings
            </Button>
          </div>
        }
      />
    </div>
  );
}
