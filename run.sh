#!/usr/bin/env bash
# Воспроизводимый запуск одним файлом: окружение, зависимости, фронтенд, сервер.
# Настройки — в .env (шаблон .env.example). Порт: ./run.sh [порт], по умолчанию 8021.
set -euo pipefail
cd "$(dirname "$0")"

PORT="${1:-8021}"
PYTHON="backend/.venv/bin/python"
[ -x "$PYTHON" ] || PYTHON="backend/.venv/Scripts/python.exe"

if [ ! -x "$PYTHON" ]; then
  echo "[1/4] Создаю окружение backend/.venv"
  python3.11 -m venv backend/.venv 2>/dev/null || python3 -m venv backend/.venv
  PYTHON="backend/.venv/bin/python"; [ -x "$PYTHON" ] || PYTHON="backend/.venv/Scripts/python.exe"
  "$PYTHON" -m pip install --quiet --upgrade pip
fi
echo "[2/4] Зависимости бэкенда"
"$PYTHON" -m pip install --quiet -r backend/requirements.txt
"$PYTHON" -m pip install --quiet -e backend --no-deps

if [ ! -f .env ]; then
  echo "[!] Файла .env нет — копирую .env.example; модель выключена, пока не заполните SD_LLM_*"
  cp .env.example .env
fi

echo "[3/4] Фронтенд"
# npm читает package.json из текущего каталога, а не из --prefix.
[ -d frontend/node_modules ] || (cd frontend && npm install)
(cd frontend && npm run build)

echo "[4/4] Сервер: http://127.0.0.1:${PORT}/  (Ctrl+C — остановить)"
exec "$PYTHON" -m uvicorn sd.api:app --host 127.0.0.1 --port "$PORT"
