// SPDX-License-Identifier: MIT
import { afterEach, beforeAll, expect, it, vi } from "vitest";
import "@testing-library/jest-dom/vitest";
import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { initI18n } from "../../lib/i18nSetup";
import { ChatComposer } from "./ChatComposer";

beforeAll(async () => {
  await initI18n("en");
});

afterEach(cleanup);

function setup(over: Partial<Parameters<typeof ChatComposer>[0]> = {}) {
  const props = {
    value: "",
    onChange: vi.fn(),
    onSend: vi.fn(),
    onCancel: vi.fn(),
    busy: false,
    attachments: [],
    onPickFiles: vi.fn(),
    onRemoveAttachment: vi.fn(),
    placeholder: "Type here",
    ...over,
  };
  render(<ChatComposer {...props} />);
  return props;
}

it("forwards typing to onChange", async () => {
  const props = setup();
  await userEvent.type(screen.getByPlaceholderText("Type here"), "hi");
  expect(props.onChange).toHaveBeenCalled();
});

it("sends on Enter", async () => {
  const props = setup();
  await userEvent.type(screen.getByPlaceholderText("Type here"), "{Enter}");
  expect(props.onSend).toHaveBeenCalled();
});

it("does not send on shift+Enter", async () => {
  const props = setup();
  await userEvent.type(
    screen.getByPlaceholderText("Type here"),
    "{Shift>}{Enter}{/Shift}"
  );
  expect(props.onSend).not.toHaveBeenCalled();
});

it("lets a parent handler consume Enter first", async () => {
  const onSend = vi.fn();
  setup({
    onSend,
    onKeyDown: (e) => {
      if (e.key === "Enter") e.preventDefault();
    },
  });
  await userEvent.type(screen.getByPlaceholderText("Type here"), "{Enter}");
  expect(onSend).not.toHaveBeenCalled();
});

it("shows stop instead of send while busy", () => {
  setup({ busy: true });
  expect(screen.getByText("Stop")).toBeInTheDocument();
  expect(screen.queryByText("↵")).not.toBeInTheDocument();
});

it("renders attachment chips and removes them", async () => {
  const props = setup({
    attachments: [{ path: "C:/x/a.txt", name: "a.txt" }],
  });
  expect(screen.getByText(/a\.txt/)).toBeInTheDocument();
  await userEvent.click(screen.getByText("✕"));
  expect(props.onRemoveAttachment).toHaveBeenCalledWith(0);
});

it("renders the upload error verbatim", () => {
  setup({
    attachments: [{ path: "C:/x/a.txt", name: "a.txt" }],
    uploadError: "File upload failed",
  });
  expect(screen.getByText("File upload failed")).toBeInTheDocument();
});

it("shows the upload error even with no attachment chips", () => {
  setup({ uploadError: "File upload failed" });
  expect(screen.getByText("File upload failed")).toBeInTheDocument();
});
