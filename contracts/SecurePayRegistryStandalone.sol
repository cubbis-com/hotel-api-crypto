// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

/**
 * @title SecurePayRegistry
 * @notice Anvieo SecurePay - Blockchain Notary for Hotel Payment Hashes
 * @dev Records immutable payment receipts (QRIS, VA, USDT Escrow) on BNB Smart Chain.
 */
contract SecurePayRegistry {
    address public owner;
    
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

    mapping(bytes32 => TransactionRecord) public transactions;
    mapping(string => bytes32) public referenceToHash;
    mapping(bytes32 => bytes32[]) public bookingTransactions;
    bytes32[] public allTxHashes;
    mapping(address => bool) public authorizedCallers;

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

    event TransactionVerified(bytes32 indexed txHash, address verifiedBy);

    modifier onlyOwner() {
        require(msg.sender == owner, "Only owner");
        _;
    }

    modifier onlyAuthorized() {
        require(msg.sender == owner || authorizedCallers[msg.sender], "Not authorized");
        _;
    }

    constructor() {
        owner = msg.sender;
        authorizedCallers[msg.sender] = true;
    }

    function setAuthorizedCaller(address _caller, bool _status) external onlyOwner {
        authorizedCallers[_caller] = _status;
    }

    function recordTransaction(
        bytes32 _txHash,
        bytes32 _bookingRef,
        string calldata _reference,
        uint8 _paymentMethod,
        uint256 _amount,
        string calldata _currency
    ) external onlyAuthorized {
        require(transactions[_txHash].timestamp == 0, "Tx already recorded");
        require(_amount > 0, "Invalid amount");

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
        if (bytes(_reference).length > 0) {
            referenceToHash[_reference] = _txHash;
        }
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

    function verifyTransaction(bytes32 _txHash) external view returns (bool found, TransactionRecord memory record) {
        if (transactions[_txHash].timestamp == 0) {
            return (false, TransactionRecord(0, 0, "", 0, 0, "", 0, address(0), false, 0));
        }
        return (true, transactions[_txHash]);
    }

    function verifyByReference(string calldata _reference) external view returns (bool found, TransactionRecord memory record) {
        bytes32 txHash = referenceToHash[_reference];
        if (txHash == bytes32(0)) {
            return (false, TransactionRecord(0, 0, "", 0, 0, "", 0, address(0), false, 0));
        }
        return (true, transactions[txHash]);
    }

    function totalTransactions() external view returns (uint256) {
        return allTxHashes.length;
    }

    function getBookingTransactions(bytes32 _bookingRef) external view returns (bytes32[] memory) {
        return bookingTransactions[_bookingRef];
    }
}
