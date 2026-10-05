# BUSINESS REQUIREMENTS DOCUMENT (BRD)
## PROYEK: ANVIEO CRYPTO SECUREPAY API
### Ekosistem Perhotelan Cerdas & Web3 Payment Escrow
**Properti Pilot**: Agnia Guesthouse Balikpapan (Anvieo Hospitality Ecosystem)  
**Versi**: 1.0.0  
**Tanggal**: 1 Oktober 2026  
**Status**: Approved for Technical Scaffolding & Scrum Execution  

---

## 1. RINGKASAN EKSEKUTIF & LATAR BELAKANG

### 1.1 Latar Belakang Bisnis
Industri perhotelan independen dan akomodasi skala menengah (Guesthouse & Boutique Hotel) di Indonesia, seperti **Agnia Guesthouse Balikpapan** (12 kamar, standar OPERA PMS v4.0), menghadapi tantangan ganda dalam operasional penerimaan tamu dan manajemen arus kas (cashflow). 

Saat ini, sistem `hotel-api-master` telah sukses mengoperasikan **Resepsionis Virtual AI 24 Jam** berbasis model Garda LLM (`gemma4:e4b`) yang terhubung langsung ke WhatsApp Gateway (`wa.inovasiuitjbt.uk`) dan Payment Gateway TriPay (QRIS & Virtual Account). Sistem ini berhasil mengatasi masalah operasional ketika meja Front Office (FO) tutup di malam hari (pukul 20:00 - 08:00 WITA) dan mencegah *lost booking opportunity*.

Namun, seiring ekspansi bisnis Anvieo ke multi-properti dan meningkatnya arus wisatawan digital mancanegara (digital nomads, ekspatriat IKN Nusantara di Kalimantan Timur), muncul batasan struktural pada sistem pembayaran konvensional:
1. **Ketergantungan Tunggal pada Gateway Fiat (Single Point of Failure)**: Ketika webhook callback TriPay gagal diterima (misal: timeout jaringan, invalid HMAC key), status reservasi tertahan `UNPAID` meskipun saldo tamu sudah terpotong.
2. **Ketiadaan Audit Trail Immutable**: Bukti transfer bank atau screenshot QRIS rentan dimanipulasi dengan aplikasi editing gambar. Intervensi manual staf FO via endpoint simulasi internal tidak memiliki jejak bukti permanen yang dapat diverifikasi publik tanpa memperlihatkan data pribadi (PII).
3. **Siklus Settlement Lambat (T+1 s/d T+2)**: Dana hasil pembayaran QRIS baru masuk ke rekening bank pemilik hotel dalam 1-2 hari kerja (terhenti pada akhir pekan dan hari libur nasional), menghambat likuiditas operasional harian hotel.
4. **Hambatan Tamu Mancanegara**: Tamu asing tidak memiliki akun perbankan lokal Indonesia maupun e-wallet domestik (GoPay, OVO, ShopeePay, DANA), namun memiliki dompet aset digital (USDT/Crypto).
5. **Rendahnya Retensi Tamu (Zero Loyalty Infrastructure)**: Tidak ada program loyalitas modern yang transparan untuk mendorong tamu menginap kembali.

### 1.2 Visi Produk & Solusi Bisnis
**Anvieo Crypto SecurePay** hadir sebagai generasi baru Hotel API yang menggabungkan keandalan AI Resepsionis WhatsApp dengan **lapisan keamanan dan pembayaran terdesentralisasi (Web3 Blockchain Layer)** di atas jaringan **BNB Smart Chain (BSC)**.

Sistem ini memperkenalkan pendekatan hibrida (*Dual-Rail Architecture*):
* **Bagi Tamu Biasa (Fiat)**: Tetap membayar via QRIS/VA secara instan tanpa perlu paham Web3, namun bukti keaslian transaksi secara otomatis di-hash dan dijangkarkan ke blockchain secara permanen (*On-Chain Notarization*).
* **Bagi Tamu Digital/Internasional (Crypto)**: Menyediakan opsi pembayaran stablecoin (USDT) menggunakan Smart Contract Escrow terdesentralisasi. Dana tamu aman di-hold oleh kontrak pintar sampai check-in fisik di hotel terkonfirmasi.
* **Bagi Tamu Setia (Loyalty Engine)**: Reward otomatis berupa token loyalitas BEP-20 (`ANV`) sebesar 5% dari nilai transaksi untuk potongan harga menginap berikutnya.

---

## 2. STAKEHOLDER & USER PERSONAS

### 2.1 Pemilik Hotel (Pak Budi Santoso)
* **Profil**: 42 tahun, pemilik & pengelola Agnia Guesthouse Balikpapan (sedang ekspansi ke 3 properti).
* **Tujuan**:
  - Arus kas lebih cepat cair tanpa menunggu settlement berhari-hari.
  - Memiliki bukti audit yang tidak terbantahkan jika terjadi sengketa tamu atau klaim palsu.
  - Memantau performa booking dan transaksi multi-properti dari 1 dashboard terpadu.
* **Pain Points**:
  - Pernah dirugikan oleh tamu yang mengirim bukti bayar palsu.
  - Staf FO kesulitan merekonsiliasi pembayaran saat callback gateway mengalami gangguan teknis.

### 2.2 Tamu Hotel / Digital Nomad (Sari Wulandari)
* **Profil**: 29 tahun, Digital Marketing Specialist, sering bepergian ke Balikpapan & kawasan IKN. Menguasai smartphone dan familiar dengan dompet kripto (USDT, Binance, MetaMask).
* **Tujuan**:
  - Reservasi cepat via WhatsApp tanpa repot install aplikasi hotel baru.
  - Memiliki jaminan uang tidak hilang jika reservasi dibatalkan sebelum batas waktu (*trustless escrow refund*).
  - Mendapatkan reward poin yang transparan dan dapat dipakai kembali.
* **Pain Points**:
  - Malas mengunduh aplikasi pemesanan hotel yang rumit.
  - Khawatir jika membatalkan hotel proses pengembalian dana (*refund*) memakan waktu berminggu-minggu.

### 2.3 Staf Front Office (FO) & Kasir
* **Profil**: Staf operasional shift pagi/siang/malam di Agnia Guesthouse.
* **Tujuan**:
  - Melakukan verifikasi pembayaran tamu dalam hitungan detik saat tamu berdiri di depan meja lobi.
  - Cukup satu klik untuk mengonfirmasi check-in fisik tamu dan secara otomatis mencairkan dana escrow.
* **Pain Points**:
  - Sering ragu apakah bukti transfer tamu valid atau rekayasa saat sistem bank *offline*.

### 2.4 Auditor Keuangan & Badan Regulasi
* **Tujuan**: Memastikan keabsahan rekonsiliasi keuangan hotel tanpa melanggar undang-undang kerahasiaan data pribadi (*data privacy*).
* **Kebutuhan**: Hash transaksi on-chain yang dapat diverifikasi publik melalui block explorer (BscScan) tanpa mengekspos nama lengkap, NIK, atau nomor WhatsApp tamu.

---

## 3. ANALISIS PERBANDINGAN: AS-IS VS TO-BE

| Parameter | Sistem Saat Ini (hotel-api-master) | Sistem Baru (hotel-api-crypto) |
|---|---|---|
| **Metode Pembayaran** | Hanya QRIS dan Virtual Account (TriPay) | Dual Option: QRIS/VA (TriPay) + Crypto USDT Escrow (BNB Smart Chain) |
| **Audit Trail Pembayaran** | Database internal SQLite & PostgreSQL | Database internal + Immutable On-Chain Hash Registry di BNB Chain |
| **Penyelesaian Sengketa** | Manual, intervensi staf tanpa bukti matematis | Verifikasi hash kriptografis independen di BscScan |
| **Mekanisme Escrow** | Bergantung pada rekening bank merchant | Smart Contract Trustless Escrow (`HotelEscrow.sol`) |
| **Kebijakan Refund** | Manual via transfer bank, proses lambat | Otomatis via Smart Contract jika cancel < 24 jam sebelum check-in |
| **Loyalty Program** | Tidak ada | Token Loyalitas BEP-20 (`LoyaltyToken.sol` - ANV) dengan 4 Tier keanggotaan |
| **Dashboard FO** | Tabel transaksi standar TriPay | Unified Dashboard + Tab "🔐 Crypto & Security" dengan status On-Chain realtime |
| **Resepsionis AI WhatsApp** | Menawarkan QRIS saja | Menawarkan Opsi A (QRIS/VA) dan Opsi B (Crypto Escrow + Loyalty Reward) |

---

## 4. ATURAN BISNIS (BUSINESS RULES)

### BR-01: Penawaran Metode Pembayaran Hibrida
1. AI Garda Resepsionis hanya akan menawarkan metode pembayaran setelah tahapan **REKAPITULASI DRAFT RESERVASI** disetujui secara eksplisit oleh tamu di WhatsApp.
2. AI wajib menampilkan 2 pilihan yang jelas dan tidak membingungkan:
   - **Pilihan A**: QRIS / Transfer Virtual Account (Semua bank & e-wallet Indonesia).
   - **Pilihan B**: Bayar Crypto USDT (Aman dengan smart contract escrow + bonus reward loyalitas).
3. Jika tamu memilih opsi non-standar (misal: "mau yang biasa saja"), sistem secara cerdas mengarahkan ke Pilihan A (QRIS).

### BR-02: Siklus Hidup Escrow Pembayaran Kripto
1. **Pembuatan (Creation)**: Ketika tamu memilih Pilihan B, sistem membuat sesi escrow dengan batas waktu pembayaran (*expiry window*) selama 30 menit. Nilai IDR dikonversi ke USDT berdasarkan nilai tukar referensi (default: 1 USDT = Rp 16.000).
2. **Pendanaan (Funding)**: Tamu mengirim USDT ke kontrak escrow. Status berubah menjadi `FUNDED`. Kamar fisik di PostgreSQL langsung dikunci (*HOLD*).
3. **Pencairan (Release)**: Saat tamu tiba di hotel dan staf FO menekan tombol *Confirm Check-In*, kontrak pintar secara otomatis mentransfer 100% dana dari escrow ke dompet (*wallet*) resmi hotel.
4. **Pembatalan & Refund**: Tamu dapat membatalkan pemesanan secara mandiri via WhatsApp sebelum batas waktu pembatalan gratis (sesuai konfigurasi `.env`: minimal 24 jam sebelum waktu check-in 14:00 WITA). Dana 100% dikembalikan seketika oleh kontrak pintar ke dompet tamu.
5. **Kadaluarsa (Expired)**: Jika tamu tidak melakukan transfer dalam 30 menit sejak escrow dibuat, status kamar dilepas kembali ke inventaris hotel.

### BR-03: Pencatatan Transaksi On-Chain (On-Chain Notarization)
1. Setiap pembayaran QRIS/VA yang sukses diverifikasi oleh TriPay (valid signature HMAC-SHA256) wajib dicatat hash transaksinya ke smart contract `SecurePayRegistry.sol`.
2. Hash yang dicatat terdiri dari: `keccak256(reference + amount + timestamp + merchant_code)`.
3. **Prinsip Zero-PII**: Tidak ada nama tamu, nomor telepon, alamat email, atau detail identitas yang diunggah ke blockchain publik.
4. Proses pencatatan on-chain berjalan secara asinkron (background task) sehingga kegagalan jaringan RPC blockchain tidak membatalkan atau menunda reservasi kamar hotel.

### BR-04: Skema Loyalitas Token BEP-20 (ANV)
1. Setiap tamu yang berhasil menyelesaikan proses menginap (*Check-In Confirmed*), baik melalui pembayaran QRIS maupun Crypto, berhak memperoleh reward token loyalitas sebesar 5% dari total nilai transaksi (1 ANV = Rp 1.000 setara).
2. Tingkatan loyalitas (*Loyalty Tiers*):
   - **Tier New**: 0 - 99 ANV
   - **Tier Silver**: 100 - 499 ANV (Diskon booking 3%)
   - **Tier Gold**: 500 - 1.999 ANV (Diskon booking 5% + Free Early Check-In)
   - **Tier Platinum**: >= 2.000 ANV (Diskon booking 7% + Free Room Upgrade jika tersedia)
3. Anti Double-Reward: Satu nomor referensi booking (`booking_ref`) hanya dapat memicu pencetakan (*minting*) poin loyalitas sebanyak 1 kali.

---

## 5. KEPATUHAN HUKUM, REGULASI & KEAMANAN DATA

### 5.1 Kepatuhan UU Perlindungan Data Pribadi (UU PDP No. 27/2022)
* Seluruh data pribadi sensitif tamu (Nama, Nomor WhatsApp, KTP, Surat Nikah untuk pasangan Syariah) **hanya disimpan secara lokal** di database PostgreSQL terenkripsi dan SQLite internal.
* Blockchain publik (BNB Smart Chain) **hanya menyimpan hash satu arah** (`bytes32`), nilai nominal numerik, kode mata uang, dan tanda waktu Unix.

### 5.2 Kepatuhan Pembayaran Bank Indonesia & Bappebti
* Pembayaran mata uang Rupiah tetap menggunakan instrumen resmi berizin Bank Indonesia melalui Payment Gateway TriPay (QRIS & Virtual Account).
* Pembayaran aset kripto diperlakukan sebagai mekanisme jaminan komparatif / voucher layanan digital tertutup berbasis smart contract escrow demi memfasilitasi transaksi non-residen mancanegara.

---

## 6. METRIK KEBERHASILAN BISNIS (KPIs)

1. **Kecepatan Verifikasi Transaksi FO**: < 5 detik untuk membuktikan keaslian pembayaran via verifikasi on-chain.
2. **Tingkat Transaksi Gagal Rekonsiliasi**: Turun dari perkiraan 5-10% menjadi **0%** berkat audit trail independen di blockchain.
3. **Peningkatan Booking Tamu Mancanegara/Digital**: Peningkatan estimasi 15-25% pemesanan dari segmen pengguna aset digital.
4. **Tingkat Keterikatan Tamu (*Guest Retention*)**: Peningkatan *repeat booking* sebesar 20-30% dalam 6 bulan pertama implementasi program token loyalitas ANV.
5. **Reliabilitas Sistem**: Uptime 99.9% pada pemrosesan webhook WhatsApp dan gateway pembayaran.
