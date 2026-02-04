# 🚀 Ultimate AI Stack Deployer

A comprehensive Python-based deployment system for self-hosted AI infrastructure with **Tailscale networking** and **Pydantic AI** integration. Deploy a complete local AI stack with a single command.

## ✨ Key Features

- **Tailscale Integration** - Secure mesh networking for remote access
- **Pydantic AI Service** - Type-safe AI agents with structured outputs
- **RAG Pipeline** - Hybrid search (vector + BM25) with pgvector
- **One-Command Deploy** - Full stack in minutes
- **Profile-Based Scaling** - Minimal (8GB) to Full (32GB+)

## 📦 What's Included

### Core AI Services
| Service | Purpose | Port | Memory |
|---------|---------|------|--------|
| **Ollama** | Local LLM inference | 11434 | 8GB |
| **Pydantic AI** | Type-safe AI agents API | 8080 | 1GB |
| **Open WebUI** | Chat interface | 3003 | 2GB |
| **n8n** | Workflow automation | 5678 | 1GB |
| **Flowise** | No-code AI agents | 3004 | 1GB |

### Data & Storage
| Service | Purpose | Port | Memory |
|---------|---------|------|--------|
| **Supabase** | PostgreSQL + Auth + Storage | 8000, 3001 | 2GB |
| **Qdrant** | Vector database | 6333 | 2GB |
| **Redis** | Caching layer | 6379 | 512MB |
| **Neo4j** | Graph database (full profile) | 7474, 7687 | 2GB |

### Observability & Search
| Service | Purpose | Port | Memory |
|---------|---------|------|--------|
| **Langfuse** | LLM observability | 3002 | 1GB |
| **SearXNG** | Private search engine | 8888 | 512MB |

## 🚀 Quick Start

### Prerequisites

- Docker & Docker Compose v2+
- Python 3.10+
- 16GB+ RAM recommended
- 50GB+ disk space
- **Tailscale** installed and connected (optional but recommended)

### Installation

```bash
# Clone the repository
git clone https://github.com/your-repo/ai-stack-deployer.git
cd ai-stack-deployer

# Install the package
pip install -e .

# Or just install dependencies
pip install -r requirements.txt
```

### Deploy with Tailscale (Recommended)

```bash
# Quick deploy with your Tailscale IP
python deploy.py --tailscale-ip 100.100.180.114 --profile standard --models -y

# Or use the module
python -m deployer deploy --network tailscale --tailscale-ip 100.100.180.114 --models
```

### Deploy Locally

```bash
# Deploy with defaults (localhost binding)
python -m deployer deploy --network localhost
```

### Deployment Profiles

| Profile | RAM | Services | Use Case |
|---------|-----|----------|----------|
| `minimal` | 8GB | Essential only | Development, testing |
| `standard` | 16GB | Full stack (no Neo4j) | Production, single user |
| `full` | 32GB+ | Everything | Team/enterprise use |

## 🌐 Tailscale Networking

All services bind to your Tailscale IP for secure remote access without exposing ports publicly.

### Access via Tailscale (IP: 100.100.180.114)

| Service | URL |
|---------|-----|
| **Open WebUI** | http://100.100.180.114:3003 |
| **n8n** | http://100.100.180.114:5678 |
| **Supabase Studio** | http://100.100.180.114:3001 |
| **Supabase API** | http://100.100.180.114:8000 |
| **Pydantic AI API** | http://100.100.180.114:8080 |
| **Langfuse** | http://100.100.180.114:3002 |
| **Flowise** | http://100.100.180.114:3004 |
| **SearXNG** | http://100.100.180.114:8888 |
| **Ollama API** | http://100.100.180.114:11434 |
| **Qdrant** | http://100.100.180.114:6333 |

## 🤖 Pydantic AI Integration

The stack includes a production-ready Pydantic AI service that provides type-safe AI agents with structured outputs.

### API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/health` | GET | Service health check |
| `/chat` | POST | Chat completion with optional system prompt |
| `/embed` | POST | Generate 768-dim embeddings |

### Python Usage

```python
from pydantic_ai import Agent
from pydantic_ai.models.openai import OpenAIChatModel
from pydantic_ai.providers.ollama import OllamaProvider

# Connect to Ollama via Tailscale
model = OpenAIChatModel(
    model_name="llama3.2:3b",
    provider=OllamaProvider(base_url="http://100.100.180.114:11434/v1")
)

# Create a simple agent
agent = Agent(model, instructions="You are a helpful AI assistant.")
result = agent.run_sync("What is machine learning?")
print(result.output)
```

### Structured Outputs

```python
from pydantic import BaseModel
from pydantic_ai import Agent

class MovieReview(BaseModel):
    title: str
    rating: float
    summary: str
    recommended: bool

agent = Agent(model, output_type=MovieReview)
result = agent.run_sync("Review the movie Inception")
print(result.output.rating)  # Type-safe access!
```

### RAG with Hybrid Search

```python
import httpx
import asyncpg

# Generate embedding
async def get_embedding(text: str) -> list[float]:
    async with httpx.AsyncClient() as client:
        r = await client.post(
            "http://100.100.180.114:11434/api/embeddings",
            json={"model": "nomic-embed-text", "prompt": text}
        )
        return r.json()["embedding"]

# Hybrid search (vector + keyword)
async def search(query: str, embedding: list[float]):
    conn = await asyncpg.connect("postgresql://postgres:password@100.100.180.114:5432/postgres")
    results = await conn.fetch("""
        SELECT * FROM rag.hybrid_search($1, $2::vector, 10, 0.3)
    """, query, embedding)
    return results
```

### Using the REST API

```bash
# Health check
curl http://100.100.180.114:8080/health

# Chat
curl -X POST http://100.100.180.114:8080/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "What is the capital of France?"}'

# Generate embedding
curl -X POST "http://100.100.180.114:8080/embed?text=Hello%20world"
```

## 📖 CLI Commands

```bash
# Deploy the stack
python -m deployer deploy [options]

# Check status of all services
python -m deployer status

# View logs
python -m deployer logs [service_name]
python -m deployer logs ollama -f  # Follow logs

# Stop all services
python -m deployer stop

# Restart services
python -m deployer restart [service_name]

# Health check
python -m deployer health

# Backup management
python -m deployer backup list
python -m deployer backup create --type full
python -m deployer backup restore --backup-id <id>

# Model management
python -m deployer models list
python -m deployer models pull llama3.2:3b
python -m deployer models recommend --ram 16
```

### Deploy Options

```bash
python -m deployer deploy \
    --name my-ai-stack \           # Project name
    --profile standard \           # minimal|standard|full
    --network tailscale \          # localhost|tailscale|public
    --tailscale-ip 100.100.180.114 \  # Your Tailscale IP
    --domain ai.example.com \      # Domain for SSL (public mode)
    --memory 16 \                  # Total RAM in GB
    --cpus 4 \                     # Number of CPUs
    --base-dir ~/ai-stack \        # Installation directory
    --models \                     # Pull recommended models
    -y                             # Skip confirmation
```

## 🔧 Configuration

### Directory Structure

```
~/ai-stack/
├── docker-compose.yml      # Main compose file
├── .env                    # Environment variables (secrets)
├── config/
│   └── stack-config.yaml   # Stack configuration
├── supabase/
│   ├── init.sql           # Database initialization with RAG schema
│   └── kong.yml           # API gateway config
├── searxng/
│   └── settings.yml       # Search engine config
├── pydantic-ai/
│   └── pydantic_ai_service.py  # Pydantic AI service
├── backups/               # Backup files
└── logs/                  # Log files
```

### Environment Variables

The `.env` file contains all secrets and Tailscale-aware configuration:

```bash
# Tailscale
TAILSCALE_IP=100.100.180.114

# Database
POSTGRES_PASSWORD=<generated>
DATABASE_URL=postgresql://postgres:...@supabase-db:5432/postgres

# Supabase
JWT_SECRET=<generated>
ANON_KEY=<generated>
SERVICE_ROLE_KEY=<generated>
SUPABASE_URL=http://100.100.180.114:8000

# Ollama
OLLAMA_BASE_URL=http://ollama:11434
OLLAMA_EXTERNAL_URL=http://100.100.180.114:11434

# Pydantic AI
PYDANTIC_AI_MODEL=llama3.2:3b
PYDANTIC_AI_EMBEDDING_MODEL=nomic-embed-text
```

## 🗄️ Database Schema

The SQL initialization creates a RAG-optimized schema in the `rag` schema:

### Tables
- `rag.documents` - Document metadata and processing status
- `rag.chunks` - Text chunks with 768-dim vector embeddings
- `rag.collections` - Document organization
- `rag.conversations` - Chat history
- `rag.messages` - Individual messages

### Features
- **HNSW indexes** for 15x faster vector search (m=16, ef_construction=64)
- **Hybrid search** combining vector similarity + BM25 keyword matching with RRF
- **Full-text search** with PostgreSQL tsvector
- **Trigram indexes** for fuzzy matching
- **768-dimension vectors** optimized for nomic-embed-text

### Search Functions

```sql
-- Pure vector similarity search
SELECT * FROM rag.search_similar_chunks(
    query_embedding := $1::vector,
    match_threshold := 0.7,
    match_count := 10
);

-- Hybrid search (vector + keyword with Reciprocal Rank Fusion)
SELECT * FROM rag.hybrid_search(
    query_text := 'machine learning',
    query_embedding := $1::vector,
    match_count := 10,
    keyword_weight := 0.3  -- 30% keyword, 70% vector
);
```

## 🤖 Model Management

### Recommended Models

```bash
# View recommendations for your RAM
python -m deployer models recommend --ram 16

# Chat models
llama3.2:3b      # Fast, good quality (2GB)
llama3.2:1b      # Fastest, compact (1GB)
qwen2.5:3b       # Good multilingual (2GB)
mistral:7b       # High quality (4.5GB)

# Embedding models
nomic-embed-text # 768 dims, high quality (275MB) ← Default
mxbai-embed-large # 1024 dims, best quality (670MB)

# Code models
qwen2.5-coder:3b # Code generation (2GB)
deepseek-coder:6.7b # Advanced coding (4GB)
```

### Model Operations

```bash
# Pull a model
python -m deployer models pull llama3.2:3b

# List installed models
python -m deployer models list

# Delete a model
python -m deployer models delete llama3.2:3b

# Pull recommended models automatically
python deploy.py --models -y
```

## 💾 Backup & Restore

### Backup Types

| Type | Contents | Use Case |
|------|----------|----------|
| `full` | Everything | Disaster recovery |
| `database` | PostgreSQL dump | Daily backups |
| `volumes` | Docker volumes | Data migration |
| `config` | Config files | Version control |

### Commands

```bash
# Create backups
python -m deployer backup create --type full
python -m deployer backup create --type database

# List available backups
python -m deployer backup list

# Restore from backup
python -m deployer backup restore --backup-id database_20240101_120000
```

## 🏥 Health Monitoring

```bash
# Quick health check
python -m deployer health

# JSON output for monitoring systems
python -m deployer health --json

# Test Pydantic AI service
curl http://100.100.180.114:8080/health
```

The health checker monitors:
- HTTP endpoints for all services
- Database connections
- Container status
- Memory usage
- Response times

## 🔒 Security

### Network Modes

| Mode | Description | Use Case |
|------|-------------|----------|
| `localhost` | Bind to 127.0.0.1 only | Development, SSH tunnel |
| `tailscale` | Tailscale mesh network | **Recommended for remote access** |
| `public` | Public with Caddy SSL | Production with domain |

### Best Practices

1. **Use Tailscale mode** for secure remote access without exposing ports
2. **Rotate secrets** regularly using the backup/restore workflow
3. **Enable firewall** rules for Docker (only allow Tailscale)
4. **Use SSH tunneling** as fallback for localhost mode
5. **Keep .env secure** with `chmod 600`

## 🔌 Integration Examples

### n8n + Ollama (via Tailscale)

```javascript
// HTTP Request node to Ollama
{
  "url": "http://100.100.180.114:11434/api/generate",
  "method": "POST",
  "body": {
    "model": "llama3.2:3b",
    "prompt": "{{ $json.userMessage }}",
    "stream": false
  }
}
```

### n8n + Pydantic AI Service

```javascript
// HTTP Request to Pydantic AI
{
  "url": "http://100.100.180.114:8080/chat",
  "method": "POST",
  "body": {
    "message": "{{ $json.userMessage }}",
    "system_prompt": "You are a helpful assistant."
  }
}
```

### Python RAG Pipeline

```python
import httpx
from supabase import create_client

# Connect to Supabase via Tailscale
supabase = create_client(
    "http://100.100.180.114:8000",
    "your-anon-key"
)

# Generate embedding via Pydantic AI service
async def get_embedding(text: str):
    async with httpx.AsyncClient() as client:
        r = await client.post(
            "http://100.100.180.114:8080/embed",
            params={"text": text}
        )
        return r.json()["embedding"]

# Store document chunk
async def store_chunk(content: str):
    embedding = await get_embedding(content)
    supabase.table("rag.chunks").insert({
        "content": content,
        "embedding": embedding
    }).execute()

# Search similar chunks
def search(query_embedding: list):
    return supabase.rpc("search_similar_chunks", {
        "query_embedding": query_embedding,
        "match_count": 5
    }).execute()
```

## 🐳 Docker Tips

### Resource Management

```bash
# View resource usage
docker stats

# Clean up unused resources
docker system prune -a --volumes

# View disk usage
docker system df
```

### Troubleshooting

```bash
# View logs for a service
docker logs ollama -f --tail 100

# Restart a service
docker compose restart ollama

# Rebuild and restart
docker compose up -d --force-recreate ollama

# Shell into a container
docker exec -it ollama sh

# Check Pydantic AI service
docker logs pydantic-ai -f
```

## 🛠️ Development

### Running the Pydantic AI Service Locally

```bash
cd ~/ai-stack/pydantic-ai

# Install dependencies
pip install pydantic-ai pydantic-ai-slim[openai] pydantic-settings fastapi uvicorn httpx asyncpg

# Set environment
export OLLAMA_EXTERNAL_URL=http://100.100.180.114:11434
export PYDANTIC_AI_MODEL=llama3.2:3b

# Run
python pydantic_ai_service.py
```

### Testing

```bash
# Run tests
pytest tests/

# Test with coverage
pytest --cov=deployer tests/
```

## 🤝 Contributing

Contributions welcome! Please read our contributing guidelines first.

## 📄 License

MIT License - see LICENSE file for details.

## 🙏 Acknowledgments

- [Pydantic AI](https://ai.pydantic.dev) - Type-safe AI agents
- [Ollama](https://ollama.ai) - Local LLM inference
- [Supabase](https://supabase.com) - Open source Firebase alternative
- [n8n](https://n8n.io) - Workflow automation
- [Qdrant](https://qdrant.tech) - Vector database
- [Langfuse](https://langfuse.com) - LLM observability
- [Tailscale](https://tailscale.com) - Secure mesh networking
