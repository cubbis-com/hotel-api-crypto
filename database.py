import datetime
from sqlalchemy import create_engine, Column, Integer, String, Text, DateTime, Float, Boolean
from sqlalchemy.orm import declarative_base, sessionmaker, Session

from config import settings

db_url = settings.INQUIRIES_DATABASE_URL
connect_args = {"check_same_thread": False} if db_url.startswith("sqlite") else {}

engine = create_engine(db_url, connect_args=connect_args)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

class ReservationInquiry(Base):
    __tablename__ = "reservation_inquiries"

    id = Column(Integer, primary_key=True, index=True)
    phone = Column(String(50), index=True)
    display_name = Column(String(100), nullable=True)
    guest_name = Column(String(100), nullable=True)
    room_type = Column(String(50), nullable=True)       # e.g. KNGN, SDBN, SJSN
    checkin_date = Column(String(50), nullable=True)
    checkout_date = Column(String(50), nullable=True)
    nights = Column(Integer, default=1)
    adults = Column(Integer, default=1)
    children = Column(Integer, default=0)
    special_requests = Column(String(255), nullable=True)
    estimated_total = Column(Float, default=0.0)
    
    # Status alur: COLLECTING_DATA, DRAFT_RECAP_SENT, CONFIRMED_BY_GUEST, ESCALATED_TO_FO
    status = Column(String(50), default="COLLECTING_DATA")
    summary_text = Column(Text, nullable=True)
    
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.datetime.utcnow, onupdate=datetime.datetime.utcnow)

class ChatHistory(Base):
    __tablename__ = "chat_history"

    id = Column(Integer, primary_key=True, index=True)
    phone = Column(String(50), index=True)
    role = Column(String(20)) # "user" atau "assistant"
    message = Column(Text)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)

class WebhookEventLog(Base):
    __tablename__ = "webhook_event_logs"

    id = Column(Integer, primary_key=True, index=True)
    event_type = Column(String(50), default="message.received")
    sender_phone = Column(String(50), index=True)
    sender_name = Column(String(100), nullable=True)
    message_content = Column(Text, nullable=True)
    status = Column(String(50), default="received")  # received, processed, replied, failed
    bot_reply = Column(Text, nullable=True)
    raw_payload = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)

class PaymentTransaction(Base):
    __tablename__ = "payment_transactions"

    id = Column(Integer, primary_key=True, index=True)
    reference = Column(String(100), unique=True, index=True)      # TriPay reference (e.g. DEV-T52086...)
    merchant_ref = Column(String(100), index=True)                 # Booking / invoice ID
    payment_method = Column(String(50), nullable=True)             # e.g. BRIVA, QRIS, BCAVA, CRYPTO_USDT
    payment_name = Column(String(100), nullable=True)               # e.g. BRI Virtual Account
    customer_name = Column(String(100), nullable=True)
    customer_phone = Column(String(50), nullable=True, index=True)
    customer_email = Column(String(100), nullable=True)
    total_amount = Column(Integer, default=0)
    fee = Column(Integer, default=0)
    amount_received = Column(Integer, default=0)
    pay_code = Column(String(100), nullable=True)                  # No VA / kode bayar
    checkout_url = Column(Text, nullable=True)
    status = Column(String(50), default="UNPAID")                  # UNPAID, PAID, FAILED, EXPIRED, REFUND
    note = Column(Text, nullable=True)
    raw_payload = Column(Text, nullable=True)
    paid_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.datetime.utcnow, onupdate=datetime.datetime.utcnow)

class GardaSessionState(Base):
    __tablename__ = "garda_session_states"

    id = Column(Integer, primary_key=True, index=True)
    phone = Column(String(50), unique=True, index=True)
    session_version = Column(Integer, default=1)
    status = Column(String(50), default="active")                  # active, completed, reset
    last_reset_reason = Column(String(100), nullable=True)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.datetime.utcnow, onupdate=datetime.datetime.utcnow)

# ==============================================================================
# WEB3 & CRYPTO SECUREPAY MODELS
# ==============================================================================

class CryptoEscrow(Base):
    """
    Menyimpan data escrow pembayaran hotel berbasis smart contract BNB Smart Chain.
    """
    __tablename__ = "crypto_escrows"

    id = Column(Integer, primary_key=True, index=True)
    booking_ref = Column(String(100), unique=True, index=True)
    guest_phone = Column(String(50), index=True)
    guest_wallet = Column(String(100), nullable=True)
    hotel_wallet = Column(String(100), nullable=False)
    amount_usdt = Column(Float, nullable=False)
    amount_idr = Column(Integer, nullable=False)
    checkin_timestamp = Column(Integer, nullable=False)
    status = Column(String(50), default="CREATED")                 # CREATED, FUNDED, CONFIRMED, REFUNDED, DISPUTED, EXPIRED
    tx_hash_create = Column(String(100), nullable=True)
    tx_hash_fund = Column(String(100), nullable=True)
    tx_hash_release = Column(String(100), nullable=True)
    tx_hash_refund = Column(String(100), nullable=True)
    contract_address = Column(String(100), nullable=False)
    expires_at = Column(DateTime, nullable=False)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.datetime.utcnow, onupdate=datetime.datetime.utcnow)

class OnChainAuditRecord(Base):
    """
    Menyimpan hash transaksi yang dijangkarkan ke smart contract SecurePayRegistry.
    Memberikan audit trail immutable tanpa mengekspos PII tamu.
    """
    __tablename__ = "onchain_audit_records"

    id = Column(Integer, primary_key=True, index=True)
    reference = Column(String(100), unique=True, index=True)
    booking_ref = Column(String(100), index=True)
    payment_method = Column(String(50), nullable=False)
    amount = Column(Float, nullable=False)
    currency = Column(String(20), default="IDR")
    tx_hash = Column(String(100), unique=True, index=True)
    block_number = Column(Integer, nullable=True)
    network = Column(String(50), default="BSC Testnet")
    verified = Column(Boolean, default=True)
    payload_hash = Column(String(100), nullable=False)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)

class LoyaltyAccount(Base):
    """
    Akun loyalitas tamu untuk token BEP-20 (ANV).
    """
    __tablename__ = "loyalty_accounts"

    id = Column(Integer, primary_key=True, index=True)
    phone = Column(String(50), unique=True, index=True)
    wallet_address = Column(String(100), unique=True, nullable=True)
    total_earned = Column(Integer, default=0)
    total_redeemed = Column(Integer, default=0)
    balance = Column(Integer, default=0)
    tier = Column(String(30), default="None")                     # None, Silver, Gold, Platinum
    booking_count = Column(Integer, default=0)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.datetime.utcnow, onupdate=datetime.datetime.utcnow)

class LoyaltyTransactionRecord(Base):
    """
    Riwayat penambahan dan penukaran poin loyalitas ANV.
    """
    __tablename__ = "loyalty_transaction_records"

    id = Column(Integer, primary_key=True, index=True)
    phone = Column(String(50), index=True)
    wallet_address = Column(String(100), nullable=True)
    booking_ref = Column(String(100), index=True, nullable=True)
    action_type = Column(String(50))                              # MINT_CHECKIN, REDEEM_CASHBACK, ACTION_BONUS
    points = Column(Integer, nullable=False)
    tx_hash = Column(String(100), nullable=True)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)

# ==============================================================================
# HELPER FUNCTIONS
# ==============================================================================

def clean_session_phone(phone: str) -> str:
    return str(phone).replace("@", "_").replace(".", "_").replace("+", "").strip()

def get_or_create_garda_session_id(phone: str, db: Session) -> str:
    if not phone:
        return "agnia_guesthouse_guest_v1"
    
    clean_p = clean_session_phone(phone)
    state = db.query(GardaSessionState).filter(GardaSessionState.phone == phone).first()
    if not state:
        state = GardaSessionState(phone=phone, session_version=1, status="active")
        db.add(state)
        try:
            db.commit()
            db.refresh(state)
        except Exception:
            db.rollback()
            state = db.query(GardaSessionState).filter(GardaSessionState.phone == phone).first()

    version = state.session_version if state else 1
    return f"agnia_guesthouse_{clean_p}_v{version}"

def reset_garda_session(phone: str, db: Session, reason: str = "payment_paid") -> str:
    if not phone:
        return "agnia_guesthouse_guest_v1"
    
    clean_p = clean_session_phone(phone)
    state = db.query(GardaSessionState).filter(GardaSessionState.phone == phone).first()
    if not state:
        state = GardaSessionState(
            phone=phone,
            session_version=2,
            status="completed",
            last_reset_reason=reason
        )
        db.add(state)
    else:
        state.session_version += 1
        state.status = "completed"
        state.last_reset_reason = reason
        state.updated_at = datetime.datetime.utcnow()

    try:
        db.commit()
        db.refresh(state)
    except Exception:
        db.rollback()
        return f"agnia_guesthouse_{clean_p}_v2"

    new_session_id = f"agnia_guesthouse_{clean_p}_v{state.session_version}"
    return new_session_id

def seed_initial_crypto_data():
    """
    Memastikan data escrow crypto, notarisasi on-chain, dan akun loyalitas
    tersedia secara default pada instance database baru / restart di Railway.
    """
    db = SessionLocal()
    try:
        if db.query(CryptoEscrow).count() == 0:
            now = datetime.datetime.utcnow()
            sample_escrows = [
                CryptoEscrow(
                    booking_ref="BOOK-CRYPTO-TEST-001",
                    guest_phone="6281299998888",
                    guest_wallet="0x71C...345",
                    hotel_wallet=settings.HOTEL_WALLET_ADDRESS,
                    amount_usdt=40.62,
                    amount_idr=650000,
                    checkin_timestamp=int(now.timestamp()) + 86400,
                    status="CONFIRMED",
                    tx_hash_create="0xc7278f5128e87884ee6f57f73229d93c12d24c3e59347a2e7a56661703071929",
                    tx_hash_release="0x0e09dc36ed8ace3eec6dcb95d03b3de1be82e49fef014f85fb16857b11b8f214",
                    contract_address=settings.HOTEL_ESCROW_ADDRESS,
                    expires_at=now + datetime.timedelta(minutes=30),
                    created_at=now - datetime.timedelta(hours=2)
                ),
                CryptoEscrow(
                    booking_ref="BOOK-METAMASK-TEST-002",
                    guest_phone="6281299998888",
                    guest_wallet="0xGuestWallet123",
                    hotel_wallet=settings.HOTEL_WALLET_ADDRESS,
                    amount_usdt=46.88,
                    amount_idr=750000,
                    checkin_timestamp=int(now.timestamp()) + 86400 * 2,
                    status="CREATED",
                    tx_hash_create="0x8a593f24508132158f8974c2d93541d021eefddf639ae24555e7f695cc4048b5",
                    contract_address=settings.HOTEL_ESCROW_ADDRESS,
                    expires_at=now + datetime.timedelta(minutes=30),
                    created_at=now - datetime.timedelta(hours=1)
                ),
                CryptoEscrow(
                    booking_ref="BOOK-METAMASK-TEST-003",
                    guest_phone="6281299998888",
                    guest_wallet="0xGuestWallet123",
                    hotel_wallet=settings.HOTEL_WALLET_ADDRESS,
                    amount_usdt=46.88,
                    amount_idr=750000,
                    checkin_timestamp=int(now.timestamp()) + 86400 * 3,
                    status="CONFIRMED",
                    tx_hash_create="0x1b2699e41d3849c2ffd1274c327b4cb9cca282969fb3d150b1aa481abe7df496",
                    tx_hash_release="0xe0832bfb54fb294255e43e2e89905c801ba29bc68215a434d812d5674456fbcb",
                    contract_address=settings.HOTEL_ESCROW_ADDRESS,
                    expires_at=now + datetime.timedelta(minutes=30),
                    created_at=now - datetime.timedelta(minutes=45)
                )
            ]
            db.add_all(sample_escrows)
            db.commit()

        if db.query(OnChainAuditRecord).count() == 0:
            now = datetime.datetime.utcnow()
            sample_notarizations = [
                OnChainAuditRecord(
                    reference="ESCROW-BOOK-CRYPTO-TEST-001",
                    booking_ref="BOOK-CRYPTO-TEST-001",
                    payment_method="CRYPTO_USDT",
                    amount=650000.0,
                    currency="IDR",
                    tx_hash="0xc7278f5128e87884ee6f57f73229d93c12d24c3e59347a2e7a56661703071929",
                    block_number=45129801,
                    network="BSC Testnet (Chain ID: 97)",
                    verified=True,
                    payload_hash="0xc7278f5128e87884ee6f57f73229d93c12d24c3e59347a2e7a56661703071929",
                    created_at=now - datetime.timedelta(hours=2)
                ),
                OnChainAuditRecord(
                    reference="ESCROW-BOOK-METAMASK-TEST-003",
                    booking_ref="BOOK-METAMASK-TEST-003",
                    payment_method="CRYPTO_USDT",
                    amount=750000.0,
                    currency="IDR",
                    tx_hash="0x1b2699e41d3849c2ffd1274c327b4cb9cca282969fb3d150b1aa481abe7df496",
                    block_number=45129845,
                    network="BSC Testnet (Chain ID: 97)",
                    verified=True,
                    payload_hash="0x1b2699e41d3849c2ffd1274c327b4cb9cca282969fb3d150b1aa481abe7df496",
                    created_at=now - datetime.timedelta(minutes=45)
                )
            ]
            db.add_all(sample_notarizations)
            db.commit()

        if db.query(LoyaltyAccount).count() == 0:
            now = datetime.datetime.utcnow()
            loyalty_acc = LoyaltyAccount(
                phone="6281299998888",
                wallet_address="0x71C...345",
                total_earned=69,
                total_redeemed=0,
                balance=69,
                tier="None",
                booking_count=2,
                created_at=now - datetime.timedelta(hours=2)
            )
            db.add(loyalty_acc)
            db.commit()
    except Exception as e:
        db.rollback()
    finally:
        db.close()

def init_db():
    Base.metadata.create_all(bind=engine)
    seed_initial_crypto_data()

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
