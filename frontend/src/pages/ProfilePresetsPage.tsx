import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useMemo, useState } from "react";

import { ApiError } from "@/api/client";
import { queryKeys, travelWatchApi } from "@/api/travelWatchApi";
import { PreferencesForm, TravelerGroupForm } from "@/components/profile/ProfileForms";
import { Button, PillRow, SectionHeading, Surface } from "@/components/ui/primitives";

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

export function ProfilePresetsPage() {
  const queryClient = useQueryClient();
  const [editingGroupId, setEditingGroupId] = useState<string | null>(null);
  const { data } = useQuery({
    queryKey: queryKeys.profile,
    queryFn: travelWatchApi.getProfileWorkspace,
  });
  const { data: integrationData } = useQuery({
    queryKey: queryKeys.integrations,
    queryFn: travelWatchApi.getIntegrations,
  });

  const savePreferencesMutation = useMutation({
    mutationFn: travelWatchApi.savePreferences,
    onSuccess: async () => {
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: queryKeys.profile }),
        queryClient.invalidateQueries({ queryKey: ["watch-draft"] }),
      ]);
    },
  });

  const saveTravelerGroupMutation = useMutation({
    mutationFn: travelWatchApi.saveTravelerGroup,
    onSuccess: async () => {
      setEditingGroupId(null);
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: queryKeys.profile }),
        queryClient.invalidateQueries({ queryKey: ["watch-draft"] }),
      ]);
    },
  });

  const deleteTravelerGroupMutation = useMutation({
    mutationFn: travelWatchApi.deleteTravelerGroup,
    onSuccess: async () => {
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: queryKeys.profile }),
        queryClient.invalidateQueries({ queryKey: ["watch-draft"] }),
      ]);
    },
  });

  const editingGroup = useMemo(() => {
    const travelerGroups = data?.travelerGroupOptions ?? [];
    if (editingGroupId === "new") {
      return { name: "", travelerIds: [] };
    }
    return editingGroupId
      ? travelerGroups.find((group) => group.id === editingGroupId) ?? null
      : null;
  }, [data?.travelerGroupOptions, editingGroupId]);

  if (!data) {
    return (
      <div className="stack">
        <Surface>Loading watch presets...</Surface>
      </div>
    );
  }

  const messagingIntegration = integrationData?.providers.find((provider) => provider.key === "notifications");

  return (
    <div className="stack">
      <SectionHeading
        eyebrow="Defaults"
        title="Watch presets"
        description="Set these less-often-changed defaults once, then let TRAMP reuse them whenever you create or refine a watch."
        action={<Button variant="secondary" to="/profile">Back to profile</Button>}
      />

      <Surface>
        <SectionHeading
          eyebrow="Traveler groups"
          title="Preset traveler shortcuts"
          description="Turn your household into reusable trip presets so each new watch starts with the right people already selected."
          action={
            <Button type="button" variant="secondary" onClick={() => setEditingGroupId("new")}>
              Add group
            </Button>
          }
        />
        <PillRow items={data.travelerGroups} selected={data.travelerGroups[0]} />
        <div className="stack-tight">
          {data.travelerGroupOptions.map((group) => (
            <Surface key={group.id} className="list-card inset-card">
              <div className="watch-topline">
                <div>
                  <h3>{group.name}</h3>
                  <p className="item-copy">
                    {group.travelerIds.length} traveler{group.travelerIds.length === 1 ? "" : "s"} in this preset
                  </p>
                </div>
                <div className="button-row">
                  <Button type="button" variant="secondary" onClick={() => setEditingGroupId(group.id)}>
                    Edit
                  </Button>
                  <Button
                    type="button"
                    variant="ghost"
                    onClick={() => deleteTravelerGroupMutation.mutate(group.id)}
                    disabled={deleteTravelerGroupMutation.isPending}
                  >
                    Remove
                  </Button>
                </div>
              </div>
            </Surface>
          ))}
        </div>
        {editingGroup ? (
          <TravelerGroupForm
            initialValue={editingGroupId === "new" ? null : editingGroup}
            travelers={data.travelers}
            submitLabel={editingGroupId === "new" ? "Save group" : "Update group"}
            onSubmit={(value) => saveTravelerGroupMutation.mutate(value)}
            onCancel={() => setEditingGroupId(null)}
            disabled={saveTravelerGroupMutation.isPending}
          />
        ) : null}
        {saveTravelerGroupMutation.isError || deleteTravelerGroupMutation.isError ? (
          <div className="notice notice-alert">
            {getErrorMessage(
              saveTravelerGroupMutation.error ?? deleteTravelerGroupMutation.error,
              "Unable to update traveler groups.",
            )}
          </div>
        ) : null}
      </Surface>

      <Surface>
        <PreferencesForm
          initialValue={data.preferences}
          submitLabel={savePreferencesMutation.isPending ? "Saving presets..." : "Save watch presets"}
          onSubmit={(value) => savePreferencesMutation.mutate(value)}
          disabled={savePreferencesMutation.isPending}
          includeNotificationControls={false}
          notificationContext={{
            currentUserEmail: data.currentUser?.email,
            telegramChatId: data.currentUser?.telegramChatId,
            messagingIntegration,
          }}
        />

        {savePreferencesMutation.isError ? (
          <div className="notice notice-alert">
            {getErrorMessage(savePreferencesMutation.error, "Unable to save watch presets.")}
          </div>
        ) : null}
      </Surface>
    </div>
  );
}
