# Docker Monitoring Dashboard for Windows

Monitor your Docker containers on Windows using Docker Desktop, Prometheus, and Grafana.

## Pre-requisites

* docker on windows
* docker-desktop on windows
* docker-compose

## Setup and Installation

1. In Docker Desktop, go to **Settings → General** and check the box  
   **“Expose daemon on tcp://localhost:2375 without TLS”**. (for some versions, restart Docker Desktop)

2. Clone this repository on your Windows machine where Docker is already running.

3. Open PowerShell in the repository folder and run:
```
docker-compose up -d
```

## Video Tutorial

## Screenshot

Grafana Dashboard
![Grafana Dashboard Dashboard](./screen_dashboard.png)

## Configuration

By default, the services are accessible on the following URLs:

Docker-exporter: http://localhost:8000/

Prometheus: http://localhost:9090/targets

Grafana: http://localhost:3000/login

