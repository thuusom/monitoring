
# Monitoring with Prometheus & Grafana

This project provides a starting point for setting up and monitoring a web stack using **Varnish** as a caching layer in front of **Apache** and **Nginx** backends. Monitoring is handled via **Prometheus**, with dashboards visualized in **Grafana**.

Dashboards are preloaded and cannot be deleted, serving as examples for further customization. The project is designed to extend into a combined monitoring system for various components.

## Architecture  

The system works as follows:

- The web servers (Apache and Nginx) and Varnish are monitored using exporters which feed into Prometheus.
- All metrics are scraped by Prometheus who pulls from the exporters and stores them in a time series database at a regular interval.
- Grafana is used to visualize the metrics.
- Alerts can be configured using Prometheus Alertmanager.

---

## Components

### Web Servers
- **Apache**: HTTP server backend.
  - Monitored using Bitnami Apache Exporter.
  - [Apache Exporter Documentation](https://github.com/Lusitaniae/apache_exporter)

- **Nginx**: HTTP server backend.
  - Monitored using the official Nginx Prometheus Exporter.
  - [Nginx Exporter Documentation](https://github.com/nginxinc/nginx-prometheus-exporter)

### Cache Layer
- **Varnish**: High-performance HTTP accelerator and caching server.
  - Includes a custom Varnish Exporter for Prometheus.
  - [Varnish Exporter Documentation](https://github.com/MooncellWiki/varnish_exporter)

### Monitoring and Visualization
- **Prometheus**: Collects and stores metrics.
  - [Prometheus Documentation](https://prometheus.io)

- **Grafana**: Visualizes metrics with interactive dashboards.
  - [Grafana Documentation](https://grafana.com/oss/grafana)

- **Stream Monitor**: Monitors live streams and extracts metrics.
  - Combines stream probing, image extraction, and metrics export
  - Uses FFprobe for stream analysis
  - Provides Prometheus metrics endpoint
  - Extracts thumbnails for visual monitoring
  - Note: Thumbnail extraction may not work with DRM-protected content

### System Metrics
- **cAdvisor**: Collects metrics about container resource usage.
  - [cAdvisor Documentation](https://github.com/google/cadvisor)
  - NOT SETUP!

---

## Directory Structure

```bash
project-root/
├── apache/
│   ├── httpd.conf        # Apache server configuration
├── nginx/
│   ├── nginx.conf        # Nginx server configuration
├── varnish/
│   ├── default.vcl       # Varnish configuration
│   ├── exporter/         # Custom Varnish Exporter Docker context
├── prometheus/
│   ├── prometheus.yml    # Prometheus configuration
├── grafana/
│   ├── dashboards/       # Grafana JSON dashboards
│   ├── provisioning/     # Datasources and dashboard provisioning
├── html/
│   ├── apache/           # Apache web content
│   ├── nginx/            # Nginx web content
├── varnish_exporter/     # Subdirectory for Varnish exporter setup
├── docker-compose.yml    # Docker Compose configuration
├── stream-monitor/
│   ├── stream_monitor.py     # Stream monitoring service
│   ├── default-streams.json  # Stream configuration
│   ├── templates/            # Web interface templates
│   ├── Dockerfile            # Container configuration
```

---

## Setup and Usage

1. **Clone the Repository**:

   ```bash
   git clone https://github.com/thuusom/monitoring.git
   cd monitoring
   ```

2. **Copy the .env.example file to .env and set the variables**:

   ```bash
   cp example.env .env
   ```

   This ensures that the docker containers are not colliding with other using the same names

4. **Start the Stack**:
   Use `docker compose` to build and run all services:

   ```bash
   docker compose up --build -d
   ```

5. **Access Services**:
   - **Apache**: [http://localhost:8081](http://localhost:8081)
   - **Nginx**: [http://localhost:8082](http://localhost:8082)
   - **Varnish (nginx)**: [http://localhost:8080](http://localhost:8080)
   - **Varnish (apache)**: [http://localhost:8080/apache/](http://localhost:8080/apache/)
   - **Prometheus**: [http://localhost:9090](http://localhost:9090)
   - **Grafana**: [http://localhost:3000](http://localhost:3000)  
     Default credentials: `admin / admin`
   - **Stream Monitor**: [http://localhost:9118](http://localhost:9118)

6. **Configure Streams**:
   The stream monitor uses a JSON configuration file. The default configuration can be overridden by mounting a custom file. f.ex. docker-compose-dev.yml:

   ```yaml
   stream-monitor:
     volumes:
       - ./my-streams.json:/app/streams.json:ro
   ```

   Example streams.json format:

   ```json
   {
     "general": {
       "frequency": 10,
       "log_level": "INFO"
     },
     "image_extraction": {
       "enabled": true,
       "output_path": "./images",
       "width": 640,
       "height": 360
     },
     "streams": [
       {
         "name": "stream1",
         "url": "http://example.com/stream.m3u8",
         "image_extraction": {
           "enabled": true,
           "width": 1280,
           "height": 720
         }
       }
     ]
   }
   ```

   Use `docker compose` to build and run all services with the overriding yml file:

   ```bash
   docker compose -f docker-compose.yml -f docker-compose.dev.yml up -d
   ```
---

## Preloaded Dashboards

This setup includes preloaded Grafana dashboards for:

- **Varnish**
![Varnish Dashboard Preview](./docs/varnish.png)

- **Apache**
![Apache Dashboard Preview](./docs/apache.png)

- **Nginx**
![Nginx Dashboard Preview](./docs/nginx.png)

- **Stream Monitor**
![Stream Monitor Dashboard Preview](./docs/stream-monitor.png)
  - Stream status and uptime
  - Video and audio bitrates
  - Resolution and codec information
  - Live thumbnails (where available)
  - Stream format details

These dashboards are installed during setup and cannot be deleted. They serve as examples and starting points for further customization. Changes made to the files will be available in grafana.

---

## Customization

1. **Update Dashboards**:
   Place custom Grafana dashboards in the `grafana/dashboards/` directory.

2. **Add Prometheus Targets**:
   Update the `prometheus/prometheus.yml` file to include additional exporters or targets.

3. **Extend Monitoring**:
   Add more exporters and configure corresponding dashboards to monitor additional services or components.

---

## Troubleshooting

1. **Service Not Accessible**:
   - Check if the service is running:

     ```bash
     docker compose ps
     ```

   - Review logs:

     ```bash
     docker compose logs <service_name>
     ```

2. **Metrics Missing in Prometheus**:
   - Verify the exporter is running and correctly configured.
   - Check Prometheus targets: [http://localhost:9090/targets](http://localhost:9090/targets).

3. **Grafana Dashboards Not Loading**:
   - Ensure the provisioning directory is correctly mapped in `docker-compose.yml`.
   - Check Grafana logs:

     ```bash
     docker compose logs grafana
     ```

---

## Links and Resources

- [Apache Exporter Documentation](https://github.com/Lusitaniae/apache_exporter)
- [Nginx Prometheus Exporter Guide](https://github.com/nginxinc/nginx-prometheus-exporter/blob/main/grafana/README.md)
- [Varnish Exporter Documentation](https://github.com/MooncellWiki/varnish_exporter)
- [Prometheus Documentation](https://prometheus.io)
- [Grafana Documentation](https://grafana.com/oss/grafana)
- [cAdvisor Documentation](https://github.com/google/cadvisor)
- [FFprobe Documentation](https://ffmpeg.org/ffprobe.html)

---
