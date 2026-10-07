#!/usr/bin/env python3
"""
Script to execute SCC check for INC53714453 with coordinates (-8.646586, 115.173562)
and record all HTTP requests, responses, headers, endpoints, and payloads to a new folder.
"""

import os
import json
import time
import requests
from datetime import datetime, timezone
from urllib.parse import unquote

TICKET = "INC53714453"
LAT = -8.646586
LON = 115.173562
BASE_URL = "https://scc.telkom.co.id/CloseTicket.Internet/Check_embededv1"
MYSIIS_BASE = "https://api.mysiis.io/m/speedtest/v1"
MYSIIS_KEY = "MVnSDdytX3LVwtwDsTeVDiBxVAUoq9p9"

OUTPUT_DIR = os.path.join(os.getcwd(), "traffic_INC53714453")
os.makedirs(OUTPUT_DIR, exist_ok=True)

traffic_entries = []

HEADERS_DEFAULT = {
    "User-Agent": "Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Mobile Safari/537.36",
    "Accept": "application/json, text/javascript, */*; q=0.01",
    "X-Requested-With": "XMLHttpRequest",
    "X-KL-Ajax-Request": "Ajax_Request",
    "Content-Type": "application/x-www-form-urlencoded",
}
DETAIL_ACCESS = json.dumps({
    "brands": [{"brand": "Chrome", "version": "120"}],
    "mobile": True,
    "platform": "Android",
})

class TrafficRecorder:
    def __init__(self):
        self.session = requests.Session()
        self.step = 0

    def request(self, method, url, **kwargs):
        self.step += 1
        step_num = self.step
        start_t = time.time()
        req_headers = dict(self.session.headers)
        if "headers" in kwargs:
            req_headers.update(kwargs["headers"])

        # Determine payload
        payload = None
        if "data" in kwargs:
            payload = kwargs["data"]
        elif "json" in kwargs:
            payload = kwargs["json"]

        resp = self.session.request(method, url, **kwargs)
        elapsed = round(time.time() - start_t, 3)

        # Parse body
        resp_text = resp.text
        try:
            resp_body = resp.json()
        except Exception:
            resp_body = resp_text if len(resp_text) < 10000 else resp_text[:1000] + "... [truncated]"

        entry = {
            "step": step_num,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "elapsed_seconds": elapsed,
            "request": {
                "method": method.upper(),
                "url": url,
                "headers": req_headers,
                "body": payload,
            },
            "response": {
                "status_code": resp.status_code,
                "headers": dict(resp.headers),
                "body": resp_body,
            }
        }
        traffic_entries.append(entry)
        print(f"[{step_num:02d}] {method.upper()} {url} -> Status {resp.status_code} ({elapsed}s)")
        return resp

recorder = TrafficRecorder()

print(f"=== Memulai pengecekan tiket {TICKET} dengan koordinat ({LAT}, {LON}) ===")

# 1. Buka halaman check di tsc.infomedia.co.id
r1 = recorder.request(
    "GET",
    f"https://tsc.infomedia.co.id/pages/check?ticketId={TICKET}",
    headers={"User-Agent": HEADERS_DEFAULT["User-Agent"]}
)

# 2. Inisialisasi sesi pada backend SCC Telkom
r_init = recorder.request(
    "GET",
    f"{BASE_URL}/?ticketId={TICKET}&nd=",
    headers={"User-Agent": HEADERS_DEFAULT["User-Agent"]}
)

# 3. CreateTask
r2 = recorder.request(
    "POST",
    f"{BASE_URL}/createTask",
    headers=HEADERS_DEFAULT,
    data={"ticket": TICKET, "nd": "", "detailAccess": DETAIL_ACCESS, "device": "false"}
)
d2 = r2.json() if r2.status_code == 200 else {}
uid = d2.get("data", {}).get("uid")
print(f"    UID diperoleh: {uid}")

if not uid:
    print("Gagal memperoleh UID!")
    exit(1)

# 3. RetrieveToken1
recorder.request(
    "POST",
    f"{BASE_URL}/retrieveToken1",
    headers=HEADERS_DEFAULT,
    data={"uid": uid}
)

# 4. RetrieveNDByIN
r4 = recorder.request(
    "POST",
    f"{BASE_URL}/retrieveNDByIN",
    headers=HEADERS_DEFAULT,
    data={"uid": uid}
)
nd_data = r4.json().get("data", {}) if r4.status_code == 200 else {}
nd = nd_data.get("nd")
witel = nd_data.get("witel")
olt = nd_data.get("hostname_olt")
service_id = nd_data.get("service_id")
print(f"    ND: {nd} | Witel: {witel} | OLT: {olt}")

# 5. RetrieveUPCF
r5 = recorder.request(
    "POST",
    f"{BASE_URL}/retrieveUPCF",
    headers=HEADERS_DEFAULT,
    data={"uid": uid}
)
upcf_data = r5.json().get("data", {}) if r5.status_code == 200 else {}
pkg_name = upcf_data.get("package_name")
print(f"    Paket: {pkg_name}")

# 6. RetrieveIPRadius
r6 = recorder.request(
    "POST",
    f"{BASE_URL}/retrieveIPRadius",
    headers=HEADERS_DEFAULT,
    data={"uid": uid}
)
is_bng = r6.json().get("data", {}).get("is_bng") if r6.status_code == 200 else None
print(f"    Is BNG: {is_bng}")

# 7. Get Public IP
ip_addr = None
for ip_url in ["https://myip.tacc.id", "https://myip.indihome.co.id"]:
    try:
        r_ip = recorder.request("GET", ip_url, headers={"User-Agent": HEADERS_DEFAULT["User-Agent"]})
        ip_addr = r_ip.json().get("ip_addr")
        if ip_addr:
            break
    except Exception as e:
        print(f"    Gagal get IP from {ip_url}: {e}")

print(f"    IP Publik: {ip_addr}")

# 8. SaveWho
recorder.request(
    "POST",
    f"{BASE_URL}/saveWho",
    headers=HEADERS_DEFAULT,
    data={
        "uid": uid,
        "ip_addr": ip_addr or "",
        "success": 1,
        "request": "",
        "response": json.dumps({"ip_addr": ip_addr}),
        "statusCode": 200
    }
)

# 9. RetrieveSpeedAcsis
r9 = recorder.request(
    "POST",
    f"{BASE_URL}/retrieveSpeedAcsis",
    headers=HEADERS_DEFAULT,
    data={"uid": uid}
)
ont_speed = r9.json().get("data", {}).get("speed") if r9.status_code == 200 else None
print(f"    ONT Speed: {ont_speed}")

# 10. RetrieveUkur (Kualitas Jaringan)
r10 = recorder.request(
    "POST",
    f"{BASE_URL}/retrieveUkur",
    headers=HEADERS_DEFAULT,
    data={"uid": uid}
)
ukur_data = r10.json().get("data", {}) if r10.status_code == 200 else {}
redaman_passed = ukur_data.get("redaman_passed")
print(f"    Redaman Passed: {redaman_passed}")

# 11. RequestSpeedDBT (Get auth param for mysiis)
r11 = recorder.request(
    "POST",
    f"{BASE_URL}/RequestSpeedDBT",
    headers=HEADERS_DEFAULT,
    data={"uid": uid}
)
dbt_data = r11.json().get("data", {}) if r11.status_code == 200 else {}
param = unquote(dbt_data.get("param", ""))

# 12. Auth External to mysiis
r12 = recorder.request(
    "POST",
    f"{MYSIIS_BASE}/auth/external",
    headers={
        "Authorization": f"Bearer {param}",
        "apikey": MYSIIS_KEY,
        "Content-Type": "application/x-www-form-urlencoded"
    },
    data={"grant_type": "client_credentials"}
)
jwt_token = r12.json().get("data", {}).get("accessToken") if r12.status_code == 200 else None

# 13. Check ODP Inside ND with coordinates
odp_data = {}
if jwt_token:
    r13 = recorder.request(
        "POST",
        f"{MYSIIS_BASE}/tools/check-odp-inside-nd",
        headers={
            "Authorization": f"Bearer {jwt_token}",
            "apikey": MYSIIS_KEY,
            "Content-Type": "application/json"
        },
        json={"lat": LAT, "long": LON}
    )
    odp_data = r13.json().get("data", {}) if r13.status_code == 200 else {}
    print(f"    ODP Name: {odp_data.get('odpName')}")
    print(f"    ODP Distance: {odp_data.get('distance')} m")
    print(f"    ODP Inside Radius: {odp_data.get('isInside')}")

# Save full results summary
final_summary = {
    "ticket": TICKET,
    "nd": nd,
    "witel": witel,
    "olt": olt,
    "service_id": service_id,
    "package": pkg_name,
    "ip_address": ip_addr,
    "is_bng": is_bng,
    "kualitas_jaringan": "Layak" if redaman_passed == 1 else "Belum Layak",
    "redaman_passed": redaman_passed,
    "ont_speed": ont_speed,
    "coordinates_checked": {
        "lat": LAT,
        "lon": LON
    },
    "odp_info": odp_data,
    "uid": uid,
    "timestamp": datetime.now(timezone.utc).isoformat(),
    "status": "NORMAL (Layak & dalam radius ODP)" if (redaman_passed == 1 and odp_data.get("isInside")) else "BELUM NORMAL"
}

with open(os.path.join(OUTPUT_DIR, "traffic_log.json"), "w", encoding="utf-8") as f:
    json.dump(traffic_entries, f, indent=2, ensure_ascii=False)

with open(os.path.join(OUTPUT_DIR, "summary_result.json"), "w", encoding="utf-8") as f:
    json.dump(final_summary, f, indent=2, ensure_ascii=False)

# Write human readable trace text
with open(os.path.join(OUTPUT_DIR, "traffic_trace.txt"), "w", encoding="utf-8") as f:
    f.write(f"=== HTTP TRAFFIC TRACE FOR TICKET {TICKET} ===\n")
    f.write(f"Generated At: {datetime.now(timezone.utc).isoformat()}\n")
    f.write(f"Target URL: https://tsc.infomedia.co.id/pages/check\n")
    f.write(f"Coordinates: Lat {LAT}, Lon {LON}\n\n")

    for entry in traffic_entries:
        f.write(f"{'='*70}\n")
        f.write(f"STEP {entry['step']:02d} | {entry['request']['method']} {entry['request']['url']}\n")
        f.write(f"Timestamp: {entry['timestamp']} | Latency: {entry['elapsed_seconds']}s | Status: {entry['response']['status_code']}\n")
        f.write(f"{'-'*70}\n")
        f.write("REQUEST HEADERS:\n")
        for k, v in entry['request']['headers'].items():
            f.write(f"  {k}: {v}\n")
        if entry['request']['body']:
            f.write("REQUEST BODY:\n")
            if isinstance(entry['request']['body'], (dict, list)):
                f.write(json.dumps(entry['request']['body'], indent=2) + "\n")
            else:
                f.write(f"  {entry['request']['body']}\n")
        f.write("\nRESPONSE HEADERS:\n")
        for k, v in entry['response']['headers'].items():
            f.write(f"  {k}: {v}\n")
        f.write("RESPONSE BODY:\n")
        if isinstance(entry['response']['body'], (dict, list)):
            f.write(json.dumps(entry['response']['body'], indent=2) + "\n")
        else:
            f.write(f"  {entry['response']['body']}\n")
        f.write("\n")

print(f"\n[DONE] Semua data traffic dan hasil berhasil disimpan ke: {OUTPUT_DIR}")
