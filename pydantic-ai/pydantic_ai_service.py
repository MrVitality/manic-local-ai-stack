"""
Pydantic AI Service - FastAPI wrapper for local LLM interactions
"""
import os
import httpx
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional, List

app = FastAPI(title="Pydantic AI Service", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

OLLAMA_URL = os.getenv("OLLAMA_EXTERNAL_URL", "http://localhost:11434")

class ChatRequest(BaseModel):
    message: str
    model: str = "llama3.2:3b"
    system_prompt: Optional[str] = None
    temperature: float = 0.7

class ChatResponse(BaseModel):
    response: str
    model: str
    tokens_used: Optional[int] = None

class Message(BaseModel):
    role: str
    content: str

class MultiTurnRequest(BaseModel):
    messages: List[Message]
    model: str = "llama3.2:3b"
    system_prompt: Optional[str] = None
    temperature: float = 0.7

@app.get("/health")
async def health():
    return {"status": "healthy", "ollama_url": OLLAMA_URL}

@app.get("/models")
async def list_models():
    async with httpx.AsyncClient() as client:
        try:
            resp = await client.get(f"{OLLAMA_URL}/api/tags", timeout=10)
            return resp.json()
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

@app.post("/chat", response_model=ChatResponse)
async def chat(request: ChatRequest):
    messages = []
    if request.system_prompt:
        messages.append({"role": "system", "content": request.system_prompt})
    messages.append({"role": "user", "content": request.message})
    
    async with httpx.AsyncClient() as client:
        try:
            resp = await client.post(
                f"{OLLAMA_URL}/api/chat",
                json={
                    "model": request.model,
                    "messages": messages,
                    "stream": False,
                    "options": {"temperature": request.temperature}
                },
                timeout=120
            )
            data = resp.json()
            return ChatResponse(
                response=data.get("message", {}).get("content", ""),
                model=request.model,
                tokens_used=data.get("eval_count")
            )
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

@app.post("/chat/multi", response_model=ChatResponse)
async def multi_turn_chat(request: MultiTurnRequest):
    messages = []
    if request.system_prompt:
        messages.append({"role": "system", "content": request.system_prompt})
    messages.extend([{"role": m.role, "content": m.content} for m in request.messages])
    
    async with httpx.AsyncClient() as client:
        try:
            resp = await client.post(
                f"{OLLAMA_URL}/api/chat",
                json={
                    "model": request.model,
                    "messages": messages,
                    "stream": False,
                    "options": {"temperature": request.temperature}
                },
                timeout=120
            )
            data = resp.json()
            return ChatResponse(
                response=data.get("message", {}).get("content", ""),
                model=request.model,
                tokens_used=data.get("eval_count")
            )
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

@app.post("/embeddings")
async def generate_embeddings(text: str, model: str = "nomic-embed-text"):
    async with httpx.AsyncClient() as client:
        try:
            resp = await client.post(
                f"{OLLAMA_URL}/api/embeddings",
                json={"model": model, "prompt": text},
                timeout=60
            )
            return resp.json()
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8080)
