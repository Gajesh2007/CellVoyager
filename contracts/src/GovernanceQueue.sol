// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

import {Ownable} from "openzeppelin-contracts/contracts/access/Ownable.sol";
import {ReentrancyGuard} from "openzeppelin-contracts/contracts/utils/ReentrancyGuard.sol";
import {DonationSBT} from "./DonationSBT.sol";

/// @title GovernanceQueue
/// @notice Queue of research datasets that can be prioritized by holders of governance votes (DonationSBT).
/// @dev Users can bump a research's priority once every 24 hours. Owner manages authorized submitters and public key.
contract GovernanceQueue is Ownable, ReentrancyGuard {
    error NotAuthorized();
    error NotAgent();
    error CooldownActive(uint256 secondsRemaining);
    error InvalidResearch();
    error NoVotingPower();

    event PublicKeyUpdated(string oldKey, string newKey);
    event AuthorizedUpdated(address indexed account, bool authorized);
    event ResearchAdded(uint256 indexed id, address indexed submitter);
    event PriorityBumped(uint256 indexed id, address indexed voter, uint256 weight, uint256 newPriority);

    struct Research {
        // Metadata
        string analysisName;
        string description;
        string encryptedH5adPath; // client-side encrypted string
        string modelName;
        uint32 numAnalyses;
        uint32 maxIterations;

        // Admin/meta
        address submitter;
        uint64 createdAt;

        // Governance
        uint256 priority; // accumulated priority from votes
        uint256 totalVotes; // total weight applied
    }

    DonationSBT public immutable governanceToken;
    string public publicEncryptionKey; // Public key string used to encrypt dataset path off-chain
    address public immutable agent;

    modifier onlyAgent() {
        if (msg.sender != agent) revert NotAgent();
        _;
    }

    // Authorized dataset submitters
    mapping(address => bool) public isAuthorized;

    // Research storage
    Research[] private _researches;

    // Voter cooldown: global per-address 24h cooldown
    mapping(address => uint64) public lastBumpAt;
    uint64 public constant COOLDOWN_SECONDS = 24 hours;

    constructor(address initialOwner, address initialAgent,
    DonationSBT sbt, string memory initialPublicKey) Ownable(initialOwner == address(0) ? msg.sender : initialOwner) {
        governanceToken = sbt;
        publicEncryptionKey = initialPublicKey;
        agent = initialAgent;
    }

    // --- Admin ---
    function setPublicEncryptionKey(string calldata newKey) external onlyAgent {
        emit PublicKeyUpdated(publicEncryptionKey, newKey);
        publicEncryptionKey = newKey;
    }

    function setAuthorized(address account, bool authorized) external onlyAgent {
        isAuthorized[account] = authorized;
        emit AuthorizedUpdated(account, authorized);
    }

    // --- Submission ---
    function addResearch(
        string calldata analysisName,
        string calldata description,
        string calldata encryptedH5adPath,
        string calldata modelName,
        uint32 numAnalyses,
        uint32 maxIterations
    ) external nonReentrant returns (uint256 id) {
        if (!(msg.sender == owner() || isAuthorized[msg.sender])) revert NotAuthorized();

        Research memory r;
        r.analysisName = analysisName;
        r.description = description;
        r.encryptedH5adPath = encryptedH5adPath;
        r.modelName = modelName;
        r.numAnalyses = numAnalyses;
        r.maxIterations = maxIterations;
        r.submitter = msg.sender;
        r.createdAt = uint64(block.timestamp);
        r.priority = 0;
        r.totalVotes = 0;

        _researches.push(r);
        id = _researches.length - 1;
        emit ResearchAdded(id, msg.sender);
    }

    // --- Governance ---
    /// @notice Bump the priority of a research using your DonationSBT voting power; once per 24h per address.
    function bumpPriority(uint256 id) external nonReentrant {
        if (id >= _researches.length) revert InvalidResearch();

        uint64 last = lastBumpAt[msg.sender];
        uint64 nowTs = uint64(block.timestamp);
        if (last != 0 && nowTs - last < COOLDOWN_SECONDS) {
            revert CooldownActive(uint256(COOLDOWN_SECONDS) - (nowTs - last));
        }

        uint256 weight = governanceToken.balanceOf(msg.sender);
        if (weight == 0) revert NoVotingPower();

        Research storage r = _researches[id];
        r.priority += weight;
        r.totalVotes += weight;
        lastBumpAt[msg.sender] = nowTs;

        emit PriorityBumped(id, msg.sender, weight, r.priority);
    }

    // --- Views ---
    function getResearch(uint256 id) external view returns (Research memory) {
        if (id >= _researches.length) revert InvalidResearch();
        return _researches[id];
    }

    function researchCount() external view returns (uint256) {
        return _researches.length;
    }
}


