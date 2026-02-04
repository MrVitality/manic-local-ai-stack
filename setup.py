#!/usr/bin/env python3
"""
Ultimate AI Stack Deployer - Package Setup

Install with: pip install -e .
"""

from setuptools import setup, find_packages
from pathlib import Path

# Read README for long description
readme_path = Path(__file__).parent / "README.md"
long_description = readme_path.read_text() if readme_path.exists() else ""

setup(
    name="ai-stack-deployer",
    version="1.0.0",
    author="AI Stack Deployer",
    author_email="",
    description="Comprehensive deployment tool for self-hosted AI infrastructure",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/your-repo/ai-stack-deployer",
    packages=find_packages(),
    classifiers=[
        "Development Status :: 4 - Beta",
        "Intended Audience :: Developers",
        "Intended Audience :: System Administrators",
        "License :: OSI Approved :: MIT License",
        "Operating System :: POSIX :: Linux",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
        "Programming Language :: Python :: 3.12",
        "Topic :: System :: Systems Administration",
        "Topic :: Software Development :: Libraries :: Python Modules",
    ],
    python_requires=">=3.10",
    install_requires=[
        "pyyaml>=6.0.1",
        "requests>=2.31.0",
        "rich>=13.7.0",
    ],
    extras_require={
        "dev": [
            "pytest>=7.4.0",
            "pytest-asyncio>=0.21.0",
            "black>=23.0.0",
            "mypy>=1.7.0",
            "ruff>=0.1.0",
        ],
        "full": [
            "asyncpg>=0.29.0",
            "psycopg2-binary>=2.9.9",
            "redis>=5.0.0",
            "prometheus-client>=0.19.0",
            "cryptography>=41.0.0",
        ],
    },
    entry_points={
        "console_scripts": [
            "ai-stack=deployer.__main__:main",
            "ai-deploy=deployer.__main__:main",
        ],
    },
    include_package_data=True,
    package_data={
        "deployer": ["sql/*.sql", "templates/*"],
    },
)
