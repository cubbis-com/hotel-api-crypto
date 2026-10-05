"""
Activity & Transaction Logger Module (Format TXT & Structured JSON)
Mencatat seluruh transaksi WhatsApp Gateway (Terima & Kirim Pesan) serta
Transaksi Pembayaran TriPay (Tagihan, Callback, & Simulasi) ke dalam file .txt
dan menyediakan API untuk dashboard monitoring realtime.
"""

import os
import datetime
from typing import Optional, List, Dict, Any
from sqlalchemy.orm import Session
from database import ChatHistory, WebhookEventLog, PaymentTransaction

LOGS_DIR = os.path.join(os.path.dirname(__file__), "logs")
ACTIVITY_LOG_FILE = os.path.join(LOGS_DIR, "activity_logger.txt")

def _get_wita_now_str() -> str:
    """Mengambil string waktu saat ini dalam format WITA (UTC+8)."""
    wita_tz = datetime.timezone(datetime.timedelta(hours=8))
    return datetime.datetime.now(wita_tz).strftime("%Y-%m-%d %H:%M:%S WITA")

def _format_time_to_wita(dt: Optional[datetime.datetime]) -> str:
    if not dt:
        return _get_wita_now_str()
    # Asumsikan dt dari DB adalah UTC, tambahkan 8 jam untuk WITA
    dt_wita = dt + datetime.timedelta(hours=8)
    return dt_wita.strftime("%Y-%m-%d %H:%M:%S WITA")

class ActivityLogger:
    @staticmethod
    def ensure_dir():
        """Memastikan direktori logs/ tersedia."""
        if not os.path.exists(LOGS_DIR):
            os.makedirs(LOGS_DIR, exist_ok=True)
        if not os.path.exists(ACTIVITY_LOG_FILE):
            ActivityLogger.write_header()

    @staticmethod
    def write_header():
        """Menulis header pembuka pada file log text."""
        header = (
            "================================================================================\n"
            "   AGNIA GUESTHOUSE - AUDIT TRAIL & TRANSACTION LOGGER (.TXT FORMAT)\n"
            "   Hotel: Agnia Guesthouse Balikpapan (Kalimantan Timur)\n"
            "   Timezone: WITA (UTC+8)\n"
            f"   File Created: {_get_wita_now_str()}\n"
            "================================================================================\n\n"
        )
        try:
            with open(ACTIVITY_LOG_FILE, "w", encoding="utf-8") as f:
                f.write(header)
        except Exception as e:
            print(f"[ActivityLogger] Error write header: {e}")

    @staticmethod
    def log_event(
        category: str,
        status: str,
        phone: str = "",
        reference: str = "",
        message: str = "",
        extra: str = ""
    ):
        """
        Menulis satu baris log aktivitas ke activity_logger.txt.
        Category: WA-TERIMA, WA-KIRIM, TRIPAY-BILL, TRIPAY-CALLBACK, TRIPAY-SIMULATE, SYSTEM
        """
        try:
            ActivityLogger.ensure_dir()
            timestamp = _get_wita_now_str()
            
            # Format pembersihan pesan satu baris agar rapi di TXT
            clean_msg = " ".join(str(message or "").replace("\r", " ").replace("\n", " ").split())
            if len(clean_msg) > 160:
                clean_msg = clean_msg[:157] + "..."

            parts = [f"[{timestamp}]", f"[{category.upper()}]", f"[{status.upper()}]"]
            if phone:
                parts.append(f"Phone: {phone}")
            if reference:
                parts.append(f"Ref: {reference}")
            if clean_msg:
                parts.append(f"Msg: \"{clean_msg}\"")
            if extra:
                parts.append(f"Info: {extra}")

            line = " | ".join(parts) + "\n"

            with open(ACTIVITY_LOG_FILE, "a", encoding="utf-8") as f:
                f.write(line)
        except Exception as e:
            print(f"[ActivityLogger] Error logging event: {e}")

    @staticmethod
    def log_wa_inbound(phone: str, sender_name: str, message: str, status: str = "DITERIMA"):
        """Mencatat pesan WhatsApp yang DITERIMA dari tamu."""
        extra = f"Sender: {sender_name}" if sender_name else ""
        ActivityLogger.log_event(
            category="WA-TERIMA",
            status=status,
            phone=phone,
            message=message,
            extra=extra
        )

    @staticmethod
    def log_wa_outbound(to_phone: str, message: str, sender_type: str = "Garda AI", status: str = "TERKIRIM"):
        """Mencatat pesan WhatsApp yang DIKIRIM ke tamu (oleh bot / FO)."""
        extra = f"Via: {sender_type}"
        ActivityLogger.log_event(
            category="WA-KIRIM",
            status=status,
            phone=to_phone,
            message=message,
            extra=extra
        )

    @staticmethod
    def log_tripay_create(
        merchant_ref: str,
        tripay_ref: str,
        customer_name: str,
        customer_phone: str,
        total_amount: int,
        payment_method: str = "QRIS"
    ):
        """Mencatat pembuatan tagihan / transaksi baru TriPay."""
        msg = f"Booking {merchant_ref} ({customer_name}) Rp {total_amount:,} via {payment_method}"
        ActivityLogger.log_event(
            category="TRIPAY-BILL",
            status="UNPAID",
            phone=customer_phone,
            reference=f"{merchant_ref}/{tripay_ref}",
            message=msg,
            extra="Menunggu Pembayaran Tamu"
        )

    @staticmethod
    def log_tripay_callback(
        merchant_ref: str,
        tripay_ref: str,
        status: str,
        total_amount: int,
        room_allocated: str = ""
    ):
        """Mencatat penerimaan webhook callback dari TriPay."""
        room_info = f" (Alokasi Kamar {room_allocated})" if room_allocated else ""
        msg = f"Pelunasan TriPay Rp {total_amount:,}{room_info}"
        ActivityLogger.log_event(
            category="TRIPAY-CALLBACK",
            status=status,
            reference=f"{merchant_ref}/{tripay_ref}",
            message=msg,
            extra="Status PMS: Confirmed" if status.upper() == "PAID" else status
        )

    @staticmethod
    def log_tripay_simulate(
        merchant_ref: str,
        tripay_ref: str,
        customer_name: str,
        total_amount: int
    ):
        """Mencatat simulasi pelunasan 1-klik TriPay."""
        msg = f"Simulasi Pelunasan Sukses: {customer_name} Rp {total_amount:,}"
        ActivityLogger.log_event(
            category="TRIPAY-SIMULATE",
            status="PAID",
            reference=f"{merchant_ref}/{tripay_ref}",
            message=msg,
            extra="Simulasi 1-Klik Sandbox"
        )

    @staticmethod
    def log_error(
        module: str,
        error_message: str,
        phone: str = "",
        reference: str = "",
        details: str = "",
        status: str = "ERROR"
    ):
        """Mencatat kejadian error / kendala sistem ke activity_logger.txt."""
        extra = f"Module: {module}"
        if details:
            extra += f" | {details}"
        ActivityLogger.log_event(
            category="ERROR",
            status=status,
            phone=phone,
            reference=reference,
            message=error_message,
            extra=extra
        )

    @staticmethod
    def sync_to_file(db: Session):
        """
        Melakukan sinkronisasi penuh dari database ke activity_logger.txt
        agar file text selalu memuat seluruh pesan dan transaksi terbaru secara lengkap.
        """
        ActivityLogger.ensure_dir()
        events = []

        # 1. Chat History
        chats = db.query(ChatHistory).order_by(ChatHistory.id.asc()).all()
        for c in chats:
            category = "WA-TERIMA" if c.role == "user" else "WA-KIRIM"
            status = "DITERIMA" if c.role == "user" else "TERKIRIM"
            extra = "Tamu (Inbound)" if c.role == "user" else "Garda AI / FO Staff"
            events.append({
                "time": c.created_at or datetime.datetime.utcnow(),
                "category": category,
                "status": status,
                "phone": c.phone or "",
                "reference": "",
                "message": c.message or "",
                "extra": extra
            })

        # 2. Payment Transactions
        txs = db.query(PaymentTransaction).order_by(PaymentTransaction.id.asc()).all()
        for t in txs:
            events.append({
                "time": t.created_at or datetime.datetime.utcnow(),
                "category": "TRIPAY-BILL",
                "status": t.status or "UNPAID",
                "phone": t.customer_phone or "",
                "reference": f"{t.merchant_ref or ''}/{t.reference or ''}",
                "message": f"Tagihan Booking {t.merchant_ref} - {t.customer_name} (Rp {t.total_amount:,})",
                "extra": f"Metode: {t.payment_method or 'QRIS'}"
            })
            if t.paid_at or t.status == "PAID":
                events.append({
                    "time": t.paid_at or t.updated_at or t.created_at or datetime.datetime.utcnow(),
                    "category": "TRIPAY-CALLBACK",
                    "status": "PAID",
                    "phone": t.customer_phone or "",
                    "reference": f"{t.merchant_ref or ''}/{t.reference or ''}",
                    "message": f"Pembayaran Lunas {t.merchant_ref} ({t.customer_name}) Rp {t.total_amount:,}",
                    "extra": "PMS Confirmed"
                })

        events.sort(key=lambda x: x["time"])
        ActivityLogger.write_header()

        try:
            with open(ACTIVITY_LOG_FILE, "a", encoding="utf-8") as f:
                f.write(f"# [AUDIT TRAIL] Total {len(events)} entri transaksi & pesan tercatat\n\n")
                for e in events:
                    wita_time = _format_time_to_wita(e["time"])
                    clean_msg = " ".join(str(e["message"] or "").replace("\r", " ").replace("\n", " ").split())
                    if len(clean_msg) > 160:
                        clean_msg = clean_msg[:157] + "..."
                    parts = [f"[{wita_time}]", f"[{e['category']}]", f"[{e['status']}]"]
                    if e["phone"]:
                        parts.append(f"Phone: {e['phone']}")
                    if e["reference"]:
                        parts.append(f"Ref: {e['reference']}")
                    if clean_msg:
                        parts.append(f"Msg: \"{clean_msg}\"")
                    if e["extra"]:
                        parts.append(f"Info: {e['extra']}")
                    f.write(" | ".join(parts) + "\n")
        except Exception as err:
            print(f"[ActivityLogger] Error during sync_to_file: {err}")

    @staticmethod
    def get_raw_txt(max_lines: int = 1000, db: Optional[Session] = None) -> str:
        """Mengambil teks isi activity_logger.txt (hingga max_lines terakhir)."""
        ActivityLogger.ensure_dir()
        if db:
            try:
                ActivityLogger.sync_to_file(db)
            except Exception as e:
                print(f"[ActivityLogger] Error syncing db to txt: {e}")

        if not os.path.exists(ACTIVITY_LOG_FILE):
            return "Log file empty."
        try:
            with open(ACTIVITY_LOG_FILE, "r", encoding="utf-8", errors="replace") as f:
                lines = f.readlines()
                if len(lines) > max_lines:
                    header = lines[:7]
                    recent = lines[-(max_lines - 7):]
                    return "".join(header + ["[... baris lama dipotong ...]\n"] + recent)
                return "".join(lines)
        except Exception as e:
            return f"Error reading log file: {e}"

    @staticmethod
    def backfill_if_empty(db: Session):
        """
        Jika file activity_logger.txt belum terisi log aktivitas,
        lakukan sinkronisasi dari SQLite (ChatHistory, PaymentTransaction, WebhookEventLog)
        sehingga seluruh riwayat sebelumnya langsung tercatat.
        """
        ActivityLogger.ensure_dir()
        file_size = os.path.getsize(ACTIVITY_LOG_FILE) if os.path.exists(ACTIVITY_LOG_FILE) else 0
        if file_size > 500:
            return
        ActivityLogger.sync_to_file(db)
        try:
            with open(ACTIVITY_LOG_FILE, "a", encoding="utf-8") as f:
                f.write(f"# [INFO] Sinkronisasi otomatis {len(events)} entri riwayat lampau ke file log\n\n")
                for e in events:
                    wita_time = _format_time_to_wita(e["time"])
                    clean_msg = " ".join(str(e["message"] or "").replace("\r", " ").replace("\n", " ").split())
                    if len(clean_msg) > 150:
                        clean_msg = clean_msg[:147] + "..."
                    parts = [f"[{wita_time}]", f"[{e['category']}]", f"[{e['status']}]"]
                    if e["phone"]:
                        parts.append(f"Phone: {e['phone']}")
                    if e["reference"]:
                        parts.append(f"Ref: {e['reference']}")
                    if clean_msg:
                        parts.append(f"Msg: \"{clean_msg}\"")
                    if e["extra"]:
                        parts.append(f"Info: {e['extra']}")
                    f.write(" | ".join(parts) + "\n")
        except Exception as err:
            print(f"[ActivityLogger] Error during backfill: {err}")

    @staticmethod
    def get_unified_activity_feed(db: Session, limit: int = 100, filter_type: str = "ALL", search: str = "") -> Dict[str, Any]:
        """
        Menyusun data aktivitas terpadu (WA & TriPay) dalam bentuk list terstruktur untuk antarmuka tabel web.
        """
        items = []
        search_lower = (search or "").lower().strip()

        # 1. Ambil Pesan WhatsApp (Inbound & Outbound)
        chats_query = db.query(ChatHistory).order_by(ChatHistory.id.desc())
        if search_lower:
            chats_query = chats_query.filter(
                (ChatHistory.phone.contains(search_lower)) |
                (ChatHistory.message.contains(search_lower))
            )
        chats = chats_query.limit(limit).all()

        for c in chats:
            is_user = (c.role == "user")
            cat = "WA_INBOUND" if is_user else "WA_OUTBOUND"
            if filter_type != "ALL" and filter_type != cat and filter_type != "WA_ALL":
                continue

            items.append({
                "id": f"chat_{c.id}",
                "type": "WA",
                "category": cat,
                "badge_label": "PESAN MASUK (TAMU)" if is_user else "PESAN KELUAR (BOT/FO)",
                "badge_color": "emerald" if is_user else "blue",
                "direction": "IN" if is_user else "OUT",
                "phone": c.phone or "-",
                "sender_or_target": "Tamu" if is_user else "Garda AI / FO Staff",
                "status": "Diterima" if is_user else "Terkirim",
                "status_badge": "bg-emerald-500/20 text-emerald-400 border-emerald-500/30" if is_user else "bg-blue-500/20 text-blue-400 border-blue-500/30",
                "reference": "-",
                "amount": None,
                "message": c.message or "",
                "created_at": _format_time_to_wita(c.created_at),
                "timestamp_raw": c.created_at.timestamp() if c.created_at else 0
            })

        # 2. Ambil Transaksi TriPay
        txs_query = db.query(PaymentTransaction).order_by(PaymentTransaction.id.desc())
        if search_lower:
            txs_query = txs_query.filter(
                (PaymentTransaction.reference.contains(search_lower)) |
                (PaymentTransaction.merchant_ref.contains(search_lower)) |
                (PaymentTransaction.customer_name.contains(search_lower)) |
                (PaymentTransaction.customer_phone.contains(search_lower))
            )
        txs = txs_query.limit(limit).all()

        for t in txs:
            if filter_type != "ALL" and filter_type != "TRIPAY":
                continue

            is_paid = (t.status == "PAID")
            status_style = "bg-emerald-500/20 text-emerald-400 border-emerald-500/30" if is_paid else "bg-amber-500/20 text-amber-400 border-amber-500/30"

            items.append({
                "id": f"tx_{t.id}",
                "type": "TRIPAY",
                "category": "TRIPAY",
                "badge_label": "TRIPAY " + (t.payment_method or "QRIS"),
                "badge_color": "purple" if is_paid else "amber",
                "direction": "PAYMENT",
                "phone": t.customer_phone or "-",
                "sender_or_target": t.customer_name or "Tamu",
                "status": t.status or "UNPAID",
                "status_badge": status_style,
                "reference": t.merchant_ref or t.reference or "-",
                "tripay_ref": t.reference or "-",
                "amount": int(t.total_amount or 0),
                "amount_formatted": f"Rp {int(t.total_amount or 0):,}",
                "message": f"Transaksi Booking {t.merchant_ref} - {t.payment_name or 'QRIS'} - Rp {int(t.total_amount or 0):,} ({t.status})",
                "checkout_url": t.checkout_url,
                "created_at": _format_time_to_wita(t.created_at),
                "timestamp_raw": t.created_at.timestamp() if t.created_at else 0
            })

        # 3. Ambil Log Error & Kendala Sistem (dari WebhookEventLog berstatus gagal/error & dari file activity_logger.txt)
        error_items = []

        # 3a. Dari WebhookEventLog
        err_webhooks = db.query(WebhookEventLog).filter(
            WebhookEventLog.status.in_(["failed", "error", "rejected", "exception"])
        ).order_by(WebhookEventLog.id.desc()).limit(limit).all()

        for w in err_webhooks:
            is_err_match = (filter_type in ["ALL", "ERROR"])
            if is_err_match:
                error_items.append({
                    "id": f"webhook_err_{w.id}",
                    "type": "ERROR",
                    "category": "ERROR",
                    "badge_label": "ERROR WEBHOOK",
                    "badge_color": "rose",
                    "direction": "ALERT",
                    "phone": w.sender_phone or "-",
                    "sender_or_target": w.sender_name or "Webhook Gateway",
                    "status": (w.status or "ERROR").upper(),
                    "status_badge": "bg-rose-500/20 text-rose-400 border-rose-500/30",
                    "reference": "-",
                    "amount": None,
                    "message": w.message_content or w.bot_reply or "Kegagalan webhook",
                    "created_at": _format_time_to_wita(w.created_at),
                    "timestamp_raw": w.created_at.timestamp() if w.created_at else 0
                })

        # 3b. Dari baris [ERROR] atau [WARNING] di activity_logger.txt
        txt_err_count = 0
        if os.path.exists(ACTIVITY_LOG_FILE):
            try:
                with open(ACTIVITY_LOG_FILE, "r", encoding="utf-8", errors="replace") as f:
                    err_idx = 0
                    for line in f:
                        if "| [ERROR]" in line or "| [WARNING]" in line:
                            txt_err_count += 1
                            if filter_type not in ["ALL", "ERROR"]:
                                continue

                            parts = [p.strip() for p in line.strip().split(" | ")]
                            t_str = parts[0].replace("[", "").replace("]", "") if len(parts) > 0 else ""
                            cat = parts[1].replace("[", "").replace("]", "") if len(parts) > 1 else "ERROR"
                            st = parts[2].replace("[", "").replace("]", "") if len(parts) > 2 else "FAILED"
                            
                            ph = "-"
                            rf = "-"
                            ms = ""
                            inf = "Sistem"
                            for p in parts[3:]:
                                if p.startswith("Phone:"):
                                    ph = p.replace("Phone:", "").strip()
                                elif p.startswith("Ref:"):
                                    rf = p.replace("Ref:", "").strip()
                                elif p.startswith("Msg:"):
                                    ms = p.replace("Msg:", "").strip().strip('"')
                                elif p.startswith("Info:"):
                                    inf = p.replace("Info:", "").strip()

                            if not ms and len(parts) > 3:
                                ms = parts[3]

                            if search_lower and search_lower not in line.lower():
                                continue

                            is_real_err = (cat == "ERROR")
                            error_items.append({
                                "id": f"txt_err_{err_idx}",
                                "type": "ERROR" if is_real_err else "WARNING",
                                "category": "ERROR",
                                "badge_label": "KENDALA SISTEM" if is_real_err else "PERINGATAN",
                                "badge_color": "rose" if is_real_err else "amber",
                                "direction": "ALERT",
                                "phone": ph,
                                "sender_or_target": inf,
                                "status": st,
                                "status_badge": "bg-rose-500/20 text-rose-400 border-rose-500/30" if is_real_err else "bg-amber-500/20 text-amber-400 border-amber-500/30",
                                "reference": rf,
                                "amount": None,
                                "message": ms,
                                "created_at": t_str,
                                "timestamp_raw": 0
                            })
                            err_idx += 1
            except Exception as e:
                print(f"[ActivityLogger] Error parsing error lines: {e}")

        # Gabungkan item error jika filter sesuai
        if filter_type == "ERROR":
            items = error_items
        else:
            items.extend(error_items)

        # Urutkan berdasarkan waktu paling baru
        items.sort(key=lambda x: x["timestamp_raw"], reverse=True)
        items = items[:limit]

        # Hitung statistik
        total_inbound = db.query(ChatHistory).filter(ChatHistory.role == "user").count()
        total_outbound = db.query(ChatHistory).filter(ChatHistory.role == "assistant").count()
        total_tripay = db.query(PaymentTransaction).count()
        total_tripay_paid = db.query(PaymentTransaction).filter(PaymentTransaction.status == "PAID").count()
        total_errors = len(err_webhooks) + txt_err_count

        return {
            "stats": {
                "total_inbound": total_inbound,
                "total_outbound": total_outbound,
                "total_tripay": total_tripay,
                "total_tripay_paid": total_tripay_paid,
                "total_errors": total_errors,
                "total_events": total_inbound + total_outbound + total_tripay + total_errors
            },
            "items": items
        }


import logging

class ActivityLoggerHandler(logging.Handler):
    """
    Handler logging Python otomatis yang mencegat seluruh panggilan
    logger.error(...) dan logger.warning(...) di seluruh sistem (WA, TriPay, Database, LLM)
    dan langsung mencatatnya ke dalam file activity_logger.txt.
    """
    def emit(self, record):
        if record.levelno >= logging.ERROR:
            try:
                msg = self.format(record)
                ActivityLogger.log_event(
                    category="ERROR",
                    status="FAILED",
                    message=msg,
                    extra=f"Module: {record.name} (L{record.lineno})"
                )
            except Exception:
                pass
        elif record.levelno == logging.WARNING:
            msg_str = record.getMessage().lower()
            if any(k in msg_str for k in ["overbooking", "gagal", "fail", "timeout", "reject", "mismatch", "error"]):
                try:
                    msg = self.format(record)
                    ActivityLogger.log_event(
                        category="WARNING",
                        status="WARN",
                        message=msg,
                        extra=f"Module: {record.name}"
                    )
                except Exception:
                    pass

def setup_root_error_logging():
    """Menghubungkan ActivityLoggerHandler ke root logger Python."""
    root_logger = logging.getLogger()
    for h in root_logger.handlers:
        if isinstance(h, ActivityLoggerHandler):
            return
    handler = ActivityLoggerHandler()
    handler.setLevel(logging.WARNING)
    formatter = logging.Formatter("%(name)s: %(message)s")
    handler.setFormatter(formatter)
    root_logger.addHandler(handler)
