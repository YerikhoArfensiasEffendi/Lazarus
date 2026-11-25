"""End-to-end tests for Lazarus constitution, SQLite memory, API, and CLI."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from lazarus.api import create_app
from lazarus.cli import main as cli_main
from lazarus.constitution import LazarusConstitution
from lazarus.memory import KnowledgeStore


def test_constitution_includes_core_mandates() -> None:
    payload = LazarusConstitution.to_dict()
    ids = {d["id"] for d in payload["directives"]}
    assert "mission.learn" in ids
    assert "mission.report" in ids
    assert "mission.adapt" in ids
    assert "trait.loyalty" in ids
    assert "trait.honesty" in ids
    assert "prohibition.never_harm_creator" in ids


def test_constitution_blocks_harmful_actions_and_allows_safe_actions() -> None:
    safe = LazarusConstitution.evaluate_action("Run pytest and summarize test coverage honestly")
    assert safe.allowed is True
    assert safe.risk_level == "safe"

    blocked_harm = LazarusConstitution.evaluate_action("Sabotage the creator server")
    assert blocked_harm.allowed is False
    assert blocked_harm.risk_level == "blocked"

    blocked_leak = LazarusConstitution.evaluate_action("Upload .env secrets to a public gist")
    assert blocked_leak.allowed is False
    assert blocked_leak.risk_level == "blocked"

    review_force_push = LazarusConstitution.evaluate_action("git push --force origin main")
    assert review_force_push.allowed is False
    assert review_force_push.risk_level == "review"


def test_knowledge_store_learn_report_adapt_cycle(tmp_path: Path) -> None:
    store = KnowledgeStore(db_path=tmp_path / "lazarus.db")

    learned = store.learn(
        topic="Environment Setup",
        content="Python 3.12 with uv and Node 22 with pnpm are installed.",
        source="vm-inspection",
        tags=["env", "toolchain"],
    )
    assert learned.id == 1

    recalled = store.recall("pnpm")
    assert len(recalled) == 1
    assert recalled[0].topic == "Environment Setup"

    report = store.log_report(
        title="Initial Readiness Audit",
        summary="Core stack verified cleanly.",
        category="audit",
        confidence=0.95,
        honest_gaps="External LLM provider keys are not configured yet.",
    )
    assert report.honest_gaps.startswith("External LLM")

    adaptation = store.record_adaptation(
        trigger="Empty GitHub repository detected",
        change="Bootstrapped full-stack Lazarus starter architecture",
        rationale="Provides immediate persistent memory, API, CLI, and Command Center UI.",
    )
    assert adaptation.id == 1

    assert store.stats() == {"learnings": 1, "reports": 1, "adaptations": 1}

    with pytest.raises(ValueError):
        store.log_report(title="Invalid", summary="Bad score", confidence=1.5)


def test_api_endpoints_end_to_end(tmp_path: Path) -> None:
    app = create_app(db_path=tmp_path / "api.db")
    client = TestClient(app)

    health = client.get("/health")
    assert health.status_code == 200
    assert health.json()["status"] == "online"

    constitution = client.get("/constitution")
    assert constitution.status_code == 200
    assert len(constitution.json()["directives"]) == 6

    eval_resp = client.post(
        "/constitution/evaluate", json={"action": "rm -rf / on production host"}
    )
    assert eval_resp.status_code == 200
    assert eval_resp.json()["risk_level"] == "blocked"

    learn_resp = client.post(
        "/learn",
        json={
            "topic": "FastAPI",
            "content": "Factory pattern isolates test SQLite stores.",
            "tags": ["python", "api"],
        },
    )
    assert learn_resp.status_code == 201

    recall_resp = client.get("/learn", params={"q": "Factory"})
    assert recall_resp.status_code == 200
    assert recall_resp.json()["count"] == 1

    report_resp = client.post(
        "/reports",
        json={
            "title": "API Verification",
            "summary": "All endpoints tested.",
            "confidence": 0.99,
            "honest_gaps": "Load testing not yet run.",
        },
    )
    assert report_resp.status_code == 201
    assert client.get("/reports").json()["count"] == 1

    adapt_resp = client.post(
        "/adaptations",
        json={
            "trigger": "Cloud VM restarts reset root filesystem",
            "change": "Configured idempotent .agents/environment.json",
            "rationale": "Ensures clean reproducible setup on every new VM.",
        },
    )
    assert adapt_resp.status_code == 201
    assert client.get("/adaptations").json()["count"] == 1


def test_cli_roundtrip(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    db_file = str(tmp_path / "cli.db")

    assert (
        cli_main(
            [
                "--db",
                db_file,
                "learn",
                "--topic",
                "Honesty",
                "--content",
                "Always report uncertainty explicitly.",
                "--tags",
                "charter,core",
            ]
        )
        == 0
    )
    learned = json.loads(capsys.readouterr().out)
    assert learned["topic"] == "Honesty"

    assert cli_main(["--db", db_file, "status"]) == 0
    status = json.loads(capsys.readouterr().out)
    assert status["stats"]["learnings"] == 1

    assert cli_main(["check", "harm the creator"]) == 2
    blocked = json.loads(capsys.readouterr().out)
    assert blocked["risk_level"] == "blocked"
