import os
import logging
import httpx
import datetime
from fastapi import FastAPI, Request, Depends, HTTPException, BackgroundTasks, Header
from fastapi.middleware.cors import CORSMiddleware
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse, Response, FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from sqlalchemy.orm import Session
from contextlib import asynccontextmanager
from typing import Optional, List

import json
from config import settings
from database import (
    init_db, get_db, SessionLocal, ReservationInquiry, ChatHistory, WebhookEventLog, PaymentTransaction,
    GardaSessionState, get_or_create_garda_session_id, reset_garda_session,
    CryptoEscrow, OnChainAuditRecord, LoyaltyAccount, LoyaltyTransactionRecord
)
from crypto_service import CryptoSecurePayService
from tripay_service import TriPayService
from opera_catalog import ROOM_TYPES, get_catalog_context_str, get_room_types
from db_hotel_service import HotelDatabaseService
from garda_service import GardaService, parse_dates_smart, is_general_room_inquiry
from wa_service import WhatsAppService
from qr_service import QRService
from activity_logger import ActivityLogger, ACTIVITY_LOG_FILE, setup_root_error_logging

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
setup_root_error_logging()
logger = logging.getLogger("hotel_ai_main")


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    logger.info(f"Database initialized. Server running for {settings.HOTEL_NAME}")
    try:
        with SessionLocal() as s_db:
            ActivityLogger.backfill_if_empty(s_db)
    except Exception as log_err:
        logger.warning(f"Backfill activity logger warning: {log_err}")
    try:
        await WhatsAppService.disable_gateway_internal_bot()
    except Exception as e:
        logger.warning(f"Tidak dapat memverifikasi status bot gateway saat startup: {e}")
    yield


app = FastAPI(
    title="Garda Hotel AI - WhatsApp Reservation Service",
    description="Layanan AI Resepsionis Virtual berbasis Garda LLM & integrasi WhatsApp Gateway Wuller/wa.",
    version="1.0.0",
    lifespan=lifespan
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
templates = Jinja2Templates(directory=os.path.join(BASE_DIR, "templates"))

# Buat dan mount direktori static untuk file gambar QR Code lokal
STATIC_DIR = os.path.join(BASE_DIR, "static")
os.makedirs(os.path.join(STATIC_DIR, "qr"), exist_ok=True)

@app.api_route("/static/qr/{filename}", methods=["GET", "HEAD"])
async def serve_static_qr_file(filename: str, db: Session = Depends(get_db)):
    """
    Menyajikan file QR Code PNG dari static/qr/.
    Jika file fisik belum ada (misal setelah container restart di Railway),
    generate otomatis on-the-fly dari TriPay / database lalu simpan & sajikan.
    """
    file_path = os.path.join(STATIC_DIR, "qr", filename)
    if os.path.exists(file_path):
        with open(file_path, "rb") as f:
            return Response(content=f.read(), media_type="image/png")

    ref = filename.replace(".png", "")
    tx = db.query(PaymentTransaction).filter(
        (PaymentTransaction.reference == ref) | (PaymentTransaction.merchant_ref == ref)
    ).first()

    qr_url = None
    qr_string = None
    fallback_url = None

    if tx:
        fallback_url = tx.checkout_url
        if tx.raw_payload:
            try:
                payload = json.loads(tx.raw_payload)
                qr_url = payload.get("qr_url")
                qr_string = payload.get("qr_string")
                fallback_url = payload.get("checkout_url") or fallback_url
            except Exception:
                pass
    else:
        fallback_url = f"https://tripay.co.id/checkout/{ref}"

    _, png_bytes, mime = await QRService.resolve_qr_media(
        qr_url=qr_url,
        qr_string=qr_string,
        fallback_url=fallback_url
    )

    if png_bytes:
        QRService.save_qr_locally(filename, png_bytes)
        return Response(content=png_bytes, media_type=mime)

    raise HTTPException(status_code=404, detail="QR Code image not found")

app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

# -------------------------------------------------------------
# Web Dashboard (Front Office & Konfigurasi)
# -------------------------------------------------------------
@app.get("/", response_class=HTMLResponse)
@app.get("/dashboard", response_class=HTMLResponse)
def dashboard(request: Request, db: Session = Depends(get_db)):
    """Menampilkan Dashboard Front Office & Konfigurasi WhatsApp Web serta Crypto SecurePay."""
    rooms = get_room_types()
    tenant_status = HotelDatabaseService.get_tenant_status()
    crypto_stats = CryptoSecurePayService.get_dashboard_crypto_stats(db)
    escrows = db.query(CryptoEscrow).order_by(CryptoEscrow.id.desc()).limit(20).all()
    onchain_records = db.query(OnChainAuditRecord).order_by(OnChainAuditRecord.id.desc()).limit(20).all()
    loyalty_members = db.query(LoyaltyAccount).order_by(LoyaltyAccount.balance.desc()).limit(10).all()

    return templates.TemplateResponse(
        request=request,
        name="dashboard.html",
        context={
            "hotel_name": settings.HOTEL_NAME,
            "settings": settings,
            "rooms": rooms,
            "tenant_status": tenant_status,
            "crypto_stats": crypto_stats,
            "escrows": escrows,
            "onchain_records": onchain_records,
            "loyalty_members": loyalty_members
        }
    )

@app.get("/api/v1/tenant/status")
def get_tenant_status_endpoint():
    """Mengambil status dan metadata tenant Agnia Guesthouse dari database."""
    return HotelDatabaseService.get_tenant_status()

@app.get("/api/v1/tenant/schema-tables")
def get_tenant_schema_tables_endpoint():
    """Melihat daftar seluruh tabel dalam schema database tenant saat ini."""
    return HotelDatabaseService.get_schema_tables()

@app.get("/api/v1/catalog")
def get_catalog():
    """Melihat katalog kamar standar OPERA PMS, season aktif, dan paket promo yang aktif dari PostgreSQL."""
    return {
        "hotel": settings.HOTEL_NAME,
        "tenant_id": settings.TENANT_ID,
        "schema": settings.POSTGRES_SCHEMA,
        "rooms": get_room_types(),
        "seasons": HotelDatabaseService.get_active_seasons(),
        "packages": HotelDatabaseService.get_active_packages()
    }

@app.get("/api/v1/seasons")
def get_seasons():
    """Melihat kalender season dan rate multipliers yang berlaku."""
    return {"seasons": HotelDatabaseService.get_active_seasons()}

@app.get("/api/v1/packages")
def get_packages():
    """Melihat paket diskon dan promo hotel yang aktif."""
    return {"packages": HotelDatabaseService.get_active_packages()}

@app.get("/api/v1/availability")
def check_availability(room_type: str, checkin: str, checkout: str):
    """Memeriksa sisa kamar kosong pada rentang tanggal tertentu."""
    return HotelDatabaseService.check_room_availability(room_type, checkin, checkout)

class CreateReservationRequest(BaseModel):
    guest_name: str
    guest_phone: str
    room_type_code: str
    checkin_date: str
    checkout_date: str
    adults: int = 1
    children: int = 0
    special_requests: Optional[str] = None
    estimated_total: float = 0.0
    deposit_amount: float = 0.0
    status: str = "reserved"
    booking_source: str = "Reservasi Online / WA"
    merchant_ref: Optional[str] = None

@app.post("/api/v1/reservations")
def create_reservation_endpoint(req: CreateReservationRequest):
    """Membuat reservasi baru langsung ke PMS database PostgreSQL menggunakan role AI."""
    try:
        res = HotelDatabaseService.create_reservation(
            guest_name=req.guest_name,
            guest_phone=req.guest_phone,
            room_type_code=req.room_type_code,
            checkin_date=req.checkin_date,
            checkout_date=req.checkout_date,
            adults=req.adults,
            children=req.children,
            special_requests=req.special_requests,
            estimated_total=req.estimated_total,
            deposit_amount=req.deposit_amount,
            status=req.status,
            booking_source=req.booking_source,
            merchant_ref=req.merchant_ref
        )
        return {"status": "success", "reservation": res}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

class FolioPaymentRequest(BaseModel):
    reservation_id: str
    guest_name: str
    room_number: Optional[str] = None
    total_amount: float
    payment_amount: float
    payment_method: str = "QRIS / Transfer Bank"

@app.post("/api/v1/folios/payment")
def create_folio_payment_endpoint(req: FolioPaymentRequest):
    """Membuka folio dan mencatat transaksi pembayaran/deposit ke PMS database."""
    try:
        folio = HotelDatabaseService.create_folio_and_payment(
            reservation_id=req.reservation_id,
            guest_name=req.guest_name,
            room_number=req.room_number,
            total_amount=req.total_amount,
            payment_amount=req.payment_amount,
            payment_method=req.payment_method
        )
        return {"status": "success", "folio": folio}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# -------------------------------------------------------------
# Integrasi TriPay Payment Gateway & Webhook Callback
# -------------------------------------------------------------
async def notify_guest_payment_success(
    phone: str,
    customer_name: str,
    merchant_ref: str,
    reference: str,
    total_amount: int,
    payment_method: str,
    reservation_no: Optional[str] = None,
    room_number: Optional[str] = None
):
    """Mengirim pesan notifikasi WhatsApp resmi setelah pembayaran diverifikasi oleh TriPay."""
    if not phone:
        return

    if "@lid" in phone:
        target_phone = phone
    else:
        clean_digits = "".join(ch for ch in phone if ch.isdigit())
        if clean_digits.startswith("08"):
            clean_digits = "62" + clean_digits[1:]
        target_phone = clean_digits or phone

    rsv_line = f"• *No. Reservasi PMS:* {reservation_no}\n" if reservation_no else ""
    room_line = f"• *Alokasi Kamar:* Kamar {room_number}\n" if room_number else "• *Alokasi Kamar:* Sesuai tipe pesanan (Ready saat check-in)\n"

    msg = (
        f"✅ *PEMBAYARAN RESERVASI DITERIMA*\n\n"
        f"Halo Bapak/Ibu *{customer_name or 'Tamu'}*,\n"
        f"Pembayaran Anda untuk reservasi di *{settings.HOTEL_NAME}* telah berhasil kami terima dan diverifikasi secara otomatis.\n\n"
        f"📋 *Rincian Pembayaran & Reservasi:*\n"
        f"{rsv_line}"
        f"• *Kode Booking:* {merchant_ref}\n"
        f"• *No. Referensi Transaksi:* {reference}\n"
        f"• *Metode Pembayaran:* {payment_method}\n"
        f"• *Total Pelunasan:* Rp {int(total_amount):,}\n"
        f"{room_line}"
        f"• *Status:* 🟢 LUNAS & TERKONFIRMASI (CONFIRMED)\n\n"
        f"Kamar Anda telah berhasil dikonfirmasi dan masuk ke sistem reservasi hotel kami (Stay View). Silakan tunjukkan pesan WhatsApp ini saat proses check-in di Front Desk.\n\n"
        f"Terima kasih telah memilih {settings.HOTEL_NAME}! 🤝"
    )

    # 1. Catat ke ChatHistory
    db = SessionLocal()
    try:
        db.add(ChatHistory(phone=target_phone, role="assistant", message=msg))
        db.commit()
    finally:
        db.close()

    # 2. Kirim pesan ke WhatsApp tamu
    await WhatsAppService.send_message(target_phone, msg)

@app.get("/api/v1/payment/tripay-callback")
def get_tripay_callback_status():
    """Endpoint pengecekan status (health check) callback TriPay Payment Gateway."""
    return {
        "status": "online",
        "service": "hotel-api-crypto",
        "endpoint": "/api/v1/payment/tripay-callback",
        "method": "POST",
        "callback_url": settings.tripay_callback_url,
        "merchant_code": settings.TRIPAY_MERCHANT_CODE,
        "message": "TriPay callback webhook endpoint is active and listening for POST events."
    }

@app.post("/api/v1/payment/tripay-callback")
async def tripay_webhook_callback(
    request: Request,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    x_callback_signature: Optional[str] = Header(None, alias="X-Callback-Signature"),
    x_callback_event: Optional[str] = Header(None, alias="X-Callback-Event")
):
    """
    Endpoint resmi penerima notifikasi webhook callback dari TriPay Payment Gateway.
    Menerima notifikasi perubahan status transaksi (PAID, EXPIRED, FAILED, REFUND).
    URL: https://hotel-api-crypto-production.up.railway.app/api/v1/payment/tripay-callback
    """
    raw_body = await request.body()

    if not x_callback_signature:
        logger.warning("Callback TriPay ditolak: Header X-Callback-Signature tidak ditemukan")
        raise HTTPException(status_code=400, detail="Missing X-Callback-Signature header")

    # 1. Verifikasi Integritas HMAC-SHA256 Signature
    if not TriPayService.verify_callback_signature(raw_body, x_callback_signature):
        logger.error(f"Callback TriPay ditolak: Signature mismatch. Header: {x_callback_signature}")
        raise HTTPException(status_code=403, detail="Invalid Callback Signature")

    try:
        payload = json.loads(raw_body.decode("utf-8"))
    except Exception as e:
        logger.error(f"Gagal parse JSON body callback TriPay: {e}")
        raise HTTPException(status_code=400, detail="Invalid JSON payload")

    event = x_callback_event or payload.get("event") or "payment_status"
    reference = payload.get("reference")
    merchant_ref = payload.get("merchant_ref")
    payment_method = payload.get("payment_method") or payload.get("payment_method_code", "TriPay")
    total_amount = int(payload.get("total_amount") or 0)
    fee = int(payload.get("total_fee") or payload.get("fee_merchant") or 0)
    amount_received = int(payload.get("amount_received") or 0)
    status = str(payload.get("status") or "").upper().strip()  # PAID, EXPIRED, FAILED, REFUND
    paid_at_ts = payload.get("paid_at")
    note = payload.get("note")

    logger.info(f"Menerima Webhook TriPay: {reference} ({merchant_ref}) -> Status: {status}, Total: {total_amount}")

    # 2. Catat instan ke WebhookEventLog untuk realtime dashboard monitoring
    w_log = WebhookEventLog(
        event_type=f"tripay.{event}",
        sender_phone=merchant_ref or reference or "TRIPAY",
        sender_name=f"TriPay Gateway ({status})",
        message_content=f"Payment {reference} ({merchant_ref}): Rp {total_amount:,} status is {status}",
        status=status.lower(),
        bot_reply=f"Payment callback processed: {status}",
        raw_payload=raw_body.decode("utf-8", errors="ignore")
    )
    db.add(w_log)

    # 3. Simpan / Perbarui transaksi di PaymentTransaction
    tx = db.query(PaymentTransaction).filter(PaymentTransaction.reference == reference).first()
    if not tx and merchant_ref:
        tx = db.query(PaymentTransaction).filter(PaymentTransaction.merchant_ref == merchant_ref).first()

    paid_at_dt = datetime.datetime.fromtimestamp(paid_at_ts) if paid_at_ts else (datetime.datetime.utcnow() if status == "PAID" else None)

    if tx:
        tx.status = status
        tx.amount_received = amount_received or tx.amount_received
        tx.fee = fee or tx.fee
        if paid_at_dt:
            tx.paid_at = paid_at_dt
        if note:
            tx.note = note
    else:
        tx = PaymentTransaction(
            reference=reference,
            merchant_ref=merchant_ref,
            payment_method=payload.get("payment_method_code"),
            payment_name=payment_method,
            total_amount=total_amount,
            fee=fee,
            amount_received=amount_received,
            status=status,
            note=note,
            raw_payload=raw_body.decode("utf-8", errors="ignore"),
            paid_at=paid_at_dt
        )
        db.add(tx)

    # 4. Jika status PAID: Update status reservasi di PMS PostgreSQL & kirim notifikasi WhatsApp ke tamu
    if status == "PAID":
        phone_to_notify = (tx.customer_phone if tx else None)
        customer_name = (tx.customer_name if tx else None) or "Tamu"

        if not phone_to_notify and merchant_ref:
            inquiry = db.query(ReservationInquiry).filter(
                (ReservationInquiry.phone.in_([merchant_ref, merchant_ref.replace("BOOK-", "")])) |
                (ReservationInquiry.summary_text.contains(merchant_ref))
            ).first()
            if inquiry:
                phone_to_notify = inquiry.phone
                customer_name = inquiry.guest_name or inquiry.display_name or customer_name
                inquiry.status = "CONFIRMED"

        # Hubungkan ke PMS PostgreSQL: Mengubah status reservasi ke 'confirmed' (muncul di Hotel Stay View),
        # mengalokasikan nomor kamar fisik, serta menerbitkan Folio + deposit pembayaran lunas
        pms_res = None
        try:
            pms_res = HotelDatabaseService.confirm_payment_and_activate_reservation(
                merchant_ref=merchant_ref or reference or "",
                payment_amount=float(total_amount),
                payment_method=payment_method,
                phone=phone_to_notify,
                tripay_ref=reference
            )
            if pms_res:
                logger.info(f"[PMS Webhook] Reservasi {pms_res.get('reservation_no')} aktif di Stay View (Kamar: {pms_res.get('room_number')})")
        except Exception as pms_err:
            logger.error(f"[PMS Webhook] Error aktivasi reservasi PMS: {pms_err}")

        # Sinkronkan nomor WhatsApp dan nama tamu jika dari transaksi lokal kosong
        if pms_res:
            if not phone_to_notify and pms_res.get("guest_phone"):
                phone_to_notify = pms_res.get("guest_phone")
            if (not customer_name or customer_name == "Tamu") and pms_res.get("guest_name"):
                customer_name = pms_res.get("guest_name")

        reservation_no = pms_res.get("reservation_no") if pms_res else None
        room_number = pms_res.get("room_number") if pms_res else None

        if phone_to_notify:
            # 1. Auto-reset sesi Garda LLM agar obrolan berikutnya dimulai sebagai sesi baru yang segar (fresh receptionist persona)
            try:
                new_sess = reset_garda_session(phone_to_notify, db, reason=f"payment_paid_{reference}")
                logger.info(f"[Auto-Reset] Sesi Garda untuk {phone_to_notify} berhasil direset ke {new_sess} setelah pelunasan {reference}")
            except Exception as reset_err:
                logger.error(f"[Auto-Reset] Gagal mereset sesi Garda untuk {phone_to_notify}: {reset_err}")

            # 2. Tandai seluruh inquiry aktif untuk nomor ini menjadi 'PAID' agar draft lama tidak terbawa lagi
            try:
                db.query(ReservationInquiry).filter(
                    ReservationInquiry.phone == phone_to_notify,
                    ReservationInquiry.status.notin_(["CANCELLED"])
                ).update({"status": "PAID"}, synchronize_session=False)
            except Exception as inq_err:
                logger.error(f"[Inquiry Update] Gagal update status inquiry ke PAID: {inq_err}")

            background_tasks.add_task(
                notify_guest_payment_success,
                phone=phone_to_notify,
                customer_name=customer_name,
                merchant_ref=merchant_ref,
                reference=reference,
                total_amount=total_amount,
                payment_method=payment_method,
                reservation_no=reservation_no,
                room_number=room_number
            )

            # 🆕 ON-CHAIN HASH NOTARIZATION (SecurePayRegistry.sol)
            try:
                await CryptoSecurePayService.record_onchain_transaction(
                    db=db,
                    reference=reference,
                    booking_ref=merchant_ref or reference,
                    payment_method=payment_method,
                    amount=float(total_amount),
                    currency="IDR"
                )
            except Exception as e_notary:
                logger.warning(f"[Tripay Webhook] Gagal notarisasi on-chain: {e_notary}")

            # 🆕 LOYALTY REWARD POINTS (LoyaltyToken.sol - 5% ANV)
            try:
                CryptoSecurePayService.award_loyalty_points(
                    db=db,
                    phone=phone_to_notify,
                    booking_ref=merchant_ref or reference,
                    amount_idr=total_amount
                )
            except Exception as e_loyalty:
                logger.warning(f"[Tripay Webhook] Gagal cetak poin loyalitas: {e_loyalty}")

        try:
            ActivityLogger.log_tripay_callback(
                merchant_ref=merchant_ref,
                tripay_ref=reference,
                status=status,
                total_amount=total_amount,
                room_allocated=str(room_number or "")
            )
        except Exception:
            pass

    db.commit()

    # 5. Respon Wajib TriPay (Harus JSON {"success": true})
    return {"success": True}

class CreatePaymentRequest(BaseModel):
    method: str = "BRIVA"
    merchant_ref: str
    amount: int
    customer_name: str
    customer_email: str = "tamu@hotel.com"
    customer_phone: str
    order_items: List[dict]
    return_url: Optional[str] = None
    expired_time: Optional[int] = None

@app.post("/api/v1/payment/create-transaction")
async def create_payment_transaction(req: CreatePaymentRequest, db: Session = Depends(get_db)):
    """Membuat transaksi pembayaran TriPay (Closed Payment) baru."""
    res = await TriPayService.create_closed_transaction(
        method=req.method,
        merchant_ref=req.merchant_ref,
        amount=req.amount,
        customer_name=req.customer_name,
        customer_email=req.customer_email,
        customer_phone=req.customer_phone,
        order_items=req.order_items,
        return_url=req.return_url,
        expired_time=req.expired_time
    )

    if res.get("success") and res.get("data"):
        d = res["data"]
        tx = PaymentTransaction(
            reference=d.get("reference"),
            merchant_ref=d.get("merchant_ref"),
            payment_method=d.get("payment_method"),
            payment_name=d.get("payment_name"),
            customer_name=d.get("customer_name"),
            customer_phone=d.get("customer_phone"),
            customer_email=d.get("customer_email"),
            total_amount=d.get("amount", req.amount),
            fee=d.get("total_fee", 0),
            amount_received=d.get("amount_received", req.amount),
            pay_code=d.get("pay_code"),
            checkout_url=d.get("checkout_url"),
            status=d.get("status", "UNPAID"),
            raw_payload=json.dumps(d)
        )
        db.add(tx)
        db.commit()

    return res

@app.get("/api/v1/payment/channels")
async def get_payment_channels():
    """Mengambil daftar saluran pembayaran TriPay aktif."""
    return await TriPayService.get_payment_channels()

@app.get("/api/v1/payment/transactions")
def list_payment_transactions(limit: int = 50, db: Session = Depends(get_db)):
    """Melihat daftar seluruh transaksi pembayaran TriPay yang tercatat."""
    txs = db.query(PaymentTransaction).order_by(PaymentTransaction.id.desc()).limit(limit).all()
    return txs

@app.get("/api/v1/payment/detail/{reference}")
async def get_payment_detail(reference: str, db: Session = Depends(get_db)):
    """Mengambil detail status pembayaran langsung dari TriPay API."""
    local_tx = db.query(PaymentTransaction).filter(PaymentTransaction.reference == reference).first()
    remote = await TriPayService.get_transaction_detail(reference)
    return {
        "local": local_tx,
        "tripay": remote
    }


@app.get("/api/v1/payment/simulate-pay/{ref}", response_class=HTMLResponse)
@app.post("/api/v1/payment/simulate-pay/{ref}")
async def simulate_pay_endpoint(
    ref: str,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db)
):
    """
    [SANDBOX HELPER] Mensimulasikan pelunasan pembayaran secara instan untuk transaksi tertentu.
    Memicu aktivasi reservasi PMS ke status 'confirmed', membuat folio, dan mengirim bukti pelunasan WhatsApp.
    Mendukung ref berupa reference TriPay (DEV-...) maupun kode booking hotel (AGH-...).
    """
    clean_digits = "".join(ch for ch in ref if ch.isdigit())
    tx = db.query(PaymentTransaction).filter(
        (PaymentTransaction.reference == ref) |
        (PaymentTransaction.merchant_ref == ref) |
        (PaymentTransaction.merchant_ref.contains(clean_digits[-8:] if len(clean_digits) >= 8 else clean_digits))
    ).order_by(PaymentTransaction.id.desc()).first()

    merchant_ref = tx.merchant_ref if tx else ref
    tripay_ref = tx.reference if tx else ref
    total_amount = int(tx.total_amount) if tx else 250000
    phone_to_notify = tx.customer_phone if tx else None
    customer_name = tx.customer_name if tx else "Tamu"

    # 1. Update status transaksi lokal
    if tx:
        tx.status = "PAID"
        tx.paid_at = datetime.datetime.utcnow()
        db.commit()

    # 2. Catat ke WebhookEventLog
    w_log = WebhookEventLog(
        event_type="tripay.payment_status",
        sender_phone=merchant_ref,
        sender_name="TriPay Simulator (PAID)",
        message_content=f"Payment {tripay_ref} ({merchant_ref}): Rp {total_amount:,} status is PAID (Simulated)",
        status="paid",
        bot_reply="Payment callback processed: PAID (Simulated)"
    )
    db.add(w_log)
    db.commit()

    # 3. Hubungkan ke PMS PostgreSQL
    pms_res = None
    try:
        pms_res = HotelDatabaseService.confirm_payment_and_activate_reservation(
            merchant_ref=merchant_ref,
            payment_amount=float(total_amount),
            payment_method="QRIS Sandbox (Simulasi)",
            phone=phone_to_notify,
            tripay_ref=tripay_ref
        )
    except Exception as e:
        logger.error(f"[Simulate Pay] Error aktivasi PMS: {e}")

    if pms_res:
        if not phone_to_notify and pms_res.get("guest_phone"):
            phone_to_notify = pms_res.get("guest_phone")
        if (not customer_name or customer_name == "Tamu") and pms_res.get("guest_name"):
            customer_name = pms_res.get("guest_name")

    reservation_no = pms_res.get("reservation_no") if pms_res else None
    room_number = pms_res.get("room_number") if pms_res else None

    # 4. Kirim notifikasi WhatsApp ke tamu
    if phone_to_notify:
        try:
            reset_garda_session(phone_to_notify, db, reason=f"payment_paid_simulated_{tripay_ref}")
        except Exception:
            pass

        try:
            db.query(ReservationInquiry).filter(
                ReservationInquiry.phone == phone_to_notify,
                ReservationInquiry.status.notin_(["CANCELLED"])
            ).update({"status": "PAID"}, synchronize_session=False)
            db.commit()
        except Exception:
            pass

        background_tasks.add_task(
            notify_guest_payment_success,
            phone=phone_to_notify,
            customer_name=customer_name,
            merchant_ref=merchant_ref,
            reference=tripay_ref,
            total_amount=total_amount,
            payment_method="QRIS Sandbox (Simulasi)",
            reservation_no=reservation_no,
            room_number=room_number
        )

    # 5. Notarisasi on-chain (SecurePayRegistry.sol) & Award Loyalitas (ANV Token)
    try:
        await CryptoSecurePayService.record_onchain_transaction(
            db=db,
            reference=tripay_ref,
            booking_ref=merchant_ref or tripay_ref,
            payment_method="QRIS Sandbox (Simulasi)",
            amount=float(total_amount),
            currency="IDR"
        )
        if phone_to_notify:
            CryptoSecurePayService.award_loyalty_points(
                db=db,
                phone=phone_to_notify,
                booking_ref=merchant_ref or tripay_ref,
                amount_idr=total_amount
            )
    except Exception as e_crypto:
        logger.warning(f"Simulate pay crypto notarization warning: {e_crypto}")

    try:
        ActivityLogger.log_tripay_simulate(
            merchant_ref=merchant_ref,
            tripay_ref=tripay_ref,
            customer_name=customer_name,
            total_amount=total_amount
        )
    except Exception:
        pass

    html_content = f"""
    <!DOCTYPE html>
    <html lang="id">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Simulasi Pelunasan Berhasil</title>
        <style>
            body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; background: #f1f5f9; display: flex; align-items: center; justify-content: center; min-height: 100vh; margin: 0; padding: 20px; }}
            .card {{ background: white; max-width: 520px; width: 100%; border-radius: 16px; padding: 32px; box-shadow: 0 10px 25px -5px rgba(0,0,0,0.08); text-align: center; }}
            .badge {{ display: inline-block; background: #dcfce7; color: #15803d; font-weight: 700; padding: 6px 16px; border-radius: 9999px; margin-bottom: 16px; font-size: 14px; }}
            h1 {{ font-size: 22px; color: #0f172a; margin-bottom: 8px; }}
            p {{ color: #475569; font-size: 15px; line-height: 1.5; }}
            .info-box {{ background: #f8fafc; border: 1px solid #e2e8f0; border-radius: 12px; padding: 16px; margin: 20px 0; text-align: left; font-size: 14px; }}
            .info-row {{ display: flex; justify-content: space-between; margin-bottom: 8px; }}
            .info-label {{ color: #64748b; }}
            .info-val {{ font-weight: 600; color: #0f172a; }}
            .btn {{ display: inline-block; background: #2563eb; color: white; padding: 12px 24px; border-radius: 8px; text-decoration: none; font-weight: 600; margin-top: 8px; }}
        </style>
    </head>
    <body>
        <div class="card">
            <span class="badge">SIMULASI BERHASIL</span>
            <h1>Pembayaran Berhasil Dilunaskan!</h1>
            <p>Transaksi ini telah berhasil disimulasikan sebagai <b>LUNAS (PAID)</b> pada sistem hotel.</p>
            <div class="info-box">
                <div class="info-row"><span class="info-label">Kode Booking:</span><span class="info-val">{merchant_ref}</span></div>
                <div class="info-row"><span class="info-label">Referensi TriPay:</span><span class="info-val">{tripay_ref}</span></div>
                <div class="info-row"><span class="info-label">Nama Tamu:</span><span class="info-val">{customer_name}</span></div>
                <div class="info-row"><span class="info-label">WhatsApp Tujuan:</span><span class="info-val">{phone_to_notify or '-'}</span></div>
                <div class="info-row"><span class="info-label">Total Pelunasan:</span><span class="info-val">Rp {total_amount:,}</span></div>
                <div class="info-row"><span class="info-label">No. Reservasi PMS:</span><span class="info-val">{reservation_no or 'Aktif di PMS'}</span></div>
                <div class="info-row"><span class="info-label">Kamar Terpilih:</span><span class="info-val">{f'Kamar {room_number}' if room_number else 'Sesuai Tipe'}</span></div>
            </div>
            <p style="font-size: 13px; color: #64748b;">Notifikasi WhatsApp konfirmasi pelunasan resmi sedang/telah dikirimkan secara otomatis ke nomor tamu.</p>
            <a href="/" class="btn">Kembali ke Dashboard</a>
        </div>
    </body>
    </html>
    """
    return HTMLResponse(content=html_content)


@app.get("/api/v1/payment/qr/{ref}")
async def get_payment_qr_image(ref: str, db: Session = Depends(get_db)):
    """
    Menampilkan dan menyajikan file gambar QR Code (PNG) langsung di browser atau untuk dibagikan.
    Mendukung pencarian via reference TriPay (e.g. DEV-T52086...) maupun merchant_ref (e.g. AGH-...).
    Jika gambar resmi tidak dapat diakses, QR Code akan digenerate secara lokal on-the-fly.
    """
    tx = db.query(PaymentTransaction).filter(
        (PaymentTransaction.reference == ref) | (PaymentTransaction.merchant_ref == ref)
    ).first()

    qr_url = None
    qr_string = None
    fallback_url = None

    if tx:
        fallback_url = tx.checkout_url
        if tx.raw_payload:
            try:
                payload = json.loads(tx.raw_payload)
                qr_url = payload.get("qr_url")
                qr_string = payload.get("qr_string")
                fallback_url = payload.get("checkout_url") or fallback_url
            except Exception:
                pass
    else:
        if ref.startswith("http"):
            fallback_url = ref

    _, png_bytes, mime = await QRService.resolve_qr_media(
        qr_url=qr_url,
        qr_string=qr_string,
        fallback_url=fallback_url or f"https://tripay.co.id/checkout/{ref}"
    )

    if png_bytes:
        return Response(content=png_bytes, media_type=mime)

    raise HTTPException(status_code=404, detail="QR Code tidak ditemukan atau gagal digenerate.")


# -------------------------------------------------------------
# Konfigurasi Pendaftaran Webhook Otomatis ke WA Gateway
# -------------------------------------------------------------
class RegisterWebhookRequest(BaseModel):
    webhook_url: str

@app.post("/api/v1/config/register-webhook")
async def register_webhook_to_gateway(req: RegisterWebhookRequest):
    """
    Mendaftarkan URL webhook service ini ke WhatsApp Gateway Wuller/wa secara otomatis via API.
    """
    endpoint = f"{settings.WA_GATEWAY_URL}/api/instances/{settings.WA_INSTANCE_ID}/webhooks"
    headers = {
        "Authorization": f"Bearer {settings.WA_API_KEY}",
        "Content-Type": "application/json"
    }
    payload = {
        "url": req.webhook_url,
        "webhook_secret": settings.WEBHOOK_SECRET
    }

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            res = await client.post(endpoint, json=payload, headers=headers)
            if res.status_code in [200, 201]:
                logger.info(f"Webhook berhasil didaftarkan ke gateway: {req.webhook_url}")
                return {"status": "success", "data": res.json()}
            else:
                logger.error(f"Gagal daftarkan webhook ke gateway, HTTP {res.status_code}: {res.text}")
                raise HTTPException(status_code=res.status_code, detail=f"Gateway error: {res.text}")
    except Exception as e:
        logger.error(f"Exception saat mendaftarkan webhook: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# -------------------------------------------------------------
# Auto-Payment: Parsing Sinyal AI & Integrasi TriPay QRIS
# -------------------------------------------------------------
import re as _re

def normalize_date_input(val: str) -> str:
    """
    Menormalkan berbagai format input tanggal menjadi format ISO YYYY-MM-DD.
    Mendukung format: YYYY-MM-DD, DD-MM-YYYY, DD/MM/YYYY, angka tanggal saja (bulan & tahun sekarang),
    'besok' (H+1), 'lusa' (H+3).
    """
    if not val:
        return ""
    val = val.strip()
    if _re.match(r'^\d{4}-\d{2}-\d{2}$', val):
        return val

    from zoneinfo import ZoneInfo
    try:
        tz = ZoneInfo(settings.HOTEL_TIMEZONE)
    except Exception:
        tz = ZoneInfo("Asia/Makassar")
    now = datetime.datetime.now(tz)

    low = val.lower()
    if 'besok' in low:
        return (now + datetime.timedelta(days=1)).strftime("%Y-%m-%d")
    if 'lusa' in low:
        return (now + datetime.timedelta(days=3)).strftime("%Y-%m-%d")
    if 'hari ini' in low:
        return now.strftime("%Y-%m-%d")

    match_dmy = _re.match(r'^(\d{1,2})[-/](\d{1,2})[-/](\d{4})$', val)
    if match_dmy:
        d, m, y = match_dmy.groups()
        return f"{int(y):04d}-{int(m):02d}-{int(d):02d}"

    if val.isdigit() and 1 <= int(val) <= 31:
        day_num = int(val)
        if day_num < now.day:
            month = now.month + 1 if now.month < 12 else 1
            year = now.year if now.month < 12 else now.year + 1
        else:
            month = now.month
            year = now.year
        return f"{year:04d}-{month:02d}-{day_num:02d}"

    bulan_map = {
        'januari': 1, 'februari': 2, 'maret': 3, 'april': 4, 'mei': 5, 'juni': 6,
        'juli': 7, 'agustus': 8, 'september': 9, 'oktober': 10, 'november': 11, 'desember': 12,
        'jan': 1, 'feb': 2, 'mar': 3, 'apr': 4, 'mei': 5, 'jun': 6,
        'jul': 7, 'agu': 8, 'sep': 9, 'okt': 10, 'nov': 11, 'des': 12
    }
    match_text = _re.search(r'(\d{1,2})\s+([a-zA-Z]+)(?:\s+(\d{4}))?', val)
    if match_text:
        d_str, m_str, y_str = match_text.groups()
        m_num = bulan_map.get(m_str.lower())
        if m_num:
            y_num = int(y_str) if y_str else now.year
            return f"{y_num:04d}-{m_num:02d}-{int(d_str):02d}"

    return val

def reconcile_booking_dates(checkin_str: str, checkout_str: str, nights: int = 1) -> tuple:
    """
    Memvalidasi dan merekonsiliasi tanggal check-in, check-out, dan jumlah malam (nights).
    Aturan Logika Ketat:
    1. Check-in dinormalkan ke YYYY-MM-DD. Jika kosong/tidak valid, default ke hari ini.
    2. Nights (jumlah malam) bernilai integer minimal 1.
    3. Check-out HARUS SELALU lebih besar dari check-in (c_out > c_in).
    4. Jika check-out <= check-in, kosong, atau tidak valid:
       Otomatis dihitung dengan rumus pasti: checkout = checkin + timedelta(days=nights).
    5. Jika check-out > check-in dan nights != (checkout - checkin).days:
       Sinkronkan nights = (checkout - checkin).days agar kalkulasi durasi menginap 100% konsisten.
    """
    from zoneinfo import ZoneInfo
    try:
        tz = ZoneInfo(settings.HOTEL_TIMEZONE)
    except Exception:
        tz = ZoneInfo("Asia/Makassar")
    today = datetime.datetime.now(tz).date()

    # 1. Parse check-in
    c_in = None
    if checkin_str:
        try:
            clean_in = normalize_date_input(checkin_str)
            c_in = datetime.datetime.strptime(clean_in, "%Y-%m-%d").date()
        except Exception:
            pass
    if not c_in:
        c_in = today

    # 2. Parse nights
    try:
        n = int(nights) if nights else 1
    except Exception:
        n = 1
    n = max(1, n)

    # 3. Parse check-out
    c_out = None
    if checkout_str:
        try:
            clean_out = normalize_date_input(checkout_str)
            c_out = datetime.datetime.strptime(clean_out, "%Y-%m-%d").date()
        except Exception:
            pass

    # 4. Rekonsiliasi: checkout TIDAK BOLEH <= checkin
    if not c_out or c_out <= c_in:
        # Checkout salah/sama/kurang dari checkin -> hitung pasti dari nights!
        c_out = c_in + datetime.timedelta(days=n)
    else:
        # Jika checkout valid > checkin, perbarui nights agar presisi
        n = (c_out - c_in).days

    return c_in.strftime("%Y-%m-%d"), c_out.strftime("%Y-%m-%d"), n

def parse_booking_signal(raw_reply: str) -> Optional[dict]:
    """
    Mengekstrak data pemesanan terstruktur dari sinyal <<BOOKING_CONFIRMED>> yang
    dihasilkan oleh Garda AI di dalam respons.
    Mengembalikan dict berisi NAMA, KODE_KAMAR, CHECKIN, CHECKOUT, MALAM, DEWASA, TOTAL, EMAIL
    atau None jika sinyal tidak ditemukan.
    """
    match = _re.search(r'<<BOOKING_CONFIRMED>>(.*?)<<END_BOOKING>>', raw_reply, _re.DOTALL)
    if not match:
        return None
    block = match.group(1).strip()
    data = {}
    for line in block.splitlines():
        if ':' in line:
            key, _, val = line.partition(':')
            data[key.strip()] = val.strip()
    required = ['NAMA', 'KODE_KAMAR', 'CHECKIN', 'TOTAL']
    if not all(k in data and data[k] for k in required):
        logger.warning(f"Sinyal BOOKING_CONFIRMED tidak lengkap: {data}")
        return None
    
    # Normalisasi dan rekonsiliasi otomatis tanggal check-in, check-out, dan jumlah malam
    nights = int(data.get('MALAM', 1) or 1)
    c_in = normalize_date_input(data.get('CHECKIN', ''))
    c_out = normalize_date_input(data.get('CHECKOUT', ''))
    c_in, c_out, nights = reconcile_booking_dates(c_in, c_out, nights)
    data['CHECKIN'] = c_in
    data['CHECKOUT'] = c_out
    data['MALAM'] = nights
    try:
        data['TOTAL'] = int(float(str(data.get('TOTAL', 0)).replace(',', '').replace('.', '') or 0))
    except Exception:
        pass
    return data


def generate_merchant_ref(phone: str) -> str:
    """
    Menghasilkan nomor referensi pemesanan unik untuk TriPay (maks 25 karakter).
    Format: AGH-{6_digit_tanggal}-{4_digit_phone}{4_digit_time} (total 19 karakter, unik per detik)
    """
    now = datetime.datetime.now()
    today = now.strftime("%d%m%y")
    time_suffix = now.strftime("%H%M%S")[-4:]
    phone_suffix = "".join(ch for ch in phone if ch.isdigit())[-4:]
    return f"AGH-{today}-{phone_suffix}{time_suffix}"


def extract_from_recap(s: str) -> Optional[dict]:
    """
    Mengekstrak data pemesanan dari teks REKAPITULASI DRAFT RESERVASI yang tersimpan di inquiry.
    Sebagai fallback jika LLM tidak menyertakan sinyal <<BOOKING_CONFIRMED>> saat tamu konfirmasi.
    Mendukung format tanggal Indonesia (contoh: 25 September 2026) dan inferensi kode kamar.
    """
    if not s:
        return None
    data = {}
    name_m = _re.search(r'Nama(?:\s*Pemesan)?\s*:\*?\s*([^\n\*•\(\)]+)', s, _re.IGNORECASE)
    if name_m:
        data['NAMA'] = name_m.group(1).strip()
    
    code_m = _re.search(r'\b(STD-FAN|DLX-TWN|SUP-DBL)\b', s, _re.IGNORECASE)
    if code_m:
        data['KODE_KAMAR'] = code_m.group(1).upper()
    elif _re.search(r'superior', s, _re.IGNORECASE):
        data['KODE_KAMAR'] = 'SUP-DBL'
    elif _re.search(r'deluxe', s, _re.IGNORECASE):
        data['KODE_KAMAR'] = 'DLX-TWN'
    elif _re.search(r'standard|kipas|fan', s, _re.IGNORECASE):
        data['KODE_KAMAR'] = 'STD-FAN'
    else:
        data['KODE_KAMAR'] = 'SUP-DBL'

    night_m = _re.search(r'\(?(\d+)\s*Malam\)?', s, _re.IGNORECASE)
    nights = int(night_m.group(1)) if night_m else 1
    data['MALAM'] = max(1, nights)

    months = {
        'januari': '01', 'februari': '02', 'maret': '03', 'april': '04',
        'mei': '05', 'juni': '06', 'juli': '07', 'agustus': '08',
        'september': '09', 'oktober': '10', 'november': '11', 'desember': '12'
    }

    from zoneinfo import ZoneInfo
    try:
        tz = ZoneInfo(settings.HOTEL_TIMEZONE)
    except Exception:
        tz = ZoneInfo("Asia/Makassar")
    cur_year = datetime.datetime.now(tz).year

    # 1. Cari tanggal dengan format nama bulan (misal: 25 September 2026)
    date_id_m = _re.findall(r'(\d{1,2})\s+(Januari|Februari|Maret|April|Mei|Juni|Juli|Agustus|September|Oktober|November|Desember)(?:\s+(\d{4}))?', s, _re.IGNORECASE)
    c_in_raw = None
    c_out_raw = None

    if len(date_id_m) >= 2:
        y0 = date_id_m[0][2] or str(cur_year)
        y1 = date_id_m[1][2] or date_id_m[0][2] or str(cur_year)
        c_in_raw = f"{y0}-{months[date_id_m[0][1].lower()]}-{int(date_id_m[0][0]):02d}"
        c_out_raw = f"{y1}-{months[date_id_m[1][1].lower()]}-{int(date_id_m[1][0]):02d}"
    elif len(date_id_m) == 1:
        y0 = date_id_m[0][2] or str(cur_year)
        c_in_raw = f"{y0}-{months[date_id_m[0][1].lower()]}-{int(date_id_m[0][0]):02d}"
    else:
        date_m = _re.findall(r'(\d{1,2}[-/]\d{1,2}[-/]\d{4}|\d{4}-\d{2}-\d{2})', s)
        if len(date_m) >= 2:
            c_in_raw = normalize_date_input(date_m[0])
            c_out_raw = normalize_date_input(date_m[1])
        elif len(date_m) == 1:
            c_in_raw = normalize_date_input(date_m[0])

    # 2. Rekonsiliasi tanggal pasti: jika c_out <= c_in atau c_out kosong, c_out otomatis dihitung dari nights!
    c_in, c_out, nights = reconcile_booking_dates(c_in_raw or "", c_out_raw or "", data['MALAM'])
    data['CHECKIN'] = c_in
    data['CHECKOUT'] = c_out
    data['MALAM'] = nights
        
    adult_m = _re.search(r'(\d+)\s*Dewasa', s, _re.IGNORECASE)
    data['DEWASA'] = int(adult_m.group(1)) if adult_m else 2
        
    total_m = _re.search(r'(?:Total|Biaya)\s*:\*?\s*(?:Rp\s*)?([0-9\.,]+)', s, _re.IGNORECASE)
    if total_m:
        data['TOTAL'] = int(_re.sub(r'[^0-9]', '', total_m.group(1)))
        
    email_m = _re.search(r'[\w\.-]+@[\w\.-]+\.\w+', s)
    data['EMAIL'] = email_m.group(0) if email_m else 'tamu@agniaguesthouse.com'

    required = ['KODE_KAMAR', 'CHECKIN', 'CHECKOUT', 'TOTAL']
    if all(k in data and data[k] for k in required):
        if not data.get('NAMA'):
            data['NAMA'] = 'Tamu'
        return data
    return None


def is_confirmation_intent(text: str) -> bool:
    """Mendeteksi apakah pesan tamu adalah persetujuan/konfirmasi dari draft rekapitulasi."""
    if not text:
        return False
    t = text.strip().lower()
    patterns = [
        r'^\s*(ya|iya|yep|yes|ok|oke|okay|deal|setuju|lanjut|konfirmasi|betul|benar|siap|cocok|pass|gas|yoi|acc|fix)\b',
        r'^\s*([ab]|opsi\s*[ab]|pilih\s*[ab]|crypto|usdt|bayar\s*crypto|bayar\s*usdt|qris)\b',
        r'^\s*[ab]\s*$',
        r'(sudah|udah)\s+(benar|sesuai|betul|oke|ok|pas)',
        r'siap\s+(lanjut|proses|konfirmasi)',
        r'bisa\s+di\s*proses',
        r'tolong\s+di\s*proses',
        r'proses\s+saja'
    ]
    return any(_re.search(p, t, _re.IGNORECASE) for p in patterns)


def is_resend_qr_intent(text: str) -> bool:
    """Mendeteksi apakah tamu meminta pengiriman ulang QR Code / QRIS atau menanyakan gambar/tautan QR."""
    if not text:
        return False
    t = text.strip().lower()

    # Kata kunci eksplisit QR/QRIS/Barcode
    has_qr = bool(_re.search(r'\b(qr|qris|barcode)\b', t))
    has_resend_verb = bool(_re.search(r'(kirim|minta|tampil|lihat|bagi|share|bantu|mana|belum|dapat|terima)', t))
    has_again_adverb = bool(_re.search(r'(ulang|lagi|kembali)', t))
    
    # Kombinasi 1: ada kata QR/QRIS + kata kerja kirim/minta/mana/belum ATAU kata ulang/lagi/kembali
    if has_qr and (has_resend_verb or has_again_adverb):
        return True

    # Kombinasi 2: frasa spesifik kirim ulang, tautan pembayaran, langkah bayar, dsb.
    specific_patterns = [
        r'(kirim|minta|tampilkan|bagi|share).*(ulang|lagi|kembali)',
        r'(mana|belum\s+ada).*(gambar|foto|kode|link|tautan|qr|qris)',
        r'(link|tautan).*(bayar|pembayaran|qris)',
        r'(cara|bagaimana|langkah).*(bayar|pembayaran)',
        r'scan.*(mana|di\s*mana|link|tautan)',
        r'gambar.*(mana|belum)',
        r'^(lalu|terus|lanjut|gimana|bagaimana)\s*(bagaimana|gimana|kelanjutannya|langkahnya|\?)?$',
        r'(bayar|qris|qr).*(mana|gimana|bagaimana)'
    ]
    return any(_re.search(p, t, _re.IGNORECASE) for p in specific_patterns)


def is_reset_intent(text: str) -> bool:
    """Mendeteksi apakah tamu meminta reset percakapan, mulai dari awal, atau membatalkan draft saat ini."""
    if not text:
        return False
    t = text.strip().lower()
    reset_patterns = [
        r'^(reset|clear|restart)$',
        r'^(mulai|ulang)\s*(dari\s*awal|lagi|baru)$',
        r'^(booking|reservasi|pesan)\s*baru$',
        r'^(batal|batalkan|batalin|cancel)\s*(yang\s*tadi|pemesanan|booking)?$',
        r'^(mau|tolong|bisa)?\s*(reset|ulang|ganti)\s*(percakapan|data|sesi|booking|tanggal|topik)?$',
        r'^(ganti|tanya)\s*(yang\s*lain|lain|topik)?$',
        r'^(hapus|bersihkan)\s*(data|chat|sesi)$'
    ]
    return any(_re.search(p, t, _re.IGNORECASE) for p in reset_patterns)


def parse_room_type_smart(msg: str) -> Optional[str]:
    """Mendeteksi pilihan tipe kamar dari teks pesan tamu secara akurat."""
    if not msg:
        return None
    m = msg.lower()
    # 1. Cek kode spesifik
    if "dlx-twn" in m or "dlx_twn" in m:
        return "DLX-TWN"
    if "sup-dbl" in m or "sup_dbl" in m:
        return "SUP-DBL"
    if "std-fan" in m or "std_fan" in m:
        return "STD-FAN"
    # 2. Cek nama tipe kamar utama
    if "deluxe" in m:
        return "DLX-TWN"
    if "superior" in m:
        return "SUP-DBL"
    if "standard" in m or "fan" in m or "kipas" in m:
        return "STD-FAN"
    # 3. Cek bed type kata kunci
    if "double" in m:
        return "SUP-DBL"
    if "twin" in m:
        return "DLX-TWN"
    if "single" in m:
        return "STD-FAN"
    if "dlx" in m:
        return "DLX-TWN"
    if "sup" in m:
        return "SUP-DBL"
    if "std" in m:
        return "STD-FAN"
    return None


async def resend_qr_payment(
    phone: str,
    db: Session,
    instance_id: Optional[str] = None
) -> bool:
    """
    Mengirimkan kembali rincian reservasi resmi dan gambar QRIS lokal ke WhatsApp tamu.
    Mendukung pemulihan otomatis dari PostgreSQL database jika container aplikasi baru saja restart.
    """
    clean_digits = "".join(ch for ch in phone if ch.isdigit())
    tx = db.query(PaymentTransaction).filter(
        (PaymentTransaction.customer_phone.contains(clean_digits[-8:])) |
        (PaymentTransaction.merchant_ref.contains(clean_digits[-4:]))
    ).order_by(PaymentTransaction.id.desc()).first()

    inquiry = db.query(ReservationInquiry).filter(
        ReservationInquiry.phone == phone
    ).order_by(ReservationInquiry.id.desc()).first()

    # 1. Cek PostgreSQL: Jika reservasi sudah ada dan sudah terkonfirmasi/lunas, beri tahu tamu
    if not tx:
        pg_rsv = HotelDatabaseService.get_latest_reservation_by_phone(phone)
        if pg_rsv:
            if pg_rsv.get("status") == "confirmed":
                conf_msg = (
                    f"Alhamdulillah, pembayaran untuk reservasi *{pg_rsv['reservation_no']}* "
                    f"atas nama *{pg_rsv['guest_name']}* sudah *LUNAS TERKONFIRMASI* di sistem kami! 🤝\n\n"
                    f"📋 *Rincian Reservasi:*\n"
                    f"• *Tipe Kamar:* {pg_rsv.get('room_type_name', '')} ({pg_rsv.get('room_type_code', '')})\n"
                    f"• *Periode Menginap:* {pg_rsv['check_in_date']} s/d {pg_rsv['check_out_date']} ({pg_rsv.get('total_nights', 1)} malam)\n\n"
                    f"Kami siap menyambut kedatangan Anda di *{settings.HOTEL_NAME}*! 😊"
                )
                await WhatsAppService.send_message(phone, conf_msg, instance_id=instance_id)
                return True

    if not tx and not inquiry:
        logger.warning(f"Tidak ditemukan transaksi maupun inquiry untuk nomor {phone}")
        return False

    # Jika belum ada transaksi TriPay tapi inquiry sudah ada draft recap, buat pembayaran baru
    if not tx and inquiry and (inquiry.status in ["CONFIRMED_BY_GUEST", "DRAFT_RECAP_SENT"] or inquiry.summary_text):
        booking_data = extract_from_recap(inquiry.summary_text or "")
        if booking_data:
            res = await process_tripay_payment(phone, booking_data, db, instance_id=instance_id)
            return bool(res.get("success"))

    if not tx:
        return False

    merchant_ref = tx.merchant_ref
    tripay_ref = tx.reference or merchant_ref
    total_amount = tx.total_amount or 0
    guest_name = tx.customer_name or (inquiry.guest_name if inquiry else None) or (inquiry.display_name if inquiry else None) or "Kakak"

    # Pastikan file gambar QR code lokal ada di static/qr/{merchant_ref}.png
    local_qr_path = os.path.join(STATIC_DIR, "qr", f"{merchant_ref}.png")
    b64_data = None
    if os.path.exists(local_qr_path):
        try:
            with open(local_qr_path, "rb") as f:
                b64_data = base64.b64encode(f.read()).decode("utf-8")
        except Exception:
            pass

    if not b64_data:
        qr_url = None
        qr_string = None
        checkout_url = tx.checkout_url
        if tx.raw_payload:
            try:
                payload = json.loads(tx.raw_payload)
                qr_url = payload.get("qr_url")
                qr_string = payload.get("qr_string")
                checkout_url = payload.get("checkout_url") or checkout_url
            except Exception:
                pass

        b64_data, png_bytes, _ = await QRService.resolve_qr_media(
            qr_url=qr_url,
            qr_string=qr_string,
            fallback_url=checkout_url
        )
        if png_bytes:
            QRService.save_qr_locally(f"{merchant_ref}.png", png_bytes)
            if tripay_ref:
                QRService.save_qr_locally(f"{tripay_ref}.png", png_bytes)

    qr_img_url = f"{settings.APP_URL}/static/qr/{merchant_ref}.png"
    checkout_url = tx.checkout_url or f"https://tripay.co.id/checkout/{tripay_ref}"

    room_desc = ""
    if inquiry and inquiry.room_type:
        room_name = next((r["name"] for r in ROOM_TYPES if isinstance(r, dict) and r.get("code") == inquiry.room_type), inquiry.room_type)
        room_desc = f"• *Tipe Kamar:* {room_name}\n"
        if inquiry.checkin_date and inquiry.checkout_date:
            room_desc += f"• *Periode Menginap:* {inquiry.checkin_date} s/d {inquiry.checkout_date} ({inquiry.nights or 1} malam)\n"

    is_sandbox = "sandbox" in settings.TRIPAY_BASE_URL.lower()
    sandbox_guide = ""
    if is_sandbox:
        simulate_url = f"{settings.APP_URL}/api/v1/payment/simulate-pay/{merchant_ref}"
        sandbox_guide = (
            f"🧪 *UJI COBA PELUNASAN (SANDBOX MODE):*\n"
            f"Karena sistem masih mode simulasi/testing, QRIS ini tidak dapat dibayar via m-banking asli.\n"
            f"Untuk simulasi pelunasan instan 1-klik, buka tautan berikut:\n"
            f"👉 {simulate_url}\n\n"
        )

    resend_msg = (
        f"Siap, Kak *{guest_name}*! 🤝✨\n"
        f"Berikut kami kirimkan kembali detail reservasi dan gambar QRIS resmi untuk pembayaran di *{settings.HOTEL_NAME}*:\n\n"
        f"📋 *Rincian Reservasi:*\n"
        f"• *Kode Booking:* `{merchant_ref}`\n"
        f"{room_desc}"
        f"• *Total Tagihan:* *Rp {int(total_amount):,}*\n"
        f"• *Metode Pembayaran:* QRIS (Scan & Pay)\n"
        f"• *Status:* 🟡 Menunggu Pembayaran\n\n"
        f"🖼️ *Link Gambar QRIS Resmi (Alternatif jika gambar tidak terbuka):*\n"
        f"{qr_img_url}\n\n"
        f"🔗 *Link Checkout / Simulator Pembayaran:*\n"
        f"{checkout_url}\n\n"
        f"{sandbox_guide}"
        f"💳 *Cara Pembayaran:*\n"
        f"1. Pindai / Scan langsung gambar QR Code di atas menggunakan m-Banking (BCA, Mandiri, BRI, BNI) atau E-Wallet (GoPay, OVO, Dana, ShopeePay).\n"
        f"2. Pastikan nominal pembayaran sesuai: *Rp {int(total_amount):,}*.\n"
        f"3. Setelah pembayaran berhasil, konfirmasi pelunasan otomatis akan langsung masuk ke WhatsApp ini.\n\n"
        f"Kamar Anda akan langsung kami amankan setelah transaksi terverifikasi. Terima kasih Kak! ❤️"
    )

    # Catat ke riwayat percakapan
    db.add(ChatHistory(phone=phone, role="assistant", message=resend_msg))
    db.commit()

    # Kirim satu pesan WhatsApp lengkap (Gambar QR Code JPEG langsung + caption)
    media_sent = False
    if b64_data:
        media_sent = await WhatsAppService.send_media(
            to_phone=phone,
            base64_data=b64_data,
            caption=resend_msg,
            filename="gambar.jpg",
            mimetype="image/jpeg",
            instance_id=instance_id
        )

    if not media_sent:
        await WhatsAppService.send_message(phone, resend_msg, instance_id=instance_id)

    logger.info(f"[Resend] Berhasil kirim ulang QRIS untuk {phone} (Booking: {merchant_ref}, media_sent={media_sent})")
    return True


async def process_tripay_payment(
    phone: str,
    booking_data: dict,
    db,
    instance_id: Optional[str] = None
):
    """
    Alur otomatis pasca konfirmasi tamu:
    1. Buat reservasi ke PMS database PostgreSQL
    2. Buat transaksi TriPay QRIS (Sandbox)
    3. Simpan PaymentTransaction di SQLite lokal
    4. Buat dan simpan file gambar QR Code secara fisik di server lokal (static/qr/{merchant_ref}.png)
    5. Kirim SATU CHAT LENGKAP ke WhatsApp tamu berisi ucapan terima kasih, detail booking, link gambar QRIS, dan panduan bayar.
    """
    guest_name = booking_data.get('NAMA', 'Tamu')
    room_type_code = booking_data.get('KODE_KAMAR', 'DLX-TWN')
    checkin_date = booking_data.get('CHECKIN', '')
    checkout_date = booking_data.get('CHECKOUT', '')
    nights = int(booking_data.get('MALAM', 1) or 1)

    # Validasi & Rekonsiliasi Tanggal Check-in, Check-out, dan Jumlah Malam
    checkin_date, checkout_date, nights = reconcile_booking_dates(checkin_date, checkout_date, nights)
    booking_data['CHECKIN'] = checkin_date
    booking_data['CHECKOUT'] = checkout_date
    booking_data['MALAM'] = nights
    adults = int(booking_data.get('DEWASA', 1) or 1)
    total_amount = int(float(str(booking_data.get('TOTAL', 0)).replace(',', '').replace('.', '') or 0))
    guest_email = booking_data.get('EMAIL', 'tamu@agniaguesthouse.com') or 'tamu@agniaguesthouse.com'

    merchant_ref = generate_merchant_ref(phone)
    logger.info(f"[Payment] Memproses reservasi {merchant_ref} untuk {guest_name} ({phone}), total: Rp {total_amount:,}")

    # 0. CEK KETERSEDIAAN KAMAR FISIK REAL-TIME SEBELUM BUAT TRANSAKSI (ANTI OVERBOOKING)
    free_room = HotelDatabaseService.get_available_physical_room(room_type_code, checkin_date, checkout_date)
    if not free_room:
        logger.warning(f"[Overbooking Blocked] Kamar {room_type_code} sudah penuh pada {checkin_date} s/d {checkout_date}")
        avail_list = HotelDatabaseService.get_all_rooms_availability_for_dates(checkin_date, checkout_date)
        alt_rooms = [f"• *{a['name']}* ({a['available_rooms']} unit tersedia - Rp {a['base_rate']:,}/malam)" for a in avail_list if a["is_available"]]
        alt_text = "\n".join(alt_rooms) if alt_rooms else "• Menggeser tanggal menginap ke sebelum atau sesudah tanggal tersebut."

        sold_out_msg = (
            f"Mohon maaf yang sebesar-besarnya, Kak *{guest_name}*. 🤝\n\n"
            f"Kamar tipe *{room_type_code}* untuk periode menginap *{checkin_date} s/d {checkout_date}* saat ini sudah terisi penuh oleh tamu lain (0 unit tersedia).\n\n"
            f"Agar Kakak tetap nyaman menginap di *{settings.HOTEL_NAME}*, kami sangat merekomendasikan opsi alternatif berikut:\n"
            f"{alt_text}\n"
            f"• Atau menggeser tanggal check-in/out saat kamar ini kembali kosong.\n\n"
            f"Apakah Kakak ingin kami bantu pilihkan opsi di atas? Kami siap membantu Kakak! 😊"
        )
        db.add(ChatHistory(phone=phone, role="assistant", message=sold_out_msg))
        db.commit()
        await WhatsAppService.send_message(phone, sold_out_msg, instance_id=instance_id)
        return

    # 1. Buat reservasi di PMS database PostgreSQL
    try:
        HotelDatabaseService.create_reservation(
            guest_name=guest_name,
            guest_phone=phone,
            room_type_code=room_type_code,
            checkin_date=checkin_date,
            checkout_date=checkout_date,
            adults=adults,
            children=0,
            special_requests=None,
            estimated_total=float(total_amount),
            deposit_amount=float(total_amount),
            status="reserved",
            booking_source="Reservasi Online / WA",
            merchant_ref=merchant_ref
        )
        logger.info(f"[Payment] Reservasi {merchant_ref} berhasil dibuat di PMS dengan alokasi Kamar {free_room['room_number']}.")
    except Exception as e:
        logger.error(f"[Payment] Gagal membuat reservasi di PMS: {e}")
        err_msg = (
            f"Mohon maaf Kak *{guest_name}*, terjadi kendala saat mengamankan alokasi kamar. "
            f"Silakan konfirmasi kembali tanggal menginap Anda ya, Kak. 🤝"
        )
        await WhatsAppService.send_message(phone, err_msg, instance_id=instance_id)
        return

    # 2. Buat transaksi TriPay QRIS Sandbox
    # Pastikan amount minimal Rp 10.000 (minimum TriPay sandbox)
    if total_amount < 10000:
        total_amount = 160000  # Default Deluxe Twin 1 malam jika kalkulasi gagal

    order_items = [
        {
            "name": f"Reservasi Kamar {room_type_code} - {nights} Malam",
            "price": total_amount,
            "quantity": 1
        }
    ]

    # Expired 24 jam dari sekarang
    expired_time = int((datetime.datetime.now() + datetime.timedelta(hours=24)).timestamp())

    tripay_res = await TriPayService.create_closed_transaction(
        method="QRIS2",
        merchant_ref=merchant_ref,
        amount=total_amount,
        customer_name=guest_name,
        customer_email=guest_email,
        customer_phone=phone.replace('@lid', '').replace('62', '0', 1) if phone.startswith('62') else phone,
        order_items=order_items,
        expired_time=expired_time
    )

    logger.info(f"[Payment] TriPay response: {tripay_res.get('message', 'no message')} | success={tripay_res.get('success')}")

    # 3. Simpan PaymentTransaction di SQLite lokal
    if tripay_res.get("success") and tripay_res.get("data"):
        d = tripay_res["data"]
        tx = PaymentTransaction(
            reference=d.get("reference"),
            merchant_ref=merchant_ref,
            payment_method="QRIS2",
            payment_name="QRIS (Scan & Pay)",
            customer_name=guest_name,
            customer_phone=phone,
            customer_email=guest_email,
            total_amount=total_amount,
            fee=d.get("total_fee", 0),
            amount_received=d.get("amount_received", total_amount),
            pay_code=d.get("pay_code"),
            checkout_url=d.get("checkout_url"),
            status=d.get("status", "UNPAID"),
            raw_payload=json.dumps(d)
        )
        db.add(tx)
        db.commit()

        try:
            ActivityLogger.log_tripay_create(
                merchant_ref=merchant_ref,
                tripay_ref=d.get("reference", merchant_ref),
                customer_name=guest_name,
                customer_phone=phone,
                total_amount=total_amount,
                payment_method="QRIS2"
            )
        except Exception:
            pass

        # 4. Ambil data QR dan simpan file gambar QR Code secara fisik di server lokal
        qr_url = d.get("qr_url") or d.get("checkout_url", "")
        qr_string = d.get("qr_string", "")
        tripay_ref = d.get("reference", merchant_ref)
        checkout_url = d.get("checkout_url", "")
        expired_dt = datetime.datetime.fromtimestamp(d.get("expired_time", expired_time)).strftime("%d %b %Y %H:%M WITA") if d.get("expired_time") else "24 jam dari sekarang"

        b64_data, png_bytes, mime = await QRService.resolve_qr_media(
            qr_url=qr_url,
            qr_string=qr_string,
            fallback_url=checkout_url
        )
        if png_bytes:
            QRService.save_qr_locally(f"{merchant_ref}.png", png_bytes)
            if tripay_ref:
                QRService.save_qr_locally(f"{tripay_ref}.png", png_bytes)
            logger.info(f"[Payment] QR Code gambar tersimpan di static/qr/{merchant_ref}.png")

        local_qr_img_url = f"{settings.APP_URL}/static/qr/{merchant_ref}.png"
        room_name = next((r["name"] for r in ROOM_TYPES if isinstance(r, dict) and r.get("code") == room_type_code), f"Kamar {room_type_code}")

        is_sandbox = "sandbox" in settings.TRIPAY_BASE_URL.lower()
        sandbox_guide = ""
        if is_sandbox:
            simulate_url = f"{settings.APP_URL}/api/v1/payment/simulate-pay/{merchant_ref}"
            sandbox_guide = (
                f"🧪 *UJI COBA PELUNASAN (SANDBOX MODE):*\n"
                f"Karena sistem masih mode simulasi/testing, QRIS ini tidak dapat dibayar via m-banking asli.\n"
                f"Untuk simulasi pelunasan instan 1-klik, buka tautan berikut:\n"
                f"👉 {simulate_url}\n\n"
            )

        # 5. Susun SATU CHAT LENGKAP: Terima Kasih + Detail Reservasi + Link Gambar QRIS + Link Simulator TriPay + Panduan Bayar
        full_caption = (
            f"🎉 *RESERVASI RESMI BERHASIL DIKONFIRMASI!*\n\n"
            f"Alhamdulillah, terima kasih banyak Kak *{guest_name}*! 🤝✨\n"
            f"Reservasi Anda di *{settings.HOTEL_NAME}* telah berhasil dikonfirmasi dan terdaftar di sistem hotel kami.\n\n"
            f"📋 *Rincian Reservasi:*\n"
            f"• *Kode Booking:* `{merchant_ref}`\n"
            f"• *Tipe Kamar:* {room_name} ({room_type_code})\n"
            f"• *Periode Menginap:* {checkin_date} s/d {checkout_date} ({nights} malam)\n"
            f"• *Jumlah Tamu:* {adults} Dewasa\n"
            f"• *Total Tagihan:* *Rp {total_amount:,}*\n\n"
            f"🖼️ *Link Gambar QRIS Resmi (Klik untuk Buka/Simpan):*\n"
            f"{local_qr_img_url}\n\n"
            f"🔗 *Link Checkout / Simulator Pembayaran:*\n"
            f"{checkout_url}\n\n"
            f"{sandbox_guide}"
            f"💳 *Instruksi Pembayaran QRIS:*\n"
            f"1. Pindai / Scan langsung gambar QR Code di atas menggunakan m-Banking (BCA, Mandiri, BRI, BNI) atau E-Wallet (GoPay, OVO, Dana, ShopeePay).\n"
            f"2. Pastikan nominal pembayaran sesuai: *Rp {total_amount:,}*.\n"
            f"3. Setelah pembayaran berhasil, konfirmasi pelunasan otomatis akan langsung masuk ke WhatsApp ini.\n\n"
            f"⏰ *Batas Waktu Bayar:* {expired_dt}\n\n"
            f"Terima kasih telah memilih *{settings.HOTEL_NAME}*. Kami tunggu kedatangan Kak {guest_name} di Balikpapan! Sampai jumpa! ❤️"
        )

        # Catat ke ChatHistory
        db.add(ChatHistory(phone=phone, role="assistant", message=full_caption))
        db.commit()

        # Kirim SATU pesan ke WhatsApp tamu (Gambar QR Code JPEG langsung + caption)
        media_sent = False
        if b64_data:
            media_sent = await WhatsAppService.send_media(
                to_phone=phone,
                base64_data=b64_data,
                caption=full_caption,
                filename="gambar.jpg",
                mimetype="image/jpeg",
                instance_id=instance_id
            )

        if not media_sent:
            await WhatsAppService.send_message(
                to_phone=phone,
                message=full_caption,
                instance_id=instance_id
            )

        logger.info(f"[Payment] Pesan tunggal QRIS berhasil dikirim ke {phone} untuk booking {merchant_ref} (media_sent={media_sent})")

        return {
            "success": True,
            "merchant_ref": merchant_ref,
            "tripay_ref": tripay_ref,
            "qr_url": qr_url,
            "local_qr_img_url": local_qr_img_url,
            "checkout_url": checkout_url,
            "amount": total_amount,
            "expired_dt": expired_dt
        }

    else:
        # Fallback jika TriPay gagal: tetap konfirmasi reservasi & minta transfer manual
        err_msg = tripay_res.get('message', 'Tidak diketahui')
        logger.error(f"[Payment] TriPay gagal untuk {merchant_ref}: {err_msg}")
        fallback_msg = (
            f"✅ *RESERVASI RESMI DICATAT!*\n\n"
            f"Alhamdulillah, terima kasih banyak Kak *{guest_name}*! 🤝✨\n"
            f"Reservasi Anda dengan kode booking *{merchant_ref}* sudah kami terima di *{settings.HOTEL_NAME}*.\n\n"
            f"💸 *Total Pembayaran: Rp {total_amount:,}*\n\n"
            f"Mohon maaf, sistem QRIS otomatis sedang dalam pemeliharaan sejenak.\n"
            f"Silakan lakukan transfer ke:\n"
            f"• *BCA:* 1234567890 (a.n. Agnia Guesthouse)\n"
            f"• *Mandiri:* 0987654321 (a.n. Agnia Guesthouse)\n"
            f"Berita transfer: *{merchant_ref}*\n\n"
            f"Kami tunggu kedatangan Kak {guest_name}! Konfirmasi transfer dapat dikirimkan langsung ke chat ini. Terima kasih! 🤝"
        )
        db.add(ChatHistory(phone=phone, role="assistant", message=fallback_msg))
        db.commit()
        await WhatsAppService.send_message(phone, fallback_msg, instance_id=instance_id)
        return {
            "success": False,
            "merchant_ref": merchant_ref,
            "error": err_msg
        }


async def process_crypto_escrow_payment(
    phone: str,
    booking_data: dict,
    db,
    instance_id: Optional[str] = None
):
    """
    Alur otomatis pembayaran Crypto Escrow pasca konfirmasi tamu:
    1. Cek ketersediaan kamar fisik real-time (anti-overbooking)
    2. Buat reservasi ke PMS database PostgreSQL
    3. Buat kontrak escrow di Smart Contract BSC (HotelEscrow.sol)
    4. Simpan CryptoEscrow & PaymentTransaction di SQLite lokal
    5. Kirim chat WhatsApp lengkap berisi rincian USDT, alamat kontrak escrow, timer 30 menit, dan bonus loyalitas ANV.
    """
    guest_name = booking_data.get('NAMA', 'Tamu')
    room_type_code = booking_data.get('KODE_KAMAR', 'DLX-TWN')
    checkin_date = booking_data.get('CHECKIN', '')
    checkout_date = booking_data.get('CHECKOUT', '')
    nights = int(booking_data.get('MALAM', 1) or 1)

    checkin_date, checkout_date, nights = reconcile_booking_dates(checkin_date, checkout_date, nights)
    booking_data['CHECKIN'] = checkin_date
    booking_data['CHECKOUT'] = checkout_date
    booking_data['MALAM'] = nights
    adults = int(booking_data.get('DEWASA', 1) or 1)
    total_amount = int(float(str(booking_data.get('TOTAL', 0)).replace(',', '').replace('.', '') or 0))

    merchant_ref = generate_merchant_ref(phone)
    logger.info(f"[Crypto Payment] Memproses reservasi escrow {merchant_ref} untuk {guest_name} ({phone}), total IDR: Rp {total_amount:,}")

    # 1. Cek kamar fisik kosong
    free_room = HotelDatabaseService.get_available_physical_room(room_type_code, checkin_date, checkout_date)
    if not free_room:
        sold_out_msg = (
            f"Mohon maaf yang sebesar-besarnya, Kak *{guest_name}*. 🤝\n\n"
            f"Kamar tipe *{room_type_code}* untuk periode menginap *{checkin_date} s/d {checkout_date}* saat ini sudah terisi penuh oleh tamu lain.\n"
            f"Silakan pilih tanggal lain atau kamar tipe lainnya."
        )
        db.add(ChatHistory(phone=phone, role="assistant", message=sold_out_msg))
        db.commit()
        await WhatsAppService.send_message(phone, sold_out_msg, instance_id=instance_id)
        return {
            "success": False,
            "merchant_ref": merchant_ref,
            "error": "Room sold out"
        }

    # 2. Buat reservasi di PostgreSQL
    try:
        HotelDatabaseService.create_reservation(
            guest_name=guest_name,
            guest_phone=phone,
            room_type_code=room_type_code,
            checkin_date=checkin_date,
            checkout_date=checkout_date,
            adults=adults,
            children=0,
            special_requests="Pembayaran via Crypto USDT Escrow (BNB Smart Chain)",
            estimated_total=float(total_amount),
            deposit_amount=0.0,
            status="reserved",
            booking_source="WhatsApp Crypto Escrow",
            merchant_ref=merchant_ref
        )
    except Exception as e:
        logger.error(f"[PMS Error] Gagal buat reservasi PostgreSQL untuk crypto: {e}")

    # 3. Buat sesi Escrow di SQLite & Web3
    escrow_res = CryptoSecurePayService.create_escrow(
        db=db,
        booking_ref=merchant_ref,
        guest_phone=phone,
        guest_wallet=None,
        amount_idr=total_amount,
        checkin_date=checkin_date
    )

    # Catat ke PaymentTransaction
    tx = PaymentTransaction(
        reference=f"ESCROW-{merchant_ref}",
        merchant_ref=merchant_ref,
        payment_method="CRYPTO_USDT",
        payment_name="USDT Escrow (BSC)",
        customer_name=guest_name,
        customer_phone=phone,
        total_amount=total_amount,
        fee=0,
        amount_received=0,
        pay_code=escrow_res['contract_address'],
        checkout_url=f"https://testnet.bscscan.com/address/{escrow_res['contract_address']}",
        status="UNPAID",
        note=f"USDT Amount: {escrow_res['amount_usdt']} USDT. Escrow ID: {escrow_res['escrow_id']}"
    )
    db.add(tx)
    db.commit()

    room_name = next((r["name"] for r in ROOM_TYPES if isinstance(r, dict) and r.get("code") == room_type_code), f"Kamar {room_type_code}")

    # 4. Kirim rincian ke WhatsApp Tamu
    wa_msg = (
        f"🤝 Alhamdulillah, terima kasih banyak Kak *{guest_name}*! ✨\n\n"
        f"Reservasi kamar *{room_name}* Anda berhasil kami siapkan dengan jaminan *Crypto Escrow Web3*.\n\n"
        f"🪙 *TAGIHAN PEMBAYARAN CRYPTO ESCROW*\n"
        f"─────────────────────────────\n"
        f"• *Kode Booking:* `{merchant_ref}`\n"
        f"• *Tipe Kamar:* {room_name} ({room_type_code})\n"
        f"• *Periode Menginap:* {checkin_date} s/d {checkout_date} ({nights} malam)\n"
        f"• *Total Tagihan:* Rp {total_amount:,} (*{escrow_res['amount_usdt']} USDT*)\n"
        f"• *Jaringan (Network):* {escrow_res['network']}\n"
        f"• *Token Stablecoin:* {escrow_res['token']}\n"
        f"• *Alamat Escrow Smart Contract:*\n`{escrow_res['contract_address']}`\n\n"
        f"• *Dompet Penerima Hotel:*\n`{escrow_res['hotel_wallet']}`\n"
        f"• *Batas Waktu Transfer:* 30 Menit (⏰)\n"
        f"─────────────────────────────\n"
        f"🔒 *Jaminan Keamanan Web3:*\n"
        f"Dana Anda aman di-hold oleh smart contract dan *hanya dicairkan ke hotel saat Anda check-in fisik di hotel*. "
        f"Jika Anda membatalkan minimal 24 jam sebelum check-in, dana 100% otomatis kembali ke dompet Anda!\n\n"
        f"🎁 *Reward Loyalitas:* Setelah check-in, Anda akan mendapatkan bonus poin token BEP-20 ANV (setara 5% nilai booking)!\n\n"
        f"_Silakan transfer tepat *{escrow_res['amount_usdt']} USDT* ke alamat smart contract di atas melalui dompet kripto Anda (MetaMask/Binance/TrustWallet)._"
    )
    db.add(ChatHistory(phone=phone, role="assistant", message=wa_msg))
    db.commit()
    await WhatsAppService.send_message(phone, wa_msg, instance_id=instance_id)

    return {
        "success": True,
        "merchant_ref": merchant_ref,
        "amount_usdt": escrow_res['amount_usdt'],
        "contract_address": escrow_res['contract_address'],
        "status": "CREATED"
    }


@app.post("/api/v1/payment/test-qris")
async def test_create_qris(
    guest_name: str = "Budi Santoso",
    amount: int = 160000,
    phone: str = "081234567890",
    db: Session = Depends(get_db)
):
    """
    [DEV/TESTING] Membuat transaksi QRIS TriPay sandbox untuk pengetesan cepat.
    """
    import time
    merchant_ref = f"AGH-TEST-{int(time.time())}"
    order_items = [{
        "sku": "DLX-TWN",
        "name": "Deluxe Twin Room (AC) - Testing",
        "price": amount,
        "quantity": 1
    }]
    res = await TriPayService.create_closed_transaction(
        method="QRIS2",
        merchant_ref=merchant_ref,
        amount=amount,
        customer_name=guest_name,
        customer_email="budi@example.com",
        customer_phone=phone,
        order_items=order_items
    )
    return res


@app.post("/api/v1/payment/simulate-confirm")
async def simulate_confirm_booking(
    phone: str = "628123456789",
    guest_name: str = "Budi Santoso",
    room_type_code: str = "DLX-TWN",
    checkin: str = "2026-09-24",
    checkout: str = "2026-09-25",
    total: int = 160000,
    db: Session = Depends(get_db)
):
    """
    [DEV/TESTING] Mensimulasikan kondisi ketika tamu WA menyetujui rekap (konfirmasi booking),
    langsung membuat reservasi di PMS & membuat invoice QRIS sandbox + kirim ke WhatsApp tamu.
    """
    booking_data = {
        "NAMA": guest_name,
        "KODE_KAMAR": room_type_code,
        "CHECKIN": checkin,
        "CHECKOUT": checkout,
        "MALAM": 1,
        "DEWASA": 2,
        "TOTAL": total,
        "SPECIAL_REQUESTS": "Simulasi konfirmasi test"
    }
    result = await process_tripay_payment(phone=phone, booking_data=booking_data, db=db)
    return {
        "status": "success",
        "message": f"Simulasi konfirmasi booking untuk {guest_name} ({phone}) berhasil diproses",
        "result": result
    }



# -------------------------------------------------------------
# Alur Percakapan & Webhook WhatsApp
# -------------------------------------------------------------
async def process_and_reply_wa(phone: str, display_name: str, message_body: str, log_id: Optional[int] = None, instance_id: Optional[str] = None):
    """Fungsi latar belakang untuk memproses pesan dengan Garda dan mengirim balasan WA."""
    db = SessionLocal()
    try:
        # 1. Catat pesan tamu ke riwayat percakapan
        db.add(ChatHistory(phone=phone, role="user", message=message_body))
        db.commit()

        # 2a. INTERSEP INTENT: TAMU MINTA RESET ATAU MULAI DARI AWAL
        if is_reset_intent(message_body):
            logger.info(f"Deteksi permintaan reset percakapan dari {phone}: '{message_body}'")
            reset_garda_session(phone, db, reason="guest_requested_reset")
            db.query(ReservationInquiry).filter(
                ReservationInquiry.phone == phone,
                ReservationInquiry.status.notin_(["PAID", "CANCELLED"])
            ).update({"status": "CANCELLED"}, synchronize_session=False)
            db.commit()

        # 2b. Ambil atau inisialisasi inquiry aktif di database (bukan yang sudah PAID / CANCELLED)
        inquiry = db.query(ReservationInquiry).filter(
            ReservationInquiry.phone == phone,
            ReservationInquiry.status.notin_(["PAID", "COMPLETED", "CANCELLED"])
        ).order_by(ReservationInquiry.id.desc()).first()

        if not inquiry:
            inquiry = ReservationInquiry(
                phone=phone,
                display_name=display_name,
                status="COLLECTING_DATA"
            )
            db.add(inquiry)
            db.commit()
            db.refresh(inquiry)
        else:
            if display_name and display_name != "Tamu":
                inquiry.display_name = display_name

        # 2c. INTERSEP INTENT: TAMU MINTA KIRIM ULANG QR / QRIS
        if is_resend_qr_intent(message_body):
            logger.info(f"Deteksi permintaan kirim ulang QR dari {phone}: '{message_body}'")
            resent = await resend_qr_payment(phone=phone, db=db, instance_id=instance_id)
            if resent:
                if log_id:
                    w_log = db.query(WebhookEventLog).filter(WebhookEventLog.id == log_id).first()
                    if w_log:
                        w_log.status = "replied"
                        w_log.bot_reply = "QR Code berhasil dikirim ulang"
                        db.commit()
                return

        # 3. Deteksi tanggal menginap dari pesan atau gunakan tanggal yang tersimpan di inquiry
        p_in, p_out = parse_dates_smart(message_body)
        if p_in and p_out:
            inquiry.checkin_date = p_in
            inquiry.checkout_date = p_out
            db.commit()
        elif is_general_room_inquiry(message_body):
            # Jika tamu bertanya secara umum tentang kamar kosong, bersihkan tanggal/tipe lama agar informasi akurat
            inquiry.checkin_date = None
            inquiry.checkout_date = None
            inquiry.room_type = None
            inquiry.summary_text = None
            db.commit()

        # Deteksi tipe kamar dari pesan tamu jika ada (misal: "Deluxe Twin Room")
        p_room = parse_room_type_smart(message_body)
        if p_room:
            inquiry.room_type = p_room
            if inquiry.summary_text and p_room not in inquiry.summary_text:
                inquiry.summary_text = None
                inquiry.status = "COLLECTING_DATA"
            db.commit()

        def extract_clean_name(text: str) -> Optional[str]:
            if not text:
                return None
            m = _re.search(r'\b(?:nama\s*(?:saya)?\s*[:=]?|a/?n\.?)\s*([A-Za-z\s]{3,35})', text, _re.IGNORECASE)
            if m:
                raw_name = m.group(1).split(':')[0].strip()
                if raw_name.lower() not in ["superior", "deluxe", "standard", "hotel", "guesthouse"]:
                    return raw_name.title()
            return None

        # Deteksi nama pemesan dari pesan saat ini jika ada
        if not inquiry.guest_name:
            c_name = extract_clean_name(message_body)
            if c_name:
                inquiry.guest_name = c_name
                db.commit()

        # Jika inquiry belum memiliki tanggal atau nama tamu, pulihkan dari riwayat chat (hanya jika bukan inquiry umum)
        if not is_general_room_inquiry(message_body) and (not inquiry.checkin_date or not inquiry.checkout_date or not inquiry.guest_name):
            past_msgs = db.query(ChatHistory).filter(
                ChatHistory.phone == phone,
                ChatHistory.role == "user"
            ).order_by(ChatHistory.id.desc()).limit(10).all()
            for pm in past_msgs:
                if not inquiry.checkin_date or not inquiry.checkout_date:
                    cin, cout = parse_dates_smart(pm.message)
                    if cin and cout:
                        inquiry.checkin_date = cin
                        inquiry.checkout_date = cout
                if not inquiry.guest_name:
                    c_name = extract_clean_name(pm.message)
                    if c_name:
                        inquiry.guest_name = c_name
            db.commit()

        if inquiry.checkin_date and inquiry.checkout_date:
            try:
                d_in = datetime.datetime.strptime(inquiry.checkin_date, "%Y-%m-%d").date()
                d_out = datetime.datetime.strptime(inquiry.checkout_date, "%Y-%m-%d").date()
                diff_n = (d_out - d_in).days
                if diff_n > 0:
                    inquiry.nights = diff_n
                    db.commit()
            except Exception:
                pass

        effective_guest_name = inquiry.guest_name or (display_name if display_name and display_name != "Tamu" else None)

        # 🆕 Fast-Path: Cek Poin Loyalitas ANV via WhatsApp
        low_msg = message_body.strip().lower()
        if any(pt in low_msg for pt in ["cek poin", "saldo poin", "poin saya", "poin loyalitas", "poin anv", "saldo anv"]):
            loyalty_info = CryptoSecurePayService.get_loyalty_balance(db, phone)
            if loyalty_info.get("registered"):
                loyalty_reply = (
                    f"💎 *INFORMASI LOYALITAS ANVIEO POINTS (ANV)* 💎\n"
                    f"─────────────────────────────\n"
                    f"• *Nomor Akun:* `{phone}`\n"
                    f"• *Total Saldo:* *{loyalty_info['balance']} ANV*\n"
                    f"• *Tier Member:* 🏆 *{loyalty_info['tier']}*\n"
                    f"• *Frekuensi Menginap:* {loyalty_info['booking_count']}x booking\n"
                    f"• *Keuntungan Anda:* {loyalty_info['perks']}\n"
                    f"─────────────────────────────\n"
                    f"_Poin ANV Anda dapat ditukarkan untuk potongan harga reservasi berikutnya!_"
                )
            else:
                loyalty_reply = (
                    f"👋 Halo! Nomor WhatsApp Anda `{phone}` belum memiliki saldo poin loyalitas ANV.\n\n"
                    f"🎁 Setiap kali Anda menyelesaikan masa inap di *{settings.HOTEL_NAME}*, "
                    f"Anda otomatis mendapatkan reward poin setara *5% nilai reservasi*! "
                    f"Poin ini bisa digunakan untuk potongan harga pemesanan berikutnya."
                )
            db.add(ChatHistory(phone=phone, role="assistant", message=loyalty_reply))
            if log_id:
                w_log = db.query(WebhookEventLog).filter(WebhookEventLog.id == log_id).first()
                if w_log:
                    w_log.status = "replied"
                    w_log.bot_reply = loyalty_reply
            db.commit()
            await WhatsAppService.send_message(phone, loyalty_reply, instance_id=instance_id)
            return

        # Ambil session_id versi terbaru dan kirim ke Garda LLM API dengan konteks lengkap
        session_id = get_or_create_garda_session_id(phone, db)
        garda_reply = await GardaService.chat(
            phone=phone,
            user_message=message_body,
            session_id=session_id,
            checkin_date=inquiry.checkin_date if inquiry else None,
            checkout_date=inquiry.checkout_date if inquiry else None,
            guest_name=effective_guest_name,
            room_type=inquiry.room_type if inquiry else None,
            phone_number=phone
        )

        # 4. Catat balasan Garda ke riwayat
        db.add(ChatHistory(phone=phone, role="assistant", message=garda_reply))
        
        # 5. Cek apakah Garda sudah menghasilkan REKAPITULASI DRAFT
        if "REKAPITULASI DRAFT RESERVASI" in garda_reply.upper() or "REKAPITULASI" in garda_reply.upper():
            inquiry.status = "DRAFT_RECAP_SENT"
            inquiry.summary_text = garda_reply
            logger.info(f"Draft reservasi berhasil direkap untuk tamu {phone}")
        
        # 6. Cek apakah Garda menghasilkan sinyal <<BOOKING_CONFIRMED>> (tamu konfirmasi reservasi)
        booking_data = parse_booking_signal(garda_reply)

        # Fallback Cerdas: Jika LLM tidak memunculkan <<BOOKING_CONFIRMED>>, tapi status sebelumnya DRAFT_RECAP_SENT
        # dan tamu mengirim kata-kata konfirmasi ("ya", "oke", "setuju", dll)
        if not booking_data and inquiry.status == "DRAFT_RECAP_SENT" and is_confirmation_intent(message_body):
            logger.info(f"Deteksi konfirmasi dari pesan tamu '{message_body}', mengekstrak data dari draft recap...")
            booking_data = extract_from_recap(inquiry.summary_text or "")
            if booking_data:
                logger.info(f"Berhasil ekstrak booking data dari recap: {booking_data}")

        if booking_data:
            inquiry.status = "CONFIRMED_BY_GUEST"
            inquiry.guest_name = booking_data.get('NAMA', inquiry.display_name)
            inquiry.room_type = booking_data.get('KODE_KAMAR', '')
            inquiry.checkin_date = booking_data.get('CHECKIN', '')
            inquiry.checkout_date = booking_data.get('CHECKOUT', '')
            inquiry.nights = int(booking_data.get('MALAM', 1) or 1)
            inquiry.adults = int(booking_data.get('DEWASA', 1) or 1)
            inquiry.estimated_total = float(str(booking_data.get('TOTAL', 0)).replace(',', '').replace('.', '') or 0)
            logger.info(f"Konfirmasi booking terverifikasi untuk tamu {phone}, mengirim QRIS 1 chat terpadu...")

        if log_id:
            w_log = db.query(WebhookEventLog).filter(WebhookEventLog.id == log_id).first()
            if w_log:
                w_log.status = "replied"
                w_log.bot_reply = garda_reply

        db.commit()

        # 7. Pengiriman Pesan ke WhatsApp Tamu:
        if booking_data:
            metode = str(booking_data.get('METODE', '')).upper()
            is_crypto = (
                "CRYPTO" in metode or 
                "USDT" in metode or 
                message_body.strip().upper() == "B" or 
                "CRYPTO" in message_body.upper() or 
                "USDT" in message_body.upper()
            )
            if is_crypto:
                logger.info(f"Tamu {phone} memilih pembayaran CRYPTO ESCROW, memproses escrow USDT...")
                await process_crypto_escrow_payment(phone, booking_data, db, instance_id=instance_id)
            else:
                logger.info(f"Tamu {phone} memilih pembayaran QRIS/FIAT, memproses TriPay QRIS...")
                await process_tripay_payment(phone, booking_data, db, instance_id=instance_id)
        else:
            # Cek apakah Garda LLM menjawab dengan menjanjikan link/tautan QRIS tetapi belum ada URL-nya (Safety net anti-halusinasi)
            # PENTING: Jangan picu safety net jika ini adalah REKAPITULASI DRAFT yang masih menunggu jawaban "YA" dari tamu!
            low_reply = garda_reply.lower()
            qr_promise_triggers = [
                "link pembayaran qris", "scan link pembayaran", "qris di bawah ini",
                "tautan pembayaran", "tautan qris", "scan tautan pembayaran",
                "tautan pembayaran qris", "link pembayaran", "link qris",
                "scan tautan", "scan link", "melakukan scan", "melakukan *scan*"
            ]
            if (
                "REKAPITULASI" not in garda_reply.upper() and
                any(trig in low_reply for trig in qr_promise_triggers) and 
                ("http://" not in garda_reply and "https://" not in garda_reply)
            ):
                logger.info("Garda LLM menjanjikan link QRIS tanpa URL, menyematkan detail transaksi & QR link lokal...")
                clean_digits = "".join(ch for ch in phone if ch.isdigit())
                tx = db.query(PaymentTransaction).filter(
                    (PaymentTransaction.customer_phone.contains(clean_digits[-8:])) |
                    (PaymentTransaction.merchant_ref.contains(clean_digits[-4:]))
                ).order_by(PaymentTransaction.id.desc()).first()

                # 1. Jika sudah ada transaksi TriPay aktif dan belum lunas, kirimkan kembali QR Code-nya
                if tx and tx.status != "PAID":
                    logger.info(f"Safety net menemukan tx {tx.merchant_ref}, mengirimkan gambar QRIS via resend_qr_payment...")
                    await resend_qr_payment(phone, db, instance_id=instance_id)
                    return

            # Untuk percakapan biasa dan penyajian draft recap, kirim balasan teks Garda
            await WhatsAppService.send_message(phone, garda_reply, instance_id=instance_id)

    except Exception as e:
        logger.error(f"Error pada process_and_reply_wa: {e}")
        if log_id:
            try:
                w_log = db.query(WebhookEventLog).filter(WebhookEventLog.id == log_id).first()
                if w_log:
                    w_log.status = "failed"
                    w_log.bot_reply = f"Error: {e}"
                    db.commit()
            except Exception:
                pass
    finally:
        db.close()

@app.get("/webhook/whatsapp")
def get_whatsapp_webhook_status():
    """
    Endpoint pengecekan status (health check) untuk webhook callback WhatsApp.
    Memudahkan pengujian langsung via browser atau pemantauan uptime.
    """
    return {
        "status": "online",
        "service": "hotel-api-crypto",
        "endpoint": "/webhook/whatsapp",
        "method": "POST",
        "webhook_url": settings.public_webhook_url,
        "instance_id": settings.WA_INSTANCE_ID,
        "gateway_url": settings.WA_GATEWAY_URL,
        "supported_events": ["message.received", "message.ack"],
        "message": "WhatsApp webhook callback endpoint is active and listening for incoming messages."
    }

@app.post("/webhook/whatsapp")
async def whatsapp_webhook(request: Request, background_tasks: BackgroundTasks, db: Session = Depends(get_db)):
    """
    Endpoint penerima webhook dari WhatsApp Gateway (Wuller/wa).
    Menerima event 'message.received'.
    """
    try:
        payload = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON body")

    event = payload.get("event")
    data = payload.get("data", {})
    instance_id = str(data.get("instanceId") or settings.WA_INSTANCE_ID).strip()

    logger.info(f"Menerima webhook event: {event} dari instance {instance_id}")

    if event != "message.received":
        return {"status": "ignored", "reason": f"Event '{event}' not handled"}

    # 1. HANYA PROSES PESAN DARI INSTANCE RESMI BOT HOTEL (settings.WA_INSTANCE_ID)
    # Ini krusial agar instance tamu/admin yang terhubung ke gateway yang sama tidak saling membalas (infinite ping-pong loop)
    official_instance = str(settings.WA_INSTANCE_ID).strip()
    if instance_id != official_instance:
        logger.info(f"Mengabaikan event dari instance non-hotel ({instance_id}). Bot resmi: {official_instance}")
        return {"status": "ignored", "reason": f"Instance {instance_id} is not the official hotel bot"}

    msg = data.get("msg", {})
    contact = data.get("contact", {})

    # 2. FILTER PESAN OUTGOING (fromMe atau ID diawali true_)
    msg_id = str(msg.get("id", ""))
    if msg.get("fromMe", False) or msg_id.startswith("true_"):
        logger.info(f"Mengabaikan pesan outgoing (dari diri sendiri): {msg_id}")
        return {"status": "ignored", "reason": "Outgoing message (fromMe)"}

    # 2b. DEDUPLIKASI WEBHOOK: CEGAH PEMROSESAN GANDA DARI RETRY GATEWAY
    if msg_id:
        existing_log = db.query(WebhookEventLog).filter(
            WebhookEventLog.raw_payload.contains(msg_id)
        ).first()
        if existing_log:
            logger.info(f"Mengabaikan duplicate webhook msg_id: {msg_id} (sudah tercatat di log #{existing_log.id})")
            return {"status": "ignored", "reason": f"Duplicate msg_id ({msg_id})"}

    # 3. FILTER PESAN GROUP
    if contact.get("isGroup", False):
        return {"status": "ignored", "reason": "Group messages are ignored"}

    # 4. CEGAH BOT MEMPROSES PESAN DARI NOMOR SENDIRI
    contact_id = str(contact.get("id", ""))
    contact_phone = str(contact.get("phone", ""))
    bot_numbers = [official_instance, "76249309392990"] # Nomor bot & LID bot
    if any(b in contact_id or b in contact_phone for b in bot_numbers):
        logger.info(f"Mengabaikan pesan dari bot sendiri: id={contact_id}, phone={contact_phone}")
        return {"status": "ignored", "reason": "Sender is bot itself"}

    message_body = msg.get("body", "").strip()

    # 5. CEGAH LOOP BALASAN OTOMATIS / SYSTEM TEXT ECHO
    if any(sig in message_body for sig in ["[FO Staff]:", "Saya Garda", "📋 *REKAPITULASI DRAFT RESERVASI*"]):
        logger.info("Mengabaikan pesan balasan internal bot untuk mencegah looping.")
        return {"status": "ignored", "reason": "System message signature detected"}

    # Ekstraksi Target WhatsApp Pengirim:
    # Mengambil ID kontak atau nomor pengirim asli dari payload event message.received.
    # Jangan pernah me-redirect / me-reroute pesan tamu ke nomor admin!
    raw_id = str(contact.get("id") or msg.get("from") or msg.get("key", {}).get("remoteJid") or "").strip()
    raw_phone = str(contact.get("phone") or "").strip()
    display_name = contact.get("displayName") or contact.get("name") or "Tamu"

    clean_phone_digits = "".join(ch for ch in raw_phone if ch.isdigit())
    if clean_phone_digits.startswith("08"):
        clean_phone_digits = "62" + clean_phone_digits[1:]

    # Jika pengirim memiliki nomor telepon HP valid (panjang 10-14 digit diawali 628):
    if clean_phone_digits.startswith("628") and 10 <= len(clean_phone_digits) <= 14:
        phone = clean_phone_digits
    elif "@lid" in raw_id:
        # Format WhatsApp LID (misal: 170020676092120@lid atau 7511964934235@lid)
        # Gunakan format LID asli agar balasan terkirim langsung ke thread chat pengirim
        phone = raw_id
    elif "@s.whatsapp.net" in raw_id:
        # Format standard WhatsApp JID (misal: 628123456789@s.whatsapp.net)
        base_num = raw_id.split("@")[0].split(":")[0]
        clean_num = "".join(ch for ch in base_num if ch.isdigit())
        if clean_num.startswith("08"):
            clean_num = "62" + clean_num[1:]
        phone = clean_num or raw_id
    else:
        # Fallback raw_id atau raw_phone yang ada
        clean_any = "".join(ch for ch in (raw_phone or raw_id) if ch.isdigit())
        if clean_any.startswith("08"):
            clean_any = "62" + clean_any[1:]
        elif clean_any.startswith("8") and 9 <= len(clean_any) <= 13:
            clean_any = "62" + clean_any
        
        if len(clean_any) >= 14 and not clean_any.startswith(("08", "628")):
            phone = f"{clean_any}@lid"
        else:
            phone = clean_any or raw_id or raw_phone
    # Cek jika ada media
    media_info = msg.get("media")
    if media_info:
        logger.info(f"Pesan dari {phone} memiliki lampiran media: {media_info.get('mimetype')}")
        if not message_body:
            message_body = f"[Tamu mengirimkan lampiran berkas/foto: {media_info.get('originalName', 'file')}]"

    if not phone or not message_body:
        return {"status": "ignored", "reason": "Missing phone or empty message"}

    # Catat Webhook Event Log realtime
    w_log = WebhookEventLog(
        event_type=event,
        sender_phone=phone,
        sender_name=display_name,
        message_content=message_body,
        status="processing",
        raw_payload=json.dumps(payload)
    )
    db.add(w_log)
    db.commit()
    db.refresh(w_log)

    try:
        ActivityLogger.log_wa_inbound(
            phone=phone,
            sender_name=display_name,
            message=message_body,
            status="DITERIMA"
        )
    except Exception:
        pass

    # Proses asinkron di latar belakang
    background_tasks.add_task(process_and_reply_wa, phone, display_name, message_body, w_log.id, instance_id)

    return {"status": "queued", "phone": phone, "log_id": w_log.id}

# -------------------------------------------------------------
# Endpoint Pengujian Langsung (Simulator Web / Swagger)
# -------------------------------------------------------------
class TestChatRequest(BaseModel):
    phone: str = "628123456789"
    message: str = "Halo, apakah ada kamar kosong untuk besok malam?"
    send_to_wa: bool = False

@app.post("/api/v1/test-chat")
async def test_chat(req: TestChatRequest, db: Session = Depends(get_db)):
    """Simulasi obrolan tamu dengan Garda AI langsung dari Web UI / Swagger."""
    db.add(ChatHistory(phone=req.phone, role="user", message=req.message))
    db.commit()

    inquiry = db.query(ReservationInquiry).filter(
        ReservationInquiry.phone == req.phone,
        ReservationInquiry.status.notin_(["PAID", "COMPLETED", "CANCELLED"])
    ).order_by(ReservationInquiry.id.desc()).first()
    if not inquiry:
        inquiry = ReservationInquiry(
            phone=req.phone,
            display_name="Tamu Test",
            status="COLLECTING_DATA"
        )
        db.add(inquiry)
        db.commit()
        db.refresh(inquiry)

    p_in, p_out = parse_dates_smart(req.message)
    if p_in and p_out:
        inquiry.checkin_date = p_in
        inquiry.checkout_date = p_out
        db.commit()
    elif is_general_room_inquiry(req.message):
        inquiry.checkin_date = None
        inquiry.checkout_date = None
        inquiry.room_type = None
        inquiry.summary_text = None
        db.commit()

    p_room = parse_room_type_smart(req.message)
    if p_room:
        inquiry.room_type = p_room
        db.commit()

    # Deteksi nama pemesan dari pesan jika ada
    if not inquiry.guest_name:
        m_name = _re.search(r'(?:nama\s*(?:saya)?|an\.?|a/n)\s*([A-Za-z\s]{3,35})', req.message, _re.IGNORECASE)
        if m_name:
            inquiry.guest_name = m_name.group(1).strip()
            db.commit()

    session_id = get_or_create_garda_session_id(req.phone, db)
    garda_reply = await GardaService.chat(
        phone=req.phone,
        user_message=req.message,
        session_id=session_id,
        checkin_date=inquiry.checkin_date if inquiry else None,
        checkout_date=inquiry.checkout_date if inquiry else None,
        guest_name=inquiry.guest_name,
        room_type=inquiry.room_type,
        phone_number=req.phone
    )

    db.add(ChatHistory(phone=req.phone, role="assistant", message=garda_reply))
    if "REKAPITULASI" in garda_reply.upper():
        inquiry.status = "DRAFT_RECAP_SENT"
        inquiry.summary_text = garda_reply
    
    # Catat ke WebhookEventLog untuk monitoring simulator
    w_log = WebhookEventLog(
        event_type="simulator.chat",
        sender_phone=req.phone,
        sender_name="Simulator Tamu",
        message_content=req.message,
        status="replied",
        bot_reply=garda_reply,
        raw_payload=json.dumps({"phone": req.phone, "message": req.message})
    )
    db.add(w_log)
    db.commit()

    # Jika opsi kirim ke WhatsApp aktif, kirim balasan ke nomor WA
    if req.send_to_wa:
        await WhatsAppService.send_message(req.phone, garda_reply)

    return {
        "phone": req.phone,
        "session_id": session_id,
        "user_message": req.message,
        "garda_reply": garda_reply,
        "inquiry_status": inquiry.status,
        "sent_to_wa": req.send_to_wa
    }

class ResetSessionRequest(BaseModel):
    phone: str = "170020676092120@lid"
    reason: Optional[str] = "manual_admin_reset"

@app.post("/api/v1/chat/reset-session")
def reset_session_endpoint(req: ResetSessionRequest, db: Session = Depends(get_db)):
    """Mereset sesi percakapan Garda LLM untuk nomor tertentu secara manual."""
    new_sess = reset_garda_session(req.phone, db, reason=req.reason or "manual_admin_reset")
    db.query(ReservationInquiry).filter(
        ReservationInquiry.phone == req.phone,
        ReservationInquiry.status.notin_(["PAID", "CANCELLED"])
    ).update({"status": "CANCELLED"}, synchronize_session=False)
    db.commit()
    return {
        "status": "success",
        "phone": req.phone,
        "new_session_id": new_sess,
        "message": f"Sesi percakapan untuk {req.phone} berhasil di-reset. Obrolan berikutnya akan memulai sesi baru."
    }


# -------------------------------------------------------------
# Endpoint Front Office & Live Log Monitoring
# -------------------------------------------------------------
@app.get("/api/v1/inquiries")
def list_inquiries(status: Optional[str] = None, db: Session = Depends(get_db)):
    """Melihat daftar seluruh draft reservasi yang dikumpulkan oleh Garda."""
    query = db.query(ReservationInquiry)
    if status:
        query = query.filter(ReservationInquiry.status == status)
    return query.order_by(ReservationInquiry.updated_at.desc()).all()

@app.get("/api/v1/inquiries/{phone}")
def get_inquiry_detail(phone: str, db: Session = Depends(get_db)):
    """Melihat detail rekapitulasi dan riwayat obrolan tamu tertentu."""
    inquiry = db.query(ReservationInquiry).filter(ReservationInquiry.phone == phone).order_by(ReservationInquiry.id.desc()).first()
    if not inquiry:
        raise HTTPException(status_code=404, detail="Inquiry tidak ditemukan")
    
    chats = db.query(ChatHistory).filter(ChatHistory.phone == phone).order_by(ChatHistory.id.asc()).all()
    return {
        "inquiry": inquiry,
        "chat_history": chats
    }

@app.get("/api/v1/live-logs")
def get_live_logs(limit: int = 50, db: Session = Depends(get_db)):
    """Mengambil riwayat webhook dan percakapan realtime untuk tab monitoring log."""
    logs = db.query(WebhookEventLog).order_by(WebhookEventLog.id.desc()).limit(limit).all()
    inquiries = db.query(ReservationInquiry).order_by(ReservationInquiry.updated_at.desc()).limit(30).all()
    total_chats = db.query(ChatHistory).count()
    total_webhooks = db.query(WebhookEventLog).count()
    
    return {
        "stats": {
            "total_webhooks": total_webhooks,
            "total_inquiries": len(inquiries),
            "total_chat_messages": total_chats
        },
        "logs": [
            {
                "id": l.id,
                "event_type": l.event_type,
                "sender_phone": l.sender_phone,
                "sender_name": l.sender_name or "Tamu",
                "message_content": l.message_content,
                "status": l.status,
                "bot_reply": l.bot_reply,
                "raw_payload": l.raw_payload,
                "created_at": l.created_at.strftime("%Y-%m-%d %H:%M:%S") if l.created_at else ""
            }
            for l in logs
        ],
        "inquiries": [
            {
                "id": inq.id,
                "phone": inq.phone,
                "display_name": inq.display_name or inq.guest_name or "Tamu",
                "status": inq.status,
                "summary": inq.summary_text,
                "updated_at": inq.updated_at.strftime("%Y-%m-%d %H:%M:%S") if inq.updated_at else ""
            }
            for inq in inquiries
        ]
    }

@app.get("/api/v1/logs/activity")
def get_activity_logs_endpoint(
    limit: int = 100,
    filter_type: str = "ALL",
    search: str = "",
    db: Session = Depends(get_db)
):
    """
    Mengambil data aktivitas transaksi WhatsApp Gateway dan TriPay terpadu
    beserta statistik untuk monitoring di backend dashboard.
    """
    return ActivityLogger.get_unified_activity_feed(
        db=db,
        limit=limit,
        filter_type=filter_type,
        search=search
    )

@app.get("/api/v1/logs/raw-txt")
def get_raw_txt_logs_endpoint(lines: int = 1000, db: Session = Depends(get_db)):
    """
    Melihat isi file log activity_logger.txt dalam format plain text langsung di browser.
    """
    content = ActivityLogger.get_raw_txt(max_lines=lines, db=db)
    return Response(content=content, media_type="text/plain; charset=utf-8")

@app.get("/api/v1/logs/download-txt")
def download_txt_logs_endpoint(db: Session = Depends(get_db)):
    """
    Mengunduh berkas log activity_logger.txt sebagai audit trail transaksi hotel.
    """
    ActivityLogger.sync_to_file(db)
    today_str = datetime.datetime.now().strftime("%Y%m%d_%H%M")
    filename = f"agnia_hotel_logs_{today_str}.txt"
    return FileResponse(
        path=ACTIVITY_LOG_FILE,
        filename=filename,
        media_type="text/plain; charset=utf-8"
    )

@app.get("/api/v1/live-chat/{phone}")
def get_live_chat_by_phone(phone: str, db: Session = Depends(get_db)):
    """Mengambil detail percakapan realtime untuk tamu tertentu."""
    inquiry = db.query(ReservationInquiry).filter(ReservationInquiry.phone == phone).order_by(ReservationInquiry.id.desc()).first()
    chats = db.query(ChatHistory).filter(ChatHistory.phone == phone).order_by(ChatHistory.id.asc()).all()
    return {
        "phone": phone,
        "guest_name": (inquiry.display_name if inquiry else None) or "Tamu",
        "status": inquiry.status if inquiry else "ACTIVE",
        "summary": inquiry.summary_text if inquiry else None,
        "chats": [
            {
                "id": c.id,
                "role": c.role,
                "message": c.message,
                "created_at": c.created_at.strftime("%H:%M:%S") if c.created_at else ""
            }
            for c in chats
        ]
    }

class ManualSendRequest(BaseModel):
    phone: str
    message: str

@app.post("/api/v1/live-chat/send")
async def send_manual_chat_reply(req: ManualSendRequest, db: Session = Depends(get_db)):
    """Mengirim balasan manual dari Front Office langsung ke WhatsApp tamu & mencatat riwayat."""
    chat = ChatHistory(
        phone=req.phone,
        role="assistant",
        message=f"[FO Staff]: {req.message}"
    )
    db.add(chat)
    
    event_log = WebhookEventLog(
        event_type="manual_fo_reply",
        sender_phone=req.phone,
        sender_name="Front Office Staff",
        message_content=req.message,
        status="sent_by_fo",
        bot_reply=req.message,
        raw_payload=json.dumps({"type": "manual_fo_reply", "message": req.message})
    )
    db.add(event_log)
    db.commit()
    
    sent = await WhatsAppService.send_message(req.phone, req.message)
    return {"status": "success" if sent else "warning", "message_sent_to_wa": sent}


# ==============================================================================
# REST API V2: CRYPTO SECUREPAY, ON-CHAIN AUDIT & LOYALTY ENGINE
# ==============================================================================

class CreateEscrowRequest(BaseModel):
    booking_ref: str
    guest_phone: str
    guest_wallet: Optional[str] = None
    amount_idr: int
    checkin_date: Optional[str] = None
    guest_name: Optional[str] = None

@app.post("/api/v2/crypto/create-escrow")
def api_create_escrow(req: CreateEscrowRequest, db: Session = Depends(get_db)):
    """Membuat sesi escrow baru di smart contract BSC untuk pembayaran via USDT."""
    checkin = req.checkin_date or (datetime.date.today() + datetime.timedelta(days=1)).strftime("%Y-%m-%d")
    return CryptoSecurePayService.create_escrow(
        db=db,
        booking_ref=req.booking_ref,
        guest_phone=req.guest_phone,
        guest_wallet=req.guest_wallet,
        amount_idr=req.amount_idr,
        checkin_date=checkin
    )

@app.get("/api/v2/crypto/escrow/{booking_ref}")
def api_get_escrow(booking_ref: str, db: Session = Depends(get_db)):
    """Melihat status terkini dari kontrak escrow pemesanan."""
    escrow = db.query(CryptoEscrow).filter(CryptoEscrow.booking_ref == booking_ref).first()
    if not escrow:
        raise HTTPException(status_code=404, detail="Escrow booking ref tidak ditemukan")
    return escrow

@app.post("/api/v2/crypto/escrow/{booking_ref}/confirm-checkin")
def api_confirm_escrow_checkin(booking_ref: str, db: Session = Depends(get_db)):
    """
    Staf Front Office mengonfirmasi check-in tamu fisik.
    Memicu pencairan dana escrow ke hotel wallet dan pencetakan token loyalitas ANV.
    """
    res = CryptoSecurePayService.confirm_escrow_checkin(db, booking_ref)
    if not res.get("success"):
        status_code = res.get("code", 400)
        raise HTTPException(status_code=status_code, detail=res.get("message"))
    return res

@app.post("/api/v2/crypto/escrow/{booking_ref}/cancel")
def api_cancel_escrow(booking_ref: str, db: Session = Depends(get_db)):
    """Pembatalan reservasi escrow oleh tamu minimal 24 jam sebelum check-in."""
    res = CryptoSecurePayService.cancel_escrow(db, booking_ref)
    if not res.get("success"):
        raise HTTPException(status_code=400, detail=res.get("message"))
    return res

@app.post("/api/v2/crypto/escrow/{booking_ref}/dispute")
def api_dispute_escrow(booking_ref: str, reason: str = "Tamu dispute", db: Session = Depends(get_db)):
    """Membekukan dana di escrow jika terjadi sengketa antara tamu dan hotel."""
    escrow = db.query(CryptoEscrow).filter(CryptoEscrow.booking_ref == booking_ref).first()
    if not escrow:
        raise HTTPException(status_code=404, detail="Escrow tidak ditemukan")
    escrow.status = "DISPUTED"
    db.commit()
    return {"success": True, "booking_ref": booking_ref, "status": "DISPUTED", "reason": reason}

class RecordTransactionRequest(BaseModel):
    reference: str
    booking_ref: str
    payment_method: str
    amount: float
    currency: str = "IDR"

@app.post("/api/v2/security/record-transaction")
async def api_record_transaction(req: RecordTransactionRequest, db: Session = Depends(get_db)):
    """Mencatat hash transaksi pembayaran ke smart contract SecurePayRegistry.sol."""
    return await CryptoSecurePayService.record_onchain_transaction(
        db=db,
        reference=req.reference,
        booking_ref=req.booking_ref,
        payment_method=req.payment_method,
        amount=req.amount,
        currency=req.currency
    )

@app.get("/api/v2/security/verify/{reference}")
def api_verify_transaction(reference: str, db: Session = Depends(get_db)):
    """Memverifikasi keabsahan transaksi on-chain berdasarkan kode referensi."""
    res = CryptoSecurePayService.verify_onchain_transaction(db, reference)
    if not res.get("verified"):
        raise HTTPException(status_code=404, detail=res)
    return res

@app.get("/api/v2/security/audit-trail/{booking_ref}")
def api_get_audit_trail(booking_ref: str, db: Session = Depends(get_db)):
    """Mengambil linimasa lengkap seluruh peristiwa transaksi on-chain untuk satu reservasi."""
    return CryptoSecurePayService.get_audit_trail(db, booking_ref)

@app.get("/api/v2/loyalty/balance/{identifier}")
def api_get_loyalty_balance(identifier: str, db: Session = Depends(get_db)):
    """Melihat saldo poin loyalitas ANV dan peringkat tier berdasarkan HP atau wallet address."""
    return CryptoSecurePayService.get_loyalty_balance(db, identifier)

class AwardLoyaltyRequest(BaseModel):
    phone: str
    booking_ref: str
    amount_idr: int
    wallet_address: Optional[str] = None

@app.post("/api/v2/loyalty/award")
def api_award_loyalty(req: AwardLoyaltyRequest, db: Session = Depends(get_db)):
    """Pencetakan poin loyalitas token BEP-20 (5% nilai reservasi)."""
    return CryptoSecurePayService.award_loyalty_points(
        db=db,
        phone=req.phone,
        booking_ref=req.booking_ref,
        amount_idr=req.amount_idr,
        wallet_address=req.wallet_address
    )

@app.get("/api/v2/dashboard/crypto-stats")
def api_get_crypto_stats(db: Session = Depends(get_db)):
    """Mengambil ringkasan statistik on-chain realtime untuk dashboard FO."""
    return CryptoSecurePayService.get_dashboard_crypto_stats(db)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host=settings.HOST, port=settings.PORT, reload=True)

