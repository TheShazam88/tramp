import { Button, EmptyState } from "@/components/ui/primitives";

export function NotFoundPage() {
  return (
    <EmptyState
      title="This route is not in the scaffold yet"
      copy="The app shell is ready for additional surfaces, but this path has not been designed into the foundation."
      action={<Button to="/watches">Back to watches</Button>}
    />
  );
}
