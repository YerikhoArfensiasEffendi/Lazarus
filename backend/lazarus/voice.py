"""Local Speech-to-Text (faster-whisper) and Text-to-Speech (Edge / Piper / OpenAI) for Lazarus."""

from __future__ import annotations

import asyncio
import io
import os
import re
import shutil
import subprocess
import tempfile
import time
import wave
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx


def clean_text_for_speech(text: str, max_chars: int = 900) -> str:
    """Convert markdown/code-heavy text into clean, natural spoken prose."""
    cleaned = re.sub(r"```[\s\S]*?```", " detail lengkap sudah saya kirim ke DM Discord. ", text)
    cleaned = re.sub(r"`([^`]+)`", r"\1", cleaned)
    cleaned = re.sub(r"https?://\S+", "tautan di DM", cleaned)
    cleaned = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", cleaned)
    cleaned = re.sub(r"[*_~#>|]", " ", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    if len(cleaned) > max_chars:
        cutoff = cleaned[:max_chars].rsplit(".", 1)[0].strip()
        cleaned = (cutoff + ".") if cutoff else (cleaned[:max_chars].strip() + "...")
    return cleaned


@dataclass(frozen=True)
class TranscriptionResult:
    text: str
    language: str
    duration_ms: int
    engine: str


@dataclass(frozen=True)
class SynthesisResult:
    audio_bytes: bytes
    mime_type: str
    engine: str
    voice: str
    duration_ms: int


class LocalWhisperSTT:
    """Lazy-loaded local faster-whisper STT supporting Indonesian and English on laptop CPU/GPU."""

    def __init__(
        self,
        model_size: str | None = None,
        device: str | None = None,
        compute_type: str | None = None,
        language: str | None = None,
    ) -> None:
        self.model_size = model_size or os.environ.get("LAZARUS_WHISPER_MODEL", "small")
        self.device = device or os.environ.get("LAZARUS_WHISPER_DEVICE", "cpu")
        self.compute_type = compute_type or os.environ.get("LAZARUS_WHISPER_COMPUTE_TYPE", "int8")
        lang = language if language is not None else os.environ.get("LAZARUS_VOICE_LANGUAGE", "id")
        self.language = None if lang in {"", "auto"} else lang
        self._model: Any = None

    def _get_model(self) -> Any:
        if self._model is None:
            from faster_whisper import WhisperModel

            self._model = WhisperModel(
                self.model_size,
                device=self.device,
                compute_type=self.compute_type,
            )
        return self._model

    def transcribe_bytes(self, audio_bytes: bytes, suffix: str = ".wav") -> TranscriptionResult:
        started = time.perf_counter()
        if not audio_bytes:
            return TranscriptionResult(
                text="",
                language=self.language or "unknown",
                duration_ms=0,
                engine=f"faster-whisper:{self.model_size}",
            )

        with tempfile.NamedTemporaryFile(suffix=suffix, delete=True) as tmp:
            tmp.write(audio_bytes)
            tmp.flush()
            model = self._get_model()
            segments, info = model.transcribe(
                tmp.name,
                language=self.language,
                vad_filter=True,
                beam_size=1,
            )
            text = " ".join(seg.text.strip() for seg in segments if seg.text.strip()).strip()
            detected_lang = getattr(info, "language", self.language or "unknown")

        elapsed_ms = int((time.perf_counter() - started) * 1000)
        return TranscriptionResult(
            text=text,
            language=str(detected_lang),
            duration_ms=elapsed_ms,
            engine=f"faster-whisper:{self.model_size}",
        )


class LazarusTTS:
    """Multi-backend TTS supporting natural Edge Neural Voices, offline Piper, and OpenAI TTS."""

    def __init__(
        self,
        provider: str | None = None,
        voice: str | None = None,
        piper_model_path: str | None = None,
    ) -> None:
        self.provider = (provider or os.environ.get("LAZARUS_TTS_PROVIDER", "edge")).lower()
        self.voice = voice or os.environ.get("LAZARUS_TTS_VOICE", "id-ID-ArdiNeural")
        self.piper_model_path = piper_model_path or os.environ.get("LAZARUS_PIPER_MODEL_PATH", "")

    async def synthesize(self, text: str) -> SynthesisResult:
        started = time.perf_counter()
        spoken = clean_text_for_speech(text)
        if not spoken:
            return SynthesisResult(
                audio_bytes=b"",
                mime_type="audio/mpeg",
                engine=self.provider,
                voice=self.voice,
                duration_ms=0,
            )

        if self.provider == "piper":
            audio_bytes = await asyncio.to_thread(self._synthesize_piper, spoken)
            return SynthesisResult(
                audio_bytes=audio_bytes,
                mime_type="audio/wav",
                engine="piper-local",
                voice=Path(self.piper_model_path).name if self.piper_model_path else "piper",
                duration_ms=int((time.perf_counter() - started) * 1000),
            )

        if self.provider == "openai":
            audio_bytes = await self._synthesize_openai(spoken)
            return SynthesisResult(
                audio_bytes=audio_bytes,
                mime_type="audio/mpeg",
                engine="openai-tts",
                voice=os.environ.get("LAZARUS_OPENAI_TTS_VOICE", "alloy"),
                duration_ms=int((time.perf_counter() - started) * 1000),
            )

        audio_bytes = await self._synthesize_edge(spoken)
        return SynthesisResult(
            audio_bytes=audio_bytes,
            mime_type="audio/mpeg",
            engine="edge-tts",
            voice=self.voice,
            duration_ms=int((time.perf_counter() - started) * 1000),
        )

    async def _synthesize_edge(self, text: str) -> bytes:
        import edge_tts

        communicate = edge_tts.Communicate(text, voice=self.voice)
        buf = io.BytesIO()
        async for chunk in communicate.stream():
            if chunk.get("type") == "audio":
                buf.write(chunk["data"])
        return buf.getvalue()

    def _synthesize_piper(self, text: str) -> bytes:
        if not self.piper_model_path or not Path(self.piper_model_path).is_file():
            raise FileNotFoundError(
                "LAZARUS_PIPER_MODEL_PATH must point to a downloaded .onnx Piper voice model."
            )

        piper_bin = shutil.which("piper")
        if piper_bin:
            with tempfile.NamedTemporaryFile(suffix=".wav", delete=True) as tmp:
                subprocess.run(
                    [piper_bin, "--model", self.piper_model_path, "--output_file", tmp.name],
                    input=text.encode("utf-8"),
                    check=True,
                    capture_output=True,
                )
                return Path(tmp.name).read_bytes()

        from piper.voice import PiperVoice

        voice = PiperVoice.load(self.piper_model_path)
        buf = io.BytesIO()
        with wave.open(buf, "wb") as wav_file:
            voice.synthesize_wav(text, wav_file)
        return buf.getvalue()

    async def _synthesize_openai(self, text: str) -> bytes:
        api_key = os.environ.get("OPENAI_API_KEY") or os.environ.get("LAZARUS_LLM_API_KEY", "")
        if not api_key:
            raise ValueError("OPENAI_API_KEY is required when LAZARUS_TTS_PROVIDER=openai.")
        voice_name = os.environ.get("LAZARUS_OPENAI_TTS_VOICE", "alloy")
        model_name = os.environ.get("LAZARUS_OPENAI_TTS_MODEL", "tts-1")
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(
                "https://api.openai.com/v1/audio/speech",
                headers={"Authorization": f"Bearer {api_key}"},
                json={"model": model_name, "voice": voice_name, "input": text},
            )
            resp.raise_for_status()
            return resp.content

    def status(self) -> dict[str, Any]:
        return {
            "provider": self.provider,
            "voice": self.voice,
            "piper_model_ready": bool(
                self.piper_model_path and Path(self.piper_model_path).is_file()
            ),
        }
