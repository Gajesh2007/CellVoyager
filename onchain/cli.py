import argparse
import os
import time
from typing import Optional

from dotenv import load_dotenv
from web3 import Web3
from eth_account import Account
from eth_account.signers.local import LocalAccount

from onchain.utils import load_openai_api_key
from onchain.web3_utils import connect_web3, load_contract_abi
from onchain.governance_client import GovernanceClient
from onchain.agent_runner import run_analysis


def get_account_from_env() -> LocalAccount:
    priv = os.getenv("PRIVATE_KEY")
    if priv:
        return Account.from_key(priv)
    mnemonic = os.getenv("MNEMONIC")
    if not mnemonic:
        raise RuntimeError("Set PRIVATE_KEY or MNEMONIC in environment for the agent account.")
    try:
        Account.enable_unaudited_hdwallet_features()
    except Exception:
        pass
    acct = Account.from_mnemonic(mnemonic)
    return acct


def derive_rsa_keypair(mnemonic: str) -> tuple[str, str]:
    from crypto_utils import derive_rsa_keypair_from_mnemonic
    return derive_rsa_keypair_from_mnemonic(mnemonic)


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

    openai_api_key = load_openai_api_key()
    if not openai_api_key:
        print("❌ OPENAI_API_KEY not found")
        return 1

    w3 = connect_web3(args.rpc_url)
    acct = get_account_from_env()
    print(f"✅ Connected to chain {w3.eth.chain_id} as {acct.address}")

    mnemonic = os.getenv("MNEMONIC")
    if not mnemonic:
        print("❌ MNEMONIC is required to derive RSA keypair")
        return 1
    private_pem, public_pem = derive_rsa_keypair(mnemonic)

    keys_dir = os.path.join(args.output_home, "keys")
    os.makedirs(keys_dir, exist_ok=True)
    with open(os.path.join(keys_dir, f"agent_rsa_{acct.address}.pem"), "w") as f:
        f.write(private_pem)
    with open(os.path.join(keys_dir, f"agent_rsa_{acct.address}.pub.pem"), "w") as f:
        f.write(public_pem)

    abi = load_contract_abi(args.abi_path if args.abi_path else None)
    contract = w3.eth.contract(address=Web3.to_checksum_address(args.gov_address), abi=abi)

    try:
        onchain_agent = Web3.to_checksum_address(contract.functions.agent().call())
        if onchain_agent != Web3.to_checksum_address(acct.address):
            print(f"❌ Agent mismatch: contract agent {onchain_agent} != local {acct.address}")
            return 1
    except Exception:
        pass

    gclient = GovernanceClient(w3, contract, acct)
    try:
        gclient.ensure_public_key(public_pem, chain_id=(args.chain_id or None))
    except Exception as e:
        print(f"⚠️ Failed to set public key on-chain (continuing): {e}")

    def tick_once() -> bool:
        try:
            return run_analysis(
                w3=w3,
                gclient=gclient,
                acct=acct,
                private_pem=private_pem,
                openai_api_key=openai_api_key,
                default_paper_summary_path=args.paper_summary,
                output_home=args.output_home,
                log_home=args.log_home,
                prompt_dir=args.prompt_dir,
            )
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

    return 0


