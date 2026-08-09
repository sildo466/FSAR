// SPDX-License-Identifier: MIT
import React from "react";
import ReactDOM from "react-dom/client";
import { App } from "./app";
import { initI18n } from "./lib/i18nSetup";
import "./styles/globals.css";
import "katex/dist/katex.min.css";

const root = document.getElementById("root")!;

initI18n("en").then(() => {
  ReactDOM.createRoot(root).render(
    <React.StrictMode>
      <App />
    </React.StrictMode>,
  );
});