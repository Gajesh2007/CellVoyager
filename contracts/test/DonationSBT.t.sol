// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

import "forge-std/Test.sol";
import {DonationSBT} from "../src/DonationSBT.sol";
import {IERC20} from "openzeppelin-contracts/contracts/token/ERC20/IERC20.sol";

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

contract DonationSBTTest is Test {
    DonationSBT sbt;
    MockERC20 tokenA;
    address admin = address(0xA11CE);
    address user = address(0xBEEF);

    function setUp() public {
        vm.prank(admin);
        sbt = new DonationSBT(admin);
        tokenA = new MockERC20();

        // whitelist tokenA with rate 1e18 votes per token unit
        vm.prank(admin);
        sbt.setWhitelist(address(tokenA), true, 1e18);

        tokenA.mint(user, 1_000 ether);
    }

    function testDonateMintsVotes() public {
        vm.startPrank(user);
        tokenA.approve(address(sbt), 100 ether);
        sbt.donate(address(tokenA), 100 ether);
        vm.stopPrank();

        // votes = amount * rate / 1e18 = 100 ether * 1e18 / 1e18 = 100 ether
        assertEq(sbt.totalSupply(), 100 ether);
        assertEq(sbt.balanceOf(user), 100 ether);
    }

    function testNonTransferable() public {
        vm.startPrank(user);
        tokenA.approve(address(sbt), 1 ether);
        sbt.donate(address(tokenA), 1 ether);
        vm.stopPrank();

        vm.expectRevert(DonationSBT.TransferDisabled.selector);
        sbt.transfer(address(1), 1);

        vm.expectRevert(DonationSBT.TransferDisabled.selector);
        sbt.approve(address(1), 1);

        vm.expectRevert(DonationSBT.TransferDisabled.selector);
        sbt.transferFrom(user, address(1), 1);
    }

    function testNotWhitelistedReverts() public {
        MockERC20 tokenB = new MockERC20();
        tokenB.mint(user, 10 ether);
        vm.startPrank(user);
        tokenB.approve(address(sbt), 10 ether);
        vm.expectRevert(abi.encodeWithSelector(DonationSBT.NotWhitelisted.selector, address(tokenB)));
        sbt.donate(address(tokenB), 10 ether);
        vm.stopPrank();
    }

    function testOnlyAdminCanWhitelist() public {
        vm.prank(user);
        vm.expectRevert();
        sbt.setWhitelist(address(0x1234), true, 1);
    }
}


