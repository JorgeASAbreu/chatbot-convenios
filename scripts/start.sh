#!/usr/bin/env bash
set -euo pipefail
test -d .venv || { echo "Crie o ambiente: python3.12 -m venv .venv"; exit 1; }
test -f .env || { echo "Copie .env.example para .env e configure DATABASE_URL"; exit 1; }
source .venv/bin/activate
alembic upgrade head
streamlit run app/main.py --server.address "${STREAMLIT_HOST:-0.0.0.0}" --server.port "${STREAMLIT_PORT:-8501}"
