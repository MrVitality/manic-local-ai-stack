"""
Ultimate AI Stack Deployer
==========================

A comprehensive Python-based deployment system for self-hosted AI infrastructure.

Features:
- Docker Compose generation and management
- Environment configuration and secrets management
- Service health monitoring and auto-recovery
- Backup and restore functionality
- Model management for Ollama
- Database initialization and migrations
- SSL/TLS certificate management
- Resource monitoring and alerting

Author: AI Stack Deployer
License: MIT
"""

__version__ = "1.0.0"
__author__ = "AI Stack Deployer"

from .core import AIStackDeployer
from .config import StackConfig, ServiceConfig
from .services import ServiceManager
from .health import HealthChecker
from .backup import BackupManager
from .models import ModelManager

__all__ = [
    "AIStackDeployer",
    "StackConfig",
    "ServiceConfig",
    "ServiceManager",
    "HealthChecker",
    "BackupManager",
    "ModelManager",
]
