// SPDX-License-Identifier: Apache-2.0
import { useEffect } from "react";
import { useWS } from "./stores/ws";

export function App() {
  const init = useWS((s) => s.init);
  useEffect(() => {
    init();
  }, [init]);
  return <div className="p-4">FSAR</div>;
}
