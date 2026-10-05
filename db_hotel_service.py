"""
Database Service Khusus AI (hotel_ai_agent)
Terhubung ke PostgreSQL Railway dengan schema tenant_agnia_guesthouse.
Menyediakan fungsionalitas pencarian kamar, cek kamar kosong, season, harga & diskon,
pembuatan reservasi, dan pembayaran/folio.
"""

import logging
import uuid
import datetime
from decimal import Decimal
from typing import List, Dict, Any, Optional
import psycopg2
from psycopg2.extras import RealDictCursor
from config import settings

logger = logging.getLogger("db_hotel_service")

def get_connection():
    """Membuka koneksi ke PostgreSQL menggunakan user hotel_ai_agent."""
    dsn = settings.postgres_connection_string
    return psycopg2.connect(dsn, connect_timeout=10)

class HotelDatabaseService:
    @staticmethod
    def get_room_types_and_inventory() -> List[Dict[str, Any]]:
        """
        Mengambil master tipe kamar beserta jumlah kamar kosong (vacant) saat ini.
        """
        schema = settings.POSTGRES_SCHEMA
        query = f"""
        SELECT 
            rt.code,
            rt.name,
            rt.bed_type,
            COALESCE(rt.base_capacity_adults, 2) AS adults,
            COALESCE(rt.base_capacity_children, 1) AS children,
            COALESCE(rt.base_rate, 200000) AS base_rate,
            COALESCE(rt.extra_bed_price, 100000) AS extra_bed_price,
            rt.description,
            rt.amenities,
            COUNT(r.id) FILTER (WHERE COALESCE(r.is_inactive, false) = false) AS total_units
        FROM "{schema}".hotel_room_types rt
        LEFT JOIN "{schema}".hotel_rooms r 
            ON r.room_type_id = rt.id AND r.tenant_id = rt.tenant_id
        WHERE rt.tenant_id = %s AND COALESCE(rt.is_active, true) = true
        GROUP BY rt.id
        ORDER BY rt.sort_key ASC, rt.base_rate ASC;
        """
        try:
            with get_connection() as conn:
                with conn.cursor(cursor_factory=RealDictCursor) as cur:
                    cur.execute(query, (settings.TENANT_ID,))
                    rows = cur.fetchall()
                    result = []
                    for row in rows:
                        facilities = []
                        if row["amenities"]:
                            if isinstance(row["amenities"], list):
                                facilities = [str(x) for x in row["amenities"]]
                            elif isinstance(row["amenities"], dict):
                                facilities = [f"{k}: {v}" for k, v in row["amenities"].items()]
                        else:
                            facilities = [
                                "AC Dingin",
                                "TV",
                                "Kamar mandi shower pribadi",
                                "Wi-Fi berkecepatan tinggi gratis",
                                "Kopi/teh di lobi"
                            ]

                        result.append({
                            "code": row["code"],
                            "name": row["name"],
                            "bed": row["bed_type"] or "Queen Bed",
                            "capacity": f"Maksimal {row['adults']} Dewasa" + (f" + {row['children']} Anak" if row['children'] else ""),
                            "price_per_night": int(row["base_rate"]),
                            "extra_bed_price": int(row["extra_bed_price"]),
                            "facilities": facilities,
                            "available_units": int(row["total_units"] or 2),
                            "description": row["description"] or ""
                        })
                    return result
        except Exception as e:
            logger.error(f"Error fetching room types from PostgreSQL: {e}")
            return []

    @staticmethod
    def get_active_seasons() -> List[Dict[str, Any]]:
        """
        Mengambil daftar season kalender aktif dari database hotel.
        """
        schema = settings.POSTGRES_SCHEMA
        query = f"""
        SELECT 
            name, 
            alias, 
            start_date, 
            end_date, 
            COALESCE(rate_multiplier, 1.0) AS rate_multiplier,
            COALESCE(flat_surcharge, 0.0) AS flat_surcharge,
            description
        FROM "{schema}".hotel_config_seasons
        WHERE tenant_id = %s 
          AND is_active = true
          AND (end_date IS NULL OR end_date >= CURRENT_DATE)
        ORDER BY start_date ASC;
        """
        try:
            with get_connection() as conn:
                with conn.cursor(cursor_factory=RealDictCursor) as cur:
                    cur.execute(query, (settings.TENANT_ID,))
                    rows = cur.fetchall()
                    return [
                        {
                            "name": r["name"],
                            "alias": r["alias"],
                            "start_date": str(r["start_date"]),
                            "end_date": str(r["end_date"]) if r["end_date"] else None,
                            "rate_multiplier": float(r["rate_multiplier"]),
                            "flat_surcharge": int(r["flat_surcharge"]),
                            "description": r["description"] or ""
                        }
                        for r in rows
                    ]
        except Exception as e:
            logger.error(f"Error fetching seasons from PostgreSQL: {e}")
            return []

    @staticmethod
    def get_active_packages() -> List[Dict[str, Any]]:
        """
        Mengambil daftar promo dan paket diskon aktif di hotel.
        """
        schema = settings.POSTGRES_SCHEMA
        query = f"""
        SELECT 
            name, 
            alias, 
            description
        FROM "{schema}".hotel_config_packages
        WHERE tenant_id = %s AND is_active = true;
        """
        try:
            with get_connection() as conn:
                with conn.cursor(cursor_factory=RealDictCursor) as cur:
                    cur.execute(query, (settings.TENANT_ID,))
                    rows = cur.fetchall()
                    return [
                        {
                            "name": r["name"],
                            "code": r["alias"],
                            "description": r["description"] or ""
                        }
                        for r in rows
                    ]
        except Exception as e:
            logger.error(f"Error fetching packages from PostgreSQL: {e}")
            return []

    @staticmethod
    def get_extra_charges() -> List[Dict[str, Any]]:
        """
        Mengambil daftar layanan tambahan, rental kendaraan, dan biaya ekstra aktif.
        """
        schema = settings.POSTGRES_SCHEMA
        query = f"""
        SELECT 
            code, 
            name, 
            category,
            COALESCE(price, 0) AS price,
            charge_type,
            description
        FROM "{schema}".hotel_config_extra_charges
        WHERE tenant_id = %s AND is_active = true
        ORDER BY created_at ASC;
        """
        try:
            with get_connection() as conn:
                with conn.cursor(cursor_factory=RealDictCursor) as cur:
                    cur.execute(query, (settings.TENANT_ID,))
                    rows = cur.fetchall()
                    return [
                        {
                            "code": r["code"],
                            "name": r["name"],
                            "category": r["category"],
                            "price": int(r["price"]),
                            "charge_type": r["charge_type"],
                            "description": r["description"] or ""
                        }
                        for r in rows
                    ]
        except Exception as e:
            logger.error(f"Error fetching extra charges from PostgreSQL: {e}")
            return []

    @staticmethod
    def get_available_physical_room(room_type_code: str, checkin_date: str, checkout_date: str) -> Optional[Dict[str, Any]]:
        """
        Mencari 1 unit kamar fisik yang BEBAS (tidak ada konflik/overlap reservasi aktif)
        pada rentang interval tanggal [checkin_date, checkout_date).
        Rumus overlap interval hotel: rsv.check_in_date < checkout AND rsv.check_out_date > checkin.
        """
        schema = settings.POSTGRES_SCHEMA
        find_free_room_sql = f"""
        SELECT r.id, r.room_number, rt.code as room_type_code, rt.name as room_type_name, rt.base_rate
        FROM "{schema}".hotel_rooms r
        JOIN "{schema}".hotel_room_types rt ON rt.id = r.room_type_id
        WHERE r.tenant_id = %s
          AND rt.code = %s
          AND r.is_active = true
          AND COALESCE(r.is_inactive, false) = false
          AND r.id NOT IN (
              SELECT DISTINCT rsv.room_id
              FROM "{schema}".hotel_reservations rsv
              WHERE rsv.tenant_id = %s
                AND rsv.room_id IS NOT NULL
                AND rsv.status IN ('confirmed', 'reserved', 'in_house', 'blocked')
                AND rsv.check_in_date < %s::date
                AND rsv.check_out_date > %s::date
          )
        ORDER BY r.room_number ASC
        LIMIT 1;
        """
        try:
            with get_connection() as conn:
                with conn.cursor(cursor_factory=RealDictCursor) as cur:
                    cur.execute(find_free_room_sql, (
                        settings.TENANT_ID,
                        room_type_code.upper(),
                        settings.TENANT_ID,
                        checkout_date,
                        checkin_date
                    ))
                    return cur.fetchone()
        except Exception as e:
            logger.error(f"Error finding free physical room: {e}")
            return None

    @staticmethod
    def get_all_rooms_availability_for_dates(checkin_date: str, checkout_date: str) -> List[Dict[str, Any]]:
        """
        Mengambil status ketersediaan real-time untuk SELURUH tipe kamar pada rentang tanggal tertentu.
        Mendeteksi unit fisik yang terisi vs unit yang masih bebas.
        """
        schema = settings.POSTGRES_SCHEMA
        query = f"""
        SELECT 
            rt.id as room_type_id,
            rt.code,
            rt.name,
            rt.base_rate,
            r.id as room_id,
            r.room_number,
            CASE WHEN occupied.room_id IS NOT NULL THEN true ELSE false END as is_occupied,
            occupied.guest_name,
            occupied.reservation_no
        FROM "{schema}".hotel_room_types rt
        JOIN "{schema}".hotel_rooms r ON r.room_type_id = rt.id AND r.tenant_id = rt.tenant_id
        LEFT JOIN (
            SELECT DISTINCT rsv.room_id, rsv.guest_name, rsv.reservation_no
            FROM "{schema}".hotel_reservations rsv
            WHERE rsv.tenant_id = %s
              AND rsv.room_id IS NOT NULL
              AND rsv.status IN ('confirmed', 'reserved', 'in_house', 'blocked')
              AND rsv.check_in_date < %s::date
              AND rsv.check_out_date > %s::date
        ) occupied ON occupied.room_id = r.id
        WHERE rt.tenant_id = %s AND rt.is_active = true AND COALESCE(r.is_inactive, false) = false
        ORDER BY rt.code, r.room_number;
        """
        try:
            with get_connection() as conn:
                with conn.cursor(cursor_factory=RealDictCursor) as cur:
                    cur.execute(query, (settings.TENANT_ID, checkout_date, checkin_date, settings.TENANT_ID))
                    rows = cur.fetchall()

                    grouped: Dict[str, Dict[str, Any]] = {}
                    for row in rows:
                        code = row["code"]
                        if code not in grouped:
                            grouped[code] = {
                                "code": code,
                                "name": row["name"],
                                "base_rate": int(row["base_rate"]),
                                "total_rooms": 0,
                                "available_rooms": 0,
                                "free_room_numbers": [],
                                "occupied_room_numbers": [],
                                "is_available": False
                            }
                        grouped[code]["total_rooms"] += 1
                        if row["is_occupied"]:
                            grouped[code]["occupied_room_numbers"].append(row["room_number"])
                        else:
                            grouped[code]["available_rooms"] += 1
                            grouped[code]["free_room_numbers"].append(row["room_number"])

                    for item in grouped.values():
                        item["is_available"] = item["available_rooms"] > 0

                    return list(grouped.values())
        except Exception as e:
            logger.error(f"Error checking all rooms availability: {e}")
            return []

    @staticmethod
    def get_upcoming_active_bookings(days: int = 14) -> List[Dict[str, Any]]:
        """
        Mengambil daftar seluruh reservasi aktif di hotel yang sedang/akan menginap
        mulai hari ini hingga N hari ke depan.
        """
        schema = settings.POSTGRES_SCHEMA
        query = f"""
        SELECT rsv.reservation_no, rsv.guest_name, rsv.room_number, 
               rsv.check_in_date, rsv.check_out_date, rt.code as room_type, rt.name as room_type_name
        FROM "{schema}".hotel_reservations rsv
        JOIN "{schema}".hotel_room_types rt ON rt.id = rsv.room_type_id
        WHERE rsv.tenant_id = %s
          AND rsv.status IN ('confirmed', 'reserved', 'in_house', 'blocked')
          AND rsv.check_out_date >= CURRENT_DATE
          AND rsv.check_in_date <= (CURRENT_DATE + interval '{days} days')
        ORDER BY rsv.room_number, rsv.check_in_date;
        """
        try:
            with get_connection() as conn:
                with conn.cursor(cursor_factory=RealDictCursor) as cur:
                    cur.execute(query, (settings.TENANT_ID,))
                    return cur.fetchall()
        except Exception as e:
            logger.error(f"Error fetching upcoming active bookings: {e}")
            return []

    @staticmethod
    def get_availability_summary_for_llm(checkin_date: Optional[str] = None, checkout_date: Optional[str] = None) -> str:
        """
        Menghasilkan ringkasan ketersediaan kamar real-time dalam format teks terstruktur
        yang disematkan ke dalam konteks Garda LLM agar tidak terjadi overbooking atau penumpukan kamar.
        """
        lines = []

        # 1. Jika ada rentang tanggal spesifik yang ditanyakan
        if checkin_date and checkout_date:
            try:
                avail_list = HotelDatabaseService.get_all_rooms_availability_for_dates(checkin_date, checkout_date)
                lines.append("=============================================================")
                lines.append(f"STATUS KETERSEDIAAN KAMAR REAL-TIME UNTUK TANGGAL: {checkin_date} s/d {checkout_date}")
                lines.append("=============================================================")
                for a in avail_list:
                    if a["is_available"]:
                        lines.append(f"• {a['name']} ({a['code']}): ✅ TERSEDIA ({a['available_rooms']} unit tersedia) - Rp {a['base_rate']:,}/malam")
                    else:
                        lines.append(f"• {a['name']} ({a['code']}): ❌ PENUH / SOLD OUT (0 unit tersedia) - Rp {a['base_rate']:,}/malam")
                
                lines.append("")
                lines.append("PANDUAN & ATURAN WAJIB GARDA PADA PERIODE INI:")
                lines.append("- STATUS DI ATAS ADALAH KEBENARAN MUTLAK SISTEM. IKUTI 100% STATUS TERSEBUT!")
                lines.append("- Jika kamar bertanda '✅ TERSEDIA' (seperti Deluxe Twin Room atau Standard Twin Room), kamar tersebut PASTI BISA DIPESAN. Segera proses/rekap pemesanannya jika tamu memilihnya!")
                lines.append("- Jika kamar bertanda '❌ PENUH / SOLD OUT' (seperti Superior Double Room), DILARANG KERAS menawarkan atau menyetujui pemesanan tipe tersebut pada tanggal ini.")
                lines.append("- DILARANG MENYEBUT NOMOR KAMAR FISIK TERTENTU (seperti kamar 101, 103, 104, 106) kepada tamu, karena nomor kamar ditetapkan oleh Front Desk saat check-in.")
                lines.append("- JIKA TIPE KAMAR YANG DIMINATI PENUH, TAWARKAN SOLUSI:")
                lines.append("  1. REKOMENDASIKAN TIPE KAMAR LAIN yang masih '✅ TERSEDIA' di atas (misal: Deluxe Twin Room AC).")
                lines.append("  2. ATAU TAWARKAN GESER TANGGAL: Sarankan tamu memajukan atau memundurkan tanggal menginap sebelum/sesudah tanggal penuh tersebut.")
                lines.append("  3. ATAU OPSI PINDAH KAMAR (SPLIT STAY): Jika menginap beberapa malam, tawarkan malam 1 di kamar A dan malam berikutnya pindah ke kamar B.")
                lines.append("=============================================================")
                return "\n".join(lines).strip()
            except Exception as e:
                logger.error(f"Error formatting date availability for LLM: {e}")

        # 2. Jika tanggal belum ditentukan oleh tamu
        lines.append("=============================================================")
        lines.append("RINGKASAN STATUS KETERSEDIAAN KAMAR TERKINI (HARI INI & BESOK):")
        lines.append("=============================================================")
        try:
            from zoneinfo import ZoneInfo
            tz = ZoneInfo(settings.HOTEL_TIMEZONE)
            now_dt = datetime.datetime.now(tz)
            today_str = now_dt.strftime("%Y-%m-%d")
            tomorrow_dt = now_dt + datetime.timedelta(days=1)
            tomorrow_str = tomorrow_dt.strftime("%Y-%m-%d")
            day_after_dt = now_dt + datetime.timedelta(days=2)
            day_after_str = day_after_dt.strftime("%Y-%m-%d")

            today_avail = HotelDatabaseService.get_all_rooms_availability_for_dates(today_str, tomorrow_str)
            tomorrow_avail = HotelDatabaseService.get_all_rooms_availability_for_dates(tomorrow_str, day_after_str)

            lines.append(f"• STATUS MALAM INI / HARI INI ({today_str} s/d {tomorrow_str}):")
            for a in today_avail:
                status_icon = f"✅ TERSEDIA ({a['available_rooms']} unit kosong)" if a["is_available"] else "❌ PENUH / SOLD OUT (0 unit kosong)"
                lines.append(f"  - {a['name']} ({a['code']}): {status_icon} - Rp {a['base_rate']:,}/malam")

            lines.append(f"• STATUS BESOK ({tomorrow_str} s/d {day_after_str}):")
            for a in tomorrow_avail:
                status_icon = f"✅ TERSEDIA ({a['available_rooms']} unit kosong)" if a["is_available"] else "❌ PENUH / SOLD OUT (0 unit kosong)"
                lines.append(f"  - {a['name']} ({a['code']}): {status_icon} - Rp {a['base_rate']:,}/malam")

            lines.append("")
            lines.append("PANDUAN MENJAWAB PERTANYAAN KETERSEDIAAN KAMAR UMUM (KAMAR KOSONG):")
            lines.append("1. Jika tamu menanyakan 'kamar kosong', 'ada kamar kosong?', atau ketersediaan umum:")
            lines.append("   Jawab dengan ramah, sebutkan gambaran ketersediaan kamar untuk malam ini dan besok sesuai data di atas.")
            lines.append("   Lalu tanyakan rencana tanggal check-in dan durasi menginap tamu secara hangat.")
            lines.append("2. DILARANG KERAS merespons dengan bingung, menanyakan 'apakah tempat tidur atau kamar', atau menolak memberi informasi ketersediaan!")
            lines.append("3. DILARANG menyebut nomor kamar fisik tertentu kepada tamu.")
            lines.append("=============================================================")
            return "\n".join(lines).strip()
        except Exception as e:
            logger.error(f"Error fetching default today/tomorrow availability: {e}")
            lines.append("- Periode tanggal menginap belum ditentukan oleh tamu.")
            lines.append("- Tanyakan rencana tanggal check-in dan tanggal check-out (atau durasi menginap) untuk melakukan pengecekan ketersediaan kamar.")
            lines.append("- DILARANG berasumsi kamar penuh atau kosong sebelum tamu memberikan tanggal yang jelas.")
            lines.append("- DILARANG menyebut nomor kamar fisik tertentu kepada tamu.")
            return "\n".join(lines).strip()

    @staticmethod
    def check_room_availability(room_type_code: str, checkin_date: str, checkout_date: str) -> Dict[str, Any]:
        """
        Memeriksa sisa kamar kosong pada rentang tanggal tertentu dengan memperhitungkan reservasi aktif.
        """
        schema = settings.POSTGRES_SCHEMA
        query = f"""
        WITH selected_type AS (
            SELECT id, code, name, base_rate FROM "{schema}".hotel_room_types 
            WHERE code = %s AND tenant_id = %s LIMIT 1
        ),
        total_rooms AS (
            SELECT count(*) as total_count FROM "{schema}".hotel_rooms r
            JOIN selected_type st ON st.id = r.room_type_id
            WHERE r.tenant_id = %s AND r.is_active = true AND COALESCE(r.is_inactive, false) = false
        ),
        booked_rooms AS (
            SELECT count(DISTINCT rsv.room_id) as booked_count
            FROM "{schema}".hotel_reservations rsv
            JOIN selected_type st ON st.id = rsv.room_type_id
            WHERE rsv.tenant_id = %s
              AND rsv.room_id IS NOT NULL
              AND rsv.status IN ('confirmed', 'reserved', 'in_house', 'blocked')
              AND rsv.check_in_date < %s::date
              AND rsv.check_out_date > %s::date
        )
        SELECT 
            st.code, 
            st.name, 
            st.base_rate,
            tr.total_count,
            br.booked_count,
            GREATEST(0, tr.total_count - br.booked_count) AS available_count
        FROM selected_type st
        CROSS JOIN total_rooms tr
        CROSS JOIN booked_rooms br;
        """
        try:
            with get_connection() as conn:
                with conn.cursor(cursor_factory=RealDictCursor) as cur:
                    cur.execute(query, (
                        room_type_code.upper(), 
                        settings.TENANT_ID, 
                        settings.TENANT_ID, 
                        settings.TENANT_ID, 
                        checkout_date, 
                        checkin_date
                    ))
                    row = cur.fetchone()
                    if row:
                        free_room = HotelDatabaseService.get_available_physical_room(room_type_code, checkin_date, checkout_date)
                        return {
                            "code": row["code"],
                            "name": row["name"],
                            "base_rate": int(row["base_rate"]),
                            "total_rooms": int(row["total_count"]),
                            "booked_rooms": int(row["booked_count"]),
                            "available_rooms": int(row["available_count"]),
                            "is_available": int(row["available_count"]) > 0,
                            "allocated_room": free_room["room_number"] if free_room else None
                        }
                    else:
                        return {"error": f"Tipe kamar {room_type_code} tidak ditemukan.", "is_available": False}
        except Exception as e:
            logger.error(f"Error checking availability: {e}")
            return {"error": str(e), "is_available": False}

    @staticmethod
    def create_reservation(
        guest_name: str,
        guest_phone: str,
        room_type_code: str,
        checkin_date: str,
        checkout_date: str,
        adults: int = 1,
        children: int = 0,
        special_requests: Optional[str] = None,
        estimated_total: float = 0.0,
        deposit_amount: float = 0.0,
        status: str = "reserved",
        booking_source: str = "Reservasi Online / WA",
        merchant_ref: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Menyimpan reservasi baru ke tabel hotel_reservations di PostgreSQL.
        Status awal saat request dari WA adalah 'reserved' / Reservasi Online.
        DILENGKAPI PENGECEKAN KONFLIK KAMAR FISIK REAL-TIME (ANTI DOUBLE-BOOKING & OVERBOOKING).
        """
        schema = settings.POSTGRES_SCHEMA
        find_type_sql = f"""
        SELECT id, base_rate FROM "{schema}".hotel_room_types 
        WHERE code = %s AND tenant_id = %s LIMIT 1;
        """
        insert_res_sql = f"""
        INSERT INTO "{schema}".hotel_reservations (
            id, tenant_id, reservation_no, guest_name, guest_phone,
            check_in_date, check_out_date, total_nights, room_type_id,
            room_id, room_number, num_adults, num_children, booking_source,
            nightly_rate, total_room_charge, grand_total, deposit_amount,
            status, special_requests, created_at, updated_at
        ) VALUES (
            %s, %s, %s, %s, %s,
            %s, %s, %s, %s,
            %s, %s, %s, %s, %s,
            %s, %s, %s, %s,
            %s, %s, %s, %s
        ) RETURNING id, reservation_no;
        """

        try:
            c_in = datetime.datetime.strptime(checkin_date, "%Y-%m-%d").date()
        except Exception:
            c_in = datetime.date.today()

        try:
            n = int(total_nights) if total_nights else 1
        except Exception:
            n = 1
        n = max(1, n)

        try:
            c_out = datetime.datetime.strptime(checkout_date, "%Y-%m-%d").date()
        except Exception:
            c_out = None

        # Check-out HARUS SELALU > check-in. Jika <= check-in, hitung pasti: checkin + nights
        if not c_out or c_out <= c_in:
            c_out = c_in + datetime.timedelta(days=n)
        else:
            n = (c_out - c_in).days
        total_nights = n

        reservation_id = str(uuid.uuid4())
        today_str = datetime.datetime.now().strftime("%Y%m%d")
        rand_suffix = str(uuid.uuid4())[:4].upper()
        reservation_no = f"RSV-{today_str}-{rand_suffix}"
        now = datetime.datetime.utcnow()

        final_notes = special_requests or ""
        if merchant_ref and merchant_ref not in final_notes:
            final_notes = f"TriPay Ref: {merchant_ref} | {final_notes}".strip(" |")

        try:
            with get_connection() as conn:
                with conn.cursor(cursor_factory=RealDictCursor) as cur:
                    # 1. Cari room type
                    cur.execute(find_type_sql, (room_type_code.upper(), settings.TENANT_ID))
                    rt = cur.fetchone()
                    if not rt:
                        cur.execute(f'SELECT id, base_rate FROM "{schema}".hotel_room_types WHERE tenant_id = %s LIMIT 1;', (settings.TENANT_ID,))
                        rt = cur.fetchone()
                    
                    room_type_id = rt["id"]
                    nightly_rate = float(rt["base_rate"] or 200000)
                    total_charge = estimated_total if estimated_total > 0 else (nightly_rate * total_nights)

                    # 2. Cari kamar fisik BEBAS yang tidak bertabrakan dengan reservasi orang lain
                    free_room = HotelDatabaseService.get_available_physical_room(
                        room_type_code=room_type_code,
                        checkin_date=str(c_in),
                        checkout_date=str(c_out)
                    )

                    if not free_room:
                        err_msg = f"Kamar tipe {room_type_code} sudah PENUH pada tanggal {c_in} s/d {c_out}. Seluruh unit fisik sudah terisi reservasi lain."
                        logger.warning(f"[Overbooking Prevention] Ditolak: {err_msg}")
                        raise ValueError(err_msg)

                    room_id = free_room["id"]
                    room_number = free_room["room_number"]

                    # 3. Insert reservasi
                    cur.execute(insert_res_sql, (
                        reservation_id, settings.TENANT_ID, reservation_no, guest_name, guest_phone,
                        c_in, c_out, total_nights, room_type_id,
                        room_id, room_number, adults, children, booking_source,
                        nightly_rate, total_charge, total_charge, deposit_amount,
                        status, final_notes, now, now
                    ))
                    created = cur.fetchone()
                    conn.commit()

                    logger.info(f"Reservasi berhasil dibuat: {reservation_no} (Kamar Bebas: {room_number}) untuk {guest_name} ({guest_phone})")
                    return {
                        "id": str(created["id"]),
                        "reservation_no": created["reservation_no"],
                        "room_number": room_number,
                        "room_id": str(room_id),
                        "check_in_date": str(c_in),
                        "check_out_date": str(c_out),
                        "total_nights": total_nights,
                        "grand_total": total_charge,
                        "status": status,
                        "booking_source": booking_source,
                        "guest_name": guest_name,
                        "guest_phone": guest_phone
                    }
        except Exception as e:
            logger.error(f"Error creating reservation in PostgreSQL: {e}")
            raise e

    @staticmethod
    def confirm_payment_and_activate_reservation(
        merchant_ref: str,
        payment_amount: float,
        payment_method: str = "QRIS TriPay",
        phone: Optional[str] = None,
        tripay_ref: Optional[str] = None
    ) -> Optional[Dict[str, Any]]:
        """
        Mengonfirmasi pembayaran resmi dari Webhook TriPay ke PostgreSQL:
        1. Mencari reservasi di tenant_agnia_guesthouse.hotel_reservations berdasarkan merchant_ref atau no HP.
        2. Mengubah status reservasi menjadi 'confirmed' (sehingga langsung masuk ke hotel/stay-view).
        3. Memastikan nomor kamar fisik (room_id & room_number) ter-assign dan kamar di-set 'reserved' di hotel_rooms.
        4. Membuka Folio tamu di hotel_folios dan mencatat transaksi deposit pembayaran di hotel_folio_transactions.
        """
        schema = settings.POSTGRES_SCHEMA
        clean_digits = "".join(ch for ch in (phone or "") if ch.isdigit())
        phone_pattern_8 = f"%{clean_digits[-8:]}%" if len(clean_digits) >= 8 else f"%{clean_digits}%"
        phone_pattern_4 = f"%{clean_digits[-4:]}%" if len(clean_digits) >= 4 else f"%{merchant_ref[-4:]}%"

        find_sql = f"""
        SELECT 
            r.id, r.reservation_no, r.guest_name, r.guest_phone,
            r.room_id, r.room_number, r.room_type_id,
            r.check_in_date, r.check_out_date, r.total_nights,
            r.grand_total, r.deposit_amount, r.status, r.special_requests
        FROM "{schema}".hotel_reservations r
        WHERE r.tenant_id = %s
          AND (
              r.special_requests LIKE %s
              OR r.reservation_no LIKE %s
              OR (r.guest_phone LIKE %s AND r.status IN ('reserved', 'pending'))
              OR (r.guest_phone LIKE %s AND r.status IN ('reserved', 'pending'))
              OR r.guest_phone LIKE %s
          )
        ORDER BY 
            CASE WHEN r.status = 'reserved' THEN 1 WHEN r.status = 'confirmed' THEN 2 ELSE 3 END ASC,
            r.created_at DESC
        LIMIT 1;
        """

        try:
            with get_connection() as conn:
                with conn.cursor(cursor_factory=RealDictCursor) as cur:
                    cur.execute(find_sql, (
                        settings.TENANT_ID,
                        f"%{merchant_ref}%",
                        f"%{merchant_ref}%",
                        phone_pattern_8,
                        phone_pattern_4,
                        f"%{merchant_ref[-4:]}%"
                    ))
                    rsv = cur.fetchone()
                    if not rsv:
                        logger.warning(f"[PMS Confirm] Reservasi tidak ditemukan untuk merchant_ref={merchant_ref}, phone={phone}")
                        return None

                    rsv_id = str(rsv["id"])
                    room_id = rsv["room_id"]
                    room_number = rsv["room_number"]
                    room_type_id = rsv["room_type_id"]

                    # 1. Pastikan kamar fisik ter-assign jika sebelumnya belum ada
                    if not room_id or not room_number:
                        find_vacant_room_sql = f"""
                        SELECT id, room_number FROM "{schema}".hotel_rooms
                        WHERE room_type_id = %s AND tenant_id = %s
                          AND id NOT IN (
                              SELECT res.room_id FROM "{schema}".hotel_reservations res
                              WHERE res.tenant_id = %s
                                AND res.id != %s
                                AND res.status IN ('confirmed', 'reserved', 'in_house', 'blocked')
                                AND res.check_in_date < %s
                                AND res.check_out_date > %s
                                AND res.room_id IS NOT NULL
                          )
                        ORDER BY room_number ASC LIMIT 1;
                        """
                        cur.execute(find_vacant_room_sql, (
                            room_type_id, settings.TENANT_ID,
                            settings.TENANT_ID, rsv_id,
                            rsv["check_out_date"], rsv["check_in_date"]
                        ))
                        available_room = cur.fetchone()
                        if available_room:
                            room_id = available_room["id"]
                            room_number = available_room["room_number"]

                    # 2. Update status reservasi menjadi 'confirmed'
                    notes = rsv.get("special_requests") or ""
                    paid_note = f"Lunas TriPay: {tripay_ref or merchant_ref} ({payment_method})"
                    if paid_note not in notes:
                        notes = f"{notes} | {paid_note}".strip(" |")

                    update_rsv_sql = f"""
                    UPDATE "{schema}".hotel_reservations
                    SET status = 'confirmed',
                        booking_source = 'Reservasi Online / WA',
                        deposit_amount = %s,
                        room_id = %s,
                        room_number = %s,
                        special_requests = %s,
                        updated_at = NOW()
                    WHERE id = %s;
                    """
                    cur.execute(update_rsv_sql, (
                        payment_amount,
                        room_id,
                        room_number,
                        notes,
                        rsv_id
                    ))

                    # 3. Update status kamar di hotel_rooms menjadi 'reserved'
                    if room_id:
                        cur.execute(f"""
                            UPDATE "{schema}".hotel_rooms
                            SET front_desk_status = 'reserved', updated_at = NOW()
                            WHERE id = %s AND front_desk_status = 'vacant';
                        """, (room_id,))

                    conn.commit()
                    logger.info(f"[PMS Confirm] Reservasi {rsv['reservation_no']} diupdate ke 'confirmed' (Kamar: {room_number}). Masuk ke Stay View!")

            # 4. Buka Folio dan Catat Pembayaran Deposit di PostgreSQL
            folio_info = None
            try:
                # Cek apakah folio sudah pernah dibuat
                with get_connection() as conn:
                    with conn.cursor(cursor_factory=RealDictCursor) as cur:
                        cur.execute(f'SELECT id, folio_no FROM "{schema}".hotel_folios WHERE reservation_id = %s LIMIT 1;', (rsv_id,))
                        existing_folio = cur.fetchone()
                
                if not existing_folio:
                    folio_info = HotelDatabaseService.create_folio_and_payment(
                        reservation_id=rsv_id,
                        guest_name=rsv["guest_name"],
                        room_number=room_number,
                        total_amount=float(rsv["grand_total"] or payment_amount),
                        payment_amount=float(payment_amount),
                        payment_method=f"{payment_method} ({tripay_ref or merchant_ref})"
                    )
                else:
                    folio_info = {"folio_no": existing_folio["folio_no"]}
            except Exception as fe:
                logger.warning(f"[PMS Confirm] Gagal buat folio otomatis: {fe}")

            return {
                "id": rsv_id,
                "reservation_no": rsv["reservation_no"],
                "guest_name": rsv["guest_name"],
                "guest_phone": rsv["guest_phone"],
                "room_id": str(room_id) if room_id else None,
                "room_number": room_number,
                "check_in_date": str(rsv["check_in_date"]),
                "check_out_date": str(rsv["check_out_date"]),
                "grand_total": float(rsv["grand_total"] or payment_amount),
                "deposit_amount": float(payment_amount),
                "status": "confirmed",
                "folio_no": folio_info.get("folio_no") if folio_info else None
            }
        except Exception as e:
            logger.error(f"[PMS Confirm] Error mengonfirmasi reservasi di PostgreSQL: {e}")
            return None

    @staticmethod
    def get_latest_reservation_by_phone(phone: str) -> Optional[Dict[str, Any]]:
        """
        Mencari data reservasi aktif terbaru tamu di PostgreSQL berdasarkan nomor telepon.
        Digunakan untuk pemulihan (resend) QRIS otomatis meskipun container aplikasi baru saja restart.
        """
        clean_digits = "".join(ch for ch in phone if ch.isdigit())
        schema = settings.POSTGRES_SCHEMA
        query = f"""
        SELECT 
            r.id,
            r.reservation_no,
            r.guest_name,
            r.guest_phone,
            r.check_in_date,
            r.check_out_date,
            r.total_nights,
            r.num_adults,
            r.grand_total,
            r.deposit_amount,
            r.status,
            rt.name as room_type_name,
            rt.code as room_type_code
        FROM "{schema}".hotel_reservations r
        LEFT JOIN "{schema}".hotel_room_types rt ON rt.id = r.room_type_id
        WHERE r.tenant_id = %s
          AND r.status IN ('confirmed', 'reserved')
          AND (r.guest_phone LIKE %s OR r.guest_phone LIKE %s)
        ORDER BY r.created_at DESC
        LIMIT 1;
        """
        try:
            with get_connection() as conn:
                with conn.cursor(cursor_factory=RealDictCursor) as cur:
                    cur.execute(query, (settings.TENANT_ID, f"%{clean_digits[-8:]}%", f"%{clean_digits[-4:]}%"))
                    row = cur.fetchone()
                    if row:
                        return dict(row)
        except Exception as e:
            logger.error(f"Error searching latest reservation in PostgreSQL for {phone}: {e}")
        return None

    @staticmethod
    def create_folio_and_payment(
        reservation_id: str,
        guest_name: str,
        room_number: Optional[str],
        total_amount: float,
        payment_amount: float,
        payment_method: str = "QRIS / Transfer Bank"
    ) -> Dict[str, Any]:
        """
        Membuka folio dan mencatat transaksi pembayaran/deposit ke PostgreSQL.
        """
        schema = settings.POSTGRES_SCHEMA
        insert_folio_sql = f"""
        INSERT INTO "{schema}".hotel_folios (
            id, tenant_id, folio_no, reservation_id, room_number,
            guest_name, total_charges, total_payments, balance,
            status, opened_at
        ) VALUES (
            %s, %s, %s, %s, %s,
            %s, %s, %s, %s,
            %s, %s
        ) RETURNING id, folio_no;
        """

        insert_txn_sql = f"""
        INSERT INTO "{schema}".hotel_folio_transactions (
            id, tenant_id, folio_id, transaction_date, transaction_type,
            category, description, amount, total_amount, reference_no,
            created_by_name, created_at
        ) VALUES (
            %s, %s, %s, %s, %s,
            %s, %s, %s, %s, %s,
            %s, %s
        ) RETURNING id, reference_no;
        """

        folio_id = str(uuid.uuid4())
        today_str = datetime.datetime.now().strftime("%Y%m%d")
        rand_suffix = str(uuid.uuid4())[:4].upper()
        folio_no = f"FOL-{today_str}-{rand_suffix}"
        balance = total_amount - payment_amount
        now = datetime.datetime.utcnow()

        try:
            with get_connection() as conn:
                with conn.cursor(cursor_factory=RealDictCursor) as cur:
                    # 1. Buka Folio
                    cur.execute(insert_folio_sql, (
                        folio_id, settings.TENANT_ID, folio_no, reservation_id, room_number,
                        guest_name, total_amount, payment_amount, balance,
                        "open", now
                    ))
                    created_folio = cur.fetchone()

                    # 2. Catat Transaksi Pembayaran / Deposit
                    txn_id = str(uuid.uuid4())
                    ref_no = f"PAY-{today_str}-{rand_suffix}"
                    cur.execute(insert_txn_sql, (
                        txn_id, settings.TENANT_ID, folio_id, now.date(), "payment",
                        "deposit", f"Pembayaran Deposit via {payment_method}", payment_amount, payment_amount, ref_no,
                        "WhatsApp AI Garda", now
                    ))
                    created_txn = cur.fetchone()
                    conn.commit()

                    logger.info(f"Folio {folio_no} dibuka & transaksi pembayaran {ref_no} dicatat.")
                    return {
                        "folio_id": str(created_folio["id"]),
                        "folio_no": created_folio["folio_no"],
                        "total_amount": total_amount,
                        "payment_amount": payment_amount,
                        "balance": balance,
                        "payment_ref": created_txn["reference_no"]
                    }
        except Exception as e:
            logger.error(f"Error creating folio & payment in PostgreSQL: {e}")
            raise e

    @staticmethod
    def get_tenant_status() -> Dict[str, Any]:
        """
        Mengambil data profil & status tenant dari public.tenants beserta statistik real-time kamar dari schema tenant.
        """
        schema = settings.POSTGRES_SCHEMA
        tenant_id = settings.TENANT_ID

        tenant_info = {
            "tenant_id": tenant_id,
            "slug": settings.HOTEL_SLUG,
            "name": settings.HOTEL_NAME,
            "legal_name": settings.HOTEL_LEGAL_NAME,
            "status": settings.HOTEL_STATUS,
            "timezone": settings.HOTEL_TIMEZONE,
            "locale": settings.HOTEL_LOCALE,
            "currency": settings.HOTEL_CURRENCY,
            "address": settings.HOTEL_ADDRESS,
            "phone": settings.HOTEL_PHONE,
            "email": settings.HOTEL_EMAIL,
            "installed_modules": ["hotel", "hotel_config", "crm", "partner", "project", "fixed_asset", "pos", "hrm", "inventory", "hcm", "finance", "dms", "payroll"],
            "schema_name": schema,
            "db_connected": False,
            "stats": {
                "total_room_types": 0,
                "total_rooms": 0,
                "available_rooms": 0,
                "occupied_rooms": 0
            }
        }

        try:
            with get_connection() as conn:
                with conn.cursor(cursor_factory=RealDictCursor) as cur:
                    # 1. Ambil data dari public.tenants
                    cur.execute("SELECT * FROM public.tenants WHERE id = %s LIMIT 1;", (tenant_id,))
                    t_row = cur.fetchone()
                    if t_row:
                        tenant_info.update({
                            "tenant_id": str(t_row["id"]),
                            "name": t_row.get("name") or tenant_info["name"],
                            "slug": t_row.get("slug") or tenant_info["slug"],
                            "legal_name": t_row.get("legal_name") or tenant_info["legal_name"],
                            "status": t_row.get("status") or tenant_info["status"],
                            "timezone": t_row.get("timezone") or tenant_info["timezone"],
                            "locale": t_row.get("locale") or tenant_info["locale"],
                            "currency": t_row.get("currency") or tenant_info["currency"],
                            "address": t_row.get("address") or tenant_info["address"],
                            "phone": t_row.get("phone") or tenant_info["phone"],
                            "email": t_row.get("email_public") or tenant_info["email"],
                            "installed_modules": t_row.get("module_order") or tenant_info["installed_modules"],
                            "created_at": str(t_row.get("created_at")),
                            "updated_at": str(t_row.get("updated_at"))
                        })

                    # 2. Ambil statistik kamar dari schema tenant
                    cur.execute(f"""
                        SELECT 
                            COUNT(DISTINCT rt.id) AS total_room_types,
                            COUNT(r.id) AS total_rooms,
                            COUNT(r.id) FILTER (WHERE r.front_desk_status ILIKE 'vacant%%') AS available_rooms,
                            COUNT(r.id) FILTER (WHERE r.front_desk_status ILIKE 'occ%%') AS occupied_rooms
                        FROM "{schema}".hotel_room_types rt
                        LEFT JOIN "{schema}".hotel_rooms r 
                            ON r.room_type_id = rt.id AND r.tenant_id = rt.tenant_id
                        WHERE rt.tenant_id = %s;
                    """, (tenant_id,))
                    stat_row = cur.fetchone()
                    if stat_row:
                        tenant_info["stats"] = {
                            "total_room_types": stat_row["total_room_types"] or 0,
                            "total_rooms": stat_row["total_rooms"] or 0,
                            "available_rooms": stat_row["available_rooms"] or 0,
                            "occupied_rooms": stat_row["occupied_rooms"] or 0
                        }
                    tenant_info["db_connected"] = True
        except Exception as e:
            logger.error(f"Error fetching tenant status: {e}")
            tenant_info["db_error"] = str(e)

        return tenant_info

    @staticmethod
    def get_schema_tables() -> Dict[str, Any]:
        """
        Mengambil daftar seluruh tabel yang ada pada schema tenant saat ini beserta rincian kategori.
        """
        schema = settings.POSTGRES_SCHEMA
        result = {
            "schema": schema,
            "total_tables": 0,
            "categories": {},
            "tables": []
        }
        try:
            with get_connection() as conn:
                with conn.cursor(cursor_factory=RealDictCursor) as cur:
                    cur.execute("""
                        SELECT table_name 
                        FROM information_schema.tables 
                        WHERE table_schema = %s AND table_type = 'BASE TABLE'
                        ORDER BY table_name;
                    """, (schema,))
                    rows = cur.fetchall()
                    table_names = [r["table_name"] for r in rows]
                    result["total_tables"] = len(table_names)
                    
                    categories = {
                        "hotel_core": [],
                        "hotel_config": [],
                        "crm": [],
                        "finance_and_accounting": [],
                        "pos_and_inventory": [],
                        "hrm_and_payroll": [],
                        "users_and_security": [],
                        "other": []
                    }
                    
                    for t in table_names:
                        if t.startswith("hotel_config_"):
                            categories["hotel_config"].append(t)
                        elif t.startswith("hotel_"):
                            categories["hotel_core"].append(t)
                        elif t.startswith("crm_"):
                            categories["crm"].append(t)
                        elif any(t.startswith(p) for p in ["fin_", "acc_", "gl_", "tax_", "bank_"]):
                            categories["finance_and_accounting"].append(t)
                        elif any(t.startswith(p) for p in ["pos_", "inv_", "item_", "stock_"]):
                            categories["pos_and_inventory"].append(t)
                        elif any(t.startswith(p) for p in ["hrm_", "payroll_", "emp_"]):
                            categories["hrm_and_payroll"].append(t)
                        elif any(t.startswith(p) for p in ["user", "role", "permission", "auth"]):
                            categories["users_and_security"].append(t)
                        else:
                            categories["other"].append(t)
                            
                    result["categories"] = {k: len(v) for k, v in categories.items()}
                    result["tables"] = table_names
        except Exception as e:
            logger.error(f"Error inspecting schema tables: {e}")
            result["error"] = str(e)
            
        return result

