import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useMemo, useState } from "react";

import { ApiError } from "@/api/client";
import { queryKeys, travelWatchApi } from "@/api/travelWatchApi";
import { Badge, Button, SectionHeading, Surface } from "@/components/ui/primitives";

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

function channelLabel(value: string) {
  switch (value) {
    case "email":
      return "Email";
    case "telegram":
      return "Telegram";
    case "both":
      return "Both";
    default:
      return "Inherit";
  }
}

export function ProfileNotificationsPage() {
  const queryClient = useQueryClient();
  const { data } = useQuery({
    queryKey: queryKeys.profile,
    queryFn: travelWatchApi.getProfileWorkspace,
  });
  const { data: integrationData } = useQuery({
    queryKey: queryKeys.integrations,
    queryFn: travelWatchApi.getIntegrations,
  });

  const messagingIntegration = integrationData?.providers.find((provider) => provider.key === "notifications");
  const [form, setForm] = useState({
    accountChannel: "email",
    watchDefaultChannel: "inherit",
    telegramChatId: "",
  });

  useEffect(() => {
    if (!data) {
      return;
    }
    setForm({
      accountChannel: data.currentUser?.defaultNotifyChannel ?? "email",
      watchDefaultChannel: data.preferences.defaultNotifyChannel ?? "inherit",
      telegramChatId: data.currentUser?.telegramChatId ?? "",
    });
  }, [data]);

  const guidance = useMemo(() => {
    if (form.accountChannel === "email") {
      return [
        `Alerts will go to ${data?.currentUser?.email ?? "your signed-in email address"}.`,
        "Ask an admin to enable the Messaging integration with `smtp_dev` and test the connector before relying on email alerts.",
      ];
    }

    if (form.accountChannel === "telegram") {
      return [
        "Paste your Telegram chat ID below to link this account to your bot destination.",
        "Ask an admin to enable the Messaging integration with `telegram_bot` and test it after adding the bot token.",
      ];
    }

    if (form.accountChannel === "both") {
      return [
        "Both will deliver to your email and your Telegram chat when both destinations are ready.",
        "Make sure your Telegram chat ID is linked and the admin Messaging integration is enabled before switching here.",
      ];
    }

    return [
      "Inherit follows the account-level or watch-level notification routing.",
      "Use the watch default below to decide what new watches should preselect.",
    ];
  }, [data?.currentUser?.email, form.accountChannel]);

  const saveMutation = useMutation({
    mutationFn: async () => {
      await Promise.all([
        travelWatchApi.saveUserSettings({
          defaultNotifyChannel: form.accountChannel,
          telegramChatId: form.telegramChatId,
        }),
        data
          ? travelWatchApi.savePreferences({
              ...data.preferences,
              defaultNotifyChannel: form.watchDefaultChannel,
            })
          : Promise.resolve(),
      ]);
    },
    onSuccess: async () => {
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: queryKeys.profile }),
        queryClient.invalidateQueries({ queryKey: ["watch-draft"] }),
      ]);
    },
  });

  if (!data) {
    return (
      <div className="stack">
        <Surface>Loading notification settings...</Surface>
      </div>
    );
  }

  const telegramReady = Boolean(form.telegramChatId.trim());
  const messagingReady = Boolean(messagingIntegration?.enabled);

  return (
    <div className="stack">
      <SectionHeading
        eyebrow="Notifications"
        title="Notification method"
        description="Pick how this user receives alerts, link the right destination, and set what new watches should default to."
        action={<Button variant="secondary" to="/profile">Back to profile</Button>}
      />

      <Surface>
        <SectionHeading
          eyebrow="Delivery status"
          title="User enablement"
          description="The admin enables the connector. The user links their own destination here."
          action={
            messagingIntegration ? (
              <Badge tone={messagingIntegration.enabled ? "value" : "alert"}>
                {messagingIntegration.environment} / {messagingIntegration.enabled ? "enabled" : "disabled"}
              </Badge>
            ) : (
              <Badge tone="alert">Messaging unavailable</Badge>
            )
          }
        />

        <div className="summary-grid">
          <Surface className="field-card">
            <p className="field-label">Account email</p>
            <strong>{data.currentUser?.email ?? "Not signed in"}</strong>
          </Surface>
          <Surface className="field-card">
            <p className="field-label">Telegram destination</p>
            <strong>{data.currentUser?.telegramChatId || "Not linked"}</strong>
          </Surface>
          <Surface className="field-card">
            <p className="field-label">Account channel</p>
            <strong>{channelLabel(data.currentUser?.defaultNotifyChannel ?? "email")}</strong>
          </Surface>
          <Surface className="field-card">
            <p className="field-label">New watch default</p>
            <strong>{channelLabel(data.preferences.defaultNotifyChannel || "inherit")}</strong>
          </Surface>
        </div>

        <Surface className="inset-card">
          <p className="field-label">What the user needs</p>
          <div className="stack-tight">
            {guidance.map((line) => (
              <p key={line} className="helper-copy">
                {line}
              </p>
            ))}
            <p className="helper-copy">
              Current readiness: connector {messagingReady ? "enabled" : "not enabled"} / Telegram destination{" "}
              {telegramReady ? "linked" : "not linked"}.
            </p>
          </div>
        </Surface>
      </Surface>

      <Surface>
        <form
          className="form-shell"
          onSubmit={(event) => {
            event.preventDefault();
            saveMutation.mutate();
          }}
        >
          <div className="toolbar-row">
            <div>
              <p className="field-label">Delivery controls</p>
              <p className="helper-copy">
                Account channel controls where alerts route for this user. Watch default controls what newly created watches start with.
              </p>
            </div>
            <div className="button-row">
              <Button variant="ghost" to="/admin/integrations/messaging">
                Open messaging admin
              </Button>
            </div>
          </div>

          <div className="form-grid">
            <div className="field-stack">
              <label htmlFor="notification-account-channel">Account channel</label>
              <select
                id="notification-account-channel"
                className="text-input"
                value={form.accountChannel}
                onChange={(event) => setForm((current) => ({ ...current, accountChannel: event.target.value }))}
                disabled={saveMutation.isPending}
              >
                <option value="email">Email</option>
                <option value="telegram">Telegram</option>
                <option value="both">Both</option>
                <option value="inherit">Inherit</option>
              </select>
              <p className="helper-copy">Used for user-level delivery routing.</p>
            </div>

            <div className="field-stack">
              <label htmlFor="notification-watch-default">New watch default</label>
              <select
                id="notification-watch-default"
                className="text-input"
                value={form.watchDefaultChannel}
                onChange={(event) =>
                  setForm((current) => ({ ...current, watchDefaultChannel: event.target.value }))
                }
                disabled={saveMutation.isPending}
              >
                <option value="inherit">Inherit</option>
                <option value="email">Email</option>
                <option value="telegram">Telegram</option>
                <option value="both">Both</option>
              </select>
              <p className="helper-copy">Used to prefill new watches.</p>
            </div>

            <div className="field-stack field-span-full">
              <label htmlFor="notification-telegram-chat-id">Telegram chat ID</label>
              <input
                id="notification-telegram-chat-id"
                className="text-input"
                value={form.telegramChatId}
                onChange={(event) => setForm((current) => ({ ...current, telegramChatId: event.target.value }))}
                placeholder="123456789 or -1001234567890"
                disabled={saveMutation.isPending}
              />
              <p className="helper-copy">
                Users can paste their own Telegram chat ID here after starting a chat with the configured bot.
              </p>
            </div>
          </div>

          <div className="panel-actions">
            <Button type="submit" disabled={saveMutation.isPending}>
              {saveMutation.isPending ? "Saving notification settings..." : "Save notification settings"}
            </Button>
          </div>

          {saveMutation.isError ? (
            <div className="notice notice-alert">
              {getErrorMessage(saveMutation.error, "Unable to save notification settings.")}
            </div>
          ) : null}
        </form>
      </Surface>
    </div>
  );
}
