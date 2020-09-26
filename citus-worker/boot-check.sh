#!/bin/bash

set -e

MASTER=${CITUS_MASTER:=master}
MANAGER=${CITUS_MANAGER:=manager}
PG_USER=${POSTGRES_USER:=postgres}

echo "CITUS_MASTER service set as: $CITUS_MASTER"
echo "POSTGRES_USER set as: $POSTGRES_USER"
echo "CITUS_MANAGER service set as: $CITUS_MANAGER"

# make sure master is ready to accept connections
until pg_isready -h $MASTER -p 5432 -U $PG_USER
do
  echo "Waiting for master node..."
  sleep 2
done

echo "Postgres master node is ready in: $MASTER"

# make sure membership manager is ready 

until [ $(getent hosts tasks.$MANAGER) ]
do 
    echo "Waiting for membership manager..."
    sleep 2
done 

MEMBERSHIP_MANAGER=$(getent hosts tasks.$MANAGER)

echo "Membership manager is up in: $MEMBERSHIP_MANAGER"

sleep 5

exec gosu postgres "/docker-entrypoint.sh" "postgres"