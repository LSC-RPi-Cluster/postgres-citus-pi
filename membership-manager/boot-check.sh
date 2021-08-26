#!/bin/sh

set -e

COORDINATOR_SERVICE=${CITUS_COORDINATOR:=coordinator}
COORDINATOR_PORT=${CITUS_COORDINATOR:=5432}
PG_USER=${POSTGRES_USER:=postgres}

echo "CITUS_COORDINATOR service set as: $COORDINATOR_SERVICE"
echo "POSTGRES_USER set as: $PG_USER"

# make sure coordinator is ready to accept connections
COORDINATOR_IP=$(getent hosts tasks.$COORDINATOR_SERVICE)
while ! nc -z $COORDINATOR_IP $COORDINATOR_PORT
do
  echo "Waiting for Citus coordinator from service $COORDINATOR_SERVICE"
  sleep 2
done

echo "Citus coordinator node is ready in: $COORDINATOR_IP"
echo "Starting membership manager..."

