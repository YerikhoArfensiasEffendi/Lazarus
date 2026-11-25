"""FastAPI service for Lazarus — The Underground Office."""

from __future__ import annotations

import asyncio
import base64
from dataclasses import asdict
from pathlib import Path

from fastapi import FastAPI, File, Form, Query, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from lazarus import __version__
from lazarus.brain import LazarusBrain
from lazarus.constitution import LazarusConstitution
from lazarus.memory import KnowledgeStore
from lazarus.skills import SkillArsenal
from lazarus.voice import LazarusTTS, LocalWhisperSTT


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


class BrainChatRequest(BaseModel):
    user_id: str = Field(default="creator", min_length=1, max_length=120)
    username: str = Field(default="Creator", max_length=120)
    message: str = Field(min_length=1)
    voice_mode: bool = Field(default=False)


class TTSRequest(BaseModel):
    text: str = Field(min_length=1, max_length=2000)


def create_app(
    db_path: str | Path | None = None,
    repo_root: str | Path | None = None,
    brain: LazarusBrain | None = None,
    stt: LocalWhisperSTT | None = None,
    tts: LazarusTTS | None = None,
) -> FastAPI:
    store = KnowledgeStore(db_path=db_path)
    arsenal = SkillArsenal(repo_root=repo_root)
    brain_engine = brain or LazarusBrain(store=store, arsenal=arsenal)
    stt_engine = stt or LocalWhisperSTT()
    tts_engine = tts or LazarusTTS()

    app = FastAPI(
        title="Lazarus — The Underground Office API",
        version=__version__,
        description=(
            "Loyal, honest, adaptive AI assistant core supporting continuous learning, "
            "transparent reporting, adaptation logs, curated top-rated GitHub agentic skills, "
            "live agentic library inspection, local Discord voice + DM assistant, and non-harm "
            "safety guardrails."
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

    @app.post("/brain/chat")
    async def brain_chat(payload: BrainChatRequest) -> dict[str, object]:
        response = await brain_engine.respond(
            user_id=payload.user_id,
            message=payload.message,
            username=payload.username,
            voice_mode=payload.voice_mode,
        )
        return response.to_dict()

    @app.get("/voice/status")
    async def voice_status() -> dict[str, object]:
        llm_health = await brain_engine.check_llm_health()
        return {
            "stt": {
                "engine": f"faster-whisper:{stt_engine.model_size}",
                "device": stt_engine.device,
                "language": stt_engine.language or "auto",
            },
            "tts": tts_engine.status(),
            "llm": llm_health,
            "skills_available": len(arsenal.list_installed()),
        }

    @app.post("/voice/tts")
    async def synthesize_tts(payload: TTSRequest) -> dict[str, object]:
        synth = await tts_engine.synthesize(payload.text)
        return {
            "engine": synth.engine,
            "voice": synth.voice,
            "mime_type": synth.mime_type,
            "duration_ms": synth.duration_ms,
            "audio_base64": base64.b64encode(synth.audio_bytes).decode("ascii"),
        }

    @app.post("/voice/turn")
    async def voice_turn(
        audio: UploadFile = File(...),  # noqa: B008
        user_id: str = Form(default="creator"),
        username: str = Form(default="Creator"),
    ) -> dict[str, object]:
        raw_bytes = await audio.read()
        suffix = Path(audio.filename or "speech.wav").suffix or ".wav"
        stt_res = await asyncio.to_thread(stt_engine.transcribe_bytes, raw_bytes, suffix)

        if not stt_res.text:
            return {
                "transcript": "",
                "language": stt_res.language,
                "spoken_reply": "",
                "audio_base64": "",
                "audio_mime": "audio/mpeg",
                "should_send_dm": False,
                "dm_title": "",
                "dm_content": "",
                "dm_attachment": None,
                "matched_skills": [],
                "timings_ms": {"stt": stt_res.duration_ms, "brain": 0, "tts": 0},
            }

        brain_res = await brain_engine.respond(
            user_id=user_id,
            message=stt_res.text,
            username=username,
            voice_mode=True,
        )

        audio_b64 = ""
        audio_mime = "audio/mpeg"
        tts_ms = 0
        tts_error: str | None = None
        try:
            synth = await tts_engine.synthesize(brain_res.spoken_reply)
            audio_b64 = base64.b64encode(synth.audio_bytes).decode("ascii")
            audio_mime = synth.mime_type
            tts_ms = synth.duration_ms
        except Exception as exc:  # noqa: BLE001
            tts_error = str(exc)

        return {
            "transcript": stt_res.text,
            "language": stt_res.language,
            "spoken_reply": brain_res.spoken_reply,
            "audio_base64": audio_b64,
            "audio_mime": audio_mime,
            "tts_error": tts_error,
            "should_send_dm": brain_res.should_send_dm,
            "dm_title": brain_res.dm_title,
            "dm_content": brain_res.dm_content,
            "dm_attachment": asdict(brain_res.dm_attachment) if brain_res.dm_attachment else None,
            "matched_skills": brain_res.matched_skills,
            "provider": brain_res.provider,
            "model": brain_res.model,
            "timings_ms": {
                "stt": stt_res.duration_ms,
                "brain": brain_res.latency_ms,
                "tts": tts_ms,
            },
        }

    return app


app = create_app()
