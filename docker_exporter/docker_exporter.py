from prometheus_client import start_http_server, Gauge
from concurrent.futures import ThreadPoolExecutor, as_completed
import docker
import time
from datetime import datetime

# Connexion au daemon Docker via TCP sur Windows (docker exporter dans container)
client = docker.DockerClient(base_url="tcp://host.docker.internal:2375")
# Connexion au daemon Docker via TCP sur Windows (docker exporter en local)
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

def update_metrics():
    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] Start update metrics")
    containers = client.containers.list(all=True)
    container_state_gauge.clear()

    # Récupérer l'état du container: 1=Running, 0=Exited
    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] Start etat des containers")
    for c in containers:
        if c.status == "running":
            state = 1
        elif c.status == "created":
            state = 0.5
        else:
            state = 0
        container_state_gauge.labels(name=c.name).set(state)

    # Récupérer le nombre de coeurs CPU total disponible sur le serveur (600% pour 6 coeurs CPU)
    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] Start count number CPUs on serveur")
    pourcent_total_cpu_available = 0
    if containers:
        stats = containers[0].stats(stream=False)
        try:
            pourcent_total_cpu_available = int(stats["cpu_stats"]["online_cpus"] * 100)
            print(f"Coeurs CPU théorique du serveur :", pourcent_total_cpu_available, "%")
        except Exception as e:
            print("ERROR :", e)
            pourcent_total_cpu_available = 0
        total_cpu_available_gauge.set(pourcent_total_cpu_available)

    # Récupérer le nombre de nanosecondes de CPU total consommé par le serveur entre 2 snap
    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] Start count nanosecs used by serveur")
    delta_nanosecs_serveur = 0
    if containers:
        stats = containers[0].stats(stream=False)
        try:
            # Total nanosecs CPU utilisé par serveur (tous les conteneurs) lors de la mesure précédente
            last_nanosecs_cpu_serveur = stats["precpu_stats"]["system_cpu_usage"]
            # Total nanosecs CPU utilisé par serveur (tous les conteneurs) au moment présent
            current_nanosecs_cpu_serveur = stats["cpu_stats"]["system_cpu_usage"]
            # Différence = consommation nanosecs CPU du serveur entre les deux mesures
            delta_nanosecs_serveur = current_nanosecs_cpu_serveur - last_nanosecs_cpu_serveur
            print(f"Réel consommation nanosecs CPUs du serveur :", delta_nanosecs_serveur)
        except Exception as e:
            print("ERROR :", e)
            delta_nanosecs_serveur = 0


    def get_pourcent_cpu_usage_by_container(c, delta_nanosecs_serveur, pourcent_total_cpu_available):
        try:
            stats = c.stats(stream=False)
            last_ns = stats["precpu_stats"]["cpu_usage"]["total_usage"]
            current_ns = stats["cpu_stats"]["cpu_usage"]["total_usage"]
            delta_ns = current_ns - last_ns

            if delta_nanosecs_serveur > 0 and delta_ns > 0:
                cpu_percent = (delta_ns / delta_nanosecs_serveur) * pourcent_total_cpu_available
                cpu_percent = round(cpu_percent, 2)
                container_cpu_used_gauge.labels(name=c.name).set(cpu_percent)
                print(f"CPU {c.name}: {delta_ns} ns = {cpu_percent}% / {pourcent_total_cpu_available} available")
                return cpu_percent
            else:
                container_cpu_used_gauge.labels(name=c.name).set(0)
                return 0.0
        except Exception as e:
            print(f"ERROR {c.name}: {e}")
            container_cpu_used_gauge.labels(name=c.name).set(0)
            return 0.0

    # Récupérer le nombre de nanosecondes de CPU total consommé par chaque containeurs entre 2 snap, puis le % d'utilisation
    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] Start consommation nanosecs CPUs par containers")
    pourcent_cpu_used_by_all_containers = 0.0
    cpu_result_conteneurs = []
    with ThreadPoolExecutor(max_workers=50) as executor:
        for c in containers:
            if c.status == "running" or c.status == "created":
                cpu_result_conteneurs.append(executor.submit(get_pourcent_cpu_usage_by_container, c, delta_nanosecs_serveur, pourcent_total_cpu_available))
            else:
                # Supprimer les metrics des conteneurs arrêtés
                container_cpu_used_gauge.remove(c.name)

        # Récupération des résultats de tout les conteneurs
        for cpu_result_conteneur in as_completed(cpu_result_conteneurs):
            pourcent_cpu_used_by_all_containers += cpu_result_conteneur.result()
        # Calcul de l'utilisation de CPU total des conteneurs
        print(f"Total % CPU used on serveur {round(pourcent_cpu_used_by_all_containers, 2)} %")
        total_cpu_used_gauge.set(round(pourcent_cpu_used_by_all_containers, 2))


    # Récupérer la capacité de mémoire total disponible sur le serveur
    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] Get Total MegaBytes available on serveur")
    total_memory_available_mb = 0
    if containers:
        stats = containers[0].stats(stream=False)
        try:
            # nombre de octets (Bytes) utilisés par le serveur
            total_memory_available_bytes = stats["memory_stats"]["limit"]
            # nombre de MegaBytes utilisés par le serveur
            total_memory_available_mb = total_memory_available_bytes / (1024 * 1024)
            # arrondis x.xx MB
            total_memory_available_mb = round(total_memory_available_mb, 2)
            print(f"Memory total available on serveur :", total_memory_available_mb, "MegaBytes")
            total_memory_available_gauge.set(total_memory_available_mb)
        except Exception as e:
            pass

    def get_memory_usage_by_container(c, total_memory_available_mb):
        try:
            stats = c.stats(stream=False)
            # nombre de octets (Bytes) utilisés par le conteneur
            container_memory_used_bytes = stats["memory_stats"]["usage"]
            # nombre de MegaBytes utilisés par le conteneur
            container_memory_used_mb = container_memory_used_bytes / (1024 * 1024)
            # arrondis x.xx MB
            container_memory_used_mb = round(container_memory_used_mb, 2)
            container_memory_used_gauge.labels(name=c.name).set(container_memory_used_mb)
            print(f"Memory {c.name} : {container_memory_used_mb} MB / {total_memory_available_mb} MB available")
            return container_memory_used_mb
        except Exception as e:
            print(f"ERROR MEM {c.name}: {e}")
            container_memory_used_gauge.labels(name=c.name).set(-1)
            return 0.0

    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] Start consommation memory par containers")
    total_memory_used = 0.0
    memory_result_conteneurs = []

    with ThreadPoolExecutor(max_workers=10) as executor:
        for c in containers:
            if c.status == "running":
                memory_result_conteneurs.append(executor.submit(get_memory_usage_by_container, c, total_memory_available_mb))
            else:
                # Supprimer les metrics des conteneurs arrêtés
                container_memory_used_gauge.remove(c.name)

        # Récupération des résultats de tout les conteneurs
        for memory_result_conteneur in as_completed(memory_result_conteneurs):
            total_memory_used += memory_result_conteneur.result()
        # Calcul de l'utilisation de la mémoire total des conteneurs
        print(f"Total MegaBytes used on serveur {round(total_memory_used, 2)} MB / {total_memory_available_mb} MB available")
        total_memory_used_gauge.set(round(total_memory_used, 2))



def start_prometheus_client():
    # Serveur HTTP Prometheus sur le port 8000
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
