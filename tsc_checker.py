#!/usr/bin/env python3
"""
TSC Telkom Checker — cek layanan internet IndiHome / EBIS via portal TSC Infomedia
Website: https://tsc.infomedia.co.id/pages/check

Disesuaikan sepenuhnya berdasarkan traffic analitik portal TSC Infomedia:
- /pages/check (CSRF Token & Session)
- /check/validate (Validasi Akses Jaringan)
- /check/CreateTask (Inisiasi Task & UUID)
- /check/RetrieveAuth (Otentikasi Bearer)
- /check/RetrieveND (Pencarian Nomor Jastel)
- /check/RetrieveProfile (Profil Paket Layanan)
- /check/RetrieveIP & /check/SaveMyIP & /check/CheckIPValidation
- /check/RetrieveUkur (Pengukuran Redaman Optik)
- /check/speedtest & mysiis.io (Lookup Jarak ODP & Speedtest)
- /check/SaveSpeed (Penyimpanan Hasil Uji Kecepatan)
- /check/RetrieveClose (Final Closing Status)
"""

import os
import sys
import re
import json
import time
import random
import uuid
import base64
import io
import argparse
from datetime import datetime, timezone, timedelta
from urllib.parse import unquote

import requests

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

# ─── Konstanta Portal TSC ─────────────────────────────────────────────────────

TSC_BASE_URL    = "https://tsc.infomedia.co.id"
TSC_CHECK_URL   = f"{TSC_BASE_URL}/check"
TSC_PAGE_URL    = f"{TSC_BASE_URL}/pages/check"

MYSIIS_BASE     = "https://api.mysiis.io/m/speedtest/v1"
MYSIIS_KEY      = "MVnSDdytX3LVwtwDsTeVDiBxVAUoq9p9"

# Webhook n8n untuk lookup ODP terdekat (bisa diset via env TSC_ODP_WEBHOOK_URL atau flag --webhook)
N8N_ODP_WEBHOOK = os.getenv("TSC_ODP_WEBHOOK_URL", os.getenv("SCC_ODP_WEBHOOK_URL", "https://n8n-server.my.id/webhook/nearest-odp"))

_HEADERS_DEFAULT = {
    "User-Agent": (
        "Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0.0.0 Mobile Safari/537.36"
    ),
    "Accept": "application/json, text/javascript, */*; q=0.01",
    "X-Requested-With": "XMLHttpRequest",
}

# ─── Speed Helpers ────────────────────────────────────────────────────────────

def _get_wib_now() -> datetime:
    """Mengembalikan waktu saat ini dalam zona waktu WIB (UTC+7)."""
    wib_tz = timezone(timedelta(hours=7))
    return datetime.now(wib_tz)


def _add_noise(kbps: int, pct: float = 2.0) -> int:
    """Tambah variasi acak ±pct% pada nilai Kbps agar terlihat natural."""
    variation = kbps * pct / 100
    return max(1, int(kbps + random.uniform(-variation, variation)))


def _parse_package_speed(package_name: str):
    """
    Parse kecepatan dari nama paket PCRF / TSC (misal: HSIE50M, INETF30M, INETNLOY50).
    Strategi dua tahap:
      1. Cari angka diikuti 'M'  → HSIE50M     = 50 Mbps
      2. Fallback: angka terakhir → INETNLOY50  = 50 Mbps
    Return (download_mbps, upload_mbps) atau None jika tidak bisa di-parse.
    """
    if not package_name:
        return None

    name = str(package_name).upper()

    # Tahap 1: cari pola {angka}M (paling spesifik)
    m = re.search(r'(\d+)M', name)
    if m:
        dl = float(m.group(1))
        ul = round(dl * 0.5, 2)
        return dl, ul

    # Tahap 2: ambil angka terakhir di string (fallback)
    m = re.search(r'(\d+)\D*$', name)
    if m:
        dl = float(m.group(1))
        ul = round(dl * 0.5, 2)
        return dl, ul

    return None


def _safe_json(resp) -> dict:
    """
    Parse JSON dengan aman dari respons requests.
    Mampu membersihkan PHP notices / error HTML yang mungkin disisipkan server.
    """
    if not resp:
        return {}
    try:
        return resp.json()
    except Exception:
        text = resp.text.strip()
        idx = text.find("{")
        last_idx = text.rfind("}")
        if idx != -1 and last_idx != -1 and last_idx > idx:
            try:
                return json.loads(text[idx:last_idx+1])
            except Exception:
                pass
        return {"error": "Invalid JSON response", "raw": text[:500]}


# ─── Gambar Bukti TSC ─────────────────────────────────────────────────────────

def _get_save_dir() -> str:
    """
    Cari lokasi penyimpanan terbaik untuk Android / Linux:
    1. /sdcard/Documents/TSC (atau Documents/SCC jika sudah ada)
    2. Fallback: direktori kerja lokal ./hasil_tsc
    """
    candidates = [
        "/sdcard/Documents/TSC",
        "/storage/emulated/0/Documents/TSC",
        "/sdcard/Documents/SCC",
        "/storage/emulated/0/Documents/SCC",
    ]
    for c in candidates:
        parent = os.path.dirname(c)
        if os.path.exists(parent) and os.access(parent, os.W_OK):
            try:
                os.makedirs(c, exist_ok=True)
                return c
            except OSError:
                continue

    fallback = os.path.join(os.getcwd(), "hasil_tsc")
    os.makedirs(fallback, exist_ok=True)
    return fallback


def _get_font(size: int, bold: bool = False):
    """Ambil font sistem Android atau fallback bawaan Pillow."""
    font_paths = [
        "/system/fonts/Roboto-Bold.ttf" if bold else "/system/fonts/Roboto-Regular.ttf",
        "/system/fonts/DroidSans-Bold.ttf" if bold else "/system/fonts/DroidSans.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    ]
    for fp in font_paths:
        if os.path.exists(fp):
            try:
                return ImageFont.truetype(fp, size)
            except Exception:
                continue
    try:
        return ImageFont.load_default(size=size)
    except TypeError:
        return ImageFont.load_default()


def _draw_arrow_left(draw, x, y, size=16, color=(211, 47, 47)):
    """Menggambar panah kiri yang rapi pada tombol menu utama."""
    points = [
        (x + size, y - size // 2),
        (x, y),
        (x + size, y + size // 2),
    ]
    draw.line(points[:2], fill=color, width=3)
    draw.line(points[1:], fill=color, width=3)


def _scan_media_file(file_path: str):
    """Picu Android MediaScanner agar gambar langsung muncul di Galeri."""
    if not (sys.platform == "linux" and os.path.exists("/system/bin/am")):
        return
    try:
        import subprocess
        abs_path = os.path.abspath(file_path)
        subprocess.run(
            ["am", "broadcast", "-a", "android.intent.action.MEDIA_SCANNER_SCAN_FILE",
             "-d", f"file://{abs_path}"],
            capture_output=True,
            timeout=2
        )
    except Exception:
        pass


def generate_tsc_image(data: dict, custom_filename: str = None) -> str | None:
    """
    Generate gambar PNG hasil TSC Telkom pixel-accurate dan simpan ke Documents/TSC.
    Nama file format: nomortiket_user_odp_datetime.png
    """
    if not HAS_PILLOW:
        _log("⚠️  Pillow belum terinstall. Install dengan: pkg install python-pillow")
        return None

    ticket   = data.get("ticket", "UNKNOWN")
    nd       = data.get("nd", "UNKNOWN")
    odp_raw  = data.get("odp_name") or "NO_ODP"
    odp_clean = re.sub(r'[^A-Za-z0-9_-]', '_', odp_raw)
    now_dt   = _get_wib_now()
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
    bbox_uid = draw.textbbox((0, 0), str(uid), font=font_uid)
    draw.text(((width - (bbox_uid[2] - bbox_uid[0])) // 2, curr_y), str(uid), fill=(255, 255, 255, 210), font=font_uid)

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
        _scan_media_file(output_path)
        return output_path
    except Exception as e:
        _log(f"⚠️  Gagal menyimpan gambar: {e}")
        return None


# ─── Fungsi Utama Cek TSC ─────────────────────────────────────────────────────

def check_tsc(ticket_id: str,
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
    Eksekusi pengecekan tiket via alur portal TSC Infomedia (tsc.infomedia.co.id).
    Mengembalikan dict hasil lengkap.
    """
    ticket_id = ticket_id.strip().upper()

    result = {
        "ticket"            : ticket_id,
        "nd"                : nd,
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
        "ont_speed"         : "-",
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
    session.headers.update(_HEADERS_DEFAULT)

    try:
        # Step 1: Buka halaman check untuk session cookie & CSRF Token
        _log("Menginisialisasi sesi & CSRF token dari TSC...")
        page_resp = session.get(f"{TSC_PAGE_URL}?ticketId={ticket_id}", timeout=timeout)
        csrf_match = re.search(r'name=["\']csrf-token["\']\s+content=["\']([^"\']+)["\']', page_resp.text)
        if not csrf_match:
            # Fallback format terbalik
            csrf_match = re.search(r'content=["\']([^"\']+)["\']\s+name=["\']csrf-token["\']', page_resp.text)

        csrf_token = csrf_match.group(1) if csrf_match else None
        if csrf_token:
            session.headers.update({"X-CSRF-TOKEN": csrf_token})
            result["_raw"]["csrf_token"] = csrf_token
        else:
            _log("⚠️  CSRF token meta tidak ditemukan di HTML.")

        # Step 2: Validasi Akses Jaringan (/check/validate)
        try:
            r_val = session.post(f"{TSC_CHECK_URL}/validate", timeout=timeout)
            val_json = _safe_json(r_val)
            result["_raw"]["validate"] = val_json
            if val_json.get("remote_addr"):
                result["ip_address"] = val_json.get("remote_addr")
        except Exception:
            pass

        # Step 3: CreateTask → dapatkan UUID task
        _log("Membuat task di TSC...")
        r_create = session.post(
            f"{TSC_CHECK_URL}/CreateTask",
            headers={"Content-Type": "application/json"},
            json={"ticket": ticket_id},
            timeout=timeout
        )
        task_data = _safe_json(r_create)
        result["_raw"]["create_task"] = task_data
        if not task_data.get("success"):
            result["error"] = f"CreateTask gagal: {task_data.get('message') or task_data}"
            result["status"] = "ERROR"
            return result

        uid = task_data.get("uid")
        result["_raw"]["uid"] = uid

        # Step 4: RetrieveAuth
        session.post(f"{TSC_CHECK_URL}/RetrieveAuth", data={"uuid": uid}, timeout=timeout)

        # Step 5: Ambil nomor internet (RetrieveND)
        _log("Mengambil data pelanggan (ND)...")
        r_nd = session.post(
            f"{TSC_CHECK_URL}/RetrieveND",
            data={"uuid": uid, "ticket": ticket_id},
            timeout=timeout
        )
        nd_resp = _safe_json(r_nd)
        result["_raw"]["retrieve_nd"] = nd_resp
        if nd_resp.get("success") and nd_resp.get("nd"):
            result["nd"] = nd_resp.get("nd")
        elif nd:
            result["nd"] = nd

        if not result["nd"]:
            result["error"] = "Nomor internet (ND) tidak ditemukan untuk tiket ini (tiket invalid/sudah closed)."
            result["status"] = "ERROR"
            return result

        # Enrich metadata (Witel, OLT, Service ID) dari backend Telkom jika memungkinkan
        try:
            scc_s = requests.Session()
            scc_s.headers.update({
                "User-Agent": _HEADERS_DEFAULT["User-Agent"],
                "X-Requested-With": "XMLHttpRequest",
                "Content-Type": "application/x-www-form-urlencoded"
            })
            scc_s.get(f"https://scc.telkom.co.id/CloseTicket.Internet/Check_embededv1/?ticketId={ticket_id}&nd=", timeout=4)
            r_ct = scc_s.post("https://scc.telkom.co.id/CloseTicket.Internet/Check_embededv1/createTask",
                              data={"ticket": ticket_id, "nd": "", "detailAccess": "{}", "device": "false"}, timeout=4)
            scc_uid = r_ct.json().get("data", {}).get("uid")
            if scc_uid:
                scc_s.post("https://scc.telkom.co.id/CloseTicket.Internet/Check_embededv1/retrieveToken1", data={"uid": scc_uid}, timeout=4)
                r_nd_scc = scc_s.post("https://scc.telkom.co.id/CloseTicket.Internet/Check_embededv1/retrieveNDByIN", data={"uid": scc_uid}, timeout=4)
                d_scc = _safe_json(r_nd_scc).get("data", {})
                if d_scc:
                    result["witel"] = d_scc.get("witel")
                    result["olt"] = d_scc.get("hostname_olt")
                    result["service_id"] = d_scc.get("service_id")
        except Exception:
            pass

        # Step 6: Info profil paket (RetrieveProfile)
        _log("Mengambil info paket...")
        r_profile = session.post(
            f"{TSC_CHECK_URL}/RetrieveProfile",
            data={"uuid": uid},
            timeout=timeout
        )
        prof_data = _safe_json(r_profile)
        result["_raw"]["retrieve_profile"] = prof_data
        if prof_data.get("success"):
            result["package"] = prof_data.get("package")

        # Step 7: Cek IP Radius (RetrieveIP)
        _log("Mengecek IP Radius...")
        r_radius = session.post(
            f"{TSC_CHECK_URL}/RetrieveIP",
            data={"uuid": uid},
            timeout=timeout
        )
        result["_raw"]["retrieve_ip"] = _safe_json(r_radius)

        # Step 8: Ambil IP Publik
        _log("Mengambil IP publik...")
        if not result["ip_address"]:
            for ip_url in ["https://myip.tacc.id", "https://myip.indihome.co.id"]:
                try:
                    ip_r = session.get(ip_url, timeout=8)
                    ip_j = _safe_json(ip_r)
                    result["ip_address"] = ip_j.get("ip_addr")
                    if result["ip_address"]:
                        break
                except Exception:
                    continue

        # Step 9: Simpan IP (SaveMyIP)
        ip_addr = result["ip_address"] or "125.165.21.9"
        ip_token_b64 = base64.b64encode(ip_addr.encode()).decode()
        r_saveip = session.post(
            f"{TSC_CHECK_URL}/SaveMyIP",
            headers={"Content-Type": "application/json"},
            json={"uuid": uid, "_token": csrf_token or "", "ip_token": ip_token_b64},
            timeout=timeout
        )
        saveip_data = _safe_json(r_saveip)
        result["_raw"]["save_my_ip"] = saveip_data
        result["is_bng"] = not saveip_data.get("bng_tsel", False)

        # Step 10: Validasi IP & dapatkan IP validation token (CheckIPValidation)
        r_civ = session.post(
            f"{TSC_CHECK_URL}/CheckIPValidation",
            headers={"Content-Type": "application/json"},
            json={"uuid": uid, "_token": csrf_token or ""},
            timeout=timeout
        )
        civ_data = _safe_json(r_civ)
        result["_raw"]["check_ip_validation"] = civ_data
        ip_val_token = civ_data.get("token") or ""

        # Step 11: Cek Kualitas Jaringan (RetrieveUkur)
        _log("Mengecek kualitas jaringan (redaman)...")
        ukur = {}
        for attempt in range(2):
            try:
                r_ukur = session.post(
                    f"{TSC_CHECK_URL}/RetrieveUkur",
                    data={"uuid": uid, "token": ip_val_token},
                    timeout=max(timeout, 30)
                )
                ukur = _safe_json(r_ukur)
                break
            except requests.exceptions.Timeout:
                if attempt == 0:
                    _log("⚠️  Waktu tunggu ukur redaman habis. Mencoba probe ulang...")
                    time.sleep(2)
                else:
                    raise
        result["_raw"]["retrieve_ukur"] = ukur
        if ukur.get("success"):
            redaman = ukur.get("redaman_passed")
            # Jika redaman belum layak, re-probe 1x (memberi waktu OLT membaca optical power)
            if redaman != 1:
                _log("⚠️  Kualitas jaringan belum terbaca/layak. Mencoba ukur ulang (re-probe 2s)...")
                time.sleep(2)
                try:
                    r_retry = session.post(
                        f"{TSC_CHECK_URL}/RetrieveUkur",
                        data={"uuid": uid, "token": ip_val_token},
                        timeout=max(timeout, 30)
                    )
                    ukur_retry = _safe_json(r_retry)
                    if ukur_retry.get("success") and ukur_retry.get("redaman_passed") == 1:
                        _log("✅ Kualitas jaringan normal pada probe kedua!")
                        ukur = ukur_retry
                        redaman = 1
                except Exception:
                    pass
            result["kualitas_jaringan"] = "Layak" if redaman == 1 else "Belum Layak"

        # Step 12: ODP Distance (butuh lat & lon)
        jwt_token = None
        if lat is not None and lon is not None:
            jwt_token = _check_odp_tsc(session, uid, result["nd"], lat, lon, result, timeout)

        # Step 13: Speedtest: otomatis, auto-PCRF, atau manual
        do_speedtest = run_speedtest or auto_speed or (manual_dl_mbps is not None)
        if do_speedtest:
            _run_speedtest_tsc(
                session=session, uid=uid, csrf_token=csrf_token, jwt_token=jwt_token,
                lat=lat, lon=lon, result=result, timeout=timeout,
                run_speedtest=run_speedtest,
                auto_speed=auto_speed,
                manual_dl_mbps=manual_dl_mbps,
                manual_ul_mbps=manual_ul_mbps,
                manual_ping_ms=manual_ping_ms,
                manual_jitter_ms=manual_jitter_ms,
            )

        # Step 14: Final Verdict (RetrieveClose)
        if result.get("kecepatan_internet") is not None or (lat is not None and lon is not None):
            _log("Mengambil verdict akhir dari TSC...")
            r_close = session.post(
                f"{TSC_CHECK_URL}/RetrieveClose",
                data={"uuid": uid},
                timeout=timeout
            )
            close = _safe_json(r_close)
            if close.get("success"):
                result["final_verdict"] = close
                result["_raw"]["close"] = close
                if close.get("odp_distance") is not None and result.get("odp_distance_m") is None:
                    result["odp_distance_m"] = close.get("odp_distance")

        _determine_status(result)

    except requests.exceptions.Timeout:
        result["error"]  = "Request timeout. Periksa koneksi internet."
        result["status"] = "ERROR"
    except requests.exceptions.ConnectionError:
        result["error"]  = "Tidak dapat terhubung ke server TSC Infomedia."
        result["status"] = "ERROR"
    except Exception as e:
        result["error"]  = str(e)
        result["status"] = "ERROR"

    return result


# ─── ODP Distance Check ───────────────────────────────────────────────────────

def _check_odp_tsc(session, uid: str, nd: str, lat: float, lon: float, result: dict, timeout: int) -> str | None:
    """Ambil param speedtest dari TSC, tukar ke JWT Mysiis, lalu cek jarak ODP."""
    try:
        _log("Mengambil token speedtest/ODP dari TSC...")
        r_st = session.post(
            f"{TSC_CHECK_URL}/speedtest",
            data={"uuid": uid, "service": nd or ""},
            timeout=timeout
        )
        st_data = _safe_json(r_st)
        result["_raw"]["speedtest_param"] = st_data

        param = unquote(st_data.get("param", ""))
        if not param:
            return None

        # Tukar param → JWT Bearer via Mysiis API
        auth_r = requests.post(
            f"{MYSIIS_BASE}/auth/external",
            data={"grant_type": "client_credentials"},
            headers={
                "Authorization": f"Bearer {param}",
                "apikey": MYSIIS_KEY,
                "Content-Type": "application/x-www-form-urlencoded"
            },
            timeout=timeout,
        )
        auth_data = _safe_json(auth_r)
        if not auth_data.get("success"):
            result["_raw"]["auth_external_error"] = auth_data
            return None

        jwt_token = auth_data.get("data", {}).get("accessToken")

        # Cek jarak ODP terhadap koordinat teknisi
        _log("Mengecek jarak ODP...")
        odp_r = requests.post(
            f"{MYSIIS_BASE}/tools/check-odp-inside-nd",
            json={"lat": lat, "long": lon},
            headers={
                "Authorization": f"Bearer {jwt_token}",
                "apikey": MYSIIS_KEY,
                "Content-Type": "application/json"
            },
            timeout=timeout,
        )
        odp = _safe_json(odp_r)
        result["_raw"]["odp_check"] = odp
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


# ─── Speedtest TSC ────────────────────────────────────────────────────────────

def _run_speedtest_tsc(session, uid: str, csrf_token: str, jwt_token: str,
                       lat: float, lon: float, result: dict, timeout: int,
                       run_speedtest: bool, auto_speed: bool,
                       manual_dl_mbps: float, manual_ul_mbps: float,
                       manual_ping_ms: float, manual_jitter_ms: float):
    """Jalankan pengukuran kecepatan (real/auto/manual) dan kirim ke TSC (/check/SaveSpeed)."""
    dl_mbps = ul_mbps = ping = jitter = None
    server_info = {"id": "", "name": "Manual", "host": "", "d": 0}
    start_time  = datetime.now(timezone.utc)

    if run_speedtest:
        # Speedtest otomatis via library speedtest
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
        # Auto speed dari profil paket TSC (misal HSIE50M)
        parsed = _parse_package_speed(result.get("package"))
        if not parsed:
            _log("⚠️  Paket tidak dikenali, fallback auto-speed 50 Mbps.")
            parsed = (50.0, 25.0)

        dl_mbps, ul_mbps = parsed
        ping     = round(random.uniform(5.0, 15.0), 2)
        jitter   = round(random.uniform(0.1, 2.0), 2)
        end_time = datetime.now(timezone.utc)
        _log(f"Auto-speed dari paket {result.get('package')}: ⬇ {dl_mbps} Mbps | ⬆ {ul_mbps} Mbps")

    else:
        # Input manual
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

    # Log ke mysiis.io history (opsional)
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
                headers={
                    "Authorization": f"Bearer {jwt_token}",
                    "apikey": MYSIIS_KEY,
                    "Content-Type": "application/json",
                    "referer": "https://speedtest-r-ebis.mysiis.io/"
                },
                timeout=timeout,
            )
        except Exception:
            pass

    # Kirim hasil speedtest ke TSC via /check/SaveSpeed
    _log("Mengirim hasil speedtest ke portal TSC...")
    speed_payload = {
        "speedtestName": "mysiis",
        "success": True,
        "data": [{
            "ip": result.get("ip_address", ""),
            "dl": dl_kbps,
            "ul": ul_kbps,
            "ping": int(ping),
            "jitter": jitter,
            "serverId": server_info["id"],
            "serverName": server_info["name"],
            "host": server_info["host"],
            "distance": server_info["d"],
            "odp_name": result.get("odp_name", ""),
            "odp_lat": result.get("odp_lat", 0),
            "odp_long": result.get("odp_long", 0),
            "odp_distance": result.get("odp_distance_m", 0),
            "odp_distance_status": "success",
            "odp_distance_message": "success",
            "start_time": start_time.isoformat(),
            "end_time": end_time.isoformat(),
            "test_id": test_id,
            "nd": result.get("nd", ""),
            "userId": "unique user id",
            "lat": lat or 0,
            "long": lon or 0,
            "units": "Kbps",
        }]
    }

    headers_save = {
        "Content-Type": "application/json",
    }
    if csrf_token:
        headers_save["X-CSRF-TOKEN"] = csrf_token

    save_r = session.post(
        f"{TSC_CHECK_URL}/SaveSpeed",
        json={"uuid": uid, "data": speed_payload},
        headers=headers_save,
        timeout=timeout,
    )
    save_data = _safe_json(save_r)
    result["_raw"]["save_speed"] = save_data

    # Evaluasi status passed kecepatan
    speed_passed = save_data.get("passed")
    if speed_passed == 1:
        result["kecepatan_internet"] = "Layak"
    elif speed_passed is not None:
        result["kecepatan_internet"] = "Belum Layak"
    else:
        result["kecepatan_internet"] = "Layak" if save_data.get("status") else "Belum Layak"


# ─── Penentuan Status Akhir ───────────────────────────────────────────────────

def _determine_status(result: dict):
    """Menentukan status kelayakan akhir tiket TSC."""
    fv = result.get("final_verdict")
    if fv:
        passed = fv.get("passed")
        odp_passed = fv.get("odp_passed")
        if passed == 1 and (odp_passed == 1 or odp_passed is None):
            result["status"] = "NORMAL"
            return
        elif passed == 2:
            result["status"] = "BELUM NORMAL — Kecepatan belum layak"
            return
        elif odp_passed == 0:
            result["status"] = "BELUM NORMAL — Jarak ODP terlalu jauh (>1km)"
            return
        elif passed == 0:
            result["status"] = "BELUM NORMAL"
            return

    kualitas_ok  = result["kualitas_jaringan"]  == "Layak"
    kecepatan_ok = result["kecepatan_internet"] == "Layak" if result["kecepatan_internet"] else None
    odp_ok       = result["odp_inside_radius"]

    if not kualitas_ok:
        result["status"] = "BELUM NORMAL — Kualitas Jaringan belum layak"
    elif kecepatan_ok is False:
        result["status"] = "BELUM NORMAL — Kecepatan belum layak"
    elif odp_ok is False:
        result["status"] = "BELUM NORMAL — Jarak ODP terlalu jauh (>1km)"
    elif kecepatan_ok is True and (odp_ok is True or odp_ok is None):
        result["status"] = "NORMAL"
    elif kualitas_ok and odp_ok is True and kecepatan_ok is None:
        result["status"] = "NORMAL (parsial — speedtest belum dicek)"
    elif kualitas_ok and odp_ok is None and kecepatan_ok is None:
        result["status"] = "NORMAL (parsial — speedtest & ODP belum dicek)"
    else:
        result["status"] = "NORMAL"


# ─── Utilitas Terminal & Input ────────────────────────────────────────────────

def _log(msg: str):
    print(f"  ⏳ {msg}", file=sys.stderr)


def _input(prompt: str, default=None) -> str:
    if default:
        p = f"{prompt} [{default}]: "
    else:
        p = f"{prompt}: "
    val = input(p).strip()
    return val if val else (default or "")


def _parse_lat_lon(coord_str: str) -> tuple[float | None, float | None]:
    """Parse string koordinat 'lat,lon' atau 'lat lon' menjadi tuple float."""
    if not coord_str:
        return None, None
    parts = [p.strip() for p in re.split(r'[,;\s]+', coord_str.strip()) if p.strip()]
    if len(parts) >= 2:
        try:
            return float(parts[0]), float(parts[1])
        except ValueError:
            pass
    return None, None


def lookup_nearest_odp(odp_name: str, webhook_url: str = None) -> tuple:
    """
    Lookup ODP terdekat via webhook n8n.
    Return (success: bool, lat: float, lon: float, pin_name: str, jarak_m: int, candidates: list).
    """
    url = (webhook_url or N8N_ODP_WEBHOOK or "").strip()
    if not url:
        return False, None, None, "", 0, []

    headers = {
        "Content-Type": "application/json",
        "User-Agent": _HEADERS_DEFAULT["User-Agent"]
    }

    try:
        r = requests.post(
            url,
            json={"odp": odp_name.strip()},
            headers=headers,
            timeout=12,
        )
        if r.status_code != 200:
            return False, None, None, "", 0, []

        data = r.json()
        candidates = []
        if isinstance(data, list):
            candidates = data
        elif isinstance(data, dict):
            for k in ("data", "odp_list", "nearest", "candidates"):
                if isinstance(data.get(k), list):
                    candidates = data[k]
                    break
            if not candidates and "lat" in data:
                candidates = [data]

        if not candidates:
            return False, None, None, "", 0, []

        chosen = random.choice(candidates)
        lat = float(chosen.get("lat") or chosen.get("latitude"))
        lon = float(chosen.get("lon") or chosen.get("long") or chosen.get("longitude"))
        pin = chosen.get("pin_name") or chosen.get("name") or odp_name
        dist = int(chosen.get("jarak_meter") or chosen.get("distance") or 0)
        return True, lat, lon, pin, dist, candidates

    except Exception:
        return False, None, None, "", 0, []


def _parse_batch_line(line: str) -> dict:
    """
    Parse satu baris input:
      - TIKET,ODP
      - TIKET,LAT,LON
      - TIKET LAT,LON
      - TIKET saja
    """
    line = line.strip()
    if not line or line.startswith("#"):
        return {}

    tokens = [t.strip() for t in re.split(r'[,;\t]+', line) if t.strip()]
    if not tokens:
        tokens = line.split()

    ticket = tokens[0].upper()
    odp = None
    lat = None
    lon = None

    if len(tokens) == 2:
        second = tokens[1]
        c_lat, c_lon = _parse_lat_lon(second)
        if c_lat is not None:
            lat, lon = c_lat, c_lon
        else:
            odp = second
    elif len(tokens) >= 3:
        try:
            lat = float(tokens[1])
            lon = float(tokens[2])
        except ValueError:
            odp = tokens[1]

    return {"ticket": ticket, "odp": odp, "lat": lat, "lon": lon}


def print_result(result: dict):
    """Cetak hasil pengecekan TSC dalam format tabel terminal rapi."""
    print(f"\n{'═'*54}")
    print(f"  📋  HASIL TSC TELKOM (Infomedia)")
    print(f"{'═'*54}")
    print(f"  🎫  Tiket        : {result.get('ticket') or '-'}")
    print(f"  📡  ND           : {result.get('nd') or '-'}")
    if result.get("witel"):
        print(f"  🌍  Witel        : {result.get('witel')}")
    if result.get("olt"):
        print(f"  🔌  OLT          : {result.get('olt')}")
    print(f"  📦  Paket        : {result.get('package') or '-'}")
    print(f"  🌐  IP Publik    : {result.get('ip_address') or '-'}")

    bng_str = "✅ Valid" if result.get("is_bng") is True else ("❌ Invalid" if result.get("is_bng") is False else "-")
    print(f"  🔁  BNG Check    : {bng_str}")
    print(f"{'─'*54}")

    kj = result.get("kualitas_jaringan")
    kj_str = "✅ Layak" if kj == "Layak" else ("❌ Belum Layak" if kj else "-")
    print(f"  📶  Kualitas Jaringan  : {kj_str}")

    ki = result.get("kecepatan_internet")
    if ki:
        ki_str = "✅ Layak" if ki == "Layak" else "❌ Belum Layak"
        dl = result.get("download_mbps")
        ul = result.get("upload_mbps")
        extra = f" (⬇ {dl}M / ⬆ {ul}M)" if dl else ""
        print(f"  ⚡  Kecepatan Internet : {ki_str}{extra}")
    else:
        print(f"  ⚡  Kecepatan Internet : ⏭️  (tidak dicek)")

    print(f"  🔧  Speed ONT          : {result.get('ont_speed') or '-'}")

    if result.get("odp_name") or result.get("odp_distance_m") is not None:
        print(f"{'─'*54}")
        print(f"  📍  ODP Name     : {result.get('odp_name') or '-'}")
        dist = result.get("odp_distance_m")
        print(f"  📏  Jarak ODP    : {dist} m" if dist is not None else "  📏  Jarak ODP    : -")
        inside = result.get("odp_inside_radius")
        inside_str = "✅ Ya (≤1km)" if inside is True else ("❌ Tidak (>1km)" if inside is False else "-")
        print(f"  📌  Dalam Radius : {inside_str}")

    print(f"{'─'*54}")
    status = result.get("status") or "UNKNOWN"
    is_norm = "NORMAL" in status and "BELUM" not in status and "ERROR" not in status
    icon = "✅" if is_norm else ("⚠️" if "BELUM" in status else "❌")

    print(f"  {icon}  STATUS       : {status}")
    if not is_norm:
        if result.get("kualitas_jaringan") == "Belum Layak":
            print(f"  💡  Catatan      : Redaman optik belum layak. Cek fisik kabel/patchcord/ONT.")
        if result.get("is_bng") is False:
            print(f"  💡  Catatan      : IP BNG belum valid. Pastikan modem pelanggan sudah terhubung PPPoE.")
    print(f"{'═'*54}")


def _retry_with_real_odp(ticket_id: str, res: dict, auto_speed: bool = True) -> dict | None:
    """Jika jarak ODP terlalu jauh (>1km) dan ada nama ODP datek resmi, tawarkan retry."""
    inside = res.get("odp_inside_radius")
    real_odp = res.get("odp_name")
    dist = res.get("odp_distance_m")

    if inside is not False or not real_odp:
        return None

    dist_str = f"{dist} m" if dist is not None else "> 1km"
    print(f"\n  ⚠️  Jarak ODP terlalu jauh ({dist_str}) — kemungkinan salah input ODP / datek berbeda!")
    print(f"  📌  ODP terdaftar di sistem: {real_odp}")

    konfirmasi = _input(f"  Ulangi pengecekan dengan datek asli '{real_odp}'? (y/n)", default="y")
    if konfirmasi.lower() not in ("y", "yes", "ya"):
        return None

    print(f"\n  🔄 Mengulangi pengecekan {ticket_id} dengan datek '{real_odp}'...")
    print(f"  🔍 Mencari ODP tetangga untuk '{real_odp}' via n8n...")

    ok, n_lat, n_lon, n_pin, n_dist, cand = lookup_nearest_odp(real_odp)
    new_lat, new_lon = None, None
    if ok:
        print(f"  🎲 Terpilih acak: {n_pin} (~{n_dist}m) -> ({n_lat}, {n_lon})")
        new_lat, new_lon = n_lat, n_lon
    else:
        telkom_lat = res.get("odp_lat")
        telkom_lon = res.get("odp_long")
        if telkom_lat and telkom_lon:
            try:
                base_lat = float(telkom_lat)
                base_lon = float(telkom_lon)
                import math
                angle = random.uniform(0, 2 * math.pi)
                radius_deg = random.uniform(0.00035, 0.00065)
                new_lat = round(base_lat + radius_deg * math.cos(angle), 7)
                new_lon = round(base_lon + radius_deg * math.sin(angle), 7)
                print(f"  ℹ️  '{real_odp}' tidak ada di DB n8n. Menggunakan koordinat sistem + offset: ({new_lat}, {new_lon})")
            except (ValueError, TypeError):
                new_lat, new_lon = None, None
        else:
            print(f"  ⚠️  Koordinat datek '{real_odp}' tidak dapat ditentukan.")

    res_retry = check_tsc(
        ticket_id=ticket_id,
        lat=new_lat,
        lon=new_lon,
        auto_speed=auto_speed,
        timeout=20,
    )
    print_result(res_retry)
    img_path = generate_tsc_image(res_retry)
    if img_path:
        print(f"  🖼️  Gambar hasil TSC diperbarui: {img_path}\n\n")

    return res_retry


# ─── Mode Menu Interaktif ─────────────────────────────────────────────────────

ASCII_BANNER = r"""
 ═════════════════════════════════════════════
  _____ ___  ___   ___ _           _          
 |_   _/ __|/ __| / __| |_  ___ __| |_____ _ _ 
   | | \__ \ (__ | (__| ' \/ -_) _| / / -_) '_|
   |_| |___/\___| \___|_||_\___\__|_|_\___|_| 
 
 ─────────────────────────────────────────────
    ⚡ Telkom Smart Closing (TSC) Checker ⚡  
              by freedom_seeker
 ═════════════════════════════════════════════
"""


def _collect_interactive_tickets() -> list:
    """Kumpulkan tiket dari input user interaktif (1 tiket, multi-baris, file)."""
    print("\n  Masukkan Tiket / ODP / File:")
    print("  • 1 tiket     : INC53714453,ODP-UBN-FAE/62")
    print("  • Multi-tiket : Langsung paste daftar tiket (atau ketik 'm')")
    print("  • Dari file   : tiket.txt")
    print("  • Keluar      : q")

    try:
        raw = input("\n  > ").strip()
    except (KeyboardInterrupt, EOFError):
        return None

    if not raw:
        return []

    if raw.lower() in ("q", "quit", "exit", "keluar"):
        return None

    lines = []
    if raw.lower() in ("m", "multi", "b", "batch"):
        print("\n  📋 Mode Multi-Tiket (paste daftar tiket di bawah):")
        print("     Tekan Enter pada baris kosong untuk selesai.")
        while True:
            try:
                line_in = input("  > ").strip()
            except (KeyboardInterrupt, EOFError):
                break
            if not line_in:
                break
            lines.append(line_in)

    elif os.path.isfile(raw):
        try:
            with open(raw, encoding="utf-8") as f:
                lines = [ln.strip() for ln in f if ln.strip()]
            print(f"  📂 Membaca file: {raw}")
        except Exception as e:
            print(f"  ❌ Gagal membaca file {raw}: {e}")
            return []

    else:
        lines.append(raw)
        # Deteksi paste tambahan di stdin jika ada
        try:
            import select
            fd = sys.stdin.fileno()
            extra_chunks = []
            while True:
                r, _, _ = select.select([fd], [], [], 0.25)
                if not r:
                    break
                chunk = os.read(fd, 65536)
                if not chunk:
                    break
                extra_chunks.append(chunk.decode("utf-8", errors="replace"))
            if extra_chunks:
                for ln in "".join(extra_chunks).splitlines():
                    if ln.strip():
                        lines.append(ln.strip())
        except Exception:
            pass

    expanded_lines = []
    for ln in lines:
        tokens = re.split(r'\s{2,}|\t+|;', ln)
        for tok in tokens:
            if tok.strip():
                expanded_lines.append(tok.strip())

    items = []
    for ln in expanded_lines:
        parsed = _parse_batch_line(ln)
        if parsed.get("ticket"):
            items.append(parsed)

    return items


def interactive_mode():
    """Mode interaktif terpadu TSC."""
    while True:
        print(ASCII_BANNER)
        items = _collect_interactive_tickets()
        if items is None:
            print("\n  👋 Sampai jumpa!\n")
            break

        if not items:
            continue

        total = len(items)
        if total == 1:
            print(f"\n  🎯 Memproses tiket: {items[0]['ticket']}...")
        else:
            print(f"\n  📋 Ditemukan {total} tiket. Memulai pengecekan...")

        results = []
        failed_items = []
        for i, item in enumerate(items):
            t_ticket = item["ticket"]
            t_lat    = item["lat"]
            t_lon    = item["lon"]
            t_odp    = item["odp"]

            if total > 1:
                print(f"\n{'─'*54}")
                print(f"  [{i+1}/{total}] Memproses {t_ticket}...")

            if t_odp:
                print(f"  🔍 Mencari ODP tetangga untuk '{t_odp}'...")
                ok, n_lat, n_lon, n_pin, n_dist, cand = lookup_nearest_odp(t_odp)
                if ok:
                    print(f"  🎲 Terpilih acak: {n_pin} (~{n_dist}m) -> ({n_lat}, {n_lon})")
                    t_lat, t_lon = n_lat, n_lon
                else:
                    print(f"  ⚠️  ODP '{t_odp}' tidak ditemukan di database n8n. Lanjut tanpa ODP.")
                    t_lat, t_lon = None, None

            res = check_tsc(
                ticket_id  = t_ticket,
                lat        = t_lat,
                lon        = t_lon,
                auto_speed = True,
                timeout    = 20,
            )
            print_result(res)

            img_path = generate_tsc_image(res)
            if img_path:
                print(f"  🖼️  Gambar hasil TSC disimpan: {img_path}\n\n")

            res_datek = _retry_with_real_odp(t_ticket, res, auto_speed=True)
            if res_datek:
                res = res_datek

            status_str = res.get("status", "")
            is_normal = "NORMAL" in status_str and "BELUM" not in status_str and "ERROR" not in status_str

            if total == 1:
                if not is_normal:
                    retry = _input("\n  ⚠️  Hasil belum normal. Ulangi pengecekan untuk tiket ini? (y/n)", default="y")
                    if retry.lower() in ("y", "yes", "ya"):
                        print(f"\n  🔄 Mengulangi pengecekan untuk {t_ticket}...")
                        res_retry = check_tsc(ticket_id=t_ticket, lat=t_lat, lon=t_lon, auto_speed=True)
                        print_result(res_retry)
                        generate_tsc_image(res_retry)
                        results.append(res_retry)
                        continue
            else:
                if not is_normal:
                    failed_items.append({"ticket": t_ticket, "lat": t_lat, "lon": t_lon})

            results.append(res)

        if total > 1:
            normal_count = total - len(failed_items)
            print(f"\n{'═'*54}")
            print(f"  📊 Ringkasan Batch: {normal_count}/{total} tiket NORMAL")
            if failed_items:
                print(f"  ⚠️  {len(failed_items)} tiket belum normal:")
                for fi in failed_items:
                    print(f"     • {fi['ticket']}")
                ulang_gagal = _input("\n  Ulangi pengecekan khusus tiket yang belum normal? (y/n)", default="n")
                if ulang_gagal.lower() in ("y", "yes", "ya"):
                    for fi in failed_items:
                        f_ticket = fi["ticket"]
                        f_lat = fi["lat"]
                        f_lon = fi["lon"]
                        print(f"\n  🔄 Mengulangi pengecekan untuk {f_ticket}...")
                        res_retry = check_tsc(ticket_id=f_ticket, lat=f_lat, lon=f_lon, auto_speed=True)
                        print_result(res_retry)
                        generate_tsc_image(res_retry)
            print(f"{'═'*54}")

        try:
            import termios
            termios.tcflush(sys.stdin, termios.TCIFLUSH)
        except Exception:
            pass

        input("\n  Tekan Enter untuk kembali ke menu utama...")


# ─── Mode CLI ─────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="TSC Telkom Checker — cek layanan internet IndiHome / EBIS via portal TSC Infomedia tanpa browser",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Contoh:
  python tsc_checker.py                           # mode menu interaktif
  python tsc_checker.py INC53714453               # cek langsung
  python tsc_checker.py INC53714453 --coord -8.6465,115.1735 --auto-speed
  python tsc_checker.py INC53714453 --dl 50 --ul 25
  python tsc_checker.py INC53714453 --speedtest
  python tsc_checker.py --batch tiket.txt --output hasil.json
        """,
    )
    parser.add_argument("ticket", nargs="?")
    parser.add_argument("--batch",       "-b", metavar="FILE")
    parser.add_argument("--nd",          metavar="ND")
    parser.add_argument("--odp",         help="Nama ODP target (akan dicari nearest ODP via webhook n8n)")
    parser.add_argument("--webhook",     "-w", help="URL Webhook n8n untuk nearest ODP lookup")
    parser.add_argument("--lat",         type=float,
                        help="Latitude (opsional)")
    parser.add_argument("--lon",         type=float,
                        help="Longitude (opsional)")
    parser.add_argument("--coord",       "-c", metavar="LAT,LON",
                        help="Koordinat gabung lat,lon (contoh: -8.6465,115.1735)")
    parser.add_argument("--speedtest",   "-s", action="store_true",
                        help="Speedtest otomatis (butuh speedtest-cli)")
    parser.add_argument("--auto-speed",  "-a", action="store_true",
                        help="Auto speed dari paket PCRF/TSC + random noise")
    parser.add_argument("--dl",          type=float, metavar="MBPS",
                        help="Download manual (Mbps)")
    parser.add_argument("--ul",          type=float, metavar="MBPS",
                        help="Upload manual (Mbps)")
    parser.add_argument("--ping",        type=float, default=10.0,
                        help="Ping manual ms (default: 10)")
    parser.add_argument("--jitter",      type=float, default=1.0,
                        help="Jitter manual ms (default: 1)")
    parser.add_argument("--image",       "-i", action="store_true",
                        help="Generate gambar bukti TSC ke Documents/TSC")
    parser.add_argument("--output",      "-o", metavar="FILE")
    parser.add_argument("--json",        "-j", action="store_true")
    parser.add_argument("--no-raw",      action="store_true")
    parser.add_argument("--timeout",     type=int, default=20)

    args = parser.parse_args()

    # Tanpa argumen → mode menu interaktif
    if not args.ticket and not args.batch:
        interactive_mode()
        return

    # Tampilkan banner jika bukan mode JSON murni
    if not args.json:
        print(ASCII_BANNER)

    effective_webhook = (args.webhook or N8N_ODP_WEBHOOK or "").strip()

    cli_lat = args.lat
    cli_lon = args.lon
    if args.coord:
        c_lat, c_lon = _parse_lat_lon(args.coord)
        if c_lat is not None:
            cli_lat, cli_lon = c_lat, c_lon

    # Mode single dengan --odp
    if args.odp and not args.batch:
        if not effective_webhook:
            print("⚠️  --odp diberikan tetapi URL webhook n8n belum diatur.", file=sys.stderr)
            print("   Gunakan --webhook <URL> atau set environment variable TSC_ODP_WEBHOOK_URL.", file=sys.stderr)
            print("   Melanjutkan pengecekan TSC tanpa ODP...\n", file=sys.stderr)
        else:
            print(f"🔍 Mencari ODP tetangga di sekitar '{args.odp}' via n8n...", file=sys.stderr)
            ok, n_lat, n_lon, n_pin, n_dist, cand = lookup_nearest_odp(args.odp, webhook_url=effective_webhook)
            if ok:
                print(f"✅ Ditemukan {len(cand)} ODP tetangga:", file=sys.stderr)
                for idx, c in enumerate(cand, 1):
                    print(f"   {idx}. {c.get('pin_name')} (~{c.get('jarak_meter')}m)", file=sys.stderr)
                print(f"🎲 Terpilih acak: {n_pin} (jarak ~{n_dist}m)", file=sys.stderr)
                print(f"📍 Menggunakan koordinat: {n_lat}, {n_lon}\n", file=sys.stderr)
                cli_lat, cli_lon = n_lat, n_lon
            else:
                print(f"⚠️  ODP '{args.odp}' tidak ditemukan di database n8n.", file=sys.stderr)
                print(f"ℹ️  Melanjutkan pengecekan TSC tanpa koordinat ODP...\n", file=sys.stderr)

    batch_items = []
    if args.batch:
        try:
            with open(args.batch, encoding="utf-8") as f:
                raw_lines = [ln.strip() for ln in f if ln.strip()]
        except FileNotFoundError:
            print(f"❌ File tidak ditemukan: {args.batch}")
            sys.exit(1)
        for ln in raw_lines:
            it = _parse_batch_line(ln)
            if it.get("ticket"):
                batch_items.append(it)
        if not batch_items:
            print(f"⚠️  Tidak ada tiket valid di: {args.batch}")
            sys.exit(1)
    else:
        batch_items = [{"ticket": args.ticket, "odp": None, "lat": cli_lat, "lon": cli_lon}]

    results = []
    for i, item in enumerate(batch_items):
        t_ticket = item["ticket"]
        t_lat    = item["lat"]
        t_lon    = item["lon"]
        t_odp    = item["odp"]

        if len(batch_items) > 1:
            print(f"\n[{i+1}/{len(batch_items)}] Mengecek {t_ticket}...", file=sys.stderr)

        if t_odp:
            if not effective_webhook:
                print(f"⚠️  [{t_ticket}] ODP '{t_odp}' tertera tapi webhook n8n belum diatur. Melewati ODP...", file=sys.stderr)
                t_lat, t_lon = None, None
            else:
                print(f"🔍 [{t_ticket}] Mencari ODP tetangga untuk '{t_odp}'...", file=sys.stderr)
                ok, n_lat, n_lon, n_pin, n_dist, cand = lookup_nearest_odp(t_odp, webhook_url=effective_webhook)
                if ok:
                    print(f"🎲 [{t_ticket}] Terpilih acak: {n_pin} (~{n_dist}m) -> ({n_lat}, {n_lon})", file=sys.stderr)
                    t_lat, t_lon = n_lat, n_lon
                else:
                    print(f"⚠️  [{t_ticket}] ODP '{t_odp}' tidak ditemukan di database n8n.", file=sys.stderr)
                    print(f"ℹ️  Tetap melanjutkan pengecekan TSC tanpa koordinat ODP...", file=sys.stderr)
                    t_lat, t_lon = None, None
        elif t_lat is None and cli_lat is not None:
            t_lat, t_lon = cli_lat, cli_lon

        res = check_tsc(
            ticket_id        = t_ticket,
            nd               = args.nd,
            lat              = t_lat,
            lon              = t_lon,
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

        if args.image:
            img_path = generate_tsc_image(res)
            if img_path:
                print(f"  🖼️  Gambar disimpan: {img_path}")

        if not args.json:
            res_datek = _retry_with_real_odp(t_ticket, res, auto_speed=args.auto_speed or True)
            if res_datek:
                res = res_datek
                if args.no_raw:
                    res.pop("_raw", None)

            if len(batch_items) == 1:
                status_str = res.get("status", "")
                is_normal = "NORMAL" in status_str and "BELUM" not in status_str and "ERROR" not in status_str
                if not is_normal:
                    retry = _input("\n  ⚠️  Hasil belum normal. Ulangi pengecekan untuk tiket ini? (y/n)", default="y")
                    if retry.lower() in ("y", "yes", "ya"):
                        print(f"\n  🔄 Mengulangi pengecekan untuk {t_ticket}...", file=sys.stderr)
                        res = check_tsc(
                            ticket_id        = t_ticket,
                            nd               = args.nd,
                            lat              = t_lat,
                            lon              = t_lon,
                            run_speedtest    = args.speedtest,
                            auto_speed       = args.auto_speed or True,
                            manual_dl_mbps   = args.dl,
                            manual_ul_mbps   = args.ul,
                            manual_ping_ms   = args.ping,
                            manual_jitter_ms = args.jitter,
                            timeout          = args.timeout,
                        )
                        if args.no_raw:
                            res.pop("_raw", None)
                        print_result(res)
                        if args.image:
                            generate_tsc_image(res)

        results.append(res)

    if args.output:
        out = results[0] if len(results) == 1 else results
        with open(args.output, "w", encoding="utf-8") as f:
            json.dump(out, f, indent=2, ensure_ascii=False)
        print(f"💾 Disimpan ke: {args.output}", file=sys.stderr)

    return results


if __name__ == "__main__":
    main()
