from __future__ import annotations

from pathlib import Path

from app.core.config import Settings

_KNOWN_DATA_SUBDIRS = {"raw", "processed", "faiss_indexes"}


def _split_path_parts(path_value: str | Path) -> list[str]:
    normalized = str(path_value).strip().replace("\\", "/")
    return [part for part in normalized.split("/") if part and part != "."]


def normalize_document_storage_path(path_value: str | Path, settings: Settings) -> str:
    parts = _split_path_parts(path_value)
    if not parts:
        return ""

    data_dir_name = settings.data_dir.name
    if data_dir_name in parts:
        anchor = parts.index(data_dir_name)
        relative_parts = parts[anchor + 1 :]
        return Path(*relative_parts).as_posix() if relative_parts else ""

    if parts[0].lower() in _KNOWN_DATA_SUBDIRS:
        return Path(*parts).as_posix()

    if len(parts) >= 2 and parts[-2].lower() in _KNOWN_DATA_SUBDIRS:
        return Path(parts[-2], parts[-1]).as_posix()

    if len(parts) == 1:
        return parts[0]

    return Path(*parts).as_posix()


def resolve_document_storage_path(path_value: str | Path, settings: Settings) -> Path:
    raw_path = Path(str(path_value))
    if raw_path.exists():
        return raw_path

    portable_path = Path(normalize_document_storage_path(path_value, settings))
    if not portable_path.parts:
        return settings.raw_data_dir

    if portable_path.parts[0].lower() in _KNOWN_DATA_SUBDIRS:
        return settings.data_dir / portable_path

    return settings.raw_data_dir / portable_path.name


def build_document_storage_path(stored_name: str) -> str:
    return (Path("raw") / stored_name).as_posix()
