import { cleanup, fireEvent, render, waitFor } from "@testing-library/react";
import { afterEach, beforeAll, expect, it, vi } from "vitest";
import { initI18n } from "../../lib/i18nSetup";
import { integrationClient, type IntegrationSnapshot } from "../../clients/integrationClient";
import { IntegrationEditor } from "./IntegrationEditor";

beforeAll(async () => {
  await initI18n("en");
});

afterEach(() => {
  vi.restoreAllMocks();
  cleanup();
});

it("saves freely editable endpoints for the main agent and sub models", async () => {
  const integration: IntegrationSnapshot = {
    id: 7,
    name: "Research team",
    description: "",
    main_model_id: 11,
    main_model: {
      id: 11,
      provider: "openai",
      base_url: "https://api.openai.com/v1",
      model: "gpt-4o-mini",
      persona_prompt: "Route and synthesize.",
    },
    rounds: 2,
    max_depth: 2,
    max_subs_picked: 1,
    subs: [{
      id: 19,
      display_name: "Reviewer",
      kind: "model",
      model_id: 12,
      model: {
        id: 12,
        provider: "openai",
        base_url: "https://api.openai.com/v1",
        model: "gpt-4o-mini",
        persona_prompt: "Review the answer.",
      },
    }],
  };
  const save = vi.spyOn(integrationClient, "save").mockResolvedValue({ id: integration.id });
  const screen = render(
    <IntegrationEditor intg={integration} onSaved={() => undefined} onDeleted={() => undefined} />,
  );

  fireEvent.change(screen.getByLabelText("Main base URL"), { target: { value: "https://main.example/v1" } });
  fireEvent.change(screen.getByLabelText("Main provider name"), { target: { value: "main-relay" } });
  fireEvent.change(screen.getByLabelText("Main model ID"), { target: { value: "main-model" } });
  fireEvent.change(screen.getByLabelText("Sub base URL"), { target: { value: "https://sub.example/v1" } });
  fireEvent.change(screen.getByLabelText("Sub provider name"), { target: { value: "sub-relay" } });
  fireEvent.change(screen.getByLabelText("Sub model ID"), { target: { value: "sub-model" } });
  fireEvent.click(screen.getByRole("button", { name: "Save ensemble" }));

  await waitFor(() => expect(save).toHaveBeenCalledWith(expect.objectContaining({
    main_model: expect.objectContaining({
      base_url: "https://main.example/v1",
      provider: "main-relay",
      model: "main-model",
    }),
    subs: [expect.objectContaining({
      model: expect.objectContaining({
        base_url: "https://sub.example/v1",
        provider: "sub-relay",
        model: "sub-model",
      }),
    })],
  })));
});
