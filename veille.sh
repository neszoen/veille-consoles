#!/usr/bin/env bash
# Lance la veille consoles rétro sur Chromebook (mode Linux), Linux, Mac ou Codespaces.
# Utilisation : ./veille.sh
set -e
cd "$(dirname "$0")"

if [ ! -x .venv/bin/python ]; then
  echo
  echo "  Première ouverture : préparation de Python, patiente une minute..."
  if ! python3 -m venv .venv; then
    echo
    echo "  Python n'est pas prêt. Lance d'abord :"
    echo "    sudo apt update && sudo apt install -y python3 python3-venv"
    exit 1
  fi
fi

if ! cmp -s requirements.txt .venv/requirements.installed; then
  echo "  Installation des composants nécessaires..."
  .venv/bin/python -m pip install --disable-pip-version-check -q -r requirements.txt
  cp requirements.txt .venv/requirements.installed
fi

if [ "$1" = "menu" ] || [ "$CODESPACES" = "true" ]; then  # Codespaces : pas de fenêtre possible
  exec .venv/bin/python -m veille --menu
fi
exec .venv/bin/python -m veille --app "$@"
