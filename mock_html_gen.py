"""
HTML Mock Generator untuk SCC Telkom
Menghasilkan file HTML responsif yang persis 100% dengan tampilan asli web SCC Telkom.
"""

from datetime import datetime, timezone, timedelta

WIB_TZ = timezone(timedelta(hours=7))

try:
    from logos_b64 import LOGO1_B64, LOGO2_B64
except ImportError:
    LOGO1_B64 = ""
    LOGO2_B64 = ""

def generate_scc_html(data: dict, output_file: str = "mock_scc.html") -> str:
    """
    Generate file HTML hasil SCC Telkom dari data dict hasil pengecekan.
    """
    ticket = data.get("ticket", "-")
    nd = data.get("nd", "-")
    kualitas = data.get("kualitas_jaringan", "Layak")
    kecepatan = data.get("kecepatan_internet", "Layak") or "Layak"
    speed_ont = data.get("ont_speed", "-") or "-"
    
    lat = data.get("odp_lat")
    lon = data.get("odp_long")
    if lat is not None and lon is not None:
        latlong = f"{lat:.6f},{lon:.6f}"
    else:
        latlong = "-"
        
    jarak = data.get("odp_distance_m")
    jarak_str = f"{jarak} m" if jarak is not None else "0 m"
    odp_name = data.get("odp_name") or "-"
    
    now = datetime.now(timezone.utc).astimezone(WIB_TZ)
    ts1 = now.strftime("%Y-%m-%d %H:%M:%S WIB")
    ts2 = now.strftime("%H:%M:%S WIB")
    
    uid = data.get("_raw", {}).get("uid", "1789894156.430d9c5e5ac4e9b03243d9182b41a67ceda50773")
    
    # Logo base64 data URIs
    src_logo1 = f"data:image/png;base64,{LOGO1_B64}" if LOGO1_B64 else "https://scc.telkom.co.id/CloseTicket.Internet/asset/img/logo1.png"
    src_logo2 = f"data:image/png;base64,{LOGO2_B64}" if LOGO2_B64 else "https://scc.telkom.co.id/CloseTicket.Internet/asset/img/logo2.png"

    html_content = f"""<!DOCTYPE html>
<html lang="id">
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1, shrink-to-fit=no, maximum-scale=1.0, user-scalable=no">
    <title>Hasil Pengecekan Internet Anda</title>
    <style>
        * {{
            box-sizing: border-box;
            margin: 0;
            padding: 0;
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
            -webkit-tap-highlight-color: transparent;
        }}
        body {{
            background-color: #db4455;
            color: #333333;
            min-height: 100vh;
            display: flex;
            flex-direction: column;
            align-items: center;
        }}
        /* Header Logo Bar */
        .header-logo {{
            width: 100%;
            background-color: #ffffff;
            padding: 10px 16px;
            display: flex;
            justify-content: space-between;
            align-items: center;
            box-shadow: 0 1px 3px rgba(0,0,0,0.1);
        }}
        .header-logo img {{
            height: 28px;
            object-fit: contain;
        }}
        
        /* Main Container */
        .container {{
            width: 100%;
            max-width: 480px;
            padding: 16px 20px 40px 20px;
            display: flex;
            flex-direction: column;
            align-items: center;
        }}
        
        .main-title {{
            color: #ffffff;
            font-size: 20px;
            font-weight: 500;
            text-align: center;
            margin-top: 4px;
            margin-bottom: 6px;
            position: relative;
            padding-bottom: 6px;
        }}
        .main-title::after {{
            content: '';
            position: absolute;
            left: 0;
            right: 0;
            bottom: 0;
            height: 1.5px;
            background-color: rgba(255, 255, 255, 0.7);
        }}
        
        .timestamp-top {{
            color: #ffffff;
            font-size: 13px;
            font-weight: 400;
            text-align: right;
            width: 100%;
            margin-top: 8px;
            margin-bottom: 12px;
        }}
        
        /* Card Items */
        .card-list {{
            width: 100%;
            display: flex;
            flex-direction: column;
            gap: 9px;
        }}
        .card-item {{
            display: flex;
            background-color: #ffffff;
            border-radius: 6px;
            overflow: hidden;
            height: 38px;
            box-shadow: 0 1px 2px rgba(0,0,0,0.06);
        }}
        .card-label {{
            width: 52%;
            background-color: #e9ecef;
            color: #495057;
            font-size: 12px;
            font-weight: 500;
            display: flex;
            align-items: center;
            padding-left: 12px;
            border-right: 1px solid #ced4da;
            white-space: nowrap;
        }}
        .card-value {{
            width: 48%;
            background-color: #ffffff;
            color: #212529;
            font-size: 12.5px;
            font-weight: 400;
            display: flex;
            align-items: center;
            padding-left: 12px;
            padding-right: 6px;
            overflow: hidden;
            text-overflow: ellipsis;
            white-space: nowrap;
        }}
        
        .timestamp-bottom {{
            color: #ffffff;
            font-size: 12px;
            text-align: right;
            width: 100%;
            margin-top: 8px;
            margin-bottom: 24px;
        }}
        
        .verdict-text {{
            color: #ffffff;
            font-size: 13.5px;
            text-align: center;
            margin-bottom: 22px;
            width: 100%;
            border-top: 1px solid rgba(255, 255, 255, 0.2);
            padding-top: 18px;
        }}
        
        .btn-ok {{
            background-color: #ffffff;
            color: #333333;
            border: none;
            border-radius: 4px;
            font-size: 13.5px;
            font-weight: 500;
            padding: 7px 32px;
            cursor: pointer;
            box-shadow: 0 1px 3px rgba(0,0,0,0.15);
            margin-bottom: 50px;
        }}
        
        .uid-text {{
            color: rgba(255, 255, 255, 0.85);
            font-size: 11px;
            text-align: center;
            width: 100%;
            word-break: break-all;
            margin-bottom: 16px;
            letter-spacing: 0.2px;
        }}
        
        /* Bottom Menu Button */
        .btn-bottom-menu {{
            width: 100%;
            background-color: #ffffff;
            color: #d32f2f;
            border: 1px solid #ced4da;
            border-radius: 8px;
            padding: 12px 16px;
            font-size: 14.5px;
            font-weight: 600;
            display: flex;
            justify-content: center;
            align-items: center;
            gap: 8px;
            cursor: pointer;
            box-shadow: 0 1px 3px rgba(0,0,0,0.08);
        }}
        .arrow-left {{
            font-size: 18px;
            line-height: 1;
        }}
    </style>
</head>
<body>

    <!-- Logo Header -->
    <div class="header-logo">
        <img src="{src_logo1}" alt="Telkom Indonesia">
        <img src="{src_logo2}" alt="IndiHome">
    </div>

    <!-- Main Container -->
    <div class="container">
        <h1 class="main-title">Hasil Pengecekan Internet Anda</h1>
        <div class="timestamp-top">{ts1}</div>

        <div class="card-list">
            <div class="card-item">
                <div class="card-label">Nomor Tiket / Permintaan</div>
                <div class="card-value">{ticket}</div>
            </div>
            <div class="card-item">
                <div class="card-label">Nomor Internet Anda</div>
                <div class="card-value">{nd}</div>
            </div>
            <div class="card-item">
                <div class="card-label">Kualitas Jaringan</div>
                <div class="card-value">{kualitas}</div>
            </div>
            <div class="card-item">
                <div class="card-label">Kecepatan Internet</div>
                <div class="card-value">{kecepatan}</div>
            </div>
            <div class="card-item">
                <div class="card-label">Speed Test ONT</div>
                <div class="card-value">{speed_ont}</div>
            </div>
            <div class="card-item">
                <div class="card-label">LatLong ODP</div>
                <div class="card-value">{latlong}</div>
            </div>
            <div class="card-item">
                <div class="card-label">Jarak ODP</div>
                <div class="card-value">{jarak_str}</div>
            </div>
            <div class="card-item">
                <div class="card-label">Nama ODP</div>
                <div class="card-value">{odp_name}</div>
            </div>
        </div>

        <div class="timestamp-bottom">{ts2}</div>

        <div class="verdict-text">Layanan internet anda dalam kondisi normal.</div>

        <button class="btn-ok">Ok</button>

        <div class="uid-text">{uid}</div>

        <button class="btn-bottom-menu">
            <span class="arrow-left">&#8592;</span> Kembali Ke Menu Utama
        </button>
    </div>

</body>
</html>
"""
    with open(output_file, "w", encoding="utf-8") as f:
        f.write(html_content)
    return output_file

if __name__ == "__main__":
    sample_data = {
        "ticket": "INC53196742",
        "nd": "172418753943",
        "kualitas_jaringan": "Layak",
        "kecepatan_internet": "Layak",
        "ont_speed": "-",
        "odp_lat": -8.666807,
        "odp_long": 115.181211,
        "odp_distance_m": 33,
        "odp_name": "ODP-UBN-FAR/08",
        "_raw": {
            "uid": "1789894156.430d9c5e5ac4e9b03243d9182b41a67ceda50773"
        }
    }
    file_path = generate_scc_html(sample_data, "mock_scc.html")
    print(f"HTML mock generated: {file_path}")
