#!/usr/bin/env sh
set -eu
cd "$(dirname "$0")"
PORT="${COMBINIX_PORT:-5000}"
URL="http://127.0.0.1:${PORT}"

if command -v python3 >/dev/null 2>&1; then
  PYTHON_CMD=python3
elif command -v python >/dev/null 2>&1; then
  PYTHON_CMD=python
else
  echo "ERRO: Python 3.10 ou superior nao foi encontrado."
  exit 1
fi

"$PYTHON_CMD" -c 'import sys; raise SystemExit(0 if sys.version_info >= (3, 10) else 1)' || {
  echo "ERRO: instale Python 3.10 ou superior."
  exit 1
}

[ -f vendor/flask/__init__.py ] && [ -f vendor/werkzeug/__init__.py ] && [ -f vendor/openpyxl/__init__.py ] || {
  echo "ERRO: pasta vendor incompleta. Extraia novamente o ZIP completo."
  exit 1
}

echo "Iniciando Combinix Lovelace em $URL"
echo "Nenhum pacote sera instalado e nenhuma conexao com a internet e necessaria."
"$PYTHON_CMD" app.py
