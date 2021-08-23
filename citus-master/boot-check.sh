#!/bin/bash

set -e

COORDINATOR=${CITUS_COORDINATOR:=coordinator}
MANAGER=${CITUS_MANAGER:=manager}
PG_USER=${POSTGRES_USER:=postgres}
COORDINATOR_PORT=${CITUS_COORDINATOR:=coordinator}

echo "CITUS_COORDINATOR service set as: $COORDINATOR"
echo "POSTGRES_USER set as: $PG_USER"
echo "CITUS_MANAGER service set as: $MANAGER"

# make sure coordinator is ready to accept connections
COORDINATOR_IP=$(getent hosts tasks.$COORDINATOR)
until pg_isready -h $COORDINATOR_IP -p 5432 -U $PG_USER
do
  echo "Waiting for Citus coordinator from service $COORDINATOR"
  sleep 2
done

echo "Postgres coordinator node is ready in: $COORDINATOR_IP"

# make sure membership manager is ready 

until [[ $(getent hosts tasks.$MANAGER) ]]
do 
    echo "Waiting for membership manager from service $MANAGER"
    sleep 2
done 

MANAGER_IP=$(getent hosts tasks.$MANAGER)

echo "Membership manager is up in: $MANAGER_IP"

sleep 5

exec gosu postgres "/docker-entrypoint.sh" "postgres"