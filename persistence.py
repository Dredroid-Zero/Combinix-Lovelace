"""
persistence.py — Persistência ATÔMICA de estado.

Estratégia:
1. Sempre escreve para arquivo temporário primeiro
2. Faz fsync + rename atômico (operação POSIX)
3. Se houver corrupção, recupera do backup automaticamente
4. Nunca usa append — sempre overwrite completo

Isso elimina os erros "Extra data" causados por escritas interrompidas.
"""
import json
import os
import shutil
import tempfile

# Caminhos relativos ao diretório do app (não ao CWD)
_DIR = os.path.dirname(os.path.abspath(__file__))
STATE_FILE  = os.path.join(_DIR, 'database', 'state.json')
BACKUP_FILE = os.path.join(_DIR, 'database', 'state.backup.json')


def _convert_tuples_to_lists(obj):
    if isinstance(obj, tuple):
        return list(obj)
    elif isinstance(obj, list):
        return [_convert_tuples_to_lists(i) for i in obj]
    elif isinstance(obj, dict):
        return {k: _convert_tuples_to_lists(v) for k, v in obj.items()}
    return obj


def _atomic_write_json(path, data):
    """
    Escreve JSON de forma atômica:
    1. Escreve para arquivo temporário no mesmo diretório
    2. Faz flush + fsync (garante que os bytes estão no disco)
    3. Renomeia atomicamente sobre o arquivo final
    Se o processo for morto durante a escrita, o arquivo final fica intacto.
    """
    target_dir = os.path.dirname(path)
    os.makedirs(target_dir, exist_ok=True)
    fd, tmp_path = tempfile.mkstemp(dir=target_dir, prefix='.tmp_', suffix='.json')
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
            f.flush()
            try:
                os.fsync(f.fileno())  # garante write-through ao disco
            except OSError:
                pass
        # Rename atômico (POSIX) — substitui o arquivo final
        os.replace(tmp_path, path)
    except Exception:
        # Se algo der errado, remove o tmp para não acumular lixo
        if os.path.exists(tmp_path):
            try: os.remove(tmp_path)
            except OSError: pass
        raise


def _safe_load_json(path):
    """Carrega JSON validando que é um dict e retornando {} se corrompido."""
    if not os.path.exists(path):
        return None
    try:
        with open(path, 'r', encoding='utf-8') as f:
            content = f.read()
        if not content.strip():
            return None
        data = json.loads(content)
        if not isinstance(data, dict):
            return None
        return data
    except (json.JSONDecodeError, OSError, UnicodeDecodeError) as e:
        print(f"[persistence] Arquivo corrompido em {path}: {e}")
        return None


def save_state(session_data):
    """
    Salva o estado de forma atômica e resiliente.
    Mantém um backup do estado anterior antes de escrever.
    """
    try:
        os.makedirs(os.path.dirname(STATE_FILE), exist_ok=True)

        # Backup do estado anterior (se existir e for válido)
        if os.path.exists(STATE_FILE):
            current = _safe_load_json(STATE_FILE)
            if current is not None:
                try:
                    shutil.copy2(STATE_FILE, BACKUP_FILE)
                except OSError:
                    pass

        data = _convert_tuples_to_lists(session_data)
        _atomic_write_json(STATE_FILE, data)
        return True
    except Exception as e:
        print(f"[persistence] Erro ao salvar: {e}")
        return False


def load_state():
    """
    Carrega o estado. Se o arquivo principal estiver corrompido,
    tenta recuperar do backup automaticamente.
    """
    data = _safe_load_json(STATE_FILE)
    if data is not None:
        return data

    # Arquivo principal corrompido ou inexistente — tentar backup
    if os.path.exists(BACKUP_FILE):
        backup_data = _safe_load_json(BACKUP_FILE)
        if backup_data is not None:
            print("[persistence] Recuperado do backup")
            # Restaurar arquivo principal a partir do backup
            try:
                _atomic_write_json(STATE_FILE, backup_data)
            except Exception:
                pass
            return backup_data

    return {}


def reset_state():
    """Remove arquivos de estado. Não toca em outros arquivos do sistema."""
    for f in (STATE_FILE, BACKUP_FILE):
        if os.path.exists(f):
            try:
                os.remove(f)
            except OSError:
                pass