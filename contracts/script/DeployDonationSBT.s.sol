// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

import {Script} from "forge-std/Script.sol";
import {console2} from "forge-std/console2.sol";
import {DonationSBT} from "../src/DonationSBT.sol";

contract DeployDonationSBT is Script {
    function run() external {
        address admin = vm.envOr("ADMIN", address(0));
        vm.startBroadcast();
        DonationSBT sbt = new DonationSBT(admin);
        vm.stopBroadcast();
        console2.log("DonationSBT deployed at", address(sbt));
    }
}


