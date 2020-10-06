#!/usr/bin/env python3

# ----------------------------------------------------------------------------------------
#
# manager.py
#
# Created to manage add/remove worker operations in Citus docker-compose.
#
# ----------------------------------------------------------------------------------------
import docker
from os import environ
import os
import psycopg2
import signal
from sys import exit, stderr
from time import sleep

# get a list of worker nodes actives in the cluster
def get_active_workers(conn):
    cur = conn.cursor()
    cur.execute("""SELECT node_name FROM master_get_active_worker_nodes();""")

    rows = cur.fetchall()

    return [node[0] for node in rows]


# adds a host to the cluster
def add_worker(conn, host):
    cur = conn.cursor()
    worker_dict = ({'host': host, 'port': 5432})

    print("adding %s" % host, file=stderr)
    cur.execute("""SELECT master_add_node(%(host)s, %(port)s)""", worker_dict)


# removes all placements from a host and removes it from the cluster
def remove_worker(conn, host):
    cur = conn.cursor()
    worker_dict = ({'host': host, 'port': 5432})

    print("removing %s" % host, file=stderr)
    cur.execute("""DELETE FROM pg_dist_placement WHERE groupid = (SELECT groupid FROM 
                   pg_dist_node WHERE nodename = %(host)s AND nodeport = %(port)s LIMIT 1);
                   SELECT master_remove_node(%(host)s, %(port)s)""", worker_dict)


# connect_to_master method is used to connect to master coordinator at the start-up.
# Citus docker-compose has a dependency mapping as worker -> manager -> master.
# This means that whenever manager is created, master is already there, but it may
# not be ready to accept connections. We'll try until we can create a connection.
def connect_to_master():

    master_hostname = environ.get('CITUS_HOST', 'master')
    postgres_pass   = environ.get('POSTGRES_PASSWORD', '')
    postgres_user   = environ.get('POSTGRES_USER', 'postgres')
    postgres_db     = environ.get('POSTGRES_DB', postgres_user)
    citus_host      = master_hostname#find_host(master_hostname)[0][0]

    print("master hostname: "+master_hostname)

    conn = None
    while conn is None:
        try:
            conn = psycopg2.connect("dbname=%s user=%s host=%s password=%s" %
                                    (postgres_db, postgres_user, citus_host, postgres_pass))
        except psycopg2.OperationalError as error:
            print("Could not connect to %s, trying again in 1 second" % citus_host)
            sleep(1)
        except (Exception, psycopg2.Error) as error:
            raise error
        
    conn.autocommit = True

    print("connected to %s" % citus_host, file=stderr)

    return conn


# return a list of tasks with desireState = running
def get_healthy_tasks(service):

    # wait a while for service tasks status update
    sleep(5) 

    healthy = []
    for task in service.tasks():
        if task['DesiredState'] == 'running':
            task_ip = task['NetworksAttachments'][0]['Addresses'][0]
            healthy.append(task_ip.split('/', 1)[0])

    return healthy

# checks the status of tasks in the service and updates workers in the citus cluster
def update_cluster(conn, service):
    healthy_tasks = get_healthy_tasks(service)
    active_workers = get_active_workers(conn)

    new_nodes = list(set(healthy_tasks)-set(active_workers))

    if new_nodes:
        for node in new_nodes:
            add_worker(conn, node)

    down_nodes = list(set(active_workers)-set(healthy_tasks))

    if down_nodes:
        for node in down_nodes:
            remove_worker(conn, node)


# main logic loop for the manager
def docker_checker():
    client = docker.DockerClient(base_url='unix:///var/run/docker.sock')
   
    # creates the necessary connection to make the sql calls if the master is ready
    conn = connect_to_master()

    # introspect the stack namespace used by this citus cluster
    my_hostname = environ['HOSTNAME']
    this_container = client.containers.get(my_hostname)
    swarm_stack = this_container.labels['com.docker.stack.namespace']

    # Filter only citus workers services in swarm stack
    print("Found swarm stack: %s" % swarm_stack, file=stderr)
    filters = {'label': ["com.docker.stack.namespace=%s" % swarm_stack,
                         "com.citusdata.role=Worker"]}

    services = client.services.list(filters=filters)

    # consume docker events
    print('Listening for events...', file=stderr)
    
    for event in client.events(decode=True):
        service_id = event['Actor']['ID']
        actor_attrs = event['Actor']['Attributes'] 

        # get service scale events
        if (event['Type'] == "service") and (service_id == services[0].id):
            if ("replicas.new" in actor_attrs):
                update_cluster(conn, services[0])

        # get node down events
        if (event['Type'] == "node") and ("state.new" in actor_attrs):
            if (actor_attrs['state.new'] == "down"):
                update_cluster(conn, services[0])

# implemented to make Docker exit faster (it sends sigterm)
def graceful_shutdown(signal, frame):
    print('shutting down...', file=stderr)
    exit(0)


def main():
    signal.signal(signal.SIGTERM, graceful_shutdown)
    docker_checker()


if __name__ == '__main__':
    main()
