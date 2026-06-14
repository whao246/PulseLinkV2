from app.infrastructure.db.base import Base


def test_new_schema_contains_evidence_units():
    assert "evidence_units" in Base.metadata.tables


def test_new_schema_contains_page_artifacts():
    assert "page_artifacts" in Base.metadata.tables


def test_evidence_units_have_source_ref_column():
    table = Base.metadata.tables["evidence_units"]

    assert "source_ref" in table.columns


def test_analysis_tasks_have_model_profile_column():
    table = Base.metadata.tables["analysis_tasks"]

    assert "model_profile" in table.columns


def test_task_steps_have_worker_retry_and_progress_columns():
    table = Base.metadata.tables["task_steps"]

    for column_name in (
        "locked_until",
        "attempt_count",
        "max_attempts",
        "progress_payload",
        "error_code",
    ):
        assert column_name in table.columns


def test_evidence_units_have_domain_alignment_columns():
    table = Base.metadata.tables["evidence_units"]

    for column_name in (
        "category",
        "content",
        "structured_data",
        "confidence_score",
    ):
        assert column_name in table.columns


def test_new_schema_contains_expected_unique_constraints():
    expected_constraints = {
        "files": {"uq_files_user_sha256"},
        "analysis_tasks": {"uq_tasks_user_idempotency"},
        "task_steps": {"uq_task_steps_task_step"},
        "document_pages": {"uq_document_pages_task_page"},
        "evidence_units": {"uq_evidence_units_source"},
        "fact_cards": {"uq_fact_cards_task_dimension"},
        "judgment_cards": {"uq_judgment_cards_task_dimension"},
        "score_results": {"uq_score_results_task"},
        "reports": {"uq_reports_task"},
    }

    for table_name, constraint_names in expected_constraints.items():
        table = Base.metadata.tables[table_name]
        actual_names = {constraint.name for constraint in table.constraints}

        assert constraint_names <= actual_names
