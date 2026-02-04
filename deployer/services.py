"""
Service management for individual services in the AI Stack.

Handles:
- Service lifecycle (start, stop, restart)
- Health monitoring
- Resource scaling
- Log management
- Configuration updates
"""

import subprocess
import json
import time
from pathlib import Path
from typing import Optional, Dict, List, Any
from dataclasses import dataclass, field
from enum import Enum
import logging
import requests

from .config import StackConfig, ServiceConfig

logger = logging.getLogger(__name__)


class ServiceStatus(Enum):
    """Service status states."""
    RUNNING = "running"
    STOPPED = "stopped"
    STARTING = "starting"
    STOPPING = "stopping"
    UNHEALTHY = "unhealthy"
    UNKNOWN = "unknown"


@dataclass
class ServiceInfo:
    """Detailed information about a service."""
    name: str
    status: ServiceStatus
    container_id: Optional[str] = None
    image: str = ""
    ports: List[str] = field(default_factory=list)
    memory_usage: Optional[str] = None
    cpu_percent: Optional[float] = None
    uptime: Optional[str] = None
    health: Optional[str] = None
    logs_tail: List[str] = field(default_factory=list)


class ServiceManager:
    """
    Manages individual services within the AI Stack.
    
    Provides fine-grained control over:
    - Service lifecycle management
    - Resource monitoring
    - Configuration updates
    - Health checking
    """
    
    def __init__(self, config: StackConfig):
        """Initialize service manager with configuration."""
        self.config = config
        self._ensure_docker()
    
    def _ensure_docker(self):
        """Verify Docker is available and running."""
        try:
            subprocess.run(
                ["docker", "info"],
                capture_output=True,
                check=True
            )
        except subprocess.CalledProcessError:
            raise RuntimeError("Docker is not running or not installed")
    
    def _run_compose(self, *args, capture: bool = True) -> subprocess.CompletedProcess:
        """Run a docker compose command."""
        cmd = ["docker", "compose", "-f", str(self.config.base_dir / "docker-compose.yml")]
        cmd.extend(args)
        return subprocess.run(cmd, capture_output=capture, text=True)
    
    def start(self, service_name: str) -> bool:
        """Start a specific service."""
        if service_name not in self.config.services:
            logger.error(f"Unknown service: {service_name}")
            return False
        
        result = self._run_compose("up", "-d", service_name)
        if result.returncode == 0:
            logger.info(f"Started service: {service_name}")
            return True
        logger.error(f"Failed to start {service_name}: {result.stderr}")
        return False
    
    def stop(self, service_name: str) -> bool:
        """Stop a specific service."""
        result = self._run_compose("stop", service_name)
        if result.returncode == 0:
            logger.info(f"Stopped service: {service_name}")
            return True
        logger.error(f"Failed to stop {service_name}: {result.stderr}")
        return False
    
    def restart(self, service_name: str) -> bool:
        """Restart a specific service."""
        result = self._run_compose("restart", service_name)
        if result.returncode == 0:
            logger.info(f"Restarted service: {service_name}")
            return True
        logger.error(f"Failed to restart {service_name}: {result.stderr}")
        return False
    
    def get_status(self, service_name: str) -> ServiceStatus:
        """Get the status of a service."""
        result = subprocess.run(
            ["docker", "inspect", "--format", "{{.State.Status}}", service_name],
            capture_output=True,
            text=True
        )
        if result.returncode != 0:
            return ServiceStatus.UNKNOWN
        
        status_map = {
            "running": ServiceStatus.RUNNING,
            "exited": ServiceStatus.STOPPED,
            "starting": ServiceStatus.STARTING,
            "stopping": ServiceStatus.STOPPING,
        }
        return status_map.get(result.stdout.strip(), ServiceStatus.UNKNOWN)
    
    def get_info(self, service_name: str) -> ServiceInfo:
        """Get detailed information about a service."""
        info = ServiceInfo(
            name=service_name,
            status=self.get_status(service_name)
        )
        
        # Get container details
        result = subprocess.run(
            ["docker", "inspect", service_name],
            capture_output=True,
            text=True
        )
        
        if result.returncode == 0:
            try:
                data = json.loads(result.stdout)[0]
                info.container_id = data.get("Id", "")[:12]
                info.image = data.get("Config", {}).get("Image", "")
                
                # Get port mappings
                ports = data.get("NetworkSettings", {}).get("Ports", {})
                for container_port, bindings in ports.items():
                    if bindings:
                        for binding in bindings:
                            info.ports.append(f"{binding['HostPort']}:{container_port}")
                
                # Get health status
                health = data.get("State", {}).get("Health", {})
                info.health = health.get("Status", "none")
                
                # Calculate uptime
                started = data.get("State", {}).get("StartedAt", "")
                if started and info.status == ServiceStatus.RUNNING:
                    info.uptime = started
                    
            except (json.JSONDecodeError, KeyError, IndexError) as e:
                logger.warning(f"Error parsing container info: {e}")
        
        # Get resource usage
        stats = self.get_stats(service_name)
        if stats:
            info.memory_usage = stats.get("memory")
            info.cpu_percent = stats.get("cpu_percent")
        
        # Get recent logs
        info.logs_tail = self.get_logs(service_name, tail=10)
        
        return info
    
    def get_stats(self, service_name: str) -> Optional[Dict[str, Any]]:
        """Get resource usage statistics for a service."""
        result = subprocess.run(
            ["docker", "stats", "--no-stream", "--format", 
             '{"name":"{{.Name}}","cpu":"{{.CPUPerc}}","memory":"{{.MemUsage}}","net":"{{.NetIO}}"}',
             service_name],
            capture_output=True,
            text=True
        )
        
        if result.returncode == 0 and result.stdout.strip():
            try:
                data = json.loads(result.stdout)
                return {
                    "cpu_percent": float(data["cpu"].rstrip("%")),
                    "memory": data["memory"],
                    "network": data["net"]
                }
            except (json.JSONDecodeError, KeyError, ValueError):
                pass
        return None
    
    def get_logs(self, service_name: str, tail: int = 100, since: Optional[str] = None) -> List[str]:
        """Get logs for a service."""
        cmd = ["docker", "logs", "--tail", str(tail)]
        if since:
            cmd.extend(["--since", since])
        cmd.append(service_name)
        
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode == 0:
            # Combine stdout and stderr (logs can be in either)
            logs = result.stdout + result.stderr
            return logs.strip().split("\n")
        return []
    
    def stream_logs(self, service_name: str):
        """Stream logs from a service (blocking)."""
        subprocess.run(["docker", "logs", "-f", service_name])
    
    def execute(self, service_name: str, command: List[str], interactive: bool = False) -> str:
        """Execute a command in a running container."""
        cmd = ["docker", "exec"]
        if interactive:
            cmd.extend(["-it"])
        cmd.append(service_name)
        cmd.extend(command)
        
        result = subprocess.run(cmd, capture_output=not interactive, text=True)
        return result.stdout if not interactive else ""
    
    def scale(self, service_name: str, replicas: int) -> bool:
        """Scale a service to specified number of replicas."""
        result = self._run_compose("up", "-d", "--scale", f"{service_name}={replicas}", service_name)
        return result.returncode == 0
    
    def update_image(self, service_name: str, pull: bool = True) -> bool:
        """Update a service to the latest image version."""
        if pull:
            pull_result = self._run_compose("pull", service_name)
            if pull_result.returncode != 0:
                logger.error(f"Failed to pull image for {service_name}")
                return False
        
        result = self._run_compose("up", "-d", "--force-recreate", service_name)
        return result.returncode == 0
    
    def get_all_services(self) -> Dict[str, ServiceInfo]:
        """Get information about all configured services."""
        services = {}
        for name in self.config.services:
            services[name] = self.get_info(name)
        return services
    
    def wait_for_healthy(self, service_name: str, timeout: int = 120) -> bool:
        """Wait for a service to become healthy."""
        start_time = time.time()
        while time.time() - start_time < timeout:
            info = self.get_info(service_name)
            if info.health == "healthy":
                return True
            if info.status == ServiceStatus.STOPPED:
                return False
            time.sleep(2)
        return False
    
    # Service-specific operations
    
    def ollama_list_models(self) -> List[Dict[str, Any]]:
        """List models available in Ollama."""
        try:
            response = requests.get(f"{self.config.ollama.base_url}/api/tags", timeout=10)
            if response.status_code == 200:
                return response.json().get("models", [])
        except requests.RequestException as e:
            logger.error(f"Failed to list Ollama models: {e}")
        return []
    
    def ollama_pull_model(self, model_name: str) -> bool:
        """Pull a model in Ollama."""
        try:
            response = requests.post(
                f"{self.config.ollama.base_url}/api/pull",
                json={"name": model_name},
                stream=True,
                timeout=3600  # Models can take a while to download
            )
            
            for line in response.iter_lines():
                if line:
                    data = json.loads(line)
                    if "status" in data:
                        logger.info(f"Ollama pull: {data['status']}")
                    if data.get("status") == "success":
                        return True
            return False
        except requests.RequestException as e:
            logger.error(f"Failed to pull model {model_name}: {e}")
            return False
    
    def ollama_unload_models(self) -> bool:
        """Unload all models from Ollama memory."""
        models = self.ollama_list_models()
        for model in models:
            try:
                requests.post(
                    f"{self.config.ollama.base_url}/api/generate",
                    json={"model": model["name"], "keep_alive": 0}
                )
            except requests.RequestException:
                pass
        return True
    
    def qdrant_health(self) -> Dict[str, Any]:
        """Check Qdrant health status."""
        try:
            response = requests.get("http://localhost:6333/readyz", timeout=5)
            return {"healthy": response.status_code == 200}
        except requests.RequestException:
            return {"healthy": False}
    
    def qdrant_list_collections(self) -> List[str]:
        """List Qdrant collections."""
        try:
            response = requests.get("http://localhost:6333/collections", timeout=5)
            if response.status_code == 200:
                return [c["name"] for c in response.json().get("result", {}).get("collections", [])]
        except requests.RequestException:
            pass
        return []
    
    def redis_info(self) -> Dict[str, Any]:
        """Get Redis server information."""
        output = self.execute("redis", ["redis-cli", "INFO"])
        info = {}
        for line in output.split("\n"):
            if ":" in line:
                key, value = line.split(":", 1)
                info[key] = value.strip()
        return info
    
    def postgres_query(self, query: str, database: str = "postgres") -> str:
        """Execute a query on PostgreSQL."""
        return self.execute(
            "supabase-db",
            ["psql", "-U", "postgres", "-d", database, "-c", query]
        )
    
    def n8n_health(self) -> Dict[str, Any]:
        """Check n8n health status."""
        try:
            response = requests.get("http://localhost:5678/healthz", timeout=5)
            return {"healthy": response.status_code == 200}
        except requests.RequestException:
            return {"healthy": False}
