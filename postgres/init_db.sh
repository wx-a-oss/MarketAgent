#!/usr/bin/env bash
set -euo pipefail

: "${PGHOST:=localhost}"
: "${PGPORT:=5432}"
: "${PGUSER:=market_agent}"
: "${PGDATABASE:=market_agent}"
: "${PGPASSWORD:=market_agent_password}"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BOOTSTRAP_BASE_SCHEMA="${BOOTSTRAP_BASE_SCHEMA:-0}"

if [ "${BOOTSTRAP_BASE_SCHEMA}" = "1" ]; then
  PGGSSENCMODE=disable PGPASSWORD="${PGPASSWORD}" \
  psql "host=${PGHOST} port=${PGPORT} user=${PGUSER} dbname=${PGDATABASE}" \
    -f "${SCRIPT_DIR}/init.sql"
fi

if [ -d "${SCRIPT_DIR}/migrations" ]; then
  for migration in "${SCRIPT_DIR}"/migrations/*.sql; do
    [ -e "${migration}" ] || continue
    echo "Applying migration: ${migration}"
    PGGSSENCMODE=disable PGPASSWORD="${PGPASSWORD}" \
    psql "host=${PGHOST} port=${PGPORT} user=${PGUSER} dbname=${PGDATABASE}" \
      -f "${migration}"
  done
fi
