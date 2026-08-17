from __future__ import annotations

import sqlite3
from pathlib import Path


class ProductWorkspaceStore:
    """One SQLite database; every query requires a workspace boundary."""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._migrate()

    def connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        return connection

    def _migrate(self) -> None:
        with self.connect() as db:
            db.executescript("""
            CREATE TABLE IF NOT EXISTS product_schema_migrations (version INTEGER PRIMARY KEY);
            INSERT OR IGNORE INTO product_schema_migrations(version) VALUES (1);
            CREATE TABLE IF NOT EXISTS product_projects (
              project_id TEXT PRIMARY KEY, workspace_id TEXT NOT NULL, title TEXT NOT NULL,
              root_ref TEXT NOT NULL, root_display_name TEXT NOT NULL,
              status TEXT NOT NULL, pinned INTEGER NOT NULL DEFAULT 0,
              manual_order INTEGER NOT NULL DEFAULT 0, created_at_utc TEXT NOT NULL,
              updated_at_utc TEXT NOT NULL, archived_at_utc TEXT, archive_reason TEXT);
            CREATE INDEX IF NOT EXISTS product_projects_workspace
              ON product_projects(workspace_id, updated_at_utc DESC);
            CREATE TABLE IF NOT EXISTS product_tasks (
              task_id TEXT PRIMARY KEY, workspace_id TEXT NOT NULL, project_id TEXT NOT NULL,
              title TEXT NOT NULL, status TEXT NOT NULL,
              priority INTEGER NOT NULL DEFAULT 0, pinned INTEGER NOT NULL DEFAULT 0,
              manual_order INTEGER NOT NULL DEFAULT 0, archived_at_utc TEXT, archive_reason TEXT,
              reasoning_effort TEXT NOT NULL DEFAULT 'medium',
              speed_profile TEXT NOT NULL DEFAULT 'standard',
              approval_profile TEXT NOT NULL DEFAULT 'risk_based', assistant_session_id TEXT,
              assistant_turn_id TEXT,
              team_job_id TEXT, created_at_utc TEXT NOT NULL, updated_at_utc TEXT NOT NULL,
              FOREIGN KEY(project_id) REFERENCES product_projects(project_id));
            CREATE INDEX IF NOT EXISTS product_tasks_scope
              ON product_tasks(workspace_id, project_id, updated_at_utc DESC);
            CREATE TABLE IF NOT EXISTS product_messages (
              message_id TEXT PRIMARY KEY, workspace_id TEXT NOT NULL, task_id TEXT NOT NULL,
              role TEXT NOT NULL, body TEXT NOT NULL, created_at_utc TEXT NOT NULL,
              FOREIGN KEY(task_id) REFERENCES product_tasks(task_id));
            CREATE TABLE IF NOT EXISTS product_links (
              link_id TEXT PRIMARY KEY, workspace_id TEXT NOT NULL, task_id TEXT NOT NULL,
              target_type TEXT NOT NULL, target_id TEXT NOT NULL, created_at_utc TEXT NOT NULL,
              UNIQUE(workspace_id, task_id, target_type, target_id));
            CREATE TABLE IF NOT EXISTS product_preferences (
              workspace_id TEXT NOT NULL, principal_id TEXT NOT NULL, preference_key TEXT NOT NULL,
              value_json TEXT NOT NULL, updated_at_utc TEXT NOT NULL,
              PRIMARY KEY(workspace_id, principal_id, preference_key));
            CREATE TABLE IF NOT EXISTS product_mutation_dedup (
              workspace_id TEXT NOT NULL, idempotency_key TEXT NOT NULL, method TEXT NOT NULL,
              payload_json TEXT NOT NULL, response_json TEXT NOT NULL, created_at_utc TEXT NOT NULL,
              PRIMARY KEY(workspace_id, idempotency_key));
            INSERT OR IGNORE INTO product_schema_migrations(version) VALUES (2);
            """)
            project_columns = {
                row["name"]
                for row in db.execute("PRAGMA table_info(product_projects)").fetchall()
            }
            additions = {
                "root_ref": "TEXT NOT NULL DEFAULT ''",
                "root_display_name": "TEXT NOT NULL DEFAULT ''",
                "pinned": "INTEGER NOT NULL DEFAULT 0",
                "manual_order": "INTEGER NOT NULL DEFAULT 0",
                "archived_at_utc": "TEXT",
                "archive_reason": "TEXT",
            }
            for name, definition in additions.items():
                if name not in project_columns:
                    db.execute(f"ALTER TABLE product_projects ADD COLUMN {name} {definition}")
            db.execute(
                """UPDATE product_projects
                SET root_ref='root-' || project_id
                WHERE root_ref IS NULL OR root_ref=''"""
            )
            db.execute(
                """UPDATE product_projects
                SET root_display_name=title
                WHERE root_display_name IS NULL OR root_display_name=''"""
            )
            db.execute(
                """CREATE INDEX IF NOT EXISTS product_projects_sidebar
                ON product_projects(workspace_id, status, pinned DESC, manual_order ASC,
                updated_at_utc DESC)"""
            )
            db.execute("INSERT OR IGNORE INTO product_schema_migrations(version) VALUES (3)")
            task_columns = {
                row["name"]
                for row in db.execute("PRAGMA table_info(product_tasks)").fetchall()
            }
            task_additions = {
                "reasoning_effort": "TEXT NOT NULL DEFAULT 'medium'",
                "speed_profile": "TEXT NOT NULL DEFAULT 'standard'",
                "approval_profile": "TEXT NOT NULL DEFAULT 'risk_based'",
            }
            for name, definition in task_additions.items():
                if name not in task_columns:
                    db.execute(f"ALTER TABLE product_tasks ADD COLUMN {name} {definition}")
            db.execute("INSERT OR IGNORE INTO product_schema_migrations(version) VALUES (4)")
            task_columns = {
                row["name"] for row in db.execute("PRAGMA table_info(product_tasks)").fetchall()
            }
            task_additions = {
                "priority": "INTEGER NOT NULL DEFAULT 0",
                "pinned": "INTEGER NOT NULL DEFAULT 0",
                "manual_order": "INTEGER NOT NULL DEFAULT 0",
                "archived_at_utc": "TEXT",
                "archive_reason": "TEXT",
            }
            for name, definition in task_additions.items():
                if name not in task_columns:
                    db.execute(f"ALTER TABLE product_tasks ADD COLUMN {name} {definition}")
            db.execute(
                """CREATE INDEX IF NOT EXISTS product_tasks_sidebar
                ON product_tasks(workspace_id, project_id, status, pinned DESC, manual_order ASC,
                updated_at_utc DESC)"""
            )
            db.execute("INSERT OR IGNORE INTO product_schema_migrations(version) VALUES (5)")
