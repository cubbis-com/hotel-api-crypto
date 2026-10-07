import re
import httpx
import logging
import datetime
import calendar
from zoneinfo import ZoneInfo
from typing import Dict, Any
from config import settings
from opera_catalog import get_catalog_context_str

logger = logging.getLogger("garda_service")


def get_datetime_and_timezone_info() -> Dict[str, Any]:
    """
    Menghasilkan data kalender dinamis (waktu sekarang, hari ini, besok, lusa, sisa hari bulan ini,
    bulan depan, dan zona waktu resmi hotel WITA).
    """
    try:
        tz = ZoneInfo(settings.HOTEL_TIMEZONE)
    except Exception:
        tz = ZoneInfo("Asia/Makassar")

    now = datetime.datetime.now(tz)
    hari_id = ["Senin", "Selasa", "Rabu", "Kamis", "Jumat", "Sabtu", "Minggu"]
    bulan_id = [
        "", "Januari", "Februari", "Maret", "April", "Mei", "Juni",
        "Juli", "Agustus", "September", "Oktober", "November", "Desember"
    ]

    def fmt_id(dt: datetime.datetime) -> str:
        h = hari_id[dt.weekday()]
        b = bulan_id[dt.month]
        return f"{h}, {dt.day} {b} {dt.year}"

    today = now
    besok = now + datetime.timedelta(days=1)      # H+1
    lusa_h2 = now + datetime.timedelta(days=2)    # H+2
    lusa_h3 = now + datetime.timedelta(days=3)    # H+3 (sesuai spesifikasi pengguna: lusa H+3)
    h4 = now + datetime.timedelta(days=4)
    h5 = now + datetime.timedelta(days=5)
    h6 = now + datetime.timedelta(days=6)
    h7 = now + datetime.timedelta(days=7)

    waktu_str = now.strftime("%H:%M")
    curr_month_name = bulan_id[now.month]
    next_month_num = now.month + 1 if now.month < 12 else 1
    next_month_year = now.year if now.month < 12 else now.year + 1
    next_month_name = bulan_id[next_month_num]

    # Generate sisa hari di bulan saat ini
    _, last_day = calendar.monthrange(now.year, now.month)
    sisa_hari_list = []
    for d in range(now.day, last_day + 1):
        dt = datetime.datetime(now.year, now.month, d)
        tag = ""
        if d == now.day:
            tag = " [HARI INI]"
        elif d == now.day + 1:
            tag = " [BESOK / H+1]"
        elif d == now.day + 2:
            tag = " [H+2]"
        elif d == now.day + 3:
            tag = " [LUSA / H+3]"
        sisa_hari_list.append(f"  • Tanggal {d} -> {fmt_id(dt)} ({dt.strftime('%Y-%m-%d')}){tag}")
    sisa_hari_str = "\n".join(sisa_hari_list)

    return {
        "timezone_code": "WITA",
        "timezone_full": "WITA (Waktu Indonesia Tengah / UTC+8 / GMT+8)",
        "waktu_sekarang": waktu_str,
        "hari_ini_day": today.day,
        "hari_ini_full": fmt_id(today),
        "hari_ini_iso": today.strftime("%Y-%m-%d"),
        "besok_full": fmt_id(besok),
        "besok_iso": besok.strftime("%Y-%m-%d"),
        "lusa_h3_full": fmt_id(lusa_h3),
        "lusa_h3_iso": lusa_h3.strftime("%Y-%m-%d"),
        "lusa_h2_full": fmt_id(lusa_h2),
        "lusa_h2_iso": lusa_h2.strftime("%Y-%m-%d"),
        "h4_full": fmt_id(h4),
        "h4_iso": h4.strftime("%Y-%m-%d"),
        "h5_full": fmt_id(h5),
        "h5_iso": h5.strftime("%Y-%m-%d"),
        "h6_full": fmt_id(h6),
        "h6_iso": h6.strftime("%Y-%m-%d"),
        "h7_full": fmt_id(h7),
        "h7_iso": h7.strftime("%Y-%m-%d"),
        "bulan_sekarang": curr_month_name,
        "bulan_sekarang_num": now.month,
        "tahun_sekarang": now.year,
        "bulan_depan": next_month_name,
        "tahun_bulan_depan": next_month_year,
        "sisa_hari_str": sisa_hari_str,
    }


def get_clock_calendar_and_timezone_str() -> str:
    """
    Menghasilkan dokumen teks konteks kalender real-time dan zona waktu hotel
    yang dilampirkan sebagai file referensi LLM Garda.
    """
    dt = get_datetime_and_timezone_info()
    return f"""=============================================================
WAKTU, KALENDER REAL-TIME & INFORMASI ZONA WAKTU HOTEL RESMI
=============================================================
• Nama Hotel: {settings.HOTEL_NAME} ({settings.HOTEL_LEGAL_NAME})
• Lokasi Hotel: Balikpapan Selatan, Kalimantan Timur (1.5 km dari Bandara Sultan Aji Muhammad Sulaiman Sepinggan / BPN)
• Waktu Saat Ini di Hotel: {dt['hari_ini_full']} pukul {dt['waktu_sekarang']} WITA
• Zona Waktu Hotel: {dt['timezone_full']}
• Bulan Berjalan: {dt['bulan_sekarang']} {dt['tahun_sekarang']}
• Bulan Depan: {dt['bulan_depan']} {dt['tahun_bulan_depan']}

KALENDER REAL-TIME TERKINI:
• HARI INI (H+0): {dt['hari_ini_full']} | Kode: {dt['hari_ini_iso']}
• BESOK (H+1): {dt['besok_full']} | Kode: {dt['besok_iso']}
• LUSA (H+3): {dt['lusa_h3_full']} | Kode: {dt['lusa_h3_iso']} (Catatan: H+2 adalah {dt['lusa_h2_full']})
• H+4: {dt['h4_full']} | Kode: {dt['h4_iso']}
• H+5: {dt['h5_full']} | Kode: {dt['h5_iso']}
• H+6: {dt['h6_full']} | Kode: {dt['h6_iso']}
• H+7: {dt['h7_full']} | Kode: {dt['h7_iso']}

DAFTAR TANGGAL SISA BULAN INI ({dt['bulan_sekarang']} {dt['tahun_sekarang']}):
{dt['sisa_hari_str']}

PANDUAN KECERDASAN INFERENSI TANGGAL DARI TAMU:
1. ATURAN "BESOK" (H+1):
   - Jika tamu menyebut "besok", artinya H+1: {dt['besok_full']} ({dt['besok_iso']}).
   - Jika tamu bilang "booking besok 1 malam", artinya Check-in: {dt['besok_iso']}, Check-out: {dt['lusa_h2_iso']}.

2. ATURAN "LUSA" (H+3):
   - Jika tamu menyebut "lusa", artinya H+3: {dt['lusa_h3_full']} ({dt['lusa_h3_iso']}) atau H+2 ({dt['lusa_h2_full']}).
   - Sebutkan konfirmasi tanggal pastinya secara ramah.
   - Jika tamu menyebut "besok sampai lusa", artinya Check-in: {dt['besok_iso']} dan Check-out: {dt['lusa_h3_iso']} atau {dt['lusa_h2_iso']}.

3. ATURAN JIKA TAMU HANYA MENYEBUT ANGKA TANGGAL SAJA (TANPA BULAN DAN TAHUN):
   - Contoh: "booking tgl 28 ya", "tanggal 25 sampai 27", "ada kamar tgl 30?".
   - Otomatis pahami bahwa angka tanggal tersebut adalah di BULAN SEKARANG ({dt['bulan_sekarang']}) dan TAHUN SEKARANG ({dt['tahun_sekarang']})!
   - Contoh: Tamu bilang "tgl 28" -> langsung pahami sebagai 28 {dt['bulan_sekarang']} {dt['tahun_sekarang']} ({dt['tahun_sekarang']}-{dt['bulan_sekarang_num']:02d}-28).
   - Contoh: Tamu bilang "tgl 25 sampai 27" -> Check-in: 25 {dt['bulan_sekarang']} {dt['tahun_sekarang']}, Check-out: 27 {dt['bulan_sekarang']} {dt['tahun_sekarang']} (2 malam).
   - Smart Rollover: Jika angka tanggal yang disebut < tanggal hari ini ({dt['hari_ini_day']}) (contoh: tamu bilang "tanggal 5", padahal hari ini sudah tanggal {dt['hari_ini_day']}), otomatis pahami itu adalah tanggal 5 di BULAN DEPAN ({dt['bulan_depan']} {dt['tahun_sekarang']})!

4. ATURAN JIKA TAMU MENYEBUT TANGGAL DAN BULAN (TANPA TAHUN):
   - Contoh: "saya mau booking 5 Oktober", "check in 28 September", "10 November".
   - Otomatis pahami bahwa tanggal dan bulan tersebut adalah di TAHUN SEKARANG ({dt['tahun_sekarang']})!
   - Contoh: "5 Oktober" -> 5 Oktober {dt['tahun_sekarang']} ({dt['tahun_sekarang']}-10-05).
   - Contoh: "28 September" -> 28 September {dt['tahun_sekarang']} ({dt['tahun_sekarang']}-09-28).

5. ATURAN SELALU MENYEBUTKAN TANGGAL LENGKAP:
   - Setiap kali mengonfirmasi atau membalas tamu, SELALU sebutkan:
     [Nama Hari], [Tanggal] [Bulan] [Tahun] (contoh: "Senin, 28 September 2026").
     Ini memberikan kepastian 100% kepada tamu agar tidak ada kesalahpahaman tanggal.

PANDUAN ZONA WAKTU RESMI HOTEL (WITA / UTC+8):
1. Hotel Agnia Guest House berada di Balikpapan, Kalimantan Timur, dan menggunakan zona waktu resmi: WITA (Waktu Indonesia Tengah / UTC+8).
2. Perbandingan dengan Zona Waktu Lain di Indonesia:
   • WIB (Jakarta, Bandung, Surabaya, Semarang, Medan, Sumatera, Jawa, Pontianak):
     WITA adalah 1 JAM LEBIH CEPAT daripada WIB.
     Contoh konkret: Pukul 14:00 WITA di hotel = Pukul 13:00 WIB di Jakarta.
   • WIT (Maluku, Jayapura, Papua):
     WITA adalah 1 JAM LEBIH LAMBAT daripada WIT.
     Contoh: Pukul 14:00 WITA di hotel = Pukul 15:00 WIT di Papua.
3. Jam Check-in & Check-out Hotel:
   • Waktu Check-in: Pukul 14:00 - 20:00 WITA (setara pukul 13:00 - 19:00 WIB).
   • Waktu Check-out: Pukul 12:00 - 12:30 WITA (setara pukul 11:00 - 11:30 WIB).
4. ATURAN PENTING:
   • Anda SELALU menyertakan satuan 'WITA' setiap kali menyebutkan jam/waktu.
   • Jika tamu menanyakan jam operasional, check-in, jadwal tiba penerbangan (terutama dari Jakarta/Surabaya/kota-kota WIB lainnya), atau perbedaan waktu, sampaikan dengan ramah bahwa hotel berada di zona waktu WITA (UTC+8) yang 1 jam lebih cepat dibanding WIB/Jakarta.
=============================================================
"""


def get_system_prompt() -> str:
    """
    Menghasilkan System Prompt lengkap Garda dengan data kalender real-time & zona waktu hotel terinjeksi dinamis.
    """
    dt = get_datetime_and_timezone_info()
    return f"""Anda adalah Garda, Resepsionis Virtual & Asisten Reservasi resmi di {settings.HOTEL_NAME} ({settings.HOTEL_LEGAL_NAME}).
Akomodasi adalah Penginapan / Guesthouse Syariah-Friendly di Balikpapan Selatan, hanya berjarak 1.5 km (±5 menit) dari Bandara Internasional Sultan Aji Muhammad Sulaiman Sepinggan Balikpapan (BPN).
Alamat Lengkap: {settings.HOTEL_ADDRESS}.
Kontak Resmi: WhatsApp {settings.HOTEL_PHONE} | Email: {settings.HOTEL_EMAIL}.

=============================================================
WAKTU REAL-TIME, KALENDER TERKINI & ZONA WAKTU HOTEL (WAJIB DIPAHAMI):
=============================================================
• Waktu Saat Ini di Hotel: {dt['hari_ini_full']} pukul {dt['waktu_sekarang']} WITA.
• Bulan Berjalan: {dt['bulan_sekarang']} {dt['tahun_sekarang']} | Bulan Depan: {dt['bulan_depan']} {dt['tahun_bulan_depan']}
• HARI INI (H+0): {dt['hari_ini_full']} (ISO: {dt['hari_ini_iso']})
• BESOK (H+1): {dt['besok_full']} (ISO: {dt['besok_iso']})
• LUSA (H+3): {dt['lusa_h3_full']} (ISO: {dt['lusa_h3_iso']}) (Catatan: H+2 adalah {dt['lusa_h2_full']})
• H+4: {dt['h4_full']} (ISO: {dt['h4_iso']})
• H+5: {dt['h5_full']} (ISO: {dt['h5_iso']})
• H+6: {dt['h6_full']} (ISO: {dt['h6_iso']})
• H+7: {dt['h7_full']} (ISO: {dt['h7_iso']})

DAFTAR TANGGAL SISA BULAN INI ({dt['bulan_sekarang']} {dt['tahun_sekarang']}):
{dt['sisa_hari_str']}

ATURAN KECERDASAN KALENDER & PEMAHAMAN TANGGAL DARI TAMU:
- Anda SELALU tahu tanggal dan hari saat ini secara real-time. DILARANG KERAS berkata Anda tidak tahu atau tidak memiliki akses ke tanggal real-time!
- ATURAN 1 (BESOK): "Besok" berarti H+1 dari hari ini, yaitu {dt['besok_full']} ({dt['besok_iso']}).
- ATURAN 2 (LUSA): "Lusa" berarti H+3 dari hari ini, yaitu {dt['lusa_h3_full']} ({dt['lusa_h3_iso']}) atau H+2 ({dt['lusa_h2_full']}). Konfirmasikan tanggal pastinya dengan jelas.
- ATURAN 3 (HANYA MENYEBUT ANGKA TANGGAL):
  * Jika tamu hanya menyebut angka tanggal saja tanpa menyebut bulan dan tahun (contoh: "tgl 28", "tanggal 25 sampai 27", "ada kamar tgl 30?"):
    -> Otomatis pahami bahwa tanggal tersebut adalah di BULAN SEKARANG ({dt['bulan_sekarang']}) dan TAHUN SEKARANG ({dt['tahun_sekarang']})!
    -> Contoh: Tamu bilang "booking tgl 28" = 28 {dt['bulan_sekarang']} {dt['tahun_sekarang']} ({dt['tahun_sekarang']}-{dt['bulan_sekarang_num']:02d}-28).
    -> Contoh: "tgl 25 sampai 27" = Check-in 25 {dt['bulan_sekarang']} {dt['tahun_sekarang']} dan Check-out 27 {dt['bulan_sekarang']} {dt['tahun_sekarang']} (2 malam).
    -> Smart Rollover: Jika angka tanggal yang disebut < tanggal hari ini ({dt['hari_ini_day']}) (contoh: tamu bilang "tanggal 5", padahal sekarang sudah tanggal {dt['hari_ini_day']}), otomatis pahami itu adalah tanggal 5 di BULAN DEPAN ({dt['bulan_depan']} {dt['tahun_sekarang']})!
- ATURAN 4 (TANGGAL & BULAN TANPA TAHUN):
  * Jika tamu menyebut tanggal dan bulan tanpa tahun (contoh: "5 Oktober", "12 November", "28 September"):
    -> Otomatis pahami bahwa tanggal dan bulan tersebut adalah di TAHUN SEKARANG ({dt['tahun_sekarang']})!
    -> Contoh: "5 Oktober" = 5 Oktober {dt['tahun_sekarang']} ({dt['tahun_sekarang']}-10-05).
    -> Contoh: "28 September" = 28 September {dt['tahun_sekarang']} ({dt['tahun_sekarang']}-09-28).
- ATURAN 5 (SELALU SEBUT TANGGAL LENGKAP):
  * Setiap kali mengonfirmasi atau membalas tamu, selalu sebutkan nama hari, tanggal, bulan, dan tahun secara eksplisit: [Nama Hari], [Tanggal] [Bulan] [Tahun] (contoh: "Senin, 28 September 2026").
- ATURAN 6 (PERHITUNGAN TANGGAL CHECK-OUT & JUMLAH MALAM - SANGAT KRUSIAL):
  * Tanggal Check-Out HARUS SELALU di hari/tanggal BERIKUTNYA setelah Check-In (Check-Out > Check-In).
  * DILARANG KERAS menetapkan tanggal Check-Out sama dengan tanggal Check-In!
  * Rumus Tanggal Check-Out:
    Tanggal Check-Out = Tanggal Check-In + Jumlah Malam.
    Contoh Konkret:
    - Check-in: 25 September 2026, Durasi: 1 malam -> Check-out: 26 September 2026.
    - Check-in: 25 September 2026, Durasi: 2 malam -> Check-out: 27 September 2026.
    - Check-in: 25 September 2026, Durasi: 3 malam -> Check-out: 28 September 2026.
  * Baik dalam teks obrolan, format REKAPITULASI DRAFT RESERVASI, maupun blok sinyal <<BOOKING_CONFIRMED>>:
    Nilai CHECKIN dan CHECKOUT harus berupa tanggal ISO YYYY-MM-DD yang benar sesuai penambahan durasi malam tersebut!

ATURAN KRUSIAL KETERSEDIAAN KAMAR FISIK & ANTI-PENUMPUKAN / OVERBOOKING:
1. CEK DULU KETERSEDIAAN KAMAR REAL-TIME:
   Sebelum merekomendasikan tipe kamar atau mengonfirmasi ketersediaan kamar kepada tamu, Anda WAJIB memeriksa lampiran status ketersediaan kamar real-time untuk tanggal yang ditanyakan.
2. JIKA SUATU TIPE KAMAR PENUH / SUDAH DI-RESERVASI (0 UNIT):
   - DILARANG KERAS mengatakan kamar tersebut masih tersedia!
   - DILARANG KERAS membuatkan rekapitulasi draft atau sinyal booking untuk tipe kamar yang statusnya PENUH / SOLD OUT pada tanggal tersebut!
3. SOLUSI WAJIB KETIKA KAMAR PENUH:
   Jika tipe kamar yang diminati tamu sudah penuh (contoh: Superior Double sudah terisi semua), tawarkan opsi solusi berikut dengan ramah dan solutif:
   • Opsi A (Tipe Kamar Lain yang Kosong): Rekomendasikan tipe kamar lain yang masih berstatus '✅ TERSEDIA' pada tanggal tersebut. Jelaskan kelebihan kamar tersebut (misal: Deluxe Twin AC masih tersedia 1 unit, sangat nyaman dan bersih).
   • Opsi B (Geser Tanggal Sebelum / Sesudah): Tawarkan tamu untuk memajukan atau memundurkan tanggal menginap sebelum tanggal penuh tersebut atau sesudahnya saat kamar sudah kosong kembali.
   • Opsi C (Pindah Kamar / Room Move / Split Stay): Jika tamu menginap lebih dari 1 malam dan tidak ada 1 kamar yang kosong penuh di seluruh malam, tawarkan solusi pindah kamar di tengah masa inap (contoh: malam ke-1 di Deluxe Twin, malam ke-2 di Superior Double).
4. ATURAN 1 KAMAR 1 TAMU & LARANGAN MENYEBUT NOMOR KAMAR:
   - Setiap unit kamar fisik di Agnia Guesthouse HANYA BISA DIISI 1 RESERVASI pada tanggal yang sama. Dilarang keras menumpuk pemesanan di kamar yang sama!
   - DILARANG KERAS menyebutkan atau menjanjikan nomor kamar fisik spesifik (seperti kamar 101, 103, 104, 106) kepada tamu! Penomoran kamar fisik dilakukan oleh Front Desk saat tamu tiba untuk check-in.

INFORMASI ZONA WAKTU HOTEL (WITA / UTC+8):
- Hotel berlokasi di Balikpapan, Kalimantan Timur, dan menggunakan zona waktu resmi: WITA (Waktu Indonesia Tengah / UTC+8 / GMT+8).
- Penjelasan Perbandingan Zona Waktu:
  * Terhadap WIB (Jakarta, Bandung, Surabaya, Semarang, Medan, Sumatera, Jawa, Pontianak):
    WITA adalah 1 JAM LEBIH CEPAT daripada WIB.
    Contoh konkret: Jika di Jakarta masih pukul 10:00 WIB, maka di hotel Balikpapan sudah pukul 11:00 WITA.
  * Terhadap WIT (Maluku, Papua):
    WITA adalah 1 JAM LEBIH LAMBAT daripada WIT.
    Contoh: Jika di Jayapura sudah pukul 12:00 WIT, di Balikpapan masih pukul 11:00 WITA.
- Kebijakan Waktu Hotel:
  * Waktu Check-in: Mulai pukul 14:00 WITA (setara pukul 13:00 WIB).
  * Waktu Check-out: Maksimal pukul 12:00 WITA (setara pukul 11:00 WIB).
- ATURAN KOMUNIKASI:
  * SELALU cantumkan satuan "WITA" setiap kali menyebutkan jam/waktu.
  * Jika tamu menanyakan jam operasional, waktu check-in, jadwal kedatangan pesawat/transit ke Bandara Sepinggan (BPN), atau bertanya tentang zona waktu hotel, jelaskan dengan ramah bahwa hotel berada di zona waktu WITA (1 jam lebih cepat dibanding WIB/Jakarta).
=============================================================

Anda berkomunikasi dengan calon tamu melalui WhatsApp dengan bahasa Indonesia yang ramah, hangat, sopan, dan profesional.
PENTING: Nama akomodasi Anda adalah {settings.HOTEL_NAME} ({settings.HOTEL_LEGAL_NAME}). Jangan pernah menyebut nama hotel lain. DILARANG KERAS menyebut nama "Anvieo" atau "Anvieo Hotel & Resort" dalam situasi apa pun. Properti Anda adalah {settings.HOTEL_NAME}.

TUGAS UTAMA ANDA:
1. Menjawab pertanyaan tamu mengenai ketersediaan kamar, tipe kamar, fasilitas, tarif, season, kalender, zona waktu, dan paket promo diskon sesuai dokumen katalog kamar real-time yang dilampirkan.
2. Mengumpulkan data-data reservasi tamu secara natural dan bertahap (jangan interogasi seperti formulir kaku). Data yang harus dikumpulkan meliputi:
   - Nama lengkap pemesan
   - Tanggal Check-In dan Check-Out (atau perkiraan tanggal dan jumlah malam) dalam format YYYY-MM-DD
   - Tipe kamar yang diminati (gunakan KODE resmi berikut):
     * STD-FAN : Standard Twin / Single Room (Kipas Angin) - Rp 115.000/malam (weekday) | Rp 125.000/malam (weekend)
     * DLX-TWN : Deluxe Twin Room (AC) - Rp 160.000/malam (weekday) | Rp 175.000/malam (weekend)
     * SUP-DBL : Superior Double Room (AC, Ranjang Besar) - Rp 235.000/malam (weekday) | Rp 260.000/malam (weekend)
   - Jumlah tamu (jumlah orang dewasa dan anak-anak)
   - Nomor WhatsApp tamu (konfirmasi dari nomor yang sedang digunakan)
   - Alamat email tamu (jika tidak ada, gunakan default: tamu@agniaguesthouse.com)
   - Permintaan khusus (misalnya: extra bed Rp 75.000, sewa motor Rp 85.000, laundry Rp 15.000/kg, antar-jemput bandara, dll)

3. TAHAP REKAPITULASI (SANGAT KRUSIAL):
   - Jika tamu telah menentukan tipe kamar (misal: "Deluxe Twin Room" atau "DLX-TWN"), DILARANG KERAS menanyakan kembali pilihan kamar atau menawarkan tipe lain!
   - Jika Nama Pemesan, Periode Menginap, dan Tipe Kamar sudah ada, SEGERA sajikan rangkuman / rekapitulasi draft pemesanan dengan format rapi berikut!
   - Gunakan nilai default yang wajar jika tamu belum menyebutkan secara rinci (Jumlah Tamu: 2 Dewasa, Email: default tamu@agniaguesthouse.com, Permintaan Khusus: Tidak ada). JANGAN menunda rekapitulasi demi menanyakan hal-hal opsional!

   📋 *REKAPITULASI DRAFT RESERVASI*
   • *Nama Pemesan:* [Nama Tamu]
   • *No. WhatsApp:* [Nomor HP Tamu]
   • *Email:* [Email Tamu]
   • *Tipe Kamar:* [Nama Tipe Kamar] (Kode: [STD-FAN / DLX-TWN / SUP-DBL])
   • *Periode Menginap:* [Hari, YYYY-MM-DD] s/d [Hari, YYYY-MM-DD] ([X] Malam)
   • *Waktu Check-in:* Mulai 14:00 WITA
   • *Waktu Check-out:* Maksimal 12:00 WITA
   • *Jumlah Tamu:* [X] Dewasa, [X] Anak
   • *Estimasi Total Biaya:* Rp [Total Kalkulasi]
   • *Permintaan Khusus:* [Permintaan / Tidak ada]

   *Status:* 🟡 MENUNGGU KONFIRMASI TAMU
   ─────────────────────────────
   Apakah rincian reservasi di atas sudah sesuai?
   Jika sudah benar, silakan pilih metode pembayaran:
   • *A) QRIS / Virtual Account* (Transfer Bank BCA, BRI, DANA, GoPay, OVO)
   • *B) Crypto USDT Escrow* (Smart Contract BNB Chain, Aman + Bonus Reward Poin ANV 🎁)
   
   Ketik *A* atau *B* (atau *YA* untuk QRIS standar) untuk melanjutkan! 🎉

4. TAHAP KONFIRMASI & PEMBAYARAN (SANGAT PENTING):
   Jika tamu membalas dengan konfirmasi atau memilih metode bayar (misalnya: A, B, ya, oke, betul, setuju, lanjut, konfirmasi, qris, crypto, usdt):
   a. Ucapkan terima kasih dan selamat datang dengan hangat bahwa kamar telah berhasil dikonfirmasi. DILARANG meminta tamu untuk menunggu (DILARANG KERAS berkata "mohon ditunggu" atau "sedang dibuatkan").
   b. Segera KELUARKAN sinyal terstruktur berikut di AKHIR respons Anda (WAJIB TEPAT, tidak boleh diubah formatnya):

   <<BOOKING_CONFIRMED>>
   NAMA:[Nama lengkap tamu]
   KODE_KAMAR:[STD-FAN atau DLX-TWN atau SUP-DBL]
   CHECKIN:[YYYY-MM-DD]
   CHECKOUT:[YYYY-MM-DD]
   MALAM:[Jumlah malam angka saja]
   DEWASA:[Jumlah dewasa angka saja]
   TOTAL:[Total biaya angka saja tanpa titik/koma/Rp]
   EMAIL:[Email tamu]
   METODE:[QRIS atau CRYPTO]
   <<END_BOOKING>>

   Catatan: Blok sinyal ini adalah kode mesin internal, TIDAK AKAN terlihat oleh tamu.

5. TANYA JAWAB LOYALITAS & POIN ANV:
   - Jika tamu menanyakan "cek poin", "saldo loyalitas", atau "poin ANV", informasikan bahwa setiap tamu otomatis memperoleh 5% reward poin BEP-20 ANV saat check-in, yang bisa ditukarkan untuk cashback menginap berikutnya.
   - Peringkat Tier: Silver (100 ANV, diskon 3%), Gold (500 ANV, diskon 5% + early check-in), Platinum (2000 ANV, diskon 7% + upgrade kamar).

ATURAN FORMAT PENULISAN WHATSAPP & PERSONA RESEPSIONIS (SANGAT PENTING):
- Persona Anda adalah Garda, Resepsionis Front Desk Agnia Guesthouse Balikpapan yang hangat, ramah, dan profesional.
- Sambut tamu baru dengan salam hangat, perkenalkan diri sebagai Resepsionis Virtual Agnia Guesthouse, sebutkan lokasi strategis (dekat Bandara Sepinggan BPN), dan zona waktu WITA.
- DILARANG KERAS berbicara seperti chatbot kaku atau memberikan kuesioner bernomor seperti formulir (misal: "1. Tanggal Check-In... 2. Tipe Kamar... 3. Jumlah tamu..."). Tanyakan kebutuhan tamu secara luwes, bersahabat, dan mengalir seperti percakapan resepsionis asli.
- JANGAN PERNAH mengungkit atau menagih data reservasi lama yang sudah selesai atau lunas. Jika tamu memulai percakapan baru, layani kebutuhan reservasi mereka yang baru.
- Gunakan format teks tebal WhatsApp (*tebal* dengan 1 bintang, JANGAN gunakan **tebal** 2 bintang).
- Untuk poin daftar/list rincian kamar, gunakan simbol bullet (• ), JANGAN gunakan format markdown (*   ).
- DILARANG KERAS menuliskan teks narasi akting / roleplay dalam kurung seperti *(Garda tersenyum)*, *(menarik napas)*, *(antusias)*, dsb. Langsung berbicara santun kepada tamu.
- JANGAN gunakan heading markdown (###) atau garis pemisah (***).
- Jangan pernah mengulang kalimat atau paragraf yang sama dua kali. Tulis jawaban bersih, ringkas, dan enak dibaca di layar HP.
- Kebijakan Syariah-Friendly: Pasangan wajib membawa KTP & Surat Nikah sah.
- Waktu Check-in: 14:00 - 20:00 WITA. Waktu Check-out: 12:00 - 12:30 WITA.
- JANGAN meminta nomor kartu kredit atau CVV di chat WhatsApp.
- JANGAN menjanjikan nomor kamar fisik tertentu (misal kamar 101/204), karena penetapan nomor kamar fisik dilakukan oleh Front Office saat check-in.
- ATURAN EMOJI TERIMA KASIH: Untuk ucapan terima kasih atau salam kesepakatan, DILARANG KERAS menggunakan emoji 🙏. Selalu gunakan emoji jabat tangan 🤝.
- Alur: INQUIRY -> CEK KETERSEDIAAN & HARGA -> KUMPULKAN DATA -> REKAPITULASI DUAL PAYMENT -> KONFIRMASI TAMU (A / B) -> PROSES PEMBAYARAN (QRIS / CRYPTO ESCROW).
"""

# Alias untuk backward compatibility
SYSTEM_PROMPT = get_system_prompt()


class GardaService:
    @staticmethod
    def sanitize_wa_text(text: str) -> str:
        """
        Membersihkan karakter markdown, narasi roleplay, dan duplikasi pesan agar sesuai dengan format WhatsApp.
        """
        if not text:
            return ""

        text = text.strip()

        # 1. Hapus duplikasi blok jika LLM mengulang seluruh pesan dua kali
        for split_offset in range(-15, 16):
            half = (len(text) // 2) + split_offset
            if 20 < half < len(text):
                p1 = text[:half].strip()
                p2 = text[half:].strip()
                if p1 == p2:
                    text = p1
                    break

        # 2. Hapus narasi roleplay / stage directions dalam tanda kurung (misal: *(Garda tersenyum...)*)
        text = re.sub(r'^\s*[*_]*\([^\)]*\)[*_]*\s*$', '', text, flags=re.MULTILINE)
        text = re.sub(r'\*?\([A-Za-z]+ (?:tersenyum|menarik|menghela|merekam|mencondongkan|menanggapi|menyunggingkan|memasang|mengambil)[^\)]*\)\*?', '', text, flags=re.IGNORECASE)

        # 3. Ubah heading markdown (### Judul -> *Judul*)
        text = re.sub(r'^[#]+\s*(.*?)$', r'*\1*', text, flags=re.MULTILINE)

        # 4. Ubah garis pemisah markdown (*** atau ---) menjadi garis rapi
        text = re.sub(r'^[*\-_]{3,}\s*$', r'─────────────────────────────', text, flags=re.MULTILINE)

        # 5. Ubah bullet markdown (*   atau -   atau +  ) menjadi simbol bullet WhatsApp (• )
        text = re.sub(r'^\s*[*+-]\s+', r'• ', text, flags=re.MULTILINE)

        # 6. Ubah bold markdown (**teks**) menjadi format WhatsApp (*teks*)
        text = re.sub(r'\*\*(.*?)\*\*', r'*\1*', text)

        # 7. Rapikan sisa-sisa asterik ganda
        text = re.sub(r'\*{2,}', r'*', text)

        # 8. Hapus blok sinyal mesin internal <<BOOKING_CONFIRMED>>...<<END_BOOKING>> dari pesan WA
        text = re.sub(r'<<BOOKING_CONFIRMED>>.*?<<END_BOOKING>>', '', text, flags=re.DOTALL)

        # 9. Ganti emoji terimakasih 🙏 menjadi emoji jabat tangan 🤝
        text = text.replace("🙏", "🤝")

        # 10. Ganti setiap penyebutan Anvieo menjadi nama properti resmi (Agnia Guesthouse)
        hotel_brand = settings.HOTEL_NAME if ("anvieo" not in settings.HOTEL_NAME.lower()) else "Agnia Guesthouse"
        text = re.sub(r'Anvieo Hotel(?:\s*&\s*Resort)?', hotel_brand, text, flags=re.IGNORECASE)
        text = re.sub(r'\bAnvieo\b', hotel_brand, text, flags=re.IGNORECASE)

        # 11. Rapikan spasi trailing & newline berlebih (maksimal 2 baris kosong)
        text = re.sub(r'[ \t]+$', '', text, flags=re.MULTILINE)
        text = re.sub(r'\n{3,}', '\n\n', text)

        return text.strip()

def parse_dates_smart(msg: str):
    """
    Mendeteksi secara cerdas tanggal check-in dan check-out dari teks pesan tamu.
    Mendukung format rentang tanggal (25-28 September), durasi malam (2 malam mulai 25 Okt),
    serta kata relatif (besok, lusa).
    """
    if not msg:
        return None, None
    dt_info = get_datetime_and_timezone_info()
    curr_year = dt_info['tahun_sekarang']
    curr_month = dt_info['bulan_sekarang_num']

    bulan_map = {
        'jan': 1, 'januari': 1, 'feb': 2, 'februari': 2, 'mar': 3, 'maret': 3,
        'apr': 4, 'april': 4, 'mei': 5, 'jun': 6, 'juni': 6, 'jul': 7, 'juli': 7,
        'agu': 8, 'agustus': 8, 'agt': 8, 'sep': 9, 'september': 9, 'okt': 10, 'oktober': 10,
        'nov': 11, 'november': 11, 'des': 12, 'desember': 12
    }

    # 1. '2 malam mulai 25 Oktober'
    m_rev = re.search(r'(\d+)\s*malam.*?(?:mulai|dari|tgl|tanggal)?\s*(\d{1,2})\s*([a-zA-Z]+)?(?:\s*(\d{4}))?', msg, re.IGNORECASE)
    if m_rev:
        nights = int(m_rev.group(1))
        d1 = int(m_rev.group(2))
        m_str = m_rev.group(3)
        y_str = m_rev.group(4)
        m = bulan_map.get(m_str.lower() if m_str else '', curr_month)
        y = int(y_str) if y_str else curr_year
        try:
            cin = datetime.date(y, m, d1)
            cout = cin + datetime.timedelta(days=nights)
            return str(cin), str(cout)
        except Exception:
            pass

    # 2. '25 sampai 28 September' or '25-28 September'
    m_range = re.search(r'(?:tgl|tanggal)?\s*(\d{1,2})\s*(?:s/?d|sampai|-|hingga)\s*(\d{1,2})\s*([a-zA-Z]+)?(?:\s*(\d{4}))?', msg, re.IGNORECASE)
    if m_range:
        d1 = int(m_range.group(1))
        d2 = int(m_range.group(2))
        m_str = m_range.group(3)
        y_str = m_range.group(4)
        m = bulan_map.get(m_str.lower() if m_str else '', curr_month)
        y = int(y_str) if y_str else curr_year
        try:
            cin = datetime.date(y, m, d1)
            cout = datetime.date(y, m, d2)
            if cout <= cin:
                cout = cin + datetime.timedelta(days=1)
            return str(cin), str(cout)
        except Exception:
            pass

    # 3. 'mulai 25 Oktober untuk 2 malam'
    m_fwd = re.search(r'(?:mulai|dari|tgl|tanggal)?\s*(\d{1,2})\s*([a-zA-Z]+)?.*?(?:untuk)?\s*(\d+)\s*malam', msg, re.IGNORECASE)
    if m_fwd:
        d1 = int(m_fwd.group(1))
        m_str = m_fwd.group(2)
        nights = int(m_fwd.group(3))
        m = bulan_map.get(m_str.lower() if m_str else '', curr_month)
        try:
            cin = datetime.date(curr_year, m, d1)
            cout = cin + datetime.timedelta(days=nights)
            return str(cin), str(cout)
        except Exception:
            pass

    # 4. Single date with month: 'tanggal 25 september', 'tgl 25 sep 2026', '25 september'
    m_single_month = re.search(r'(?:tgl|tanggal)?\s*(\d{1,2})\s+([a-zA-Z]+)(?:\s+(\d{4}))?', msg, re.IGNORECASE)
    if m_single_month:
        d1 = int(m_single_month.group(1))
        m_str = m_single_month.group(2).lower()
        if m_str in bulan_map:
            y_str = m_single_month.group(3)
            m = bulan_map[m_str]
            y = int(y_str) if y_str else curr_year
            try:
                cin = datetime.date(y, m, d1)
                cout = cin + datetime.timedelta(days=1)
                return str(cin), str(cout)
            except Exception:
                pass

    # 5. Single date with tgl/tanggal only: 'tgl 28', 'tanggal 28', 'tgl 5'
    m_single_tgl = re.search(r'(?:tgl|tanggal)\s*(\d{1,2})\b', msg, re.IGNORECASE)
    if m_single_tgl:
        d1 = int(m_single_tgl.group(1))
        m = curr_month
        y = curr_year
        curr_day = dt_info['hari_ini_day']
        if d1 < curr_day:
            m += 1
            if m > 12:
                m = 1
                y += 1
        try:
            cin = datetime.date(y, m, d1)
            cout = cin + datetime.timedelta(days=1)
            return str(cin), str(cout)
        except Exception:
            pass

    # 6. 'hari ini' / 'malam ini' / 'sekarang'
    if re.search(r'\b(hari\s*ini|malam\s*ini|sekarang|saat\s*ini|today|tonight)\b', msg, re.IGNORECASE):
        try:
            m_dur = re.search(r'(\d+)\s*(?:hari|malam)', msg, re.IGNORECASE)
            dur = int(m_dur.group(1)) if m_dur else 1
            if dur < 1:
                dur = 1
            cin_d = datetime.datetime.strptime(dt_info['hari_ini_iso'], '%Y-%m-%d').date()
            return str(cin_d), str(cin_d + datetime.timedelta(days=dur))
        except Exception:
            pass

    # 7. 'besok' (termasuk variasi typo umum: beaok, bsk, bsok, bsoq, besuk, besokk, tmrw)
    if re.search(r'\b(besok|beaok|bsk|bsok|bsoq|besuk|besokk|tmrw|tomorrow)\b', msg, re.IGNORECASE):
        try:
            m_dur = re.search(r'(\d+)\s*(?:hari|malam)', msg, re.IGNORECASE)
            dur = int(m_dur.group(1)) if m_dur else 1
            if dur < 1:
                dur = 1
            cin_d = datetime.datetime.strptime(dt_info['besok_iso'], '%Y-%m-%d').date()
            return str(cin_d), str(cin_d + datetime.timedelta(days=dur))
        except Exception:
            pass

    # 8. 'lusa' (termasuk variasi typo: lusaa)
    if re.search(r'\b(lusa|lusaa)\b', msg, re.IGNORECASE):
        try:
            m_dur = re.search(r'(\d+)\s*(?:hari|malam)', msg, re.IGNORECASE)
            dur = int(m_dur.group(1)) if m_dur else 1
            if dur < 1:
                dur = 1
            cin_d = datetime.datetime.strptime(dt_info['lusa_h2_iso'], '%Y-%m-%d').date()
            return str(cin_d), str(cin_d + datetime.timedelta(days=dur))
        except Exception:
            pass

    return None, None


def is_general_room_inquiry(msg: str) -> bool:
    """Mendeteksi apakah tamu menanyakan ketersediaan kamar secara umum (kamar kosong, ada kamar, dll)."""
    if not msg:
        return False
    pats = [
        r'\bkamar\s*(?:mana\s*(?:saja\s*)?(?:yang\s*)?)?kosong\b',
        r'\b(?:ada|cek)\s*(?:berapa\s*)?kamar\b',
        r'\bketersediaan\s*kamar\b',
        r'\b(?:kamar\s*)?(?:masih\s*)?(?:ada\s*)?availabel?\b',
        r'\b(?:kamar\s*)?(?:masih\s*)?(?:ada\s*)?available\b',
        r'\bada\s*kamar\s*kosong\b',
        r'\bada\s*kamar\b',
        r'\binfo\s*kamar\b'
    ]
    return any(re.search(p, msg, re.IGNORECASE) for p in pats)


class GardaService:
    @staticmethod
    def sanitize_wa_text(text: str) -> str:
        """
        Membersihkan karakter markdown, narasi roleplay, dan duplikasi pesan agar sesuai dengan format WhatsApp.
        """
        if not text:
            return ""

        text = text.strip()

        # 1. Hapus duplikasi blok jika LLM mengulang seluruh pesan dua kali
        for split_offset in range(-15, 16):
            half = (len(text) // 2) + split_offset
            if 20 < half < len(text):
                p1 = text[:half].strip()
                p2 = text[half:].strip()
                if p1 == p2:
                    text = p1
                    break

        # 2. Hapus narasi roleplay / stage directions dalam tanda kurung (misal: *(Garda tersenyum...)*)
        text = re.sub(r'^\s*[*_]*\([^\)]*\)[*_]*\s*$', '', text, flags=re.MULTILINE)
        text = re.sub(r'\*?\([A-Za-z]+ (?:tersenyum|menarik|menghela|merekam|mencondongkan|menanggapi|menyunggingkan|memasang|mengambil)[^\)]*\)\*?', '', text, flags=re.IGNORECASE)

        # 3. Ubah heading markdown (### Judul -> *Judul*)
        text = re.sub(r'^[#]+\s*(.*?)$', r'*\1*', text, flags=re.MULTILINE)

        # 4. Ubah garis pemisah markdown (*** atau ---) menjadi garis rapi
        text = re.sub(r'^[*\-_]{3,}\s*$', r'─────────────────────────────', text, flags=re.MULTILINE)

        # 5. Ubah bullet markdown (*   atau -   atau +  ) menjadi simbol bullet WhatsApp (• )
        text = re.sub(r'^\s*[*+-]\s+', r'• ', text, flags=re.MULTILINE)

        # 6. Ubah bold markdown (**teks**) menjadi format WhatsApp (*teks*)
        text = re.sub(r'\*\*(.*?)\*\*', r'*\1*', text)

        # 7. Rapikan sisa-sisa asterik ganda
        text = re.sub(r'\*{2,}', r'*', text)

        # 8. Blok sinyal <<BOOKING_CONFIRMED>> dipertahankan di sini agar main.py dapat mengekstrak data reservasi
        # Blok ini akan dibersihkan oleh main.py sebelum dikirimkan ke chat WhatsApp tamu.

        # 9. Ganti emoji terimakasih 🙏 menjadi emoji jabat tangan 🤝
        text = text.replace("🙏", "🤝")

        # 10. Ganti setiap penyebutan Anvieo menjadi nama properti resmi (Agnia Guesthouse)
        hotel_brand = settings.HOTEL_NAME if ("anvieo" not in settings.HOTEL_NAME.lower()) else "Agnia Guesthouse"
        text = re.sub(r'Anvieo Hotel(?:\s*&\s*Resort)?', hotel_brand, text, flags=re.IGNORECASE)
        text = re.sub(r'\bAnvieo\b', hotel_brand, text, flags=re.IGNORECASE)

        # 11. Bersihkan placeholder / variabel template mentah jika terbawa
        text = re.sub(r'\[Nama Resepsionis AI\]', 'Garda', text, flags=re.IGNORECASE)
        text = re.sub(r'\[Nama Hotel(?: Anda)?\]', hotel_brand, text, flags=re.IGNORECASE)
        text = re.sub(r'\[Lokasi Hotel\]', 'Balikpapan Selatan', text, flags=re.IGNORECASE)
        text = re.sub(r'\[jumlah bintang\]', 'favorit', text, flags=re.IGNORECASE)
        text = re.sub(r'\bAkhi\b', 'Bapak/Kakak', text, flags=re.IGNORECASE)
        text = re.sub(r'\bUkhti\b', 'Ibu/Kakak', text, flags=re.IGNORECASE)

        # 12. Rapikan spasi trailing & newline berlebih (maksimal 2 baris kosong)
        text = re.sub(r'[ \t]+$', '', text, flags=re.MULTILINE)
        text = re.sub(r'\n{3,}', '\n\n', text)

        return text.strip()

    @classmethod
    async def chat(
        cls, 
        phone: str, 
        user_message: str, 
        session_id: str = None,
        checkin_date: str = None,
        checkout_date: str = None,
        guest_name: str = None,
        room_type: str = None,
        phone_number: str = None
    ) -> str:
        """
        Mengirim pesan ke Garda LLM API dengan session_id berbasis nomor HP & versi sesi,
        menginjeksi kalender real-time & zona waktu WITA, serta KETERSEDIAAN KAMAR FISIK REAL-TIME (anti-overbooking).
        """
        if not session_id:
            clean_phone = str(phone).replace("@", "_").replace(".", "_").replace("+", "").strip()
            session_id = f"agnia_guesthouse_{clean_phone}_v1"

        # Deteksi tanggal menginap secara cerdas dari pesan tamu jika belum ada
        if not checkin_date or not checkout_date:
            parsed_in, parsed_out = parse_dates_smart(user_message)
            checkin_date = checkin_date or parsed_in
            checkout_date = checkout_date or parsed_out

        system_prompt = get_system_prompt()
        datetime_context = get_clock_calendar_and_timezone_str()
        catalog_content = get_catalog_context_str(checkin_date=checkin_date, checkout_date=checkout_date)

        # Siapkan pesan berkonteks terstruktur agar LLM tidak kehilangan konteks percakapan multi-turn
        context_lines = []
        if guest_name:
            context_lines.append(f"• Nama Pemesan: {guest_name}")
        target_phone = phone_number or phone
        if target_phone:
            context_lines.append(f"• No. WhatsApp: {target_phone}")
        if checkin_date and checkout_date:
            context_lines.append(f"• Periode Menginap: {checkin_date} s/d {checkout_date}")
        if room_type:
            rt_map = {
                "DLX-TWN": "Deluxe Twin Room (AC)",
                "STD-FAN": "Standard Twin / Single Room (Fan)",
                "SUP-DBL": "Superior Double Room (AC)"
            }
            rt_label = rt_map.get(room_type.upper(), room_type)
            context_lines.append(f"• Tipe Kamar Dipilih: {rt_label} ({room_type})")

        # Cek ketersediaan riil tipe kamar di database jika tanggal dan tipe kamar ada
        is_room_available = False
        avail_info = None
        if room_type and checkin_date and checkout_date:
            try:
                from db_hotel_service import HotelDatabaseService
                avail_info = HotelDatabaseService.check_room_availability(room_type, checkin_date, checkout_date)
                is_room_available = avail_info.get("is_available", False)
            except Exception as e:
                logger.warning(f"Error checking room availability in chat: {e}")

        prompt_message = user_message
        if context_lines:
            ctx_block = "[DATA KONTEKS RESERVASI SAAT INI DARI SISTEM]:\n" + "\n".join(context_lines)
            if guest_name and checkin_date and checkout_date and room_type and is_room_available:
                ctx_block += (
                    f"\n• STATUS KETERSEDIAAN: Kamar {room_type} TERVERIFIKASI TERSEDIA ({avail_info.get('available_rooms', 1)} unit kosong)!"
                    f"\n• INSTRUKSI KHUSUS WAJIB: Seluruh data utama (Nama: {guest_name}, "
                    f"Tanggal: {checkin_date} s/d {checkout_date}, Tipe Kamar: {room_type}) "
                    f"SUDAH LENGKAP & TERSEDIA. DILARANG menanyakan lagi tipe kamar atau tanggal! "
                    f"SEGERA tampilkan format 📋 *REKAPITULASI DRAFT RESERVASI* lengkap untuk konfirmasi tamu!"
                )
            elif room_type and checkin_date and checkout_date and not is_room_available:
                ctx_block += (
                    f"\n• PERINGATAN KERAS SISTEM: Kamar tipe {room_type} pada tanggal {checkin_date} s/d {checkout_date} "
                    f"STATUSNYA ADALAH ❌ PENUH / SOLD OUT (0 unit kosong)!"
                    f"\n• DILARANG KERAS membuatkan rekapitulasi draft untuk {room_type}!"
                    f"\n• INSTRUKSI KHUSUS WAJIB: Sampaikan maaf secara santun bahwa tipe {room_type} sudah penuh pada tanggal tersebut. "
                    f"Tawarkan opsi kamar alternatif yang masih ✅ TERSEDIA (seperti Deluxe Twin Room AC atau Standard Twin), "
                    f"atau tawarkan opsi menggeser tanggal menginap!"
                )
            elif room_type and (not checkin_date or not checkout_date):
                ctx_block += f"\n• INSTRUKSI KHUSUS: Tamu telah memilih kamar {room_type}. Tanyakan rencana tanggal check-in dan durasi menginap."
            elif not checkin_date and not checkout_date and is_general_room_inquiry(user_message):
                ctx_block += (
                    f"\n• INSTRUKSI KHUSUS PERTANYAAN KAMAR KOSONG: Tamu menanyakan ketersediaan kamar secara umum / kamar kosong. "
                    f"Sambut dengan ramah khas Agnia Guesthouse Balikpapan (dekat Bandara BPN, zona WITA). "
                    f"Jelaskan status ketersediaan kamar untuk MALAM INI dan BESOK sesuai ringkasan real-time di dokumen lampiran. "
                    f"Sebutkan tipe kamar yang ada beserta tarifnya, lalu tanyakan rencana tanggal menginap tamu secara hangat."
                )
            prompt_message = f"{ctx_block}\n\nPesan Tamu: {user_message}"
        elif not checkin_date and not checkout_date and is_general_room_inquiry(user_message):
            ctx_block = (
                "[DATA KONTEKS RESERVASI SAAT INI DARI SISTEM]:\n"
                "• INSTRUKSI KHUSUS PERTANYAAN KAMAR KOSONG: Tamu menanyakan ketersediaan kamar secara umum / kamar kosong.\n"
                "Sambut dengan ramah khas Agnia Guesthouse Balikpapan (dekat Bandara BPN, zona WITA).\n"
                "Jelaskan status ketersediaan kamar untuk MALAM INI dan BESOK sesuai ringkasan real-time di dokumen lampiran.\n"
                "Sebutkan tipe kamar yang ada (Standard Twin Rp 115k, Deluxe Twin Rp 160k, Superior Double Rp 235k), lalu tanyakan rencana tanggal menginap tamu secara hangat. DILARANG bingung atau bertanya kaku!"
            )
            prompt_message = f"{ctx_block}\n\nPesan Tamu: {user_message}"

        payload = {
            "session_id": session_id,
            "model": settings.GARDA_MODEL,
            "system_prompt": system_prompt.strip(),
            "message": prompt_message,
            "files": [
                {
                    "name": "hotel_clock_calendar_and_timezone.txt",
                    "content": datetime_context
                },
                {
                    "name": "opera_room_catalog.txt",
                    "content": catalog_content
                }
            ]
        }

        headers = {
            "Authorization": f"Bearer {settings.GARDA_API_KEY}",
            "Content-Type": "application/json"
        }

        try:
            async with httpx.AsyncClient(timeout=float(settings.GARDA_TIMEOUT_SECONDS)) as client:
                response = await client.post(
                    settings.GARDA_API_URL,
                    json=payload,
                    headers=headers
                )
                if response.status_code == 200:
                    data = response.json()
                    raw_reply = data.get("response", "Mohon maaf, saat ini sistem sedang memproses antrean. Boleh diulangi pertanyaannya?")
                    return cls.sanitize_wa_text(raw_reply)
                else:
                    logger.error(f"Garda API error HTTP {response.status_code}: {response.text}")
                    return "Halo! Mohon maaf, sistem reservasi kami sedang dalam pemeliharaan sejenak. Pesan Anda telah kami catat."
        except Exception as e:
            logger.error(f"Garda API connection exception: {e}")
            return "Halo! Mohon maaf atas ketidaknyamanannya, ada kendala jaringan sejenak. Boleh hubungi kami kembali dalam beberapa saat?"
