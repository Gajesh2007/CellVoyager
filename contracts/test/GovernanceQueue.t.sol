// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

import "forge-std/Test.sol";
import {DonationSBT} from "../src/DonationSBT.sol";
import {GovernanceQueue} from "../src/GovernanceQueue.sol";

contract MockERC20 {
    string public name = "Mock";
    string public symbol = "MOCK";
    uint8 public decimals = 18;
    mapping(address => uint256) public balanceOf;
    mapping(address => mapping(address => uint256)) public allowance;

    event Transfer(address indexed from, address indexed to, uint256 value);
    event Approval(address indexed owner, address indexed spender, uint256 value);

    function mint(address to, uint256 amount) external {
        balanceOf[to] += amount;
        emit Transfer(address(0), to, amount);
    }

    function approve(address spender, uint256 value) external returns (bool) {
        allowance[msg.sender][spender] = value;
        emit Approval(msg.sender, spender, value);
        return true;
    }

    function transferFrom(address from, address to, uint256 value) external returns (bool) {
        uint256 allowed = allowance[from][msg.sender];
        require(allowed >= value, "allowance");
        require(balanceOf[from] >= value, "balance");
        allowance[from][msg.sender] = allowed - value;
        balanceOf[from] -= value;
        balanceOf[to] += value;
        emit Transfer(from, to, value);
        return true;
    }
}

contract GovernanceQueueTest is Test {
    DonationSBT sbt;
    GovernanceQueue gq;
    MockERC20 token;

    address admin = address(0xA11CE);
    address user1 = address(0xBEEF);
    address user2 = address(0xCAFE);

    function setUp() public {
        vm.startPrank(admin);
        sbt = new DonationSBT(admin);
        gq = new GovernanceQueue(admin, admin, sbt, "PUB_KEY");
        vm.stopPrank();

        token = new MockERC20();
        vm.prank(admin);
        sbt.setWhitelist(address(token), true, 1e18);

        token.mint(user1, 100 ether);
        token.mint(user2, 50 ether);
        vm.startPrank(user1);
        token.approve(address(sbt), type(uint256).max);
        sbt.donate(address(token), 100 ether);
        vm.stopPrank();

        vm.startPrank(user2);
        token.approve(address(sbt), type(uint256).max);
        sbt.donate(address(token), 50 ether);
        vm.stopPrank();
    }

    function testOwnerOrAuthorizedCanAdd() public {
        vm.prank(admin);
        uint256 id = gq.addResearch("A", "desc", "enc", "o3-mini", 8, 6);
        assertEq(id, 0);

        address auth = address(0x1234);
        vm.prank(admin);
        gq.setAuthorized(auth, true);

        vm.prank(auth);
        uint256 id2 = gq.addResearch("B", "desc2", "enc2", "gpt-4o", 5, 3);
        assertEq(id2, 1);
    }

    function testBumpPriorityRespectsCooldownAndWeight() public {
        vm.prank(admin);
        uint256 id = gq.addResearch("A", "desc", "enc", "o3-mini", 8, 6);

        // user1 votes (100), then user2 votes (50)
        vm.prank(user1);
        gq.bumpPriority(id);
        GovernanceQueue.Research memory r = gq.getResearch(id);
        assertEq(r.priority, 100 ether);
        assertEq(r.totalVotes, 100 ether);

        vm.prank(user2);
        gq.bumpPriority(id);
        r = gq.getResearch(id);
        assertEq(r.priority, 150 ether);
        assertEq(r.totalVotes, 150 ether);

        // user1 cannot vote again within 24h
        vm.prank(user1);
        vm.expectRevert();
        gq.bumpPriority(id);

        // warp by one day, then user1 can vote again
        vm.warp(block.timestamp + 1 days);
        vm.prank(user1);
        gq.bumpPriority(id);
        r = gq.getResearch(id);
        assertEq(r.priority, 250 ether);
        assertEq(r.totalVotes, 250 ether);
    }

    function testUpdatePublicKey() public {
        vm.prank(admin);
        gq.setPublicEncryptionKey("NEW_KEY");
        assertEq(gq.publicEncryptionKey(), "NEW_KEY");
    }
}


