"""Tests for the SQLite decision history store."""

import pytest

import app.history as history
from app.schemas import CouncilResult


@pytest.fixture(autouse=True)
def isolated_database(monkeypatch, tmp_path):
    monkeypatch.setattr(history, "DATABASE_PATH", tmp_path / "nested" / "history.db")


def _result(request_id: str | None, question: str = "Should we?") -> CouncilResult:
    return CouncilResult(
        question=question, decision_charter="c", round1=[], round2=[], final_answer="a", request_id=request_id
    )


def test_save_and_list_decisions_newest_first():
    history.save_decision(_result("first", "Q1"))
    history.save_decision(_result("second", "Q2"))

    records = history.list_decisions(10)
    assert [record.id for record in records] == ["second", "first"]
    assert records[0].result["final_answer"] == "a"


def test_list_respects_limit():
    for index in range(5):
        history.save_decision(_result(f"id{index}"))
    assert len(history.list_decisions(2)) == 2


def test_decision_without_request_id_is_skipped():
    history.save_decision(_result(None))
    assert history.list_decisions(10) == []


def test_get_decision():
    history.save_decision(_result("abc"))
    assert history.get_decision("abc").question == "Should we?"
    assert history.get_decision("missing") is None


def test_save_feedback_updates_existing_decision():
    history.save_decision(_result("abc"))
    assert history.save_feedback("abc", 5, "  Went well  ") is True

    record = history.get_decision("abc")
    assert record.rating == 5
    assert record.outcome_note == "Went well"


def test_save_feedback_for_unknown_decision_returns_false():
    assert history.save_feedback("missing", 3, None) is False


def test_check_database_reports_healthy_store():
    assert history.check_database() is True
