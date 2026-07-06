from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def test_production_compose_uses_non_reload_api_and_worker_commands():
    compose = (ROOT / "docker-compose.prod.yml").read_text()

    assert "uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers" in compose
    assert "python -m app.workers.main" in compose
    assert "--reload" not in compose
    assert "./backend:/app/backend" not in compose


def test_alembic_runtime_config_exists():
    assert (ROOT / "backend" / "alembic.ini").exists()
    assert (ROOT / "backend" / "migrations" / "env.py").exists()


def test_production_requirements_include_alembic():
    requirements = (ROOT / "backend" / "requirements.txt").read_text()

    assert "alembic" in requirements
