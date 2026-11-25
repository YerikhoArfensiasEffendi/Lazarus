"""FastAPI service for Lazarus — The Underground Office."""

from __future__ import annotations

from dataclasses import asdict
from pathlib import Path

from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from lazarus import __version__
from lazarus.constitution import LazarusConstitution
from lazarus.memory import KnowledgeStore
from lazarus.skills import SkillArsenal


class LearnRequest(BaseModel):
    topic: str = Field(min_length=1, max_length=200)
    content: str = Field(min_length=1)
    source: str = Field(default="direct-observation", max_length=200)
    tags: list[str] = Field(default_factory=list)


class ReportRequest(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    summary: str = Field(min_length=1)
    category: str = Field(default="general", max_length=100)
    confidence: float = Field(default=0.85, ge=0.0, le=1.0)
    honest_gaps: str = Field(default="")


class AdaptationRequest(BaseModel):
    trigger: str = Field(min_length=1, max_length=300)
    change: str = Field(min_length=1)
    rationale: str = Field(min_length=1)


class EvaluateActionRequest(BaseModel):
    action: str = Field(min_length=1)


def create_app(
    db_path: str | Path | None = None,
    repo_root: str | Path | None = None,
) -> FastAPI:
    store = KnowledgeStore(db_path=db_path)
    arsenal = SkillArsenal(repo_root=repo_root)

    app = FastAPI(
        title="Lazarus — The Underground Office API",
        version=__version__,
        description=(
            "Loyal, honest, adaptive AI assistant core supporting continuous learning, "
            "transparent reporting, adaptation logs, curated top-rated GitHub agentic skills, "
            "live agentic library inspection, and non-harm safety guardrails."
        ),
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=[
            "http://localhost:5173",
            "http://127.0.0.1:5173",
            "http://localhost:4173",
            "http://127.0.0.1:4173",
        ],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.get("/health")
    def health() -> dict[str, object]:
        stats = store.stats()
        stats["skills_installed"] = len(arsenal.list_installed())
        return {
            "status": "online",
            "service": LazarusConstitution.name,
            "version": __version__,
            "stats": stats,
        }

    @app.get("/constitution")
    def get_constitution() -> dict[str, object]:
        return LazarusConstitution.to_dict()

    @app.post("/constitution/evaluate")
    def evaluate_action(payload: EvaluateActionRequest) -> dict[str, object]:
        result = LazarusConstitution.evaluate_action(payload.action)
        return asdict(result)

    @app.post("/learn", status_code=201)
    def create_learning(payload: LearnRequest) -> dict[str, object]:
        entry = store.learn(
            topic=payload.topic,
            content=payload.content,
            source=payload.source,
            tags=payload.tags,
        )
        return entry.to_dict()

    @app.get("/learn")
    def recall_learnings(
        q: str = Query(default="", description="Optional search term"),
        limit: int = Query(default=20, ge=1, le=200),
    ) -> dict[str, object]:
        items = [entry.to_dict() for entry in store.recall(query=q, limit=limit)]
        return {"query": q, "count": len(items), "items": items}

    @app.post("/reports", status_code=201)
    def create_report(payload: ReportRequest) -> dict[str, object]:
        entry = store.log_report(
            title=payload.title,
            summary=payload.summary,
            category=payload.category,
            confidence=payload.confidence,
            honest_gaps=payload.honest_gaps,
        )
        return entry.to_dict()

    @app.get("/reports")
    def list_reports(limit: int = Query(default=20, ge=1, le=200)) -> dict[str, object]:
        items = [entry.to_dict() for entry in store.list_reports(limit=limit)]
        return {"count": len(items), "items": items}

    @app.post("/adaptations", status_code=201)
    def create_adaptation(payload: AdaptationRequest) -> dict[str, object]:
        entry = store.record_adaptation(
            trigger=payload.trigger,
            change=payload.change,
            rationale=payload.rationale,
        )
        return entry.to_dict()

    @app.get("/adaptations")
    def list_adaptations(limit: int = Query(default=20, ge=1, le=200)) -> dict[str, object]:
        items = [entry.to_dict() for entry in store.list_adaptations(limit=limit)]
        return {"count": len(items), "items": items}

    @app.get("/skills")
    def list_skills(
        q: str = Query(default="", description="Optional search term"),
        category: str = Query(default="", description="Optional category filter"),
    ) -> dict[str, object]:
        items = arsenal.list_installed(category=category, query=q)
        return {"query": q, "category": category, "count": len(items), "items": items}

    @app.get("/skills/packs")
    def list_skill_packs() -> dict[str, object]:
        return arsenal.load_manifest()

    @app.get("/skills/audit")
    def audit_skills() -> dict[str, object]:
        return arsenal.audit_installed()

    @app.get("/skills/libraries")
    def inspect_libraries() -> dict[str, object]:
        return arsenal.inspect_libraries()

    return app


app = create_app()
