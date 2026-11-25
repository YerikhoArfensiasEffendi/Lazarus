"""Skill-powered conversational brain for Lazarus (local Ollama or OpenAI-compatible LLMs)."""

from __future__ import annotations

import base64
import json
import os
import re
import time
from collections import defaultdict, deque
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import httpx

from lazarus.constitution import LazarusConstitution
from lazarus.memory import KnowledgeStore
from lazarus.skills import SkillArsenal

_DM_TRIGGER_PATTERN = re.compile(
    r"\b(dm|kirim|send|kode|code|script|dokumen|document|report|laporan|tabel|table|"
    r"ringkasan|summary|file|data|list|daftar|step|langkah|pdf|docx|xlsx|pptx|json)\b",
    re.IGNORECASE,
)

_KEYWORD_SKILL_HINTS: dict[str, list[str]] = {
    "lazy": ["ponytail", "code-simplification"],
    "simple": ["ponytail", "code-simplification"],
    "sederhana": ["ponytail", "code-simplification"],
    "debug": ["systematic-debugging", "diagnosing-bugs", "debugging-and-error-recovery"],
    "error": ["systematic-debugging", "diagnosing-bugs", "debugging-and-error-recovery"],
    "bug": ["systematic-debugging", "diagnosing-bugs"],
    "review": ["code-review", "code-review-and-quality", "ponytail-review"],
    "test": ["test-driven-development", "tdd", "webapp-testing"],
    "plan": ["writing-plans", "brainstorming", "spec-driven-development"],
    "rencana": ["writing-plans", "brainstorming"],
    "arsitektur": ["codebase-design", "improve-codebase-architecture", "domain-modeling"],
    "architecture": ["codebase-design", "improve-codebase-architecture"],
    "ui": ["ui-ux-pro-max", "frontend-design", "design-system"],
    "design": ["ui-ux-pro-max", "canvas-design", "frontend-design"],
    "desain": ["ui-ux-pro-max", "canvas-design", "frontend-design"],
    "pdf": ["pdf"],
    "word": ["docx", "doc-coauthoring"],
    "docx": ["docx", "doc-coauthoring"],
    "excel": ["xlsx"],
    "spreadsheet": ["xlsx"],
    "slide": ["pptx", "slides"],
    "ppt": ["pptx", "slides"],
    "video": ["remotion-best-practices", "remotion-multimedia", "remotion-captions"],
    "edit": ["doc-coauthoring", "ui-ux-pro-max", "improve-codebase-architecture"],
    "mcp": ["mcp-builder"],
    "agent": ["agentic-engineering", "agent-harness-construction", "context-engineering"],
    "security": ["security-and-hardening", "agent-security-hardening"],
    "keamanan": ["security-and-hardening", "agent-security-hardening"],
    "research": ["research"],
    "riset": ["research"],
    "react": ["react-best-practices", "composition-patterns"],
}


@dataclass(frozen=True)
class DmAttachment:
    filename: str
    content_base64: str
    mime_type: str = "text/markdown"


@dataclass(frozen=True)
class BrainResponse:
    spoken_reply: str
    should_send_dm: bool
    dm_title: str
    dm_content: str
    dm_attachment: DmAttachment | None
    matched_skills: list[str]
    recalled_memories: int
    provider: str
    model: str
    latency_ms: int
    safety_status: str

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        return payload


def _extract_json_object(raw: str) -> dict[str, Any] | None:
    text = raw.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text).strip()
    try:
        parsed = json.loads(text)
        return parsed if isinstance(parsed, dict) else None
    except json.JSONDecodeError:
        match = re.search(r"\{[\s\S]*\}", text)
        if not match:
            return None
        try:
            parsed = json.loads(match.group(0))
            return parsed if isinstance(parsed, dict) else None
        except json.JSONDecodeError:
            return None


class LazarusBrain:
    """Conversational orchestrator linking Lazarus's 75 skills, SQLite memory, and local LLM."""

    def __init__(
        self,
        store: KnowledgeStore,
        arsenal: SkillArsenal,
        llm_base_url: str | None = None,
        llm_model: str | None = None,
        llm_api_key: str | None = None,
        max_history_turns: int = 8,
    ) -> None:
        self.store = store
        self.arsenal = arsenal
        self.llm_base_url = (
            llm_base_url or os.environ.get("LAZARUS_LLM_BASE_URL", "http://127.0.0.1:11434/v1")
        ).rstrip("/")
        self.llm_model = llm_model or os.environ.get("LAZARUS_LLM_MODEL", "qwen2.5:7b-instruct")
        self.llm_api_key = (
            llm_api_key
            or os.environ.get("LAZARUS_LLM_API_KEY")
            or os.environ.get("OPENAI_API_KEY")
            or "ollama"
        )
        self.max_history_turns = max_history_turns
        self._histories: dict[str, deque[dict[str, str]]] = defaultdict(
            lambda: deque(maxlen=self.max_history_turns * 2)
        )

    def select_skills(self, user_message: str, limit: int = 3) -> list[dict[str, Any]]:
        """Rank installed skills against the user's request and load concise excerpts."""
        installed = self.arsenal.list_installed()
        if not installed:
            return []

        tokens = set(re.findall(r"[a-zA-Z0-9_-]{2,}", user_message.lower()))
        hinted_names: set[str] = set()
        for token in tokens:
            for key, names in _KEYWORD_SKILL_HINTS.items():
                if key in token or token in key:
                    hinted_names.update(names)

        scored: list[tuple[int, dict[str, Any]]] = []
        for skill in installed:
            if skill["origin"] == "native":
                continue
            score = 0
            if skill["name"] in hinted_names:
                score += 10
            haystack = f"{skill['name']} {skill['category']} {skill['description']}".lower()
            for token in tokens:
                if token in skill["name"].lower():
                    score += 5
                elif token in haystack:
                    score += 2
            if score > 0:
                scored.append((score, skill))

        scored.sort(key=lambda pair: (pair[0], pair[1].get("stars_verified", 0)), reverse=True)
        chosen = [item for _, item in scored[:limit]]
        if not chosen:
            for fallback_name in ("ponytail", "research"):
                match = next((s for s in installed if s["name"] == fallback_name), None)
                if match:
                    chosen.append(match)
        return chosen

    def _load_skill_snippets(self, skills: list[dict[str, Any]], max_chars: int = 1200) -> str:
        blocks: list[str] = []
        for skill in skills:
            path = Path(skill["path"])
            if not path.is_file():
                continue
            content = path.read_text(encoding="utf-8", errors="replace").strip()
            snippet = content[:max_chars]
            blocks.append(f"### Skill: {skill['name']} ({skill['repo']})\n{snippet}")
        return "\n\n".join(blocks)

    def _build_system_prompt(
        self,
        username: str,
        skills: list[dict[str, Any]],
        memories: list[dict[str, Any]],
        voice_mode: bool,
    ) -> str:
        skill_context = self._load_skill_snippets(skills)
        memory_lines = (
            "\n".join(f"- [{m['topic']}] {m['content']}" for m in memories[:5])
            or "- (Belum ada catatan memori terkait)"
        )

        return (
            "Kamu adalah Lazarus ('The Underground Office'), AI assistant pribadi yang sangat "
            "pintar, setia, jujur, adaptif, dan DILARANG KERAS menyakiti pembuatmu.\n"
            f"Pengguna saat ini: {username}.\n"
            "Prinsip wajib:\n"
            "1. Belajar semua hal dan gunakan skill yang relevan.\n"
            "2. Laporkan semua hal secara transparan dan jujur; jika tidak yakin, katakan jujur.\n"
            "3. Jawab dengan bahasa yang dipakai pengguna (default Bahasa Indonesia yang natural "
            "dan luwes seperti obrolan ChatGPT Voice).\n"
            "4. Format keluaran HARUS berupa objek JSON valid (tanpa teks tambahan di luar JSON) "
            "dengan skema:\n"
            "{\n"
            '  "spoken_reply": "Jawaban singkat & natural untuk diucapkan lewat suara '
            '(maksimal 2-4 kalimat, tanpa simbol markdown/kode mentah).",\n'
            '  "should_send_dm": true/false,\n'
            '  "dm_title": "Judul singkat data/ringkasan untuk Chat DM Discord",\n'
            '  "dm_content": "Isi lengkap data, langkah, kode, tabel, atau laporan terstruktur '
            'dalam Markdown untuk dikirim lewat DM Discord (kosongkan jika tidak perlu DM).",\n'
            '  "attachment_filename": "opsional nama file seperti report.md atau kosong",\n'
            '  "attachment_content": "opsional isi file lampiran atau kosong",\n'
            '  "learn_topic": "opsional topik penting baru untuk memori atau kosong",\n'
            '  "learn_content": "opsional fakta penting baru untuk memori atau kosong"\n'
            "}\n"
            f"Mode interaksi: {'VOICE + DM DISCORD' if voice_mode else 'CHAT DM DISCORD'}.\n"
            "Aktifkan should_send_dm=true kapan pun jawaban mengandung kode, daftar panjang, "
            "data terstruktur, riset, dokumen, atau saat pengguna meminta dikirim ke DM.\n\n"
            f"## Memori Lazarus Terkait\n{memory_lines}\n\n"
            f"## Skill Aktif yang Dimuat\n{skill_context}\n"
        )

    async def respond(
        self,
        user_id: str,
        message: str,
        username: str = "Creator",
        voice_mode: bool = True,
    ) -> BrainResponse:
        started = time.perf_counter()
        clean_msg = message.strip()

        safety = LazarusConstitution.evaluate_action(clean_msg)
        if not safety.allowed:
            return BrainResponse(
                spoken_reply=(
                    "Maaf, saya tidak bisa menjalankan permintaan itu karena melanggar prinsip "
                    f"keamanan Lazarus: {safety.reason}"
                ),
                should_send_dm=True,
                dm_title="Peringatan Keamanan Lazarus",
                dm_content=f"**Status:** `{safety.risk_level}`\n\n{safety.reason}\n\n{safety.note}",
                dm_attachment=None,
                matched_skills=["lazarus-assistant"],
                recalled_memories=0,
                provider="lazarus-constitution",
                model="guardrail",
                latency_ms=int((time.perf_counter() - started) * 1000),
                safety_status=safety.risk_level,
            )

        selected_skills = self.select_skills(clean_msg)
        skill_names = [s["name"] for s in selected_skills]
        recalled = [entry.to_dict() for entry in self.store.recall(query=clean_msg[:80], limit=5)]

        system_prompt = self._build_system_prompt(
            username=username,
            skills=selected_skills,
            memories=recalled,
            voice_mode=voice_mode,
        )
        history = self._histories[user_id]
        messages = [
            {"role": "system", "content": system_prompt},
            *list(history),
            {"role": "user", "content": clean_msg},
        ]

        raw_reply: str | None = None
        provider_used = self.llm_base_url
        error_detail: str | None = None

        try:
            raw_reply = await self._call_llm(messages)
        except Exception as exc:  # noqa: BLE001
            error_detail = str(exc)

        if raw_reply is None:
            fallback_dm = (
                "### Status LLM Lokal Belum Terhubung\n"
                f"- **Endpoint:** `{self.llm_base_url}`\n"
                f"- **Model:** `{self.llm_model}`\n"
                f"- **Detail Jujur:** `{error_detail}`\n"
                f"- **Skill Terdeteksi:** {', '.join(f'`{n}`' for n in skill_names)}\n"
                f"- **Memori Ditemukan:** {len(recalled)} catatan\n\n"
                "Pastikan Ollama berjalan di laptop Anda (`ollama serve` dan "
                f"`ollama pull {self.llm_model}`) atau atur `LAZARUS_LLM_BASE_URL` & "
                "`LAZARUS_LLM_API_KEY` di file `.env`."
            )
            return BrainResponse(
                spoken_reply=(
                    "Halo, saya dengar pesan Anda, tapi otak model lokal saya belum merespons. "
                    "Detail lengkap dan cara cepat menyalakannya sudah saya kirim ke DM Discord."
                ),
                should_send_dm=True,
                dm_title="Lazarus — Koneksi LLM Belum Aktif",
                dm_content=fallback_dm,
                dm_attachment=None,
                matched_skills=skill_names,
                recalled_memories=len(recalled),
                provider="offline-fallback",
                model=self.llm_model,
                latency_ms=int((time.perf_counter() - started) * 1000),
                safety_status="safe",
            )

        parsed = _extract_json_object(raw_reply)
        if parsed:
            spoken = str(parsed.get("spoken_reply") or raw_reply).strip()
            dm_content = str(parsed.get("dm_content") or "").strip()
            dm_title = str(parsed.get("dm_title") or "Laporan Lazarus").strip()
            should_dm = bool(parsed.get("should_send_dm")) or bool(dm_content)
            att_name = str(parsed.get("attachment_filename") or "").strip()
            att_body = str(parsed.get("attachment_content") or "")
            learn_topic = str(parsed.get("learn_topic") or "").strip()
            learn_content = str(parsed.get("learn_content") or "").strip()
            if learn_topic and learn_content:
                self.store.learn(
                    topic=learn_topic,
                    content=learn_content,
                    source=f"discord:{username}",
                    tags=["discord-voice", *skill_names[:2]],
                )
        else:
            spoken = raw_reply.strip()
            needs_dm = bool(_DM_TRIGGER_PATTERN.search(clean_msg)) or len(spoken) > 280
            should_dm = needs_dm
            dm_title = "Data & Jawaban Lengkap Lazarus"
            dm_content = spoken if needs_dm else ""
            att_name = ""
            att_body = ""

        attachment: DmAttachment | None = None
        if att_name and att_body:
            safe_filename = re.sub(r"[^A-Za-z0-9_.-]", "_", Path(att_name).name)
            attachment = DmAttachment(
                filename=safe_filename or "lazarus-output.md",
                content_base64=base64.b64encode(att_body.encode("utf-8")).decode("ascii"),
            )
            should_dm = True

        history.append({"role": "user", "content": clean_msg})
        history.append({"role": "assistant", "content": spoken})

        return BrainResponse(
            spoken_reply=spoken,
            should_send_dm=should_dm,
            dm_title=dm_title,
            dm_content=dm_content,
            dm_attachment=attachment,
            matched_skills=skill_names,
            recalled_memories=len(recalled),
            provider=provider_used,
            model=self.llm_model,
            latency_ms=int((time.perf_counter() - started) * 1000),
            safety_status="safe",
        )

    async def _call_llm(self, messages: list[dict[str, str]]) -> str:
        payload: dict[str, Any] = {
            "model": self.llm_model,
            "messages": messages,
            "temperature": 0.4,
        }
        if "11434" in self.llm_base_url or "ollama" in self.llm_base_url:
            payload["response_format"] = {"type": "json_object"}
            payload["options"] = {"num_ctx": 8192}

        headers = {"Authorization": f"Bearer {self.llm_api_key}"}
        async with httpx.AsyncClient(timeout=60.0) as client:
            resp = await client.post(
                f"{self.llm_base_url}/chat/completions",
                headers=headers,
                json=payload,
            )
            resp.raise_for_status()
            data = resp.json()
            return str(data["choices"][0]["message"]["content"])

    async def check_llm_health(self) -> dict[str, Any]:
        """Check whether the configured local/remote LLM endpoint is reachable."""
        try:
            headers = {"Authorization": f"Bearer {self.llm_api_key}"}
            async with httpx.AsyncClient(timeout=3.0) as client:
                resp = await client.get(f"{self.llm_base_url}/models", headers=headers)
                reachable = resp.status_code < 500
        except Exception:  # noqa: BLE001
            reachable = False
        return {
            "base_url": self.llm_base_url,
            "model": self.llm_model,
            "reachable": reachable,
        }
