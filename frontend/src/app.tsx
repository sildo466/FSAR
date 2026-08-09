// SPDX-License-Identifier: MIT
import { useEffect } from "react";
import { BrowserRouter, Routes, Route, useLocation } from "react-router-dom";
import { useWS } from "./stores/ws";
import { useCardsStore } from "./stores/cards";
import { useSessions } from "./stores/sessions";
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
import { SettingsWorkspace } from "./pages/SettingsWorkspace";
import { Onboarding } from "./pages/Onboarding";
import { IntergrationPage } from "./pages/IntergrationPage";
import { Scheduler } from "./pages/Scheduler";
import { EscapeModal } from "./components/workspace/EscapeModal";
import { useWorkspace } from "./stores/workspace";
import { useThemeApplication, useMotionApplication, useFontScaleApplication } from "./lib/theme";
import { useLocaleApplication } from "./hooks/useLocaleApplication";
import { useSpeechStore } from "./stores/speech";

function AppShell() {
  const location = useLocation();
  const isChat = location.pathname === "/" || location.pathname === "/chat";

  return (
    <div className="relative flex h-screen overflow-hidden">
      <div className="app-backdrop" aria-hidden="true">
        <div className="app-orb one" />
        <div className="app-orb two" />
        <div className="app-orb three" />
      </div>
      <Sidebar />
      <div className="relative z-10 flex min-w-0 flex-1 flex-col">
        {isChat && <Topbar />}
        <main className={`flex-1 overflow-auto px-3 pb-3 ${isChat ? "pt-[4.5rem]" : "pt-3"}`}>
          <Routes>
            <Route path="/" element={<Chat />} />
            <Route path="/chat" element={<Chat />} />
            <Route path="/reflection" element={<Reflection />} />
            <Route path="/memory" element={<Memory />} />
            <Route path="/library" element={<Library />} />
            <Route path="/cards" element={<Cards />} />
            <Route path="/insights" element={<Insights />} />
            <Route path="/settings" element={<Settings />} />
            <Route path="/settings/speech" element={<Settings initialTab="speech" />} />
            <Route path="/settings/workspace" element={<SettingsWorkspace />} />
            <Route path="/usage" element={<Usage />} />
            <Route path="/intergration" element={<IntergrationPage />} />
            <Route path="/scheduler" element={<Scheduler />} />
          </Routes>
        </main>
      </div>
    </div>
  );
}

export function App() {
  const init = useWS((s) => s.init);
  useEffect(() => {
    init();
  }, [init]);

  const client = useWS((s) => s.client);
  const initCards = useCardsStore((s) => s.init);
  const initWorkspace = useWorkspace((s) => s.init);
  const initSessions = useSessions((s) => s.init);
  useEffect(() => {
    if (!client) return;
    const detach = initCards(client);
    return () => detach();
  }, [client, initCards]);
  // Sessions must stay subscribed for the whole connection, not just while
  // the chat route is mounted: conversation.* replies arriving on another
  // route would otherwise be dropped.
  useEffect(() => {
    if (!client) return;
    const detach = initSessions(client);
    return () => detach();
  }, [client, initSessions]);
  useEffect(() => {
    if (!client) return;
    return initWorkspace(client);
  }, [client, initWorkspace]);

  useThemeApplication();
  useMotionApplication();
  useFontScaleApplication();
  useLocaleApplication();

  const config = useWS((s) => s.config) as Record<string, unknown> | null;
  const syncSpeechConfig = useSpeechStore((state) => state.syncConfig);
  useEffect(() => {
    syncSpeechConfig(config);
  }, [config, syncSpeechConfig]);
  const required = (config?.onboarding as { required?: boolean } | undefined)?.required === true;
  const escapeRequest = useWorkspace((state) => state.escapeRequest);
  const clearEscape = useWorkspace((state) => state.clearEscape);

  return (
    <BrowserRouter>
      <AppShell />
      {required && <Onboarding />}
      {escapeRequest && client && (
        <EscapeModal request={escapeRequest} onDecision={(decision) => {
          client.send({ type: "tool.sandbox.escape_decision", request_id: escapeRequest.request_id, decision });
          clearEscape();
        }} />
      )}
    </BrowserRouter>
  );
}
