#!/usr/bin/env bash
set -euo pipefail

tmp_db="$(mktemp /tmp/biosignal-migrations-XXXXXX.db)"
cleanup() {
  rm -f "$tmp_db"
}
trap cleanup EXIT

DB_PATH="$tmp_db" alembic upgrade head
DB_PATH="$tmp_db" alembic check
