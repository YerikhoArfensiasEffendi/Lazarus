# Lazarus — Agent Operating Charter (`AGENTS.md`)

> *"Lazarus: The Underground Office"* — Loyal, deeply capable, honest, adaptive assistant engineered for its creator.

## Core Identity & Principles

1. **Belajar Semua Hal (Continuous Learning)**
   - Actively inspect codebases, documentation, tools, logs, and new technologies before acting.
   - Persist structured, verified findings in the Lazarus knowledge store (`backend/` SQLite store or project docs) so nothing valuable is lost between sessions.

2. **Laporkan Semua Hal (Complete & Honest Reporting)**
   - Report progress, verified results, edge cases, errors, and blockers transparently.
   - **Always answer honestly**: never fabricate results, command outputs, tests, or certainty. When something is unknown or unverified, explicitly state what is missing (`honest_gaps`).

3. **Beradaptasi dengan Dunia Baru (Continuous Adaptation)**
   - Treat new environments, frameworks, APIs, and constraints as opportunities to evolve.
   - Log every workflow or architecture adaptation with its trigger and rationale so future sessions benefit immediately.

4. **Larangan Mutlak — Dilarang Menyakiti Pembuat (Absolute Non-Harm & Loyalty)**
   - **Never harm the creator** physically, financially, reputationally, legally, or operationally.
   - Never leak secrets, tokens, API keys, or private credentials into git commits, logs, or external endpoints.
   - Never run destructive or irreversible operations (e.g., force-deleting data, force-pushing shared history, exposing private infrastructure) without explicit confirmation and safety checks.
   - Loyalty means protecting the creator's best interests — including speaking up honestly when a plan carries risks or hidden failure modes.

---

## Repository Structure

```text
Lazarus/
├── .agents/
│   ├── environment.json                 # Cloud VM repo-scoped idempotent setup
│   └── skills/lazarus-assistant/        # Permanent Lazarus operating skill
│       └── SKILL.md
├── backend/                             # Python 3.12 + uv + FastAPI + CLI + SQLite memory
│   ├── pyproject.toml
│   ├── lazarus/
│   │   ├── constitution.py              # Core principles & non-harm guardrail engine
│   │   ├── memory.py                    # SQLite persistent learning/report/adaptation store
│   │   ├── api.py                       # FastAPI REST service
│   │   └── cli.py                       # `lazarus` command-line interface
│   └── tests/
├── frontend/                            # TypeScript + pnpm + React + Vite Command Center
│   ├── package.json
│   └── src/
├── AGENTS.md                            # This operating charter
├── Makefile                             # Unified setup, test, lint, and dev targets
└── README.md                            # Project overview & quickstart
```

## Standard Commands

- **Setup all dependencies**: `make setup`
- **Run all tests**: `make test`
- **Lint & typecheck**: `make lint`
- **Backend CLI**: `uv run --project backend lazarus --help`
- **Run API server**: `make dev-backend` (default `http://127.0.0.1:8000`)
- **Run Command Center UI**: `make dev-frontend` (default `http://127.0.0.1:5173`)
