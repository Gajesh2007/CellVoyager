// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

import {Script} from "forge-std/Script.sol";
import {console2} from "forge-std/console2.sol";
import {DonationSBT} from "../src/DonationSBT.sol";
import {GovernanceQueue} from "../src/GovernanceQueue.sol";
import {MockERC20} from "../src/MockERC20.sol";

contract DeployAll is Script {
    function run() external {
        string memory pubKey = vm.envString("PUBLIC_KEY");
        address agent = vm.envAddress("AGENT");

        vm.startBroadcast();

        // Deployer is admin
        address admin = msg.sender;

        DonationSBT sbt = new DonationSBT(admin);
        console2.log("DonationSBT:", address(sbt));

        // GovernanceQueue with distinct agent address
        require(agent != address(0), "Invalid AGENT env (must be non-zero and != admin)");
        GovernanceQueue gq = new GovernanceQueue(admin, agent, sbt, pubKey);
        console2.log("GovernanceQueue:", address(gq));

        // Deploy mock token and mint 100k to admin
        uint256 initial = 100_000 ether; // 18 decimals
        MockERC20 mock = new MockERC20("MockToken", "MOCK", initial, admin);
        console2.log("MockERC20:", address(mock));

        // Whitelist mock token with 1e18 vote rate
        sbt.setWhitelist(address(mock), true, 1e18);

        vm.stopBroadcast();
    }
}


