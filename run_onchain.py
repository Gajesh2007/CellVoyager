import os
import sys
import json
import base64
import time
import argparse
from typing import Callable, Tuple, Optional, List, Dict, Any

from dotenv import load_dotenv
from web3 import Web3
from web3.middleware import geth_poa_middleware
from eth_account import Account
from eth_account.signers.local import LocalAccount

from crypto_utils import (
    decrypt_envelope_or_oaep,
    derive_rsa_keypair_from_mnemonic,
)
import urllib.request
import urllib.parse
import shutil

from agent import AnalysisAgent


def load_contract_abi(abi_path: Optional[str]) -> List[Dict[str, Any]]:
    """Load ABI from Foundry artifact JSON. Fail if it cannot be loaded.

    If abi_path is provided, it will be used. Otherwise, defaults to
    ./contracts/out/GovernanceQueue.sol/GovernanceQueue.json relative to this file.
    """
    # Try user-provided path first
    if abi_path:
        try:
            with open(abi_path, "r") as f:
                data = json.load(f)
            if isinstance(data, dict) and "abi" in data:
                return data["abi"]
        except Exception:
            pass

    # Default artifact location
    default_path = os.path.join(
        os.path.dirname(__file__),
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


def _load_openai_api_key() -> Optional[str]:
    key = os.getenv("OPENAI_API_KEY")
    if key:
        return key
    candidate_paths = []
    env_file = os.getenv("OPENAI_API_KEY_FILE")
    if env_file:
        candidate_paths.append(env_file)
    candidate_paths.extend([
        "/run/secrets/openai_api_key",
        "/run/secrets/OPENAI_API_KEY",
        "/var/run/secrets/openai_api_key",
        "/var/run/secrets/OPENAI_API_KEY",
        "/etc/secrets/openai_api_key",
        "/etc/secrets/OPENAI_API_KEY",
    ])
    for path in candidate_paths:
        try:
            if path and os.path.exists(path):
                with open(path, "r") as f:
                    content = f.read().strip()
                    if content:
                        return content
        except Exception:
            continue
    return None


def connect_web3(rpc_url: str) -> Web3:
    w3 = Web3(Web3.HTTPProvider(rpc_url, request_kwargs={"timeout": 30}))
    # Optional: POA middleware for some testnets
    try:
        w3.middleware_onion.inject(geth_poa_middleware, layer=0)
    except Exception:
        pass
    if not w3.is_connected():
        raise RuntimeError(f"Failed to connect to RPC {rpc_url}")
    return w3


def get_account_from_env() -> LocalAccount:
    priv = os.getenv("PRIVATE_KEY")
    if priv:
        return Account.from_key(priv)
    mnemonic = os.getenv("MNEMONIC")
    if not mnemonic:
        raise RuntimeError("Set PRIVATE_KEY or MNEMONIC in environment for the agent account.")
    # Derive first account path m/44'/60'/0'/0/0
    try:
        # Enable HD wallet features required by eth-account for mnemonic derivation
        Account.enable_unaudited_hdwallet_features()
    except Exception:
        # If already enabled or not required, continue
        pass
    acct = Account.from_mnemonic(mnemonic)
    return acct


def ensure_public_key_onchain(
    w3: Web3,
    acct: LocalAccount,
    contract,
    public_key_pem: str,
    chain_id: Optional[int] = None,
) -> None:
    try:
        current = contract.functions.publicEncryptionKey().call()
        if current == public_key_pem:
            return
    except Exception:
        pass

    # Estimating gas because storing a long PEM string can exceed a fixed gas limit
    try:
        estimated_gas = contract.functions.setPublicEncryptionKey(public_key_pem).estimate_gas({
            "from": acct.address,
        })
    except Exception:
        estimated_gas = 800_000  # fallback

    gas_limit = min(3_000_000, int(estimated_gas * 2) + 50_000)

    tx = contract.functions.setPublicEncryptionKey(public_key_pem).build_transaction({
        "from": acct.address,
        "nonce": w3.eth.get_transaction_count(acct.address),
        "gas": gas_limit,
        "maxFeePerGas": w3.to_wei(os.getenv("MAX_FEE_GWEI", "30"), "gwei"),
        "maxPriorityFeePerGas": w3.to_wei(os.getenv("MAX_PRIORITY_FEE_GWEI", "2"), "gwei"),
        "chainId": chain_id or w3.eth.chain_id,
    })
    signed = acct.sign_transaction(tx)
    tx_hash = w3.eth.send_raw_transaction(signed.rawTransaction)
    receipt = w3.eth.wait_for_transaction_receipt(tx_hash)
    if receipt.status != 1:
        raise RuntimeError("setPublicEncryptionKey transaction failed")


def process_research_queue(
    w3: Web3,
    contract,
    acct: LocalAccount,
    private_pem: str,
    openai_api_key: str,
    default_paper_summary_path: str,
    output_home: str,
    log_home: str,
    prompt_dir: str,
) -> None:
    count = contract.functions.researchCount().call()
    if count == 0:
        print("No research items found.")
        return

    items = []
    page_size = max(1, int(os.getenv("RESEARCH_PAGE_SIZE", "50")))
    offset = 0
    while offset < count:
        limit = min(page_size, count - offset)
        try:
            batch = contract.functions.getResearchRange(offset, limit).call()
        except Exception:
            # Fallback to per-item calls for this window if range call is unavailable
            batch = []
            for j in range(offset, offset + limit):
                try:
                    batch.append(contract.functions.getResearch(j).call())
                except Exception:
                    batch.append(None)

        for idx_in_page, r in enumerate(batch):
            if not r:
                continue
            i = offset + idx_in_page
            # Expected tuple layout (per frontend ABI):
            # 0 analysisName, 1 description, 2 encryptedH5adPath, 3 modelName,
            # 4 numAnalyses, 5 maxIterations, 6 submitter, 7 createdAt,
            # 8 completed, 9 completedAt, 10 priority, 11 totalVotes
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

    # Sort by current priority desc, then earliest created
    items.sort(key=lambda x: (-x[1]["priority"], x[1]["createdAt"]))

    # Find the first processable item (decryptable URL)
    chosen: Optional[Tuple[int, dict]] = None
    for research_id, meta in items:
        if meta.get("completed"):
            continue
        decrypted = decrypt_envelope_or_oaep(meta["encryptedH5adPath"], private_pem)
        if not decrypted:
            continue
        paper_summary_path = os.getenv("PAPER_SUMMARY_PATH", default_paper_summary_path)
        if not os.path.exists(paper_summary_path):
            continue
        chosen = (research_id, {**meta, "dataset_url": decrypted, "paper_summary_path": paper_summary_path})
        break

    if chosen is None:
        print("No processable research found this cycle")
        return

    research_id, meta = chosen
    print(f"\n🔎 Processing research {research_id}: {meta['analysisName']} (priority {meta['priority']})")

    # Download dataset to local file
    download_dir = os.getenv("DOWNLOAD_DIR", os.path.join(output_home, "downloads"))
    os.makedirs(download_dir, exist_ok=True)
    try:
        parsed = urllib.parse.urlparse(meta["dataset_url"]) 
        filename = os.path.basename(parsed.path) or f"research_{research_id}.h5ad"
        local_path = os.path.join(download_dir, filename)
        print(f"  ⬇️  Downloading dataset from {meta['dataset_url']} → {local_path}")
        with urllib.request.urlopen(meta["dataset_url"], timeout=120) as resp, open(local_path, "wb") as out:
            shutil.copyfileobj(resp, out)
        print("  ✅ Download complete")
    except Exception as e:
        print(f"  ❌ Download failed: {e}")
        return

    analysis_name = f"{meta['analysisName']}_id{research_id}"
    model_name = meta["modelName"] or os.getenv("DEFAULT_MODEL", "o3-mini")
    num_analyses = meta["numAnalyses"] or 1
    max_iterations = meta["maxIterations"] or 3

    agent = AnalysisAgent(
        h5ad_path=local_path,
        paper_summary_path=meta["paper_summary_path"],
        openai_api_key=openai_api_key,
        model_name=model_name,
        analysis_name=analysis_name,
        num_analyses=num_analyses,
        max_iterations=max_iterations,
        prompt_dir=prompt_dir,
        output_home=output_home,
        log_home=log_home,
    )
    agent.run()

    # Mark this research as completed on-chain (best-effort)
    try:
        # Preflight: simulate to catch NotAgent/InvalidResearch early
        try:
            contract.functions.markCompleted(research_id).call({
                "from": acct.address,
            })
        except Exception as sim_err:
            print(f"  ❌ Preflight markCompleted failed: {sim_err}")
            return

        # Estimate gas with padding
        try:
            estimated_gas = contract.functions.markCompleted(research_id).estimate_gas({
                "from": acct.address,
            })
        except Exception:
            estimated_gas = 120_000
        gas_limit = min(500_000, int(estimated_gas * 2) + 50_000)

        tx = contract.functions.markCompleted(research_id).build_transaction({
            "from": acct.address,
            "nonce": w3.eth.get_transaction_count(acct.address),
            "gas": gas_limit,
            "maxFeePerGas": w3.to_wei(os.getenv("MAX_FEE_GWEI", "30"), "gwei"),
            "maxPriorityFeePerGas": w3.to_wei(os.getenv("MAX_PRIORITY_FEE_GWEI", "2"), "gwei"),
            "chainId": w3.eth.chain_id,
        })
        signed = acct.sign_transaction(tx)
        tx_hash = w3.eth.send_raw_transaction(signed.rawTransaction)
        print(f"  📝 markCompleted tx sent: {tx_hash.hex()}")
        receipt = w3.eth.wait_for_transaction_receipt(tx_hash)
        if receipt.status == 1:
            print("  ✅ markCompleted confirmed")
        else:
            print(f"  ⚠️ markCompleted failed with status {receipt.status}")
    except Exception as e:
        print(f"⚠️ Failed to mark completed on-chain: {e}")


def main() -> int:
    load_dotenv()

    parser = argparse.ArgumentParser(description="On-chain agent runner for CellVoyager")
    parser.add_argument("--gov-address", default=os.getenv("GOV_ADDRESS") or os.getenv("NEXT_PUBLIC_GOV_ADDRESS", ""), help="GovernanceQueue contract address")
    parser.add_argument("--rpc-url", default=os.getenv("RPC_URL", ""), help="Ethereum RPC URL")
    parser.add_argument("--chain-id", type=int, default=0, help="Override chain ID (optional)")
    parser.add_argument("--prompt-dir", default="prompts", help="Prompt templates directory")
    parser.add_argument("--output-home", default=".", help="Outputs home directory")
    parser.add_argument("--log-home", default=".", help="Logs home directory")
    parser.add_argument("--paper-summary", default="example/covid19_summary.txt", help="Default paper summary path")
    parser.add_argument("--abi-path", default=os.getenv("GOV_ABI_PATH", ""), help="Path to GovernanceQueue artifact JSON (optional)")
    parser.add_argument("--watch", action="store_true", help="Continuously poll and process the queue")
    parser.add_argument("--interval", type=int, default=int(os.getenv("AGENT_INTERVAL", "300")), help="Polling interval seconds when --watch is set")
    args = parser.parse_args()

    if not args.rpc_url:
        print("❌ RPC URL is required (set --rpc-url or RPC_URL env)")
        return 1

    if not args.gov_address:
        print("❌ GovernanceQueue address is required (set --gov-address or GOV_ADDRESS env)")
        return 1

    # Prepare OpenAI
    openai_api_key = _load_openai_api_key()
    if not openai_api_key:
        print("❌ OPENAI_API_KEY not found")
        return 1

    # Web3 and account
    w3 = connect_web3(args.rpc_url)
    acct = get_account_from_env()
    print(f"✅ Connected to chain {w3.eth.chain_id} as {acct.address}")

    # RSA from mnemonic
    mnemonic = os.getenv("MNEMONIC")
    if not mnemonic:
        print("❌ MNEMONIC is required to derive RSA keypair")
        return 1
    private_pem, public_pem = derive_rsa_keypair_from_mnemonic(mnemonic)

    # Save keys locally for reuse
    keys_dir = os.path.join(args.output_home, "keys")
    os.makedirs(keys_dir, exist_ok=True)
    with open(os.path.join(keys_dir, f"agent_rsa_{acct.address}.pem"), "w") as f:
        f.write(private_pem)
    with open(os.path.join(keys_dir, f"agent_rsa_{acct.address}.pub.pem"), "w") as f:
        f.write(public_pem)

    # Contract
    abi = load_contract_abi(args.abi_path if args.abi_path else None)
    contract = w3.eth.contract(address=Web3.to_checksum_address(args.gov_address), abi=abi)

    # Sanity-check agent binding to avoid silent NotAgent reverts
    try:
        onchain_agent = Web3.to_checksum_address(contract.functions.agent().call())
        if onchain_agent != Web3.to_checksum_address(acct.address):
            print(f"❌ Agent mismatch: contract agent {onchain_agent} != local {acct.address}")
            return 1
    except Exception:
        # If the method doesn't exist (unexpected), continue
        pass

    def tick_once() -> bool:
        try:
            ensure_public_key_onchain(w3, acct, contract, public_pem, chain_id=(args.chain_id or None))
        except Exception as e:
            print(f"⚠️ Failed to set public key on-chain (continuing): {e}")
        try:
            process_research_queue(
                w3=w3,
                contract=contract,
                acct=acct,
                private_pem=private_pem,
                openai_api_key=openai_api_key,
                default_paper_summary_path=args.paper_summary,
                output_home=args.output_home,
                log_home=args.log_home,
                prompt_dir=args.prompt_dir,
            )
            return True
        except Exception as e:
            print(f"❌ Error processing research queue: {e}")
            return False

    if args.watch:
        print(f"👀 Watch mode enabled. Polling every {args.interval} seconds...")
        while True:
            tick_once()
            time.sleep(max(1, args.interval))
    else:
        ok = tick_once()
        return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
