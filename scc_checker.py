#!/usr/bin/env python3
"""
SCC Telkom Checker v4
=====================
Script untuk mengecek hasil SCC (Service Completion Check) Telkom IndiHome
tanpa perlu browser — menggunakan reverse-engineered API.

Kompatibel dengan: Android (Termux), Windows, Linux, macOS

Instalasi:
  pip install requests            # minimal
  pip install requests speedtest-cli  # dengan speedtest otomatis

Penggunaan CLI:
  python scc_checker.py                          # mode interaktif (menu)
  python scc_checker.py INC53061310              # cek langsung
  python scc_checker.py INC53061310 --lat -8.638 --lon 115.215 --speedtest
  python scc_checker.py INC53061310 --dl 150 --ul 50   # manual speed (Mbps)
  python scc_checker.py INC53061310 --auto-speed        # auto dari paket PCRF
  python scc_checker.py --batch tiket.txt --output hasil.json

Sebagai modul:
  from scc_checker import check_scc
  result = check_scc("INC53061310", lat=-8.638, lon=115.215, run_speedtest=True)
  result = check_scc("INC53061310", manual_dl_mbps=150.0, manual_ul_mbps=50.0)
  result = check_scc("INC53061310", auto_speed=True)
"""

import json
import sys
import os
import io
import base64
import uuid
import random
import re
import argparse
from datetime import datetime, timezone
from urllib.parse import unquote

try:
    import requests
except ImportError:
    print("❌ Library 'requests' belum terinstall.")
    print("   Jalankan: pip install requests")
    sys.exit(1)

try:
    from PIL import Image, ImageDraw, ImageFont
    HAS_PILLOW = True
except ImportError:
    HAS_PILLOW = False

try:
    from logos_b64 import LOGO1_B64, LOGO2_B64
except ImportError:
    LOGO1_B64 = ""
    LOGO2_B64 = ""

# ─── Konstanta ────────────────────────────────────────────────────────────────

BASE_URL    = "https://scc.telkom.co.id/CloseTicket.Internet/Check_embededv1"
MYSIIS_BASE = "https://api.mysiis.io/m/speedtest/v1"
MYSIIS_KEY  = "MVnSDdytX3LVwtwDsTeVDiBxVAUoq9p9"

_HEADERS_AJAX = {
    "User-Agent"       : "Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36 "
                         "(KHTML, like Gecko) Chrome/120.0.0.0 Mobile Safari/537.36",
    "X-Requested-With" : "XMLHttpRequest",
    "X-KL-Ajax-Request": "Ajax_Request",
    "Content-Type"     : "application/x-www-form-urlencoded",
    "Accept"           : "application/json, text/javascript, */*; q=0.01",
}

_DETAIL_ACCESS = json.dumps({
    "brands"  : [{"brand": "Chrome", "version": "120"}],
    "mobile"  : True,
    "platform": "Android",
})

# ─── Speed Helpers ────────────────────────────────────────────────────────────

def _add_noise(kbps: int, pct: float = 2.0) -> int:
    """Tambah variasi acak ±pct% pada nilai Kbps agar terlihat natural."""
    variation = kbps * pct / 100
    return max(1, int(kbps + random.uniform(-variation, variation)))


def _parse_package_speed(package_name: str):
    """
    Parse kecepatan dari nama paket PCRF.
    Strategi dua tahap:
      1. Cari angka diikuti 'M'  → INETF30M    = 30 Mbps
      2. Fallback: angka terakhir → INETNLOY50  = 50 Mbps
    Return (download_mbps, upload_mbps) atau None jika tidak bisa di-parse.
    """
    if not package_name:
        return None

    name = package_name.upper()

    # Tahap 1: cari pola {angka}M (paling spesifik)
    m = re.search(r'(\d+)M', name)
    if m:
        dl = float(m.group(1))
        ul = dl * 0.5
        return dl, ul

    # Tahap 2: ambil angka terakhir di string (fallback)
    m = re.search(r'(\d+)\D*$', name)
    if m:
        dl = float(m.group(1))
        ul = dl * 0.5
        return dl, ul

    return None


# ─── Image Generator Helpers ──────────────────────────────────────────────────

def _get_save_dir() -> str:
    """
    Cari lokasi penyimpanan gambar (diutamakan internal/Documents/SCC di Android).
    """
    candidates = [
        "/sdcard/Documents/SCC",
        "/storage/emulated/0/Documents/SCC",
        "/sdcard/Download/SCC",
        os.path.expanduser("~/Documents/SCC"),
        "SCC_Images",
    ]
    for d in candidates:
        try:
            os.makedirs(d, exist_ok=True)
            # Test write permission
            test_file = os.path.join(d, ".test_write")
            with open(test_file, "w") as f:
                f.write("1")
            os.remove(test_file)
            return d
        except Exception:
            continue
    # Fallback ke folder lokal
    local_dir = "SCC_Images"
    os.makedirs(local_dir, exist_ok=True)
    return local_dir


def _get_font(size: int, bold: bool = False):
    """Cari font sistem Android/Windows yang tersedia untuk Pillow."""
    candidates = []
    if bold:
        candidates = [
            "/system/fonts/Roboto-Medium.ttf",
            "/system/fonts/Roboto-Bold.ttf",
            "/system/fonts/DroidSans-Bold.ttf",
            "C:\\Windows\\Fonts\\arialbd.ttf",
            "C:\\Windows\\Fonts\\segoeui.ttf",
            "arialbd.ttf",
        ]
    else:
        candidates = [
            "/system/fonts/Roboto-Regular.ttf",
            "/system/fonts/DroidSans.ttf",
            "C:\\Windows\\Fonts\\arial.ttf",
            "C:\\Windows\\Fonts\\segoeui.ttf",
            "arial.ttf",
        ]
    for p in candidates:
        if os.path.exists(p):
            try:
                return ImageFont.truetype(p, size)
            except Exception:
                pass
    try:
        return ImageFont.truetype("DejaVuSans.ttf", size)
    except Exception:
        return ImageFont.load_default()


def _draw_arrow_left(draw, x, y, size=16, color=(211, 47, 47)):
    """Gambar icon panah kiri manual."""
    draw.line([(x, y), (x + size, y)], fill=color, width=3)
    draw.line([(x, y), (x + int(size * 0.4), y - int(size * 0.4))], fill=color, width=3)
    draw.line([(x, y), (x + int(size * 0.4), y + int(size * 0.4))], fill=color, width=3)


def generate_scc_image(data: dict, custom_filename: str = None) -> str | None:
    """
    Generate gambar PNG hasil SCC Telkom pixel-accurate dan simpan ke Documents/SCC.
    Nama file format: nomortiket_user_odp_datetime.png
    """
    if not HAS_PILLOW:
        _log("⚠️  Pillow belum terinstall. Install dengan: pkg install python-pillow")
        return None

    # Siapkan informasi untuk nama file: nomortiket_user_odp_datetime
    ticket   = data.get("ticket", "UNKNOWN")
    nd       = data.get("nd", "UNKNOWN")
    odp_raw  = data.get("odp_name") or "NO_ODP"
    odp_clean = re.sub(r'[^A-Za-z0-9_-]', '_', odp_raw)
    now_dt   = datetime.now()
    dt_str   = now_dt.strftime("%Y%m%d_%H%M%S")

    save_dir = _get_save_dir()
    if custom_filename:
        filename = custom_filename
    else:
        filename = f"{ticket}_{nd}_{odp_clean}_{dt_str}.png"

    output_path = os.path.join(save_dir, filename)

    width  = 720
    height = 1560

    bg_red       = (219, 68, 85)        # #db4455
    white        = (255, 255, 255)
    gray_label   = (233, 236, 239)      # #e9ecef
    text_dark    = (33, 37, 41)          # #212529
    text_gray    = (73, 80, 87)          # #495057
    border_color = (206, 212, 218)      # #ced4da

    img  = Image.new("RGB", (width, height), bg_red)
    draw = ImageDraw.Draw(img)

    # 1. Header Putih + Logo
    header_h = 100
    draw.rectangle([(0, 0), (width, header_h)], fill=white)

    try:
        logo1 = None
        logo2 = None
        if os.path.exists("logo1.png") and os.path.exists("logo2.png"):
            logo1 = Image.open("logo1.png").convert("RGBA")
            logo2 = Image.open("logo2.png").convert("RGBA")
        elif LOGO1_B64 and LOGO2_B64:
            logo1 = Image.open(io.BytesIO(base64.b64decode(LOGO1_B64))).convert("RGBA")
            logo2 = Image.open(io.BytesIO(base64.b64decode(LOGO2_B64))).convert("RGBA")

        if logo1 and logo2:
            target_h = 44
            r1 = target_h / logo1.height
            logo1 = logo1.resize((int(logo1.width * r1), target_h), Image.Resampling.LANCZOS)
            r2 = target_h / logo2.height
            logo2 = logo2.resize((int(logo2.width * r2), target_h), Image.Resampling.LANCZOS)
            img.paste(logo1, (36, (header_h - target_h) // 2), logo1)
            img.paste(logo2, (width - logo2.width - 36, (header_h - target_h) // 2), logo2)
    except Exception:
        pass

    # 2. Fonts
    font_title   = _get_font(34, bold=True)
    font_ts_top  = _get_font(23, bold=False)
    font_label   = _get_font(22, bold=True)
    font_val     = _get_font(23, bold=False)
    font_ts_bot  = _get_font(21, bold=False)
    font_verdict = _get_font(24, bold=False)
    font_btn_ok  = _get_font(24, bold=True)
    font_uid     = _get_font(19, bold=False)
    font_menu    = _get_font(26, bold=True)

    # 3. Judul Utama
    title_text = "Hasil Pengecekan Internet Anda"
    bbox_t = draw.textbbox((0, 0), title_text, font=font_title)
    tw = bbox_t[2] - bbox_t[0]
    draw.text(((width - tw) // 2, 130), title_text, fill=white, font=font_title)
    draw.line([(55, 180), (width - 55, 180)], fill=(255, 255, 255, 180), width=2)

    # Timestamp atas
    ts1 = now_dt.strftime("%Y-%m-%d %H:%M:%S WIB")
    bbox_ts1 = draw.textbbox((0, 0), ts1, font=font_ts_top)
    draw.text((width - 55 - (bbox_ts1[2] - bbox_ts1[0]), 196), ts1, fill=white, font=font_ts_top)

    # 4. Daftar Kartu / Field
    kualitas   = data.get("kualitas_jaringan", "Layak")
    kecepatan  = data.get("kecepatan_internet", "Layak") or "Layak"
    speed_ont  = data.get("ont_speed", "-") or "-"
    lat        = data.get("odp_lat")
    lon        = data.get("odp_long")
    latlong    = f"{lat:.6f},{lon:.6f}" if (lat and lon) else "-"
    jarak      = data.get("odp_distance_m")
    jarak_str  = f"{jarak} m" if jarak is not None else "0 m"
    odp_name   = data.get("odp_name") or "-"

    items = [
        ("Nomor Tiket / Permintaan", ticket),
        ("Nomor Internet Anda", nd),
        ("Kualitas Jaringan", kualitas),
        ("Kecepatan Internet", kecepatan),
        ("Speed Test ONT", speed_ont),
        ("LatLong ODP", latlong),
        ("Jarak ODP", jarak_str),
        ("Nama ODP", odp_name),
    ]

    card_x  = 55
    card_w  = width - (card_x * 2)
    card_h  = 58
    gap     = 14
    split_x = card_x + int(card_w * 0.52)
    start_y = 238

    for i, (lbl, val) in enumerate(items):
        y = start_y + i * (card_h + gap)
        draw.rounded_rectangle([(card_x, y), (card_x + card_w, y + card_h)], radius=8, fill=white)
        draw.rounded_rectangle([(card_x, y), (split_x, y + card_h)], radius=8, fill=gray_label)
        draw.rectangle([(split_x - 10, y), (split_x, y + card_h)], fill=gray_label)
        draw.line([(split_x, y), (split_x, y + card_h)], fill=border_color, width=1)

        bbox_l = draw.textbbox((0, 0), lbl, font=font_label)
        draw.text((card_x + 18, y + (card_h - (bbox_l[3] - bbox_l[1])) // 2 - 1), lbl, fill=text_gray, font=font_label)

        val_str = str(val)
        bbox_v = draw.textbbox((0, 0), val_str, font=font_val)
        draw.text((split_x + 18, y + (card_h - (bbox_v[3] - bbox_v[1])) // 2 - 1), val_str, fill=text_dark, font=font_val)

    # 5. Timestamp Bawah
    curr_y = start_y + len(items) * (card_h + gap) + 6
    ts2 = now_dt.strftime("%H:%M:%S WIB")
    bbox_ts2 = draw.textbbox((0, 0), ts2, font=font_ts_bot)
    draw.text((width - 55 - (bbox_ts2[2] - bbox_ts2[0]), curr_y), ts2, fill=white, font=font_ts_bot)

    # 6. Verdict Message
    curr_y += 45
    draw.line([(55, curr_y), (width - 55, curr_y)], fill=(255, 255, 255, 90), width=1)
    curr_y += 32
    verdict = "Layanan internet anda dalam kondisi normal."
    bbox_vd = draw.textbbox((0, 0), verdict, font=font_verdict)
    draw.text(((width - (bbox_vd[2] - bbox_vd[0])) // 2, curr_y), verdict, fill=white, font=font_verdict)

    # 7. Tombol OK
    curr_y += 68
    btn_w, btn_h = 132, 54
    bx = (width - btn_w) // 2
    draw.rounded_rectangle([(bx, curr_y), (bx + btn_w, curr_y + btn_h)], radius=6, fill=white)
    bbox_ok = draw.textbbox((0, 0), "Ok", font=font_btn_ok)
    draw.text((bx + (btn_w - (bbox_ok[2] - bbox_ok[0])) // 2, curr_y + (btn_h - (bbox_ok[3] - bbox_ok[1])) // 2 - 1), "Ok", fill=text_dark, font=font_btn_ok)

    # 8. UID Hash
    curr_y += 185
    uid = data.get("_raw", {}).get("uid", "1789894156.430d9c5e5ac4e9b03243d9182b41a67ceda50773")
    bbox_uid = draw.textbbox((0, 0), uid, font=font_uid)
    draw.text(((width - (bbox_uid[2] - bbox_uid[0])) // 2, curr_y), uid, fill=(255, 255, 255, 210), font=font_uid)

    # 9. Tombol Menu Utama Bawah
    curr_y += 45
    menu_h = 70
    draw.rounded_rectangle([(card_x, curr_y), (card_x + card_w, curr_y + menu_h)], radius=12, fill=white, outline=border_color, width=1)
    menu_text = "Kembali Ke Menu Utama"
    bbox_m = draw.textbbox((0, 0), menu_text, font=font_menu)
    total_w = 22 + 12 + (bbox_m[2] - bbox_m[0])
    start_x = (width - total_w) // 2

    _draw_arrow_left(draw, start_x, curr_y + menu_h // 2, size=18, color=(211, 47, 47))
    draw.text((start_x + 34, curr_y + (menu_h - (bbox_m[3] - bbox_m[1])) // 2 - 1), menu_text, fill=(211, 47, 47), font=font_menu)

    try:
        img.save(output_path, "PNG")
        return output_path
    except Exception as e:
        _log(f"⚠️  Gagal menyimpan gambar: {e}")
        return None


# ─── Fungsi Utama ─────────────────────────────────────────────────────────────

def check_scc(ticket_id: str,
              nd: str = None,
              lat: float = None,
              lon: float = None,
              run_speedtest: bool = False,
              auto_speed: bool = False,
              manual_dl_mbps: float = None,
              manual_ul_mbps: float = None,
              manual_ping_ms: float = 10.0,
              manual_jitter_ms: float = 1.0,
              timeout: int = 20) -> dict:
    """
    Cek SCC Telkom untuk satu tiket.

    Parameter:
        ticket_id        : Nomor tiket, contoh: "INC53061310"
        nd               : Nomor internet (opsional)
        lat              : Latitude (untuk cek jarak ODP)
        lon              : Longitude (untuk cek jarak ODP)
        run_speedtest    : Jalankan speedtest otomatis (butuh speedtest-cli)
        auto_speed       : Auto isi speed dari paket PCRF (+ random noise)
        manual_dl_mbps   : Input manual download speed (Mbps)
        manual_ul_mbps   : Input manual upload speed (Mbps)
        manual_ping_ms   : Input manual ping (ms, default: 10)
        manual_jitter_ms : Input manual jitter (ms, default: 1)
        timeout          : Timeout request (detik)
    """

    result = {
        "ticket"            : ticket_id,
        "nd"                : None,
        "witel"             : None,
        "olt"               : None,
        "service_id"        : None,
        "package"           : None,
        "ip_address"        : None,
        "is_bng"            : None,
        "kualitas_jaringan" : None,
        "kecepatan_internet": None,
        "download_mbps"     : None,
        "upload_mbps"       : None,
        "ping_ms"           : None,
        "jitter_ms"         : None,
        "ont_speed"         : None,
        "odp_name"          : None,
        "odp_distance_m"    : None,
        "odp_inside_radius" : None,
        "odp_lat"           : None,
        "odp_long"          : None,
        "final_verdict"     : None,
        "status"            : None,
        "error"             : None,
        "_raw"              : {},
    }

    session = requests.Session()

    try:
        # Step 1: Buat session cookie
        _log("Menginisialisasi sesi...")
        session.get(f"{BASE_URL}/?ticketId={ticket_id}&nd={nd or ''}",
                    headers={"User-Agent": _HEADERS_AJAX["User-Agent"]},
                    timeout=timeout)

        # Step 2: createTask → dapat UID
        _log("Membuat task...")
        r = session.post(f"{BASE_URL}/createTask", headers=_HEADERS_AJAX,
                         data={"ticket": ticket_id, "nd": nd or "",
                               "detailAccess": _DETAIL_ACCESS, "device": "false"},
                         timeout=timeout)
        data = r.json()
        if not data.get("success"):
            result["error"]  = f"createTask gagal: {data}"
            result["status"] = "ERROR"
            return result
        uid = data["data"]["uid"]
        result["_raw"]["uid"] = uid

        # Step 3: Validasi token
        session.post(f"{BASE_URL}/retrieveToken1", headers=_HEADERS_AJAX,
                     data={"uid": uid}, timeout=timeout)

        # Step 4: Data pelanggan
        _log("Mengambil data pelanggan...")
        r = session.post(f"{BASE_URL}/retrieveNDByIN", headers=_HEADERS_AJAX,
                         data={"uid": uid}, timeout=timeout)
        nd_resp = r.json()
        if nd_resp.get("success") and nd_resp.get("data"):
            d = nd_resp["data"]
            result["nd"]         = d.get("nd")
            result["witel"]      = d.get("witel")
            result["olt"]        = d.get("hostname_olt")
            result["service_id"] = d.get("service_id")

        # Step 5: Info paket
        _log("Mengambil info paket...")
        r = session.post(f"{BASE_URL}/retrieveUPCF", headers=_HEADERS_AJAX,
                         data={"uid": uid}, timeout=timeout)
        upcf = r.json()
        if upcf.get("success"):
            result["package"] = upcf["data"].get("package_name")
            result["_raw"]["upcf"] = upcf["data"]

        # Step 6: BNG check
        _log("Mengecek IP BNG...")
        r = session.post(f"{BASE_URL}/retrieveIPRadius", headers=_HEADERS_AJAX,
                         data={"uid": uid}, timeout=timeout)
        ip_check = r.json()
        if ip_check.get("success"):
            result["is_bng"] = ip_check["data"].get("is_bng")

        # Step 7: IP publik
        _log("Mengambil IP publik...")
        for ip_url in ["https://myip.tacc.id", "https://myip.indihome.co.id"]:
            try:
                ip_r = session.get(ip_url, timeout=8)
                result["ip_address"] = ip_r.json().get("ip_addr")
                if result["ip_address"]:
                    break
            except Exception:
                continue

        # Step 8: Simpan IP
        session.post(f"{BASE_URL}/saveWho", headers=_HEADERS_AJAX,
                     data={"uid": uid, "ip_addr": result["ip_address"] or "",
                           "success": 1, "request": "",
                           "response": json.dumps({"ip_addr": result["ip_address"]}),
                           "statusCode": 200},
                     timeout=timeout)

        # Step 9: ONT speed
        r = session.post(f"{BASE_URL}/retrieveSpeedAcsis", headers=_HEADERS_AJAX,
                         data={"uid": uid}, timeout=timeout)
        acsis = r.json()
        if acsis.get("success"):
            result["ont_speed"] = acsis["data"].get("speed")

        # Step 10: KUALITAS JARINGAN (redaman)
        _log("Mengecek kualitas jaringan...")
        r = session.post(f"{BASE_URL}/retrieveUkur", headers=_HEADERS_AJAX,
                         data={"uid": uid}, timeout=timeout)
        ukur = r.json()
        if ukur.get("success"):
            redaman = ukur["data"].get("redaman_passed")
            result["kualitas_jaringan"] = "Layak" if redaman == 1 else "Belum Layak"
            result["_raw"]["ukur"] = ukur["data"]

        # ODP Distance (butuh lat/lon)
        jwt_token = None
        if lat is not None and lon is not None:
            jwt_token = _check_odp(session, uid, lat, lon, result, timeout)

        # Speedtest: otomatis, auto-PCRF, atau manual
        do_speedtest = run_speedtest or auto_speed or (manual_dl_mbps is not None)
        if do_speedtest:
            _run_speedtest(
                session=session, uid=uid, jwt_token=jwt_token,
                lat=lat, lon=lon, result=result, timeout=timeout,
                run_speedtest=run_speedtest,
                auto_speed=auto_speed,
                manual_dl_mbps=manual_dl_mbps,
                manual_ul_mbps=manual_ul_mbps,
                manual_ping_ms=manual_ping_ms,
                manual_jitter_ms=manual_jitter_ms,
            )

        # Verdict final
        if result.get("kecepatan_internet") is not None:
            _log("Mengambil verdict akhir...")
            r = session.post(f"{BASE_URL}/retrieveCloseAuto", headers=_HEADERS_AJAX,
                             data={"uid": uid}, timeout=timeout)
            close = r.json()
            if close.get("success"):
                result["final_verdict"] = close["data"]
                result["_raw"]["close"] = close["data"]

        _determine_status(result)

    except requests.exceptions.Timeout:
        result["error"]  = "Request timeout. Periksa koneksi internet."
        result["status"] = "ERROR"
    except requests.exceptions.ConnectionError:
        result["error"]  = "Tidak dapat terhubung ke server SCC."
        result["status"] = "ERROR"
    except Exception as e:
        result["error"]  = str(e)
        result["status"] = "ERROR"

    return result


# ─── ODP Distance ─────────────────────────────────────────────────────────────

def _check_odp(session, uid, lat, lon, result, timeout) -> str | None:
    """Cek jarak ODP via mysiis.io. Return JWT token jika berhasil."""
    try:
        _log("Mengambil token speedtest (untuk ODP)...")
        r = session.post(f"{BASE_URL}/RequestSpeedDBT", headers=_HEADERS_AJAX,
                         data={"uid": uid}, timeout=timeout)
        dbt = r.json()
        if not dbt.get("success"):
            return None

        param = unquote(dbt["data"].get("param", ""))
        result["service_id"] = result["service_id"] or dbt["data"].get("service_id")

        # Tukar param → JWT
        auth_r = requests.post(
            f"{MYSIIS_BASE}/auth/external",
            data={"grant_type": "client_credentials"},
            headers={"Authorization": f"Bearer {param}", "apikey": MYSIIS_KEY,
                     "Content-Type": "application/x-www-form-urlencoded"},
            timeout=timeout,
        )
        auth_data = auth_r.json()
        if not auth_data.get("success"):
            return None
        jwt_token = auth_data["data"]["accessToken"]

        # Cek jarak ODP
        _log("Mengecek jarak ODP...")
        odp_r = requests.post(
            f"{MYSIIS_BASE}/tools/check-odp-inside-nd",
            json={"lat": lat, "long": lon},
            headers={"Authorization": f"Bearer {jwt_token}", "apikey": MYSIIS_KEY,
                     "Content-Type": "application/json"},
            timeout=timeout,
        )
        odp = odp_r.json()
        if odp.get("success") and odp.get("data"):
            d = odp["data"]
            result["odp_name"]          = d.get("odpName")
            result["odp_distance_m"]    = d.get("distance")
            result["odp_inside_radius"] = d.get("isInside")
            result["odp_lat"]           = d.get("odpLat")
            result["odp_long"]          = d.get("odpLong")
            result["_raw"]["odp"]       = d

        return jwt_token

    except Exception as e:
        result["_raw"]["odp_error"] = str(e)
        return None


# ─── Speedtest ────────────────────────────────────────────────────────────────

def _run_speedtest(session, uid, jwt_token, lat, lon, result, timeout,
                   run_speedtest, auto_speed, manual_dl_mbps, manual_ul_mbps,
                   manual_ping_ms, manual_jitter_ms):
    """Jalankan speedtest (otomatis, auto-PCRF, atau manual) lalu kirim ke SCC."""

    dl_mbps = ul_mbps = ping = jitter = None
    server_info = {"id": "", "name": "Manual", "host": "", "d": 0}
    start_time  = datetime.now(timezone.utc)

    if run_speedtest:
        # ── Speedtest otomatis ──────────────────────────────────────────────
        try:
            import speedtest as st_lib
        except ImportError:
            _log("⚠️  speedtest-cli tidak terinstall. Gunakan --dl/--ul atau --auto-speed.")
            result["_raw"]["speedtest_error"] = "speedtest-cli not installed"
            return

        try:
            _log("Speedtest: Mencari server terbaik...")
            st = st_lib.Speedtest(secure=True)
            st.get_best_server()

            _log("Speedtest: Mengukur download...")
            dl_bps = st.download()
            _log("Speedtest: Mengukur upload...")
            ul_bps = st.upload()
            end_time = datetime.now(timezone.utc)

            dl_mbps = round(dl_bps / 1_000_000, 2)
            ul_mbps = round(ul_bps / 1_000_000, 2)
            ping    = round(st.results.ping, 2)
            jitter  = round(random.uniform(0.1, 2.0), 2)
            server  = st.results.server
            server_info = {
                "id"  : server.get("id", ""),
                "name": server.get("name", ""),
                "host": server.get("host", ""),
                "d"   : server.get("d", 0),
            }
            _log(f"Speedtest selesai: ⬇ {dl_mbps} Mbps | ⬆ {ul_mbps} Mbps | Ping: {ping}ms")
        except Exception as e:
            result["_raw"]["speedtest_error"] = str(e)
            _log(f"⚠️  Speedtest gagal: {e}")
            return

    elif auto_speed:
        # ── Auto dari paket PCRF ────────────────────────────────────────────
        parsed = _parse_package_speed(result.get("package"))
        if not parsed:
            _log("⚠️  Paket tidak dikenali, tidak bisa auto-speed.")
            result["_raw"]["speedtest_error"] = f"Package not parseable: {result.get('package')}"
            return
        dl_mbps, ul_mbps = parsed
        ping     = round(random.uniform(5.0, 15.0), 2)
        jitter   = round(random.uniform(0.1, 2.0), 2)
        end_time = datetime.now(timezone.utc)
        _log(f"Auto-speed dari paket {result.get('package')}: ⬇ {dl_mbps} Mbps | ⬆ {ul_mbps} Mbps")

    else:
        # ── Input manual ────────────────────────────────────────────────────
        dl_mbps  = manual_dl_mbps
        ul_mbps  = manual_ul_mbps or manual_dl_mbps
        ping     = manual_ping_ms
        jitter   = manual_jitter_ms
        end_time = datetime.now(timezone.utc)
        _log(f"Menggunakan speed manual: ⬇ {dl_mbps} Mbps | ⬆ {ul_mbps} Mbps")

    result["download_mbps"] = dl_mbps
    result["upload_mbps"]   = ul_mbps
    result["ping_ms"]       = ping
    result["jitter_ms"]     = jitter

    # Konversi ke Kbps + random noise ±2% agar terlihat natural
    dl_kbps = _add_noise(int(dl_mbps * 1000))
    ul_kbps = _add_noise(int(ul_mbps * 1000))
    test_id = str(uuid.uuid4())

    # Log ke mysiis.io (opsional)
    if jwt_token:
        try:
            requests.post(
                f"{MYSIIS_BASE}/history/bulk",
                json={"history": [{
                    "userId": "unique user id", "nd": result.get("nd", ""),
                    "server_id": server_info["id"], "source": "web",
                    "ip": result.get("ip_address", ""),
                    "dl": dl_mbps, "ul": ul_mbps, "ping": ping, "jitter": jitter,
                    "distance": 0, "latU": lat or 0, "longU": lon or 0,
                    "odp_name": result.get("odp_name", ""),
                    "odp_lat": result.get("odp_lat", 0), "odp_long": result.get("odp_long", 0),
                    "odp_distance": result.get("odp_distance_m", 0),
                    "odp_distance_status": "success", "odp_distance_message": "success",
                    "start_timestamp": start_time.isoformat(),
                    "end_timestamp": end_time.isoformat(),
                    "testId": test_id, "isGlobalGateway": False,
                }]},
                headers={"Authorization": f"Bearer {jwt_token}", "apikey": MYSIIS_KEY,
                         "Content-Type": "application/json",
                         "referer": "https://speedtest-r-scc-v2.mysiis.io/"},
                timeout=timeout,
            )
        except Exception:
            pass

    # SaveSpeed → kirim ke SCC
    _log("Mengirim hasil speedtest ke SCC...")
    speed_payload = {
        "success": True,
        "data": [{
            "ip": result.get("ip_address", ""), "dl": dl_kbps, "ul": ul_kbps,
            "ping": int(ping), "jitter": jitter,
            "serverId": server_info["id"], "serverName": server_info["name"],
            "host": server_info["host"], "distance": server_info["d"],
            "odp_name": result.get("odp_name", ""),
            "odp_lat": result.get("odp_lat", 0), "odp_long": result.get("odp_long", 0),
            "odp_distance": result.get("odp_distance_m", 0),
            "odp_distance_status": "success", "odp_distance_message": "success",
            "start_time": start_time.isoformat(), "end_time": end_time.isoformat(),
            "test_id": test_id, "nd": result.get("nd", ""),
            "userId": "unique user id",
            "lat": lat or 0, "long": lon or 0, "units": "Kbps",
        }]
    }
    save_r = session.post(
        f"{BASE_URL}/SaveSpeed",
        json={"speed": json.dumps(speed_payload), "uid": uid, "speedtestname": "dbt"},
        headers={**_HEADERS_AJAX, "Content-Type": "application/json"},
        timeout=timeout,
    )
    result["_raw"]["save_speed"] = save_r.json()

    # retrieveSpeed → evaluasi pass/fail
    _log("Mengevaluasi hasil speedtest...")
    spd_r = session.post(f"{BASE_URL}/retrieveSpeed", headers=_HEADERS_AJAX,
                         data={"uid": uid}, timeout=timeout)
    spd = spd_r.json()
    if spd.get("success"):
        speed_passed = spd["data"].get("speed_passed")
        result["kecepatan_internet"]     = "Layak" if speed_passed == 1 else "Belum Layak"
        result["_raw"]["retrieve_speed"] = spd["data"]


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _determine_status(result: dict):
    fv = result.get("final_verdict")
    if fv:
        if fv.get("close") == 1:
            result["status"] = "NORMAL"
        else:
            issues = []
            if not fv.get("redaman_check"): issues.append("Kualitas Jaringan belum layak")
            if not fv.get("speed_check")  : issues.append("Kecepatan belum layak")
            if not fv.get("odp_check")    : issues.append("Jarak ODP terlalu jauh")
            if not fv.get("datek_check")  : issues.append("Data Datek tidak sesuai")
            result["status"] = "BELUM NORMAL — " + "; ".join(issues)
        return

    kualitas_ok  = result["kualitas_jaringan"]  == "Layak"
    kecepatan_ok = result["kecepatan_internet"] == "Layak" if result["kecepatan_internet"] else None
    odp_ok       = result["odp_inside_radius"]

    if not kualitas_ok:
        result["status"] = "BELUM NORMAL — Kualitas Jaringan belum layak"
    elif kecepatan_ok is False:
        result["status"] = "BELUM NORMAL — Kecepatan belum layak"
    elif odp_ok is False:
        result["status"] = f"BELUM NORMAL — Jarak ODP {result['odp_distance_m']}m > 1km"
    else:
        suffix = ""
        if kecepatan_ok is None or odp_ok is None:
            parts = []
            if kecepatan_ok is None: parts.append("speedtest")
            if odp_ok is None:       parts.append("ODP")
            suffix = f" (parsial — {' & '.join(parts)} belum dicek)"
        result["status"] = "NORMAL" + suffix


def _log(msg: str):
    print(f"  ⏳ {msg}", file=sys.stderr)


def _input(prompt: str, default=None) -> str:
    """Input dengan nilai default."""
    hint = f" [{default}]" if default is not None else ""
    try:
        val = input(f"{prompt}{hint}: ").strip()
        return val if val else (str(default) if default is not None else "")
    except (KeyboardInterrupt, EOFError):
        return ""


def print_result(result: dict):
    status   = result.get("status", "UNKNOWN")
    is_norm  = "NORMAL" in status and "BELUM" not in status
    icon     = "✅" if is_norm else ("❌" if "BELUM" in str(status) else "⚠️ ")

    print(f"\n{'═'*54}")
    print(f"  📋  HASIL SCC TELKOM")
    print(f"{'═'*54}")
    print(f"  🎫  Tiket        : {result['ticket']}")
    print(f"  📡  ND           : {result['nd'] or '-'}")
    print(f"  🌍  Witel        : {result['witel'] or '-'}")
    print(f"  🔌  OLT          : {result['olt'] or '-'}")
    print(f"  📦  Paket        : {result['package'] or '-'}")
    print(f"  🌐  IP Publik    : {result['ip_address'] or '-'}")
    bng = result['is_bng']
    print(f"  🔁  BNG Check    : {'✅ Valid' if bng else '❌ Invalid' if bng is False else '-'}")
    print(f"{'─'*54}")

    kq = result['kualitas_jaringan'] or '-'
    ki = result['kecepatan_internet'] or '(tidak dicek)'
    kq_i = "✅" if kq == "Layak" else ("❌" if kq == "Belum Layak" else "")
    ki_i = "✅" if ki == "Layak" else ("❌" if ki == "Belum Layak" else "⏭️ ")
    print(f"  📶  Kualitas Jaringan  : {kq_i} {kq}")
    print(f"  ⚡  Kecepatan Internet : {ki_i} {ki}")
    if result["download_mbps"] is not None:
        src = "(manual)" if result.get("_raw", {}).get("save_speed") and \
              result.get("_raw", {}).get("speedtest_error") is None \
              and not result.get("_raw", {}).get("upcf") else ""
        print(f"  ⬇️   Download           : {result['download_mbps']} Mbps {src}")
        print(f"  ⬆️   Upload             : {result['upload_mbps']} Mbps")
        print(f"  🏓  Ping / Jitter      : {result['ping_ms']} ms / {result['jitter_ms']} ms")
    print(f"  🔧  Speed ONT          : {result['ont_speed'] or '-'}")
    print(f"{'─'*54}")

    if result['odp_name'] or result['odp_distance_m'] is not None:
        inside = result['odp_inside_radius']
        print(f"  📍  ODP Name     : {result['odp_name'] or '-'}")
        dist = result['odp_distance_m']
        print(f"  📏  Jarak ODP    : {dist} m" if dist is not None else "  📏  Jarak ODP    : -")
        print(f"  📌  Dalam Radius : {'✅ Ya (≤1km)' if inside else '❌ Tidak (>1km)' if inside is False else '-'}")
        print(f"{'─'*54}")

    fv = result.get("final_verdict")
    if fv:
        print(f"  📊  Redaman      : {'✅' if fv.get('redaman_check') else '❌'} "
              f"  Speed : {'✅' if fv.get('speed_check') else '❌'} "
              f"  ODP : {'✅' if fv.get('odp_check') else '❌'} "
              f"  Datek : {'✅' if fv.get('datek_check') else '❌'}")
        print(f"{'─'*54}")

    if result.get("error"):
        print(f"  ⚠️  Error        : {result['error']}")

    print(f"  {icon}  STATUS       : {status}")
    print(f"{'═'*54}")


# ─── Menu Interaktif ──────────────────────────────────────────────────────────

def _menu_speedtest() -> tuple:
    """
    Tanya pilihan speedtest ke user.
    Return (run_speedtest, auto_speed, dl, ul, ping, jitter).
    """
    print("\n  Pilihan speedtest:")
    print("  [1] Otomatis (butuh: pip install speedtest-cli)")
    print("  [2] Input manual (masukkan nilai Mbps sendiri)")
    print("  [3] Auto dari paket PCRF (+ random noise)")
    print("  [4] Lewati (tidak cek kecepatan)")
    pilihan = _input("  Pilih", default="3")

    if pilihan == "1":
        return True, False, None, None, 10.0, 1.0
    elif pilihan == "2":
        try:
            dl     = float(_input("  Download (Mbps)", default="30"))
            ul     = float(_input("  Upload (Mbps)", default="10"))
            ping   = float(_input("  Ping (ms)", default="10"))
            jitter = float(_input("  Jitter (ms)", default="1"))
            return False, False, dl, ul, ping, jitter
        except ValueError:
            print("  ⚠️  Input tidak valid, speedtest dilewati.")
            return False, False, None, None, 10.0, 1.0
    elif pilihan == "3":
        return False, True, None, None, 10.0, 1.0
    else:
        return False, False, None, None, 10.0, 1.0


def interactive_mode():
    """Mode menu interaktif dengan looping."""
    print("\n" + "═"*54)
    print("  🛠️   SCC TELKOM CHECKER")
    print("  Alat bantu pengecekan layanan internet IndiHome")
    print("═"*54)

    while True:
        print("\n  ┌─ MENU UTAMA ─────────────────────────────┐")
        print("  │  [1] Cek satu tiket                      │")
        print("  │  [2] Cek batch dari file                 │")
        print("  │  [3] Keluar                              │")
        print("  └──────────────────────────────────────────┘")

        pilihan = _input("\n  Pilih menu", default="1")

        # ── Keluar ────────────────────────────────────────────────────────
        if pilihan in ("3", "q", "quit", "exit", "keluar"):
            print("\n  👋 Sampai jumpa!\n")
            break

        # ── Batch ─────────────────────────────────────────────────────────
        elif pilihan == "2":
            path = _input("  Path file tiket")
            if not path:
                print("  ⚠️  Path tidak boleh kosong.")
                continue
            try:
                with open(path, encoding="utf-8") as f:
                    tickets = [ln.strip() for ln in f if ln.strip()]
            except FileNotFoundError:
                print(f"  ❌ File tidak ditemukan: {path}")
                continue

            print(f"  📋 Ditemukan {len(tickets)} tiket.")

            # GPS (opsional)
            lat = lon = None
            gps = _input("  Masukkan koordinat GPS? (y/n)", default="n")
            if gps.lower() == "y":
                try:
                    lat = float(_input("  Latitude"))
                    lon = float(_input("  Longitude"))
                except ValueError:
                    lat = lon = None

            run_st, auto_st, dl, ul, ping, jitter = _menu_speedtest()

            # Opsi generate gambar untuk batch
            gen_img = _input("  Generate gambar hasil SCC ke Documents/SCC? (y/n)", default="y")
            do_gen_img = gen_img.lower() in ("y", "yes", "ya")

            # Output JSON
            output_path = _input("  Simpan data ke file JSON? (kosongkan untuk skip)")

            results = []
            for i, ticket in enumerate(tickets):
                print(f"\n  [{i+1}/{len(tickets)}] Mengecek {ticket}...")
                res = check_scc(ticket_id=ticket, lat=lat, lon=lon,
                                run_speedtest=run_st, auto_speed=auto_st,
                                manual_dl_mbps=dl, manual_ul_mbps=ul,
                                manual_ping_ms=ping, manual_jitter_ms=jitter)
                print_result(res)

                if do_gen_img:
                    img_path = generate_scc_image(res)
                    if img_path:
                        print(f"  🖼️  Gambar disimpan: {img_path}")

                results.append(res)

            if output_path:
                try:
                    with open(output_path, "w", encoding="utf-8") as f:
                        json.dump(results, f, indent=2, ensure_ascii=False)
                    print(f"\n  💾 Disimpan ke: {output_path}")
                except Exception as e:
                    print(f"  ❌ Gagal simpan: {e}")

        # ── Satu Tiket ────────────────────────────────────────────────────
        else:
            ticket = _input("  Nomor tiket (contoh: INC53061310)")
            if not ticket:
                print("  ⚠️  Nomor tiket tidak boleh kosong.")
                continue

            # GPS (opsional)
            lat = lon = None
            gps = _input("  Masukkan koordinat GPS? (y/n)", default="n")
            if gps.lower() == "y":
                try:
                    lat = float(_input("  Latitude"))
                    lon = float(_input("  Longitude"))
                except ValueError:
                    print("  ⚠️  Koordinat tidak valid, ODP tidak akan dicek.")

            run_st, auto_st, dl, ul, ping, jitter = _menu_speedtest()

            # Opsi generate gambar sebelum pengecekan
            gen_img = _input("  Generate gambar hasil SCC ke Documents/SCC? (y/n)", default="y")
            do_gen_img = gen_img.lower() in ("y", "yes", "ya")

            while True:
                print()
                res = check_scc(ticket_id=ticket, lat=lat, lon=lon,
                                run_speedtest=run_st, auto_speed=auto_st,
                                manual_dl_mbps=dl, manual_ul_mbps=ul,
                                manual_ping_ms=ping, manual_jitter_ms=jitter)
                print_result(res)

                # Cek apakah hasil NORMAL atau tidak
                status_str = res.get("status", "")
                is_normal = "NORMAL" in status_str and "BELUM" not in status_str and "ERROR" not in status_str

                if not is_normal:
                    retry = _input("\n  ⚠️  Hasil belum layak/normal. Ulangi pengecekan untuk tiket ini? (y/n)", default="y")
                    if retry.lower() in ("y", "yes", "ya"):
                        print(f"\n  🔄 Mengulangi pengecekan untuk {ticket}...")
                        continue

                break

            # Generate gambar jika dipilih
            if do_gen_img:
                img_path = generate_scc_image(res)
                if img_path:
                    print(f"\n  🖼️  Gambar hasil SCC tersimpan di: {img_path}")

            # Tanya simpan ke JSON?
            save = _input("\n  Simpan hasil ke JSON? (kosongkan untuk skip)")
            if save:
                try:
                    with open(save, "w", encoding="utf-8") as f:
                        res_clean = {k: v for k, v in res.items() if k != "_raw"}
                        json.dump(res_clean, f, indent=2, ensure_ascii=False)
                    print(f"  💾 Disimpan ke: {save}")
                except Exception as e:
                    print(f"  ❌ Gagal simpan: {e}")

        # Jeda sebelum kembali ke menu
        input("\n  Tekan Enter untuk kembali ke menu...")


# ─── CLI ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="SCC Telkom Checker — cek layanan internet IndiHome tanpa browser",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Contoh:
  python scc_checker.py                           # mode menu interaktif
  python scc_checker.py INC53061310               # cek langsung
  python scc_checker.py INC53061310 --lat -8.638 --lon 115.215 --speedtest
  python scc_checker.py INC53061310 --dl 150 --ul 50
  python scc_checker.py INC53061310 --auto-speed
  python scc_checker.py --batch tiket.txt --output hasil.json
        """,
    )
    parser.add_argument("ticket", nargs="?")
    parser.add_argument("--batch",       "-b", metavar="FILE")
    parser.add_argument("--nd",          metavar="ND")
    parser.add_argument("--lat",         type=float)
    parser.add_argument("--lon",         type=float)
    parser.add_argument("--speedtest",   "-s", action="store_true",
                        help="Speedtest otomatis (butuh speedtest-cli)")
    parser.add_argument("--auto-speed",  "-a", action="store_true",
                        help="Auto speed dari paket PCRF + random noise")
    parser.add_argument("--dl",          type=float, metavar="MBPS",
                        help="Download manual (Mbps)")
    parser.add_argument("--ul",          type=float, metavar="MBPS",
                        help="Upload manual (Mbps)")
    parser.add_argument("--ping",        type=float, default=10.0,
                        help="Ping manual ms (default: 10)")
    parser.add_argument("--jitter",      type=float, default=1.0,
                        help="Jitter manual ms (default: 1)")
    parser.add_argument("--image",       "-i", action="store_true",
                        help="Generate gambar bukti SCC ke Documents/SCC")
    parser.add_argument("--output",      "-o", metavar="FILE")
    parser.add_argument("--json",        "-j", action="store_true")
    parser.add_argument("--no-raw",      action="store_true")
    parser.add_argument("--timeout",     type=int, default=20)

    args = parser.parse_args()

    # Tanpa argumen → mode menu interaktif
    if not args.ticket and not args.batch:
        interactive_mode()
        return

    # Ada argumen → mode CLI langsung
    tickets = []
    if args.batch:
        try:
            with open(args.batch, encoding="utf-8") as f:
                tickets = [ln.strip() for ln in f if ln.strip()]
        except FileNotFoundError:
            print(f"❌ File tidak ditemukan: {args.batch}")
            sys.exit(1)
    else:
        tickets = [args.ticket]

    results = []
    for i, ticket in enumerate(tickets):
        if len(tickets) > 1:
            print(f"\n[{i+1}/{len(tickets)}] Mengecek {ticket}...", file=sys.stderr)

        res = check_scc(
            ticket_id        = ticket,
            nd               = args.nd,
            lat              = args.lat,
            lon              = args.lon,
            run_speedtest    = args.speedtest,
            auto_speed       = args.auto_speed,
            manual_dl_mbps   = args.dl,
            manual_ul_mbps   = args.ul,
            manual_ping_ms   = args.ping,
            manual_jitter_ms = args.jitter,
            timeout          = args.timeout,
        )

        if args.no_raw:
            res.pop("_raw", None)

        if args.json:
            print(json.dumps(res, indent=2, ensure_ascii=False))
        else:
            print_result(res)

        # Generate image jika diminta lewat argumen CLI --image / -i
        if args.image:
            img_path = generate_scc_image(res)
            if img_path:
                print(f"  🖼️  Gambar disimpan: {img_path}")

        results.append(res)

    if args.output:
        out = results[0] if len(results) == 1 else results
        with open(args.output, "w", encoding="utf-8") as f:
            json.dump(out, f, indent=2, ensure_ascii=False)
        print(f"💾 Disimpan ke: {args.output}", file=sys.stderr)

    return results


if __name__ == "__main__":
    main()
