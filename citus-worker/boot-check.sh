#!/bin/bash

set -e

COORDINATOR_SERVICE=${CITUS_COORDINATOR:=coordinator}
COORDINATOR_PORT=${CITUS_COORDINATOR:=5432}
MANAGER_SERVICE=${CITUS_MANAGER:=manager}
PG_USER=${POSTGRES_USER:=postgres}

echo "CITUS_COORDINATOR service set as: $COORDINATOR_SERVICE"
echo "CITUS_MANAGER service set as: $MANAGER"
echo "POSTGRES_USER set as: $PG_USER"

# make sure coordinator is ready to accept connections
COORDINATOR_IP=$(getent hosts tasks.$COORDINATOR_SERVICE)
until pg_isready -h $COORDINATOR_IP -p $COORDINATOR_PORT -U $PG_USER
do
  echo "Waiting for Citus coordinator from service $COORDINATOR_SERVICE"
  sleep 2
done

echo "Postgres coordinator node is ready in: $COORDINATOR_IP"

# make sure membership manager is ready 
until [[ $(getent hosts tasks.$MANAGER_SERVICE) ]]
do 
    echo "Waiting for membership manager from service $MANAGER_SERVICE"
    sleep 2
done 

MANAGER_IP=$(getent hosts tasks.$MANAGER_SERVICE)

echo "Membership manager is up in: $MANAGER_IP"

sleep 5

exec gosu postgres "/docker-entrypoint.sh" "postgres"