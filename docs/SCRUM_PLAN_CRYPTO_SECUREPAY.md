# SCRUM PLAN & SPRINT ROADMAP
## PROYEK: ANVIEO CRYPTO SECUREPAY API
### Rencana Pengembangan Scrum, Epics, User Stories, & Acceptance Criteria
**Repository / Folder**: `hotel-api-crypto`  
**Metodologi**: Agile Scrum Framework  
**Total Sprints**: 4 Sprint (Durasi per Sprint: 2 Minggu)  
**Total Story Points**: 75 Poin (Skala Fibonacci)  
**Target Delivery**: Rilis Produksi & Lomba Web3 Innovation  

---

## 1. STRUKTUR TIM SCRUM & PERAN

| Peran | Tanggung Jawab Utama |
|---|---|
| **Product Owner (PO)** | Menentukan prioritas backlog, memastikan kesesuaian kebutuhan bisnis Agnia Guesthouse (Pak Budi) dan pengalaman tamu (Sari), validasi acceptance criteria. |
| **Scrum Master (SM)** | Memfasilitasi upacara Scrum, menghapus hambatan (*impediments*), mengawal komitmen sprint dan *burn-down velocity*. |
| **Blockchain & Smart Contract Engineer** | Mengembangkan, menguji (*unit test*), dan mendeploy smart contract `HotelEscrow.sol`, `SecurePayRegistry.sol`, dan `LoyaltyToken.sol` di BSC Testnet & Mainnet. |
| **Senior Backend AI & Web3 Engineer** | Mengintegrasikan Web3.py ke FastAPI, memodifikasi prompt Garda LLM, membangun antrean asinkron hash on-chain, dan menghubungkan webhook WhatsApp & TriPay. |
| **Frontend & UI/UX Specialist** | Mengembangkan tab baru "🔐 Crypto & Security" pada Jinja2 dashboard, modal verifikasi audit trail, visualisasi statistik, dan memastikan responsivitas mobile. |
| **QA & Smart Contract Auditor** | Menguji integrasi *end-to-end* (WhatsApp -> LLM -> Booking -> Payment -> Release/Refund), audit keamanan reentrancy guard, dan stress test. |

---

## 2. DEFINISI KESIAPAN & KESELESAIAN (DoR & DoD)

### Definition of Ready (DoR)
Sebuah User Story dinyatakan siap dimasukkan ke dalam Sprint Backlog apabila:
1. Format *User Story* memenuhi standar: *"As a... I want... So that..."*.
2. Memiliki *Acceptance Criteria* berbasis pola **Given-When-Then** yang teruji.
3. Ketergantungan teknis (*dependencies*) sudah teridentifikasi dan tersedia (misal: kredensial testnet BSC, ABI smart contract).
4. Estimasi *Story Point* telah disepakati bersama oleh tim pengembang melalui *Planning Poker*.

### Definition of Done (DoD)
Sebuah User Story dinyatakan selesai apabila:
1. Seluruh *Acceptance Criteria* terpenuhi dan lolos verifikasi QA.
2. Kode telah diulas (*Code Review / Pull Request*) dan digabungkan ke cabang utama.
3. Unit test & integration test berhasil dijalankan dengan *coverage* minimal 85%.
4. Dokumentasi API (Swagger/OpenAPI & Markdown) telah diperbarui.
5. Fitur telah diuji coba pada lingkungan staging/sandbox tanpa ada *critical bug*.

---

## 3. RINGKASAN EPIC & ESTIMASI STORY POINTS

```
+---------------------------------------------------------------------------------------+
| EPIC ID | NAMA EPIC                                   | JUMLAH US | STORY POINTS (SP) |
+---------------------------------------------------------------------------------------+
| EPIC 1  | Layanan Pembayaran Crypto (Escrow)          | 4 Stories | 23 SP             |
| EPIC 2  | Lapisan Keamanan (Hash On-Chain Notarization)| 3 Stories | 15 SP             |
| EPIC 3  | Program Loyalitas Token BEP-20 (ANV)        | 3 Stories | 11 SP             |
| EPIC 4  | Bridge ke Sistem Existing (Garda AI & TriPay)| 3 Stories | 11 SP             |
| EPIC 5  | Web Dashboard & Monitoring On-Chain         | 3 Stories | 15 SP             |
+---------------------------------------------------------------------------------------+
| TOTAL   | 5 EPICS                                     | 16 STORIES| 75 STORY POINTS   |
+---------------------------------------------------------------------------------------+
```

---

## 4. JADWAL SPRINT & RINCIAN USER STORY

### 🚀 SPRINT 1: Pondasi Smart Contract, Prompt AI Dual-Payment & Hash Notarization
**Durasi**: Minggu 1 - Minggu 2  
**Target Velocity**: 19 Story Points  
**Tujuan Sprint**: Mendeploy 3 Smart Contract ke BSC Testnet, mengintegrasikan prompt pemilihan metode pembayaran A/B pada Garda LLM, dan merekam hash callback TriPay secara on-chain.

#### US-1.1: Pemilihan Metode Pembayaran oleh Tamu di WhatsApp (3 SP)
* **As a**: Calon Tamu Hotel (Sari)
* **I want**: Diberikan opsi memilih pembayaran (A: QRIS/VA atau B: Crypto USDT) setelah menerima draft reservasi.
* **So that**: Saya dapat memilih instrumen pembayaran yang paling nyaman bagi saya.
* **Acceptance Criteria**:
  * **Given**: Tamu telah menerima *REKAPITULASI DRAFT RESERVASI* dan menyatakan ingin membayar.
  * **When**: Sistem Garda AI merespons.
  * **Then**: Pesan menampilkan opsi A (QRIS/VA) dan B (Crypto USDT Escrow + Bonus Poin).
  * **And**: Jika tamu membalas "A", sistem memicu pembuatan invoice TriPay; jika membalas "B", sistem mengarahkan ke escrow kripto.

#### US-4.1: Bridge Pencatatan Hash pada Callback TriPay (3 SP)
* **As a**: Developer Sistem
* **I want**: Menambahkan satu pemanggilan fungsi pencatatan hash on-chain saat webhook callback TriPay sukses divalidasi.
* **So that**: Pembayaran QRIS/VA otomatis dijangkarkan ke blockchain tanpa mengganggu alur reservasi existing.
* **Acceptance Criteria**:
  * **Given**: Webhook callback TriPay masuk dengan signature HMAC-SHA256 valid.
  * **When**: Status reservasi diubah menjadi `PAID`.
  * **Then**: Sistem memanggil fungsi asinkron `recordTransaction()` pada `SecurePayRegistry.sol`.
  * **And**: Jika jaringan blockchain mengalami kendala/timeout, alur reservasi kamar tetap sukses dan pencatatan on-chain dimasukkan ke antrean retry.

#### US-2.1: Pencatatan Transaksi QRIS/VA ke Blockchain (5 SP)
* **As a**: Pemilik Hotel (Pak Budi)
* **I want**: Setiap pembayaran QRIS/VA yang berhasil dicatat hash matematisnya di smart contract `SecurePayRegistry.sol`.
* **So that**: Hotel memiliki bukti audit permanen yang tidak dapat dimanipulasi oleh siapa pun.
* **Acceptance Criteria**:
  * **Given**: Transaksi status `PAID` terverifikasi.
  * **When**: Hash payload dicatat ke smart contract.
  * **Then**: Smart contract memancarkan event `TransactionRecorded(txHash, bookingRef, reference, amount)`.
  * **And**: `tx_hash` dan `block_number` tersimpan di database lokal SQLite (`onchain_audit_records`).

#### US-4.2: Modifikasi Prompt AI Resepsionis Garda untuk Negosiasi Dual Payment (5 SP)
* **As a**: Calon Tamu Hotel
* **I want**: AI Resepsionis memahami jawaban natural seperti "mau bayar pakai qris aja", "bisa pakai usdt?", atau "pilih A".
* **So that**: Proses transaksi terasa ramah dan tidak kaku.
* **Acceptance Criteria**:
  * **Given**: Tamu berada pada tahap pemilihan metode pembayaran.
  * **When**: Tamu membalas secara kasual tanpa mengetik huruf A atau B.
  * **Then**: AI Garda cerdas mengklasifikasikan niat tamu ke opsi pembayaran yang relevan.

#### Task Enabler: Kompilasi & Deployment Smart Contract ke BSC Testnet (3 SP)
* Deployment `HotelEscrow.sol`, `SecurePayRegistry.sol`, dan `LoyaltyToken.sol` menggunakan Hardhat / Web3.py.
* Menyimpan alamat kontrak dan ABI ke konfigurasi aplikasi (`config.py` dan `.env`).

---

### 🚀 SPRINT 2: Siklus Hidup Escrow Kripto & Pengembalian Otomatis (Refund Engine)
**Durasi**: Minggu 3 - Minggu 4  
**Target Velocity**: 21 Story Points  
**Tujuan Sprint**: Menyelesaikan seluruh siklus pembayaran crypto via smart contract (Create -> Fund -> Release on Check-In -> Auto-Refund on Cancel) dan endpoint verifikasi on-chain.

#### US-1.2: Tamu Membayar Crypto ke Smart Contract Escrow (8 SP)
* **As a**: Calon Tamu Hotel (Sari)
* **I want**: Mengirim USDT ke smart contract escrow melalui jaringan BSC Testnet.
* **So that**: Dana saya aman ditahan di blockchain sampai saya tiba di hotel.
* **Acceptance Criteria**:
  * **Given**: Tamu memilih metode B (Crypto).
  * **When**: Sistem memanggil `POST /api/v2/crypto/create-escrow`.
  * **Then**: Kontrak `HotelEscrow.createBooking()` dieksekusi, status escrow = `CREATED`.
  * **And**: WhatsApp AI mengirimkan alamat kontrak, nominal USDT, dan timer countdown 30 menit.
  * **When**: Tamu mentransfer USDT dan memanggil `fundBooking()`.
  * **Then**: Kontrak memancarkan event `BookingFunded`, status berubah menjadi `FUNDED`, dan WhatsApp mengirim konfirmasi lunas.

#### US-1.3: Konfirmasi Check-in Memicu Pencairan Dana Escrow (5 SP)
* **As a**: Staf Front Office / Pemilik Hotel (Pak Budi)
* **I want**: Menekan tombol check-in di sistem saat tamu tiba, yang otomatis mentransfer USDT dari escrow ke dompet hotel.
* **So that**: Hotel menerima dana tanpa perlu penarikan manual yang rumit.
* **Acceptance Criteria**:
  * **Given**: Escrow berstatus `FUNDED` dan tamu tiba di meja resepsionis.
  * **When**: Staf FO memanggil `POST /api/v2/crypto/escrow/{booking_ref}/confirm-checkin`.
  * **Then**: Smart contract mengeksekusi `confirmCheckin()`, dana dilepas ke `hotel_wallet`.
  * **And**: Sistem mencegah eksekusi ganda (*Double Check-in Prevention*) dengan kode 409 Conflict jika sudah dikonfirmasi.

#### US-1.4: Pembatalan Pemesanan & Pengembalian Dana Otomatis (5 SP)
* **As a**: Tamu Hotel
* **I want**: Membatalkan reservasi melalui WhatsApp dan menerima pengembalian dana USDT secara otomatis jika masih dalam batas waktu pembatalan gratis.
* **So that**: Hak pengembalian dana saya terlindungi secara instan.
* **Acceptance Criteria**:
  * **Given**: Escrow berstatus `FUNDED`.
  * **When**: Tamu membatalkan pemesanan lebih dari 24 jam sebelum waktu check-in (14:00 WITA).
  * **Then**: Sistem memanggil `cancelBooking()`, kontrak pintar mengembalikan 100% USDT ke dompet tamu.
  * **And**: Kamar fisik di PostgreSQL langsung dikembalikan ke kuota kosong.

#### US-2.2: REST API Verifikasi Transaksi On-Chain (3 SP)
* **As a**: Staf FO & Auditor
* **I want**: Endpoint publik untuk memeriksa status validasi blockchain berdasarkan nomor referensi transaksi.
* **So that**: Kami dapat membuktikan keabsahan transaksi tanpa membuka database internal hotel.
* **Acceptance Criteria**:
  * **Given**: Kode referensi pembayaran (fiat atau kripto).
  * **When**: Melakukan request `GET /api/v2/security/verify/{reference}`.
  * **Then**: Mengembalikan data: `verified: true`, `tx_hash`, `block_number`, dan `bscscan_url`.

---

### 🚀 SPRINT 3: Mesin Loyalitas Token BEP-20 & Audit Trail Lengkap
**Durasi**: Minggu 5 - Minggu 6  
**Target Velocity**: 19 Story Points  
**Tujuan Sprint**: Mengaktifkan sistem reward loyalitas token ANV otomatis, pengecekan poin lewat WhatsApp, linimasa audit trail per booking, dan monitoring transaksi terpadu.

#### US-3.1: Pencetakan Token Loyalitas Otomatis Pasca Check-In (5 SP)
* **As a**: Tamu Hotel (Sari)
* **I want**: Mendapatkan reward poin token loyalitas ANV (5% dari nilai transaksi) secara otomatis setelah check-in fisik dikonfirmasi.
* **So that**: Saya dapat mengumpulkan saldo untuk mendapatkan diskon pemesanan berikutnya.
* **Acceptance Criteria**:
  * **Given**: Check-in tamu berhasil dikonfirmasi (baik metode QRIS maupun Crypto).
  * **When**: Event check-in selesai diproses.
  * **Then**: Sistem memanggil fungsi `awardPoints()` pada kontrak `LoyaltyToken.sol`.
  * **And**: WhatsApp mengirimkan ucapan selamat dan rincian perolehan poin ke nomor tamu.
  * **And**: Sistem menolak pencetakan ganda untuk nomor referensi pemesanan yang sama (*Anti Double-Mint*).

#### US-3.2: Tamu Mengecek Saldo Poin via WhatsApp (3 SP)
* **As a**: Tamu Hotel
* **I want**: Mengetik "cek poin" atau "saldo loyalitas" di WhatsApp untuk melihat saldo dan tier keanggotaan saya.
* **So that**: Saya tahu berapa poin yang saya miliki tanpa perlu mengunjungi website eksternal.
* **Acceptance Criteria**:
  * **Given**: Tamu pernah menginap dan memiliki nomor WhatsApp terdaftar.
  * **When**: Tamu mengirim pesan *"cek poin"*.
  * **Then**: AI membalas rincian: Total Poin ANV, Tier (Silver/Gold/Platinum), dan keuntungan menginap berikutnya.

#### US-2.3: Audit Trail Linimasa Lengkap per Reservasi (5 SP)
* **As a**: Pemilik Hotel & Auditor
* **I want**: Melihat seluruh rekam jejak siklus reservasi (mulai dari draft, pembayaran, pencatatan hash on-chain, check-in, hingga loyalitas) dalam satu linimasa visual.
* **So that**: Pemeriksaan kepatuhan transaksi menjadi transparan dan mudah ditelusuri.
* **Acceptance Criteria**:
  * **Given**: Nomor referensi reservasi (contoh: `BK-2026-001`).
  * **When**: Mengakses `GET /api/v2/security/audit-trail/{booking_ref}`.
  * **Then**: Menghasilkan array peristiwa kronologis lengkap dengan status verifikasi, tautan BscScan, dan stempel waktu.

#### US-5.1: Pemilik Hotel Memantau Semua Transaksi Terpadu (6 SP)
* **As a**: Pemilik Hotel (Pak Budi)
* **I want**: Dashboard menampilkan ringkasan seluruh transaksi (QRIS, VA, dan Crypto) beserta status verifikasi blockchain.
* **So that**: Saya memiliki gambaran lengkap performa keuangan hotel dalam satu layar.
* **Acceptance Criteria**:
  * **Given**: Staf/Owner login ke Web Dashboard FO.
  * **When**: Membuka tab "🔐 Crypto & Security".
  * **Then**: Menampilkan 4 kartu statistik realtime dan tabel transaksi hibrida dengan indikator verifikasi hijau.

---

### 🚀 SPRINT 4: Dashboard Polishing, Audit Keamanan & Pengujian End-to-End
**Durasi**: Minggu 7 - Minggu 8  
**Target Velocity**: 16 Story Points  
**Tujuan Sprint**: Menambahkan modal verifikasi interaktif, tampilan statistik loyalitas, pengujian regresi menyeluruh, stress test jaringan, dan kesiapan rilis.

#### US-5.2: Modal Verifikasi On-Chain Satu Klik untuk Staf FO (4 SP)
* **As a**: Staf Front Office
* **I want**: Mengklik tombol "Verify" pada baris transaksi di dashboard untuk membuka modal bukti keaslian transaksi on-chain.
* **So that**: Saya dapat langsung memperlihatkan bukti verifikasi kepada tamu atau pihak manajemen.
* **Acceptance Criteria**:
  * **Given**: Baris transaksi pada tabel dashboard.
  * **When**: Tombol "Verify" diklik.
  * **Then**: Modal popup muncul menampilkan status VERIFIED, nomor blok, hash transaksi, metode bayar, dan tombol langsung ke BscScan.

#### US-3.3: Visualisasi Statistik Program Loyalitas di Dashboard (4 SP)
* **As a**: Pemilik Hotel (Pak Budi)
* **I want**: Melihat grafik distribusi tier anggota dan daftar 10 tamu dengan poin terbanyak (*Top 10 Guests*).
* **So that**: Saya dapat merancang strategi promosi dan retensi tamu yang lebih tepat sasaran.
* **Acceptance Criteria**:
  * **Given**: Tab "Crypto & Security" pada dashboard.
  * **When**: Halaman dimuat.
  * **Then**: Menampilkan persentase tier (Platinum, Gold, Silver) dan daftar tamu setia beserta total frekuensi booking.

#### Task Enabler: Stress Test, Audit Keamanan & Fallback Resilience (8 SP)
* Pengujian simulasi 100 transaksi bersamaan (*concurrency test*).
* Pengujian skenario kegagalan RPC node: memastikan sistem melakukan *retry* tanpa memblokir alur pemesanan tamu di WhatsApp.
* Audit kode smart contract terhadap kerentanan reentrancy, integer overflow, dan validasi hak akses (*AccessControl*).

---

## 5. RENCANA MANAJEMEN RISIKO SPRINT

| Risiko Teknis / Operasional | Dampak | Probabilitas | Rencana Mitigasi |
|---|---|---|---|
| **Lonjakan Gas Fee di BNB Chain** | Sedang | Rendah | Menggunakan estimasi gas dinamis; arsitektur siap di-bridge ke opBNB (Layer 2) yang berbiaya sub-sen. |
| **Gangguan Node RPC Testnet BSC** | Tinggi | Sedang | Mengonfigurasi *multi-RPC fallback* (Binance official RPC, Ankr, QuickNode) pada `crypto_service.py`. |
| **Keterlambatan Konfirmasi Transaksi Kripto** | Sedang | Sedang | Mengirimkan notifikasi WhatsApp berkala kepada tamu jika transaksi sedang menunggu konfirmasi blok (*pending confirmations*). |
| **Kesalahan Input Nomor HP / Wallet** | Rendah | Sedang | Validasi format otomatis dengan pustaka Web3 dan pembersihan karakter non-numerik pada nomor telepon WhatsApp. |
