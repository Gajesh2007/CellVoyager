import json
import os
from typing import Any, Dict, List, Optional

from web3 import Web3
from web3.middleware import geth_poa_middleware


def connect_web3(rpc_url: str) -> Web3:
    w3 = Web3(Web3.HTTPProvider(rpc_url, request_kwargs={"timeout": 30}))
    try:
        w3.middleware_onion.inject(geth_poa_middleware, layer=0)
    except Exception:
        pass
    if not w3.is_connected():
        raise RuntimeError(f"Failed to connect to RPC {rpc_url}")
    return w3


def load_contract_abi(abi_path: Optional[str]) -> List[Dict[str, Any]]:
    if abi_path:
        try:
            with open(abi_path, "r") as f:
                data = json.load(f)
            if isinstance(data, dict) and "abi" in data:
                return data["abi"]
        except Exception:
            pass

    default_path = os.path.join(
        os.path.dirname(os.path.dirname(__file__)),
        "contracts",
        "out",
        "GovernanceQueue.sol",
        "GovernanceQueue.json",
    )
    try:
        with open(default_path, "r") as f:
            data = json.load(f)
        if isinstance(data, dict) and "abi" in data:
            print(f"Loaded ABI from artifact: {default_path}")
            return data["abi"]
    except Exception:
        pass

    raise RuntimeError(
        "Failed to load GovernanceQueue ABI. Provide --abi-path or ensure artifact exists at "
        "contracts/out/GovernanceQueue.sol/GovernanceQueue.json"
    )


