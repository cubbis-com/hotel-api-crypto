# PRODUCT REQUIREMENTS DOCUMENT (PRD)
## PRODUK: ANVIEO CRYPTO SECUREPAY API ENGINE
### AI-Driven Virtual Receptionist with Decentralized Payment Escrow & On-Chain Audit Trail
**Repository / Folder**: `hotel-api-crypto`  
**Standar Arsitektur**: Decoupled Asynchronous Microservice + Web3 EVM Layer  
**Target Blockchain**: BNB Smart Chain (BSC Testnet Chain ID: 97 -> Mainnet Chain ID: 56)  
**Versi**: 2.0.0  
**Tanggal**: 1 Oktober 2026  

---

## 1. IKHTISAR PRODUK & TUJUAN ARSITEKTUR

### 1.1 Deskripsi Produk
**Anvieo Crypto SecurePay API** adalah platform backend cerdas perhotelan berbasis **Python FastAPI** yang memperluas fungsionalitas `hotel-api-master` dengan kemampuan transaksi Web3 terdesentralisasi. Sistem ini menyatukan:
1. **Layanan Resepsionis Virtual WhatsApp 24 Jam** yang ditenagai oleh model AI Garda LLM (`gemma4:e4b`) dengan pemahaman kalender zona waktu WITA (UTC+8) dan inventaris kamar fisik hotel secara real-time.
2. **Dual-Rail Payment Gateway**: Memproses pembayaran fiat lokal (QRIS & Virtual Account bank via TriPay) sekaligus pembayaran aset digital (USDT/BNB via Smart Contract Escrow).
3. **Lapisan Keamanan & Notarisasi On-Chain (On-Chain Audit Trail)**: Menjangkarkan hash kriptografis setiap transaksi ke smart contract `SecurePayRegistry.sol` pada BNB Smart Chain untuk mencegah pemalsuan dan manipulasi.
4. **Token Loyalitas Tamu BEP-20 (`LoyaltyToken.sol`)**: Memberikan reward poin digital otomatis (`ANV`) setelah tamu melakukan check-in resmi di hotel.
5. **Web Dashboard Front Office Terpadu**: Memberikan visualisasi audit trail on-chain, status kontrak escrow, dan manajemen sengketa bagi staf hotel.

### 1.2 Diagram Arsitektur Sistem

```
 +-----------------------------------------------------------------------------------+
 |                                 USER TOUCHPOINTS                                  |
 |  [ Calon Tamu (WhatsApp) ]                         [ Staf FO (Web Dashboard) ]    |
 +-----------------------+----------------------------------------+------------------+
                         |                                        |
                         | (Inbound Webhook HTTP)                 | (HTTP / Dashboard)
                         v                                        v
 +-----------------------------------------------------------------------------------+
 |                        ANVIEO CRYPTO SECUREPAY (FastAPI)                          |
 |                                                                                   |
 |  +-----------------------+   +----------------------+   +-----------------------+ |
 |  | WA Webhook Receiver   |-->| Garda AI Engine      |<->| Opera PMS Database    | |
 |  | (wa_service.py)       |   | (gemma4:e4b)         |   | (PostgreSQL Railway)  | |
 |  +-----------------------+   +----------------------+   +-----------------------+ |
 |             |                            |                                        |
 |             v (Background Task)          v (Dual Payment Decision)                |
 |  +------------------------------------------------------------------------------+ |
 |  |                          PAYMENT CONTROLLER ROUTER                           | |
 |  +---------------------------------------+--------------------------------------+ |
 |                     |                                        |                    |
 |                     v (Opsi A: Fiat QRIS/VA)                 v (Opsi B: Crypto)   |
 |         +-----------------------+               +-----------------------+         |
 |         | TriPay Service Client |               | Web3 Crypto Service   |         |
 |         | (HMAC-SHA256 Sig)     |               | (Web3.py / RPC)       |         |
 |         +-----------------------+               +-----------------------+         |
 |                     |                                        |                    |
 |                     v                                        v                    |
 |         +---------------------------------------------------------------+         |
 |         |             ON-CHAIN ASYNC NOTARIZATION DISPATCHER            |         |
 |         +---------------------------------------------------------------+         |
 +---------------------|----------------------------------------|--------------------+
                       |                                        |
                       v                                        v
 +-------------------------------------+  +------------------------------------------+
 |         EKSTERNAL FIAT GATEWAY      |  |         BNB SMART CHAIN (BSC TESTNET)    |
 |  TriPay Production / Sandbox API    |  |                                          |
 |  - QRIS Dynamic Generator           |  |  [ HotelEscrow.sol ]                     |
 |  - Virtual Account Multi-Bank       |  |  - Hold USDT funds until check-in        |
 |  - Webhook Callback Notifications   |  |  - Automated refund on cancellation      |
 |                                     |  |                                          |
 |                                     |  |  [ SecurePayRegistry.sol ]               |
 |                                     |  |  - Immutable transaction hash registry   |
 |                                     |  |  - Zero-PII public verification          |
 |                                     |  |                                          |
 |                                     |  |  [ LoyaltyToken.sol (ANV BEP-20) ]       |
 |                                     |  |  - Auto-mint 5% reward on check-in       |
 |                                     |  |  - Tier progression (Silver/Gold/Plat)   |
 +-------------------------------------+  +------------------------------------------+
                       |                                        |
                       +-------------------+--------------------+
                                           |
                                           v
                       +---------------------------------------+
                       |         PERSISTENCE LAYER (LOCAL)     |
                       |  - SQLite: inquiries, logs, escrows   |
                       |  - PostgreSQL: tenant_agnia_rooms     |
                       +---------------------------------------+
```

---

## 2. SPESIFIKASI KEBUTUHAN FUNGSIONAL (FUNCTIONAL REQUIREMENTS)

### Modul 1: Percakapan AI & Penawaran Dual Payment (WhatsApp)
* **FR-1.1**: AI Garda LLM mengenali niat pemesanan (*booking intent*), mengekstrak tanggal check-in/out, tipe kamar, serta jumlah tamu dari pesan WhatsApp.
* **FR-1.2**: AI melakukan verifikasi ketersediaan kamar fisik secara langsung ke database PostgreSQL tenant hotel tanpa risiko tumpang tindih (*overlap dates*).
* **FR-1.3**: Setelah tamu menyetujui pesan **REKAPITULASI DRAFT RESERVASI**, AI secara otomatis menampilkan opsi pembayaran:
  ```
  💰 PILIH METODE PEMBAYARAN:
  A) QRIS / Virtual Account (Bank Transfer, BCA, BRI, DANA, GoPay, OVO)
  B) Bayar Crypto (USDT / BNB via Smart Contract Escrow + Bonus Poin ANV)

  Balas A atau B untuk melanjutkan.
  ```
* **FR-1.4**: Jika tamu membalas `A`, sistem membuat tagihan closed payment TriPay dan mengirimkan gambar QR Code QRIS ke WhatsApp.
* **FR-1.5**: Jika tamu membalas `B`, sistem membuat kontrak escrow, menghitung ekuivalen harga dalam USDT, dan mengirim instruksi transfer dompet ke WhatsApp.

### Modul 2: Integrasi Pembayaran Fiat & Hash Notarization
* **FR-2.1**: Menerima webhook callback TriPay di `/api/v1/payment/tripay-callback`.
* **FR-2.2**: Memvalidasi signature HMAC-SHA256 menggunakan `TRIPAY_PRIVATE_KEY`.
* **FR-2.3**: Mengubah status reservasi menjadi `PAID`, mengalokasikan kamar fisik, dan membuat folio tagihan lunas di PostgreSQL.
* **FR-2.4**: Secara asinkron, sistem menghitung hash transaksi dan memanggil fungsi `recordTransaction()` pada kontrak `SecurePayRegistry.sol`.
* **FR-2.5**: Menyimpan `tx_hash` blockchain dan `block_number` ke dalam tabel database lokal `onchain_records`.

### Modul 3: Siklus Hidup Smart Contract Escrow (Crypto Payment)
* **FR-3.1**: Membuat entri booking pada kontrak pintar `HotelEscrow.sol` melalui fungsi `createBooking(bytes32 bookingRef, address guest, address hotel, uint256 amount, uint256 checkinTimestamp)`.
* **FR-3.2**: Mendengarkan (*listen/poll*) event `BookingFunded` pada blockchain. Jika tamu telah menyetor USDT ke kontrak, status diubah menjadi `FUNDED` dan notifikasi WhatsApp konfirmasi dikirimkan ke tamu.
* **FR-3.3**: Saat tamu tiba di hotel, staf FO menekan tombol *Confirm Check-In* pada Dashboard. Endpoint memanggil `confirmCheckin(bookingRef)` pada kontrak pintar, mencairkan dana USDT langsung ke dompet hotel.
* **FR-3.4**: Jika tamu membatalkan sebelum 24 jam check-in, endpoint memanggil `cancelBooking(bookingRef)` pada kontrak pintar, mengembalikan 100% USDT ke dompet tamu secara otomatis.
* **FR-3.5**: Jika terjadi perselisihan, fungsi `disputeBooking()` membekukan dana di kontrak sampai diselesaikan oleh admin hotel via `resolveDispute()`.

### Modul 4: Mesin Token Loyalitas BEP-20 (Loyalty Engine)
* **FR-4.1**: Setiap penyelesaian check-in yang sukses secara otomatis memanggil fungsi `awardPoints()` pada kontrak `LoyaltyToken.sol`.
* **FR-4.2**: Jumlah poin yang dicetak bernilai 5% dari total reservasi.
* **FR-4.3**: Tamu dapat memeriksa saldo poin loyalitas mereka kapan saja melalui WhatsApp dengan mengirim pesan `"cek poin"` atau `"saldo loyalitas"`.
* **FR-4.4**: Kontrak pintar secara otomatis menaikkan peringkat tier member berdasarkan akumulasi saldo token: *Silver (100 ANV)*, *Gold (500 ANV)*, atau *Platinum (2000 ANV)*.

### Modul 5: Web Dashboard & Monitoring On-Chain
* **FR-5.1**: Dashboard FO menyediakan tab navigasi baru: **"🔐 Crypto & Security"**.
* **FR-5.2**: Menampilkan 4 kartu ringkasan metrik: Total Transaksi QRIS/VA, Escrow Aktif, Total Record On-Chain, dan Total Poin Loyalitas Terdistribusi.
* **FR-5.3**: Menyediakan tabel audit transaksi dengan indikator verifikasi hijau (tercatat di blockchain) dan link langsung ke explorer BscScan.
* **FR-5.4**: Menyediakan tombol modal verifikasi seketika untuk mengecek eksistensi transaksi di blockchain secara transparan.

---

## 3. SPESIFIKASI DATA & MODEL DATABASE (DATABASE SCHEMA)

Sistem menggunakan model relasional hybrid:
1. **SQLite (`hotel_inquiries.db`)**: Mengelola histori pesan WhatsApp, state percakapan AI, audit log webhook, pencatatan escrow crypto, audit record on-chain, dan membership loyalitas.
2. **PostgreSQL Railway (`tenant_agnia_guesthouse`)**: Mengelola master kamar hotel, tipe kamar, reservasi resmi (`hotel_reservations`), detail kamar (`hotel_reservation_rooms`), dan folio billing (`hotel_folios`).

### Skema Tabel Baru SQLite (`database.py`):

```python
# 1. Tabel Escrow Pembayaran Kripto
class CryptoEscrow(Base):
    __tablename__ = "crypto_escrows"

    id = Column(Integer, primary_key=True, index=True)
    booking_ref = Column(String(100), unique=True, index=True) # Referensi PMS / inquiry
    guest_phone = Column(String(50), index=True)
    guest_wallet = Column(String(100), nullable=True)          # Address dompet tamu
    hotel_wallet = Column(String(100), nullable=False)         # Address dompet hotel
    amount_usdt = Column(Float, nullable=False)                # Nilai dalam USDT
    amount_idr = Column(Integer, nullable=False)               # Nilai konversi IDR
    checkin_timestamp = Column(Integer, nullable=False)        # Unix timestamp check-in
    
    # Status: CREATED, FUNDED, CONFIRMED, REFUNDED, DISPUTED, EXPIRED
    status = Column(String(50), default="CREATED")
    
    tx_hash_create = Column(String(100), nullable=True)
    tx_hash_fund = Column(String(100), nullable=True)
    tx_hash_release = Column(String(100), nullable=True)
    tx_hash_refund = Column(String(100), nullable=True)
    
    contract_address = Column(String(100), nullable=False)
    expires_at = Column(DateTime, nullable=False)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.datetime.utcnow, onupdate=datetime.datetime.utcnow)

# 2. Tabel Audit Trail On-Chain
class OnChainAuditRecord(Base):
    __tablename__ = "onchain_audit_records"

    id = Column(Integer, primary_key=True, index=True)
    reference = Column(String(100), unique=True, index=True)  # Reference TriPay / Escrow
    booking_ref = Column(String(100), index=True)
    payment_method = Column(String(50), nullable=False)       # QRIS, VA, CRYPTO_USDT
    amount = Column(Float, nullable=False)
    currency = Column(String(20), default="IDR")
    
    tx_hash = Column(String(100), unique=True, index=True)    # Hash transaksi BSC
    block_number = Column(Integer, nullable=True)
    network = Column(String(50), default="BSC Testnet")
    verified = Column(Boolean, default=True)
    payload_hash = Column(String(100), nullable=False)        # keccak256 hash
    
    created_at = Column(DateTime, default=datetime.datetime.utcnow)

# 3. Tabel Anggota Loyalitas (Loyalty Accounts)
class LoyaltyAccount(Base):
    __tablename__ = "loyalty_accounts"

    id = Column(Integer, primary_key=True, index=True)
    phone = Column(String(50), unique=True, index=True)
    wallet_address = Column(String(100), unique=True, nullable=True)
    total_earned = Column(Integer, default=0)
    total_redeemed = Column(Integer, default=0)
    balance = Column(Integer, default=0)                      # Saldo ANV token
    tier = Column(String(30), default="None")                 # None, Silver, Gold, Platinum
    booking_count = Column(Integer, default=0)
    
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.datetime.utcnow, onupdate=datetime.datetime.utcnow)

# 4. Tabel Riwayat Poin Loyalitas
class LoyaltyTransactionRecord(Base):
    __tablename__ = "loyalty_transaction_records"

    id = Column(Integer, primary_key=True, index=True)
    phone = Column(String(50), index=True)
    wallet_address = Column(String(100), nullable=True)
    booking_ref = Column(String(100), index=True, nullable=True)
    action_type = Column(String(50))                          # MINT_CHECKIN, REDEEM_CASHBACK
    points = Column(Integer, nullable=False)
    tx_hash = Column(String(100), nullable=True)
    
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
```

---

## 4. SPESIFIKASI REST API (ENDPOINTS)

### 4.1 Modul Pembayaran Fiat & Webhook (Existing Enhanced)
* `POST /webhook/whatsapp`: Menerima pesan inbound WhatsApp, memproses dialog AI, dan menangani pemilihan metode bayar (A/B).
* `POST /api/v1/payment/tripay-callback`: Menerima callback TriPay -> validasi HMAC -> update status PAID -> picu pencatatan on-chain asinkron.
* `POST /api/v1/payment/simulate-confirm`: Simulasi pembayaran internal untuk pengujian sandbox FO.

### 4.2 Modul Pembayaran Crypto Escrow (`/api/v2/crypto/`)
* `POST /api/v2/crypto/create-escrow`
  * **Deskripsi**: Membuat sesi escrow smart contract untuk reservasi tertentu.
  * **Request Body**:
    ```json
    {
      "booking_ref": "BK-2026-10-001",
      "guest_phone": "6281234567890",
      "guest_wallet": "0x70997970C51812dc3A010C7d01b50e0d17dc79C8",
      "amount_idr": 350000,
      "checkin_date": "2026-10-15"
    }
    ```
  * **Response (200 OK)**:
    ```json
    {
      "success": true,
      "escrow_id": "BK-2026-10-001",
      "amount_usdt": 21.875,
      "network": "BSC Testnet",
      "contract_address": "0x9A67b8E52fE338c2B5C3524b07AeaE301F25D94C",
      "hotel_wallet": "0x70997970C51812dc3A010C7d01b50e0d17dc79C8",
      "status": "CREATED",
      "expires_at": "2026-10-01T14:30:00Z"
    }
    ```
* `GET /api/v2/crypto/escrow/{booking_ref}`: Mengambil status escrow terkini (CREATED, FUNDED, CONFIRMED, REFUNDED).
* `POST /api/v2/crypto/escrow/{booking_ref}/confirm-checkin`: Staf FO konfirmasi check-in -> picu transfer dana escrow ke hotel wallet + mint loyalty points.
* `POST /api/v2/crypto/escrow/{booking_ref}/cancel`: Pembatalan sebelum 24 jam -> refund otomatis 100% USDT ke dompet tamu.
* `POST /api/v2/crypto/escrow/{booking_ref}/dispute`: Membekukan dana di escrow jika terjadi sengketa.

### 4.3 Modul Keamanan & Audit On-Chain (`/api/v2/security/`)
* `POST /api/v2/security/record-transaction`
  * **Deskripsi**: Memasukkan hash transaksi ke smart contract `SecurePayRegistry.sol`.
* `GET /api/v2/security/verify/{reference}`
  * **Deskripsi**: Memverifikasi keabsahan transaksi on-chain berdasarkan kode referensi.
  * **Response (200 OK)**:
    ```json
    {
      "reference": "DEV-T52086261001",
      "verified": true,
      "tx_hash": "0xabc1234567890abcdef1234567890abcdef1234567890abcdef1234567890",
      "block_number": 12345678,
      "network": "BSC Testnet",
      "timestamp": "2026-10-01T14:00:25Z",
      "bscscan_url": "https://testnet.bscscan.com/tx/0xabc1234567890abcdef1234567890abcdef1234567890abcdef1234567890"
    }
    ```
* `GET /api/v2/security/audit-trail/{booking_ref}`: Menampilkan seluruh linimasa transaksi on-chain untuk satu nomor pemesanan.

### 4.4 Modul Program Loyalitas (`/api/v2/loyalty/`)
* `GET /api/v2/loyalty/balance/{phone_or_wallet}`: Mengambil saldo token ANV, level tier, dan riwayat perolehan poin.
* `POST /api/v2/loyalty/award`: Pendaftaran member dan penambahan poin reward.
* `POST /api/v2/loyalty/redeem`: Penukaran poin loyalty untuk diskon kamar pada reservasi berikutnya.

### 4.5 Modul Dashboard Statistik (`/api/v2/dashboard/crypto-stats`)
* `GET /api/v2/dashboard/crypto-stats`: Mengembalikan metrik realtime untuk kartu widget dashboard (total transaksi, total escrow aktif, onchain records verified, dan total poin ANV).

---

## 5. KEBUTUHAN NON-FUNGSIONAL (NON-FUNCTIONAL REQUIREMENTS)

1. **Keamanan Kriptografi (Security)**:
   - Private key dompet operator hotel wajib disimpan dalam variabel lingkungan (`.env`) yang terisolasi dan tidak boleh bocor ke client.
   - Smart contracts menggunakan OpenZeppelin audited libraries (`SafeERC20`, `Ownable`, `ReentrancyGuard`, `AccessControl`).
2. **Kinerja & Latensi (Performance)**:
   - Waktu respons webhook WhatsApp ke pengguna < 3 detik.
   - Operasi penulisan ke blockchain dijalankan secara asinkron (*background task worker*) agar tidak memblokir siklus pemesanan tamu.
3. **Ketahanan Jaringan (Fault Tolerance & Reliability)**:
   - Jika node RPC BNB Chain mengalami kendala jaringan atau kegagalan koneksi, sistem secara otomatis mencoba ulang (*retry*) sebanyak 3 kali dengan mekanisme *exponential backoff*.
   - Status pemesanan di database lokal tetap aktif (*graceful degradation*).
4. **Skalabilitas Multi-Tenant (Scalability)**:
   - Arsitektur mendukung penambahan properti baru (*multi-property*) dengan memetakan `TENANT_ID` dan alamat wallet hotel terpisah.
