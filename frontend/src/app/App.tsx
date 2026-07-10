import { RouterProvider } from "react-router-dom";

import { AppQueryProvider } from "@/app/QueryProvider";
import { router } from "@/app/router";

export function App() {
  return (
    <AppQueryProvider>
      <RouterProvider router={router} />
    </AppQueryProvider>
  );
}
