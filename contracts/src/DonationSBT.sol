// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

import {Ownable} from "openzeppelin-contracts/contracts/access/Ownable.sol";
import {ReentrancyGuard} from "openzeppelin-contracts/contracts/utils/ReentrancyGuard.sol";
import {IERC20} from "openzeppelin-contracts/contracts/token/ERC20/IERC20.sol";
import {SafeERC20} from "openzeppelin-contracts/contracts/token/ERC20/utils/SafeERC20.sol";

/// @title DonationSBT - Soulbound voting receipt for donations
/// @notice Users donate whitelisted ERC20 tokens and receive non-transferable voting units based on token-specific rates.
/// @dev Not an ERC20. Tracks balances internally and forbids transfers. Supports owner-managed whitelist and rates.
contract DonationSBT is Ownable, ReentrancyGuard {
    using SafeERC20 for IERC20;

    error NotWhitelisted(address token);
    error TransferDisabled();
    error ZeroAmount();

    event Donated(address indexed donor, address indexed token, uint256 tokenAmount, uint256 votesMinted);
    event WhitelistUpdated(address indexed token, bool allowed, uint256 rate);

    // token -> allowed
    mapping(address => bool) public isWhitelisted;
    // token -> votes per 1 token unit (fixed-point 1e18 scale for precision)
    mapping(address => uint256) public voteRatePerToken;

    // user -> votes (1e18 precision)
    mapping(address => uint256) private _balance;
    uint256 private _totalSupply;

    // user => token => total donated token amount (raw token units)
    mapping(address => mapping(address => uint256)) public donatedAmount;

    // user => token => votes minted from that token (1e18 precision)
    mapping(address => mapping(address => uint256)) public votesFromToken;

    constructor(address initialOwner) Ownable(initialOwner == address(0) ? msg.sender : initialOwner) {}

    /// @notice Set or update a token whitelist status and vote rate.
    /// @param token ERC20 token address
    /// @param allowed Whether donations are accepted
    /// @param rate Votes minted per 1.0 token donated, scaled by 1e18
    function setWhitelist(address token, bool allowed, uint256 rate) external onlyOwner {
        isWhitelisted[token] = allowed;
        voteRatePerToken[token] = rate;
        emit WhitelistUpdated(token, allowed, rate);
    }

    /// @notice Donate a whitelisted token and mint soulbound votes to the caller.
    /// @dev Requires prior ERC20 allowance to this contract.
    /// @param token Whitelisted ERC20 token
    /// @param amount Token amount to donate (in token's decimals)
    function donate(address token, uint256 amount) external nonReentrant {
        if (!isWhitelisted[token]) revert NotWhitelisted(token);
        if (amount == 0) revert ZeroAmount();

        // Pull tokens safely
        IERC20(token).safeTransferFrom(msg.sender, address(this), amount);

        // Compute votes = amount * rate / 1e18
        uint256 votes = (amount * voteRatePerToken[token]) / 1e18;

        // Track per-token totals for view functions/analytics
        donatedAmount[msg.sender][token] += amount;
        votesFromToken[msg.sender][token] += votes;

        _mint(msg.sender, votes);
        emit Donated(msg.sender, token, amount, votes);
    }

    /// @notice View functions
    function balanceOf(address account) external view returns (uint256) { return _balance[account]; }
    function totalSupply() external view returns (uint256) { return _totalSupply; }

    /// @notice Transfer is disabled to keep votes soulbound
    function transfer(address, uint256) external pure returns (bool) { revert TransferDisabled(); }
    function approve(address, uint256) external pure returns (bool) { revert TransferDisabled(); }
    function transferFrom(address, address, uint256) external pure returns (bool) { revert TransferDisabled(); }

    function _mint(address to, uint256 amount) internal {
        _totalSupply += amount;
        _balance[to] += amount;
    }
}


