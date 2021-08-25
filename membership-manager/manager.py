#!/usr/bin/env python3

# ----------------------------------------------------------------------------------------
#
# manager.py
#
# Created to manage add/remove worker operations in Citus Docker Swarm Cluster.
#
# ----------------------------------------------------------------------------------------
import docker
from os import environ
import psycopg2
import signal
from sys import exit, stderr
from time import sleep


# Get a list of active worker nodes in the cluster
def get_active_workers(conn):
    cur = conn.cursor()
    cur.execute("""SELECT node_name FROM citus_get_active_worker_nodes();""")

    rows = cur.fetchall()

    return [node[0] for node in rows]


# Adds a host to the cluster
def add_worker(conn, host):
    cur = conn.cursor()
    worker_dict = ({'host': host, 'port': 5432})

    print(f"Adding {host} node", file=stderr)
    cur.execute("""SELECT citus_add_node(%(host)s, %(port)s)""", worker_dict)


# Rebalance the shards over the worker nodes
def rebalance_shards(conn):
    cur = conn.cursor()

    print("Rebalancing shards", file=stderr)
    cur.execute("""SELECT rebalance_table_shards();""")


# Removes all placements from a host and removes it from the cluster
def remove_worker(conn, host):
    cur = conn.cursor()
    worker_dict = ({'host': host, 'port': 5432})

    print(f"Removing {host} node", file=stderr)
    cur.execute("""DELETE FROM pg_dist_placement WHERE groupid = (SELECT groupid FROM 
                   pg_dist_node WHERE nodename = %(host)s AND nodeport = %(port)s LIMIT 1);
                   SELECT citus_remove_node(%(host)s, %(port)s)""", worker_dict)


# Return a list of tasks with desireState = running
def get_healthy_tasks_ip(service):
    # Wait a while for service tasks status update
    sleep(5)

    healthy_tasks_ip = []
    for task in service.tasks():
        if task['DesiredState'] == 'running':
            task_ip = task['NetworksAttachments'][0]['Addresses'][0]
            healthy_tasks_ip.append(task_ip.split('/', 1)[0])

    return healthy_tasks_ip


# Connect_to_coordinator method is used to connect to citus coordinator at the start-up.
# Citus docker-compose has a dependency mapping as worker -> manager -> coordinator.
# This means that whenever manager is created, coordinator is already there, but it may
# not be ready to accept connections. We'll try until we can create a connection.
def connect_to_coordinator():
    citus_host = environ.get('CITUS_HOST', 'coordinator')
    postgres_pass = environ.get('POSTGRES_PASSWORD', '')
    postgres_user = environ.get('POSTGRES_USER', 'postgres')
    postgres_db = environ.get('POSTGRES_DB', postgres_user)

    conn = None
    while conn is None:
        try:
            conn = psycopg2.connect(
                f"dbname={postgres_db} user={postgres_user} host={citus_host} password={postgres_pass}")
        except psycopg2.OperationalError as error:
            print(
                f"Could not connect to {citus_host}, trying again in 1 second")
            sleep(1)
        except (Exception, psycopg2.Error) as error:
            raise error

    conn.autocommit = True

    print(f"connected to {citus_host}", file=stderr)

    return conn


# Checks the tasks status in the service and updates workers in the citus cluster
def update_cluster(conn, service):
    healthy_tasks_ip = get_healthy_tasks_ip(service)
    active_workers = get_active_workers(conn)

    new_nodes = list(set(healthy_tasks_ip) - set(active_workers))

    if new_nodes:
        for node in new_nodes:
            add_worker(conn, node)
        rebalance_shards(conn)

    down_nodes = list(set(active_workers) - set(healthy_tasks_ip))

    if down_nodes:
        for node in down_nodes:
            remove_worker(conn, node)
        rebalance_shards(conn)


# Main logic loop for the manager
def docker_checker():
    client = docker.DockerClient(base_url='unix:///var/run/docker.sock')

    # Creates the necessary connection to make the sql calls if the coordinator is ready
    conn = connect_to_coordinator()

    manager_hostname = environ['HOSTNAME']
    worker_service_name = environ.get('WORKER_SERVICE', 'worker')

    # Introspect the stack namespace used by the citus swarm cluster
    manager_container = client.containers.get(manager_hostname)
    swarm_stack = manager_container.labels['com.docker.stack.namespace']

    print(f"Found swarm stack: {swarm_stack}", file=stderr)

    # Filter only citus workers services in swarm stack
    filters = {
        'label': [
            f"com.docker.stack.namespace={swarm_stack}",
            "com.citusdata.role=Worker"
        ],
        'name': f"{swarm_stack}_{worker_service_name}"
    }

    worker_service = client.services.list(filters=filters)[0]

    # Consume docker events
    print('Listening for events...', file=stderr)

    for event in client.events(decode=True):
        service_id = event['Actor']['ID']
        actor_attrs = event['Actor']['Attributes']

        # Get service scale events
        if (event['Type'] == "service") and (service_id == worker_service.id):
            if "replicas.new" in actor_attrs:
                update_cluster(conn, worker_service)

        # Get node down events
        if (event['Type'] == "node") and ("state.new" in actor_attrs):
            if actor_attrs['state.new'] == "down":
                update_cluster(conn, worker_service)


# Implemented to make Docker exit faster (it sends sigterm)
def graceful_shutdown(signal, frame):
    print('shutting down...', file=stderr)
    exit(0)


def main():
    signal.signal(signal.SIGTERM, graceful_shutdown)
    docker_checker()


if __name__ == '__main__':
    main()
