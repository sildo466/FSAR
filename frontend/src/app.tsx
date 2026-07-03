// SPDX-License-Identifier: Apache-2.0
import { useEffect } from "react";
import { BrowserRouter, Routes, Route } from "react-router-dom";
import { useWS } from "./stores/ws";
import { Chat } from "./pages/Chat";
import { Reflection } from "./pages/Reflection";
import { Memory } from "./pages/Memory";
import { Library } from "./pages/Library";
import { Insights } from "./pages/Insights";
import { Settings } from "./pages/Settings";
import { Usage } from "./pages/Usage";

export function App() {
  const init = useWS((s) => s.init);
  useEffect(() => {
    init();
  }, [init]);
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/" element={<Chat />} />
        <Route path="/reflection" element={<Reflection />} />
        <Route path="/memory" element={<Memory />} />
        <Route path="/library" element={<Library />} />
        <Route path="/insights" element={<Insights />} />
        <Route path="/settings" element={<Settings />} />
        <Route path="/usage" element={<Usage />} />
      </Routes>
    </BrowserRouter>
  );
}
