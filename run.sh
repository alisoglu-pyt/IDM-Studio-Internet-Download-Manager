#!/usr/bin/env bash
# IDM Studio'yu proje klasöründen başlatır.
set -e
cd "$(dirname "$0")"
exec python3 main.py "$@"
