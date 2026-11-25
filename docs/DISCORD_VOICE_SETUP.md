# Panduan Menjalankan Lazarus Voice Assistant di Discord (Lokal di Laptop)

Panduan ini menjelaskan cara menjalankan **Lazarus** secara lokal di laptop Anda sehingga Lazarus dapat:
1. **Masuk ke Voice Channel Discord** (`/join`) dan mengobrol santai 2 arah layaknya **ChatGPT Voice Mode** (lengkap dengan *barge-in* / bisa dipotong saat bicara).
2. **Menggunakan 75+ Agentic Skills & Memori SQLite** untuk menjawab pertanyaan secara langsung melalui suara.
3. **Mengirimkan data lengkap, kode, ringkasan, laporan, dan file lampiran otomatis ke Chat DM Discord** Anda (sehingga suara tetap ringkas & enak didengar, sementara data mentahnya rapi di DM).

---

## Arsitektur (Kenapa Hybrid Node.js + Python?)

Sejak **1 Maret 2026**, Discord mewajibkan protokol enkripsi end-to-end **DAVE** (*Discord Audio & Video E2EE*) untuk seluruh voice channel. Library Python lama (`discord-ext-voice-recv`) belum mendukung dekripsi DAVE sehingga hanya menghasilkan suara rusak/noise.

Karena itu Lazarus menggunakan arsitektur lokal dua bagian yang saling terhubung lewat `localhost` (latensi <1 ms):
- **`discord-bot/` (Node.js + TypeScript)**: Menggunakan `discord.js` + `@discordjs/voice` + `@snazzah/davey` (resmi mendukung DAVE E2EE kirim & terima suara) + `prism-media` + `opusscript`.
- **`backend/` (Python 3.12)**: Menjalankan **Whisper lokal (`faster-whisper`)** -> **Lazarus Brain** (memuat skill yang relevan dari 75 skill + memori SQLite + LLM lokal **Ollama** / API opsional) -> **TTS** (`edge-tts` suara Bahasa Indonesia super natural gratis tanpa API key, atau `piper-tts` 100% offline).

---

## Langkah 1 — Buat Discord Bot (5 Menit, Gratis)

1. Buka [Discord Developer Portal](https://discord.com/developers/applications) lalu klik **New Application** (beri nama `Lazarus`).
2. Masuk ke menu **Bot**:
   - Klik **Reset Token** dan salin token tersebut (jangan pernah dibagikan atau di-commit ke Git!).
   - Aktifkan **Message Content Intent** (dan **Server Members Intent** jika perlu).
3. Masuk ke menu **OAuth2 -> URL Generator**:
   - **Scopes**: centang `bot` dan `applications.commands`.
   - **Bot Permissions**: centang `View Channels`, `Send Messages`, `Attach Files`, `Connect`, `Speak`, `Use Voice Activity`.
4. Buka URL undangan yang dihasilkan dan masukkan bot `Lazarus` ke server Discord pribadi Anda.
5. Pastikan di pengaturan Discord Anda, opsi **Allow direct messages from server members** aktif untuk server tersebut agar Lazarus bisa mengirim DM ke Anda.

---

## Langkah 2 — Siapkan Otak LLM Lokal di Laptop (Ollama)

Agar 100% jalan lokal di laptop tanpa biaya API:
1. Install [Ollama](https://ollama.com) di laptop Anda (Windows, macOS, atau Linux).
2. Unduh model yang cepat dan fasih Bahasa Indonesia + English:
   ```bash
   # Rekomendasi laptop RAM 16GB (cepat & pintar):
   ollama pull qwen2.5:7b-instruct

   # Jika laptop RAM 8GB (lebih ringan & cepat):
   ollama pull qwen2.5:3b-instruct
   ```
   *(Catatan: Jika ingin kecepatan dan kecerdasan setara ChatGPT cloud di laptop spek ringan, Anda cukup mengganti `LAZARUS_LLM_BASE_URL`, `LAZARUS_LLM_MODEL`, dan `LAZARUS_LLM_API_KEY` di `.env` ke OpenAI / Gemini API.)*

---

## Langkah 3 — Install & Konfigurasi Lokal di Laptop

Pastikan di laptop terpasang: **Python 3.12 (`uv`)**, **Node.js 22 (`pnpm`)**, dan **`ffmpeg`**.

```bash
# 1. Clone repo Lazarus & masuk ke direktori
git clone https://github.com/YerikhoArfensiasEffendi/Lazarus.git
cd Lazarus

# 2. Install semua dependensi (Python backend, Frontend, Discord Bot, & 74+ Tier-S skills)
make setup

# 3. Verifikasi DAVE E2EE, Opus, dan FFmpeg siap
make discord-doctor

# 4. Buat file .env dari template
cp .env.example .env
```

Buka `.env` dan isi minimal:
```env
DISCORD_BOT_TOKEN=paste_token_bot_discord_anda_di_sini
DISCORD_GUILD_ID=id_server_discord_anda_untuk_sync_slash_command_instan
LAZARUS_ALLOWED_USER_IDS=id_akun_discord_anda_agar_hanya_anda_yang_bisa_akses
LAZARUS_LLM_MODEL=qwen2.5:7b-instruct
```

---

## Langkah 4 — Jalankan Lazarus & Mulai Ngobrol!

Buka **2 terminal** di folder `Lazarus`:

```bash
# Terminal 1 — Jalankan Lazarus Python Brain + Whisper STT + TTS
make dev-backend

# Terminal 2 — Jalankan Lazarus Discord Voice & DM Bot
make dev-discord
```

Di Discord:
1. Masuk ke salah satu **Voice Channel** di server Anda.
2. Ketik **`/join`** — Lazarus langsung masuk, menyapa lewat suara, dan mulai mendengarkan!
3. Langsung bicara santai dalam Bahasa Indonesia atau Inggris, misalnya:
   - *"Lazarus, pakai gaya lazy developer tolong buatkan script Python untuk bersihin CSV lalu kirim kodenya ke DM."*
   - *"Lazarus, jelasin arsitektur MCP secara singkat, lalu kirim catatan lengkapnya ke DM aku."*
4. Lazarus menjawab ringkas & natural lewat **suara di Voice Channel**, dan pada saat bersamaan mengirim kode/data/file lengkap ke **Chat DM Discord** Anda!
5. Anda juga bisa membalas langsung di **Chat DM Discord** atau pakai `/ask`, `/skills`, `/status`, `/dm-test`, dan `/leave`.

---

## Tips Performa & Latensi di Laptop

| Kondisi Laptop | Pengaturan `.env` yang Disarankan | Perkiraan Respon |
|---|---|---|
| Laptop dengan GPU NVIDIA / Apple Silicon (M1–M4) | `LAZARUS_WHISPER_MODEL=small`, `LAZARUS_LLM_MODEL=qwen2.5:7b-instruct`, `LAZARUS_TTS_PROVIDER=edge` | ~1.5 – 3 detik |
| Laptop CPU saja (RAM 8–16GB) | `LAZARUS_WHISPER_MODEL=base`, `LAZARUS_LLM_MODEL=qwen2.5:3b-instruct`, `LAZARUS_TTS_PROVIDER=edge` | ~2.5 – 5 detik |
| Mode 100% Offline TTS (tanpa internet untuk suara) | Unduh model Piper `.onnx` (mis. `id_ID-news_tts-medium.onnx`), set `LAZARUS_TTS_PROVIDER=piper` dan `LAZARUS_PIPER_MODEL_PATH=...` | ~0.3 detik untuk TTS |
