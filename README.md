# SCC Telkom Checker 🛡️

Script Python ringan untuk mengecek hasil **SCC (Service Completion Check)** Telkom IndiHome — **tanpa browser**, langsung ke API-nya.

---

## 🚀 Instalasi & Requirements

### Android (Termux)
```bash
pkg update && pkg install git python -y
pip install -r requirements.txt
```

### Windows / Linux / macOS
```bash
pip install -r requirements.txt
```

---

## 📖 Penggunaan

### Cek satu tiket
```bash
python scc_checker.py INC53061310
```

### Cek satu tiket + langsung generate gambar bukti SCC
```bash
python scc_checker.py INC53061310 --image
```

### Cek tiket + lokasi GPS + auto speed + generate gambar
```bash
python scc_checker.py INC53061310 --lat -8.638186 --lon 115.215263 --auto-speed --image
```

### Cek batch banyak tiket dari file (+ generate semua gambar)
```bash
python scc_checker.py --batch contoh_tiket.txt --auto-speed --image
```

### Output JSON (untuk integrasi program lain)
```bash
python scc_checker.py INC53061310 --json
```

### Simpan hasil ke file JSON
```bash
python scc_checker.py INC53061310 --output hasil.json
```

### Cek batch + simpan ke JSON (tanpa field _raw)
```bash
python scc_checker.py --batch contoh_tiket.txt --output semua_hasil.json --no-raw
```

---

## 📦 Sebagai Modul Python

```python
from scc_checker import check_scc

# Cek satu tiket
result = check_scc("INC53061310")
print(result["kualitas_jaringan"])  # "Layak" atau "Belum Layak"
print(result["status"])             # "NORMAL" atau "BELUM NORMAL — ..."

# Cek dengan koordinat GPS
result = check_scc("INC53061310", lat=-8.638186, lon=115.215263)
print(result["odp_distance_m"])     # jarak ke ODP dalam meter
print(result["odp_name"])           # nama ODP, misal: ODP-UBN-FCQ/66
```

---

## 📊 Contoh Output Terminal

```
════════════════════════════════════════════════════════
  📋  HASIL SCC TELKOM
════════════════════════════════════════════════════════
  🎫  Tiket        : INC53061310
  📡  ND           : 172418803791
  🌍  Witel        : DENPASAR
  🔌  OLT          : GPON14-D5-UBN-3
  📦  Paket        : INETF30M
  🌐  IP Publik    : 2404:c0:bb01:9f76:922:a680:316b:e16a
  🔁  BNG Check    : ✅ Valid
────────────────────────────────────────────────────────
  📶  Kualitas Jaringan  : ✅ Layak
  ⚡  Kecepatan Internet : -
  🔧  Speed ONT          : -
────────────────────────────────────────────────────────
  📍  ODP Name     : ODP-UBN-FCQ/66
  📏  Jarak ODP    : 695 m
  ✅  Dalam Radius : ✅ Ya (< 1km)
────────────────────────────────────────────────────────
  ✅  STATUS       : NORMAL
════════════════════════════════════════════════════════
```

---

## 📊 Contoh Output JSON

```json
{
  "ticket": "INC53061310",
  "nd": "172418803791",
  "witel": "DENPASAR",
  "olt": "GPON14-D5-UBN-3",
  "service_id": "29259599_172418803791_INTERNET",
  "package": "INETF30M",
  "ip_address": "2404:c0:bb01:9f76:922:a680:316b:e16a",
  "is_bng": true,
  "kualitas_jaringan": "Layak",
  "kecepatan_internet": null,
  "ont_speed": "-",
  "odp_name": "ODP-UBN-FCQ/66",
  "odp_distance_m": 695,
  "odp_inside_radius": true,
  "odp_lat": -8.634846,
  "odp_long": 115.220854,
  "status": "NORMAL"
}
```

---

## ⚙️ Argumen Lengkap

| Argumen | Keterangan |
|---|---|
| `ticket` | Nomor tiket (positional argument) |
| `--batch FILE` | File daftar tiket (satu per baris) |
| `--nd ND` | Nomor internet (opsional) |
| `--lat LAT` | Latitude GPS (untuk cek jarak ODP) |
| `--lon LON` | Longitude GPS (untuk cek jarak ODP) |
| `--output FILE` | Simpan hasil ke file JSON |
| `--json` | Tampilkan output JSON mentah |
| `--no-raw` | Sembunyikan field `_raw` dari JSON |
| `--timeout SEC` | Timeout request (default: 20 detik) |

---

## 🔍 Cara Kerja (API Flow)

```
1. GET  /Check_embededv1/          → buat session cookie
2. POST /createTask                → dapat UID unik
3. POST /retrieveToken1            → validasi token
4. POST /retrieveNDByIN            → ambil ND, Witel, OLT, Service ID
5. POST /retrieveUPCF              → ambil nama paket
6. POST /retrieveIPRadius          → cek IP BNG
7. GET  myip.tacc.id               → ambil IP publik
8. POST /saveWho                   → simpan data IP
9. POST /retrieveSpeedAcsis        → speed ONT dari sistem
10. POST /retrieveUkur             → ⭐ Kualitas Jaringan (redaman_passed)
[Opsional jika ada lat/lon:]
11. POST /RequestSpeedDBT          → dapat encrypted param
12. POST api.mysiis.io/auth        → tukar param → JWT token
13. POST api.mysiis.io/check-odp   → ⭐ Jarak & Nama ODP
```

---

## ⚠️ Catatan

- **Kecepatan Internet** tidak bisa dicek tanpa speedtest sungguhan (Ookla iframe). Field ini akan bernilai `null`.
- **Jarak ODP** hanya tersedia jika kamu menyertakan `--lat` dan `--lon`.
- Script ini menggunakan API internal Telkom — bisa berubah sewaktu-waktu.
- Hanya untuk penggunaan internal teknisi/testing, bukan untuk manipulasi hasil SCC.
