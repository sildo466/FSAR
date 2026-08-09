// SPDX-License-Identifier: MIT
import { afterEach, beforeAll, describe, expect, it } from "vitest";
import { cleanup, fireEvent, render } from "@testing-library/react";
import { initI18n } from "../../lib/i18nSetup";
import { MessageList, type ChatMessage } from "./MessageList";
import { useCardsStore } from "../../stores/cards";

beforeAll(async () => {
  await initI18n("en");
});

afterEach(cleanup);

function renderMessage(content: string, role: "user" | "assistant" = "assistant") {
    const messages: ChatMessage[] = [
        { id: "m1", role, content, streaming: false },
    ];
    return render(
        <MessageList
            messages={messages}
            pendingRisks={[]}
            onRespond={() => {}}
            onRate={() => {}}
        />
    );
}

describe("AssistantBody think-block rendering", () => {
    it("renders think block as collapsible, hidden by default", () => {
        const { getByTestId, getByText, queryByText } = renderMessage(
            "hello <think>internal reasoning steps</think> world"
        );
        expect(getByTestId("thinking-block")).toBeTruthy();
        // Label switches between collapsed / expanded
        expect(getByText("Thought process")).toBeTruthy();
        // Hidden content not in DOM until expanded
        expect(queryByText("internal reasoning steps")).toBeNull();
    });

    it("expands on click and shows the raw thinking text", () => {
        const { getByText } = renderMessage(
            "<think>chain of thought here</think>"
        );
        fireEvent.click(getByText("Thought process"));
        expect(getByText("chain of thought here")).toBeTruthy();
        expect(getByText("Thinking")).toBeTruthy();
    });

    it("renders surrounding prose as a ReactMarkdown paragraph", () => {
        const { container } = renderMessage(
            "<think>reasoning</think>**bold answer**"
        );
        // <strong>bold answer</strong> should appear after the think block
        expect(container.innerHTML).toContain("<strong>bold answer</strong>");
    });

    it("no think blocks: falls through to plain ReactMarkdown path (no extra UI)", () => {
        const { queryByTestId, container } = renderMessage("just **markdown**");
        expect(queryByTestId("thinking-block")).toBeNull();
        expect(container.innerHTML).toContain("<strong>markdown</strong>");
    });

    it("renders the active character name and avatar", () => {
        useCardsStore.setState({
            characters: [{
                id: 7,
                name: "Coding Coach",
                description: "",
                personality: "",
                is_default: 0,
                avatar_path: "avatars/7.jpg",
            }],
        });
        const messages: ChatMessage[] = [{
            id: "m1",
            role: "assistant",
            content: "Ready",
            character_id: 7,
            character_name: "Coding Coach",
        }];

        const { getByText, getByAltText } = render(
            <MessageList
                messages={messages}
                pendingRisks={[]}
                onRespond={() => {}}
                onRate={() => {}}
            />
        );

        expect(getByText("Coding Coach")).toBeTruthy();
        expect(getByAltText("Coding Coach").getAttribute("src")).toContain("/api/card/7/avatar");
    });
});
