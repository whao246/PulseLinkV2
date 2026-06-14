import re
from pathlib import Path


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
