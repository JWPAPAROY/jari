#!/usr/bin/env bash
# 로컬에서 jari DB에 psql 접속: ./db.sh -f file.sql  또는 ./db.sh -c "select 1"
PSQL="${PSQL:-/c/Program Files/PostgreSQL/17/bin/psql.exe}"
export PGPASSWORD="${JARI_DB_PASSWORD:-$(cat /c/Users/knoww/.secrets/supabase-jari-db-password.txt)}" PGSSLMODE=require PGCLIENTENCODING=UTF8
exec "$PSQL" -h aws-0-ap-southeast-1.pooler.supabase.com -p 5432 -U postgres.weqtznraiderretvcwzp -d postgres -v ON_ERROR_STOP=1 "$@"
