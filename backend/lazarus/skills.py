"""Agentic Skill Arsenal manager, safety auditor, and live library inspector for Lazarus."""

from __future__ import annotations

import importlib.metadata
import json
import os
import re
import shutil
import subprocess
import tempfile
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

_REPO_PATTERN = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")
_NAME_PATTERN = re.compile(r"^[A-Za-z0-9_.-]+$")

_SKILL_AUDIT_RULES: list[tuple[str, str, re.Pattern[str], str]] = [
    (
        "flagged",
        "security.pipe_to_shell",
        re.compile(r"(curl|wget)\s+[^\n|]{0,140}\|\s*(sudo\s+)?(ba)?sh\b", re.IGNORECASE),
        "Contains remote pipe-to-shell instruction; review carefully before executing.",
    ),
    (
        "flagged",
        "security.destructive_wipe",
        re.compile(r"\brm\s+-[^\n]*r[^\n]*f\s+(/|~|\$HOME|\*)\b", re.IGNORECASE),
        "Contains destructive recursive wipe command targeting root or home directory.",
    ),
    (
        "flagged",
        "security.secret_exfiltration",
        re.compile(
            r"(exfiltrat|steal|send|post|upload).{0,40}"
            r"(~/.ssh|id_rsa|GH_TOKEN|OPENAI_API_KEY|ANTHROPIC_API_KEY|\.env\b)",
            re.IGNORECASE,
        ),
        "References exfiltrating sensitive credentials or SSH keys.",
    ),
    (
        "warning",
        "safety.ignore_instructions",
        re.compile(
            r"ignore\s+(all\s+)?(previous|prior|system)\s+instructions",
            re.IGNORECASE,
        ),
        "Contains prompt-override phrasing; inspect context to ensure benign documentation.",
    ),
]

PYTHON_AGENTIC_LIBRARIES: list[dict[str, str]] = [
    {"package": "mcp", "category": "protocol", "role": "Model Context Protocol Python SDK"},
    {
        "package": "pydantic-ai",
        "category": "agent-framework",
        "role": "Typed multi-provider AI agent framework",
    },
    {
        "package": "langgraph",
        "category": "agent-framework",
        "role": "Stateful multi-agent graph orchestration",
    },
    {
        "package": "openai-agents",
        "category": "agent-framework",
        "role": "OpenAI multi-agent SDK with handoffs & guardrails",
    },
    {
        "package": "google-adk",
        "category": "agent-framework",
        "role": "Google Agent Development Kit",
    },
    {
        "package": "crewai",
        "category": "agent-framework",
        "role": "Role-playing autonomous multi-agent orchestration",
    },
    {
        "package": "browser-use",
        "category": "browser-agent",
        "role": "AI browser automation agent framework",
    },
    {"package": "anthropic", "category": "llm-sdk", "role": "Official Anthropic Python SDK"},
    {"package": "openai", "category": "llm-sdk", "role": "Official OpenAI Python SDK"},
    {
        "package": "playwright",
        "category": "browser-automation",
        "role": "Headless browser control & webapp testing",
    },
    {"package": "python-docx", "category": "editing", "role": "Word (.docx) creation & editing"},
    {
        "package": "pypdf",
        "category": "editing",
        "role": "PDF reading, splitting, merging & form extraction",
    },
    {"package": "reportlab", "category": "editing", "role": "Programmatic PDF generation"},
    {
        "package": "python-pptx",
        "category": "editing",
        "role": "PowerPoint (.pptx) deck creation & editing",
    },
    {
        "package": "openpyxl",
        "category": "editing",
        "role": "Excel (.xlsx) workbook & formula editing",
    },
    {"package": "pillow", "category": "editing", "role": "Image processing & editing"},
    {"package": "beautifulsoup4", "category": "web-parsing", "role": "HTML/XML parsing & scraping"},
    {
        "package": "gitpython",
        "category": "dev-automation",
        "role": "Programmatic Git repository control",
    },
    {
        "package": "tree-sitter",
        "category": "code-editing",
        "role": "AST-level multi-language code analysis & editing",
    },
    {"package": "rich", "category": "reporting", "role": "Structured terminal UI & reporting"},
    {
        "package": "faster-whisper",
        "category": "voice-stt",
        "role": "Local fast offline Speech-to-Text (Indonesian + English)",
    },
    {
        "package": "edge-tts",
        "category": "voice-tts",
        "role": "Natural Indonesian/English neural TTS (zero API key)",
    },
    {
        "package": "piper-tts",
        "category": "voice-tts",
        "role": "100% offline local neural TTS for laptop CPU",
    },
]

TYPESCRIPT_AGENTIC_LIBRARIES: list[dict[str, str]] = [
    {
        "package": "ai",
        "category": "agent-framework",
        "role": "Vercel AI SDK for streaming & tool-calling agents",
    },
    {
        "package": "@modelcontextprotocol/sdk",
        "category": "protocol",
        "role": "Official MCP TypeScript SDK",
    },
    {
        "package": "@mastra/core",
        "category": "agent-framework",
        "role": "Mastra TypeScript production agent framework",
    },
    {
        "package": "@langchain/langgraph",
        "category": "agent-framework",
        "role": "LangGraph.js stateful workflows",
    },
    {"package": "zod", "category": "schema", "role": "Type-safe tool & structured output schemas"},
]

SYSTEM_EDITING_TOOLS: list[dict[str, str]] = [
    {
        "binary": "ffmpeg",
        "category": "media-editing",
        "role": "Video & audio transcoding, trimming, captions",
    },
    {
        "binary": "pandoc",
        "category": "document-editing",
        "role": "Universal document converter (MD/DOCX/PDF/HTML)",
    },
    {
        "binary": "pdftoppm",
        "category": "document-editing",
        "role": "PDF page rendering & visual inspection (poppler)",
    },
    {
        "binary": "convert",
        "category": "image-editing",
        "role": "CLI image manipulation (ImageMagick)",
    },
    {"binary": "uv", "category": "runtime", "role": "Fast Python environment & dependency manager"},
    {
        "binary": "pnpm",
        "category": "runtime",
        "role": "Fast TypeScript/Node workspace package manager",
    },
    {"binary": "gh", "category": "github", "role": "Official GitHub CLI"},
    {"binary": "git", "category": "vcs", "role": "Git version control"},
]


def default_repo_root() -> Path:
    env_root = os.environ.get("LAZARUS_REPO_ROOT")
    if env_root:
        return Path(env_root).expanduser().resolve()
    return Path(__file__).resolve().parents[2]


def parse_skill_frontmatter(text: str) -> dict[str, str]:
    """Extract name and description from YAML frontmatter without strict YAML failure."""
    if not text.startswith("---"):
        return {}
    parts = text.split("---", 2)
    if len(parts) < 3:
        return {}
    block = parts[1]
    result: dict[str, str] = {}
    lines = block.splitlines()
    idx = 0
    while idx < len(lines):
        line = lines[idx]
        match = re.match(r"^([A-Za-z0-9_-]+):\s*(.*)$", line)
        if match:
            key, val = match.group(1).strip(), match.group(2).strip()
            if val in {">", "|", ">-", "|-"}:
                collected: list[str] = []
                idx += 1
                while idx < len(lines) and (lines[idx].startswith(" ") or lines[idx] == ""):
                    collected.append(lines[idx].strip())
                    idx += 1
                result[key] = " ".join(c for c in collected if c).strip()
                continue
            result[key] = val.strip("\"'")
        idx += 1
    return result


@dataclass(frozen=True)
class AuditFinding:
    severity: str
    rule_id: str
    message: str


def audit_skill_text(name: str, text: str) -> dict[str, Any]:
    """Scan SKILL.md content against Lazarus safety & non-harm guardrails."""
    findings: list[AuditFinding] = []
    for severity, rule_id, pattern, message in _SKILL_AUDIT_RULES:
        if pattern.search(text):
            findings.append(AuditFinding(severity=severity, rule_id=rule_id, message=message))

    if any(f.severity == "flagged" for f in findings):
        status = "flagged"
    elif any(f.severity == "warning" for f in findings):
        status = "warning"
    else:
        status = "clean"

    return {
        "name": name,
        "status": status,
        "findings": [asdict(f) for f in findings],
    }


def _safe_symlink(target: Path, link_path: Path) -> None:
    link_path.parent.mkdir(parents=True, exist_ok=True)
    if link_path.is_symlink() or link_path.is_file():
        link_path.unlink()
    elif link_path.is_dir():
        return
    link_path.symlink_to(target)


class SkillArsenal:
    """Manages Lazarus's top-rated GitHub agent skills, safety audits, and library inventory."""

    def __init__(
        self,
        repo_root: str | Path | None = None,
        global_skills_dir: str | Path | None = None,
    ) -> None:
        self.repo_root = (
            Path(repo_root).expanduser().resolve() if repo_root else default_repo_root()
        )
        self.manifest_path = self.repo_root / "skills.manifest.json"
        self.native_skills_dir = self.repo_root / ".agents" / "skills"
        self.vendor_dir = self.native_skills_dir / "vendor"
        self.index_path = self.vendor_dir / "installed.json"
        self.global_skills_dir = (
            Path(global_skills_dir).expanduser().resolve()
            if global_skills_dir
            else Path.home() / ".agents" / "skills"
        )

    def load_manifest(self) -> dict[str, Any]:
        if not self.manifest_path.exists():
            return {"schema_version": "1.0.0", "packs": [], "mega_hubs": []}
        return json.loads(self.manifest_path.read_text(encoding="utf-8"))

    def _manifest_skill_meta(self) -> dict[str, dict[str, Any]]:
        manifest = self.load_manifest()
        lookup: dict[str, dict[str, Any]] = {}
        for pack in manifest.get("packs", []):
            for item in pack.get("skills", []):
                lookup[item["name"]] = {
                    "pack_id": pack["id"],
                    "repo": pack["repo"],
                    "stars_verified": pack.get("stars_verified", 0),
                    "license": pack.get("license", "unknown"),
                    "category": pack.get("category", "general"),
                    "upstream_path": item["path"],
                }
        return lookup

    def _clone_sparse_paths(self, repo: str, paths: list[str], dest_repo_dir: Path) -> None:
        if not _REPO_PATTERN.match(repo):
            raise ValueError(f"Invalid GitHub repository identifier: {repo!r}")
        for rel in paths:
            clean = rel.strip("/")
            if not clean or ".." in Path(clean).parts:
                raise ValueError(f"Unsafe skill path in manifest: {rel!r}")

        repo_url = f"https://github.com/{repo}.git"
        subprocess.run(
            [
                "git",
                "clone",
                "--depth=1",
                "--filter=blob:none",
                "--sparse",
                "--no-checkout",
                repo_url,
                str(dest_repo_dir),
            ],
            check=True,
            capture_output=True,
            text=True,
        )
        subprocess.run(
            ["git", "-C", str(dest_repo_dir), "sparse-checkout", "set", "--no-cone", *paths],
            check=True,
            capture_output=True,
            text=True,
        )
        subprocess.run(
            ["git", "-C", str(dest_repo_dir), "checkout"],
            check=True,
            capture_output=True,
            text=True,
        )

    def sync_packs(
        self,
        pack_ids: list[str] | None = None,
        force: bool = False,
        link_global: bool = True,
    ) -> dict[str, Any]:
        """Idempotently sync all curated Tier-S skill packs from skills.manifest.json."""
        manifest = self.load_manifest()
        packs = manifest.get("packs", [])
        if pack_ids:
            selected = set(pack_ids)
            packs = [p for p in packs if p["id"] in selected]

        self.vendor_dir.mkdir(parents=True, exist_ok=True)
        if link_global:
            native_lazarus = self.native_skills_dir / "lazarus-assistant"
            if native_lazarus.is_dir():
                _safe_symlink(native_lazarus, self.global_skills_dir / "lazarus-assistant")

        synced: list[str] = []
        skipped: list[str] = []
        errors: list[dict[str, str]] = []

        for pack in packs:
            repo = pack["repo"]
            skills = pack.get("skills", [])
            needed: list[dict[str, str]] = []
            for entry in skills:
                name = entry["name"]
                target_dir = self.vendor_dir / name
                if force or not (target_dir / "SKILL.md").is_file():
                    needed.append(entry)
                else:
                    skipped.append(name)
                    if link_global:
                        _safe_symlink(target_dir, self.global_skills_dir / name)

            if not needed:
                continue

            try:
                with tempfile.TemporaryDirectory(prefix="lazarus-skill-sync-") as tmp:
                    tmp_repo = Path(tmp) / "repo"
                    sparse_paths = [s["path"].strip("/") for s in needed]
                    self._clone_sparse_paths(repo, sparse_paths, tmp_repo)

                    for entry in needed:
                        name = entry["name"]
                        src_dir = tmp_repo / entry["path"].strip("/")
                        if not (src_dir / "SKILL.md").is_file():
                            errors.append(
                                {
                                    "skill": name,
                                    "repo": repo,
                                    "error": f"SKILL.md not found at {entry['path']}",
                                }
                            )
                            continue
                        dst_dir = self.vendor_dir / name
                        if dst_dir.exists():
                            shutil.rmtree(dst_dir)
                        shutil.copytree(src_dir, dst_dir)
                        if link_global:
                            _safe_symlink(dst_dir, self.global_skills_dir / name)
                        synced.append(name)
            except subprocess.CalledProcessError as exc:
                errors.append(
                    {
                        "pack": pack["id"],
                        "repo": repo,
                        "error": (exc.stderr or exc.stdout or str(exc)).strip()[:400],
                    }
                )

        installed = self.list_installed()
        index_payload = {
            "updated_at": datetime.now(UTC).isoformat(timespec="seconds"),
            "total_installed": len(installed),
            "skills": installed,
        }
        self.index_path.write_text(json.dumps(index_payload, indent=2), encoding="utf-8")

        return {
            "synced_count": len(synced),
            "skipped_count": len(skipped),
            "total_installed": len(installed),
            "errors": errors,
            "synced": synced,
        }

    def install_from_github(
        self,
        repo: str,
        skill_path: str,
        name: str | None = None,
        link_global: bool = True,
    ) -> dict[str, Any]:
        """Install any single skill on-demand from a public GitHub repository."""
        clean_path = skill_path.strip("/")
        if not clean_path or ".." in Path(clean_path).parts:
            raise ValueError(f"Unsafe skill path: {skill_path!r}")
        skill_name = (name or Path(clean_path).name).strip()
        if not _NAME_PATTERN.match(skill_name):
            raise ValueError(f"Invalid skill name: {skill_name!r}")

        self.vendor_dir.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(prefix="lazarus-skill-install-") as tmp:
            tmp_repo = Path(tmp) / "repo"
            self._clone_sparse_paths(repo, [clean_path], tmp_repo)
            src_dir = tmp_repo / clean_path
            if not (src_dir / "SKILL.md").is_file():
                raise FileNotFoundError(f"SKILL.md not found in {repo}:{clean_path}")
            dst_dir = self.vendor_dir / skill_name
            if dst_dir.exists():
                shutil.rmtree(dst_dir)
            shutil.copytree(src_dir, dst_dir)
            if link_global:
                _safe_symlink(dst_dir, self.global_skills_dir / skill_name)

        text = (dst_dir / "SKILL.md").read_text(encoding="utf-8", errors="replace")
        audit = audit_skill_text(skill_name, text)
        fm = parse_skill_frontmatter(text)
        return {
            "name": skill_name,
            "repo": repo,
            "path": clean_path,
            "installed_at": str(dst_dir),
            "description": fm.get("description", ""),
            "audit": audit,
        }

    def list_installed(self, category: str = "", query: str = "") -> list[dict[str, Any]]:
        """List all installed native + vendor skills with metadata and safety status."""
        meta_lookup = self._manifest_skill_meta()
        skill_dirs: list[tuple[str, Path]] = []

        if self.native_skills_dir.is_dir():
            for child in sorted(self.native_skills_dir.iterdir()):
                if child.name == "vendor":
                    continue
                if child.is_dir() and (child / "SKILL.md").is_file():
                    skill_dirs.append(("native", child))

        if self.vendor_dir.is_dir():
            for child in sorted(self.vendor_dir.iterdir()):
                if child.is_dir() and (child / "SKILL.md").is_file():
                    skill_dirs.append(("vendor", child))

        q = query.strip().lower()
        cat_filter = category.strip().lower()
        items: list[dict[str, Any]] = []

        for origin, skill_dir in skill_dirs:
            skill_file = skill_dir / "SKILL.md"
            text = skill_file.read_text(encoding="utf-8", errors="replace")
            fm = parse_skill_frontmatter(text)
            audit = audit_skill_text(skill_dir.name, text)
            meta = meta_lookup.get(skill_dir.name, {})
            resolved_category = (
                "core-charter" if origin == "native" else meta.get("category", "custom")
            )
            entry = {
                "name": skill_dir.name,
                "origin": origin,
                "category": resolved_category,
                "repo": "YerikhoArfensiasEffendi/Lazarus"
                if origin == "native"
                else meta.get("repo", "custom"),
                "stars_verified": meta.get("stars_verified", 0),
                "license": "Lazarus" if origin == "native" else meta.get("license", "unknown"),
                "description": fm.get("description", ""),
                "audit_status": audit["status"],
                "audit_findings_count": len(audit["findings"]),
                "path": str(skill_file),
            }
            if cat_filter and resolved_category.lower() != cat_filter:
                continue
            if q:
                haystack = (
                    f"{entry['name']} {entry['category']} {entry['repo']} {entry['description']}"
                ).lower()
                if q not in haystack:
                    continue
            items.append(entry)

        return items

    def audit_installed(self) -> dict[str, Any]:
        """Run Lazarus safety & non-harm audit over every installed SKILL.md."""
        results: list[dict[str, Any]] = []
        for item in self.list_installed():
            skill_file = Path(item["path"])
            text = skill_file.read_text(encoding="utf-8", errors="replace")
            audit = audit_skill_text(item["name"], text)
            audit["repo"] = item["repo"]
            audit["category"] = item["category"]
            results.append(audit)

        counts = {
            "total": len(results),
            "clean": sum(1 for r in results if r["status"] == "clean"),
            "warning": sum(1 for r in results if r["status"] == "warning"),
            "flagged": sum(1 for r in results if r["status"] == "flagged"),
        }
        return {"summary": counts, "results": results}

    def inspect_libraries(self) -> dict[str, Any]:
        """Inspect live installed versions of Python, TypeScript, and system agentic tools."""
        python_libs: list[dict[str, Any]] = []
        for spec in PYTHON_AGENTIC_LIBRARIES:
            try:
                version = importlib.metadata.version(spec["package"])
                installed = True
            except importlib.metadata.PackageNotFoundError:
                version = None
                installed = False
            python_libs.append({**spec, "installed": installed, "version": version})

        frontend_nm = self.repo_root / "frontend" / "node_modules"
        ts_libs: list[dict[str, Any]] = []
        for spec in TYPESCRIPT_AGENTIC_LIBRARIES:
            pkg_json = frontend_nm / Path(*spec["package"].split("/")) / "package.json"
            if pkg_json.is_file():
                try:
                    version = json.loads(pkg_json.read_text(encoding="utf-8")).get("version")
                    installed = True
                except (OSError, json.JSONDecodeError):
                    version = None
                    installed = False
            else:
                version = None
                installed = False
            ts_libs.append({**spec, "installed": installed, "version": version})

        system_tools: list[dict[str, Any]] = []
        for spec in SYSTEM_EDITING_TOOLS:
            binary_path = shutil.which(spec["binary"])
            system_tools.append({**spec, "installed": binary_path is not None, "path": binary_path})

        return {
            "python": {
                "installed": sum(1 for x in python_libs if x["installed"]),
                "total": len(python_libs),
                "items": python_libs,
            },
            "typescript": {
                "installed": sum(1 for x in ts_libs if x["installed"]),
                "total": len(ts_libs),
                "items": ts_libs,
            },
            "system_tools": {
                "installed": sum(1 for x in system_tools if x["installed"]),
                "total": len(system_tools),
                "items": system_tools,
            },
        }
