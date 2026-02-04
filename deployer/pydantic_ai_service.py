"""
Pydantic AI Integration for the Ultimate AI Stack.

This module provides a production-ready Pydantic AI setup that integrates with:
- Local Ollama for LLM inference
- Supabase for vector storage and RAG
- Qdrant for vector similarity search
- Langfuse for observability (optional)

Example usage:
    from pydantic_ai_service import AIService, RAGAgent

    # Create AI service with Ollama
    service = AIService()

    # Simple chat
    response = await service.chat("What is the capital of France?")

    # RAG-enabled query
    rag_agent = RAGAgent(service)
    response = await rag_agent.query("What does our documentation say about deployment?")
"""

import os
import logging
from typing import Optional, List, Dict, Any, TypeVar, Generic
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic_ai import Agent, RunContext
from pydantic_ai.models.openai import OpenAIChatModel
from pydantic_ai.providers.ollama import OllamaProvider

logger = logging.getLogger(__name__)


# =============================================================================
# Configuration
# =============================================================================

class Settings(BaseSettings):
    """Application settings loaded from environment variables."""
    
    # Ollama configuration
    ollama_base_url: str = Field(
        default="http://100.100.180.114:11434",
        description="Ollama API base URL (Tailscale IP)"
    )
    ollama_model: str = Field(
        default="llama3.2:3b",
        description="Default Ollama model for chat"
    )
    ollama_embedding_model: str = Field(
        default="nomic-embed-text",
        description="Ollama model for embeddings"
    )
    
    # Supabase configuration
    supabase_url: str = Field(
        default="http://100.100.180.114:8000",
        description="Supabase API URL"
    )
    supabase_anon_key: str = Field(
        default="",
        description="Supabase anonymous key"
    )
    supabase_service_role_key: str = Field(
        default="",
        description="Supabase service role key"
    )
    
    # Database configuration
    database_url: str = Field(
        default="postgresql://postgres:password@100.100.180.114:5432/postgres",
        description="PostgreSQL connection string"
    )
    
    # Qdrant configuration
    qdrant_url: str = Field(
        default="http://100.100.180.114:6333",
        description="Qdrant vector database URL"
    )
    qdrant_api_key: Optional[str] = Field(
        default=None,
        description="Qdrant API key (optional)"
    )
    
    # Langfuse configuration (optional observability)
    langfuse_enabled: bool = Field(
        default=False,
        description="Enable Langfuse observability"
    )
    langfuse_public_key: Optional[str] = Field(
        default=None,
        description="Langfuse public key"
    )
    langfuse_secret_key: Optional[str] = Field(
        default=None,
        description="Langfuse secret key"
    )
    langfuse_host: str = Field(
        default="http://100.100.180.114:3002",
        description="Langfuse host URL"
    )
    
    # API configuration
    api_host: str = Field(default="0.0.0.0", description="API host")
    api_port: int = Field(default=8080, description="API port")
    log_level: str = Field(default="info", description="Logging level")
    
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore"
    )


settings = Settings()


# =============================================================================
# Pydantic Models for Structured Output
# =============================================================================

class ChatResponse(BaseModel):
    """Structured chat response."""
    content: str = Field(description="The response content")
    model_used: str = Field(description="Model that generated the response")
    tokens_used: Optional[int] = Field(default=None, description="Tokens consumed")


class RAGResponse(BaseModel):
    """RAG-enhanced response with sources."""
    content: str = Field(description="The response content")
    sources: List[Dict[str, Any]] = Field(
        default_factory=list,
        description="Source documents used"
    )
    confidence: float = Field(
        default=0.0,
        ge=0.0,
        le=1.0,
        description="Confidence score"
    )


class DocumentChunk(BaseModel):
    """A chunk of document content with metadata."""
    id: str
    content: str
    document_id: str
    similarity: float = Field(ge=0.0, le=1.0)
    metadata: Dict[str, Any] = Field(default_factory=dict)


class SearchResult(BaseModel):
    """Search results from vector database."""
    query: str
    chunks: List[DocumentChunk]
    total_found: int


class ExtractionResult(BaseModel):
    """Result of information extraction."""
    entities: List[Dict[str, Any]] = Field(default_factory=list)
    summary: str = Field(default="")
    key_points: List[str] = Field(default_factory=list)


# =============================================================================
# Dependencies for Dependency Injection
# =============================================================================

@dataclass
class AIServiceDependencies:
    """Dependencies injected into AI agents."""
    settings: Settings = field(default_factory=Settings)
    user_id: Optional[str] = None
    session_id: Optional[str] = None
    collection_id: Optional[str] = None


# =============================================================================
# Core AI Service
# =============================================================================

class AIService:
    """
    Core AI service using Pydantic AI with local Ollama.
    
    Features:
    - Type-safe structured outputs
    - Tool integration
    - RAG capabilities
    - Observability with Langfuse (optional)
    """
    
    def __init__(
        self,
        model_name: Optional[str] = None,
        base_url: Optional[str] = None
    ):
        """Initialize AI service with Ollama backend."""
        self.model_name = model_name or settings.ollama_model
        self.base_url = base_url or settings.ollama_base_url
        
        # Create Ollama-backed model
        self.model = OpenAIChatModel(
            model_name=self.model_name,
            provider=OllamaProvider(base_url=f"{self.base_url}/v1")
        )
        
        # Create embedding model
        self.embedding_model = OpenAIChatModel(
            model_name=settings.ollama_embedding_model,
            provider=OllamaProvider(base_url=f"{self.base_url}/v1")
        )
        
        # Initialize Langfuse if enabled
        if settings.langfuse_enabled:
            self._setup_langfuse()
        
        logger.info(f"AI Service initialized with model: {self.model_name}")
    
    def _setup_langfuse(self):
        """Configure Langfuse observability."""
        try:
            import logfire
            logfire.configure()
            logfire.instrument_pydantic_ai()
            logger.info("Langfuse observability enabled")
        except ImportError:
            logger.warning("Logfire not installed, observability disabled")
    
    def create_agent(
        self,
        instructions: str = "You are a helpful AI assistant.",
        output_type: Optional[type] = None,
        tools: Optional[List[Any]] = None
    ) -> Agent:
        """
        Create a Pydantic AI agent with specified configuration.
        
        Args:
            instructions: System prompt for the agent
            output_type: Pydantic model for structured output
            tools: List of tool functions
        
        Returns:
            Configured Agent instance
        """
        agent_kwargs = {
            "model": self.model,
            "instructions": instructions,
        }
        
        if output_type:
            agent_kwargs["output_type"] = output_type
        
        if tools:
            agent_kwargs["tools"] = tools
        
        return Agent(**agent_kwargs)
    
    async def chat(
        self,
        message: str,
        system_prompt: Optional[str] = None,
        history: Optional[List[Dict[str, str]]] = None
    ) -> ChatResponse:
        """
        Simple chat interface.
        
        Args:
            message: User message
            system_prompt: Optional custom system prompt
            history: Optional conversation history
        
        Returns:
            ChatResponse with content and metadata
        """
        instructions = system_prompt or "You are a helpful AI assistant. Provide clear, concise, and accurate responses."
        
        agent = self.create_agent(instructions=instructions)
        
        result = await agent.run(message, message_history=history)
        
        return ChatResponse(
            content=result.output,
            model_used=self.model_name,
            tokens_used=result.usage().request_tokens if result.usage() else None
        )
    
    def chat_sync(
        self,
        message: str,
        system_prompt: Optional[str] = None
    ) -> ChatResponse:
        """Synchronous chat interface."""
        instructions = system_prompt or "You are a helpful AI assistant."
        agent = self.create_agent(instructions=instructions)
        result = agent.run_sync(message)
        
        return ChatResponse(
            content=result.output,
            model_used=self.model_name,
            tokens_used=result.usage().request_tokens if result.usage() else None
        )
    
    async def generate_embedding(self, text: str) -> List[float]:
        """
        Generate embedding vector for text using Ollama.
        
        Args:
            text: Text to embed
        
        Returns:
            Embedding vector
        """
        import httpx
        
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{self.base_url}/api/embeddings",
                json={
                    "model": settings.ollama_embedding_model,
                    "prompt": text
                },
                timeout=60.0
            )
            response.raise_for_status()
            return response.json()["embedding"]
    
    async def generate_embeddings_batch(
        self,
        texts: List[str]
    ) -> List[List[float]]:
        """Generate embeddings for multiple texts."""
        embeddings = []
        for text in texts:
            embedding = await self.generate_embedding(text)
            embeddings.append(embedding)
        return embeddings


# =============================================================================
# RAG Agent with Tools
# =============================================================================

class RAGAgent:
    """
    RAG-enabled agent with vector search tools.
    
    Integrates with Supabase pgvector for hybrid search.
    """
    
    def __init__(
        self,
        ai_service: AIService,
        collection_id: Optional[str] = None
    ):
        """Initialize RAG agent."""
        self.ai_service = ai_service
        self.collection_id = collection_id
        self._setup_tools()
    
    def _setup_tools(self):
        """Set up RAG tools."""
        self.search_tool = self._create_search_tool()
    
    def _create_search_tool(self):
        """Create the vector search tool."""
        async def search_documents(
            ctx: RunContext[AIServiceDependencies],
            query: str,
            max_results: int = 5
        ) -> List[Dict[str, Any]]:
            """
            Search documents using hybrid vector + keyword search.
            
            Args:
                query: Search query
                max_results: Maximum number of results
            
            Returns:
                List of relevant document chunks with similarity scores
            """
            # Generate query embedding
            query_embedding = await self.ai_service.generate_embedding(query)
            
            # Search Supabase using hybrid search
            results = await self._hybrid_search(
                query_text=query,
                query_embedding=query_embedding,
                match_count=max_results,
                collection_id=ctx.deps.collection_id
            )
            
            return results
        
        return search_documents
    
    async def _hybrid_search(
        self,
        query_text: str,
        query_embedding: List[float],
        match_count: int = 5,
        collection_id: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        Perform hybrid search using Supabase RPC.
        
        Uses the rag.hybrid_search function from the database.
        """
        try:
            import asyncpg
            
            conn = await asyncpg.connect(settings.database_url)
            
            try:
                # Call the hybrid search function
                results = await conn.fetch(
                    """
                    SELECT * FROM rag.hybrid_search(
                        $1::text,
                        $2::vector(768),
                        $3::int,
                        0.3,  -- keyword_weight
                        $4::uuid,
                        NULL
                    )
                    """,
                    query_text,
                    query_embedding,
                    match_count,
                    collection_id
                )
                
                return [
                    {
                        "id": str(r["id"]),
                        "document_id": str(r["document_id"]),
                        "content": r["content"],
                        "metadata": r["metadata"],
                        "vector_score": float(r["vector_score"]),
                        "keyword_score": float(r["keyword_score"]),
                        "combined_score": float(r["combined_score"])
                    }
                    for r in results
                ]
            finally:
                await conn.close()
                
        except Exception as e:
            logger.error(f"Hybrid search failed: {e}")
            return []
    
    def create_agent(self) -> Agent:
        """Create RAG-enabled agent."""
        instructions = """You are a helpful AI assistant with access to a document search tool.
        
When answering questions:
1. Use the search_documents tool to find relevant information
2. Cite your sources when using retrieved information
3. If no relevant documents are found, say so clearly
4. Provide comprehensive answers based on the retrieved context

Always prioritize accuracy over completeness."""
        
        return Agent(
            model=self.ai_service.model,
            instructions=instructions,
            output_type=RAGResponse,
            tools=[self.search_tool],
            deps_type=AIServiceDependencies
        )
    
    async def query(
        self,
        question: str,
        user_id: Optional[str] = None
    ) -> RAGResponse:
        """
        Query with RAG-enhanced response.
        
        Args:
            question: User's question
            user_id: Optional user ID for filtering
        
        Returns:
            RAGResponse with sources
        """
        deps = AIServiceDependencies(
            collection_id=self.collection_id,
            user_id=user_id
        )
        
        agent = self.create_agent()
        result = await agent.run(question, deps=deps)
        
        return result.output


# =============================================================================
# Specialized Agents
# =============================================================================

class DataExtractionAgent:
    """Agent for extracting structured data from text."""
    
    def __init__(self, ai_service: AIService):
        self.ai_service = ai_service
    
    async def extract(
        self,
        text: str,
        output_model: type[BaseModel]
    ) -> BaseModel:
        """
        Extract structured data from text.
        
        Args:
            text: Source text
            output_model: Pydantic model defining expected output
        
        Returns:
            Validated instance of output_model
        """
        instructions = """You are a precise data extraction assistant.
Extract the requested information from the provided text.
Be accurate and only include information that is explicitly stated."""
        
        agent = self.ai_service.create_agent(
            instructions=instructions,
            output_type=output_model
        )
        
        result = await agent.run(text)
        return result.output


class SummaryAgent:
    """Agent for text summarization."""
    
    def __init__(self, ai_service: AIService):
        self.ai_service = ai_service
    
    async def summarize(
        self,
        text: str,
        max_length: int = 200,
        style: str = "concise"
    ) -> str:
        """
        Summarize text.
        
        Args:
            text: Text to summarize
            max_length: Approximate max length in words
            style: "concise", "detailed", or "bullet"
        
        Returns:
            Summary string
        """
        style_instructions = {
            "concise": "Provide a brief, concise summary.",
            "detailed": "Provide a comprehensive summary covering all key points.",
            "bullet": "Provide a summary as bullet points."
        }
        
        instructions = f"""You are a summarization assistant.
{style_instructions.get(style, style_instructions['concise'])}
Keep the summary under {max_length} words approximately."""
        
        agent = self.ai_service.create_agent(instructions=instructions)
        result = await agent.run(f"Summarize this text:\n\n{text}")
        
        return result.output


class CodeAssistant:
    """Agent for code-related tasks."""
    
    def __init__(self, ai_service: AIService):
        # Use code-optimized model if available
        self.ai_service = ai_service
    
    async def explain_code(self, code: str, language: str = "python") -> str:
        """Explain what code does."""
        instructions = f"""You are an expert {language} developer.
Explain code clearly, covering:
1. What the code does
2. Key concepts used
3. Any potential issues or improvements"""
        
        agent = self.ai_service.create_agent(instructions=instructions)
        result = await agent.run(f"Explain this {language} code:\n\n```{language}\n{code}\n```")
        
        return result.output
    
    async def generate_code(
        self,
        description: str,
        language: str = "python"
    ) -> str:
        """Generate code from description."""
        instructions = f"""You are an expert {language} developer.
Generate clean, well-documented code based on the description.
Include comments explaining key parts."""
        
        agent = self.ai_service.create_agent(instructions=instructions)
        result = await agent.run(f"Write {language} code to: {description}")
        
        return result.output


# =============================================================================
# FastAPI Integration
# =============================================================================

def create_fastapi_app():
    """Create FastAPI application with AI endpoints."""
    from fastapi import FastAPI, HTTPException
    from fastapi.middleware.cors import CORSMiddleware
    
    app = FastAPI(
        title="AI Stack API",
        description="Pydantic AI powered API with local Ollama",
        version="1.0.0"
    )
    
    # CORS for web interfaces
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    
    # Initialize AI service
    ai_service = AIService()
    rag_agent = RAGAgent(ai_service)
    
    class ChatRequest(BaseModel):
        message: str
        system_prompt: Optional[str] = None
    
    class RAGRequest(BaseModel):
        question: str
        collection_id: Optional[str] = None
    
    @app.get("/health")
    async def health_check():
        """Health check endpoint."""
        return {
            "status": "healthy",
            "model": settings.ollama_model,
            "ollama_url": settings.ollama_base_url
        }
    
    @app.post("/chat", response_model=ChatResponse)
    async def chat(request: ChatRequest):
        """Chat endpoint."""
        try:
            response = await ai_service.chat(
                request.message,
                request.system_prompt
            )
            return response
        except Exception as e:
            logger.error(f"Chat error: {e}")
            raise HTTPException(status_code=500, detail=str(e))
    
    @app.post("/rag/query", response_model=RAGResponse)
    async def rag_query(request: RAGRequest):
        """RAG-enhanced query endpoint."""
        try:
            rag = RAGAgent(ai_service, request.collection_id)
            response = await rag.query(request.question)
            return response
        except Exception as e:
            logger.error(f"RAG query error: {e}")
            raise HTTPException(status_code=500, detail=str(e))
    
    @app.post("/embed")
    async def generate_embedding(text: str):
        """Generate embedding for text."""
        try:
            embedding = await ai_service.generate_embedding(text)
            return {"embedding": embedding, "dimensions": len(embedding)}
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))
    
    return app


# =============================================================================
# CLI Interface
# =============================================================================

def main():
    """Run the AI service as a standalone API."""
    import uvicorn
    
    logging.basicConfig(level=settings.log_level.upper())
    
    print(f"""
╔═══════════════════════════════════════════════════════════════════╗
║                  🤖 Pydantic AI Service                           ║
╠═══════════════════════════════════════════════════════════════════╣
║  Model:     {settings.ollama_model:<45}        ║
║  Ollama:    {settings.ollama_base_url:<45}        ║
║  API:       http://{settings.api_host}:{settings.api_port:<40} ║
╚═══════════════════════════════════════════════════════════════════╝
""")
    
    app = create_fastapi_app()
    
    uvicorn.run(
        app,
        host=settings.api_host,
        port=settings.api_port,
        reload=False
    )


if __name__ == "__main__":
    main()
