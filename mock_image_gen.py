"""
Image Mock Generator untuk SCC Telkom v2
Kalibrasi pixel-perfect dengan font sistem Android (Roboto) agar identik 100% dengan aslinya.
"""

import os
from datetime import datetime
from PIL import Image, ImageDraw, ImageFont

def get_font(size: int, bold: bool = False):
    """
    Cari font sistem Android/Windows yang tersedia.
    """
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
                
    # Fallback jika tidak ada file font spesifik
    try:
        return ImageFont.truetype("DejaVuSans.ttf", size)
    except Exception:
        return ImageFont.load_default()

def draw_arrow_left(draw, x, y, size=16, color=(211, 47, 47)):
    """Gambar icon panah kiri manual agar tidak bergantung pada glyph font."""
    # Garis tengah horizontal
    draw.line([(x, y), (x + size, y)], fill=color, width=3)
    # Sayap atas panah
    draw.line([(x, y), (x + int(size * 0.4), y - int(size * 0.4))], fill=color, width=3)
    # Sayap bawah panah
    draw.line([(x, y), (x + int(size * 0.4), y + int(size * 0.4))], fill=color, width=3)

def generate_scc_image(data: dict, output_file: str = "mock_scc.png") -> str:
    # Resolusi standar layar smartphone: 720 x 1560
    width = 720
    height = 1560
    
    # Warna palet asli SCC Telkom
    bg_red = (219, 68, 85)        # #db4455
    white = (255, 255, 255)
    gray_label = (233, 236, 239)  # #e9ecef
    text_dark = (33, 37, 41)      # #212529
    text_gray = (73, 80, 87)      # #495057
    border_color = (206, 212, 218)# #ced4da
    
    img = Image.new("RGB", (width, height), bg_red)
    draw = ImageDraw.Draw(img)
    
    # ── 1. Header Putih + Logo (Tinggi 100px) ─────────────────────────────
    header_h = 100
    draw.rectangle([(0, 0), (width, header_h)], fill=white)
    
    try:
        logo1 = Image.open("logo1.png").convert("RGBA")
        logo2 = Image.open("logo2.png").convert("RGBA")
        
        target_h = 44
        r1 = target_h / logo1.height
        logo1 = logo1.resize((int(logo1.width * r1), target_h), Image.Resampling.LANCZOS)
        
        r2 = target_h / logo2.height
        logo2 = logo2.resize((int(logo2.width * r2), target_h), Image.Resampling.LANCZOS)
        
        img.paste(logo1, (36, (header_h - target_h) // 2), logo1)
        img.paste(logo2, (width - logo2.width - 36, (header_h - target_h) // 2), logo2)
    except Exception:
        pass

    # ── Load Fonts Berdasarkan Skala ──────────────────────────────────────
    font_title   = get_font(34, bold=True)
    font_ts_top  = get_font(23, bold=False)
    font_label   = get_font(22, bold=True)
    font_val     = get_font(23, bold=False)
    font_ts_bot  = get_font(21, bold=False)
    font_verdict = get_font(24, bold=False)
    font_btn_ok  = get_font(24, bold=True)
    font_uid     = get_font(19, bold=False)
    font_menu    = get_font(26, bold=True)

    # ── 2. Judul Utama ───────────────────────────────────────────────────
    title_text = "Hasil Pengecekan Internet Anda"
    bbox_t = draw.textbbox((0, 0), title_text, font=font_title)
    tw = bbox_t[2] - bbox_t[0]
    draw.text(((width - tw) // 2, 130), title_text, fill=white, font=font_title)
    
    # Garis tipis bawah judul
    draw.line([(55, 180), (width - 55, 180)], fill=(255, 255, 255, 180), width=2)
    
    # Timestamp atas
    now = datetime.now()
    ts1 = now.strftime("%Y-%m-%d %H:%M:%S WIB")
    bbox_ts1 = draw.textbbox((0, 0), ts1, font=font_ts_top)
    draw.text((width - 55 - (bbox_ts1[2] - bbox_ts1[0]), 196), ts1, fill=white, font=font_ts_top)

    # ── 3. Daftar Kartu / Field ──────────────────────────────────────────
    ticket = data.get("ticket", "-")
    nd = data.get("nd", "-")
    kualitas = data.get("kualitas_jaringan", "Layak")
    kecepatan = data.get("kecepatan_internet", "Layak") or "Layak"
    speed_ont = data.get("ont_speed", "-") or "-"
    
    lat = data.get("odp_lat")
    lon = data.get("odp_long")
    latlong = f"{lat:.6f},{lon:.6f}" if (lat and lon) else "-8.666807,115.181211"
    
    jarak = data.get("odp_distance_m")
    jarak_str = f"{jarak} m" if jarak is not None else "33 m"
    odp_name = data.get("odp_name", "ODP-UBN-FAR/08") or "ODP-UBN-FAR/08"

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

    card_x = 55
    card_w = width - (card_x * 2)
    card_h = 58
    gap = 14
    split_x = card_x + int(card_w * 0.52)
    start_y = 238

    for i, (lbl, val) in enumerate(items):
        y = start_y + i * (card_h + gap)
        
        # Background kartu kanan (putih)
        draw.rounded_rectangle([(card_x, y), (card_x + card_w, y + card_h)], radius=8, fill=white)
        # Background label kiri (abu-abu)
        draw.rounded_rectangle([(card_x, y), (split_x, y + card_h)], radius=8, fill=gray_label)
        draw.rectangle([(split_x - 10, y), (split_x, y + card_h)], fill=gray_label)
        draw.line([(split_x, y), (split_x, y + card_h)], fill=border_color, width=1)
        
        # Label teks
        bbox_l = draw.textbbox((0, 0), lbl, font=font_label)
        draw.text((card_x + 18, y + (card_h - (bbox_l[3] - bbox_l[1])) // 2 - 1), lbl, fill=text_gray, font=font_label)
        
        # Value teks
        val_str = str(val)
        bbox_v = draw.textbbox((0, 0), val_str, font=font_val)
        draw.text((split_x + 18, y + (card_h - (bbox_v[3] - bbox_v[1])) // 2 - 1), val_str, fill=text_dark, font=font_val)

    # ── 4. Timestamp Bawah ───────────────────────────────────────────────
    curr_y = start_y + len(items) * (card_h + gap) + 6
    ts2 = now.strftime("%H:%M:%S WIB")
    bbox_ts2 = draw.textbbox((0, 0), ts2, font=font_ts_bot)
    draw.text((width - 55 - (bbox_ts2[2] - bbox_ts2[0]), curr_y), ts2, fill=white, font=font_ts_bot)

    # ── 5. Garis Pembatas & Pesan Normal ─────────────────────────────────
    curr_y += 45
    draw.line([(55, curr_y), (width - 55, curr_y)], fill=(255, 255, 255, 90), width=1)
    
    curr_y += 32
    verdict = "Layanan internet anda dalam kondisi normal."
    bbox_vd = draw.textbbox((0, 0), verdict, font=font_verdict)
    draw.text(((width - (bbox_vd[2] - bbox_vd[0])) // 2, curr_y), verdict, fill=white, font=font_verdict)

    # ── 6. Tombol OK Putih ───────────────────────────────────────────────
    curr_y += 68
    btn_w, btn_h = 132, 54
    bx = (width - btn_w) // 2
    draw.rounded_rectangle([(bx, curr_y), (bx + btn_w, curr_y + btn_h)], radius=6, fill=white)
    bbox_ok = draw.textbbox((0, 0), "Ok", font=font_btn_ok)
    draw.text((bx + (btn_w - (bbox_ok[2] - bbox_ok[0])) // 2, curr_y + (btn_h - (bbox_ok[3] - bbox_ok[1])) // 2 - 1), "Ok", fill=text_dark, font=font_btn_ok)

    # ── 7. UID Hash ──────────────────────────────────────────────────────
    curr_y += 185
    uid = data.get("_raw", {}).get("uid", "1789894156.430d9c5e5ac4e9b03243d9182b41a67ceda50773")
    bbox_uid = draw.textbbox((0, 0), uid, font=font_uid)
    draw.text(((width - (bbox_uid[2] - bbox_uid[0])) // 2, curr_y), uid, fill=(255, 255, 255, 210), font=font_uid)

    # ── 8. Tombol Menu Utama Bawah ───────────────────────────────────────
    curr_y += 45
    menu_h = 70
    draw.rounded_rectangle([(card_x, curr_y), (card_x + card_w, curr_y + menu_h)], radius=12, fill=white, outline=border_color, width=1)
    
    menu_text = "Kembali Ke Menu Utama"
    bbox_m = draw.textbbox((0, 0), menu_text, font=font_menu)
    total_w = 22 + 12 + (bbox_m[2] - bbox_m[0])
    start_x = (width - total_w) // 2
    
    # Gambar panah manual
    draw_arrow_left(draw, start_x, curr_y + menu_h // 2, size=18, color=(211, 47, 47))
    # Teks merah
    draw.text((start_x + 34, curr_y + (menu_h - (bbox_m[3] - bbox_m[1])) // 2 - 1), menu_text, fill=(211, 47, 47), font=font_menu)

    img.save(output_file, "PNG")
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
    }
    generate_scc_image(sample_data, "mock_scc.png")
    print("PNG v2 generated successfully!")
