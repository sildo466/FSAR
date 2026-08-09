import { useWS } from "../stores/ws";
import type { ClientMsg, ServerMsg } from "../lib/ws-client";

export function send(
  message: ClientMsg | Record<string, unknown>,
  predicate: (message: ServerMsg | Record<string, unknown>) => boolean = () => true,
): Promise<ServerMsg | Record<string, unknown>> {
  return new Promise((resolve, reject) => {
    const client = useWS.getState().client;
    if (!client) {
      reject(new Error("websocket is not connected"));
      return;
    }
    const handle = (response: ServerMsg) => {
      if (!predicate(response)) return;
      off();
      if (response.type === "error") {
        reject(new Error(response.message));
        return;
      }
      resolve(response);
    };
    const off = client.on(handle);
    client.send(message as ClientMsg);
  });
}

export function subscribe(listener: (message: ServerMsg) => void): () => void {
  return useWS.getState().client?.on(listener) ?? (() => undefined);
}
