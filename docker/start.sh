#!/bin/bash
set -euo pipefail

PGDATA=/var/lib/postgresql/data
PGBIN=/usr/lib/postgresql/15/bin
DB_USER="${DB_USER:-postgres}"
DB_PASSWORD="${DB_PASSWORD:-postgres}"

pg_start() { su - postgres -c "$PGBIN/pg_ctl -D $PGDATA -w start"; }
pg_stop()  { su - postgres -c "$PGBIN/pg_ctl -D $PGDATA -m fast -w stop"; }

# Ensure directories exist and have proper permissions
mkdir -p /var/log/supervisor /var/run/postgresql "$PGDATA" /var/lib/redis
chown -R postgres:postgres /var/run/postgresql "$PGDATA"
chown -R redis:redis /var/lib/redis
chmod 2775 /var/run/postgresql

# Initialize Postgres if data directory is empty
if [ -z "$(ls -A "$PGDATA")" ]; then
    echo "Initializing Postgres database..."
    su - postgres -c "$PGBIN/initdb -D $PGDATA"

    # Enable TimescaleDB in postgresql.conf
    echo "shared_preload_libraries = 'timescaledb'" >> "$PGDATA/postgresql.conf"

    # Restrict connection access to local loopback (in-container)
    echo "listen_addresses = '127.0.0.1,localhost'" >> "$PGDATA/postgresql.conf"
    echo "host all all 127.0.0.1/32 md5" >> "$PGDATA/pg_hba.conf"
    echo "host all all ::1/128 md5" >> "$PGDATA/pg_hba.conf"

    pg_start
    # Values travel as psql variables (:"name" quotes an identifier, :'name' a literal), so a
    # password containing quotes cannot break or inject into the SQL. The app role owns its
    # database but is not a superuser.
    runuser -u postgres -- psql -v ON_ERROR_STOP=1 -v app_user="$DB_USER" -v app_pass="$DB_PASSWORD" <<'SQL'
SELECT format('CREATE ROLE %I LOGIN PASSWORD %L', :'app_user', :'app_pass')
WHERE NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = :'app_user') \gexec
ALTER ROLE :"app_user" WITH PASSWORD :'app_pass';
CREATE DATABASE "NexusQuantDB" OWNER :"app_user";
SQL
    runuser -u postgres -- psql -v ON_ERROR_STOP=1 -d NexusQuantDB -c "CREATE EXTENSION IF NOT EXISTS timescaledb CASCADE;"
    pg_stop
fi

# Force locale fix in existing postgresql.conf if it exists
if [ -f "$PGDATA/postgresql.conf" ]; then
    echo "Fixing locales in postgresql.conf..."
    sed -i "s/lc_messages = 'en_US.utf8'/lc_messages = 'C.UTF-8'/g" "$PGDATA/postgresql.conf"
    sed -i "s/lc_monetary = 'en_US.utf8'/lc_monetary = 'C.UTF-8'/g" "$PGDATA/postgresql.conf"
    sed -i "s/lc_numeric = 'en_US.utf8'/lc_numeric = 'C.UTF-8'/g" "$PGDATA/postgresql.conf"
    sed -i "s/lc_time = 'en_US.utf8'/lc_time = 'C.UTF-8'/g" "$PGDATA/postgresql.conf"
fi

# Apply schema migrations on every start (migrate.py skips scripts already applied), so new
# migrations reach existing volumes too. A failed migration stops the container.
echo "Applying schema migrations..."
pg_start
if ! python3 /app/scripts/migrate.py; then
    echo "Schema migration failed; refusing to start." >&2
    pg_stop
    exit 1
fi
pg_stop

echo "Starting supervisord..."
exec supervisord -c /supervisord.conf
