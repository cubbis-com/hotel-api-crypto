"""
Script Eksekusi Seed Data Master Agnia Guest House Syariah
Menjalankan SQL seed pada PostgreSQL Railway schema tenant_agnia_guesthouse.
"""

import sys
import os
import psycopg2
from psycopg2.extras import RealDictCursor
from config import settings

def apply_master_data():
    sql_file = "/Users/kerasakti/Documents/HOTEL/PORTAL/anvieo-backend/sql/seed_agnia_master_data.sql"
    if not os.path.exists(sql_file):
        print(f"Error: {sql_file} not found!")
        sys.exit(1)

    with open(sql_file, "r", encoding="utf-8") as f:
        sql_content = f.read()

    print(f"Connecting to PostgreSQL ({settings.POSTGRES_SERVER}:{settings.POSTGRES_PORT}/{settings.POSTGRES_DB})...")
    conn = psycopg2.connect(settings.postgres_connection_string)
    conn.autocommit = False

    try:
        with conn.cursor() as cur:
            print("Executing SQL script...")
            cur.execute(sql_content)
        conn.commit()
        print("SQL script executed and committed successfully!")

        # Verifikasi Data
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            schema = settings.POSTGRES_SCHEMA
            
            print("\n=== VERIFIKASI PROPERTY ===")
            cur.execute(f'SELECT name, property_code, phone, checkin_time, checkout_time, star_rating FROM "{schema}".hotel_properties WHERE tenant_id = %s;', (settings.TENANT_ID,))
            prop = cur.fetchone()
            print(f"Property: {prop['name']} (Code: {prop['property_code']}) | Phone: {prop['phone']}")

            print("\n=== VERIFIKASI TIPE KAMAR (ROOM TYPES) ===")
            cur.execute(f'SELECT code, name, base_rate, bed_type, room_size_sqm FROM "{schema}".hotel_room_types WHERE tenant_id = %s ORDER BY sort_key ASC;', (settings.TENANT_ID,))
            room_types = cur.fetchall()
            for rt in room_types:
                print(f"• [{rt['code']}] {rt['name']} - Rp {int(rt['base_rate']):,} ({rt['bed_type']}, {rt['room_size_sqm']} m²)")

            print("\n=== VERIFIKASI UNIT KAMAR FISIK (ROOMS) ===")
            cur.execute(f'''
                SELECT r.room_number, r.name, rt.code as type_code, r.floor_number, r.front_desk_status, r.housekeeping_status
                FROM "{schema}".hotel_rooms r
                JOIN "{schema}".hotel_room_types rt ON r.room_type_id = rt.id
                WHERE r.tenant_id = %s
                ORDER BY r.sort_key ASC, r.room_number ASC;
            ''', (settings.TENANT_ID,))
            rooms = cur.fetchall()
            for r in rooms:
                print(f"• Kamar {r['room_number']} (Lt. {r['floor_number']}) - Tipe: {r['type_code']} | Status: {r['front_desk_status']}/{r['housekeeping_status']}")

            print("\n=== VERIFIKASI EXTRA CHARGES & RENTAL KENDARAAN ===")
            cur.execute(f'SELECT code, name, category, price, charge_type FROM "{schema}".hotel_config_extra_charges WHERE tenant_id = %s ORDER BY created_at ASC;', (settings.TENANT_ID,))
            charges = cur.fetchall()
            for c in charges:
                print(f"• [{c['code']}] {c['name']} - Rp {int(c['price']):,} / {c['charge_type']} ({c['category']})")

            print("\n=== VERIFIKASI PAKET (PACKAGES) ===")
            cur.execute(f'SELECT code, name, total_package_price FROM "{schema}".hotel_config_packages WHERE tenant_id = %s;', (settings.TENANT_ID,))
            packages = cur.fetchall()
            for p in packages:
                print(f"• [{p['code']}] {p['name']} - Rp {int(p['total_package_price']):,}")

            print("\n=== VERIFIKASI RATE TYPES & MATRIKS TARIF ===")
            cur.execute(f'''
                SELECT rt.code as room_code, rtp.code as rate_code, rr.weekday_rate, rr.weekend_rate
                FROM "{schema}".hotel_room_rates rr
                JOIN "{schema}".hotel_room_types rt ON rr.room_type_id = rt.id
                JOIN "{schema}".hotel_rate_types rtp ON rr.rate_type_id = rtp.id
                WHERE rr.tenant_id = %s
                ORDER BY rt.sort_key ASC, rtp.duration ASC;
            ''', (settings.TENANT_ID,))
            rates = cur.fetchall()
            for rate in rates:
                print(f"• {rate['room_code']} + {rate['rate_code']}: Weekday Rp {int(rate['weekday_rate']):,} | Weekend Rp {int(rate['weekend_rate']):,}")

            print(f"\nTotal Kamar Fisik Terdaftar: {len(rooms)} Unit")
            print(f"Total Tipe Kamar: {len(room_types)} Kategori")
            print(f"Total Layanan Tambahan/Rental: {len(charges)} Item")

    except Exception as e:
        conn.rollback()
        print(f"Error during migration: {e}")
        raise e
    finally:
        conn.close()

if __name__ == "__main__":
    apply_master_data()
