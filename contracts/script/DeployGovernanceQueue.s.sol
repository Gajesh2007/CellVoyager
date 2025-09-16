// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

import {Script} from "forge-std/Script.sol";
import {console2} from "forge-std/console2.sol";
import {GovernanceQueue} from "../src/GovernanceQueue.sol";
import {DonationSBT} from "../src/DonationSBT.sol";

contract DeployGovernanceQueue is Script {
    function run() external {
        address admin = vm.envOr("ADMIN", address(0));
        address agent = vm.envAddress("AGENT");
        address sbtAddr = vm.envAddress("SBT");
        string memory pubKey = vm.envString("PUBLIC_KEY");
        vm.startBroadcast();
        GovernanceQueue gq = new GovernanceQueue(admin, agent, DonationSBT(sbtAddr), pubKey);
        vm.stopBroadcast();
        console2.log("GovernanceQueue deployed at", address(gq));
    }
}


