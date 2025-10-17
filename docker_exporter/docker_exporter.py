from prometheus_client import start_http_server, Gauge
from concurrent.futures import ThreadPoolExecutor, as_completed
import docker
import time
from datetime import datetime

# Connect to the Docker daemon via TCP on Windows (Docker exporter running inside a container)
client = docker.DockerClient(base_url="tcp://host.docker.internal:2375")
# Connect to the Docker daemon via TCP on Windows (Docker exporter running locally)
# client = docker.DockerClient(base_url="tcp://localhost:2375")

container_state_gauge = Gauge(
    'docker_container_state',
    'State of Docker containers (1=running, 0=not running)',
    ['name'])

container_cpu_used_gauge = Gauge(
    'docker_container_cpu_percent',
    'CPU usage percentage per container',
    ['name']
)
total_cpu_used_gauge = Gauge(
    'docker_total_cpu_used_percent',
    'Total CPU usage percentage for all running containers'
)
total_cpu_available_gauge = Gauge(
    'docker_total_cpu_available_percent',
    'Total available CPU percentage on the Docker host (100% * nb_cores)'
)

container_memory_used_gauge = Gauge(
    'docker_container_memory_used_mb',
    'Memory usage in megabytes per container',
    ['name']
)
total_memory_used_gauge = Gauge(
    'docker_total_memory_used_mb',
    'Total memory usage in megabytes for all running containers'
)
total_memory_available_gauge = Gauge(
    'docker_total_memory_available_mb',
    'Total memory available in megabytes on the Docker host'
)

def get_containers_states(containers):
    container_state_gauge.clear()

    # Get the container state: 1=Running, 0=Exited
    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] Start fetching container states")
    for c in containers:
        if c.status == "running":
            state = 1
        elif c.status == "created":
            state = 0.5
        else:
            state = 0
        container_state_gauge.labels(name=c.name).set(state)
    return "done"

def get_pourcent_cpu_available_on_server(containers):
    # Get the total number of CPU cores available on the server (for example, 600% for 6 CPU cores)
    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] Start counting the number of CPUs on the server")
    pourcent_total_cpu_available = 0
    if containers:
        stats = containers[0].stats(stream=False)
        try:
            pourcent_total_cpu_available = int(stats["cpu_stats"]["online_cpus"] * 100)
            print("Theoretical CPU cores on the server:", pourcent_total_cpu_available, "%")
        except Exception as e:
            print("ERROR :", e)
            pourcent_total_cpu_available = 0
        total_cpu_available_gauge.set(pourcent_total_cpu_available)
        return pourcent_total_cpu_available

def get_cpu_nanoseconds_used_by_server(containers):
    # Get the total CPU nanoseconds used by the server between two snapshots
    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] Start counting CPU nanoseconds used by the server")
    delta_nanosecs_serveur = 0
    if containers:
        stats = containers[0].stats(stream=False)
        try:
            # Total CPU nanoseconds used by the server (all containers) during the previous measurement
            last_nanosecs_cpu_serveur = stats["precpu_stats"]["system_cpu_usage"]
            # Total CPU nanoseconds used by the server (all containers) at the current moment
            current_nanosecs_cpu_serveur = stats["cpu_stats"]["system_cpu_usage"]
            # Difference = CPU nanoseconds consumed by the server between the two measurements
            delta_nanosecs_serveur = current_nanosecs_cpu_serveur - last_nanosecs_cpu_serveur
            print(f"Actual CPU nanoseconds consumption by the server: {delta_nanosecs_serveur}")
        except Exception as e:
            print("ERROR :", e)
            delta_nanosecs_serveur = 0
        return delta_nanosecs_serveur

def get_total_memory_available_on_server(containers):
    # Get the total memory available on the server
    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] Get total memory in megabytes available on the server")
    total_memory_available_mb = 0
    if containers:
        stats = containers[0].stats(stream=False)
        try:
            # Number of bytes(octets) used by the server
            total_memory_available_bytes = stats["memory_stats"]["limit"]
            # Number of megabytes used by the server
            total_memory_available_mb = total_memory_available_bytes / (1024 * 1024)
            # Round to two decimal places (x.xx MB)
            total_memory_available_mb = round(total_memory_available_mb, 2)
            print(f"Total Memory available on the server: {total_memory_available_mb} MegaBytes")

            total_memory_available_gauge.set(total_memory_available_mb)
        except Exception as e:
            total_memory_available_mb = 0
    else:
        total_memory_available_mb = 0
    return total_memory_available_mb

def get_pourcent_cpu_usage_for_one_container(c, pourcent_cpu_available_on_server, cpu_nanoseconds_used_by_server):
    try:
        stats = c.stats(stream=False)
        # Total CPU nanoseconds used by one container during the previous measurement
        last_nanosecs_used_by_container = stats["precpu_stats"]["cpu_usage"]["total_usage"]
        # Total CPU nanoseconds used by one container at the current moment
        current_nanosecs_used_by_container = stats["cpu_stats"]["cpu_usage"]["total_usage"]
        # Difference = CPU nanoseconds consumed by one container between the two measurements
        nanosecs_used_by_container = current_nanosecs_used_by_container - last_nanosecs_used_by_container

        if cpu_nanoseconds_used_by_server > 0 and nanosecs_used_by_container > 0:
            # Convert CPU nanoseconds consumed by a container into a percentage of available CPU
            cpu_percent = (nanosecs_used_by_container / cpu_nanoseconds_used_by_server) * pourcent_cpu_available_on_server
            cpu_percent = round(cpu_percent, 2)
            container_cpu_used_gauge.labels(name=c.name).set(cpu_percent)
            print(f"CPU {c.name}: {nanosecs_used_by_container} ns = {cpu_percent}% / {pourcent_cpu_available_on_server} available")
            return cpu_percent
        else:
            container_cpu_used_gauge.labels(name=c.name).set(0)
            return 0.0
    except Exception as e:
        print(f"ERROR {c.name}: {e}")
        container_cpu_used_gauge.labels(name=c.name).set(0)
        return 0.0

def get_cpu_pourcent_used_by_each_container(containers, pourcent_cpu_available_on_server, cpu_nanoseconds_used_by_server):
    # Get the total CPU nanoseconds used by each container between two snapshots, then calculate the usage percentage
    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] Start fetching CPU nanoseconds usage per container")
    pourcent_cpu_used_by_all_containers = 0.0
    cpu_result_containeurs = []
    with ThreadPoolExecutor(max_workers=50) as executor:
        for c in containers:
            if c.status == "running" or c.status == "created":
                cpu_result_containeurs.append(
                    executor.submit(get_pourcent_cpu_usage_for_one_container, c, pourcent_cpu_available_on_server, cpu_nanoseconds_used_by_server))
            else:
                # Remove metrics for stopped containers
                container_cpu_used_gauge.remove(c.name)

        # Get results from all containers
        for cpu_result_containeur in as_completed(cpu_result_containeurs):
            pourcent_cpu_used_by_all_containers += cpu_result_containeur.result()
        # Calculate total CPU usage across all containers
        print(f"Total % CPU used on serveur {round(pourcent_cpu_used_by_all_containers, 2)} %")
        total_cpu_used_gauge.set(round(pourcent_cpu_used_by_all_containers, 2))

def get_memory_usage_by_container(c, total_memory_mb_available_on_server):
    try:
        stats = c.stats(stream=False)
        # Number of bytes (octets) used by the container
        container_memory_used_bytes = stats["memory_stats"]["usage"]
        # Number of megabytes used by the container
        container_memory_used_mb = container_memory_used_bytes / (1024 * 1024)
        # Round to two decimal places (x.xx MB)
        container_memory_used_mb = round(container_memory_used_mb, 2)
        container_memory_used_gauge.labels(name=c.name).set(container_memory_used_mb)
        print(f"Memory {c.name} : {container_memory_used_mb} MB / {total_memory_mb_available_on_server} MB available")
        return container_memory_used_mb
    except Exception as e:
        print(f"ERROR Memory {c.name}: {e}")
        container_memory_used_gauge.labels(name=c.name).set(-1)
        return 0.0

def get_memory_used_for_each_container(containers, total_memory_mb_available_on_server):
    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] Start fetching memory usage per container")
    total_memory_used = 0.0
    memory_result_containeurs = []

    with ThreadPoolExecutor(max_workers=10) as executor:
        for c in containers:
            if c.status == "running":
                memory_result_containeurs.append(
                    executor.submit(get_memory_usage_by_container, c, total_memory_mb_available_on_server))
            else:
                # Remove metrics for stopped containers
                container_memory_used_gauge.remove(c.name)

        # Get results from all containers
        for memory_result_containeur in as_completed(memory_result_containeurs):
            total_memory_used += memory_result_containeur.result()
        # Calculate total Memory usage across all containers
        print(
            f"Total MegaBytes used on serveur {round(total_memory_used, 2)} MB / {total_memory_mb_available_on_server} MB available")
        total_memory_used_gauge.set(round(total_memory_used, 2))

def update_metrics():
    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] Start update metrics")
    containers = client.containers.list(all=True)

    with ThreadPoolExecutor(max_workers=50) as executor:
        # Launch independent tasks
        executor.submit(get_containers_states, containers)
        pourcent_cpu_available_on_server = executor.submit(get_pourcent_cpu_available_on_server, containers)
        cpu_nanoseconds_used_by_server = executor.submit(get_cpu_nanoseconds_used_by_server, containers)
        total_memory_mb_available_on_server = executor.submit(get_total_memory_available_on_server, containers)

        # Wait for CPU_available and CPU_nanoseconds_used to finish before running cpu_percent_used_by_each_container
        pourcent_cpu_available_on_server = pourcent_cpu_available_on_server.result()
        cpu_nanoseconds_used_by_server = cpu_nanoseconds_used_by_server.result()
        get_cpu_pourcent_used_by_each_container(containers, pourcent_cpu_available_on_server, cpu_nanoseconds_used_by_server)

        # Wait for total_memory_available_on_server to finish before running memory_used_for_each_container
        total_memory_mb_available_on_server = total_memory_mb_available_on_server.result()
        get_memory_used_for_each_container(containers, total_memory_mb_available_on_server)


def start_prometheus_client():
    # Prometheus HTTP server on port 8000
    start_http_server(8000)
    print("Serving metrics on http://localhost:8000/metrics")
    try:
        while True:
            update_metrics()
            time.sleep(1)
            print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] Alive")
    except KeyboardInterrupt:
        print("End prometheus_client")


if __name__ == '__main__':
    start_prometheus_client()
