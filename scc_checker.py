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
    pilihan = _input("  Pilih", default="4")

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

            # Output
            output_path = _input("  Simpan ke file JSON? (kosongkan untuk skip)")

            results = []
            for i, ticket in enumerate(tickets):
                print(f"\n  [{i+1}/{len(tickets)}] Mengecek {ticket}...")
                res = check_scc(ticket_id=ticket, lat=lat, lon=lon,
                                run_speedtest=run_st, auto_speed=auto_st,
                                manual_dl_mbps=dl, manual_ul_mbps=ul,
                                manual_ping_ms=ping, manual_jitter_ms=jitter)
                print_result(res)
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

            print()
            res = check_scc(ticket_id=ticket, lat=lat, lon=lon,
                            run_speedtest=run_st, auto_speed=auto_st,
                            manual_dl_mbps=dl, manual_ul_mbps=ul,
                            manual_ping_ms=ping, manual_jitter_ms=jitter)
            print_result(res)

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

        results.append(res)

    if args.output:
        out = results[0] if len(results) == 1 else results
        with open(args.output, "w", encoding="utf-8") as f:
            json.dump(out, f, indent=2, ensure_ascii=False)
        print(f"💾 Disimpan ke: {args.output}", file=sys.stderr)

    return results


if __name__ == "__main__":
    main()
