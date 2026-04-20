import json
import os
import shutil

STATE_FILE = 'database/state.json'
BACKUP_FILE = 'database/state.backup.json'

def save_state(session_data):
    try:
        os.makedirs(os.path.dirname(STATE_FILE), exist_ok=True)
        if os.path.exists(STATE_FILE):
            shutil.copy(STATE_FILE, BACKUP_FILE)
        data = _convert_tuples_to_lists(session_data)
        with open(STATE_FILE, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        return True
    except Exception as e:
        print(f"Erro ao salvar: {e}")
        return False

def load_state():
    if not os.path.exists(STATE_FILE):
        return {}
    try:
        with open(STATE_FILE, 'r', encoding='utf-8') as f:
            data = json.load(f)
        return data
    except Exception as e:
        print(f"Erro ao carregar: {e}")
        if os.path.exists(BACKUP_FILE):
            try:
                with open(BACKUP_FILE, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except:
                pass
        return {}

def reset_state():
    if os.path.exists(STATE_FILE):
        os.remove(STATE_FILE)
    if os.path.exists(BACKUP_FILE):
        os.remove(BACKUP_FILE)

def _convert_tuples_to_lists(obj):
    if isinstance(obj, tuple):
        return list(obj)
    elif isinstance(obj, list):
        return [_convert_tuples_to_lists(i) for i in obj]
    elif isinstance(obj, dict):
        return {k: _convert_tuples_to_lists(v) for k, v in obj.items()}
    return obj