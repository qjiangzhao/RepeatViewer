"""Open files in the user's preferred external text editor."""

from __future__ import annotations

import logging
import platform
import shlex
import shutil
import subprocess
from pathlib import Path

logger = logging.getLogger(__name__)

_SETTINGS_GROUP = "text_editor"
_SETTINGS_COMMAND_KEY = "command"


def load_text_editor_command() -> str:
    """Optional custom launch command from Settings (empty = auto-detect)."""
    try:
        from PySide6.QtCore import QSettings

        settings = QSettings()
        settings.beginGroup(_SETTINGS_GROUP)
        value = settings.value(_SETTINGS_COMMAND_KEY, "")
        settings.endGroup()
        return str(value).strip() if value else ""
    except Exception:  # noqa: BLE001
        return ""


def save_text_editor_command(command: str) -> None:
    try:
        from PySide6.QtCore import QSettings

        settings = QSettings()
        settings.beginGroup(_SETTINGS_GROUP)
        settings.setValue(_SETTINGS_COMMAND_KEY, command.strip())
        settings.endGroup()
    except Exception:  # noqa: BLE001
        return


def _editor_commands() -> list[list[str]]:
    custom = load_text_editor_command()
    if custom:
        return [shlex.split(custom)]

    commands: list[list[str]] = []
    for name in ("subl", "code", "mate"):
        if shutil.which(name):
            commands.append([name])

    system = platform.system()
    if system == "Darwin":
        commands.append(["open", "-t"])
    elif system == "Windows":
        if shutil.which("notepad"):
            commands.append(["notepad"])
    else:
        for name in ("gedit", "mousepad", "xed", "kate"):
            if shutil.which(name):
                commands.append([name])
                break
        if shutil.which("xdg-open"):
            commands.append(["xdg-open"])

    return commands


def open_in_text_editor(path: Path) -> None:
    """Open one file in Sublime Text, VS Code, or the OS default text editor."""
    resolved = path.expanduser().resolve()
    if not resolved.is_file():
        raise FileNotFoundError(resolved)

    errors: list[str] = []
    for command in _editor_commands():
        if not command:
            continue
        try:
            subprocess.Popen(
                [*command, str(resolved)],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                start_new_session=True,
            )
            logger.info("Opened %s with %s", resolved.name, " ".join(command))
            return
        except OSError as exc:
            errors.append(f"{' '.join(command)}: {exc}")

    hint = (
        "Install Sublime Text (subl), VS Code (code), or another editor.\n"
        "On macOS, TextEdit is used via: open -t <file>"
    )
    detail = "\n".join(errors) if errors else "No editor command available."
    raise RuntimeError(f"Could not open {resolved.name} in a text editor.\n\n{detail}\n\n{hint}")
