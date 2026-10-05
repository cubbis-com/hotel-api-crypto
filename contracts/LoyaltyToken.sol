// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

import "@openzeppelin/contracts/token/ERC20/ERC20.sol";
import "@openzeppelin/contracts/access/AccessControl.sol";
import "@openzeppelin/contracts/token/ERC20/extensions/ERC20Burnable.sol";

/**
 * @title LoyaltyToken (ANV)
 * @notice Token loyalty BEP-20 untuk program reward tamu hotel Anvieo.
 *         Tamu mendapat poin setelah check-in, bisa ditukarkan 
 *         untuk cashback booking berikutnya.
 * @dev Deployed di BSC Testnet -> BSC Mainnet -> opBNB (microtx)
 * @author Anvieo SecurePay
 * @version 1.0.0
 */
contract LoyaltyToken is ERC20, ERC20Burnable, AccessControl {

    // ============================================================
    //  CONSTANTS
    // ============================================================

    bytes32 public constant MINTER_ROLE = keccak256("MINTER_ROLE");
    bytes32 public constant BURNER_ROLE = keccak256("BURNER_ROLE");

    // Tier thresholds (dalam ANV)
    uint256 public constant TIER_SILVER = 100;
    uint256 public constant TIER_GOLD = 500;
    uint256 public constant TIER_PLATINUM = 2000;

    // ============================================================
    //  ENUMS & STRUCTS
    // ============================================================

    enum Tier {
        None,       // 0: Belum ada poin
        Silver,     // 1: 100-499 ANV
        Gold,       // 2: 500-1999 ANV
        Platinum    // 3: 2000+ ANV
    }

    struct MemberInfo {
        uint256 totalEarned;     // Total poin pernah didapat
        uint256 totalRedeemed;   // Total poin pernah ditukarkan
        uint256 bookingCount;    // Jumlah booking
        uint256 firstBookingAt;  // Timestamp booking pertama
        Tier tier;               // Tier saat ini
        string phone;            // Nomor WhatsApp (link ke sistem PMS)
    }

    // ============================================================
    //  STATE VARIABLES
    // ============================================================

    /// @notice Info setiap member
    mapping(address => MemberInfo) public members;

    /// @notice Lookup: phone number -> wallet address
    mapping(string => address) public phoneToWallet;

    /// @notice Daftar semua member
    address[] public allMembers;

    /// @notice Total poin yang pernah di-mint
    uint256 public totalMinted;

    /// @notice Total poin yang pernah di-redeem
    uint256 public totalRedeemed;

    /// @notice Booking references yang sudah dapat poin (anti double-mint)
    mapping(bytes32 => bool) public pointsAwardedFor;

    // ============================================================
    //  EVENTS
    // ============================================================

    event PointsMinted(
        address indexed account,
        uint256 amount,
        bytes32 indexed bookingRef,
        string reason
    );

    event PointsRedeemed(
        address indexed account,
        uint256 amount,
        bytes32 indexed bookingRef,
        string purpose
    );

    event TierUpgraded(
        address indexed account,
        Tier oldTier,
        Tier newTier
    );

    event MemberRegistered(
        address indexed wallet,
        string phone
    );

    event PointsAwarded(
        address indexed account,
        uint256 amount,
        string actionType
    );

    // ============================================================
    //  ERRORS
    // ============================================================

    error AlreadyAwarded(bytes32 bookingRef);
    error NotRegistered(address wallet);
    error InsufficientPoints(uint256 requested, uint256 available);
    error PhoneAlreadyRegistered(string phone);

    // ============================================================
    //  CONSTRUCTOR
    // ============================================================

    constructor(address _admin) ERC20("Anvieo Points", "ANV") {
        _grantRole(DEFAULT_ADMIN_ROLE, _admin);
        _grantRole(MINTER_ROLE, _admin);
        _grantRole(BURNER_ROLE, _admin);
    }

    function decimals() public pure override returns (uint8) {
        return 0;
    }

    // ============================================================
    //  INTERNAL HELPERS
    // ============================================================

    function _calculateTier(uint256 balance) internal pure returns (Tier) {
        if (balance >= TIER_PLATINUM) {
            return Tier.Platinum;
        } else if (balance >= TIER_GOLD) {
            return Tier.Gold;
        } else if (balance >= TIER_SILVER) {
            return Tier.Silver;
        } else {
            return Tier.None;
        }
    }

    // ============================================================
    //  CORE FUNCTIONS: REGISTER & AWARD
    // ============================================================

    function registerMember(address _wallet, string calldata _phone) 
        external 
        onlyRole(MINTER_ROLE) 
    {
        if (members[_wallet].firstBookingAt != 0) {
            return;
        }

        if (bytes(_phone).length > 0 && phoneToWallet[_phone] != address(0)) {
            revert PhoneAlreadyRegistered(_phone);
        }

        members[_wallet] = MemberInfo({
            totalEarned: 0,
            totalRedeemed: 0,
            bookingCount: 0,
            firstBookingAt: block.timestamp,
            tier: Tier.None,
            phone: _phone
        });

        if (bytes(_phone).length > 0) {
            phoneToWallet[_phone] = _wallet;
        }
        allMembers.push(_wallet);

        emit MemberRegistered(_wallet, _phone);
    }

    function awardPoints(
        address _account,
        uint256 _amount,
        bytes32 _bookingRef,
        string calldata _reason
    ) external onlyRole(MINTER_ROLE) {
        if (_bookingRef != bytes32(0) && pointsAwardedFor[_bookingRef]) {
            revert AlreadyAwarded(_bookingRef);
        }

        require(_account != address(0), "Invalid account");
        require(_amount > 0, "Amount must be > 0");

        if (members[_account].firstBookingAt == 0) {
            members[_account] = MemberInfo({
                totalEarned: 0,
                totalRedeemed: 0,
                bookingCount: 0,
                firstBookingAt: block.timestamp,
                tier: Tier.None,
                phone: ""
            });
            allMembers.push(_account);
        }

        if (_bookingRef != bytes32(0)) {
            pointsAwardedFor[_bookingRef] = true;
        }

        MemberInfo storage member = members[_account];
        member.totalEarned += _amount;
        member.bookingCount += 1;

        Tier oldTier = member.tier;
        Tier newTier = _calculateTier(balanceOf(_account) + _amount);

        if (newTier > oldTier) {
            member.tier = newTier;
            emit TierUpgraded(_account, oldTier, newTier);
        }

        totalMinted += _amount;
        _mint(_account, _amount);

        emit PointsMinted(_account, _amount, _bookingRef, _reason);
        emit PointsAwarded(_account, _amount, _reason);
    }

    function awardActionPoints(
        address _account,
        uint256 _amount,
        string calldata _actionType
    ) external onlyRole(MINTER_ROLE) {
        require(_account != address(0), "Invalid account");
        require(_amount > 0, "Amount must be > 0");

        if (members[_account].firstBookingAt == 0) {
            members[_account] = MemberInfo({
                totalEarned: 0,
                totalRedeemed: 0,
                bookingCount: 0,
                firstBookingAt: block.timestamp,
                tier: Tier.None,
                phone: ""
            });
            allMembers.push(_account);
        }

        members[_account].totalEarned += _amount;

        Tier oldTier = members[_account].tier;
        Tier newTier = _calculateTier(balanceOf(_account) + _amount);
        if (newTier > oldTier) {
            members[_account].tier = newTier;
            emit TierUpgraded(_account, oldTier, newTier);
        }

        totalMinted += _amount;
        _mint(_account, _amount);

        emit PointsAwarded(_account, _amount, _actionType);
    }

    function redeemPoints(
        uint256 _amount,
        bytes32 _bookingRef
    ) external {
        if (members[msg.sender].firstBookingAt == 0) {
            revert NotRegistered(msg.sender);
        }

        uint256 balance = balanceOf(msg.sender);
        if (_amount > balance) {
            revert InsufficientPoints(_amount, balance);
        }

        members[msg.sender].totalRedeemed += _amount;
        totalRedeemed += _amount;

        _burn(msg.sender, _amount);

        emit PointsRedeemed(msg.sender, _amount, _bookingRef, "BOOKING_CASHBACK");
    }

    // ============================================================
    //  VIEW FUNCTIONS
    // ============================================================

    function getTier(address _account) external view returns (Tier) {
        uint256 balance = balanceOf(_account);
        return _calculateTier(balance);
    }

    function getMemberTier(address _account) external view returns (Tier) {
        return members[_account].tier;
    }

    function hasBeenAwarded(bytes32 _bookingRef) external view returns (bool) {
        return pointsAwardedFor[_bookingRef];
    }

    function getMemberInfo(address _account) 
        external 
        view 
        returns (MemberInfo memory)
    {
        return members[_account];
    }

    function getWalletByPhone(string calldata _phone) 
        external 
        view 
        returns (address)
    {
        return phoneToWallet[_phone];
    }

    function totalMembers() external view returns (uint256) {
        return allMembers.length;
    }
}
