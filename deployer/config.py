"""
Configuration management for AI Stack Deployer.

Handles:
- Stack-wide configuration
- Per-service configuration
- Environment variable management
- Secrets generation and rotation
- Resource allocation profiles
"""

import os
import secrets
import string
import hashlib
from pathlib import Path
from dataclasses import dataclass, field
from typing import Optional, Dict, List, Any
from enum import Enum
import yaml
import json


class DeploymentProfile(Enum):
    """Predefined deployment profiles for different hardware configurations."""
    MINIMAL = "minimal"      # 8GB RAM, 2 CPU - essential services only
    STANDARD = "standard"    # 16GB RAM, 4 CPU - full stack without Neo4j
    FULL = "full"            # 32GB+ RAM, 8+ CPU - everything including Neo4j
    CUSTOM = "custom"        # User-defined resource allocation


class NetworkMode(Enum):
    """Network exposure modes for security."""
    LOCALHOST = "localhost"   # Only localhost access (SSH tunnel required)
    TAILSCALE = "tailscale"   # Tailscale mesh network
    PUBLIC = "public"         # Public with Caddy reverse proxy
    CUSTOM = "custom"         # Custom network configuration


# Default Tailscale IP - update this to your actual Tailscale IP
TAILSCALE_IP = "100.100.180.114"


@dataclass
class ResourceLimits:
    """Container resource limits."""
    memory: str = "1G"
    cpus: Optional[str] = None
    memory_swap: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        result = {"memory": self.memory}
        if self.cpus:
            result["cpus"] = self.cpus
        if self.memory_swap:
            result["memswap_limit"] = self.memory_swap
        return result


@dataclass
class ServiceConfig:
    """Configuration for individual services."""
    name: str
    enabled: bool = True
    image: str = ""
    tag: str = "latest"
    ports: List[str] = field(default_factory=list)
    volumes: List[str] = field(default_factory=list)
    environment: Dict[str, str] = field(default_factory=dict)
    depends_on: List[str] = field(default_factory=list)
    healthcheck: Optional[Dict[str, Any]] = None
    resources: ResourceLimits = field(default_factory=ResourceLimits)
    networks: List[str] = field(default_factory=lambda: ["ai-network"])
    labels: Dict[str, str] = field(default_factory=dict)
    command: Optional[str] = None
    profiles: List[str] = field(default_factory=list)
    restart_policy: str = "unless-stopped"
    
    @property
    def full_image(self) -> str:
        return f"{self.image}:{self.tag}"


@dataclass
class DatabaseConfig:
    """Database-specific configuration."""
    host: str = "supabase-db"
    port: int = 5432
    user: str = "postgres"
    password: str = ""
    database: str = "postgres"
    
    @property
    def connection_string(self) -> str:
        return f"postgresql://{self.user}:{self.password}@{self.host}:{self.port}/{self.database}"
    
    @property
    def asyncpg_url(self) -> str:
        return f"postgresql+asyncpg://{self.user}:{self.password}@{self.host}:{self.port}/{self.database}"


@dataclass
class SupabaseConfig:
    """Supabase-specific configuration."""
    jwt_secret: str = ""
    anon_key: str = ""
    service_role_key: str = ""
    api_url: str = "http://supabase-kong:8000"
    studio_port: int = 3001
    
    def generate_keys(self):
        """Generate JWT secret and API keys."""
        if not self.jwt_secret:
            self.jwt_secret = generate_secret(64)
        # In production, these would be proper JWTs
        if not self.anon_key:
            self.anon_key = generate_secret(64)
        if not self.service_role_key:
            self.service_role_key = generate_secret(64)


@dataclass
class OllamaConfig:
    """Ollama-specific configuration."""
    host: str = "ollama"
    port: int = 11434
    models: List[str] = field(default_factory=lambda: ["llama3.2:3b", "nomic-embed-text"])
    keep_alive: str = "5m"
    num_parallel: int = 2
    max_loaded_models: int = 2
    
    @property
    def base_url(self) -> str:
        return f"http://{self.host}:{self.port}"


@dataclass
class StackConfig:
    """Main configuration for the entire AI stack."""
    
    # Deployment settings
    project_name: str = "ultimate-ai-stack"
    profile: DeploymentProfile = DeploymentProfile.STANDARD
    network_mode: NetworkMode = NetworkMode.TAILSCALE
    domain: str = "localhost"
    tailscale_ip: str = TAILSCALE_IP  # Tailscale mesh IP
    
    # Directory paths
    base_dir: Path = field(default_factory=lambda: Path.home() / "ai-stack")
    data_dir: Path = field(default_factory=lambda: Path.home() / "ai-stack" / "data")
    config_dir: Path = field(default_factory=lambda: Path.home() / "ai-stack" / "config")
    backup_dir: Path = field(default_factory=lambda: Path.home() / "ai-stack" / "backups")
    logs_dir: Path = field(default_factory=lambda: Path.home() / "ai-stack" / "logs")
    
    # Database configuration
    database: DatabaseConfig = field(default_factory=DatabaseConfig)
    
    # Service-specific configs
    supabase: SupabaseConfig = field(default_factory=SupabaseConfig)
    ollama: OllamaConfig = field(default_factory=OllamaConfig)
    
    # Services configuration
    services: Dict[str, ServiceConfig] = field(default_factory=dict)
    
    # Feature flags
    enable_monitoring: bool = True
    enable_backups: bool = True
    enable_ssl: bool = True
    enable_rag: bool = True
    enable_pydantic_ai: bool = True  # Enable Pydantic AI integration
    
    # Resource totals (for validation)
    total_memory_gb: int = 16
    total_cpus: int = 4
    
    @property
    def base_url(self) -> str:
        """Get base URL based on network mode."""
        if self.network_mode == NetworkMode.TAILSCALE:
            return f"http://{self.tailscale_ip}"
        elif self.network_mode == NetworkMode.LOCALHOST:
            return "http://localhost"
        elif self.network_mode == NetworkMode.PUBLIC:
            return f"https://{self.domain}"
        return f"http://{self.domain}"
    
    def __post_init__(self):
        """Initialize default services based on profile."""
        if not self.services:
            self.services = self._get_default_services()
        
        # Generate secrets if not set
        if not self.database.password:
            self.database.password = generate_secret(32)
        self.supabase.generate_keys()
    
    def _get_default_services(self) -> Dict[str, ServiceConfig]:
        """Get default service configurations based on deployment profile."""
        services = {}
        
        # === OLLAMA - LLM Inference ===
        services["ollama"] = ServiceConfig(
            name="ollama",
            image="ollama/ollama",
            ports=["11434:11434"],
            volumes=["ollama-data:/root/.ollama"],
            resources=ResourceLimits(memory="8G"),
            healthcheck={
                "test": ["CMD", "curl", "-f", "http://localhost:11434/api/tags"],
                "interval": "30s",
                "timeout": "10s",
                "retries": 3,
                "start_period": "60s"
            }
        )
        
        # === QDRANT - Vector Database ===
        services["qdrant"] = ServiceConfig(
            name="qdrant",
            image="qdrant/qdrant",
            ports=["6333:6333", "6334:6334"],
            volumes=["qdrant-data:/qdrant/storage"],
            resources=ResourceLimits(memory="2G"),
            healthcheck={
                "test": ["CMD", "curl", "-f", "http://localhost:6333/readyz"],
                "interval": "10s",
                "timeout": "5s",
                "retries": 5
            }
        )
        
        # === REDIS - Caching ===
        services["redis"] = ServiceConfig(
            name="redis",
            image="redis",
            tag="7-alpine",
            ports=["6379:6379"],
            volumes=["redis-data:/data"],
            command="redis-server --appendonly yes --maxmemory 256mb --maxmemory-policy allkeys-lru",
            resources=ResourceLimits(memory="512M"),
            healthcheck={
                "test": ["CMD", "redis-cli", "ping"],
                "interval": "10s",
                "timeout": "5s",
                "retries": 5
            }
        )
        
        # === NEO4J - Graph Database (Full profile only) ===
        services["neo4j"] = ServiceConfig(
            name="neo4j",
            image="neo4j",
            tag="5-community",
            enabled=(self.profile == DeploymentProfile.FULL),
            profiles=["full"],
            ports=["7474:7474", "7687:7687"],
            volumes=["neo4j-data:/data", "neo4j-logs:/logs"],
            resources=ResourceLimits(memory="2G"),
            environment={
                "NEO4J_AUTH": "neo4j/${NEO4J_PASSWORD}",
                "NEO4J_PLUGINS": '["apoc"]'
            }
        )
        
        # === SUPABASE STACK ===
        services["supabase-db"] = ServiceConfig(
            name="supabase-db",
            image="supabase/postgres",
            tag="15.1.1.78",
            ports=["5432:5432"],
            volumes=[
                "supabase-db-data:/var/lib/postgresql/data",
                "./supabase/init.sql:/docker-entrypoint-initdb.d/init.sql:ro"
            ],
            command="postgres -c wal_level=logical -c max_connections=200 -c shared_buffers=256MB -c effective_cache_size=768MB -c listen_addresses=*",
            resources=ResourceLimits(memory="2G"),
            healthcheck={
                "test": ["CMD-SHELL", "pg_isready -U postgres -d postgres"],
                "interval": "10s",
                "timeout": "5s",
                "retries": 5,
                "start_period": "30s"
            }
        )
        
        services["supabase-auth"] = ServiceConfig(
            name="supabase-auth",
            image="supabase/gotrue",
            tag="v2.143.0",
            depends_on=["supabase-db"],
            resources=ResourceLimits(memory="256M")
        )
        
        services["supabase-rest"] = ServiceConfig(
            name="supabase-rest",
            image="postgrest/postgrest",
            tag="v12.0.1",
            depends_on=["supabase-db"],
            resources=ResourceLimits(memory="256M")
        )
        
        services["supabase-meta"] = ServiceConfig(
            name="supabase-meta",
            image="supabase/postgres-meta",
            tag="v0.80.0",
            depends_on=["supabase-db"],
            resources=ResourceLimits(memory="256M"),
            environment={
                "PG_META_PORT": "8080",
                "PG_META_DB_URL": "postgresql://postgres:${POSTGRES_PASSWORD}@supabase-db:5432/postgres"
            }
        )
        
        services["supabase-storage"] = ServiceConfig(
            name="supabase-storage",
            image="supabase/storage-api",
            tag="v0.46.4",
            depends_on=["supabase-db"],
            volumes=["supabase-storage-data:/var/lib/storage"],
            resources=ResourceLimits(memory="512M")
        )
        
        services["supabase-kong"] = ServiceConfig(
            name="supabase-kong",
            image="kong",
            tag="2.8.1",
            ports=["8000:8000", "8443:8443"],
            volumes=["./supabase/kong.yml:/var/lib/kong/kong.yml:ro"],
            resources=ResourceLimits(memory="512M"),
            healthcheck={
                "test": ["CMD", "kong", "health"],
                "interval": "30s",
                "timeout": "10s",
                "retries": 3
            }
        )
        
        services["supabase-studio"] = ServiceConfig(
            name="supabase-studio",
            image="supabase/studio",
            tag="20240101-8e4a094",
            ports=["3001:3000"],
            depends_on=["supabase-meta"],
            resources=ResourceLimits(memory="512M")
        )
        
        # === LANGFUSE - LLM Observability ===
        services["langfuse-db"] = ServiceConfig(
            name="langfuse-db",
            image="postgres",
            tag="15-alpine",
            volumes=["langfuse-db-data:/var/lib/postgresql/data"],
            resources=ResourceLimits(memory="512M"),
            environment={
                "POSTGRES_USER": "langfuse",
                "POSTGRES_PASSWORD": "${LANGFUSE_DB_PASSWORD}",
                "POSTGRES_DB": "langfuse"
            },
            healthcheck={
                "test": ["CMD-SHELL", "pg_isready -U langfuse -d langfuse"],
                "interval": "10s",
                "timeout": "5s",
                "retries": 5
            }
        )
        
        services["langfuse"] = ServiceConfig(
            name="langfuse",
            image="langfuse/langfuse",
            tag="2",
            ports=["3002:3000"],
            depends_on=["langfuse-db"],
            resources=ResourceLimits(memory="1G")
        )
        
        # === N8N - Workflow Automation ===
        services["n8n"] = ServiceConfig(
            name="n8n",
            image="n8nio/n8n",
            ports=["5678:5678"],
            volumes=["n8n-data:/home/node/.n8n"],
            resources=ResourceLimits(memory="1G"),
            environment={
                "N8N_HOST": "${DOMAIN}",
                "N8N_PROTOCOL": "https",
                "WEBHOOK_URL": "https://${DOMAIN}/n8n/",
                "GENERIC_TIMEZONE": "UTC"
            }
        )
        
        # === FLOWISE - No-Code AI Agents ===
        services["flowise"] = ServiceConfig(
            name="flowise",
            image="flowiseai/flowise",
            ports=["3004:3000"],
            volumes=["flowise-data:/root/.flowise"],
            resources=ResourceLimits(memory="1G")
        )
        
        # === SEARXNG - Privacy-Respecting Search ===
        services["searxng"] = ServiceConfig(
            name="searxng",
            image="searxng/searxng",
            ports=["8888:8080"],
            volumes=["./searxng:/etc/searxng"],
            resources=ResourceLimits(memory="512M")
        )
        
        # === OPEN WEBUI - Chat Interface ===
        services["open-webui"] = ServiceConfig(
            name="open-webui",
            image="ghcr.io/open-webui/open-webui",
            tag="main",
            ports=["3003:8080"],
            volumes=["open-webui-data:/app/backend/data"],
            resources=ResourceLimits(memory="2G"),
            environment={
                "OLLAMA_BASE_URL": "http://ollama:11434",
                "WEBUI_AUTH": "false"
            }
        )
        
        # === CADDY - Reverse Proxy ===
        services["caddy"] = ServiceConfig(
            name="caddy",
            image="caddy",
            tag="2-alpine",
            ports=["80:80", "443:443"],
            volumes=[
                "./Caddyfile:/etc/caddy/Caddyfile:ro",
                "caddy-data:/data",
                "caddy-config:/config"
            ],
            resources=ResourceLimits(memory="128M")
        )
        
        return services
    
    def get_enabled_services(self) -> Dict[str, ServiceConfig]:
        """Return only enabled services."""
        return {
            name: svc for name, svc in self.services.items() 
            if svc.enabled
        }
    
    def calculate_total_memory(self) -> str:
        """Calculate total memory allocation for all enabled services."""
        total_mb = 0
        for svc in self.get_enabled_services().values():
            mem_str = svc.resources.memory.upper()
            if mem_str.endswith("G"):
                total_mb += int(float(mem_str[:-1]) * 1024)
            elif mem_str.endswith("M"):
                total_mb += int(mem_str[:-1])
        return f"{total_mb}M ({total_mb / 1024:.1f}G)"
    
    def validate(self) -> List[str]:
        """Validate configuration and return list of issues."""
        issues = []
        
        # Check memory allocation
        total_mb = 0
        for svc in self.get_enabled_services().values():
            mem_str = svc.resources.memory.upper()
            if mem_str.endswith("G"):
                total_mb += int(float(mem_str[:-1]) * 1024)
            elif mem_str.endswith("M"):
                total_mb += int(mem_str[:-1])
        
        available_mb = self.total_memory_gb * 1024 * 0.85  # Leave 15% for OS
        if total_mb > available_mb:
            issues.append(
                f"Total memory allocation ({total_mb}M) exceeds available "
                f"({available_mb:.0f}M based on {self.total_memory_gb}GB system)"
            )
        
        # Check for port conflicts
        used_ports = {}
        for name, svc in self.get_enabled_services().items():
            for port_mapping in svc.ports:
                host_port = port_mapping.split(":")[0]
                if host_port in used_ports:
                    issues.append(
                        f"Port conflict: {name} and {used_ports[host_port]} "
                        f"both use port {host_port}"
                    )
                used_ports[host_port] = name
        
        # Check dependencies
        enabled_names = set(self.get_enabled_services().keys())
        for name, svc in self.get_enabled_services().items():
            for dep in svc.depends_on:
                if dep not in enabled_names:
                    issues.append(
                        f"Service {name} depends on disabled service {dep}"
                    )
        
        return issues
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert configuration to dictionary."""
        return {
            "project_name": self.project_name,
            "profile": self.profile.value,
            "network_mode": self.network_mode.value,
            "domain": self.domain,
            "base_dir": str(self.base_dir),
            "total_memory_gb": self.total_memory_gb,
            "total_cpus": self.total_cpus,
            "services": {
                name: {
                    "enabled": svc.enabled,
                    "image": svc.full_image,
                    "memory": svc.resources.memory
                }
                for name, svc in self.services.items()
            }
        }
    
    def save(self, path: Optional[Path] = None):
        """Save configuration to YAML file."""
        if path is None:
            path = self.config_dir / "stack-config.yaml"
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w") as f:
            yaml.dump(self.to_dict(), f, default_flow_style=False)
    
    @classmethod
    def load(cls, path: Path) -> "StackConfig":
        """Load configuration from YAML file."""
        with open(path) as f:
            data = yaml.safe_load(f)
        
        config = cls(
            project_name=data.get("project_name", "ultimate-ai-stack"),
            profile=DeploymentProfile(data.get("profile", "standard")),
            network_mode=NetworkMode(data.get("network_mode", "localhost")),
            domain=data.get("domain", "localhost"),
            total_memory_gb=data.get("total_memory_gb", 16),
            total_cpus=data.get("total_cpus", 4)
        )
        
        if "base_dir" in data:
            config.base_dir = Path(data["base_dir"])
            config.data_dir = config.base_dir / "data"
            config.config_dir = config.base_dir / "config"
            config.backup_dir = config.base_dir / "backups"
            config.logs_dir = config.base_dir / "logs"
        
        return config


def generate_secret(length: int = 32, include_special: bool = False) -> str:
    """Generate a cryptographically secure random secret."""
    alphabet = string.ascii_letters + string.digits
    if include_special:
        alphabet += "!@#$%^&*"
    return ''.join(secrets.choice(alphabet) for _ in range(length))


def generate_jwt_secret() -> str:
    """Generate a JWT-compatible secret (base64-safe)."""
    return secrets.token_urlsafe(48)


def hash_password(password: str) -> str:
    """Hash a password using SHA256 (for non-critical uses)."""
    return hashlib.sha256(password.encode()).hexdigest()
