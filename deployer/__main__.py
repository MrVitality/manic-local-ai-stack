#!/usr/bin/env python3
"""
Ultimate AI Stack Deployer - Command Line Interface

A comprehensive deployment tool for self-hosted AI infrastructure.

Usage:
    python -m deployer deploy [--profile PROFILE] [--domain DOMAIN]
    python -m deployer status
    python -m deployer logs [SERVICE]
    python -m deployer backup [--type TYPE]
    python -m deployer restore BACKUP_ID
    python -m deployer models list
    python -m deployer models pull MODEL_NAME
    python -m deployer health
"""

import argparse
import sys
import json
from pathlib import Path
from typing import Optional

from .config import StackConfig, DeploymentProfile, NetworkMode
from .core import AIStackDeployer
from .services import ServiceManager
from .health import HealthChecker
from .backup import BackupManager, BackupType
from .models import ModelManager


def print_banner():
    """Print the application banner."""
    banner = """
╔═══════════════════════════════════════════════════════════════════╗
║                  🚀 Ultimate AI Stack Deployer                    ║
║                                                                   ║
║  Self-hosted AI infrastructure made simple                        ║
║                                                                   ║
║  Services: Ollama, Supabase, n8n, Qdrant, Langfuse, and more     ║
╚═══════════════════════════════════════════════════════════════════╝
"""
    print(banner)


def print_status_table(services: dict):
    """Print a formatted status table."""
    print("\n" + "=" * 70)
    print(f"{'Service':<20} {'Status':<12} {'Memory':<12} {'Ports':<20}")
    print("=" * 70)
    
    status_colors = {
        "running": "\033[92m",  # Green
        "stopped": "\033[91m",  # Red
        "starting": "\033[93m",  # Yellow
        "unhealthy": "\033[91m",  # Red
        "unknown": "\033[90m",  # Gray
    }
    reset = "\033[0m"
    
    for name, info in sorted(services.items()):
        status = info.status.value if hasattr(info.status, 'value') else str(info.status)
        color = status_colors.get(status, "")
        ports = ", ".join(info.ports[:2]) if info.ports else "-"
        memory = info.memory_usage or "-"
        
        print(f"{name:<20} {color}{status:<12}{reset} {memory:<12} {ports:<20}")
    
    print("=" * 70)


def cmd_deploy(args):
    """Handle deploy command."""
    print_banner()
    print("🔧 Initializing deployment...\n")
    
    # Create configuration
    config = StackConfig(
        project_name=args.name or "ultimate-ai-stack",
        profile=DeploymentProfile(args.profile),
        network_mode=NetworkMode(args.network),
        domain=args.domain or "localhost",
        total_memory_gb=args.memory,
        total_cpus=args.cpus
    )
    
    if args.base_dir:
        config.base_dir = Path(args.base_dir)
        config.data_dir = config.base_dir / "data"
        config.config_dir = config.base_dir / "config"
        config.backup_dir = config.base_dir / "backups"
        config.logs_dir = config.base_dir / "logs"
    
    # Validate configuration
    issues = config.validate()
    if issues:
        print("⚠️  Configuration warnings:")
        for issue in issues:
            print(f"   - {issue}")
        print()
    
    # Print configuration summary
    print("📋 Configuration Summary:")
    print(f"   Project: {config.project_name}")
    print(f"   Profile: {config.profile.value}")
    print(f"   Network: {config.network_mode.value}")
    print(f"   Domain:  {config.domain}")
    print(f"   Memory:  {config.total_memory_gb}GB")
    print(f"   CPUs:    {config.total_cpus}")
    print(f"   Base:    {config.base_dir}")
    print()
    
    enabled_services = config.get_enabled_services()
    print(f"📦 Services to deploy ({len(enabled_services)}):")
    for name in sorted(enabled_services.keys()):
        svc = enabled_services[name]
        print(f"   - {name}: {svc.resources.memory}")
    print()
    
    print(f"💾 Total memory allocation: {config.calculate_total_memory()}")
    print()
    
    if not args.yes:
        response = input("Proceed with deployment? [y/N] ")
        if response.lower() != 'y':
            print("Deployment cancelled.")
            return 1
    
    # Deploy
    deployer = AIStackDeployer(config)
    
    def progress(msg):
        print(f"   {msg}")
    
    print("\n🚀 Starting deployment...")
    result = deployer.deploy(
        pull=not args.no_pull,
        build=args.build,
        progress_callback=progress
    )
    
    if result.success:
        print(f"\n✅ Deployment completed in {result.duration_seconds:.1f}s")
        print(f"   Started {len(result.services_started)} services")
        
        if result.warnings:
            print("\n⚠️  Warnings:")
            for warning in result.warnings:
                print(f"   - {warning}")
        
        print("\n📍 Access your services:")
        print(f"   Open WebUI:      http://localhost:3003")
        print(f"   n8n:             http://localhost:5678")
        print(f"   Supabase Studio: http://localhost:3001")
        print(f"   Langfuse:        http://localhost:3002")
        print(f"   Flowise:         http://localhost:3004")
        print(f"   SearXNG:         http://localhost:8888")
        print(f"   Ollama API:      http://localhost:11434")
        
        # Pull models if requested
        if args.models:
            print("\n📥 Pulling default models...")
            model_manager = ModelManager(config)
            results = model_manager.pull_recommended_models(
                categories=["chat", "embedding"],
                available_ram_gb=config.total_memory_gb
            )
            for model, success in results.items():
                status = "✅" if success else "❌"
                print(f"   {status} {model}")
        
        return 0
    else:
        print(f"\n❌ Deployment failed: {result.message}")
        return 1


def cmd_status(args):
    """Handle status command."""
    config = StackConfig()
    if args.base_dir:
        config.base_dir = Path(args.base_dir)
    
    service_manager = ServiceManager(config)
    services = service_manager.get_all_services()
    
    if args.json:
        output = {
            name: {
                "status": info.status.value,
                "ports": info.ports,
                "memory": info.memory_usage,
                "health": info.health
            }
            for name, info in services.items()
        }
        print(json.dumps(output, indent=2))
    else:
        print_status_table(services)


def cmd_logs(args):
    """Handle logs command."""
    config = StackConfig()
    deployer = AIStackDeployer(config)
    deployer.logs(service=args.service, follow=args.follow, tail=args.tail)


def cmd_stop(args):
    """Handle stop command."""
    config = StackConfig()
    deployer = AIStackDeployer(config)
    
    if args.remove_volumes:
        response = input("⚠️  This will delete all data! Are you sure? [y/N] ")
        if response.lower() != 'y':
            print("Cancelled.")
            return 1
    
    result = deployer.stop(remove_volumes=args.remove_volumes)
    if result.success:
        print("✅ Services stopped")
    else:
        print(f"❌ Failed: {result.message}")
        return 1


def cmd_restart(args):
    """Handle restart command."""
    config = StackConfig()
    deployer = AIStackDeployer(config)
    result = deployer.restart(service=args.service)
    
    if result.success:
        print(f"✅ {result.message}")
    else:
        print(f"❌ {result.message}")
        return 1


def cmd_backup(args):
    """Handle backup command."""
    config = StackConfig()
    backup_manager = BackupManager(config)
    
    if args.action == "create":
        backup_type = BackupType(args.type) if args.type else BackupType.FULL
        
        print(f"📦 Creating {backup_type.value} backup...")
        
        if backup_type == BackupType.FULL:
            result = backup_manager.backup_full()
        elif backup_type == BackupType.DATABASE:
            result = backup_manager.backup_database()
        elif backup_type == BackupType.VOLUMES:
            result = backup_manager.backup_volumes()
        elif backup_type == BackupType.CONFIG:
            result = backup_manager.backup_config()
        
        if result:
            print(f"✅ Backup created: {result.id}")
            print(f"   Path: {result.path}")
            print(f"   Size: {result._human_size(result.size_bytes)}")
        else:
            print("❌ Backup failed")
            return 1
    
    elif args.action == "list":
        backups = backup_manager.list_backups()
        
        if not backups:
            print("No backups found.")
            return
        
        print("\n" + "=" * 80)
        print(f"{'ID':<35} {'Type':<10} {'Size':<12} {'Date':<20}")
        print("=" * 80)
        
        for backup in backups:
            print(f"{backup.id:<35} {backup.type.value:<10} "
                  f"{backup._human_size(backup.size_bytes):<12} "
                  f"{backup.timestamp.strftime('%Y-%m-%d %H:%M'):<20}")
        
        print("=" * 80)
        
        stats = backup_manager.get_backup_stats()
        print(f"\nTotal: {stats['total_backups']} backups, {stats['total_size_human']}")
    
    elif args.action == "restore":
        if not args.backup_id:
            print("❌ Backup ID required for restore")
            return 1
        
        backups = backup_manager.list_backups()
        backup = next((b for b in backups if b.id == args.backup_id), None)
        
        if not backup:
            print(f"❌ Backup not found: {args.backup_id}")
            return 1
        
        print(f"⚠️  Restoring from: {backup.id}")
        print(f"   Type: {backup.type.value}")
        print(f"   Date: {backup.timestamp}")
        
        response = input("\nThis will overwrite existing data! Continue? [y/N] ")
        if response.lower() != 'y':
            print("Cancelled.")
            return 1
        
        if backup.type == BackupType.DATABASE:
            success = backup_manager.restore_database(backup.path)
        elif backup.type == BackupType.VOLUMES:
            success = backup_manager.restore_volumes(backup.path)
        elif backup.type == BackupType.CONFIG:
            success = backup_manager.restore_config(backup.path)
        else:
            print("❌ Full backup restore not yet implemented")
            return 1
        
        if success:
            print("✅ Restore completed")
        else:
            print("❌ Restore failed")
            return 1
    
    elif args.action == "delete":
        if not args.backup_id:
            print("❌ Backup ID required for delete")
            return 1
        
        if backup_manager.delete_backup(args.backup_id):
            print(f"✅ Deleted: {args.backup_id}")
        else:
            print(f"❌ Failed to delete: {args.backup_id}")
            return 1


def cmd_models(args):
    """Handle models command."""
    config = StackConfig()
    model_manager = ModelManager(config)
    
    if not model_manager.is_available():
        print("❌ Ollama is not available. Make sure it's running.")
        return 1
    
    if args.action == "list":
        models = model_manager.list_models()
        
        if not models:
            print("No models installed.")
            return
        
        print("\n" + "=" * 60)
        print(f"{'Model':<35} {'Size':<15} {'Modified':<20}")
        print("=" * 60)
        
        for model in sorted(models, key=lambda m: m.name):
            modified = model.modified_at[:10] if model.modified_at else "-"
            print(f"{model.name:<35} {model.size_human:<15} {modified:<20}")
        
        print("=" * 60)
        
        usage = model_manager.calculate_memory_usage()
        print(f"\nTotal: {usage['installed_count']} models, {usage['installed_size_human']}")
        print(f"Loaded: {usage['loaded_count']} models, {usage['loaded_size_human']}")
    
    elif args.action == "pull":
        if not args.model_name:
            print("❌ Model name required")
            return 1
        
        print(f"📥 Pulling model: {args.model_name}")
        
        def progress(p):
            if p.total_bytes > 0:
                pct = (p.completed_bytes / p.total_bytes) * 100
                bar = "█" * int(pct / 5) + "░" * (20 - int(pct / 5))
                print(f"\r   [{bar}] {pct:.1f}% - {p.status}", end="", flush=True)
            else:
                print(f"\r   {p.status}", end="", flush=True)
        
        success = model_manager.pull_model(args.model_name, progress_callback=progress)
        print()
        
        if success:
            print(f"✅ Model pulled: {args.model_name}")
        else:
            print(f"❌ Failed to pull: {args.model_name}")
            return 1
    
    elif args.action == "delete":
        if not args.model_name:
            print("❌ Model name required")
            return 1
        
        if model_manager.delete_model(args.model_name):
            print(f"✅ Deleted: {args.model_name}")
        else:
            print(f"❌ Failed to delete: {args.model_name}")
            return 1
    
    elif args.action == "recommend":
        ram = args.ram or 16
        recommendations = model_manager.get_recommendations(ram)
        
        print(f"\n📋 Recommended models for {ram}GB RAM:\n")
        
        for category, models in recommendations.items():
            print(f"  {category.upper()}:")
            for model in models[:3]:
                print(f"    - {model['name']}: {model['description']}")
            print()


def cmd_health(args):
    """Handle health command."""
    config = StackConfig()
    service_manager = ServiceManager(config)
    health_checker = HealthChecker(config, service_manager)
    
    if args.json:
        report = health_checker.get_health_report()
        print(json.dumps(report, indent=2))
    else:
        print("🏥 Health Check Report\n")
        
        results = health_checker.check_all()
        
        status_icons = {
            "healthy": "✅",
            "degraded": "⚠️",
            "unhealthy": "❌",
            "unknown": "❓"
        }
        
        for service, result in sorted(results.items()):
            icon = status_icons.get(result.status.value, "❓")
            time_str = f"({result.response_time_ms:.0f}ms)" if result.response_time_ms else ""
            print(f"  {icon} {service:<20} {result.status.value:<12} {time_str}")
            if result.message and result.status.value != "healthy":
                print(f"     └─ {result.message}")
        
        overall = health_checker.get_overall_status()
        icon = status_icons.get(overall.value, "❓")
        print(f"\n{icon} Overall Status: {overall.value.upper()}")


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Ultimate AI Stack Deployer - Self-hosted AI infrastructure"
    )
    subparsers = parser.add_subparsers(dest="command", help="Available commands")
    
    # Deploy command
    deploy_parser = subparsers.add_parser("deploy", help="Deploy the AI stack")
    deploy_parser.add_argument("--name", help="Project name")
    deploy_parser.add_argument("--profile", choices=["minimal", "standard", "full"],
                              default="standard", help="Deployment profile")
    deploy_parser.add_argument("--network", choices=["localhost", "tailscale", "public"],
                              default="localhost", help="Network mode")
    deploy_parser.add_argument("--domain", help="Domain name")
    deploy_parser.add_argument("--memory", type=int, default=16, help="Total RAM in GB")
    deploy_parser.add_argument("--cpus", type=int, default=4, help="Number of CPUs")
    deploy_parser.add_argument("--base-dir", help="Base directory for deployment")
    deploy_parser.add_argument("--no-pull", action="store_true", help="Skip pulling images")
    deploy_parser.add_argument("--build", action="store_true", help="Build custom images")
    deploy_parser.add_argument("--models", action="store_true", help="Pull recommended models")
    deploy_parser.add_argument("-y", "--yes", action="store_true", help="Skip confirmation")
    
    # Status command
    status_parser = subparsers.add_parser("status", help="Show service status")
    status_parser.add_argument("--base-dir", help="Base directory")
    status_parser.add_argument("--json", action="store_true", help="Output as JSON")
    
    # Logs command
    logs_parser = subparsers.add_parser("logs", help="View service logs")
    logs_parser.add_argument("service", nargs="?", help="Service name")
    logs_parser.add_argument("-f", "--follow", action="store_true", help="Follow logs")
    logs_parser.add_argument("-n", "--tail", type=int, default=100, help="Number of lines")
    
    # Stop command
    stop_parser = subparsers.add_parser("stop", help="Stop all services")
    stop_parser.add_argument("-v", "--remove-volumes", action="store_true",
                            help="Remove volumes (deletes all data!)")
    
    # Restart command
    restart_parser = subparsers.add_parser("restart", help="Restart services")
    restart_parser.add_argument("service", nargs="?", help="Service name (all if not specified)")
    
    # Backup command
    backup_parser = subparsers.add_parser("backup", help="Backup management")
    backup_parser.add_argument("action", choices=["create", "list", "restore", "delete"],
                              default="list", nargs="?", help="Backup action")
    backup_parser.add_argument("--type", choices=["full", "database", "volumes", "config"],
                              help="Backup type")
    backup_parser.add_argument("--backup-id", help="Backup ID for restore/delete")
    
    # Models command
    models_parser = subparsers.add_parser("models", help="Model management")
    models_parser.add_argument("action", choices=["list", "pull", "delete", "recommend"],
                              default="list", nargs="?", help="Action")
    models_parser.add_argument("model_name", nargs="?", help="Model name")
    models_parser.add_argument("--ram", type=int, help="Available RAM for recommendations")
    
    # Health command
    health_parser = subparsers.add_parser("health", help="Health check")
    health_parser.add_argument("--json", action="store_true", help="Output as JSON")
    
    args = parser.parse_args()
    
    if not args.command:
        parser.print_help()
        return 1
    
    commands = {
        "deploy": cmd_deploy,
        "status": cmd_status,
        "logs": cmd_logs,
        "stop": cmd_stop,
        "restart": cmd_restart,
        "backup": cmd_backup,
        "models": cmd_models,
        "health": cmd_health,
    }
    
    handler = commands.get(args.command)
    if handler:
        return handler(args) or 0
    else:
        parser.print_help()
        return 1


if __name__ == "__main__":
    sys.exit(main())
