#!/usr/bin/env bash

set -euo pipefail

DB_USER=${DB_USER:-ec_user}
DB_PASS=${DB_PASS:-change_me}
DB_NAME=${DB_NAME:-ecard_db}
DB_HOST=${DB_HOST:-localhost}
DB_PORT=${DB_PORT:-5432}

echo "Creating role '${DB_USER}' and database '${DB_NAME}' on ${DB_HOST}:${DB_PORT}..."

psql -v ON_ERROR_STOP=1 --host="${DB_HOST}" --port="${DB_PORT}" --username="${PGUSER:-postgres}" <<SQL
DO $$
BEGIN
    IF NOT EXISTS (SELECT FROM pg_catalog.pg_roles WHERE rolname = '${DB_USER}') THEN
        CREATE ROLE ${DB_USER} LOGIN PASSWORD '${DB_PASS}';
    END IF;
END;
$$;

DO $$
BEGIN
    IF NOT EXISTS (SELECT FROM pg_database WHERE datname = '${DB_NAME}') THEN
        CREATE DATABASE ${DB_NAME} OWNER ${DB_USER};
    END IF;
END;
$$;

GRANT ALL PRIVILEGES ON DATABASE ${DB_NAME} TO ${DB_USER};
SQL

echo "Database bootstrap complete. Configure DATABASE_URL=postgres://${DB_USER}:${DB_PASS}@${DB_HOST}:${DB_PORT}/${DB_NAME}"
