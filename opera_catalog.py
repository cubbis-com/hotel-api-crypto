"""
Agnia Guesthouse Catalog & Real-Time PostgreSQL Integration
Menghubungkan inventaris kamar, tarif, season, dan paket diskon secara dinamis
dari database PostgreSQL (tenant_agnia_guesthouse) menggunakan user AI (hotel_ai_agent).
"""

import logging
from typing import List, Dict, Any, Optional
from config import settings
from db_hotel_service import HotelDatabaseService

logger = logging.getLogger("opera_catalog")

# Fallback static definition jika database PostgreSQL sedang tidak dapat dijangkau
DEFAULT_ROOM_TYPES = [
    {
        "code": "STD-FAN",
        "name": "Standard Twin / Single Room (Fan)",
        "bed": "1 Twin Bed / 2 Single Bed",
        "capacity": "Maksimal 1 Dewasa + 1 Anak",
        "price_per_night": 115000,
        "extra_bed_price": 75000,
        "facilities": [
            "Kipas Angin (Fan)",
            "Kasur Single / Twin",
            "Meja Kerja",
            "Stopkontak Samping Kasur",
            "Kamar Mandi Luar (Shared Bathroom)",
            "High-speed Wi-Fi gratis"
        ],
        "available_units": 2
    },
    {
        "code": "DLX-TWN",
        "name": "Deluxe Twin Room (AC)",
        "bed": "2 Single Bed (Twin)",
        "capacity": "Maksimal 2 Dewasa + 1 Anak",
        "price_per_night": 160000,
        "extra_bed_price": 75000,
        "facilities": [
            "Pendingin Ruangan (AC)",
            "2 Kasur Single Bersih",
            "Meja Kerja",
            "Stopkontak Samping Kasur",
            "Kamar Mandi Luar (Shared Bathroom)",
            "High-speed Wi-Fi gratis"
        ],
        "available_units": 2
    },
    {
        "code": "SUP-DBL",
        "name": "Superior Double Room (AC)",
        "bed": "1 Double Bed (Ranjang Besar)",
        "capacity": "Maksimal 2 Dewasa + 1 Anak",
        "price_per_night": 235000,
        "extra_bed_price": 75000,
        "facilities": [
            "Pendingin Ruangan (AC)",
            "1 Ranjang Besar (Double Bed)",
            "Ruangan Lebih Lega (14 m²)",
            "Meja Kerja & Cermin",
            "Kamar Mandi Luar (Shared Bathroom)",
            "High-speed Wi-Fi gratis"
        ],
        "available_units": 2
    }
]

HOTEL_POLICIES = {
    "check_in_time": settings.CHECK_IN_TIME,
    "check_out_time": settings.CHECK_OUT_TIME,
    "extra_bed_price": settings.EXTRA_BED_PRICE,
    "cancellation_policy": settings.CANCELLATION_POLICY
}

def get_room_types() -> List[Dict[str, Any]]:
    """Mengambil master tipe kamar riil dari PostgreSQL atau fallback ke default."""
    try:
        db_rooms = HotelDatabaseService.get_room_types_and_inventory()
        if db_rooms:
            return db_rooms
    except Exception as e:
        logger.warning(f"Fallback to default rooms: {e}")
    return DEFAULT_ROOM_TYPES

# Alias untuk backward compatibility
ROOM_TYPES = get_room_types()

def get_catalog_context_str(checkin_date: Optional[str] = None, checkout_date: Optional[str] = None) -> str:
    """
    Mengonversi katalog kamar real-time, season aktif, paket promo,
    serta STATUS KETERSEDIAAN KAMAR FISIK REAL-TIME (anti-overbooking & anti-penumpukan)
    ke format teks yang dipahami oleh LLM Garda.
    """
    rooms = get_room_types()
    seasons = []
    packages = []
    avail_summary = ""

    try:
        seasons = HotelDatabaseService.get_active_seasons()
        packages = HotelDatabaseService.get_active_packages()
    except Exception as e:
        logger.warning(f"Could not load seasons/packages from DB: {e}")

    try:
        avail_summary = HotelDatabaseService.get_availability_summary_for_llm(checkin_date, checkout_date)
    except Exception as e:
        logger.warning(f"Could not load availability summary from DB: {e}")

    lines = []

    # 1. Jika ada info ketersediaan kamar riil di tanggal tertentu, taruh paling atas sebagai prioritas utama
    if avail_summary:
        lines.append(avail_summary)
        lines.append("")

    lines.append(f"KATALOG TIPE KAMAR & TARIF {settings.HOTEL_NAME.upper()} (TOTAL 6 UNIT KAMAR):")
    for r in rooms:
        lines.append(f"- Tipe: {r['name']} ({r['code']})")
        lines.append(f"  Tempat Tidur: {r['bed']}")
        lines.append(f"  Kapasitas: {r['capacity']}")
        lines.append(f"  Tarif Dasar: Rp {r['price_per_night']:,}/malam")
        if r.get("extra_bed_price"):
            lines.append(f"  Extra Bed: Rp {r['extra_bed_price']:,}/malam")
        lines.append(f"  Fasilitas: {', '.join(r['facilities'][:5])}")
        lines.append(f"  Total Fisik Properti: {r.get('available_units', 2)} unit")

    if seasons:
        lines.append("")
        lines.append("INFORMASI SEASON & KALENDER TARIF AKTIF:")
        for s in seasons[:3]:
            end_txt = f" s/d {s['end_date']}" if s.get('end_date') else ""
            lines.append(f"- {s['name']} (Mulai: {s['start_date']}{end_txt})")
            if s.get("rate_multiplier") and s["rate_multiplier"] != 1.0:
                lines.append(f"  Pengali Harga Season: {s['rate_multiplier']}x")
            if s.get("flat_surcharge") and s["flat_surcharge"] > 0:
                lines.append(f"  Biaya Tambahan Season: Rp {s['flat_surcharge']:,}/malam")

    if packages:
        lines.append("")
        lines.append("PAKET DISKON & PROMOSI TERSEDIA:")
        for p in packages:
            lines.append(f"- {p['name']} ({p.get('code', '')}): {p.get('description', '')}")

    lines.append("")
    lines.append("INFORMASI PROPERTI & KEBIJAKAN KHUSUS:")
    lines.append(f"- Lokasi: Perumahan Pelita Indah Blok A No. 13 RT.13 Kel. Sepinggan Raya, Balikpapan Selatan (1.5 km dari Bandara Sultan Aji Muhammad Sulaiman Sepinggan / BPN).")
    lines.append(f"- Zona Waktu Hotel: WITA (Waktu Indonesia Tengah / UTC+8). 1 jam lebih cepat dibanding WIB (Jakarta/Jawa/Sumatera) dan 1 jam lebih lambat dibanding WIT (Maluku/Papua).")
    lines.append(f"- Waktu Check-In: {HOTEL_POLICIES['check_in_time']} (setara pukul 13:00 - 19:00 WIB).")
    lines.append(f"- Waktu Check-Out: {HOTEL_POLICIES['check_out_time']} (setara pukul 11:00 - 11:30 WIB).")
    lines.append(f"- Biaya Extra Bed Standar: Rp {HOTEL_POLICIES['extra_bed_price']:,}/malam")
    lines.append(f"- Kebijakan Pembatalan & Syariah: {HOTEL_POLICIES['cancellation_policy']}")
    lines.append("- Fasilitas Umum: Wi-Fi gratis seluruh area, Area parkir aman, Teras, Resepsionis, Kopi/teh di lobi, Layanan Antar-Jemput Bandara Sepinggan.")
    return "\n".join(lines)

