"""
Image Mock Generator untuk SCC Telkom menggunakan Pillow (Pure Python)
Menghasilkan file gambar PNG yang persis dengan tampilan asli web SCC.
"""

from datetime import datetime
from PIL import Image, ImageDraw, ImageFont

def generate_scc_image(data: dict, output_file: str = "mock_scc.png") -> str:
    # Ukuran kanvas menyerupai rasio layar smartphone (lebar 720, tinggi 1560)
    width = 720
    height = 1560
    
    # Warna palet
    bg_red = (219, 68, 85)       # #db4455
    white = (255, 255, 255)
    gray_label = (233, 236, 239) # #e9ecef
    text_dark = (40, 40, 40)
    text_gray = (73, 80, 87)
    border_color = (206, 212, 218)
    
    # Buat image kanvas
    img = Image.new("RGB", (width, height), bg_red)
    draw = ImageDraw.Draw(img)
    
    # 1. Header Bar Logo (Tinggi 110px)
    draw.rectangle([(0, 0), (width, 110)], fill=white)
    draw.line([(0, 110), (width, 110)], fill=border_color, width=1)
    
    # Tempelkan Logo
    try:
        logo1 = Image.open("logo1.png").convert("RGBA")
        logo2 = Image.open("logo2.png").convert("RGBA")
        
        # Resize logo proporsional
        ratio1 = 56 / logo1.height
        logo1 = logo1.resize((int(logo1.width * ratio1), 56), Image.Resampling.LANCZOS)
        
        ratio2 = 56 / logo2.height
        logo2 = logo2.resize((int(logo2.width * ratio2), 56), Image.Resampling.LANCZOS)
        
        img.paste(logo1, (36, 27), logo1)
        img.paste(logo2, (width - logo2.width - 36, 27), logo2)
    except Exception:
        pass # jika logo tidak ada, biarkan putih
        
    # Fonts
    try:
        font_title = ImageFont.truetype("arial.ttf", 36)
        font_ts = ImageFont.truetype("arial.ttf", 22)
        font_label = ImageFont.truetype("arial.ttf", 22)
        font_val = ImageFont.truetype("arial.ttf", 22)
        font_verdict = ImageFont.truetype("arial.ttf", 24)
        font_btn = ImageFont.truetype("arial.ttf", 24)
        font_uid = ImageFont.truetype("arial.ttf", 18)
        font_bottom = ImageFont.truetype("arialbd.ttf", 26)
    except Exception:
        font_title = ImageFont.load_default()
        font_ts = font_label = font_val = font_verdict = font_btn = font_uid = font_bottom = font_title

    # 2. Judul Utama
    title_text = "Hasil Pengecekan Internet Anda"
    bbox = draw.textbbox((0, 0), title_text, font=font_title)
    t_w = bbox[2] - bbox[0]
    draw.text(((width - t_w) // 2, 145), title_text, fill=white, font=font_title)
    
    # Garis bawah judul
    draw.line([(50, 195), (width - 50, 195)], fill=(255, 255, 255, 180), width=2)
    
    # Timestamp atas
    now = datetime.now()
    ts1 = now.strftime("%Y-%m-%d %H:%M:%S WIB")
    bbox_ts = draw.textbbox((0, 0), ts1, font=font_ts)
    ts_w = bbox_ts[2] - bbox_ts[0]
    draw.text((width - ts_w - 50, 210), ts1, fill=white, font=font_ts)
    
    # 3. Kotak Data
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
    
    start_y = 250
    card_h = 56
    gap = 14
    margin_x = 50
    split_x = margin_x + 320
    card_w = width - (margin_x * 2)
    
    for i, (label, val) in enumerate(items):
        y = start_y + i * (card_h + gap)
        
        # Background kanan (putih)
        draw.rounded_rectangle([(margin_x, y), (margin_x + card_w, y + card_h)], radius=8, fill=white)
        # Background kiri (abu-abu label)
        draw.rounded_rectangle([(margin_x, y), (split_x, y + card_h)], radius=8, fill=gray_label)
        # Rapikan sudut kanan label agar rata
        draw.rectangle([(split_x - 10, y), (split_x, y + card_h)], fill=gray_label)
        # Garis batas vertikal
        draw.line([(split_x, y), (split_x, y + card_h)], fill=border_color, width=1)
        
        # Teks Label
        draw.text((margin_x + 16, y + 16), label, fill=text_gray, font=font_label)
        # Teks Value
        draw.text((split_x + 16, y + 16), str(val), fill=text_dark, font=font_val)

    # 4. Timestamp bawah
    ts2 = now.strftime("%H:%M:%S WIB")
    bbox_ts2 = draw.textbbox((0, 0), ts2, font=font_ts)
    ts2_w = bbox_ts2[2] - bbox_ts2[0]
    curr_y = start_y + len(items) * (card_h + gap) + 10
    draw.text((width - ts2_w - 50, curr_y), ts2, fill=white, font=font_ts)
    
    # 5. Verdict
    curr_y += 50
    draw.line([(50, curr_y), (width - 50, curr_y)], fill=(255, 255, 255, 80), width=1)
    curr_y += 30
    verdict = "Layanan internet anda dalam kondisi normal."
    bbox_v = draw.textbbox((0, 0), verdict, font=font_verdict)
    v_w = bbox_v[2] - bbox_v[0]
    draw.text(((width - v_w) // 2, curr_y), verdict, fill=white, font=font_verdict)
    
    # 6. Tombol OK
    curr_y += 65
    btn_w = 130
    btn_h = 50
    btn_x = (width - btn_w) // 2
    draw.rounded_rectangle([(btn_x, curr_y), (btn_x + btn_w, curr_y + btn_h)], radius=6, fill=white)
    bbox_btn = draw.textbbox((0, 0), "Ok", font=font_btn)
    draw.text((btn_x + (btn_w - (bbox_btn[2] - bbox_btn[0])) // 2, curr_y + 11), "Ok", fill=text_dark, font=font_btn)
    
    # 7. UID
    curr_y += 180
    uid = data.get("_raw", {}).get("uid", "1789894156.430d9c5e5ac4e9b03243d9182b41a67ceda50773")
    bbox_uid = draw.textbbox((0, 0), uid, font=font_uid)
    draw.text(((width - (bbox_uid[2] - bbox_uid[0])) // 2, curr_y), uid, fill=(255, 255, 255, 210), font=font_uid)
    
    # 8. Tombol Bottom Menu
    curr_y += 45
    btn_m_h = 68
    draw.rounded_rectangle([(margin_x, curr_y), (width - margin_x, curr_y + btn_m_h)], radius=12, fill=white, outline=border_color, width=1)
    menu_text = "←  Kembali Ke Menu Utama"
    bbox_m = draw.textbbox((0, 0), menu_text, font=font_bottom)
    draw.text(((width - (bbox_m[2] - bbox_m[0])) // 2, curr_y + 18), menu_text, fill=(211, 47, 47), font=font_bottom)
    
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
    print("PNG generated: mock_scc.png")
