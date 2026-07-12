// SPDX-License-Identifier: Apache-2.0
import { useEffect } from "react";
import { BrowserRouter, Routes, Route } from "react-router-dom";
import { useWS } from "./stores/ws";
import { useCardsStore } from "./stores/cards";
import { Sidebar } from "./components/shell/Sidebar";
import { Topbar } from "./components/shell/Topbar";
import { Chat } from "./pages/Chat";
import { Reflection } from "./pages/Reflection";
import { Memory } from "./pages/Memory";
import { Library } from "./pages/Library";
import { Insights } from "./pages/Insights";
import { Cards } from "./pages/Cards";
import { Settings } from "./pages/Settings";
import { Usage } from "./pages/Usage";
import { Onboarding } from "./pages/Onboarding";
import { useThemeApplication, useMotionApplication, useFontScaleApplication } from "./lib/theme";

export function App() {
  const init = useWS((s) => s.init);
  useEffect(() => {
    init();
  }, [init]);

  const client = useWS((s) => s.client);
  const initCards = useCardsStore((s) => s.init);
  useEffect(() => {
    if (!client) return;
    const detach = initCards(client);
    return () => detach();
  }, [client, initCards]);

  useThemeApplication();
  useMotionApplication();
  useFontScaleApplication();

  const config = useWS((s) => s.config) as Record<string, unknown> | null;
  const required = (config?.onboarding as { required?: boolean } | undefined)?.required === true;

  return (
    <BrowserRouter>
      <div className="relative flex h-screen overflow-hidden">
        <div className="app-backdrop" aria-hidden="true">
          <div className="app-orb one" />
          <div className="app-orb two" />
          <div className="app-orb three" />
        </div>
        <Sidebar />
        <div className="relative z-10 flex min-w-0 flex-1 flex-col">
        <Topbar />
        <main className="flex-1 overflow-auto px-3 pb-3 pt-[4.5rem]">
          <Routes>
            <Route path="/" element={<Chat />} />
            <Route path="/chat" element={<Chat />} />
            <Route path="/reflection" element={<Reflection />} />
            <Route path="/memory" element={<Memory />} />
            <Route path="/library" element={<Library />} />
            <Route path="/cards" element={<Cards />} />
            <Route path="/insights" element={<Insights />} />
            <Route path="/settings" element={<Settings />} />
            <Route path="/usage" element={<Usage />} />
          </Routes>
        </main>
        </div>
      </div>
      {required && <Onboarding />}
    </BrowserRouter>
  );
}
