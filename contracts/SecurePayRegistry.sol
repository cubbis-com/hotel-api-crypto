// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

import "@openzeppelin/contracts/access/AccessControl.sol";

/**
 * @title SecurePayRegistry
 * @notice Registry untuk mencatat hash transaksi pembayaran hotel di blockchain.
 *         Mendukung QRIS, Virtual Account, dan Crypto payments.
 * @dev Setiap transaksi yang divalidasi oleh payment gateway 
 *      (TriPay) dicatat sebagai immutable record di blockchain.
 *      Ini adalah LAYER KEAMANAN yang bekerja di background.
 * @author Anvieo SecurePay
 * @version 1.0.0
 */
contract SecurePayRegistry is AccessControl {

    // ============================================================
    //  CONSTANTS
    // ============================================================

    bytes32 public constant BACKEND_ROLE = keccak256("BACKEND_ROLE");
    bytes32 public constant VERIFIER_ROLE = keccak256("VERIFIER_ROLE");

    // Payment methods
    uint8 public constant METHOD_QRIS = 0;
    uint8 public constant METHOD_VIRTUAL_ACCOUNT = 1;
    uint8 public constant METHOD_CRYPTO = 2;
    uint8 public constant METHOD_STABLECOIN = 3;

    // ============================================================
    //  STRUCTS
    // ============================================================

    struct TransactionRecord {
        bytes32 txHash;           // Hash unik dari transaksi
        bytes32 bookingRef;       // Referensi booking (link ke PMS)
        string reference;         // Reference dari payment gateway
        uint8 paymentMethod;      // 0=QRIS, 1=VA, 2=Crypto, 3=Stablecoin
        uint256 amount;           // Jumlah (dalam satuan terkecil)
        string currency;          // Mata uang (IDR, USDT, dll)
        uint256 timestamp;        // Waktu record (block.timestamp)
        address recordedBy;       // Siapa yang merekam
        bool verified;            // Status verifikasi
        uint256 blockNumber;      // Block number saat dicatat
    }

    // ============================================================
    //  STATE VARIABLES
    // ============================================================

    /// @notice Semua transaksi tersimpan di sini
    mapping(bytes32 => TransactionRecord) public transactions;

    /// @notice Lookup: reference string -> txHash bytes32
    mapping(string => bytes32) public referenceToHash;

    /// @notice Lookup: bookingRef -> list of txHash
    mapping(bytes32 => bytes32[]) public bookingTransactions;

    /// @notice Daftar semua txHash yang pernah dicatat
    bytes32[] public allTxHashes;

    /// @notice Hotel property ID untuk multi-tenant
    mapping(string => bytes32[]) public propertyTransactions;

    // ============================================================
    //  EVENTS
    // ============================================================

    event TransactionRecorded(
        bytes32 indexed txHash,
        bytes32 indexed bookingRef,
        string reference,
        uint8 paymentMethod,
        uint256 amount,
        string currency,
        address recordedBy,
        uint256 blockNumber
    );

    event TransactionVerified(
        bytes32 indexed txHash,
        address verifiedBy
    );

    event TransactionUpdated(
        bytes32 indexed txHash,
        bool newVerifiedStatus,
        address updatedBy
    );

    // ============================================================
    //  ERRORS
    // ============================================================

    error TxAlreadyRecorded(bytes32 txHash);
    error TxNotFound(bytes32 txHash);
    error ReferenceAlreadyUsed(string reference);
    error InvalidPaymentMethod(uint8 method);
    error InvalidAmount();

    // ============================================================
    //  MODIFIERS
    // ============================================================

    modifier txExists(bytes32 _txHash) {
        if (transactions[_txHash].timestamp == 0) {
            revert TxNotFound(_txHash);
        }
        _;
    }

    // ============================================================
    //  CONSTRUCTOR
    // ============================================================

    constructor(address _admin) {
        _grantRole(DEFAULT_ADMIN_ROLE, _admin);
        _grantRole(BACKEND_ROLE, _admin);
        _grantRole(VERIFIER_ROLE, _admin);
    }

    // ============================================================
    //  CORE FUNCTIONS
    // ============================================================

    /**
     * @notice Catat transaksi pembayaran sebagai hash on-chain
     * @dev Dipanggil oleh backend setelah callback payment gateway valid
     * @param _txHash Hash unik transaksi (keccak256 dari reference+timestamp)
     * @param _bookingRef Referensi booking dari PMS
     * @param _reference String reference dari payment gateway (contoh: "TRX-0012")
     * @param _paymentMethod Metode pembayaran (0=QRIS, 1=VA, 2=Crypto, 3=Stablecoin)
     * @param _amount Jumlah transaksi
     * @param _currency Mata uang (contoh: "IDR", "USDT")
     */
    function recordTransaction(
        bytes32 _txHash,
        bytes32 _bookingRef,
        string calldata _reference,
        uint8 _paymentMethod,
        uint256 _amount,
        string calldata _currency
    ) external onlyRole(BACKEND_ROLE) {
        if (transactions[_txHash].timestamp != 0) {
            revert TxAlreadyRecorded(_txHash);
        }

        if (keccak256(bytes(_reference)) != bytes32(0) && 
            referenceToHash[_reference] != bytes32(0)) {
            revert ReferenceAlreadyUsed(_reference);
        }

        if (_paymentMethod > METHOD_STABLECOIN) {
            revert InvalidPaymentMethod(_paymentMethod);
        }

        if (_amount == 0) {
            revert InvalidAmount();
        }

        TransactionRecord memory record = TransactionRecord({
            txHash: _txHash,
            bookingRef: _bookingRef,
            reference: _reference,
            paymentMethod: _paymentMethod,
            amount: _amount,
            currency: _currency,
            timestamp: block.timestamp,
            recordedBy: msg.sender,
            verified: true,
            blockNumber: block.number
        });

        transactions[_txHash] = record;
        referenceToHash[_reference] = _txHash;
        bookingTransactions[_bookingRef].push(_txHash);
        allTxHashes.push(_txHash);

        emit TransactionRecorded(
            _txHash,
            _bookingRef,
            _reference,
            _paymentMethod,
            _amount,
            _currency,
            msg.sender,
            block.number
        );
    }

    /**
     * @notice Verifikasi transaksi ada di blockchain
     * @param _txHash Hash transaksi yang ingin diverifikasi
     */
    function verifyTransaction(bytes32 _txHash) 
        external 
        view 
        returns (bool found, TransactionRecord memory record)
    {
        if (transactions[_txHash].timestamp == 0) {
            return (false, TransactionRecord(0, 0, "", 0, 0, "", 0, address(0), false, 0));
        }
        return (true, transactions[_txHash]);
    }

    /**
     * @notice Verifikasi transaksi berdasarkan reference string
     * @param _reference String reference dari payment gateway
     */
    function verifyByReference(string calldata _reference) 
        external 
        view 
        returns (bool found, TransactionRecord memory record)
    {
        bytes32 txHash = referenceToHash[_reference];
        if (txHash == bytes32(0)) {
            return (false, TransactionRecord(0, 0, "", 0, 0, "", 0, address(0), false, 0));
        }
        return (true, transactions[txHash]);
    }

    /**
     * @notice Dapatkan semua transaksi untuk satu booking
     * @param _bookingRef Referensi booking
     */
    function getBookingTransactions(bytes32 _bookingRef) 
        external 
        view 
        returns (bytes32[] memory)
    {
        return bookingTransactions[_bookingRef];
    }

    /**
     * @notice Dapatkan audit trail lengkap untuk satu booking
     * @param _bookingRef Referensi booking
     */
    function getAuditTrail(bytes32 _bookingRef) 
        external 
        view 
        returns (TransactionRecord[] memory)
    {
        bytes32[] storage txHashes = bookingTransactions[_bookingRef];
        TransactionRecord[] memory records = new TransactionRecord[](txHashes.length);

        for (uint256 i = 0; i < txHashes.length; i++) {
            records[i] = transactions[txHashes[i]];
        }

        return records;
    }

    /**
     * @notice Update status verifikasi transaksi
     * @param _txHash Hash transaksi
     * @param _verified Status baru (true/false)
     */
    function updateVerification(
        bytes32 _txHash, 
        bool _verified
    ) external onlyRole(VERIFIER_ROLE) txExists(_txHash) {
        transactions[_txHash].verified = _verified;
        emit TransactionUpdated(_txHash, _verified, msg.sender);
    }

    // ============================================================
    //  VIEW FUNCTIONS
    // ============================================================

    function totalTransactions() external view returns (uint256) {
        return allTxHashes.length;
    }

    function bookingTxCount(bytes32 _bookingRef) external view returns (uint256) {
        return bookingTransactions[_bookingRef].length;
    }

    function getTxHashAt(uint256 _index) external view returns (bytes32) {
        require(_index < allTxHashes.length, "Index out of bounds");
        return allTxHashes[_index];
    }

    function countByMethod(uint8 _paymentMethod) 
        external 
        view 
        returns (uint256 count)
    {
        for (uint256 i = 0; i < allTxHashes.length; i++) {
            if (transactions[allTxHashes[i]].paymentMethod == _paymentMethod) {
                count++;
            }
        }
    }
}
