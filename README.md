<div align="center">
<img src="images/logo.jpeg" alt="CellVoyager Logo" width="700">
</div>

## Setup

First clone the current repository:
```bash
git clone https://github.com/zou-group/CellVoyager.git
cd CellVoyager
```

Create the necessary environment:
```bash
conda env create -f CellVoyager_env.yaml
conda activate CellVoyager
```

## Environment Configuration

Copy the example environment files and configure them:
```bash
# Root directory
cp .env.example .env

# Frontend directory  
cp frontend/.env.example frontend/.env

# Contracts directory (for deployment)
cp contracts/.env.example contracts/.env
```

### Root `.env` Configuration

### Required Variables
```bash
# OpenAI API Key
OPENAI_API_KEY=sk-xxxxxxxxxxxxx

# Blockchain Configuration (for on-chain agent)
MNEMONIC="your twelve word mnemonic phrase here"
RPC_URL=https://base-sepolia.drpc.org
GOV_ADDRESS=0x1234567890123456789012345678901234567890

# Contract Deployment (for deploying contracts)
PUBLIC_KEY="-----BEGIN PUBLIC KEY-----\nYOUR_RSA_PUBLIC_KEY_HERE\n-----END PUBLIC KEY-----" -- keep it empty for now, it will be set by the agent during the setup
AGENT=0x1234567890123456789012345678901234567890 - will be provided by compute, for local testing, you can set it to your own address
```

### Optional Variables
```bash
# Agent Configuration
DEFAULT_MODEL=o3-mini
AGENT_INTERVAL=300
MAX_FEE_GWEI=30
MAX_PRIORITY_FEE_GWEI=2

# File Paths
PAPER_SUMMARY_PATH=example/covid19_summary.txt
DOWNLOAD_DIR=downloads
GOV_ABI_PATH=contracts/out/GovernanceQueue.sol/GovernanceQueue.json

# Alternative API Key Loading
OPENAI_API_KEY_FILE=/path/to/api/key/file
```

## Running CellVoyager

### Local Analysis
To run the agent locally, use:
```bash
python run.py --h5ad-path PATH_TO_H5AD_DATASET \
              --paper-path PATH_TO_PAPER_SUMMARY \
              --analysis-name RUN_NAME
```
where:
* `h5ad-path` is the absolute path of the anndata `.h5ad` file
* `paper-path` is the absolute path of a `.txt` file containing the LLM or human generated summary of the paper
* `analysis-name` is the name you want your analysis files to be saved under

### Sovereign Verifiable Agent
To run the sovereign verifiable agent that processes research requests from the blockchain:
```bash
python run_onchain.py --watch
```

This will:
1. Connect to the blockchain using your `RPC_URL` and `MNEMONIC`
2. Poll the GovernanceQueue contract for new research requests
3. Download encrypted datasets, decrypt them using your RSA private key
4. Run analysis using the CellVoyager agent
5. Mark completed research on-chain

## Smart Contract Deployment

### Prerequisites
Install Foundry:
```bash
curl -L https://foundry.paradigm.xyz | bash
foundryup
```

### Deploy Contracts
Navigate to the contracts directory:
```bash
cd contracts
```

Configure your `contracts/.env` file with your deployment variables (see the example file for all options).

Deploy all contracts:
```bash
forge script script/DeployAll.s.sol --rpc-url $RPC_URL --private-key $PRIVATE_KEY --broadcast --verify
```

Or deploy individually:
```bash
# Deploy DonationSBT first
forge script script/DeployDonationSBT.s.sol --rpc-url $RPC_URL --private-key $PRIVATE_KEY --broadcast

# Then deploy GovernanceQueue (requires SBT address)
SBT=0x... forge script script/DeployGovernanceQueue.s.sol --rpc-url $RPC_URL --private-key $PRIVATE_KEY --broadcast
```

After deployment, update your root `.env` and `frontend/.env` files with the deployed contract addresses.

## Frontend Setup

The frontend is a Next.js application that provides a web interface for submitting research requests and managing the governance queue.

### Prerequisites
```bash
cd frontend
npm install
```

### Configuration
Configure your `frontend/.env` file with the deployed contract addresses and WalletConnect project ID.

### Development
```bash
npm run dev
```

The frontend will be available at `http://localhost:3000` and you will be able to submit research requests and manage the governance queue.

## Example
We are going to use the COVID-19 case study from the CellVoyager, which builds on [this paper](https://www.nature.com/articles/s41591-020-0944-y).


To download the `.h5ad` object run
```
curl -o example/covid19.h5ad "https://hosted-matrices-prod.s3-us-west-2.amazonaws.com/Single_cell_atlas_of_peripheral_immune_response_to_SARS_CoV_2_infection-25/Single_cell_atlas_of_peripheral_immune_response_to_SARS_CoV_2_infection.h5ad"
```
An example summary of the associated manuscript is already included in `example/covid19_summary.txt`.


Then simply run `python run.py` which by default uses the COVID-19 dataset and manuscript summary. You will see the Jupyter notebooks in an `outputs` directory, which will update the notebook in real-time. Currently, the notebooks are run sequentially, but we are currently experimenting with ways to parallelize this.

## CellBench

To run base LLMs (gpt-4o, o3-mini) 3x on CellBench:

```
cd CellBench
python run_base_llm.py
python run_llm_judge.py
```

To run agent 3x on CellBench:

```
cd CellBench
python run_agent.py {gpt-4o|o3-mini}
```

Metrics should be printed to stdout and saved in the `responses` and `judged` dirs.
