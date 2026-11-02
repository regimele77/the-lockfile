#!/bin/sh
set -e

echo "Waiting for PostgreSQL at ${POSTGRES_HOST:-db}:${POSTGRES_PORT:-5432}..."
until python -c "import socket, os; host=os.environ.get('POSTGRES_HOST','db'); port=int(os.environ.get('POSTGRES_PORT','5432')); s=socket.create_connection((host, port), 2); s.close()"; do
  sleep 1
done
echo "PostgreSQL is available."

if [ "${RUN_MIGRATIONS:-1}" = "1" ]; then
  python manage.py migrate --noinput
fi

exec "$@"
