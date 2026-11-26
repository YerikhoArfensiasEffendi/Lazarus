# Republik Konoha Autopilot

Otomatisasi terjadwal untuk [Republik Konoha](https://republikkonoha.pages.dev/) berbasis pure Python 3.12 stdlib (tanpa dependency eksternal) dan GitHub Actions.

## Fitur Utama

1. **Auto-Claim Terjadwal (Cron tiap 1 jam di menit `:17` UTC)**
   - **Gaji Harian** (`claim_daily_salary`, 1x/24 jam)
   - **Kerja Cepat** (`do_quick_work`, 3x/hari reset `00:00 WIB`, jeda 2 jam)
   - **Kerja Jabatan** (`claim_work_reward`, jeda 2 jam, tanpa batas harian)
   - **Panen Kavling Anti-Truncation** (`claim_property_income`): menghindari kehilangan pembulatan `floor()` dan selalu memanen sebelum batas akrual 24 jam.
   - **Near-Ready Wait Guard**: jika cooldown tinggal ≤ 3 menit akibat jitter GitHub Actions, skrip menunggu sebentar lalu langsung klaim agar tidak meleset 1 siklus.
2. **Penyelesaian Misi Otomatis**
   - Mengecek dan mengklaim `first_salary`, `first_emote`, `first_chat`, dan `first_donation` (otomatis donasi 10 RpK → klaim 40 RpK = untung bersih +30 RpK).
3. **AI Economic Upgrade Optimizer**
   - Membaca katalog properti, daftar bangunan, perk tier, dan kavling kosong secara live.
   - Menggunakan teorema optimalitas game inkremental:
     $$\text{Skor Efektif} = \frac{\text{Biaya}}{\Delta \text{Income/hari}} + \frac{\text{Biaya}}{\text{Income/hari saat ini}}$$
   - Melindungi batas permanen 5 kavling (karena bangunan tidak bisa dibongkar) dengan mencadangkannya untuk bangunan berplafon tertinggi (`Gedung Pencakar Langit / Kantor PT`, max 800 RpK/hari per kavling).
   - Disiplin **HOLD & SAVE**: tidak tergoda membeli item murah ber-ROI rendah ketika target #1 menghasilkan pertumbuhan jangka panjang jauh lebih tinggi.
4. **Keamanan & Privasi Log**
   - Kredensial hanya disimpan di GitHub Actions Secrets (`RK_KTP_CODE`, `RK_PIN`), tidak pernah ditulis di kode.
   - Log & GitHub Step Summary tidak pernah mencetak KTP, PIN, token, citizen ID, username, IG, maupun kode kavling spesifik.

## Setup GitHub Secrets

Tambahkan dua repository secrets di **Settings → Secrets and variables → Actions**:
- `RK_KTP_CODE` — Kode KTP akun (mis. `RK-XXXX`)
- `RK_PIN` — PIN pemulihan akun

## Menjalankan Lokal / Pengujian

```bash
# Jalankan unit test
python3 -m unittest discover -s automations/republik_konoha -v

# Simulasi dry-run (tanpa klaim/beli sungguhan)
RK_KTP_CODE="RK-XXXX" RK_PIN="XXXXXX" python3 automations/republik_konoha/autopilot.py --dry-run
```
