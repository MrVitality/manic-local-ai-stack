-- =============================================================================
-- ULTIMATE LOCAL AI STACK - Supabase PostgreSQL Initialization (OPTIMIZED)
-- =============================================================================
-- Key Improvements:
--   1. Vector dimension set to 768 for nomic-embed-text (was 1536 for OpenAI)
--   2. HNSW indexes instead of IVFFlat (15x better throughput)
--   3. Hybrid search function with BM25 + vector similarity
--   4. Optimized for 16GB shared environment
-- =============================================================================

-- Enable required extensions
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pgcrypto";
CREATE EXTENSION IF NOT EXISTS "pgjwt";
CREATE EXTENSION IF NOT EXISTS "pg_stat_statements";
CREATE EXTENSION IF NOT EXISTS "pg_trgm";      -- For fuzzy text search
CREATE EXTENSION IF NOT EXISTS "vector";       -- pgvector for embeddings

-- =============================================================================
-- Create application databases
-- =============================================================================
SELECT 'CREATE DATABASE n8n' WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = 'n8n')\gexec
SELECT 'CREATE DATABASE flowise' WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = 'flowise')\gexec
SELECT 'CREATE DATABASE openwebui' WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = 'openwebui')\gexec

-- =============================================================================
-- Create Supabase roles
-- =============================================================================
DO $$
BEGIN
    -- Authenticator role
    IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'authenticator') THEN
        CREATE ROLE authenticator NOINHERIT LOGIN PASSWORD 'your-super-secret-password-change-me';
    END IF;
    
    -- Anonymous role
    IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'anon') THEN
        CREATE ROLE anon NOLOGIN NOINHERIT;
    END IF;
    
    -- Authenticated role
    IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'authenticated') THEN
        CREATE ROLE authenticated NOLOGIN NOINHERIT;
    END IF;
    
    -- Service role
    IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'service_role') THEN
        CREATE ROLE service_role NOLOGIN NOINHERIT BYPASSRLS;
    END IF;
    
    -- Supabase admin
    IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'supabase_admin') THEN
        CREATE ROLE supabase_admin LOGIN SUPERUSER PASSWORD 'your-super-secret-password-change-me';
    END IF;
    
    -- Supabase auth admin
    IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'supabase_auth_admin') THEN
        CREATE ROLE supabase_auth_admin NOLOGIN NOINHERIT;
    END IF;
    
    -- Supabase storage admin
    IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'supabase_storage_admin') THEN
        CREATE ROLE supabase_storage_admin NOLOGIN NOINHERIT;
    END IF;
END
$$;

-- Grant role memberships
GRANT anon TO authenticator;
GRANT authenticated TO authenticator;
GRANT service_role TO authenticator;
GRANT supabase_admin TO authenticator;

-- =============================================================================
-- Create Supabase schemas
-- =============================================================================
CREATE SCHEMA IF NOT EXISTS auth;
CREATE SCHEMA IF NOT EXISTS storage;
CREATE SCHEMA IF NOT EXISTS graphql;
CREATE SCHEMA IF NOT EXISTS graphql_public;
CREATE SCHEMA IF NOT EXISTS realtime;
CREATE SCHEMA IF NOT EXISTS _realtime;
CREATE SCHEMA IF NOT EXISTS extensions;

-- Grant schema permissions
GRANT USAGE ON SCHEMA public TO anon, authenticated, service_role;
GRANT USAGE ON SCHEMA auth TO anon, authenticated, service_role;
GRANT USAGE ON SCHEMA storage TO anon, authenticated, service_role;
GRANT USAGE ON SCHEMA extensions TO anon, authenticated, service_role;

-- =============================================================================
-- RAG SCHEMA - Document Processing & Vector Storage (OPTIMIZED)
-- =============================================================================
CREATE SCHEMA IF NOT EXISTS rag;
GRANT USAGE ON SCHEMA rag TO anon, authenticated, service_role;

-- Documents table
CREATE TABLE IF NOT EXISTS rag.documents (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id UUID,
    filename TEXT NOT NULL,
    content_type TEXT,
    file_size BIGINT,
    status TEXT DEFAULT 'pending' CHECK (status IN ('pending', 'processing', 'completed', 'failed')),
    error_message TEXT,
    chunk_count INTEGER DEFAULT 0,
    metadata JSONB DEFAULT '{}',
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Create index for document lookups
CREATE INDEX IF NOT EXISTS idx_documents_user_id ON rag.documents(user_id);
CREATE INDEX IF NOT EXISTS idx_documents_status ON rag.documents(status);
CREATE INDEX IF NOT EXISTS idx_documents_created_at ON rag.documents(created_at DESC);

-- Document chunks table (for RAG)
-- NOTE: Using 768 dimensions for nomic-embed-text
-- Change to 1536 if using OpenAI embeddings, 384 for all-MiniLM-L6-v2
CREATE TABLE IF NOT EXISTS rag.chunks (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    document_id UUID REFERENCES rag.documents(id) ON DELETE CASCADE,
    chunk_index INTEGER NOT NULL,
    content TEXT NOT NULL,
    content_tokens INTEGER,  -- Token count for context window management
    embedding VECTOR(768),   -- nomic-embed-text dimension
    metadata JSONB DEFAULT '{}',
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- === CRITICAL: HNSW index for vector similarity search ===
-- HNSW provides 15x better query throughput than IVFFlat
-- Parameters: m=16 (connections), ef_construction=64 (build quality)
CREATE INDEX IF NOT EXISTS idx_chunks_embedding_hnsw 
ON rag.chunks 
USING hnsw (embedding vector_cosine_ops)
WITH (m = 16, ef_construction = 64);

-- Full-text search index for hybrid search
CREATE INDEX IF NOT EXISTS idx_chunks_content_fts 
ON rag.chunks 
USING gin (to_tsvector('english', content));

-- Trigram index for fuzzy matching
CREATE INDEX IF NOT EXISTS idx_chunks_content_trgm 
ON rag.chunks 
USING gin (content gin_trgm_ops);

-- Index for document_id lookups
CREATE INDEX IF NOT EXISTS idx_chunks_document_id ON rag.chunks(document_id);

-- Collections table (for organizing documents)
CREATE TABLE IF NOT EXISTS rag.collections (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id UUID,
    name TEXT NOT NULL,
    description TEXT,
    is_public BOOLEAN DEFAULT false,
    metadata JSONB DEFAULT '{}',
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_collections_user_id ON rag.collections(user_id);

-- Document-Collection mapping
CREATE TABLE IF NOT EXISTS rag.document_collections (
    document_id UUID REFERENCES rag.documents(id) ON DELETE CASCADE,
    collection_id UUID REFERENCES rag.collections(id) ON DELETE CASCADE,
    added_at TIMESTAMPTZ DEFAULT NOW(),
    PRIMARY KEY (document_id, collection_id)
);

-- Conversations table
CREATE TABLE IF NOT EXISTS rag.conversations (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id UUID,
    title TEXT,
    model TEXT DEFAULT 'llama3.2:3b',
    system_prompt TEXT,
    temperature FLOAT DEFAULT 0.7,
    max_tokens INTEGER DEFAULT 2048,
    metadata JSONB DEFAULT '{}',
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_conversations_user_id ON rag.conversations(user_id);
CREATE INDEX IF NOT EXISTS idx_conversations_created_at ON rag.conversations(created_at DESC);

-- Messages table
CREATE TABLE IF NOT EXISTS rag.messages (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    conversation_id UUID REFERENCES rag.conversations(id) ON DELETE CASCADE,
    role TEXT NOT NULL CHECK (role IN ('system', 'user', 'assistant')),
    content TEXT NOT NULL,
    tokens_used INTEGER,
    latency_ms INTEGER,  -- Response generation time
    model_used TEXT,
    metadata JSONB DEFAULT '{}',
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_messages_conversation_id ON rag.messages(conversation_id);
CREATE INDEX IF NOT EXISTS idx_messages_created_at ON rag.messages(created_at);

-- =============================================================================
-- RAG Functions (OPTIMIZED)
-- =============================================================================

-- Function for pure vector similarity search
CREATE OR REPLACE FUNCTION rag.search_similar_chunks(
    query_embedding VECTOR(768),
    match_threshold FLOAT DEFAULT 0.7,
    match_count INT DEFAULT 5,
    filter_collection_id UUID DEFAULT NULL,
    filter_user_id UUID DEFAULT NULL
)
RETURNS TABLE (
    id UUID,
    document_id UUID,
    content TEXT,
    metadata JSONB,
    similarity FLOAT
)
LANGUAGE plpgsql
STABLE
AS $$
BEGIN
    -- Set HNSW search parameter for better recall
    PERFORM set_config('hnsw.ef_search', '100', true);
    
    RETURN QUERY
    SELECT 
        c.id,
        c.document_id,
        c.content,
        c.metadata,
        1 - (c.embedding <=> query_embedding) AS similarity
    FROM rag.chunks c
    JOIN rag.documents d ON c.document_id = d.id
    LEFT JOIN rag.document_collections dc ON c.document_id = dc.document_id
    WHERE 
        (filter_collection_id IS NULL OR dc.collection_id = filter_collection_id)
        AND (filter_user_id IS NULL OR d.user_id = filter_user_id)
        AND 1 - (c.embedding <=> query_embedding) > match_threshold
    ORDER BY c.embedding <=> query_embedding
    LIMIT match_count;
END;
$$;

-- Function for hybrid search (vector + BM25 keyword matching)
-- Uses Reciprocal Rank Fusion to combine results
CREATE OR REPLACE FUNCTION rag.hybrid_search(
    query_text TEXT,
    query_embedding VECTOR(768),
    match_count INT DEFAULT 10,
    keyword_weight FLOAT DEFAULT 0.3,  -- 0.3 = 30% keyword, 70% vector
    filter_collection_id UUID DEFAULT NULL,
    filter_user_id UUID DEFAULT NULL
)
RETURNS TABLE (
    id UUID,
    document_id UUID,
    content TEXT,
    metadata JSONB,
    vector_score FLOAT,
    keyword_score FLOAT,
    combined_score FLOAT
)
LANGUAGE plpgsql
STABLE
AS $$
DECLARE
    rrf_k INT := 60;  -- RRF constant
BEGIN
    -- Set HNSW search parameter
    PERFORM set_config('hnsw.ef_search', '100', true);
    
    RETURN QUERY
    WITH 
    -- Vector search results with ranking
    vector_results AS (
        SELECT 
            c.id,
            c.document_id,
            c.content,
            c.metadata,
            1 - (c.embedding <=> query_embedding) AS v_score,
            ROW_NUMBER() OVER (ORDER BY c.embedding <=> query_embedding) AS v_rank
        FROM rag.chunks c
        JOIN rag.documents d ON c.document_id = d.id
        LEFT JOIN rag.document_collections dc ON c.document_id = dc.document_id
        WHERE 
            (filter_collection_id IS NULL OR dc.collection_id = filter_collection_id)
            AND (filter_user_id IS NULL OR d.user_id = filter_user_id)
        ORDER BY c.embedding <=> query_embedding
        LIMIT match_count * 2  -- Fetch more for fusion
    ),
    -- Keyword search results with ranking (BM25-style via ts_rank)
    keyword_results AS (
        SELECT 
            c.id,
            ts_rank_cd(
                to_tsvector('english', c.content), 
                websearch_to_tsquery('english', query_text),
                32  -- Normalization: divide by document length
            ) AS k_score,
            ROW_NUMBER() OVER (
                ORDER BY ts_rank_cd(
                    to_tsvector('english', c.content), 
                    websearch_to_tsquery('english', query_text),
                    32
                ) DESC
            ) AS k_rank
        FROM rag.chunks c
        JOIN rag.documents d ON c.document_id = d.id
        LEFT JOIN rag.document_collections dc ON c.document_id = dc.document_id
        WHERE 
            to_tsvector('english', c.content) @@ websearch_to_tsquery('english', query_text)
            AND (filter_collection_id IS NULL OR dc.collection_id = filter_collection_id)
            AND (filter_user_id IS NULL OR d.user_id = filter_user_id)
        LIMIT match_count * 2
    ),
    -- Reciprocal Rank Fusion
    fused AS (
        SELECT 
            v.id,
            v.document_id,
            v.content,
            v.metadata,
            v.v_score,
            COALESCE(k.k_score, 0) AS k_score,
            -- RRF formula: 1/(k+rank_vector) + 1/(k+rank_keyword)
            (1.0 - keyword_weight) * (1.0 / (rrf_k + v.v_rank)) +
            keyword_weight * (1.0 / (rrf_k + COALESCE(k.k_rank, match_count * 2 + 1))) AS rrf_score
        FROM vector_results v
        LEFT JOIN keyword_results k ON v.id = k.id
    )
    SELECT 
        f.id,
        f.document_id,
        f.content,
        f.metadata,
        f.v_score AS vector_score,
        f.k_score AS keyword_score,
        f.rrf_score AS combined_score
    FROM fused f
    ORDER BY f.rrf_score DESC
    LIMIT match_count;
END;
$$;

-- Function for semantic search with metadata filtering
CREATE OR REPLACE FUNCTION rag.search_with_filters(
    query_embedding VECTOR(768),
    metadata_filter JSONB DEFAULT '{}',
    match_count INT DEFAULT 5,
    filter_user_id UUID DEFAULT NULL
)
RETURNS TABLE (
    id UUID,
    document_id UUID,
    content TEXT,
    metadata JSONB,
    similarity FLOAT
)
LANGUAGE plpgsql
STABLE
AS $$
BEGIN
    PERFORM set_config('hnsw.ef_search', '100', true);
    
    RETURN QUERY
    SELECT 
        c.id,
        c.document_id,
        c.content,
        c.metadata,
        1 - (c.embedding <=> query_embedding) AS similarity
    FROM rag.chunks c
    JOIN rag.documents d ON c.document_id = d.id
    WHERE 
        (filter_user_id IS NULL OR d.user_id = filter_user_id)
        AND (metadata_filter = '{}' OR c.metadata @> metadata_filter)
    ORDER BY c.embedding <=> query_embedding
    LIMIT match_count;
END;
$$;

-- Update timestamp trigger
CREATE OR REPLACE FUNCTION update_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Apply triggers
DROP TRIGGER IF EXISTS update_documents_updated_at ON rag.documents;
CREATE TRIGGER update_documents_updated_at
    BEFORE UPDATE ON rag.documents
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at();

DROP TRIGGER IF EXISTS update_collections_updated_at ON rag.collections;
CREATE TRIGGER update_collections_updated_at
    BEFORE UPDATE ON rag.collections
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at();

DROP TRIGGER IF EXISTS update_conversations_updated_at ON rag.conversations;
CREATE TRIGGER update_conversations_updated_at
    BEFORE UPDATE ON rag.conversations
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at();

-- =============================================================================
-- Row Level Security (RLS)
-- =============================================================================

ALTER TABLE rag.documents ENABLE ROW LEVEL SECURITY;
ALTER TABLE rag.chunks ENABLE ROW LEVEL SECURITY;
ALTER TABLE rag.collections ENABLE ROW LEVEL SECURITY;
ALTER TABLE rag.conversations ENABLE ROW LEVEL SECURITY;
ALTER TABLE rag.messages ENABLE ROW LEVEL SECURITY;

-- Drop existing policies first
DROP POLICY IF EXISTS "Users can view own documents" ON rag.documents;
DROP POLICY IF EXISTS "Users can insert own documents" ON rag.documents;
DROP POLICY IF EXISTS "Users can update own documents" ON rag.documents;
DROP POLICY IF EXISTS "Users can delete own documents" ON rag.documents;
DROP POLICY IF EXISTS "Service role has full access to documents" ON rag.documents;

-- Policies for authenticated users
CREATE POLICY "Users can view own documents" ON rag.documents
    FOR SELECT USING (auth.uid() = user_id);

CREATE POLICY "Users can insert own documents" ON rag.documents
    FOR INSERT WITH CHECK (auth.uid() = user_id);

CREATE POLICY "Users can update own documents" ON rag.documents
    FOR UPDATE USING (auth.uid() = user_id);

CREATE POLICY "Users can delete own documents" ON rag.documents
    FOR DELETE USING (auth.uid() = user_id);

-- Service role bypass
CREATE POLICY "Service role has full access to documents" ON rag.documents
    FOR ALL USING (auth.role() = 'service_role');

CREATE POLICY "Service role has full access to chunks" ON rag.chunks
    FOR ALL USING (auth.role() = 'service_role');

CREATE POLICY "Service role has full access to collections" ON rag.collections
    FOR ALL USING (auth.role() = 'service_role');

CREATE POLICY "Service role has full access to conversations" ON rag.conversations
    FOR ALL USING (auth.role() = 'service_role');

CREATE POLICY "Service role has full access to messages" ON rag.messages
    FOR ALL USING (auth.role() = 'service_role');

-- =============================================================================
-- Grant permissions
-- =============================================================================

GRANT ALL ON ALL TABLES IN SCHEMA rag TO service_role;
GRANT ALL ON ALL SEQUENCES IN SCHEMA rag TO service_role;
GRANT ALL ON ALL FUNCTIONS IN SCHEMA rag TO service_role;

GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA rag TO authenticated;
GRANT USAGE ON ALL SEQUENCES IN SCHEMA rag TO authenticated;
GRANT EXECUTE ON ALL FUNCTIONS IN SCHEMA rag TO authenticated;

-- =============================================================================
-- Maintenance: Cleanup functions
-- =============================================================================

-- Clean up orphaned chunks (chunks without documents)
CREATE OR REPLACE FUNCTION rag.cleanup_orphaned_chunks()
RETURNS INTEGER
LANGUAGE plpgsql
AS $$
DECLARE
    deleted_count INTEGER;
BEGIN
    DELETE FROM rag.chunks 
    WHERE document_id NOT IN (SELECT id FROM rag.documents);
    GET DIAGNOSTICS deleted_count = ROW_COUNT;
    RETURN deleted_count;
END;
$$;

-- =============================================================================
-- Verification
-- =============================================================================

DO $$
BEGIN
    -- Verify pgvector is installed
    IF NOT EXISTS (SELECT 1 FROM pg_extension WHERE extname = 'vector') THEN
        RAISE EXCEPTION 'pgvector extension not installed!';
    END IF;
    
    -- Verify HNSW index was created
    IF NOT EXISTS (
        SELECT 1 FROM pg_indexes 
        WHERE indexname = 'idx_chunks_embedding_hnsw'
    ) THEN
        RAISE WARNING 'HNSW index not created - vector search will be slow';
    END IF;
    
    RAISE NOTICE 'Supabase initialization completed successfully!';
    RAISE NOTICE 'Vector dimension: 768 (nomic-embed-text)';
    RAISE NOTICE 'Index type: HNSW (m=16, ef_construction=64)';
END
$$;
