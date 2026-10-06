import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useNavigate, useParams } from "react-router-dom";

import { ApiError } from "@/api/client";
import { queryKeys, travelWatchApi } from "@/api/travelWatchApi";
import { WatchForm } from "@/components/watch/WatchForm";
import {
  Badge,
  Button,
  SectionHeading,
  Surface,
} from "@/components/ui/primitives";

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

export function WatchEditorPage() {
  const { watchId } = useParams();
  const navigate = useNavigate();
  const queryClient = useQueryClient();

  const { data, error } = useQuery({
    queryKey: queryKeys.watchDraft(watchId),
    queryFn: () => travelWatchApi.getWatchDraft(watchId),
  });

  const saveWatchMutation = useMutation({
    mutationFn: travelWatchApi.saveWatchDraft,
    onSuccess: async (_, submittedDraft) => {
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: queryKeys.dashboard }),
        queryClient.invalidateQueries({ queryKey: queryKeys.watchDraft(submittedDraft.id) }),
      ]);
      navigate("/watches");
    },
  });

  const saveTravelerMutation = useMutation({
    mutationFn: travelWatchApi.saveTraveler,
  });

  if (!data) {
    return (
      <div className="stack">
        <Surface>{error ? getErrorMessage(error, "Unable to load this watch.") : "Loading watch editor..."}</Surface>
      </div>
    );
  }

  return (
    <div className="stack">
      <Surface className="page-hero">
        <SectionHeading
          eyebrow="Watch"
          title={data.title}
          description="The mockup shell is preserved, but this page now edits a real watch draft and saves it to the backend."
          action={<Badge tone={watchId ? "luxury" : "value"}>{watchId ? "Editing existing watch" : "New watch"}</Badge>}
        />

        <WatchForm
          initialValue={data}
          submitLabel={watchId ? "Save watch" : "Create watch"}
          onSubmit={(value) => saveWatchMutation.mutate(value)}
          onCreateTraveler={async (value) => {
            const traveler = await saveTravelerMutation.mutateAsync(value);
            await queryClient.invalidateQueries({ queryKey: queryKeys.profile });
            return traveler;
          }}
          disabled={saveWatchMutation.isPending}
          secondaryAction={
            <Button variant="secondary" to="/profile">
              Manage templates
            </Button>
          }
        />
      </Surface>

      {saveWatchMutation.isError ? (
        <div className="notice notice-alert">
          {getErrorMessage(saveWatchMutation.error, "Unable to save this watch draft.")}
        </div>
      ) : null}

      {saveTravelerMutation.isError ? (
        <div className="notice notice-alert">
          {getErrorMessage(saveTravelerMutation.error, "Unable to save the traveler inline.")}
        </div>
      ) : null}
    </div>
  );
}
