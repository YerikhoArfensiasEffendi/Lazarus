# Lazarus — The Underground Office

> AI Agent Assistant workspace yang dirancang untuk **belajar semua hal**, **melaporkan semua hal secara jujur & transparan**, **beradaptasi dengan dunia baru**, setia kepada pembuatnya, dan **dilarang keras menyakiti pembuatnya**.

## Agentic Arsenal (Top-Rated GitHub Skills + Libraries)

Lazarus dilengkapi **75 skill aktif** (1 charter inti `lazarus-assistant` + **74 skill ber-rating tertinggi dari 9 repositori GitHub Tier-S**) plus akses on-demand ke **4.000+ skill** di mega-hub komunitas melalui [`skills.manifest.json`](skills.manifest.json) dan CLI `lazarus skills`:

| Pack / Sumber GitHub | Kategori | Lisensi | Skill Utama |
|---|---|---|---|
| `DietrichGebert/ponytail` | Lazy Senior Developer | MIT | `ponytail`, `ponytail-review`, `ponytail-audit`, `ponytail-debt`, `ponytail-gain` |
| `obra/superpowers` | Agentic Methodology | MIT | `brainstorming`, `writing-plans`, `test-driven-development`, `systematic-debugging`, `subagent-driven-development`, `verification-before-completion` |
| `mattpocock/skills` | Senior Engineering & Editing | MIT | `code-review`, `codebase-design`, `diagnosing-bugs`, `domain-modeling`, `improve-codebase-architecture`, `research`, `writing-for-agents` |
| `addyosmani/agent-skills` | Production Engineering | MIT | `code-simplification`, `context-engineering`, `security-and-hardening`, `performance-optimization`, `spec-driven-development` |
| `anthropics/skills` | Document, Media & MCP Editing | Apache-2.0 | `docx`, `pdf`, `pptx`, `xlsx`, `doc-coauthoring`, `canvas-design`, `frontend-design`, `mcp-builder`, `webapp-testing`, `skill-creator` |
| `affaan-m/ECC` | Agent Harness & Autonomy | MIT | `agentic-engineering`, `agent-harness-construction`, `agent-eval`, `autonomous-loops`, `browser-qa` |
| `nextlevelbuilder/ui-ux-pro-max-skill` | UI/UX & Visual Editing | MIT | `ui-ux-pro-max`, `design-system`, `ui-styling`, `banner-design`, `slides`, `brand` |
| `vercel-labs/agent-skills` | React & Web Editing | MIT | `react-best-practices`, `composition-patterns`, `web-design-guidelines`, `writing-guidelines` |
| `remotion-dev/skills` | Video & Multimedia Editing | Official | `remotion-best-practices`, `remotion-create`, `remotion-multimedia`, `remotion-captions`, `remotion-render` |
| **On-Demand Mega-Hubs** | 4,000+ Community Skills | MIT / Community | `sickn33/agentic-awesome-skills`, `VoltAgent/awesome-agent-skills`, `ComposioHQ/awesome-claude-skills` |

### Agentic & Editing Libraries Terpasang
- **Python (`backend/`)**: `mcp`, `pydantic-ai`, `langgraph`, `openai-agents`, `google-adk`, `crewai`, `browser-use`, `anthropic`, `openai`, `playwright`, `python-docx`, `pypdf`, `reportlab`, `python-pptx`, `openpyxl`, `pillow`, `beautifulsoup4`, `lxml`, `gitpython`, `tree-sitter`, `rich`
- **TypeScript (`frontend/`)**: `ai` (Vercel AI SDK), `@modelcontextprotocol/sdk`, `@mastra/core`, `@langchain/langgraph`, `zod`
- **System Editing CLIs**: `ffmpeg`, `pandoc`, `poppler-utils` (`pdftoppm`), `imagemagick` (`convert`)

## Quickstart

```bash
# 1. Install seluruh dependensi Python/TypeScript & sync 74+ Tier-S skills
make setup

# 2. Verifikasi audit keamanan skill & status library aktif
make audit-skills
make libraries

# 3. Jalankan lint, test, dan production build
make lint
make test
make build
```

### Mengelola Skill & Memori lewat CLI `lazarus`

```bash
# Lihat seluruh skill aktif & cari skill tertentu
lazarus skills list
lazarus skills search ponytail
lazarus skills search editing

# Pasang skill tambahan secara on-demand dari GitHub (mis. dari 3.000+ skill mega-hub)
lazarus skills install --repo sickn33/agentic-awesome-skills --path <path-ke-skill>

# Audit keamanan semua SKILL.md terhadap aturan non-harm Lazarus
lazarus skills audit

# Cek status live seluruh library agentic Python, TypeScript, dan CLI
lazarus skills libraries

# Simpan pembelajaran & laporan jujur
lazarus learn --topic "Agentic Arsenal" --content "75 skill & 25 library aktif terverifikasi." --tags "skills,agentic"
lazarus report --title "Arsenal Audit" --summary "Seluruh skill & library lulus verifikasi." --confidence 0.98
```

### Menjalankan API & Command Center

```bash
# Terminal 1 — FastAPI backend (http://127.0.0.1:8000)
make dev-backend

# Terminal 2 — React Command Center (http://127.0.0.1:5173)
make dev-frontend
```
