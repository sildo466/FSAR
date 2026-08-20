"""Interactive modal screens for TUI commands."""

from __future__ import annotations

from typing import Callable

from textual.app import ComposeResult
from textual.containers import Container, Vertical
from textual.screen import ModalScreen
from textual.widgets import Button, Footer, Input, Label, OptionList, Static
from textual.widgets.option_list import Option


class SelectScreen(ModalScreen[str | None]):
    """Base class for selection screens with OptionList."""

    def __init__(
        self,
        title: str,
        options: list[tuple[str, str]],
        name: str | None = None,
        id: str | None = None,
        classes: str | None = None,
    ) -> None:
        super().__init__(name=name, id=id, classes=classes)
        self.title_text = title
        self.options = options

    def compose(self) -> ComposeResult:
        with Container(id="select-dialog"):
            yield Static(self.title_text, id="select-title")
            yield OptionList(
                *[Option(label, id=value) for label, value in self.options],
                id="select-options",
            )
            yield Footer()

    def on_option_list_option_selected(self, event: OptionList.OptionSelected) -> None:
        self.dismiss(event.option.id)

    def on_key(self, event) -> None:
        if event.key == "escape":
            self.dismiss(None)


class ModelSelectScreen(SelectScreen):
    """Interactive model selection screen."""

    def __init__(self, models: list[tuple[str, str]]) -> None:
        super().__init__(
            title="Select a model (↑↓ to navigate, Enter to confirm, Esc to cancel):",
            options=models,
            id="model-select",
        )


class CharacterSelectScreen(SelectScreen):
    """Interactive character card selection screen."""

    def __init__(self, characters: list[tuple[str, int]]) -> None:
        options = [(name, str(card_id)) for name, card_id in characters]
        super().__init__(
            title="Select a character (↑↓ to navigate, Enter to confirm, Esc to cancel):",
            options=options,
            id="character-select",
        )


class UserSelectScreen(SelectScreen):
    """Interactive user card selection screen."""

    def __init__(self, users: list[tuple[str, int]]) -> None:
        options = [(name, str(user_id)) for name, user_id in users]
        super().__init__(
            title="Select a user (↑↓ to navigate, Enter to confirm, Esc to cancel):",
            options=options,
            id="user-select",
        )


class ResumeSelectScreen(SelectScreen):
    """Interactive conversation history selection screen."""

    def __init__(self, conversations: list[tuple[str, str]]) -> None:
        super().__init__(
            title="Select a conversation to resume (↑↓ to navigate, Enter to confirm, Esc to cancel):",
            options=conversations,
            id="resume-select",
        )


class PermissionsScreen(ModalScreen[dict[str, str] | None]):
    """Interactive permissions configuration screen."""

    def __init__(
        self,
        current_path: str,
        current_mode: str,
        confirm_on_exit: bool,
    ) -> None:
        super().__init__(id="permissions-screen")
        self.current_path = current_path
        self.current_mode = current_mode
        self.confirm_on_exit = confirm_on_exit

    def compose(self) -> ComposeResult:
        with Container(id="permissions-dialog"):
            yield Static("Sandbox Permissions Configuration", id="permissions-title")
            with Vertical(id="permissions-form"):
                yield Label("Sandbox Path:")
                yield Input(
                    value=self.current_path,
                    placeholder="Enter sandbox path...",
                    id="sandbox-path-input",
                )
                yield Label(f"\nMode: {self.current_mode}")
                yield Static(
                    "  • auto: small agent reviews tool calls\n"
                    "  • manual: all tool calls need confirmation",
                    id="mode-help",
                )
                yield Label(f"\nConfirm on Sandbox Exit: {'Yes' if self.confirm_on_exit else 'No'}")
                yield Static(
                    "\nNote: Only sandbox path can be modified here.\n"
                    "Other security settings are read-only (configured in fsar.yaml).",
                    id="permissions-note",
                )
            with Vertical(id="permissions-actions"):
                yield Button("Save", variant="primary", id="save-btn")
                yield Button("Cancel", variant="default", id="cancel-btn")
            yield Footer()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "save-btn":
            path_input = self.query_one("#sandbox-path-input", Input)
            self.dismiss({"sandbox_path": path_input.value})
        elif event.button.id == "cancel-btn":
            self.dismiss(None)

    def on_key(self, event) -> None:
        if event.key == "escape":
            self.dismiss(None)
