"""
Model management for Ollama and other LLM providers.

Handles:
- Model pulling and updating
- Model inventory management
- Memory optimization
- Model warmup and preloading
- Embedding model management
"""

import time
import json
import logging
from typing import Optional, Dict, List, Any
from dataclasses import dataclass, field
from datetime import datetime
import requests
from concurrent.futures import ThreadPoolExecutor

from .config import StackConfig

logger = logging.getLogger(__name__)


@dataclass
class ModelInfo:
    """Information about an installed model."""
    name: str
    size_bytes: int
    modified_at: str
    digest: str
    details: Dict[str, Any] = field(default_factory=dict)
    
    @property
    def size_gb(self) -> float:
        return self.size_bytes / (1024 ** 3)
    
    @property
    def size_human(self) -> str:
        if self.size_bytes > 1024 ** 3:
            return f"{self.size_gb:.1f} GB"
        elif self.size_bytes > 1024 ** 2:
            return f"{self.size_bytes / (1024 ** 2):.1f} MB"
        else:
            return f"{self.size_bytes / 1024:.1f} KB"


@dataclass
class ModelPullProgress:
    """Progress information for model pull operation."""
    model: str
    status: str
    completed_bytes: int = 0
    total_bytes: int = 0
    
    @property
    def percent(self) -> float:
        if self.total_bytes == 0:
            return 0
        return (self.completed_bytes / self.total_bytes) * 100


class ModelManager:
    """
    Manages LLM and embedding models for the AI Stack.
    
    Features:
    - Pull and update models from Ollama
    - Track installed models
    - Manage model memory usage
    - Preload models for faster response
    - Handle embedding models separately
    """
    
    # Recommended models for different use cases
    RECOMMENDED_MODELS = {
        "chat": [
            {"name": "llama3.2:3b", "description": "Fast, good quality (2GB)", "min_ram": 4},
            {"name": "llama3.2:1b", "description": "Fastest, compact (1GB)", "min_ram": 2},
            {"name": "qwen2.5:3b", "description": "Good multilingual support (2GB)", "min_ram": 4},
            {"name": "phi3:mini", "description": "Microsoft Phi-3 mini (2.5GB)", "min_ram": 4},
            {"name": "mistral:7b", "description": "High quality reasoning (4.5GB)", "min_ram": 8},
            {"name": "llama3.1:8b", "description": "Best quality small model (5GB)", "min_ram": 10},
        ],
        "code": [
            {"name": "qwen2.5-coder:3b", "description": "Code generation (2GB)", "min_ram": 4},
            {"name": "deepseek-coder:6.7b", "description": "Advanced coding (4GB)", "min_ram": 8},
            {"name": "codellama:7b", "description": "Meta's code model (4GB)", "min_ram": 8},
        ],
        "embedding": [
            {"name": "nomic-embed-text", "description": "768 dims, high quality (275MB)", "min_ram": 1},
            {"name": "mxbai-embed-large", "description": "1024 dims, best quality (670MB)", "min_ram": 2},
            {"name": "all-minilm", "description": "384 dims, fastest (45MB)", "min_ram": 1},
        ],
        "vision": [
            {"name": "llava:7b", "description": "Vision + language (5GB)", "min_ram": 10},
            {"name": "llava-phi3", "description": "Smaller vision model (2.5GB)", "min_ram": 6},
        ]
    }
    
    def __init__(self, config: StackConfig):
        """Initialize model manager."""
        self.config = config
        self.base_url = config.ollama.base_url
    
    def _request(self, method: str, endpoint: str, **kwargs) -> requests.Response:
        """Make a request to Ollama API."""
        url = f"{self.base_url}{endpoint}"
        kwargs.setdefault("timeout", 30)
        return requests.request(method, url, **kwargs)
    
    def is_available(self) -> bool:
        """Check if Ollama is available."""
        try:
            response = self._request("GET", "/api/tags")
            return response.status_code == 200
        except requests.RequestException:
            return False
    
    def list_models(self) -> List[ModelInfo]:
        """List all installed models."""
        try:
            response = self._request("GET", "/api/tags")
            if response.status_code != 200:
                return []
            
            data = response.json()
            models = []
            
            for model_data in data.get("models", []):
                models.append(ModelInfo(
                    name=model_data.get("name", ""),
                    size_bytes=model_data.get("size", 0),
                    modified_at=model_data.get("modified_at", ""),
                    digest=model_data.get("digest", ""),
                    details=model_data.get("details", {})
                ))
            
            return models
            
        except requests.RequestException as e:
            logger.error(f"Failed to list models: {e}")
            return []
    
    def get_model_info(self, model_name: str) -> Optional[ModelInfo]:
        """Get detailed information about a specific model."""
        try:
            response = self._request("POST", "/api/show", json={"name": model_name})
            if response.status_code != 200:
                return None
            
            data = response.json()
            return ModelInfo(
                name=model_name,
                size_bytes=data.get("size", 0),
                modified_at=data.get("modified_at", ""),
                digest=data.get("digest", ""),
                details={
                    "license": data.get("license", ""),
                    "modelfile": data.get("modelfile", ""),
                    "parameters": data.get("parameters", ""),
                    "template": data.get("template", ""),
                    "system": data.get("system", "")
                }
            )
            
        except requests.RequestException as e:
            logger.error(f"Failed to get model info: {e}")
            return None
    
    def pull_model(
        self, 
        model_name: str, 
        progress_callback: Optional[callable] = None
    ) -> bool:
        """
        Pull a model from Ollama registry.
        
        Args:
            model_name: Name of the model to pull (e.g., "llama3.2:3b")
            progress_callback: Optional callback for progress updates
        
        Returns:
            True if successful, False otherwise
        """
        try:
            logger.info(f"Pulling model: {model_name}")
            
            response = requests.post(
                f"{self.base_url}/api/pull",
                json={"name": model_name},
                stream=True,
                timeout=7200  # 2 hours for large models
            )
            
            for line in response.iter_lines():
                if line:
                    data = json.loads(line)
                    
                    status = data.get("status", "")
                    
                    if progress_callback:
                        progress = ModelPullProgress(
                            model=model_name,
                            status=status,
                            completed_bytes=data.get("completed", 0),
                            total_bytes=data.get("total", 0)
                        )
                        progress_callback(progress)
                    
                    if status == "success":
                        logger.info(f"Successfully pulled: {model_name}")
                        return True
                    
                    if "error" in data:
                        logger.error(f"Pull error: {data['error']}")
                        return False
            
            return True
            
        except requests.RequestException as e:
            logger.error(f"Failed to pull model {model_name}: {e}")
            return False
    
    def delete_model(self, model_name: str) -> bool:
        """Delete a model from Ollama."""
        try:
            response = self._request("DELETE", "/api/delete", json={"name": model_name})
            
            if response.status_code == 200:
                logger.info(f"Deleted model: {model_name}")
                return True
            else:
                logger.error(f"Failed to delete model: {response.text}")
                return False
                
        except requests.RequestException as e:
            logger.error(f"Delete request failed: {e}")
            return False
    
    def copy_model(self, source: str, destination: str) -> bool:
        """Create a copy of a model with a new name."""
        try:
            response = self._request(
                "POST", "/api/copy",
                json={"source": source, "destination": destination}
            )
            return response.status_code == 200
        except requests.RequestException as e:
            logger.error(f"Copy failed: {e}")
            return False
    
    def create_modelfile(
        self,
        name: str,
        base_model: str,
        system_prompt: Optional[str] = None,
        parameters: Optional[Dict[str, Any]] = None
    ) -> bool:
        """
        Create a custom model from a Modelfile.
        
        Args:
            name: Name for the new model
            base_model: Base model to derive from
            system_prompt: Custom system prompt
            parameters: Model parameters (temperature, etc.)
        """
        modelfile_lines = [f"FROM {base_model}"]
        
        if system_prompt:
            modelfile_lines.append(f'SYSTEM """{system_prompt}"""')
        
        if parameters:
            for key, value in parameters.items():
                modelfile_lines.append(f"PARAMETER {key} {value}")
        
        modelfile = "\n".join(modelfile_lines)
        
        try:
            response = requests.post(
                f"{self.base_url}/api/create",
                json={"name": name, "modelfile": modelfile},
                stream=True,
                timeout=3600
            )
            
            for line in response.iter_lines():
                if line:
                    data = json.loads(line)
                    if data.get("status") == "success":
                        logger.info(f"Created model: {name}")
                        return True
                    if "error" in data:
                        logger.error(f"Create error: {data['error']}")
                        return False
            
            return True
            
        except requests.RequestException as e:
            logger.error(f"Create failed: {e}")
            return False
    
    def load_model(self, model_name: str, keep_alive: str = "5m") -> bool:
        """
        Load a model into memory.
        
        Args:
            model_name: Model to load
            keep_alive: How long to keep in memory (e.g., "5m", "1h", "-1" for forever)
        """
        try:
            response = self._request(
                "POST", "/api/generate",
                json={
                    "model": model_name,
                    "prompt": "",
                    "keep_alive": keep_alive
                },
                timeout=120
            )
            return response.status_code == 200
        except requests.RequestException as e:
            logger.error(f"Failed to load model: {e}")
            return False
    
    def unload_model(self, model_name: str) -> bool:
        """Unload a model from memory."""
        try:
            response = self._request(
                "POST", "/api/generate",
                json={
                    "model": model_name,
                    "prompt": "",
                    "keep_alive": 0
                }
            )
            return response.status_code == 200
        except requests.RequestException as e:
            logger.error(f"Failed to unload model: {e}")
            return False
    
    def unload_all_models(self) -> int:
        """Unload all models from memory. Returns count of models unloaded."""
        models = self.list_models()
        count = 0
        for model in models:
            if self.unload_model(model.name):
                count += 1
        return count
    
    def get_running_models(self) -> List[Dict[str, Any]]:
        """Get list of models currently loaded in memory."""
        try:
            response = self._request("GET", "/api/ps")
            if response.status_code == 200:
                return response.json().get("models", [])
        except requests.RequestException:
            pass
        return []
    
    def warmup_models(self, models: Optional[List[str]] = None):
        """
        Preload models into memory for faster first response.
        
        Args:
            models: List of model names to warmup. Uses config defaults if None.
        """
        if models is None:
            models = self.config.ollama.models
        
        logger.info(f"Warming up {len(models)} models")
        
        for model_name in models:
            logger.info(f"Warming up: {model_name}")
            self.load_model(model_name, keep_alive=self.config.ollama.keep_alive)
    
    def generate_embedding(self, model: str, text: str) -> Optional[List[float]]:
        """
        Generate an embedding vector for text.
        
        Args:
            model: Embedding model to use (e.g., "nomic-embed-text")
            text: Text to embed
        
        Returns:
            Embedding vector or None on failure
        """
        try:
            response = self._request(
                "POST", "/api/embeddings",
                json={"model": model, "prompt": text},
                timeout=60
            )
            
            if response.status_code == 200:
                return response.json().get("embedding")
            
        except requests.RequestException as e:
            logger.error(f"Embedding generation failed: {e}")
        
        return None
    
    def generate_embeddings_batch(
        self,
        model: str,
        texts: List[str],
        batch_size: int = 10
    ) -> List[Optional[List[float]]]:
        """
        Generate embeddings for multiple texts.
        
        Args:
            model: Embedding model to use
            texts: List of texts to embed
            batch_size: Number of parallel requests
        
        Returns:
            List of embedding vectors (None for failures)
        """
        results = [None] * len(texts)
        
        with ThreadPoolExecutor(max_workers=batch_size) as executor:
            futures = {
                executor.submit(self.generate_embedding, model, text): i
                for i, text in enumerate(texts)
            }
            
            for future in futures:
                idx = futures[future]
                try:
                    results[idx] = future.result()
                except Exception as e:
                    logger.warning(f"Embedding failed for text {idx}: {e}")
        
        return results
    
    def get_recommendations(self, available_ram_gb: int = 16) -> Dict[str, List[Dict[str, Any]]]:
        """
        Get model recommendations based on available RAM.
        
        Args:
            available_ram_gb: Available RAM in GB
        
        Returns:
            Dict of recommended models by category
        """
        recommendations = {}
        
        for category, models in self.RECOMMENDED_MODELS.items():
            recommendations[category] = [
                model for model in models
                if model["min_ram"] <= available_ram_gb
            ]
        
        return recommendations
    
    def pull_recommended_models(
        self,
        categories: Optional[List[str]] = None,
        available_ram_gb: int = 16
    ) -> Dict[str, bool]:
        """
        Pull recommended models for specified categories.
        
        Args:
            categories: List of categories ("chat", "code", "embedding", "vision")
            available_ram_gb: Available RAM for filtering
        
        Returns:
            Dict of model_name -> success status
        """
        if categories is None:
            categories = ["chat", "embedding"]
        
        recommendations = self.get_recommendations(available_ram_gb)
        results = {}
        
        for category in categories:
            if category not in recommendations:
                continue
            
            # Pull the first (best) model in each category
            models = recommendations[category]
            if models:
                model_name = models[0]["name"]
                logger.info(f"Pulling {category} model: {model_name}")
                results[model_name] = self.pull_model(model_name)
        
        return results
    
    def calculate_memory_usage(self) -> Dict[str, Any]:
        """Calculate total memory usage of installed models."""
        models = self.list_models()
        
        total_size = sum(m.size_bytes for m in models)
        running = self.get_running_models()
        loaded_size = sum(r.get("size", 0) for r in running)
        
        return {
            "installed_count": len(models),
            "installed_size_bytes": total_size,
            "installed_size_human": f"{total_size / (1024**3):.1f} GB",
            "loaded_count": len(running),
            "loaded_size_bytes": loaded_size,
            "loaded_size_human": f"{loaded_size / (1024**3):.1f} GB",
            "models": [
                {"name": m.name, "size": m.size_human}
                for m in sorted(models, key=lambda x: x.size_bytes, reverse=True)
            ]
        }
    
    def ensure_models(self, models: List[str]) -> Dict[str, bool]:
        """
        Ensure specified models are installed, pulling if necessary.
        
        Args:
            models: List of model names to ensure
        
        Returns:
            Dict of model_name -> success status
        """
        installed = {m.name for m in self.list_models()}
        results = {}
        
        for model in models:
            if model in installed:
                results[model] = True
                logger.info(f"Model already installed: {model}")
            else:
                logger.info(f"Model not found, pulling: {model}")
                results[model] = self.pull_model(model)
        
        return results
