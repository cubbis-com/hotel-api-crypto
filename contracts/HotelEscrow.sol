// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

import "@openzeppelin/contracts/token/ERC20/IERC20.sol";
import "@openzeppelin/contracts/token/ERC20/utils/SafeERC20.sol";
import "@openzeppelin/contracts/access/Ownable.sol";
import "@openzeppelin/contracts/utils/ReentrancyGuard.sol";

/**
 * @title HotelEscrow
 * @notice Smart contract untuk escrow pembayaran hotel di BNB Smart Chain
 * @dev Dana tamu di-hold sampai check-in terkonfirmasi oleh hotel.
 *      Refund otomatis jika booking dibatalkan.
 * @author Anvieo SecurePay
 * @version 1.0.0
 */
contract HotelEscrow is Ownable, ReentrancyGuard {
    using SafeERC20 for IERC20;

    // ============================================================
    //  ENUMS & STRUCTS
    // ============================================================

    enum BookingStatus {
        None,        // 0: Tidak ada
        Created,     // 1: Escrow dibuat, menunggu pembayaran
        Funded,      // 2: Tamu sudah bayar, dana di-hold
        Confirmed,   // 3: Check-in terkonfirmasi, dana dilepas
        Refunded,    // 4: Dibatalkan, dana dikembalikan
        Disputed,    // 5: Sengketa, dana freeze
        Expired      // 6: Kadaluarsa, dana dikembalikan
    }

    struct Booking {
        address guest;           // Wallet tamu
        address hotel;           // Wallet hotel (penerima dana)
        uint256 amount;          // Jumlah dalam token (USDT)
        uint256 checkinTimestamp; // Waktu check-in (Unix timestamp)
        uint256 createdAt;       // Waktu pembuatan escrow
        BookingStatus status;    // Status escrow
        bytes32 bookingRef;      // Referensi dari sistem PMS
        bool funded;             // Sudah dibayar atau belum
        bool refunded;           // Sudah di-refund atau belum
        uint256 paidAmount;      // Jumlah yang benar-benar dibayar
    }

    // ============================================================
    //  STATE VARIABLES
    // ============================================================

    /// @notice Token stablecoin yang digunakan (USDT)
    IERC20 public immutable paymentToken;

    /// @notice Semua booking tersimpan di sini
    mapping(bytes32 => Booking) public bookings;

    /// @notice Escrow timeout dalam detik (default 30 menit)
    uint256 public escrowTimeout = 30 minutes;

    /// @notice Admin wallet untuk dispute resolution
    address public admin;

    /// @notice Daftar semua booking references
    bytes32[] public bookingRefs;

    // ============================================================
    //  EVENTS
    // ============================================================

    event BookingCreated(
        bytes32 indexed bookingRef,
        address indexed guest,
        address indexed hotel,
        uint256 amount,
        uint256 checkinTimestamp
    );

    event BookingFunded(
        bytes32 indexed bookingRef,
        address indexed guest,
        uint256 paidAmount
    );

    event BookingConfirmed(
        bytes32 indexed bookingRef,
        address indexed hotel,
        uint256 releasedAmount
    );

    event BookingRefunded(
        bytes32 indexed bookingRef,
        address indexed guest,
        uint256 refundedAmount
    );

    event BookingDisputed(
        bytes32 indexed bookingRef,
        address indexed raisedBy,
        string reason
    );

    event BookingExpired(
        bytes32 indexed bookingRef,
        uint256 expiredAt
    );

    event EscrowTimeoutUpdated(uint256 oldTimeout, uint256 newTimeout);

    // ============================================================
    //  ERRORS
    // ============================================================

    error BookingAlreadyExists(bytes32 bookingRef);
    error BookingNotFound(bytes32 bookingRef);
    error InvalidStatus(BookingStatus expected, BookingStatus actual);
    error NotEnoughTimeToExpire();
    error AmountExceedsRequired(uint256 sent, uint256 required);
    error OnlyAdmin();
    error OnlyGuestOrHotel();
    error InsufficientBalance();

    // ============================================================
    //  MODIFIERS
    // ============================================================

    modifier onlyAdmin() {
        if (msg.sender != admin) revert OnlyAdmin();
        _;
    }

    modifier bookingExists(bytes32 _bookingRef) {
        if (bookings[_bookingRef].status == BookingStatus.None) {
            revert BookingNotFound(_bookingRef);
        }
        _;
    }

    modifier requireStatus(bytes32 _bookingRef, BookingStatus _status) {
        Booking storage b = bookings[_bookingRef];
        if (b.status != _status) {
            revert InvalidStatus(_status, b.status);
        }
        _;
    }

    // ============================================================
    //  CONSTRUCTOR
    // ============================================================

    /**
     * @param _paymentToken Address token stablecoin (USDT di BSC Testnet)
     * @param _admin Address admin untuk dispute resolution
     */
    constructor(address _paymentToken, address _admin) Ownable(msg.sender) {
        paymentToken = IERC20(_paymentToken);
        admin = _admin;
        emit EscrowTimeoutUpdated(0, escrowTimeout);
    }

    // ============================================================
    //  CORE FUNCTIONS
    // ============================================================

    /**
     * @notice Buat escrow baru untuk reservasi hotel
     * @dev Dipanggil oleh backend (operator)
     * @param _bookingRef Referensi booking dari PMS (bytes32)
     * @param _guest Wallet address tamu
     * @param _hotel Wallet address hotel (penerima dana)
     * @param _amount Jumlah pembayaran dalam token
     * @param _checkinTimestamp Waktu check-in (Unix timestamp)
     */
    function createBooking(
        bytes32 _bookingRef,
        address _guest,
        address _hotel,
        uint256 _amount,
        uint256 _checkinTimestamp
    ) external onlyAdmin {
        if (bookings[_bookingRef].status != BookingStatus.None) {
            revert BookingAlreadyExists(_bookingRef);
        }

        require(_guest != address(0), "Invalid guest address");
        require(_hotel != address(0), "Invalid hotel address");
        require(_amount > 0, "Amount must be > 0");

        bookings[_bookingRef] = Booking({
            guest: _guest,
            hotel: _hotel,
            amount: _amount,
            checkinTimestamp: _checkinTimestamp,
            createdAt: block.timestamp,
            status: BookingStatus.Created,
            bookingRef: _bookingRef,
            funded: false,
            refunded: false,
            paidAmount: 0
        });

        bookingRefs.push(_bookingRef);

        emit BookingCreated(
            _bookingRef, _guest, _hotel, _amount, _checkinTimestamp
        );
    }

    /**
     * @notice Tamu membiayai escrow (mengirim token ke contract)
     * @dev Tamu harus approve contract terlebih dahulu
     * @param _bookingRef Referensi booking
     * @param _amount Jumlah token yang dikirim
     */
    function fundBooking(bytes32 _bookingRef, uint256 _amount) 
        external 
        nonReentrant
        bookingExists(_bookingRef)
        requireStatus(_bookingRef, BookingStatus.Created)
    {
        Booking storage booking = bookings[_bookingRef];

        if (msg.sender != booking.guest) revert OnlyGuestOrHotel();

        if (_amount < booking.amount) {
            revert AmountExceedsRequired(booking.amount, _amount);
        }

        paymentToken.safeTransferFrom(msg.sender, address(this), _amount);

        booking.status = BookingStatus.Funded;
        booking.funded = true;
        booking.paidAmount = _amount;

        emit BookingFunded(_bookingRef, msg.sender, _amount);

        if (_amount > booking.amount) {
            uint256 excess = _amount - booking.amount;
            paymentToken.safeTransfer(msg.sender, excess);
        }
    }

    /**
     * @notice Konfirmasi check-in -> dana dilepas ke hotel
     * @dev Dipanggil oleh admin (backend) setelah FO konfirmasi check-in
     * @param _bookingRef Referensi booking
     */
    function confirmCheckin(bytes32 _bookingRef) 
        external 
        onlyAdmin 
        nonReentrant
        bookingExists(_bookingRef)
        requireStatus(_bookingRef, BookingStatus.Funded)
    {
        Booking storage booking = bookings[_bookingRef];

        booking.status = BookingStatus.Confirmed;

        uint256 amount = booking.paidAmount;
        paymentToken.safeTransfer(booking.hotel, amount);

        emit BookingConfirmed(_bookingRef, booking.hotel, amount);
    }

    /**
     * @notice Batalkan booking -> refund otomatis ke tamu
     * @dev Bisa dipanggil tamu (jika sebelum check-in) atau admin
     * @param _bookingRef Referensi booking
     */
    function cancelBooking(bytes32 _bookingRef) 
        external 
        nonReentrant
        bookingExists(_bookingRef)
        requireStatus(_bookingRef, BookingStatus.Funded)
    {
        Booking storage booking = bookings[_bookingRef];

        if (msg.sender != booking.guest && msg.sender != admin) {
            revert OnlyGuestOrHotel();
        }

        booking.status = BookingStatus.Refunded;
        booking.refunded = true;

        uint256 amount = booking.paidAmount;
        paymentToken.safeTransfer(booking.guest, amount);

        emit BookingRefunded(_bookingRef, booking.guest, amount);
    }

    /**
     * @notice Ajukan sengketa -> escrow di-freeze
     * @dev Dana tetap di contract sampai admin resolve
     * @param _bookingRef Referensi booking
     * @param _reason Alasan sengketa
     */
    function disputeBooking(bytes32 _bookingRef, string calldata _reason) 
        external
        bookingExists(_bookingRef)
    {
        Booking storage booking = bookings[_bookingRef];

        if (msg.sender != booking.guest && 
            msg.sender != booking.hotel && 
            msg.sender != admin) {
            revert OnlyGuestOrHotel();
        }

        if (booking.status != BookingStatus.Funded) {
            revert InvalidStatus(BookingStatus.Funded, booking.status);
        }

        booking.status = BookingStatus.Disputed;

        emit BookingDisputed(_bookingRef, msg.sender, _reason);
    }

    /**
     * @notice Admin resolve dispute -> release ke hotel atau refund ke tamu
     * @param _bookingRef Referensi booking
     * @param _releaseToHotel true = dana ke hotel, false = refund ke tamu
     */
    function resolveDispute(bytes32 _bookingRef, bool _releaseToHotel) 
        external 
        onlyAdmin
        nonReentrant
        bookingExists(_bookingRef)
        requireStatus(_bookingRef, BookingStatus.Disputed)
    {
        Booking storage booking = bookings[_bookingRef];
        uint256 amount = booking.paidAmount;

        if (_releaseToHotel) {
            booking.status = BookingStatus.Confirmed;
            paymentToken.safeTransfer(booking.hotel, amount);
            emit BookingConfirmed(_bookingRef, booking.hotel, amount);
        } else {
            booking.status = BookingStatus.Refunded;
            booking.refunded = true;
            paymentToken.safeTransfer(booking.guest, amount);
            emit BookingRefunded(_bookingRef, booking.guest, amount);
        }
    }

    /**
     * @notice Expire escrow jika tamu tidak bayar dalam batas waktu
     * @param _bookingRef Referensi booking
     */
    function expireBooking(bytes32 _bookingRef) 
        external
        bookingExists(_bookingRef)
        requireStatus(_bookingRef, BookingStatus.Created)
    {
        Booking storage booking = bookings[_bookingRef];

        if (block.timestamp < booking.createdAt + escrowTimeout) {
            revert NotEnoughTimeToExpire();
        }

        booking.status = BookingStatus.Expired;

        emit BookingExpired(_bookingRef, block.timestamp);
    }

    // ============================================================
    //  VIEW FUNCTIONS
    // ============================================================

    function getBooking(bytes32 _bookingRef) 
        external 
        view 
        bookingExists(_bookingRef)
        returns (Booking memory)
    {
        return bookings[_bookingRef];
    }

    function canExpire(bytes32 _bookingRef) 
        external 
        view 
        bookingExists(_bookingRef)
        returns (bool)
    {
        Booking storage booking = bookings[_bookingRef];
        return (
            booking.status == BookingStatus.Created &&
            block.timestamp >= booking.createdAt + escrowTimeout
        );
    }

    function totalBookings() external view returns (uint256) {
        return bookingRefs.length;
    }

    function escrowBalance() external view returns (uint256) {
        return paymentToken.balanceOf(address(this));
    }

    // ============================================================
    //  ADMIN FUNCTIONS
    // ============================================================

    function setEscrowTimeout(uint256 _newTimeout) external onlyAdmin {
        emit EscrowTimeoutUpdated(escrowTimeout, _newTimeout);
        escrowTimeout = _newTimeout;
    }

    function setAdmin(address _newAdmin) external onlyOwner {
        require(_newAdmin != address(0), "Invalid admin address");
        admin = _newAdmin;
    }

    function emergencyWithdraw(address _token, uint256 _amount) 
        external 
        onlyOwner 
        nonReentrant
    {
        IERC20(_token).safeTransfer(owner(), _amount);
    }

    receive() external payable {
        revert("Use token payment, not ETH");
    }
}
