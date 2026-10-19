from __future__ import annotations

import os
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

from .html_export import write_html
from .model import Puzzle
from .pdf_export import write_answer_key, write_pdf

OUTPUT_FOLDER_NAME = "Grid Logic Puzzles"


def _windows_documents() -> Path | None:
    import ctypes
    import uuid
    from ctypes import wintypes

    class GUID(ctypes.Structure):
        _fields_ = [
            ("Data1", wintypes.DWORD),
            ("Data2", wintypes.WORD),
            ("Data3", wintypes.WORD),
            ("Data4", ctypes.c_ubyte * 8),
        ]

    documents = uuid.UUID("FDD39AD0-238F-46AF-ADB4-6C85480369C7")  # FOLDERID_Documents
    guid = GUID(
        documents.time_low,
        documents.time_mid,
        documents.time_hi_version,
        (ctypes.c_ubyte * 8).from_buffer_copy(documents.bytes[8:]),
    )
    path = ctypes.c_wchar_p()
    shell32 = ctypes.windll.shell32
    if shell32.SHGetKnownFolderPath(ctypes.byref(guid), 0, None, ctypes.byref(path)) != 0:
        return None
    try:
        return Path(path.value)
    finally:
        ctypes.windll.ole32.CoTaskMemFree(path)


def _linux_documents() -> Path | None:
    try:
        result = subprocess.run(
            ["xdg-user-dir", "DOCUMENTS"], capture_output=True, text=True, timeout=5
        )
        found = result.stdout.strip()
    except (OSError, subprocess.SubprocessError):
        found = ""
    if found and Path(found) != Path.home():
        return Path(found)
    return None


def documents_dir() -> Path:
    found = None
    try:
        if os.name == "nt":
            found = _windows_documents()
        elif sys.platform != "darwin":
            found = _linux_documents()
    except Exception:
        found = None
    return found or Path.home() / "Documents"


DEFAULT_OUTPUT_DIR = documents_dir() / OUTPUT_FOLDER_NAME


@dataclass
class SavedPuzzle:
    folder: Path
    pdf: Path
    answer_key: Path
    html: Path


def safe_name(title: str) -> str:
    name = re.sub(r'[<>:"/\\|?*\x00-\x1f!]', "", title)
    name = re.sub(r"\s+", "_", name.strip()).strip("._")
    return name or "Untitled_Puzzle"


def unique_title(title: str, output_dir: Path) -> str:
    candidate = title
    number = 2
    while (output_dir / safe_name(candidate)).exists():
        candidate = f"{title} {number}"
        number += 1
    return candidate


def save_puzzle(puzzle: Puzzle, output_dir: Path) -> SavedPuzzle:
    name = safe_name(puzzle.title)
    folder = output_dir / name
    folder.mkdir(parents=True, exist_ok=True)
    return SavedPuzzle(
        folder=folder,
        pdf=write_pdf(puzzle, folder / f"{name}.pdf"),
        answer_key=write_answer_key(puzzle, folder / f"{name}_Answer_Key.pdf"),
        html=write_html(puzzle, folder / f"{name}.html"),
    )
