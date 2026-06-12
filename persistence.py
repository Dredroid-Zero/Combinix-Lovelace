"""Persistência local resiliente e preparada para workspaces.

No modo atual existe apenas o workspace ``local``. A separação por diretório deixa
a aplicação pronta para, futuramente, associar cada coordenador autenticado ao
seu próprio workspace sem misturar seleções, configurações e resultados.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import tempfile
import threading
from typing import Any, Dict

_DIR = os.path.dirname(os.path.abspath(__file__))
_DATABASE_DIR = os.path.join(_DIR, "database")
_LEGACY_STATE_FILE = os.path.join(_DATABASE_DIR, "state.json")
_LEGACY_BACKUP_FILE = os.path.join(_DATABASE_DIR, "state.backup.json")
_LOCK = threading.RLock()
_WORKSPACE_RE = re.compile(r"[^a-zA-Z0-9_.-]+")


def normalize_workspace_id(workspace_id: object = "local") -> str:
    value = str(workspace_id or "local").strip()
    value = _WORKSPACE_RE.sub("-", value).strip(".-")
    return value[:80] or "local"


def workspace_dir(workspace_id: object = "local") -> str:
    return os.path.join(_DATABASE_DIR, "workspaces", normalize_workspace_id(workspace_id))


def state_file(workspace_id: object = "local") -> str:
    return os.path.join(workspace_dir(workspace_id), "state.json")


def backup_file(workspace_id: object = "local") -> str:
    return os.path.join(workspace_dir(workspace_id), "state.backup.json")


def _convert_tuples_to_lists(obj: Any) -> Any:
    if isinstance(obj, tuple):
        return [_convert_tuples_to_lists(i) for i in obj]
    if isinstance(obj, list):
        return [_convert_tuples_to_lists(i) for i in obj]
    if isinstance(obj, dict):
        return {str(k): _convert_tuples_to_lists(v) for k, v in obj.items()}
    return obj


def _atomic_write_json(path: str, data: Dict[str, Any]) -> None:
    target_dir = os.path.dirname(path)
    os.makedirs(target_dir, exist_ok=True)
    fd, tmp_path = tempfile.mkstemp(dir=target_dir, prefix=".tmp_", suffix=".json")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(data, handle, indent=2, ensure_ascii=False)
            handle.flush()
            try:
                os.fsync(handle.fileno())
            except OSError:
                pass
        os.replace(tmp_path, path)
    except Exception:
        if os.path.exists(tmp_path):
            try:
                os.remove(tmp_path)
            except OSError:
                pass
        raise


def _safe_load_json(path: str) -> Dict[str, Any] | None:
    if not os.path.exists(path):
        return None
    try:
        with open(path, "r", encoding="utf-8") as handle:
            content = handle.read()
        if not content.strip():
            return None
        data = json.loads(content)
        return data if isinstance(data, dict) else None
    except (json.JSONDecodeError, OSError, UnicodeDecodeError):
        return None


def _migrate_legacy_local_state() -> None:
    """Move o formato antigo para database/workspaces/local uma única vez."""
    target = state_file("local")
    if os.path.exists(target) or not os.path.exists(_LEGACY_STATE_FILE):
        return
    os.makedirs(os.path.dirname(target), exist_ok=True)
    legacy = _safe_load_json(_LEGACY_STATE_FILE)
    if legacy is not None:
        _atomic_write_json(target, legacy)
    legacy_backup = _safe_load_json(_LEGACY_BACKUP_FILE)
    if legacy_backup is not None:
        _atomic_write_json(backup_file("local"), legacy_backup)


def save_state(session_data: Dict[str, Any], workspace_id: object = "local") -> bool:
    with _LOCK:
        try:
            _migrate_legacy_local_state()
            target = state_file(workspace_id)
            backup = backup_file(workspace_id)
            os.makedirs(os.path.dirname(target), exist_ok=True)
            if os.path.exists(target) and _safe_load_json(target) is not None:
                try:
                    shutil.copy2(target, backup)
                except OSError:
                    pass
            _atomic_write_json(target, _convert_tuples_to_lists(session_data))
            return True
        except Exception as exc:
            print(f"[persistence] Erro ao salvar: {exc}")
            return False


def load_state(workspace_id: object = "local") -> Dict[str, Any]:
    with _LOCK:
        _migrate_legacy_local_state()
        target = state_file(workspace_id)
        backup = backup_file(workspace_id)
        data = _safe_load_json(target)
        if data is not None:
            return data
        backup_data = _safe_load_json(backup)
        if backup_data is not None:
            try:
                _atomic_write_json(target, backup_data)
            except Exception:
                pass
            return backup_data
        return {}


def reset_state(workspace_id: object = "local") -> None:
    with _LOCK:
        for path in (state_file(workspace_id), backup_file(workspace_id)):
            if os.path.exists(path):
                try:
                    os.remove(path)
                except OSError:
                    pass
