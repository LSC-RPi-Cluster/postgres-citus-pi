#!/bin/sh

function wait_for_coordinator()
{
    local server=$1
    local port=$2

    let i=1

    nc -z $server $port
    nc_result=$?

    until [ $nc_result -eq 0 ]; do
      echo "Trying connect to coordinator: ${server}:${port}..."
      echo "Coordinator ${server}:${port} is not available yet"
      let "i++"
      sleep 2

      nc -z $server $port
      nc_result=$?
    done

    echo "Coordinator ${server}:${port} is available!"
}

COORDINATOR_SERVICE=${CITUS_COORDINATOR:=coordinator}
COORDINATOR_PORT=${COORDINATOR_PORT:=5432}
PG_USER=${POSTGRES_USER:=postgres}

echo "CITUS_COORDINATOR service set as: $COORDINATOR_SERVICE"
echo "POSTGRES_USER set as: $PG_USER"

# wait until coordinator service ip is reachable
until [[ "$(getent hosts tasks.$COORDINATOR_SERVICE)" ]]
do 
    echo "Waiting for Coordinator node boot"
    sleep 2
done 

COORDINATOR_IP=$(getent hosts tasks.$COORDINATOR_SERVICE | awk '{ print $1}')
echo "Citus coordinator node ip: $COORDINATOR_IP"

# make sure coordinator is ready to accept connections
wait_for_coordinator "$COORDINATOR_IP" "$COORDINATOR_PORT"

echo "Starting membership manager..."

