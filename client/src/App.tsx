import { useState, useCallback } from "react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { SplashScreen } from "@/components/SplashScreen";
import DashboardPage from "@/pages/DashboardPage";

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      retry: 1,
      staleTime: 5_000,
    },
  },
});

export default function App() {
  const [splashDone, setSplashDone] = useState(false);
  const handleSplashDone = useCallback(() => setSplashDone(true), []);

  return (
    <QueryClientProvider client={queryClient}>
      {!splashDone && <SplashScreen onDone={handleSplashDone} />}
      <div
        className={`transition-opacity duration-500 ${splashDone ? "opacity-100" : "opacity-0"}`}
        style={{ visibility: splashDone ? "visible" : "hidden" }}
      >
        <DashboardPage />
      </div>
    </QueryClientProvider>
  );
}
