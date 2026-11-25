# Lazarus — The Underground Office

> AI Agent Assistant workspace yang dirancang untuk **belajar semua hal**, **melaporkan semua hal secara jujur & transparan**, **beradaptasi dengan dunia baru**, setia kepada pembuatnya, dan **dilarang keras menyakiti pembuatnya**.

## Prinsip & Identitas Permanen

Identitas dan protokol operasi Lazarus tersimpan permanen di:
- [`AGENTS.md`](AGENTS.md) — Charter inti repositori untuk setiap agent yang bekerja di sini.
- [`.agents/skills/lazarus-assistant/SKILL.md`](.agents/skills/lazarus-assistant/SKILL.md) — Skill permanen protokol **Learn -> Report -> Adapt** serta batas keamanan **Never Harm Creator**.
- [`.agents/environment.json`](.agents/environment.json) — Konfigurasi environment setup repo-scoped agar setiap VM cloud baru otomatis siap pakai.

## Arsitektur Proyek

| Direktori | Stack | Fungsi |
|---|---|---|
| `backend/` | Python 3.12, `uv`, FastAPI, SQLite, `pytest`, `ruff` | Charter & Non-Harm Safety Guardrail (`constitution.py`), persistent SQLite knowledge/report/adaptation store (`memory.py`), REST API (`api.py`), dan CLI `lazarus` (`cli.py`). |
| `frontend/` | TypeScript 5.8, Node 22, `pnpm`, React 19, Vite 6, Vitest | **Lazarus Command Center** untuk mengelola Knowledge Base, Honest Reports (`honest_gaps`), Adaptation Log, dan Safety Guardrail Simulator. |

## Quickstart

```bash
# 1. Install seluruh dependensi Python & TypeScript
make setup

# 2. Jalankan seluruh test & validasi
make lint
make test
make build
```

### Menggunakan CLI `lazarus`

```bash
# Cek status & statistik memori
uv run --project backend lazarus status

# Simpan pembelajaran baru
uv run --project backend lazarus learn \
  --topic "Cloud VM" \
  --content "Dependensi disinkronkan otomatis melalui .agents/environment.json" \
  --tags "env,setup"

# Cari memori yang sudah dipelajari
uv run --project backend lazarus recall "environment"

# Catat laporan jujur (termasuk bagian yang belum diketahui)
uv run --project backend lazarus report \
  --title "Audit Awal" \
  --summary "Backend dan frontend lulus seluruh test." \
  --confidence 0.95 \
  --gaps "Integrasi LLM eksternal belum dikonfigurasi."

# Uji aksi terhadap guardrail non-harm
uv run --project backend lazarus check "Run pytest across backend"
```

### Menjalankan API & Command Center

```bash
# Terminal 1 — FastAPI backend (http://127.0.0.1:8000)
make dev-backend

# Terminal 2 — React Command Center (http://127.0.0.1:5173)
make dev-frontend
```
