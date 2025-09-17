import os
import shutil
import urllib.parse
import urllib.request
from typing import Optional, Tuple

from web3 import Web3
from eth_account.signers.local import LocalAccount

from agent import AnalysisAgent
from onchain.governance_client import GovernanceClient


def select_research_to_process(gclient: GovernanceClient, private_pem: str, default_paper_summary_path: str) -> Optional[Tuple[int, dict]]:
    from crypto_utils import decrypt_envelope_or_oaep

    items = gclient.list_research_items(page_size=int(os.getenv("RESEARCH_PAGE_SIZE", "50")))
    items.sort(key=lambda x: (-x[1]["priority"], x[1]["createdAt"]))

    chosen = None
    for research_id, meta in items:
        if meta.get("completed"):
            continue
        decrypted = decrypt_envelope_or_oaep(meta["encryptedH5adPath"], private_pem)
        if not decrypted:
            continue
        # Do not require local summary file here; we can fall back to on-chain description later
        chosen = (research_id, {**meta, "dataset_url": decrypted})
        break
    return chosen


def run_analysis(
    w3: Web3,
    gclient: GovernanceClient,
    acct: LocalAccount,
    private_pem: str,
    openai_api_key: str,
    default_paper_summary_path: str,
    output_home: str,
    log_home: str,
    prompt_dir: str,
) -> bool:
    chosen = select_research_to_process(gclient, private_pem, default_paper_summary_path)
    if chosen is None:
        print("No processable research found this cycle")
        return False

    research_id, meta = chosen
    print(f"\n🔎 Processing research {research_id}: {meta['analysisName']} (priority {meta['priority']})")

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
        return False

    analysis_name = f"{meta['analysisName']}_id{research_id}"
    model_name = meta["modelName"] or os.getenv("DEFAULT_MODEL", "o3-mini")
    num_analyses = meta["numAnalyses"] or 1
    max_iterations = meta["maxIterations"] or 3

    # Resolve summary path: use on-chain description when present; else use provided file path
    description_text = str(meta.get("description") or "").strip()
    if description_text:
        summaries_dir = os.path.join(output_home, "summaries")
        os.makedirs(summaries_dir, exist_ok=True)
        safe_name = (
            analysis_name.replace("/", "_").replace("\\", "_").replace(" ", "_")
        )
        summary_path = os.path.join(summaries_dir, f"{safe_name}.summary.txt")
        with open(summary_path, "w", encoding="utf-8") as f:
            f.write(description_text)
    else:
        summary_candidate = os.getenv("PAPER_SUMMARY_PATH", default_paper_summary_path)
        if not (summary_candidate and os.path.exists(summary_candidate)):
            print("  ❌ Description empty and summary file not found; skipping")
            return False
        summary_path = summary_candidate

    agent = AnalysisAgent(
        h5ad_path=local_path,
        paper_summary_path=summary_path,
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

    return gclient.mark_completed(research_id)


