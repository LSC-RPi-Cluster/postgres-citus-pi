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


# Get database credentials from the container environment variables 
def get_db_credentials():
    postgres_pass = environ.get('POSTGRES_PASSWORD', '')
    postgres_user = environ.get('POSTGRES_USER', 'postgres')
    postgres_db = environ.get('POSTGRES_DB', postgres_user)

    return {"dbname": postgres_db, "user": postgres_user, "password": postgres_pass}


# Check if the postgres node is ready to connections
def connection_is_ready(host, port):
    conn_credentials = get_db_credentials()
    conn_credentials['host'] = host
    conn_credentials['port'] = port

    try:
        conn = psycopg2.connect(**conn_credentials)
        conn.close()
        return True

    except:
        return False


# Get a list of active worker nodes in the cluster
def get_active_workers(conn):
    cur = conn.cursor()
    cur.execute("""SELECT node_name FROM citus_get_active_worker_nodes();""")

    rows = cur.fetchall()

    return [node[0] for node in rows]


# Adds a host to the cluster
def add_worker(conn, host, port=5432):
    print(f"Adding {host} node", file=stderr)

    while not connection_is_ready(host, port):
        print(f"The worker ({host}) still not accepting connections, trying again")
        sleep(1)

    cur = conn.cursor()    

    cur.execute(f"""SELECT citus_add_node('{host}', {port});""")
    print(f"Worker {host} added!", file=stderr)

# Rebalance the shards over the worker nodes
def rebalance_shards(conn):
    cur = conn.cursor()

    print("Rebalancing shards", file=stderr)
    cur.execute("""SELECT rebalance_table_shards();""")


# Removes all placements from a host and removes it from the cluster
def remove_worker(conn, host, port=5432):
    cur = conn.cursor()

    print(f"Removing {host} node", file=stderr)
    cur.execute(f"""SELECT citus_remove_node('{host}', {port});""")


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
def connect_to_coordinator(host, port=5432):
    conn_credentials = get_db_credentials()
    conn_credentials['host'] = host
    conn_credentials['port'] = port

    while not connection_is_ready(host, port):
        print(f"Could not connect to {host}, trying again in 1 second")
        sleep(1)
    
    conn = psycopg2.connect(**conn_credentials)
    conn.autocommit = True

    print(f"connected to {host}", file=stderr)

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


# Get the service object from docker swarm stack
def get_swarm_service(client, service_name, swarm_stack, label_role):
    filters = {
        'label': [
            f"com.docker.stack.namespace={swarm_stack}",
            f"com.citusdata.role={label_role}"
        ],
        'name': f"{swarm_stack}_{service_name}"
    }

    return client.services.list(filters=filters)[0]


# Main logic loop for the manager
def docker_checker():
    client = docker.DockerClient(base_url='unix:///var/run/docker.sock')

    # Introspect the stack namespace used by the citus swarm cluster
    manager_hostname = environ['HOSTNAME']
    worker_service_name = environ.get('WORKER_SERVICE', 'worker')
    coordinator_service_name = environ.get('COORDINATOR_SERVICE', 'coordinator')

    manager_container = client.containers.get(manager_hostname)
    swarm_stack = manager_container.labels['com.docker.stack.namespace']

    print(f"Found swarm stack: {swarm_stack}", file=stderr)

    # Get the coordinator connection host ip
    coordinator_service = get_swarm_service(client, coordinator_service_name, swarm_stack, "Coordinator")
    coordinator_ip = get_healthy_tasks_ip(coordinator_service)[0]

    # Creates the necessary connection to make the sql calls if the coordinator is ready
    conn = connect_to_coordinator(coordinator_ip)

    # Filter only citus workers services in swarm stack
    worker_service = get_swarm_service(client, worker_service_name, swarm_stack, "Worker")

    # Update the initial cluster workers number
    update_cluster(conn, worker_service)

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
