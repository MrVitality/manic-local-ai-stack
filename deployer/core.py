"""
Core deployment functionality for AI Stack.

Handles:
- Docker Compose file generation
- Environment file creation
- Directory structure setup
- Service orchestration
- Deployment execution
"""

import os
import sys
import subprocess
import shutil
import time
from pathlib import Path
from typing import Optional, Dict, List, Any, Callable
from dataclasses import dataclass, field
import yaml
import json
from datetime import datetime
import logging

from .config import (
    StackConfig, 
    ServiceConfig, 
    DeploymentProfile, 
    NetworkMode,
    generate_secret,
    generate_jwt_secret
)


# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


@dataclass
class DeploymentResult:
    """Result of a deployment operation."""
    success: bool
    message: str
    services_started: List[str] = field(default_factory=list)
    services_failed: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    duration_seconds: float = 0.0


class AIStackDeployer:
    """
    Main deployment orchestrator for the AI Stack.
    
    Handles complete lifecycle management:
    - Initial deployment
    - Updates and upgrades
    - Scaling services
    - Rolling restarts
    - Disaster recovery
    """
    
    def __init__(self, config: Optional[StackConfig] = None):
        """Initialize the deployer with configuration."""
        self.config = config or StackConfig()
        self._setup_directories()
        
    def _setup_directories(self):
        """Create required directory structure."""
        dirs = [
            self.config.base_dir,
            self.config.data_dir,
            self.config.config_dir,
            self.config.backup_dir,
            self.config.logs_dir,
            self.config.base_dir / "supabase",
            self.config.base_dir / "searxng",
            self.config.base_dir / "api",
            self.config.base_dir / "frontend",
            self.config.base_dir / "shared" / "extracted-images",
        ]
        for d in dirs:
            d.mkdir(parents=True, exist_ok=True)
    
    def generate_docker_compose(self) -> str:
        """Generate docker-compose.yml content."""
        compose = {
            "name": self.config.project_name,
            "services": {},
            "networks": {
                "ai-network": {
                    "driver": "bridge"
                }
            },
            "volumes": {}
        }
        
        # Add services
        for name, svc in self.config.get_enabled_services().items():
            service_def = self._build_service_definition(svc)
            compose["services"][name] = service_def
            
            # Collect volumes
            for vol in svc.volumes:
                if ":" in vol and not vol.startswith("./") and not vol.startswith("/"):
                    vol_name = vol.split(":")[0]
                    compose["volumes"][vol_name] = {}
        
        return yaml.dump(compose, default_flow_style=False, sort_keys=False)
    
    def _build_service_definition(self, svc: ServiceConfig) -> Dict[str, Any]:
        """Build a single service definition for docker-compose."""
        service_def = {
            "image": svc.full_image,
            "container_name": svc.name,
            "restart": svc.restart_policy,
        }
        
        if svc.ports:
            service_def["ports"] = svc.ports
        
        if svc.volumes:
            service_def["volumes"] = svc.volumes
        
        if svc.environment:
            service_def["environment"] = svc.environment
        
        # Always add env_file for shared secrets
        service_def["env_file"] = [".env"]
        
        if svc.depends_on:
            # Use advanced dependency syntax for health checks
            depends_on = {}
            for dep in svc.depends_on:
                dep_svc = self.config.services.get(dep)
                if dep_svc and dep_svc.healthcheck:
                    depends_on[dep] = {"condition": "service_healthy"}
                else:
                    depends_on[dep] = {"condition": "service_started"}
            service_def["depends_on"] = depends_on
        
        if svc.healthcheck:
            service_def["healthcheck"] = svc.healthcheck
        
        if svc.resources.memory != "1G" or svc.resources.cpus:
            service_def["deploy"] = {
                "resources": {
                    "limits": svc.resources.to_dict()
                }
            }
        
        if svc.networks:
            service_def["networks"] = svc.networks
        
        if svc.command:
            service_def["command"] = svc.command
        
        if svc.labels:
            service_def["labels"] = svc.labels
        
        if svc.profiles:
            service_def["profiles"] = svc.profiles
        
        return service_def
    
    def generate_env_file(self) -> str:
        """Generate .env file content with all secrets and configuration."""
        env_vars = []
        
        # Header
        env_vars.append("# ============================================================")
        env_vars.append("# Ultimate AI Stack - Environment Configuration")
        env_vars.append(f"# Generated: {datetime.now().isoformat()}")
        env_vars.append("# ============================================================")
        env_vars.append("")
        
        # General settings
        env_vars.append("# === GENERAL ===")
        env_vars.append(f"DOMAIN={self.config.domain}")
        env_vars.append(f"PROJECT_NAME={self.config.project_name}")
        env_vars.append("")
        
        # PostgreSQL / Supabase DB
        env_vars.append("# === POSTGRESQL / SUPABASE DATABASE ===")
        env_vars.append(f"POSTGRES_HOST={self.config.database.host}")
        env_vars.append(f"POSTGRES_PORT={self.config.database.port}")
        env_vars.append(f"POSTGRES_USER={self.config.database.user}")
        env_vars.append(f"POSTGRES_PASSWORD={self.config.database.password}")
        env_vars.append(f"POSTGRES_DB={self.config.database.database}")
        env_vars.append(f"DATABASE_URL={self.config.database.connection_string}")
        env_vars.append("")
        
        # Supabase specific
        env_vars.append("# === SUPABASE ===")
        env_vars.append(f"JWT_SECRET={self.config.supabase.jwt_secret}")
        env_vars.append(f"ANON_KEY={self.config.supabase.anon_key}")
        env_vars.append(f"SERVICE_ROLE_KEY={self.config.supabase.service_role_key}")
        env_vars.append(f"SUPABASE_URL={self.config.supabase.api_url}")
        env_vars.append(f"SUPABASE_ANON_KEY={self.config.supabase.anon_key}")
        env_vars.append(f"SUPABASE_SERVICE_ROLE_KEY={self.config.supabase.service_role_key}")
        env_vars.append("")
        
        # GoTrue (Supabase Auth)
        env_vars.append("# === GOTRUE (Supabase Auth) ===")
        env_vars.append("GOTRUE_API_HOST=0.0.0.0")
        env_vars.append("GOTRUE_API_PORT=9999")
        env_vars.append(f"GOTRUE_DB_DRIVER=postgres")
        env_vars.append(f"GOTRUE_DB_DATABASE_URL={self.config.database.connection_string}?search_path=auth")
        env_vars.append("GOTRUE_SITE_URL=http://localhost:3000")
        env_vars.append("GOTRUE_URI_ALLOW_LIST=*")
        env_vars.append("GOTRUE_DISABLE_SIGNUP=false")
        env_vars.append(f"GOTRUE_JWT_SECRET={self.config.supabase.jwt_secret}")
        env_vars.append("GOTRUE_JWT_EXP=3600")
        env_vars.append("GOTRUE_JWT_DEFAULT_GROUP_NAME=authenticated")
        env_vars.append("GOTRUE_EXTERNAL_EMAIL_ENABLED=true")
        env_vars.append("GOTRUE_MAILER_AUTOCONFIRM=true")
        env_vars.append("")
        
        # PostgREST
        env_vars.append("# === POSTGREST ===")
        env_vars.append(f"PGRST_DB_URI={self.config.database.connection_string}")
        env_vars.append("PGRST_DB_SCHEMAS=public,storage,graphql_public")
        env_vars.append("PGRST_DB_ANON_ROLE=anon")
        env_vars.append(f"PGRST_JWT_SECRET={self.config.supabase.jwt_secret}")
        env_vars.append("PGRST_DB_USE_LEGACY_GUCS=false")
        env_vars.append("")
        
        # Storage API
        env_vars.append("# === STORAGE API ===")
        env_vars.append("STORAGE_BACKEND=file")
        env_vars.append("FILE_STORAGE_BACKEND_PATH=/var/lib/storage")
        env_vars.append(f"POSTGREST_URL=http://supabase-rest:3000")
        env_vars.append(f"PGRST_JWT_SECRET={self.config.supabase.jwt_secret}")
        env_vars.append(f"DATABASE_URL={self.config.database.connection_string}")
        env_vars.append(f"ANON_KEY={self.config.supabase.anon_key}")
        env_vars.append(f"SERVICE_KEY={self.config.supabase.service_role_key}")
        env_vars.append("TENANT_ID=stub")
        env_vars.append("REGION=stub")
        env_vars.append("GLOBAL_S3_BUCKET=stub")
        env_vars.append("")
        
        # Kong
        env_vars.append("# === KONG API GATEWAY ===")
        env_vars.append("KONG_DATABASE=off")
        env_vars.append("KONG_DECLARATIVE_CONFIG=/var/lib/kong/kong.yml")
        env_vars.append("KONG_DNS_ORDER=LAST,A,CNAME")
        env_vars.append("KONG_PLUGINS=request-transformer,cors,key-auth,acl")
        env_vars.append("")
        
        # Studio
        env_vars.append("# === SUPABASE STUDIO ===")
        env_vars.append(f"STUDIO_DEFAULT_ORGANIZATION=Default Organization")
        env_vars.append(f"STUDIO_DEFAULT_PROJECT=Default Project")
        env_vars.append(f"SUPABASE_PUBLIC_URL=http://localhost:8000")
        env_vars.append(f"STUDIO_PG_META_URL=http://supabase-meta:8080")
        env_vars.append("")
        
        # Ollama
        env_vars.append("# === OLLAMA ===")
        env_vars.append(f"OLLAMA_HOST={self.config.ollama.host}")
        env_vars.append(f"OLLAMA_BASE_URL={self.config.ollama.base_url}")
        env_vars.append(f"OLLAMA_KEEP_ALIVE={self.config.ollama.keep_alive}")
        env_vars.append(f"OLLAMA_NUM_PARALLEL={self.config.ollama.num_parallel}")
        env_vars.append(f"OLLAMA_MAX_LOADED_MODELS={self.config.ollama.max_loaded_models}")
        env_vars.append("")
        
        # Langfuse
        env_vars.append("# === LANGFUSE ===")
        langfuse_db_password = generate_secret(32)
        env_vars.append(f"LANGFUSE_DB_PASSWORD={langfuse_db_password}")
        env_vars.append(f"LANGFUSE_DATABASE_URL=postgresql://langfuse:{langfuse_db_password}@langfuse-db:5432/langfuse")
        env_vars.append(f"NEXTAUTH_SECRET={generate_jwt_secret()}")
        env_vars.append(f"NEXTAUTH_URL=http://localhost:3002")
        env_vars.append(f"SALT={generate_secret(32)}")
        env_vars.append("TELEMETRY_ENABLED=false")
        env_vars.append("")
        
        # N8N
        env_vars.append("# === N8N ===")
        n8n_encryption_key = generate_secret(32)
        env_vars.append(f"N8N_ENCRYPTION_KEY={n8n_encryption_key}")
        env_vars.append(f"N8N_HOST={self.config.domain}")
        env_vars.append("N8N_PROTOCOL=https")
        env_vars.append(f"N8N_PORT=5678")
        env_vars.append(f"WEBHOOK_URL=https://{self.config.domain}/n8n/")
        env_vars.append("GENERIC_TIMEZONE=UTC")
        env_vars.append("N8N_DIAGNOSTICS_ENABLED=false")
        env_vars.append("N8N_PERSONALIZATION_ENABLED=false")
        env_vars.append("")
        
        # Flowise
        env_vars.append("# === FLOWISE ===")
        env_vars.append(f"FLOWISE_USERNAME=admin")
        env_vars.append(f"FLOWISE_PASSWORD={generate_secret(16)}")
        env_vars.append(f"FLOWISE_SECRETKEY_OVERWRITE={generate_secret(32)}")
        env_vars.append("")
        
        # Open WebUI
        env_vars.append("# === OPEN WEBUI ===")
        env_vars.append(f"WEBUI_SECRET_KEY={generate_secret(32)}")
        env_vars.append("WEBUI_AUTH=false")
        env_vars.append("ENABLE_RAG_WEB_SEARCH=true")
        env_vars.append("RAG_WEB_SEARCH_ENGINE=searxng")
        env_vars.append("SEARXNG_QUERY_URL=http://searxng:8080/search?q=<query>")
        env_vars.append("")
        
        # Neo4j (if enabled)
        if self.config.services.get("neo4j", ServiceConfig(name="")).enabled:
            env_vars.append("# === NEO4J ===")
            env_vars.append(f"NEO4J_PASSWORD={generate_secret(16)}")
            env_vars.append("NEO4J_AUTH=neo4j/${NEO4J_PASSWORD}")
            env_vars.append('NEO4J_PLUGINS=["apoc"]')
            env_vars.append("")
        
        # Qdrant
        env_vars.append("# === QDRANT ===")
        env_vars.append(f"QDRANT_API_KEY={generate_secret(32)}")
        env_vars.append("")
        
        # SearXNG
        env_vars.append("# === SEARXNG ===")
        env_vars.append(f"SEARXNG_SECRET={generate_secret(32)}")
        env_vars.append("")
        
        return "\n".join(env_vars)
    
    def generate_caddyfile(self) -> str:
        """Generate Caddyfile for reverse proxy."""
        caddyfile = []
        
        # Global options
        caddyfile.append("{")
        caddyfile.append("    # Global options")
        caddyfile.append("    email admin@{$DOMAIN}")
        if self.config.network_mode == NetworkMode.LOCALHOST:
            caddyfile.append("    local_certs")
        caddyfile.append("}")
        caddyfile.append("")
        
        domain = self.config.domain
        
        # Main site block
        caddyfile.append(f"{domain} {{")
        
        # Default route to frontend
        caddyfile.append("    # Frontend")
        caddyfile.append("    handle {")
        caddyfile.append("        reverse_proxy ai-frontend:3000")
        caddyfile.append("    }")
        caddyfile.append("")
        
        # API routes
        caddyfile.append("    # API")
        caddyfile.append("    handle /api/* {")
        caddyfile.append("        reverse_proxy ai-api:8080")
        caddyfile.append("    }")
        caddyfile.append("")
        
        # n8n
        caddyfile.append("    # n8n Workflow Automation")
        caddyfile.append("    handle /n8n/* {")
        caddyfile.append("        uri strip_prefix /n8n")
        caddyfile.append("        reverse_proxy n8n:5678")
        caddyfile.append("    }")
        caddyfile.append("")
        
        # Supabase
        caddyfile.append("    # Supabase API")
        caddyfile.append("    handle /supabase/* {")
        caddyfile.append("        uri strip_prefix /supabase")
        caddyfile.append("        reverse_proxy supabase-kong:8000")
        caddyfile.append("    }")
        caddyfile.append("")
        
        # Ollama
        caddyfile.append("    # Ollama LLM API")
        caddyfile.append("    handle /ollama/* {")
        caddyfile.append("        uri strip_prefix /ollama")
        caddyfile.append("        reverse_proxy ollama:11434")
        caddyfile.append("    }")
        caddyfile.append("")
        
        caddyfile.append("}")
        caddyfile.append("")
        
        # Subdomain routing (alternative to path-based)
        subdomains = {
            "n8n": "n8n:5678",
            "studio": "supabase-studio:3000",
            "chat": "open-webui:8080",
            "flowise": "flowise:3000",
            "langfuse": "langfuse:3000",
            "search": "searxng:8080",
        }
        
        for subdomain, upstream in subdomains.items():
            caddyfile.append(f"{subdomain}.{domain} {{")
            caddyfile.append(f"    reverse_proxy {upstream}")
            caddyfile.append("}")
            caddyfile.append("")
        
        return "\n".join(caddyfile)
    
    def generate_kong_config(self) -> str:
        """Generate Kong declarative configuration."""
        kong_config = {
            "_format_version": "2.1",
            "_transform": True,
            "services": [
                {
                    "name": "auth-v1-open",
                    "url": "http://supabase-auth:9999/verify",
                    "routes": [{"name": "auth-v1-open", "strip_path": True, "paths": ["/auth/v1/verify"]}],
                    "plugins": [{"name": "cors"}]
                },
                {
                    "name": "auth-v1-open-callback",
                    "url": "http://supabase-auth:9999/callback",
                    "routes": [{"name": "auth-v1-open-callback", "strip_path": True, "paths": ["/auth/v1/callback"]}],
                    "plugins": [{"name": "cors"}]
                },
                {
                    "name": "auth-v1-open-authorize",
                    "url": "http://supabase-auth:9999/authorize",
                    "routes": [{"name": "auth-v1-open-authorize", "strip_path": True, "paths": ["/auth/v1/authorize"]}],
                    "plugins": [{"name": "cors"}]
                },
                {
                    "name": "auth-v1",
                    "url": "http://supabase-auth:9999/",
                    "routes": [{"name": "auth-v1", "strip_path": True, "paths": ["/auth/v1/"]}],
                    "plugins": [
                        {"name": "cors"},
                        {"name": "key-auth", "config": {"hide_credentials": False}}
                    ]
                },
                {
                    "name": "rest-v1",
                    "url": "http://supabase-rest:3000/",
                    "routes": [{"name": "rest-v1", "strip_path": True, "paths": ["/rest/v1/"]}],
                    "plugins": [
                        {"name": "cors"},
                        {"name": "key-auth", "config": {"hide_credentials": False}}
                    ]
                },
                {
                    "name": "storage-v1",
                    "url": "http://supabase-storage:5000/",
                    "routes": [{"name": "storage-v1", "strip_path": True, "paths": ["/storage/v1/"]}],
                    "plugins": [
                        {"name": "cors"},
                        {"name": "key-auth", "config": {"hide_credentials": False}}
                    ]
                }
            ],
            "consumers": [
                {
                    "username": "ANON",
                    "keyauth_credentials": [{"key": "${ANON_KEY}"}]
                },
                {
                    "username": "SERVICE_ROLE",
                    "keyauth_credentials": [{"key": "${SERVICE_ROLE_KEY}"}]
                }
            ]
        }
        
        return yaml.dump(kong_config, default_flow_style=False, sort_keys=False)
    
    def generate_searxng_settings(self) -> str:
        """Generate SearXNG settings.yml."""
        settings = {
            "general": {
                "debug": False,
                "instance_name": "AI Stack Search",
                "contact_url": False,
                "enable_metrics": True
            },
            "search": {
                "safe_search": 0,
                "autocomplete": "google",
                "default_lang": "en",
                "formats": ["html", "json"]
            },
            "server": {
                "port": 8080,
                "bind_address": "0.0.0.0",
                "secret_key": "${SEARXNG_SECRET}",
                "limiter": True,
                "public_instance": False
            },
            "ui": {
                "static_use_hash": True,
                "default_theme": "simple",
                "infinite_scroll": True
            },
            "outgoing": {
                "request_timeout": 6.0,
                "max_request_timeout": 15.0,
                "pool_connections": 100,
                "pool_maxsize": 20,
                "enable_http2": True
            },
            "engines": [
                {"name": "google", "engine": "google", "shortcut": "g"},
                {"name": "duckduckgo", "engine": "duckduckgo", "shortcut": "ddg"},
                {"name": "wikipedia", "engine": "wikipedia", "shortcut": "wp"},
                {"name": "github", "engine": "github", "shortcut": "gh"},
                {"name": "arxiv", "engine": "arxiv", "shortcut": "ar", "categories": ["science"]}
            ]
        }
        
        return yaml.dump(settings, default_flow_style=False)
    
    def write_all_configs(self):
        """Write all configuration files to disk."""
        base = self.config.base_dir
        
        # Docker Compose
        compose_path = base / "docker-compose.yml"
        with open(compose_path, "w") as f:
            f.write(self.generate_docker_compose())
        logger.info(f"Written: {compose_path}")
        
        # Environment file
        env_path = base / ".env"
        with open(env_path, "w") as f:
            f.write(self.generate_env_file())
        os.chmod(env_path, 0o600)  # Secure permissions
        logger.info(f"Written: {env_path}")
        
        # Caddyfile
        caddy_path = base / "Caddyfile"
        with open(caddy_path, "w") as f:
            f.write(self.generate_caddyfile())
        logger.info(f"Written: {caddy_path}")
        
        # Kong configuration
        kong_dir = base / "supabase"
        kong_dir.mkdir(parents=True, exist_ok=True)
        kong_path = kong_dir / "kong.yml"
        with open(kong_path, "w") as f:
            f.write(self.generate_kong_config())
        logger.info(f"Written: {kong_path}")
        
        # SearXNG settings
        searxng_dir = base / "searxng"
        searxng_dir.mkdir(parents=True, exist_ok=True)
        searxng_path = searxng_dir / "settings.yml"
        with open(searxng_path, "w") as f:
            f.write(self.generate_searxng_settings())
        logger.info(f"Written: {searxng_path}")
        
        # Stack config (for reloading)
        self.config.save(self.config.config_dir / "stack-config.yaml")
        logger.info(f"Written: {self.config.config_dir / 'stack-config.yaml'}")
    
    def deploy(
        self, 
        pull: bool = True, 
        build: bool = False,
        progress_callback: Optional[Callable[[str], None]] = None
    ) -> DeploymentResult:
        """
        Deploy the entire stack.
        
        Args:
            pull: Whether to pull latest images
            build: Whether to build custom images
            progress_callback: Optional callback for progress updates
        
        Returns:
            DeploymentResult with deployment status
        """
        start_time = time.time()
        result = DeploymentResult(success=True, message="")
        
        def progress(msg: str):
            logger.info(msg)
            if progress_callback:
                progress_callback(msg)
        
        try:
            # Validate configuration
            progress("Validating configuration...")
            issues = self.config.validate()
            if issues:
                result.warnings.extend(issues)
                progress(f"Configuration warnings: {len(issues)}")
            
            # Write configuration files
            progress("Writing configuration files...")
            self.write_all_configs()
            
            # Change to base directory
            os.chdir(self.config.base_dir)
            
            # Pull images if requested
            if pull:
                progress("Pulling Docker images...")
                subprocess.run(
                    ["docker", "compose", "pull"],
                    check=True,
                    capture_output=True
                )
            
            # Build if requested
            if build:
                progress("Building custom images...")
                subprocess.run(
                    ["docker", "compose", "build"],
                    check=True,
                    capture_output=True
                )
            
            # Start services in dependency order
            progress("Starting services...")
            
            # Start infrastructure first
            infra_services = ["supabase-db", "redis", "langfuse-db"]
            progress("Starting infrastructure services...")
            subprocess.run(
                ["docker", "compose", "up", "-d"] + infra_services,
                check=True,
                capture_output=True
            )
            result.services_started.extend(infra_services)
            
            # Wait for databases
            progress("Waiting for databases to be ready...")
            time.sleep(10)
            
            # Start dependent services
            progress("Starting application services...")
            subprocess.run(
                ["docker", "compose", "up", "-d"],
                check=True,
                capture_output=True
            )
            
            # Get all started services
            for name in self.config.get_enabled_services():
                if name not in result.services_started:
                    result.services_started.append(name)
            
            result.message = f"Successfully deployed {len(result.services_started)} services"
            
        except subprocess.CalledProcessError as e:
            result.success = False
            result.message = f"Deployment failed: {e.stderr.decode() if e.stderr else str(e)}"
            logger.error(result.message)
            
        except Exception as e:
            result.success = False
            result.message = f"Deployment error: {str(e)}"
            logger.error(result.message)
        
        result.duration_seconds = time.time() - start_time
        return result
    
    def stop(self, remove_volumes: bool = False) -> DeploymentResult:
        """Stop all services."""
        try:
            os.chdir(self.config.base_dir)
            cmd = ["docker", "compose", "down"]
            if remove_volumes:
                cmd.append("-v")
            subprocess.run(cmd, check=True)
            return DeploymentResult(
                success=True,
                message="All services stopped"
            )
        except Exception as e:
            return DeploymentResult(
                success=False,
                message=f"Failed to stop services: {str(e)}"
            )
    
    def restart(self, service: Optional[str] = None) -> DeploymentResult:
        """Restart services."""
        try:
            os.chdir(self.config.base_dir)
            cmd = ["docker", "compose", "restart"]
            if service:
                cmd.append(service)
            subprocess.run(cmd, check=True)
            return DeploymentResult(
                success=True,
                message=f"Restarted {'all services' if not service else service}"
            )
        except Exception as e:
            return DeploymentResult(
                success=False,
                message=f"Failed to restart: {str(e)}"
            )
    
    def logs(self, service: Optional[str] = None, follow: bool = False, tail: int = 100):
        """View service logs."""
        os.chdir(self.config.base_dir)
        cmd = ["docker", "compose", "logs"]
        if follow:
            cmd.append("-f")
        cmd.extend(["--tail", str(tail)])
        if service:
            cmd.append(service)
        subprocess.run(cmd)
    
    def status(self) -> Dict[str, Any]:
        """Get status of all services."""
        try:
            os.chdir(self.config.base_dir)
            result = subprocess.run(
                ["docker", "compose", "ps", "--format", "json"],
                capture_output=True,
                text=True
            )
            if result.returncode == 0:
                services = []
                for line in result.stdout.strip().split("\n"):
                    if line:
                        services.append(json.loads(line))
                return {"success": True, "services": services}
            return {"success": False, "error": result.stderr}
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    def update(self, services: Optional[List[str]] = None) -> DeploymentResult:
        """Update services to latest images."""
        try:
            os.chdir(self.config.base_dir)
            
            # Pull new images
            pull_cmd = ["docker", "compose", "pull"]
            if services:
                pull_cmd.extend(services)
            subprocess.run(pull_cmd, check=True)
            
            # Recreate with new images
            up_cmd = ["docker", "compose", "up", "-d", "--force-recreate"]
            if services:
                up_cmd.extend(services)
            subprocess.run(up_cmd, check=True)
            
            return DeploymentResult(
                success=True,
                message=f"Updated {services if services else 'all services'}"
            )
        except Exception as e:
            return DeploymentResult(
                success=False,
                message=f"Update failed: {str(e)}"
            )
