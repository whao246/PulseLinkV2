import importlib.util
import re
from pathlib import Path

from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import create_engine, inspect


MIGRATION_FILE = (
    Path(__file__).resolve().parents[1]
    / "migrations"
    / "versions"
    / "0001_initial_schema.py"
)


def test_initial_schema_migration_exists():
    assert MIGRATION_FILE.exists()


def test_initial_schema_migration_does_not_import_base_metadata():
    migration_text = MIGRATION_FILE.read_text()

    assert "Base.metadata" not in migration_text
    assert "app.infrastructure.db.base" not in migration_text


def test_initial_schema_migration_creates_key_tables_explicitly():
    migration_text = MIGRATION_FILE.read_text()

    for table_name in (
        "users",
        "files",
        "analysis_tasks",
        "task_steps",
        "document_pages",
        "page_artifacts",
        "evidence_units",
        "fact_cards",
        "judgment_cards",
        "score_results",
        "reports",
    ):
        assert re.search(rf'op\.create_table\(\s*"{table_name}"', migration_text)


def test_initial_schema_migration_upgrades_sqlite_schema():
    spec = importlib.util.spec_from_file_location("initial_schema_migration", MIGRATION_FILE)
    migration = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(migration)

    engine = create_engine("sqlite:///:memory:")
    with engine.begin() as connection:
        context = MigrationContext.configure(connection)
        migration.op = Operations(context)
        migration.upgrade()

    inspector = inspect(engine)

    for table_name in (
        "analysis_tasks",
        "task_steps",
        "evidence_units",
    ):
        assert table_name in inspector.get_table_names()

    columns_by_table = {
        table_name: {column["name"] for column in inspector.get_columns(table_name)}
        for table_name in ("analysis_tasks", "task_steps", "evidence_units")
    }

    assert {"model_profile"} <= columns_by_table["analysis_tasks"]
    assert {
        "locked_until",
        "attempt_count",
        "max_attempts",
        "progress_payload",
        "error_code",
    } <= columns_by_table["task_steps"]
    assert {
        "category",
        "content",
        "structured_data",
        "confidence_score",
        "source_type",
        "source_ref",
        "page_number",
    } <= columns_by_table["evidence_units"]
