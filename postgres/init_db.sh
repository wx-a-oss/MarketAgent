#!/usr/bin/env bash
set -euo pipefail

: "${PGHOST:=localhost}"
: "${PGPORT:=5432}"
: "${PGUSER:=market_agent}"
: "${PGDATABASE:=market_agent}"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

psql "host=${PGHOST} port=${PGPORT} user=${PGUSER} dbname=${PGDATABASE}" \
  -f "${SCRIPT_DIR}/init.sql"
