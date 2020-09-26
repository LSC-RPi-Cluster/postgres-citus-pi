#!/bin/sh

set -e

MASTER=${CITUS_MASTER:=master}
PG_USER=${POSTGRES_USER:=postgres}

echo "CITUS_MASTER service set as: $CITUS_MASTER"
echo "POSTGRES_USER set as: $POSTGRES_USER"

# make sure master is ready to accept connections
until pg_isready -h $MASTER -p 5432 -U $PG_USER
do
  echo "Waiting for master node..."
  sleep 2
done

echo "Postgres master node is ready in: $MASTER"
echo "Starting membership manager..."

