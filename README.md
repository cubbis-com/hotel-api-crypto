# Hotel API Crypto (SecurePay & Web3 Escrow Engine)

API Hotel berbasis AI (Garda LLM) & WhatsApp Bot dengan arsitektur **Dual-Payment**:
1. **Opsi A (Fiat QRIS)**: Pembayaran instan via TriPay Gateway yang otomatis di-notarisasi secara kriptografis (*hash payload*) ke Smart Contract **`SecurePayRegistry.sol`** on-chain (BNB Smart Chain Testnet).
2. **Opsi B (Crypto Escrow USDT)**: Pembayaran kripto berbasis Smart Contract **`HotelEscrow.sol`** (dana USDT terkunci aman, dicairkan otomatis saat Front Office mengonfirmasi check-in tamu).
3. **Loyalty Token Rewards (BEP-20 ANV)**: Tamu mendapatkan cashback 5% nilai pemesanan dalam bentuk token loyalitas **`LoyaltyToken.sol`** yang dipetakan ke nomor WhatsApp mereka.

---

## 📁 Struktur Direktori Proyek

```
hotel-api-crypto/
├── contracts/                     # Smart Contracts Solidity (BSC Testnet)
│   ├── HotelEscrow.sol            # Escrow contract untuk USDT
│   ├── SecurePayRegistry.sol      # On-chain notarization & audit trail
│   └── LoyaltyToken.sol           # BEP-20 Loyalty Token (ANV)
├── docs/                          # Dokumen Rekayasa Produk & Manajemen
│   ├── BRD_CRYPTO_SECUREPAY.md    # Business Requirements Document (Detail)
│   ├── PRD_CRYPTO_SECUREPAY.md    # Product Requirements Document (Detail)
│   └── SCRUM_PLAN_CRYPTO_SECUREPAY.md # Scrum Plan (Epics, Sprints, User Stories)
├── templates/
│   └── dashboard.html             # Dashboard Admin + Tab Web3 Crypto Escrow
├── static/
│   └── qr/                        # Static QR images generator
├── logs/                          # Berkas audit log teks
├── crypto_service.py              # Web3 BSC Engine, Notarisasi & Escrow
├── garda_service.py               # Garda LLM Assistant (Dual-Payment Prompt)
├── tripay_service.py              # TriPay Payment Gateway Integration
├── db_hotel_service.py            # PostgreSQL Tenant Agnia Database Service
├── wa_service.py                  # WhatsApp Gateway Client (Wuller API)
├── activity_logger.py             # Structured Event & Activity Logger
├── database.py                    # SQLite Persistence & Web3 Data Models
├── config.py                      # Pydantic Settings & Environment Variables
├── main.py                        # FastAPI Application (V1 + V2 Endpoints)
├── .env                           # Konfigurasi aktif (100% kompatibel hotel-api-master)
├── .env.example                   # Template variabel lingkungan
└── requirements.txt               # Dependencies (FastAPI, Web3, Eth-Account, dll)
```

---

## ⚙️ Keselarasan Environment (.env)

Proyek ini menggunakan konfigurasi yang **100% sama dan kompatibel** dengan `hotel-api-master`:
- **Database PostgreSQL**: Railway Cloud (`tenant_agnia_guesthouse`)
- **TriPay Gateway**: Sandbox API Key & Private Key
- **AI LLM Garda**: Server internal `http://103.30.146.140:11434` (`gemma4:e4b`)
- **WhatsApp Gateway**: `https://wa.inovasiuitjbt.uk`
- **Konfigurasi Tambahan Web3 (Section 9)**:
  - `BSC_RPC_URL`: `https://data-seed-prebsc-1-s1.binance.org:8545/`
  - `BSC_CHAIN_ID`: `97`
  - `CONTRACT_ESCROW_ADDRESS`: `0x337610d27c682E347C9cD60BD4b3b107C9d34dDd` (Official BSC Testnet USDT)
  - `CONTRACT_REGISTRY_ADDRESS`: `0xca11bde05977b3631167028862be2a173976ca11` (BSC Testnet Registry Notary)
  - `CONTRACT_LOYALTY_TOKEN_ADDRESS`: `0x84b9b910527ad5c03a9ca831909e21e236ea7b06` (BSC Testnet Token)
  - `HOTEL_WALLET_ADDRESS`: `0x036EAe4133c72d7DA3480b9F35f84577daaC5644` (Hotel Treasury MetaMask)
  - `USDT_IDR_RATE`: `16000`

---

## 🚀 Menjalankan Server

1. **Install Dependencies**:
   ```bash
   pip install -r requirements.txt
   ```

2. **Jalankan Aplikasi dengan Uvicorn**:
   ```bash
   uvicorn main:app --host 0.0.0.0 --port 8000 --reload
   ```

3. **Akses Dashboard**:
   Buka peramban ke `http://localhost:8000/` dan klik tab **"Crypto & Web3 Escrow"**.

---

## 📑 Dokumentasi Resmi

- [PRD (Product Requirements Document)](file:///Users/kerasakti/Documents/HOTEL/PORTAL/hotel-api-crypto/docs/PRD_CRYPTO_SECUREPAY.md)
- [BRD (Business Requirements Document)](file:///Users/kerasakti/Documents/HOTEL/PORTAL/hotel-api-crypto/docs/BRD_CRYPTO_SECUREPAY.md)
- [Scrum Plan & Sprints](file:///Users/kerasakti/Documents/HOTEL/PORTAL/hotel-api-crypto/docs/SCRUM_PLAN_CRYPTO_SECUREPAY.md)
