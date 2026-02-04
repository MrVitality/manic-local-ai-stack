#!/usr/bin/env python3
"""
Ultimate AI Stack - Quick Deploy Script with Tailscale + Pydantic AI

Deploys the entire AI stack configured for Tailscale networking
and includes Pydantic AI integration service.

Usage:
    python deploy.py [--profile PROFILE] [--memory GB] [--tailscale-ip IP]

Requirements:
    - Docker & Docker Compose v2+
    - Python 3.10+
    - Tailscale installed and connected
"""

import os
import sys
import subprocess
import secrets
import string
import json
import time
from pathlib import Path
from datetime import datetime
from typing import Dict, Any, List, Optional

# Check Python version
if sys.version_info < (3, 10):
    print("Error: Python 3.10+ required")
    sys.exit(1)

try:
    import yaml
    import requests
except ImportError:
    print("Installing required packages...")
    subprocess.run([sys.executable, "-m", "pip", "install", "pyyaml", "requests", "-q"])
    import yaml
    import requests


# Default Tailscale IP - CHANGE THIS to your Tailscale IP
DEFAULT_TAILSCALE_IP = "100.100.180.114"

# Alternate ports to avoid conflicts with existing Dokploy services
# Set to True if you have existing Supabase/Redis running
USE_ALTERNATE_PORTS = True

PORTS = {
    "postgres": 5433 if USE_ALTERNATE_PORTS else 5432,      # Default: 5432
    "redis": 6380 if USE_ALTERNATE_PORTS else 6379,          # Default: 6379
    "supabase_api": 8001 if USE_ALTERNATE_PORTS else 8000,   # Default: 8000
    "supabase_ssl": 8444 if USE_ALTERNATE_PORTS else 8443,   # Default: 8443
    "supabase_studio": 3005 if USE_ALTERNATE_PORTS else 3001, # Default: 3001
    "ollama": 11434,          # Usually no conflict
    "qdrant": 6333,           # Usually no conflict
    "qdrant_grpc": 6334,      # Usually no conflict
    "n8n": 5679 if USE_ALTERNATE_PORTS else 5678,            # Default: 5678
    "open_webui": 3006 if USE_ALTERNATE_PORTS else 3003,     # Default: 3003
    "langfuse": 3007 if USE_ALTERNATE_PORTS else 3002,       # Default: 3002
    "flowise": 3008 if USE_ALTERNATE_PORTS else 3004,        # Default: 3004
    "searxng": 8889 if USE_ALTERNATE_PORTS else 8888,        # Default: 8888
    "pydantic_ai": 8082 if USE_ALTERNATE_PORTS else 8080,    # Default: 8080
}


def generate_secret(length: int = 32) -> str:
    """Generate a cryptographically secure random secret."""
    alphabet = string.ascii_letters + string.digits
    return ''.join(secrets.choice(alphabet) for _ in range(length))


def print_banner():
    print("""
╔═══════════════════════════════════════════════════════════════════╗
║          🚀 Ultimate AI Stack Deployer + Pydantic AI              ║
║                                                                   ║
║  Self-hosted AI infrastructure with Tailscale networking          ║
╚═══════════════════════════════════════════════════════════════════╝
""")


class QuickDeployer:
    """Simplified deployer for quick setup with Tailscale."""
    
    def __init__(
        self,
        base_dir: Path,
        profile: str = "standard",
        tailscale_ip: str = DEFAULT_TAILSCALE_IP,
        memory_gb: int = 16
    ):
        self.base_dir = base_dir
        self.profile = profile
        self.tailscale_ip = tailscale_ip
        self.memory_gb = memory_gb
        
        # Generate secrets
        self.postgres_password = generate_secret(32)
        self.jwt_secret = generate_secret(64)
        self.anon_key = generate_secret(64)
        self.service_role_key = generate_secret(64)
        self.langfuse_secret = generate_secret(32)
        self.langfuse_db_password = generate_secret(16)
        
    def setup_directories(self):
        """Create required directories."""
        dirs = [
            self.base_dir,
            self.base_dir / "supabase",
            self.base_dir / "searxng",
            self.base_dir / "config",
            self.base_dir / "backups",
            self.base_dir / "logs",
            self.base_dir / "pydantic-ai",
        ]
        for d in dirs:
            d.mkdir(parents=True, exist_ok=True)
        print(f"✓ Created directories in {self.base_dir}")
    
    def generate_docker_compose(self) -> str:
        """Generate docker-compose.yml with Tailscale networking."""
        
        # Memory allocations based on profile
        memory_config = {
            "minimal": {
                "ollama": "4G", "qdrant": "1G", "redis": "256M",
                "supabase-db": "1G", "open-webui": "1G", "n8n": "512M",
                "pydantic-ai": "512M"
            },
            "standard": {
                "ollama": "8G", "qdrant": "2G", "redis": "512M",
                "supabase-db": "2G", "open-webui": "2G", "n8n": "1G",
                "langfuse": "1G", "flowise": "1G", "pydantic-ai": "1G"
            },
            "full": {
                "ollama": "12G", "qdrant": "4G", "redis": "1G",
                "supabase-db": "4G", "open-webui": "2G", "n8n": "2G",
                "langfuse": "2G", "flowise": "2G", "neo4j": "4G",
                "pydantic-ai": "1G"
            }
        }
        
        mem = memory_config.get(self.profile, memory_config["standard"])
        ts = self.tailscale_ip
        p = PORTS  # Port mappings
        
        compose = {
            "name": "ultimate-ai-stack",
            "services": {
                "ollama": {
                    "image": "ollama/ollama:latest",
                    "container_name": "ollama",
                    "restart": "unless-stopped",
                    "ports": [f"{ts}:{p['ollama']}:11434"],
                    "volumes": ["ollama-data:/root/.ollama"],
                    "env_file": [".env"],
                    "deploy": {"resources": {"limits": {"memory": mem["ollama"]}}},
                    "networks": ["ai-network"],
                    "healthcheck": {
                        "test": ["CMD", "curl", "-f", "http://localhost:11434/api/tags"],
                        "interval": "30s",
                        "timeout": "10s",
                        "retries": 3,
                        "start_period": "60s"
                    }
                },
                "qdrant": {
                    "image": "qdrant/qdrant:latest",
                    "container_name": "qdrant",
                    "restart": "unless-stopped",
                    "ports": [f"{ts}:{p['qdrant']}:6333", f"{ts}:{p['qdrant_grpc']}:6334"],
                    "volumes": ["qdrant-data:/qdrant/storage"],
                    "deploy": {"resources": {"limits": {"memory": mem["qdrant"]}}},
                    "networks": ["ai-network"]
                },
                "redis": {
                    "image": "redis:7-alpine",
                    "container_name": "ai-redis",
                    "restart": "unless-stopped",
                    "ports": [f"{ts}:{p['redis']}:6379"],
                    "volumes": ["redis-data:/data"],
                    "command": "redis-server --appendonly yes --maxmemory 256mb --maxmemory-policy allkeys-lru",
                    "deploy": {"resources": {"limits": {"memory": mem["redis"]}}},
                    "networks": ["ai-network"],
                    "healthcheck": {"test": ["CMD", "redis-cli", "ping"], "interval": "10s", "timeout": "5s", "retries": 5}
                },
                "supabase-db": {
                    "image": "supabase/postgres:15.1.1.78",
                    "container_name": "ai-supabase-db",
                    "restart": "unless-stopped",
                    "ports": [f"{ts}:{p['postgres']}:5432"],
                    "volumes": [
                        "supabase-db-data:/var/lib/postgresql/data",
                        "./supabase/init.sql:/docker-entrypoint-initdb.d/init.sql:ro"
                    ],
                    "env_file": [".env"],
                    "command": ["postgres", "-c", "wal_level=logical", "-c", "max_connections=200",
                               "-c", "shared_buffers=256MB", "-c", "effective_cache_size=768MB", "-c", "listen_addresses=*"],
                    "deploy": {"resources": {"limits": {"memory": mem["supabase-db"]}}},
                    "networks": ["ai-network"],
                    "healthcheck": {"test": ["CMD-SHELL", "pg_isready -U postgres -d postgres"],
                                   "interval": "10s", "timeout": "5s", "retries": 5, "start_period": "30s"}
                },
                "supabase-auth": {
                    "image": "supabase/gotrue:v2.143.0",
                    "container_name": "ai-supabase-auth",
                    "restart": "unless-stopped",
                    "depends_on": {"supabase-db": {"condition": "service_healthy"}},
                    "env_file": [".env"],
                    "networks": ["ai-network"]
                },
                "supabase-rest": {
                    "image": "postgrest/postgrest:v12.0.1",
                    "container_name": "ai-supabase-rest",
                    "restart": "unless-stopped",
                    "depends_on": {"supabase-db": {"condition": "service_healthy"}},
                    "env_file": [".env"],
                    "networks": ["ai-network"]
                },
                "supabase-meta": {
                    "image": "supabase/postgres-meta:v0.80.0",
                    "container_name": "ai-supabase-meta",
                    "restart": "unless-stopped",
                    "depends_on": {"supabase-db": {"condition": "service_healthy"}},
                    "environment": {
                        "PG_META_PORT": "8080",
                        "PG_META_DB_URL": f"postgresql://postgres:{self.postgres_password}@supabase-db:5432/postgres"
                    },
                    "networks": ["ai-network"]
                },
                "supabase-storage": {
                    "image": "supabase/storage-api:v0.46.4",
                    "container_name": "ai-supabase-storage",
                    "restart": "unless-stopped",
                    "depends_on": {"supabase-db": {"condition": "service_healthy"}},
                    "env_file": [".env"],
                    "volumes": ["supabase-storage-data:/var/lib/storage"],
                    "networks": ["ai-network"]
                },
                "supabase-kong": {
                    "image": "kong:2.8.1",
                    "container_name": "ai-supabase-kong",
                    "restart": "unless-stopped",
                    "ports": [f"{ts}:{p['supabase_api']}:8000", f"{ts}:{p['supabase_ssl']}:8443"],
                    "env_file": [".env"],
                    "volumes": ["./supabase/kong.yml:/var/lib/kong/kong.yml:ro"],
                    "networks": ["ai-network"]
                },
                "supabase-studio": {
                    "image": "supabase/studio:20240101-8e4a094",
                    "container_name": "ai-supabase-studio",
                    "restart": "unless-stopped",
                    "ports": [f"{ts}:{p['supabase_studio']}:3000"],
                    "depends_on": ["supabase-meta"],
                    "env_file": [".env"],
                    "networks": ["ai-network"]
                },
                "n8n": {
                    "image": "n8nio/n8n:latest",
                    "container_name": "ai-n8n",
                    "restart": "unless-stopped",
                    "ports": [f"{ts}:{p['n8n']}:5678"],
                    "volumes": ["n8n-data:/home/node/.n8n"],
                    "env_file": [".env"],
                    "deploy": {"resources": {"limits": {"memory": mem["n8n"]}}},
                    "networks": ["ai-network"]
                },
                "open-webui": {
                    "image": "ghcr.io/open-webui/open-webui:main",
                    "container_name": "ai-open-webui",
                    "restart": "unless-stopped",
                    "ports": [f"{ts}:{p['open_webui']}:8080"],
                    "volumes": ["open-webui-data:/app/backend/data"],
                    "environment": {"OLLAMA_BASE_URL": "http://ollama:11434", "WEBUI_AUTH": "false"},
                    "deploy": {"resources": {"limits": {"memory": mem["open-webui"]}}},
                    "networks": ["ai-network"]
                },
                "searxng": {
                    "image": "searxng/searxng:latest",
                    "container_name": "ai-searxng",
                    "restart": "unless-stopped",
                    "ports": [f"{ts}:{p['searxng']}:8080"],
                    "volumes": ["./searxng:/etc/searxng"],
                    "deploy": {"resources": {"limits": {"memory": "512M"}}},
                    "networks": ["ai-network"]
                },
                "pydantic-ai": {
                    "image": "python:3.11-slim",
                    "container_name": "ai-pydantic-ai",
                    "restart": "unless-stopped",
                    "ports": [f"{ts}:{p['pydantic_ai']}:8080"],
                    "volumes": ["./pydantic-ai:/app", "pydantic-ai-data:/app/data"],
                    "working_dir": "/app",
                    "command": ["sh", "-c",
                        "pip install -q pydantic-ai pydantic-ai-slim[openai] pydantic-settings fastapi uvicorn httpx asyncpg && python pydantic_ai_service.py"],
                    "environment": {
                        "OLLAMA_EXTERNAL_URL": f"http://{ts}:{p['ollama']}",
                        "SUPABASE_URL": f"http://{ts}:{p['supabase_api']}",
                        "DATABASE_URL": f"postgresql://postgres:{self.postgres_password}@supabase-db:5432/postgres",
                        "QDRANT_URL": f"http://{ts}:{p['qdrant']}"
                    },
                    "depends_on": ["ollama", "supabase-db"],
                    "deploy": {"resources": {"limits": {"memory": mem["pydantic-ai"]}}},
                    "networks": ["ai-network"]
                }
            },
            "networks": {"ai-network": {"driver": "bridge"}},
            "volumes": {
                "ollama-data": {}, "qdrant-data": {}, "redis-data": {},
                "supabase-db-data": {}, "supabase-storage-data": {},
                "n8n-data": {}, "open-webui-data": {}, "pydantic-ai-data": {}
            }
        }
        
        # Add langfuse/flowise for standard/full
        if self.profile in ["standard", "full"]:
            compose["services"]["langfuse-db"] = {
                "image": "postgres:15-alpine",
                "container_name": "ai-langfuse-db",
                "restart": "unless-stopped",
                "volumes": ["langfuse-db-data:/var/lib/postgresql/data"],
                "environment": {"POSTGRES_USER": "langfuse", "POSTGRES_PASSWORD": self.langfuse_db_password, "POSTGRES_DB": "langfuse"},
                "deploy": {"resources": {"limits": {"memory": "512M"}}},
                "networks": ["ai-network"]
            }
            compose["services"]["langfuse"] = {
                "image": "langfuse/langfuse:2",
                "container_name": "ai-langfuse",
                "restart": "unless-stopped",
                "ports": [f"{ts}:{p['langfuse']}:3000"],
                "depends_on": ["langfuse-db"],
                "environment": {
                    "DATABASE_URL": f"postgresql://langfuse:{self.langfuse_db_password}@langfuse-db:5432/langfuse",
                    "NEXTAUTH_SECRET": self.langfuse_secret, "NEXTAUTH_URL": f"http://{ts}:{p['langfuse']}",
                    "SALT": generate_secret(32), "TELEMETRY_ENABLED": "false"
                },
                "deploy": {"resources": {"limits": {"memory": mem.get("langfuse", "1G")}}},
                "networks": ["ai-network"]
            }
            compose["services"]["flowise"] = {
                "image": "flowiseai/flowise:latest",
                "container_name": "ai-flowise",
                "restart": "unless-stopped",
                "ports": [f"{ts}:{p['flowise']}:3000"],
                "volumes": ["flowise-data:/root/.flowise"],
                "environment": {"FLOWISE_USERNAME": "admin", "FLOWISE_PASSWORD": generate_secret(16)},
                "deploy": {"resources": {"limits": {"memory": mem.get("flowise", "1G")}}},
                "networks": ["ai-network"]
            }
            compose["volumes"]["langfuse-db-data"] = {}
            compose["volumes"]["flowise-data"] = {}
        
        # Add neo4j for full
        if self.profile == "full":
            compose["services"]["neo4j"] = {
                "image": "neo4j:5-community",
                "container_name": "ai-neo4j",
                "restart": "unless-stopped",
                "ports": [f"{ts}:7474:7474", f"{ts}:7687:7687"],
                "volumes": ["neo4j-data:/data", "neo4j-logs:/logs"],
                "environment": {"NEO4J_AUTH": f"neo4j/{generate_secret(16)}", "NEO4J_PLUGINS": '["apoc"]'},
                "deploy": {"resources": {"limits": {"memory": mem.get("neo4j", "4G")}}},
                "networks": ["ai-network"]
            }
            compose["volumes"]["neo4j-data"] = {}
            compose["volumes"]["neo4j-logs"] = {}
        
        return yaml.dump(compose, default_flow_style=False, sort_keys=False)
    
    def generate_env_file(self) -> str:
        """Generate .env file with Tailscale URLs."""
        ts = self.tailscale_ip
        p = PORTS
        return f"""# Ultimate AI Stack - Environment Configuration
# Generated: {datetime.now().isoformat()}
# Tailscale IP: {ts}
# Using alternate ports: {USE_ALTERNATE_PORTS}

# === POSTGRESQL ===
POSTGRES_USER=postgres
POSTGRES_PASSWORD={self.postgres_password}
POSTGRES_DB=postgres
DATABASE_URL=postgresql://postgres:{self.postgres_password}@supabase-db:5432/postgres

# === SUPABASE ===
JWT_SECRET={self.jwt_secret}
ANON_KEY={self.anon_key}
SERVICE_ROLE_KEY={self.service_role_key}
SUPABASE_URL=http://{ts}:{p['supabase_api']}

# === GOTRUE ===
GOTRUE_API_HOST=0.0.0.0
GOTRUE_API_PORT=9999
GOTRUE_DB_DRIVER=postgres
GOTRUE_DB_DATABASE_URL=postgresql://postgres:{self.postgres_password}@supabase-db:5432/postgres?search_path=auth
GOTRUE_SITE_URL=http://{ts}:{p['open_webui']}
GOTRUE_URI_ALLOW_LIST=*
GOTRUE_DISABLE_SIGNUP=false
GOTRUE_JWT_SECRET={self.jwt_secret}
GOTRUE_JWT_EXP=3600
GOTRUE_JWT_DEFAULT_GROUP_NAME=authenticated
GOTRUE_EXTERNAL_EMAIL_ENABLED=true
GOTRUE_MAILER_AUTOCONFIRM=true

# === POSTGREST ===
PGRST_DB_URI=postgresql://postgres:{self.postgres_password}@supabase-db:5432/postgres
PGRST_DB_SCHEMAS=public,storage,graphql_public,rag
PGRST_DB_ANON_ROLE=anon
PGRST_JWT_SECRET={self.jwt_secret}
PGRST_DB_USE_LEGACY_GUCS=false

# === STORAGE ===
STORAGE_BACKEND=file
FILE_STORAGE_BACKEND_PATH=/var/lib/storage
POSTGREST_URL=http://supabase-rest:3000
TENANT_ID=stub
REGION=stub
GLOBAL_S3_BUCKET=stub

# === KONG ===
KONG_DATABASE=off
KONG_DECLARATIVE_CONFIG=/var/lib/kong/kong.yml
KONG_DNS_ORDER=LAST,A,CNAME
KONG_PLUGINS=request-transformer,cors,key-auth,acl

# === STUDIO ===
STUDIO_DEFAULT_ORGANIZATION=Default Organization
STUDIO_DEFAULT_PROJECT=Default Project
SUPABASE_PUBLIC_URL=http://{ts}:{p['supabase_api']}
STUDIO_PG_META_URL=http://supabase-meta:8080

# === OLLAMA ===
OLLAMA_BASE_URL=http://ollama:11434
OLLAMA_EXTERNAL_URL=http://{ts}:{p['ollama']}
OLLAMA_KEEP_ALIVE=5m

# === N8N ===
N8N_ENCRYPTION_KEY={generate_secret(32)}
N8N_HOST={ts}
N8N_PORT={p['n8n']}
WEBHOOK_URL=http://{ts}:{p['n8n']}/
GENERIC_TIMEZONE=UTC

# === PYDANTIC AI ===
PYDANTIC_AI_MODEL=llama3.2:3b
PYDANTIC_AI_EMBEDDING_MODEL=nomic-embed-text
"""
    
    def generate_kong_config(self) -> str:
        """Generate Kong configuration."""
        config = {
            "_format_version": "2.1", "_transform": True,
            "services": [
                {"name": "auth-v1-open", "url": "http://supabase-auth:9999/verify",
                 "routes": [{"name": "auth-v1-open", "strip_path": True, "paths": ["/auth/v1/verify"]}],
                 "plugins": [{"name": "cors"}]},
                {"name": "auth-v1", "url": "http://supabase-auth:9999/",
                 "routes": [{"name": "auth-v1", "strip_path": True, "paths": ["/auth/v1/"]}],
                 "plugins": [{"name": "cors"}, {"name": "key-auth", "config": {"hide_credentials": False}}]},
                {"name": "rest-v1", "url": "http://supabase-rest:3000/",
                 "routes": [{"name": "rest-v1", "strip_path": True, "paths": ["/rest/v1/"]}],
                 "plugins": [{"name": "cors"}, {"name": "key-auth", "config": {"hide_credentials": False}}]},
                {"name": "storage-v1", "url": "http://supabase-storage:5000/",
                 "routes": [{"name": "storage-v1", "strip_path": True, "paths": ["/storage/v1/"]}],
                 "plugins": [{"name": "cors"}, {"name": "key-auth", "config": {"hide_credentials": False}}]}
            ],
            "consumers": [
                {"username": "ANON", "keyauth_credentials": [{"key": self.anon_key}]},
                {"username": "SERVICE_ROLE", "keyauth_credentials": [{"key": self.service_role_key}]}
            ]
        }
        return yaml.dump(config, default_flow_style=False)
    
    def write_sql_init(self):
        """Write SQL initialization file."""
        sql = """-- Ultimate AI Stack - PostgreSQL Initialization
-- Optimized for Pydantic AI + RAG with HNSW indexes

CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pgcrypto";
CREATE EXTENSION IF NOT EXISTS "pg_trgm";
CREATE EXTENSION IF NOT EXISTS "vector";

CREATE SCHEMA IF NOT EXISTS rag;

-- Documents
CREATE TABLE IF NOT EXISTS rag.documents (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id UUID,
    filename TEXT NOT NULL,
    content_type TEXT,
    file_size BIGINT,
    status TEXT DEFAULT 'pending',
    chunk_count INTEGER DEFAULT 0,
    metadata JSONB DEFAULT '{}',
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_documents_user_id ON rag.documents(user_id);
CREATE INDEX IF NOT EXISTS idx_documents_status ON rag.documents(status);

-- Chunks with 768-dim embeddings for nomic-embed-text
CREATE TABLE IF NOT EXISTS rag.chunks (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    document_id UUID REFERENCES rag.documents(id) ON DELETE CASCADE,
    chunk_index INTEGER NOT NULL,
    content TEXT NOT NULL,
    content_tokens INTEGER,
    embedding VECTOR(768),
    metadata JSONB DEFAULT '{}',
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- HNSW index for fast vector search
CREATE INDEX IF NOT EXISTS idx_chunks_embedding_hnsw 
ON rag.chunks USING hnsw (embedding vector_cosine_ops) WITH (m = 16, ef_construction = 64);

-- Full-text search
CREATE INDEX IF NOT EXISTS idx_chunks_content_fts 
ON rag.chunks USING gin (to_tsvector('english', content));

CREATE INDEX IF NOT EXISTS idx_chunks_content_trgm 
ON rag.chunks USING gin (content gin_trgm_ops);

CREATE INDEX IF NOT EXISTS idx_chunks_document_id ON rag.chunks(document_id);

-- Collections
CREATE TABLE IF NOT EXISTS rag.collections (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id UUID,
    name TEXT NOT NULL,
    description TEXT,
    metadata JSONB DEFAULT '{}',
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Conversations
CREATE TABLE IF NOT EXISTS rag.conversations (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id UUID,
    title TEXT,
    model TEXT DEFAULT 'llama3.2:3b',
    metadata JSONB DEFAULT '{}',
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Messages
CREATE TABLE IF NOT EXISTS rag.messages (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    conversation_id UUID REFERENCES rag.conversations(id) ON DELETE CASCADE,
    role TEXT NOT NULL,
    content TEXT NOT NULL,
    tokens_used INTEGER,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Vector similarity search function
CREATE OR REPLACE FUNCTION rag.search_similar_chunks(
    query_embedding VECTOR(768),
    match_threshold FLOAT DEFAULT 0.7,
    match_count INT DEFAULT 5
)
RETURNS TABLE (id UUID, document_id UUID, content TEXT, metadata JSONB, similarity FLOAT)
LANGUAGE plpgsql STABLE AS $$
BEGIN
    PERFORM set_config('hnsw.ef_search', '100', true);
    RETURN QUERY
    SELECT c.id, c.document_id, c.content, c.metadata,
           1 - (c.embedding <=> query_embedding) AS similarity
    FROM rag.chunks c
    WHERE 1 - (c.embedding <=> query_embedding) > match_threshold
    ORDER BY c.embedding <=> query_embedding
    LIMIT match_count;
END;
$$;

-- Hybrid search function (vector + keyword)
CREATE OR REPLACE FUNCTION rag.hybrid_search(
    query_text TEXT,
    query_embedding VECTOR(768),
    match_count INT DEFAULT 10,
    keyword_weight FLOAT DEFAULT 0.3
)
RETURNS TABLE (id UUID, document_id UUID, content TEXT, metadata JSONB, 
               vector_score FLOAT, keyword_score FLOAT, combined_score FLOAT)
LANGUAGE plpgsql STABLE AS $$
DECLARE rrf_k INT := 60;
BEGIN
    PERFORM set_config('hnsw.ef_search', '100', true);
    RETURN QUERY
    WITH 
    vector_results AS (
        SELECT c.id, c.document_id, c.content, c.metadata,
               1 - (c.embedding <=> query_embedding) AS v_score,
               ROW_NUMBER() OVER (ORDER BY c.embedding <=> query_embedding) AS v_rank
        FROM rag.chunks c
        ORDER BY c.embedding <=> query_embedding LIMIT match_count * 2
    ),
    keyword_results AS (
        SELECT c.id, ts_rank_cd(to_tsvector('english', c.content), 
               websearch_to_tsquery('english', query_text), 32) AS k_score,
               ROW_NUMBER() OVER (ORDER BY ts_rank_cd(to_tsvector('english', c.content),
               websearch_to_tsquery('english', query_text), 32) DESC) AS k_rank
        FROM rag.chunks c
        WHERE to_tsvector('english', c.content) @@ websearch_to_tsquery('english', query_text)
        LIMIT match_count * 2
    ),
    fused AS (
        SELECT v.id, v.document_id, v.content, v.metadata, v.v_score,
               COALESCE(k.k_score, 0) AS k_score,
               (1.0 - keyword_weight) * (1.0 / (rrf_k + v.v_rank)) +
               keyword_weight * (1.0 / (rrf_k + COALESCE(k.k_rank, match_count * 2 + 1))) AS rrf_score
        FROM vector_results v LEFT JOIN keyword_results k ON v.id = k.id
    )
    SELECT f.id, f.document_id, f.content, f.metadata,
           f.v_score, f.k_score, f.rrf_score
    FROM fused f ORDER BY f.rrf_score DESC LIMIT match_count;
END;
$$;

DO $$ BEGIN RAISE NOTICE 'Database initialized for Pydantic AI + RAG!'; END $$;
"""
        (self.base_dir / "supabase" / "init.sql").write_text(sql)
        print("✓ Created supabase/init.sql")
    
    def write_pydantic_ai_service(self):
        """Write the Pydantic AI service."""
        service = '''"""Pydantic AI Service - Production-ready AI agent service."""

import os
import logging
from typing import Optional, List, Dict, Any

from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic_ai import Agent
from pydantic_ai.models.openai import OpenAIChatModel
from pydantic_ai.providers.ollama import OllamaProvider

logger = logging.getLogger(__name__)


class Settings(BaseSettings):
    ollama_base_url: str = Field(default="http://100.100.180.114:11434", alias="OLLAMA_EXTERNAL_URL")
    ollama_model: str = Field(default="llama3.2:3b", alias="PYDANTIC_AI_MODEL")
    embedding_model: str = Field(default="nomic-embed-text", alias="PYDANTIC_AI_EMBEDDING_MODEL")
    api_host: str = Field(default="0.0.0.0")
    api_port: int = Field(default=8080)
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


settings = Settings()


class ChatResponse(BaseModel):
    content: str
    model_used: str
    tokens_used: Optional[int] = None


class AIService:
    def __init__(self):
        self.model = OpenAIChatModel(
            model_name=settings.ollama_model,
            provider=OllamaProvider(base_url=f"{settings.ollama_base_url}/v1")
        )
        logger.info(f"AI Service: {settings.ollama_model} @ {settings.ollama_base_url}")
    
    def create_agent(self, instructions: str) -> Agent:
        return Agent(model=self.model, instructions=instructions)
    
    async def chat(self, message: str, system_prompt: Optional[str] = None) -> ChatResponse:
        agent = self.create_agent(system_prompt or "You are a helpful AI assistant.")
        result = await agent.run(message)
        return ChatResponse(
            content=result.output,
            model_used=settings.ollama_model,
            tokens_used=result.usage().request_tokens if result.usage() else None
        )
    
    async def generate_embedding(self, text: str) -> List[float]:
        import httpx
        async with httpx.AsyncClient() as client:
            r = await client.post(f"{settings.ollama_base_url}/api/embeddings",
                                  json={"model": settings.embedding_model, "prompt": text}, timeout=60)
            r.raise_for_status()
            return r.json()["embedding"]


def create_app():
    from fastapi import FastAPI, HTTPException
    from fastapi.middleware.cors import CORSMiddleware
    
    app = FastAPI(title="Pydantic AI Service", version="1.0.0")
    app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_credentials=True,
                       allow_methods=["*"], allow_headers=["*"])
    
    ai = AIService()
    
    class ChatRequest(BaseModel):
        message: str
        system_prompt: Optional[str] = None
    
    @app.get("/health")
    async def health():
        return {"status": "healthy", "model": settings.ollama_model, "url": settings.ollama_base_url}
    
    @app.post("/chat", response_model=ChatResponse)
    async def chat(req: ChatRequest):
        try:
            return await ai.chat(req.message, req.system_prompt)
        except Exception as e:
            raise HTTPException(500, str(e))
    
    @app.post("/embed")
    async def embed(text: str):
        try:
            emb = await ai.generate_embedding(text)
            return {"embedding": emb, "dimensions": len(emb)}
        except Exception as e:
            raise HTTPException(500, str(e))
    
    return app


if __name__ == "__main__":
    import uvicorn
    logging.basicConfig(level=logging.INFO)
    print(f"""
╔═══════════════════════════════════════════════════════════════════╗
║                  🤖 Pydantic AI Service                           ║
╠═══════════════════════════════════════════════════════════════════╣
║  Model:  {settings.ollama_model:<50} ║
║  Ollama: {settings.ollama_base_url:<50} ║
║  API:    http://{settings.api_host}:{settings.api_port:<43} ║
╚═══════════════════════════════════════════════════════════════════╝
""")
    uvicorn.run(create_app(), host=settings.api_host, port=settings.api_port)
'''
        (self.base_dir / "pydantic-ai" / "pydantic_ai_service.py").write_text(service)
        print("✓ Created pydantic-ai/pydantic_ai_service.py")
    
    def write_searxng_settings(self):
        """Write SearXNG settings."""
        settings = {"general": {"debug": False, "instance_name": "AI Stack Search"},
                   "search": {"safe_search": 0, "autocomplete": "google", "formats": ["html", "json"]},
                   "server": {"port": 8080, "bind_address": "0.0.0.0", "limiter": True},
                   "ui": {"default_theme": "simple"}}
        (self.base_dir / "searxng" / "settings.yml").write_text(yaml.dump(settings))
        print("✓ Created searxng/settings.yml")
    
    def write_all_configs(self):
        """Write all configuration files."""
        (self.base_dir / "docker-compose.yml").write_text(self.generate_docker_compose())
        print("✓ Created docker-compose.yml")
        
        env_path = self.base_dir / ".env"
        env_path.write_text(self.generate_env_file())
        os.chmod(env_path, 0o600)
        print("✓ Created .env")
        
        (self.base_dir / "supabase" / "kong.yml").write_text(self.generate_kong_config())
        print("✓ Created supabase/kong.yml")
        
        self.write_sql_init()
        self.write_pydantic_ai_service()
        self.write_searxng_settings()
    
    def deploy(self, pull: bool = True):
        """Deploy the stack."""
        os.chdir(self.base_dir)
        
        if pull:
            print("\n📥 Pulling Docker images...")
            subprocess.run(["docker", "compose", "pull"], check=True)
        
        print("\n🚀 Starting services...")
        print("   Starting databases...")
        subprocess.run(["docker", "compose", "up", "-d", "supabase-db", "redis"], check=True)
        time.sleep(10)
        
        print("   Starting all services...")
        subprocess.run(["docker", "compose", "up", "-d"], check=True)
        
        print("\n✅ Deployment complete!")
        return True


def pull_models(tailscale_ip: str, models: List[str]):
    """Pull Ollama models."""
    print("\n📥 Pulling models...")
    for model in models:
        print(f"   Pulling {model}...")
        try:
            r = requests.post(f"http://{tailscale_ip}:11434/api/pull", json={"name": model}, stream=True, timeout=3600)
            for line in r.iter_lines():
                if line:
                    data = json.loads(line)
                    if data.get("status") == "success":
                        print(f"   ✓ {model}")
                        break
        except Exception as e:
            print(f"   ✗ {model}: {e}")


def main():
    import argparse
    
    parser = argparse.ArgumentParser(description="Deploy Ultimate AI Stack with Tailscale + Pydantic AI")
    parser.add_argument("--profile", choices=["minimal", "standard", "full"], default="standard")
    parser.add_argument("--memory", type=int, default=16, help="Total RAM in GB")
    parser.add_argument("--tailscale-ip", default=DEFAULT_TAILSCALE_IP)
    parser.add_argument("--base-dir", default=str(Path.home() / "ai-stack"))
    parser.add_argument("--no-pull", action="store_true")
    parser.add_argument("--models", action="store_true", help="Pull recommended models")
    parser.add_argument("-y", "--yes", action="store_true")
    
    args = parser.parse_args()
    print_banner()
    
    base_dir = Path(args.base_dir)
    ts = args.tailscale_ip
    
    print(f"📋 Configuration:")
    print(f"   Profile:       {args.profile}")
    print(f"   Memory:        {args.memory}GB")
    print(f"   Tailscale IP:  {ts}")
    print(f"   Directory:     {base_dir}\n")
    
    if not args.yes:
        if input("Proceed? [y/N] ").lower() != 'y':
            return 1
    
    deployer = QuickDeployer(base_dir, args.profile, ts, args.memory)
    deployer.setup_directories()
    deployer.write_all_configs()
    
    if deployer.deploy(pull=not args.no_pull):
        p = PORTS
        print(f"\n📍 Access via Tailscale ({ts}):")
        print(f"   Open WebUI:        http://{ts}:{p['open_webui']}")
        print(f"   n8n:               http://{ts}:{p['n8n']}")
        print(f"   Supabase Studio:   http://{ts}:{p['supabase_studio']}")
        print(f"   Supabase API:      http://{ts}:{p['supabase_api']}")
        print(f"   Pydantic AI API:   http://{ts}:{p['pydantic_ai']}")
        if args.profile in ["standard", "full"]:
            print(f"   Langfuse:          http://{ts}:{p['langfuse']}")
            print(f"   Flowise:           http://{ts}:{p['flowise']}")
        print(f"   SearXNG:           http://{ts}:{p['searxng']}")
        print(f"   Ollama API:        http://{ts}:{p['ollama']}")
        print(f"   Qdrant:            http://{ts}:{p['qdrant']}")
        print(f"   PostgreSQL:        {ts}:{p['postgres']}")
        print(f"   Redis:             {ts}:{p['redis']}")
        
        if USE_ALTERNATE_PORTS:
            print(f"\n⚠️  Using ALTERNATE PORTS to avoid conflicts with existing services")
        
        if args.models:
            print("\n⏳ Waiting for Ollama...")
            time.sleep(20)
            pull_models(ts, ["llama3.2:3b", "nomic-embed-text"])
        
        print(f"\n🎉 Stack deployed! Test: curl http://{ts}:{p['pydantic_ai']}/health")
        return 0
    return 1


if __name__ == "__main__":
    sys.exit(main())
