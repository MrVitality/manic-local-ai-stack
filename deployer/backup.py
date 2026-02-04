"""
Backup and restore functionality for AI Stack.

Handles:
- Automated database backups
- Volume snapshot management
- Configuration backup
- Point-in-time recovery
- Backup rotation and cleanup
"""

import os
import subprocess
import shutil
import tarfile
import gzip
import json
from pathlib import Path
from typing import Optional, Dict, List, Any
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
import logging
import threading
import time

from .config import StackConfig

logger = logging.getLogger(__name__)


class BackupType(Enum):
    """Types of backups."""
    FULL = "full"
    DATABASE = "database"
    VOLUMES = "volumes"
    CONFIG = "config"


@dataclass
class BackupInfo:
    """Information about a backup."""
    id: str
    type: BackupType
    timestamp: datetime
    path: Path
    size_bytes: int
    services: List[str]
    compressed: bool = True
    encrypted: bool = False
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "type": self.type.value,
            "timestamp": self.timestamp.isoformat(),
            "path": str(self.path),
            "size_bytes": self.size_bytes,
            "size_human": self._human_size(self.size_bytes),
            "services": self.services,
            "compressed": self.compressed,
            "encrypted": self.encrypted,
            "metadata": self.metadata
        }
    
    @staticmethod
    def _human_size(size_bytes: int) -> str:
        for unit in ["B", "KB", "MB", "GB"]:
            if size_bytes < 1024:
                return f"{size_bytes:.1f} {unit}"
            size_bytes /= 1024
        return f"{size_bytes:.1f} TB"


@dataclass
class BackupSchedule:
    """Backup schedule configuration."""
    enabled: bool = True
    full_backup_interval_hours: int = 168  # Weekly
    database_backup_interval_hours: int = 24  # Daily
    retention_days: int = 30
    retention_count: int = 10  # Minimum backups to keep


class BackupManager:
    """
    Manages backups for the AI Stack.
    
    Features:
    - Full stack backups
    - Database-specific backups
    - Volume backups
    - Configuration backups
    - Scheduled automatic backups
    - Retention policy enforcement
    - Restore operations
    """
    
    def __init__(self, config: StackConfig):
        """Initialize backup manager."""
        self.config = config
        self.backup_dir = config.backup_dir
        self.backup_dir.mkdir(parents=True, exist_ok=True)
        
        self.schedule = BackupSchedule()
        self._scheduler_running = False
        self._scheduler_thread: Optional[threading.Thread] = None
    
    def _generate_backup_id(self, backup_type: BackupType) -> str:
        """Generate unique backup ID."""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        return f"{backup_type.value}_{timestamp}"
    
    def backup_database(self, database: str = "postgres") -> Optional[BackupInfo]:
        """
        Create a PostgreSQL database backup.
        
        Uses pg_dump to create a consistent backup of the database.
        """
        backup_id = self._generate_backup_id(BackupType.DATABASE)
        backup_path = self.backup_dir / f"{backup_id}.sql.gz"
        
        try:
            logger.info(f"Starting database backup: {database}")
            
            # Run pg_dump inside the container
            dump_cmd = [
                "docker", "exec", "supabase-db",
                "pg_dump", "-U", "postgres", "-d", database,
                "--clean", "--if-exists", "--no-owner"
            ]
            
            # Pipe through gzip for compression
            with gzip.open(backup_path, "wt") as f:
                result = subprocess.run(
                    dump_cmd,
                    capture_output=True,
                    text=True
                )
                
                if result.returncode != 0:
                    logger.error(f"Database backup failed: {result.stderr}")
                    return None
                
                f.write(result.stdout)
            
            size = backup_path.stat().st_size
            
            info = BackupInfo(
                id=backup_id,
                type=BackupType.DATABASE,
                timestamp=datetime.now(),
                path=backup_path,
                size_bytes=size,
                services=["supabase-db"],
                compressed=True,
                metadata={"database": database}
            )
            
            # Save metadata
            self._save_backup_metadata(info)
            
            logger.info(f"Database backup completed: {backup_path} ({info._human_size(size)})")
            return info
            
        except Exception as e:
            logger.error(f"Database backup error: {e}")
            if backup_path.exists():
                backup_path.unlink()
            return None
    
    def backup_volumes(self, volumes: Optional[List[str]] = None) -> Optional[BackupInfo]:
        """
        Create a backup of Docker volumes.
        
        Args:
            volumes: List of volume names to backup. If None, backs up all stack volumes.
        """
        if volumes is None:
            # Get all volumes from docker compose
            result = subprocess.run(
                ["docker", "volume", "ls", "--format", "{{.Name}}"],
                capture_output=True,
                text=True
            )
            if result.returncode == 0:
                all_volumes = result.stdout.strip().split("\n")
                # Filter to our stack volumes
                volumes = [v for v in all_volumes if v.startswith(self.config.project_name)]
        
        if not volumes:
            logger.warning("No volumes to backup")
            return None
        
        backup_id = self._generate_backup_id(BackupType.VOLUMES)
        backup_path = self.backup_dir / f"{backup_id}.tar.gz"
        
        try:
            logger.info(f"Starting volume backup: {len(volumes)} volumes")
            
            with tarfile.open(backup_path, "w:gz") as tar:
                for volume in volumes:
                    logger.info(f"Backing up volume: {volume}")
                    
                    # Create a temporary container to access the volume
                    temp_path = f"/tmp/backup_{volume}"
                    
                    # Use a busybox container to read the volume data
                    result = subprocess.run([
                        "docker", "run", "--rm",
                        "-v", f"{volume}:/volume:ro",
                        "-v", f"{self.backup_dir}:/backup",
                        "busybox",
                        "tar", "cvf", f"/backup/temp_{volume}.tar", "-C", "/volume", "."
                    ], capture_output=True)
                    
                    if result.returncode == 0:
                        temp_tar = self.backup_dir / f"temp_{volume}.tar"
                        if temp_tar.exists():
                            tar.add(temp_tar, arcname=f"{volume}.tar")
                            temp_tar.unlink()
            
            size = backup_path.stat().st_size
            
            info = BackupInfo(
                id=backup_id,
                type=BackupType.VOLUMES,
                timestamp=datetime.now(),
                path=backup_path,
                size_bytes=size,
                services=["volumes"],
                compressed=True,
                metadata={"volumes": volumes}
            )
            
            self._save_backup_metadata(info)
            
            logger.info(f"Volume backup completed: {backup_path} ({info._human_size(size)})")
            return info
            
        except Exception as e:
            logger.error(f"Volume backup error: {e}")
            if backup_path.exists():
                backup_path.unlink()
            return None
    
    def backup_config(self) -> Optional[BackupInfo]:
        """Create a backup of all configuration files."""
        backup_id = self._generate_backup_id(BackupType.CONFIG)
        backup_path = self.backup_dir / f"{backup_id}.tar.gz"
        
        try:
            logger.info("Starting configuration backup")
            
            config_files = [
                self.config.base_dir / "docker-compose.yml",
                self.config.base_dir / ".env",
                self.config.base_dir / "Caddyfile",
                self.config.base_dir / "supabase",
                self.config.base_dir / "searxng",
                self.config.config_dir,
            ]
            
            with tarfile.open(backup_path, "w:gz") as tar:
                for file_path in config_files:
                    if file_path.exists():
                        arcname = file_path.relative_to(self.config.base_dir)
                        tar.add(file_path, arcname=str(arcname))
            
            size = backup_path.stat().st_size
            
            info = BackupInfo(
                id=backup_id,
                type=BackupType.CONFIG,
                timestamp=datetime.now(),
                path=backup_path,
                size_bytes=size,
                services=["config"],
                compressed=True
            )
            
            self._save_backup_metadata(info)
            
            logger.info(f"Config backup completed: {backup_path} ({info._human_size(size)})")
            return info
            
        except Exception as e:
            logger.error(f"Config backup error: {e}")
            if backup_path.exists():
                backup_path.unlink()
            return None
    
    def backup_full(self) -> Optional[BackupInfo]:
        """Create a full backup of the entire stack."""
        backup_id = self._generate_backup_id(BackupType.FULL)
        backup_path = self.backup_dir / f"{backup_id}.tar.gz"
        
        try:
            logger.info("Starting full stack backup")
            
            # Create individual backups first
            db_backup = self.backup_database()
            vol_backup = self.backup_volumes()
            cfg_backup = self.backup_config()
            
            # Combine into single archive
            with tarfile.open(backup_path, "w:gz") as tar:
                for backup in [db_backup, vol_backup, cfg_backup]:
                    if backup and backup.path.exists():
                        tar.add(backup.path, arcname=backup.path.name)
            
            # Clean up individual backups
            for backup in [db_backup, vol_backup, cfg_backup]:
                if backup and backup.path.exists():
                    backup.path.unlink()
                    meta_path = backup.path.with_suffix(".json")
                    if meta_path.exists():
                        meta_path.unlink()
            
            size = backup_path.stat().st_size
            
            info = BackupInfo(
                id=backup_id,
                type=BackupType.FULL,
                timestamp=datetime.now(),
                path=backup_path,
                size_bytes=size,
                services=list(self.config.get_enabled_services().keys()),
                compressed=True,
                metadata={
                    "included_backups": ["database", "volumes", "config"]
                }
            )
            
            self._save_backup_metadata(info)
            
            logger.info(f"Full backup completed: {backup_path} ({info._human_size(size)})")
            return info
            
        except Exception as e:
            logger.error(f"Full backup error: {e}")
            if backup_path.exists():
                backup_path.unlink()
            return None
    
    def restore_database(self, backup_path: Path, database: str = "postgres") -> bool:
        """
        Restore a database from backup.
        
        WARNING: This will overwrite the existing database!
        """
        if not backup_path.exists():
            logger.error(f"Backup file not found: {backup_path}")
            return False
        
        try:
            logger.info(f"Restoring database from: {backup_path}")
            
            # Decompress if needed
            if str(backup_path).endswith(".gz"):
                with gzip.open(backup_path, "rt") as f:
                    sql_content = f.read()
            else:
                with open(backup_path) as f:
                    sql_content = f.read()
            
            # Write to temp file
            temp_file = Path("/tmp/restore.sql")
            with open(temp_file, "w") as f:
                f.write(sql_content)
            
            # Copy to container
            subprocess.run([
                "docker", "cp", str(temp_file), "supabase-db:/tmp/restore.sql"
            ], check=True)
            
            # Execute restore
            result = subprocess.run([
                "docker", "exec", "supabase-db",
                "psql", "-U", "postgres", "-d", database, "-f", "/tmp/restore.sql"
            ], capture_output=True, text=True)
            
            if result.returncode != 0:
                logger.error(f"Database restore failed: {result.stderr}")
                return False
            
            # Cleanup
            temp_file.unlink()
            subprocess.run([
                "docker", "exec", "supabase-db", "rm", "/tmp/restore.sql"
            ])
            
            logger.info("Database restore completed successfully")
            return True
            
        except Exception as e:
            logger.error(f"Database restore error: {e}")
            return False
    
    def restore_volumes(self, backup_path: Path) -> bool:
        """Restore volumes from backup."""
        if not backup_path.exists():
            logger.error(f"Backup file not found: {backup_path}")
            return False
        
        try:
            logger.info(f"Restoring volumes from: {backup_path}")
            
            # Extract to temp directory
            temp_dir = Path("/tmp/volume_restore")
            temp_dir.mkdir(exist_ok=True)
            
            with tarfile.open(backup_path, "r:gz") as tar:
                tar.extractall(temp_dir)
            
            # Restore each volume
            for vol_tar in temp_dir.glob("*.tar"):
                volume_name = vol_tar.stem
                logger.info(f"Restoring volume: {volume_name}")
                
                # Use busybox to restore
                subprocess.run([
                    "docker", "run", "--rm",
                    "-v", f"{volume_name}:/volume",
                    "-v", f"{temp_dir}:/backup:ro",
                    "busybox",
                    "tar", "xvf", f"/backup/{vol_tar.name}", "-C", "/volume"
                ], check=True)
            
            # Cleanup
            shutil.rmtree(temp_dir)
            
            logger.info("Volume restore completed successfully")
            return True
            
        except Exception as e:
            logger.error(f"Volume restore error: {e}")
            return False
    
    def restore_config(self, backup_path: Path) -> bool:
        """Restore configuration files from backup."""
        if not backup_path.exists():
            logger.error(f"Backup file not found: {backup_path}")
            return False
        
        try:
            logger.info(f"Restoring config from: {backup_path}")
            
            # Extract directly to base directory
            with tarfile.open(backup_path, "r:gz") as tar:
                tar.extractall(self.config.base_dir)
            
            logger.info("Config restore completed successfully")
            return True
            
        except Exception as e:
            logger.error(f"Config restore error: {e}")
            return False
    
    def list_backups(self, backup_type: Optional[BackupType] = None) -> List[BackupInfo]:
        """List all available backups."""
        backups = []
        
        for meta_file in self.backup_dir.glob("*.json"):
            try:
                with open(meta_file) as f:
                    data = json.load(f)
                
                info = BackupInfo(
                    id=data["id"],
                    type=BackupType(data["type"]),
                    timestamp=datetime.fromisoformat(data["timestamp"]),
                    path=Path(data["path"]),
                    size_bytes=data["size_bytes"],
                    services=data["services"],
                    compressed=data.get("compressed", True),
                    encrypted=data.get("encrypted", False),
                    metadata=data.get("metadata", {})
                )
                
                if backup_type is None or info.type == backup_type:
                    if info.path.exists():
                        backups.append(info)
                        
            except (json.JSONDecodeError, KeyError) as e:
                logger.warning(f"Invalid backup metadata: {meta_file}: {e}")
        
        # Sort by timestamp, newest first
        backups.sort(key=lambda b: b.timestamp, reverse=True)
        return backups
    
    def delete_backup(self, backup_id: str) -> bool:
        """Delete a specific backup."""
        for backup in self.list_backups():
            if backup.id == backup_id:
                try:
                    if backup.path.exists():
                        backup.path.unlink()
                    
                    meta_path = self.backup_dir / f"{backup_id}.json"
                    if meta_path.exists():
                        meta_path.unlink()
                    
                    logger.info(f"Deleted backup: {backup_id}")
                    return True
                except Exception as e:
                    logger.error(f"Failed to delete backup: {e}")
                    return False
        
        logger.warning(f"Backup not found: {backup_id}")
        return False
    
    def cleanup_old_backups(self):
        """Remove backups older than retention period."""
        cutoff = datetime.now() - timedelta(days=self.schedule.retention_days)
        
        for backup_type in BackupType:
            backups = self.list_backups(backup_type)
            
            # Keep minimum count
            if len(backups) <= self.schedule.retention_count:
                continue
            
            # Delete old backups beyond minimum count
            for backup in backups[self.schedule.retention_count:]:
                if backup.timestamp < cutoff:
                    self.delete_backup(backup.id)
    
    def _save_backup_metadata(self, info: BackupInfo):
        """Save backup metadata to JSON file."""
        meta_path = self.backup_dir / f"{info.id}.json"
        with open(meta_path, "w") as f:
            json.dump(info.to_dict(), f, indent=2)
    
    def start_scheduled_backups(self):
        """Start the scheduled backup thread."""
        if self._scheduler_running:
            logger.warning("Backup scheduler is already running")
            return
        
        self._scheduler_running = True
        self._scheduler_thread = threading.Thread(
            target=self._scheduler_loop,
            daemon=True
        )
        self._scheduler_thread.start()
        logger.info("Backup scheduler started")
    
    def stop_scheduled_backups(self):
        """Stop the scheduled backup thread."""
        self._scheduler_running = False
        if self._scheduler_thread:
            self._scheduler_thread.join(timeout=10)
        logger.info("Backup scheduler stopped")
    
    def _scheduler_loop(self):
        """Main scheduler loop."""
        last_full_backup = datetime.now() - timedelta(hours=self.schedule.full_backup_interval_hours)
        last_db_backup = datetime.now() - timedelta(hours=self.schedule.database_backup_interval_hours)
        
        while self._scheduler_running:
            now = datetime.now()
            
            # Check for full backup
            if (now - last_full_backup).total_seconds() >= self.schedule.full_backup_interval_hours * 3600:
                logger.info("Running scheduled full backup")
                self.backup_full()
                last_full_backup = now
            
            # Check for database backup
            elif (now - last_db_backup).total_seconds() >= self.schedule.database_backup_interval_hours * 3600:
                logger.info("Running scheduled database backup")
                self.backup_database()
                last_db_backup = now
            
            # Cleanup old backups daily
            self.cleanup_old_backups()
            
            # Sleep for 1 hour
            time.sleep(3600)
    
    def get_backup_stats(self) -> Dict[str, Any]:
        """Get backup statistics."""
        all_backups = self.list_backups()
        
        total_size = sum(b.size_bytes for b in all_backups)
        
        by_type = {}
        for backup_type in BackupType:
            type_backups = [b for b in all_backups if b.type == backup_type]
            by_type[backup_type.value] = {
                "count": len(type_backups),
                "total_size_bytes": sum(b.size_bytes for b in type_backups),
                "latest": type_backups[0].timestamp.isoformat() if type_backups else None
            }
        
        return {
            "total_backups": len(all_backups),
            "total_size_bytes": total_size,
            "total_size_human": BackupInfo._human_size(total_size),
            "by_type": by_type,
            "retention_days": self.schedule.retention_days,
            "retention_count": self.schedule.retention_count
        }
