from __future__ import annotations

from textual import events
from textual.widgets import Input


def normalize_paste(text: str) -> str:
    lines = [line.strip() for line in text.splitlines()]
    return " ".join(line for line in lines if line)


def read_clipboard_text() -> str:
    try:
        import pyperclip

        text = pyperclip.paste()
        if text:
            return str(text)
    except Exception:
        pass

    try:
        import tkinter

        root = tkinter.Tk()
        root.withdraw()
        try:
            return str(root.clipboard_get())
        finally:
            root.destroy()
    except Exception:
        return ""


class PromptInput(Input):
    def action_paste(self) -> None:
        text = normalize_paste(read_clipboard_text() or self.app.clipboard)
        if not text:
            return
        start, end = self.selection
        self.replace(text, start, end)

    def _on_paste(self, event: events.Paste) -> None:
        text = normalize_paste(event.text)
        if text:
            selection = self.selection
            if selection.is_empty:
                self.insert_text_at_cursor(text)
            else:
                self.replace(text, *selection)
        event.stop()
