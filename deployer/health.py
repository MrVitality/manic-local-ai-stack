"""
Health monitoring and alerting for AI Stack services.

Handles:
- Periodic health checks
- Service auto-recovery
- Alert notifications
- Health metrics collection
"""

import time
import threading
import logging
from typing import Optional, Dict, List, Any, Callable
from dataclasses import dataclass, field
from enum import Enum
from datetime import datetime, timedelta
import requests
import json
from concurrent.futures import ThreadPoolExecutor, as_completed

from .config import StackConfig
from .services import ServiceManager, ServiceStatus

logger = logging.getLogger(__name__)


class HealthStatus(Enum):
    """Health status levels."""
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNHEALTHY = "unhealthy"
    UNKNOWN = "unknown"


@dataclass
class HealthCheckResult:
    """Result of a single health check."""
    service: str
    status: HealthStatus
    response_time_ms: Optional[float] = None
    message: str = ""
    timestamp: datetime = field(default_factory=datetime.now)
    details: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ServiceHealthConfig:
    """Configuration for service health checks."""
    service_name: str
    check_type: str = "http"  # http, tcp, command, docker
    endpoint: str = ""
    port: int = 0
    command: List[str] = field(default_factory=list)
    timeout_seconds: int = 10
    interval_seconds: int = 30
    unhealthy_threshold: int = 3
    healthy_threshold: int = 2
    auto_restart: bool = True
    restart_cooldown_seconds: int = 300


class HealthChecker:
    """
    Comprehensive health monitoring system for the AI Stack.
    
    Features:
    - Configurable health checks per service
    - Auto-recovery with cooldown
    - Alert callbacks for external integrations
    - Metrics collection and history
    """
    
    def __init__(
        self,
        config: StackConfig,
        service_manager: ServiceManager,
        alert_callback: Optional[Callable[[HealthCheckResult], None]] = None
    ):
        """Initialize the health checker."""
        self.config = config
        self.service_manager = service_manager
        self.alert_callback = alert_callback
        
        # Health check configurations
        self.health_configs: Dict[str, ServiceHealthConfig] = self._default_health_configs()
        
        # State tracking
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._consecutive_failures: Dict[str, int] = {}
        self._consecutive_successes: Dict[str, int] = {}
        self._last_restart: Dict[str, datetime] = {}
        self._health_history: Dict[str, List[HealthCheckResult]] = {}
        
        # Initialize counters
        for service in self.health_configs:
            self._consecutive_failures[service] = 0
            self._consecutive_successes[service] = 0
            self._health_history[service] = []
    
    def _default_health_configs(self) -> Dict[str, ServiceHealthConfig]:
        """Get default health check configurations for all services."""
        configs = {}
        
        # Ollama
        configs["ollama"] = ServiceHealthConfig(
            service_name="ollama",
            check_type="http",
            endpoint="http://localhost:11434/api/tags",
            timeout_seconds=10,
            interval_seconds=30,
            auto_restart=True
        )
        
        # Qdrant
        configs["qdrant"] = ServiceHealthConfig(
            service_name="qdrant",
            check_type="http",
            endpoint="http://localhost:6333/readyz",
            timeout_seconds=5,
            interval_seconds=30
        )
        
        # Redis
        configs["redis"] = ServiceHealthConfig(
            service_name="redis",
            check_type="command",
            command=["docker", "exec", "redis", "redis-cli", "ping"],
            timeout_seconds=5,
            interval_seconds=15
        )
        
        # Supabase DB
        configs["supabase-db"] = ServiceHealthConfig(
            service_name="supabase-db",
            check_type="command",
            command=["docker", "exec", "supabase-db", "pg_isready", "-U", "postgres"],
            timeout_seconds=10,
            interval_seconds=30
        )
        
        # Supabase Kong
        configs["supabase-kong"] = ServiceHealthConfig(
            service_name="supabase-kong",
            check_type="http",
            endpoint="http://localhost:8000/",
            timeout_seconds=10,
            interval_seconds=30
        )
        
        # n8n
        configs["n8n"] = ServiceHealthConfig(
            service_name="n8n",
            check_type="http",
            endpoint="http://localhost:5678/healthz",
            timeout_seconds=10,
            interval_seconds=30
        )
        
        # Langfuse
        configs["langfuse"] = ServiceHealthConfig(
            service_name="langfuse",
            check_type="http",
            endpoint="http://localhost:3002/api/public/health",
            timeout_seconds=10,
            interval_seconds=60
        )
        
        # Open WebUI
        configs["open-webui"] = ServiceHealthConfig(
            service_name="open-webui",
            check_type="http",
            endpoint="http://localhost:3003/",
            timeout_seconds=10,
            interval_seconds=30
        )
        
        # Flowise
        configs["flowise"] = ServiceHealthConfig(
            service_name="flowise",
            check_type="http",
            endpoint="http://localhost:3004/",
            timeout_seconds=10,
            interval_seconds=60
        )
        
        # Searxng
        configs["searxng"] = ServiceHealthConfig(
            service_name="searxng",
            check_type="http",
            endpoint="http://localhost:8888/",
            timeout_seconds=10,
            interval_seconds=60
        )
        
        # Caddy
        configs["caddy"] = ServiceHealthConfig(
            service_name="caddy",
            check_type="docker",
            timeout_seconds=5,
            interval_seconds=30
        )
        
        return configs
    
    def check_service(self, service_name: str) -> HealthCheckResult:
        """Perform a health check on a specific service."""
        if service_name not in self.health_configs:
            return HealthCheckResult(
                service=service_name,
                status=HealthStatus.UNKNOWN,
                message="No health check configured"
            )
        
        config = self.health_configs[service_name]
        start_time = time.time()
        
        try:
            if config.check_type == "http":
                result = self._check_http(config)
            elif config.check_type == "tcp":
                result = self._check_tcp(config)
            elif config.check_type == "command":
                result = self._check_command(config)
            elif config.check_type == "docker":
                result = self._check_docker(config)
            else:
                result = HealthCheckResult(
                    service=service_name,
                    status=HealthStatus.UNKNOWN,
                    message=f"Unknown check type: {config.check_type}"
                )
            
            result.response_time_ms = (time.time() - start_time) * 1000
            
        except Exception as e:
            result = HealthCheckResult(
                service=service_name,
                status=HealthStatus.UNHEALTHY,
                message=f"Check failed with exception: {str(e)}",
                response_time_ms=(time.time() - start_time) * 1000
            )
        
        # Update history
        if service_name in self._health_history:
            self._health_history[service_name].append(result)
            # Keep only last 100 results
            self._health_history[service_name] = self._health_history[service_name][-100:]
        
        return result
    
    def _check_http(self, config: ServiceHealthConfig) -> HealthCheckResult:
        """Perform HTTP health check."""
        try:
            response = requests.get(
                config.endpoint,
                timeout=config.timeout_seconds
            )
            
            if response.status_code < 400:
                return HealthCheckResult(
                    service=config.service_name,
                    status=HealthStatus.HEALTHY,
                    message=f"HTTP {response.status_code}",
                    details={"status_code": response.status_code}
                )
            else:
                return HealthCheckResult(
                    service=config.service_name,
                    status=HealthStatus.UNHEALTHY,
                    message=f"HTTP {response.status_code}",
                    details={"status_code": response.status_code}
                )
                
        except requests.Timeout:
            return HealthCheckResult(
                service=config.service_name,
                status=HealthStatus.UNHEALTHY,
                message="Request timed out"
            )
        except requests.ConnectionError:
            return HealthCheckResult(
                service=config.service_name,
                status=HealthStatus.UNHEALTHY,
                message="Connection refused"
            )
    
    def _check_tcp(self, config: ServiceHealthConfig) -> HealthCheckResult:
        """Perform TCP port check."""
        import socket
        
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(config.timeout_seconds)
            result = sock.connect_ex(("localhost", config.port))
            sock.close()
            
            if result == 0:
                return HealthCheckResult(
                    service=config.service_name,
                    status=HealthStatus.HEALTHY,
                    message=f"Port {config.port} is open"
                )
            else:
                return HealthCheckResult(
                    service=config.service_name,
                    status=HealthStatus.UNHEALTHY,
                    message=f"Port {config.port} is closed"
                )
        except socket.error as e:
            return HealthCheckResult(
                service=config.service_name,
                status=HealthStatus.UNHEALTHY,
                message=f"Socket error: {str(e)}"
            )
    
    def _check_command(self, config: ServiceHealthConfig) -> HealthCheckResult:
        """Perform command-based health check."""
        import subprocess
        
        try:
            result = subprocess.run(
                config.command,
                capture_output=True,
                text=True,
                timeout=config.timeout_seconds
            )
            
            if result.returncode == 0:
                return HealthCheckResult(
                    service=config.service_name,
                    status=HealthStatus.HEALTHY,
                    message="Command succeeded",
                    details={"output": result.stdout[:200]}
                )
            else:
                return HealthCheckResult(
                    service=config.service_name,
                    status=HealthStatus.UNHEALTHY,
                    message=f"Command failed: {result.stderr[:200]}"
                )
                
        except subprocess.TimeoutExpired:
            return HealthCheckResult(
                service=config.service_name,
                status=HealthStatus.UNHEALTHY,
                message="Command timed out"
            )
    
    def _check_docker(self, config: ServiceHealthConfig) -> HealthCheckResult:
        """Check Docker container status."""
        status = self.service_manager.get_status(config.service_name)
        
        if status == ServiceStatus.RUNNING:
            return HealthCheckResult(
                service=config.service_name,
                status=HealthStatus.HEALTHY,
                message="Container is running"
            )
        else:
            return HealthCheckResult(
                service=config.service_name,
                status=HealthStatus.UNHEALTHY,
                message=f"Container status: {status.value}"
            )
    
    def check_all(self) -> Dict[str, HealthCheckResult]:
        """Perform health checks on all configured services."""
        results = {}
        
        # Use thread pool for parallel checks
        with ThreadPoolExecutor(max_workers=10) as executor:
            future_to_service = {
                executor.submit(self.check_service, name): name
                for name in self.health_configs
            }
            
            for future in as_completed(future_to_service):
                service = future_to_service[future]
                try:
                    results[service] = future.result()
                except Exception as e:
                    results[service] = HealthCheckResult(
                        service=service,
                        status=HealthStatus.UNKNOWN,
                        message=f"Check error: {str(e)}"
                    )
        
        return results
    
    def _handle_check_result(self, result: HealthCheckResult):
        """Handle the result of a health check."""
        service = result.service
        config = self.health_configs.get(service)
        
        if not config:
            return
        
        if result.status == HealthStatus.HEALTHY:
            # Reset failure counter, increment success counter
            self._consecutive_failures[service] = 0
            self._consecutive_successes[service] += 1
            
        else:
            # Increment failure counter, reset success counter
            self._consecutive_failures[service] += 1
            self._consecutive_successes[service] = 0
            
            # Check if we should trigger alert
            if self._consecutive_failures[service] >= config.unhealthy_threshold:
                logger.warning(
                    f"Service {service} is unhealthy "
                    f"({self._consecutive_failures[service]} consecutive failures)"
                )
                
                # Send alert
                if self.alert_callback:
                    self.alert_callback(result)
                
                # Auto-restart if enabled
                if config.auto_restart:
                    self._maybe_restart(service, config)
    
    def _maybe_restart(self, service: str, config: ServiceHealthConfig):
        """Attempt to restart a service if cooldown has passed."""
        last_restart = self._last_restart.get(service)
        now = datetime.now()
        
        if last_restart is None or \
           (now - last_restart).total_seconds() >= config.restart_cooldown_seconds:
            logger.info(f"Auto-restarting service: {service}")
            
            if self.service_manager.restart(service):
                self._last_restart[service] = now
                self._consecutive_failures[service] = 0
                logger.info(f"Successfully restarted: {service}")
            else:
                logger.error(f"Failed to restart: {service}")
        else:
            remaining = config.restart_cooldown_seconds - (now - last_restart).total_seconds()
            logger.info(f"Restart cooldown active for {service}: {remaining:.0f}s remaining")
    
    def start_monitoring(self, interval: int = 30):
        """Start background health monitoring."""
        if self._running:
            logger.warning("Health monitoring is already running")
            return
        
        self._running = True
        self._thread = threading.Thread(target=self._monitoring_loop, args=(interval,), daemon=True)
        self._thread.start()
        logger.info("Health monitoring started")
    
    def stop_monitoring(self):
        """Stop background health monitoring."""
        self._running = False
        if self._thread:
            self._thread.join(timeout=10)
        logger.info("Health monitoring stopped")
    
    def _monitoring_loop(self, interval: int):
        """Main monitoring loop."""
        while self._running:
            try:
                results = self.check_all()
                for service, result in results.items():
                    self._handle_check_result(result)
            except Exception as e:
                logger.error(f"Error in monitoring loop: {e}")
            
            time.sleep(interval)
    
    def get_overall_status(self) -> HealthStatus:
        """Get overall health status of the stack."""
        results = self.check_all()
        
        unhealthy_count = sum(1 for r in results.values() if r.status == HealthStatus.UNHEALTHY)
        degraded_count = sum(1 for r in results.values() if r.status == HealthStatus.DEGRADED)
        
        if unhealthy_count > len(results) // 2:
            return HealthStatus.UNHEALTHY
        elif unhealthy_count > 0 or degraded_count > 0:
            return HealthStatus.DEGRADED
        else:
            return HealthStatus.HEALTHY
    
    def get_health_report(self) -> Dict[str, Any]:
        """Generate a comprehensive health report."""
        results = self.check_all()
        
        report = {
            "timestamp": datetime.now().isoformat(),
            "overall_status": self.get_overall_status().value,
            "services": {},
            "summary": {
                "total": len(results),
                "healthy": 0,
                "degraded": 0,
                "unhealthy": 0,
                "unknown": 0
            }
        }
        
        for service, result in results.items():
            report["services"][service] = {
                "status": result.status.value,
                "message": result.message,
                "response_time_ms": result.response_time_ms,
                "consecutive_failures": self._consecutive_failures.get(service, 0)
            }
            
            if result.status == HealthStatus.HEALTHY:
                report["summary"]["healthy"] += 1
            elif result.status == HealthStatus.DEGRADED:
                report["summary"]["degraded"] += 1
            elif result.status == HealthStatus.UNHEALTHY:
                report["summary"]["unhealthy"] += 1
            else:
                report["summary"]["unknown"] += 1
        
        return report
    
    def get_history(self, service: str, limit: int = 50) -> List[Dict[str, Any]]:
        """Get health check history for a service."""
        history = self._health_history.get(service, [])[-limit:]
        return [
            {
                "timestamp": h.timestamp.isoformat(),
                "status": h.status.value,
                "message": h.message,
                "response_time_ms": h.response_time_ms
            }
            for h in history
        ]
