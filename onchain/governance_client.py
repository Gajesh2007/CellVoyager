import os
from typing import Any, Dict, List, Optional, Tuple

from web3 import Web3
from eth_account.signers.local import LocalAccount


class GovernanceClient:
    def __init__(self, w3: Web3, contract, account: LocalAccount):
        self.w3 = w3
        self.contract = contract
        self.account = account

    def ensure_public_key(self, public_key_pem: str, chain_id: Optional[int] = None) -> None:
        try:
            current = self.contract.functions.publicEncryptionKey().call()
            if current == public_key_pem:
                return
        except Exception:
            pass

        try:
            estimated_gas = self.contract.functions.setPublicEncryptionKey(public_key_pem).estimate_gas({
                "from": self.account.address,
            })
        except Exception:
            estimated_gas = 800_000
        gas_limit = min(3_000_000, int(estimated_gas * 2) + 50_000)

        tx = self.contract.functions.setPublicEncryptionKey(public_key_pem).build_transaction({
            "from": self.account.address,
            "nonce": self.w3.eth.get_transaction_count(self.account.address),
            "gas": gas_limit,
            "maxFeePerGas": self.w3.to_wei(os.getenv("MAX_FEE_GWEI", "30"), "gwei"),
            "maxPriorityFeePerGas": self.w3.to_wei(os.getenv("MAX_PRIORITY_FEE_GWEI", "2"), "gwei"),
            "chainId": chain_id or self.w3.eth.chain_id,
        })
        signed = self.account.sign_transaction(tx)
        tx_hash = self.w3.eth.send_raw_transaction(signed.rawTransaction)
        receipt = self.w3.eth.wait_for_transaction_receipt(tx_hash)
        if receipt.status != 1:
            raise RuntimeError("setPublicEncryptionKey transaction failed")

    def list_research_items(self, page_size: int = 50) -> List[Tuple[int, Dict[str, Any]]]:
        count = self.contract.functions.researchCount().call()
        items: List[Tuple[int, Dict[str, Any]]] = []
        offset = 0
        while offset < count:
            limit = min(page_size, count - offset)
            try:
                batch = self.contract.functions.getResearchRange(offset, limit).call()
            except Exception:
                batch = []
                for j in range(offset, offset + limit):
                    try:
                        batch.append(self.contract.functions.getResearch(j).call())
                    except Exception:
                        batch.append(None)

            for idx_in_page, r in enumerate(batch):
                if not r:
                    continue
                i = offset + idx_in_page
                item = {
                    "analysisName": r[0],
                    "description": r[1],
                    "encryptedH5adPath": r[2],
                    "modelName": r[3],
                    "numAnalyses": int(r[4]),
                    "maxIterations": int(r[5]),
                    "submitter": r[6],
                    "createdAt": int(r[7]),
                    "completed": bool(r[8]),
                    "completedAt": int(r[9]),
                    "priority": int(r[10]),
                    "totalVotes": int(r[11]),
                }
                items.append((i, item))
            offset += limit
        return items

    def mark_completed(self, research_id: int) -> bool:
        try:
            self.contract.functions.markCompleted(research_id).call({"from": self.account.address})
        except Exception as sim_err:
            print(f"  ❌ Preflight markCompleted failed: {sim_err}")
            return False
        try:
            estimated_gas = self.contract.functions.markCompleted(research_id).estimate_gas({
                "from": self.account.address,
            })
        except Exception:
            estimated_gas = 120_000
        gas_limit = min(500_000, int(estimated_gas * 2) + 50_000)
        tx = self.contract.functions.markCompleted(research_id).build_transaction({
            "from": self.account.address,
            "nonce": self.w3.eth.get_transaction_count(self.account.address),
            "gas": gas_limit,
            "maxFeePerGas": self.w3.to_wei(os.getenv("MAX_FEE_GWEI", "30"), "gwei"),
            "maxPriorityFeePerGas": self.w3.to_wei(os.getenv("MAX_PRIORITY_FEE_GWEI", "2"), "gwei"),
            "chainId": self.w3.eth.chain_id,
        })
        signed = self.account.sign_transaction(tx)
        tx_hash = self.w3.eth.send_raw_transaction(signed.rawTransaction)
        print(f"  📝 markCompleted tx sent: {tx_hash.hex()}")
        receipt = self.w3.eth.wait_for_transaction_receipt(tx_hash)
        if receipt.status == 1:
            print("  ✅ markCompleted confirmed")
            return True
        print(f"  ⚠️ markCompleted failed with status {receipt.status}")
        return False


