#!/usr/bin/env python3
"""
4MICA Payment Assurance Demo
============================

This script demonstrates how to route agent payments through the 4MICA protocol.
Instead of issuing on-chain transfers for every transaction, the recipient
opens tabs, the payer acquires cryptographic guarantees, and only after several
successful verifications is a single settlement transaction submitted on-chain.

Prerequisites
-------------
* `git clone https://github.com/4mica/4mica-core` (or ensure it exists at
  ``~/4mica-core`` by default)
* Populate a `.env` file with at least:
    FOURMICA_OPERATOR_URL=...
    FOURMICA_RPC_URL=...
    FOURMICA_CONTRACT_ADDRESS=...
    FOURMICA_PRIVATE_KEY=...          # payer key used for guarantees & settlement
    FOURMICA_RECIPIENT_ADDRESS=...    # recipient wallet
    FOURMICA_PAYMENT_AMOUNT_USDC=0.0001 # per-run amount (default 0.0001)
    FOURMICA_PAYMENT_COUNT=3            # number of guarantee runs (default 3)

The script will:
1. Reuse existing collateral locked in 4MICA.
2. For each run, open (or reuse) a payment tab, request a BLS-backed guarantee, and verify it.
3. After the guarantees succeed, submit a single on-chain `recordPayment`
   transaction covering the aggregated total.
"""

import os
import sys
import time
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Dict, List, Optional
from urllib.parse import urljoin

import json
import requests
from dotenv import load_dotenv
from eth_account import Account
from eth_account.messages import encode_typed_data
from eth_utils import to_checksum_address
from py_ecc.bls import G2Basic as bls
from web3 import Web3
from web3.types import TxReceipt
from web3.exceptions import ABIFunctionNotFound
from rich.console import Console, Group
from rich.panel import Panel
from rich.table import Table
from demo_presenter import DemoNarrator, SectionContent, WaitBar

load_dotenv()

console = Console()
presenter = DemoNarrator(console)


def load_env_file(path: str = ".env") -> None:
    env_path = Path(path)
    if not env_path.exists():
        return
    for raw_line in env_path.read_text().splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        if not key or key in os.environ:
            continue
        value = value.strip().strip('"').strip("'")
        os.environ[key] = value


@dataclass
class DemoStepResult:
    name: str
    status: str
    latency: Optional[float] = None
    gas_used: Optional[int] = None
    gas_price_gwei: Optional[float] = None
    gas_cost_eth: Optional[float] = None
    tx_hash: Optional[str] = None
    notes: str = ""
    agent_name: Optional[str] = None
    agent_wallet: Optional[str] = None


demo_results: List[DemoStepResult] = []


def _shorten(text: str, limit: int = 72) -> str:
    """Trim long strings for console-friendly summaries."""
    if not text or len(text) <= limit:
        return text or ""
    return text[: limit - 1] + "…"


def record_result(
    name: str,
    status: str,
    *,
    latency: Optional[float] = None,
    tx_hash: Optional[str] = None,
    receipt: Optional[dict] = None,
    w3: Optional[Web3] = None,
    notes: str = "",
    agent_name: Optional[str] = None,
    agent_wallet: Optional[str] = None,
) -> None:
    gas_used: Optional[int] = None
    gas_price_gwei: Optional[float] = None
    gas_cost_eth: Optional[float] = None

    if receipt is not None and w3 is not None:
        gas_used = receipt.get("gasUsed")
        effective_price = receipt.get("effectiveGasPrice") or receipt.get("gasPrice")
        if effective_price is None:
            tx = w3.eth.get_transaction(receipt.get("transactionHash"))
            effective_price = tx.get("gasPrice")
        if effective_price is not None:
            gas_price_gwei = float(w3.from_wei(effective_price, "gwei"))
            if gas_used is not None:
                gas_cost_eth = float(w3.from_wei(effective_price * gas_used, "ether"))

    demo_results.append(
        DemoStepResult(
            name=name,
            status=status,
            latency=latency,
            gas_used=gas_used,
            gas_price_gwei=gas_price_gwei,
            gas_cost_eth=gas_cost_eth,
            tx_hash=tx_hash,
            notes=notes,
            agent_name=agent_name,
            agent_wallet=agent_wallet,
        )
    )


def print_header():
    header = Panel.fit(
        "\n[bold cyan]CHAOSCHAIN SDK + 4MICA CREDIT DEMO[/bold cyan]\n\n"
        "[yellow]What this walkthrough includes:[/yellow]\n"
        "  ✅ ERC-8004 Identity & Metadata\n"
        "  ✅ Local IPFS Storage\n"
        "  ✅ Process Integrity Verification\n"
        "  ✅ x402 Credit Payment (4MICA)\n",
        title="🏆 Genesis Studio - 4MICA Credit Flow",
        border_style="cyan",
    )
    console.print(header)

# ---------------------------------------------------------------------------
# Configuration / Imports from 4MICA CLI
# ---------------------------------------------------------------------------
load_env_file()
FOURMICA_PRIVATE_KEY = os.getenv("FOURMICA_PRIVATE_KEY") or os.getenv("PRIVATE_KEY")
FOURMICA_RECIPIENT = os.getenv("FOURMICA_RECIPIENT_ADDRESS")
FOURMICA_OPERATOR = os.getenv("FOURMICA_OPERATOR_URL")
FOURMICA_USDC_ADDRESS = os.getenv("FOURMICA_USDC_TOKEN")
FOURMICA_AMOUNT_ETH = float(os.getenv("FOURMICA_PAYMENT_AMOUNT_ETH", "0.001"))
FOURMICA_AMOUNT_USDC = float(os.getenv("FOURMICA_PAYMENT_AMOUNT_USDC", "0.0001"))
FOURMICA_PAYMENT_COUNT = int(os.getenv("FOURMICA_PAYMENT_COUNT", "3"))
FOURMICA_TAB_ID = os.getenv("FOURMICA_TAB_ID")
FOURMICA_TAB_TTL = os.getenv("FOURMICA_TAB_TTL_SECONDS")
FOURMICA_EXPLORER_BASE = os.getenv(
    "FOURMICA_EXPLORER_BASE", "https://sepolia.etherscan.io/tx/"
).rstrip("/")
REGISTER_AGENT = (
    os.getenv("DEMO_REGISTER_AGENT", "false").strip().lower() == "true"
)

FOURMICA_ETH_RPC_URL = (
    os.getenv("FOURMICA_ETH_RPC_URL")
    or os.getenv("ETHEREUM_SEPOLIA_RPC_URL")
    or os.getenv("SEPOLIA_RPC_URL")
)
FOURMICA_CONTRACT_ADDRESS = os.getenv("FOURMICA_CONTRACT_ADDRESS")
FOURMICA_ARTIFACT_PATH = os.getenv(
    "FOURMICA_ARTIFACT_PATH",
    os.path.join(
        os.path.expanduser("~"),
        "4mica-core",
        "contracts",
        "out",
        "Core4Mica.sol",
        "Core4Mica.json",
    ),
)

ESTIMATED_SETTLEMENT_GAS = int(os.getenv("FOURMICA_ESTIMATED_SETTLEMENT_GAS", "250000"))

if not FOURMICA_PRIVATE_KEY:
    raise SystemExit("FOURMICA_PRIVATE_KEY (or PRIVATE_KEY) must be set in the environment.")
if not FOURMICA_OPERATOR:
    raise SystemExit("FOURMICA_OPERATOR_URL must be set in the environment.")
if not FOURMICA_RECIPIENT:
    raise SystemExit("FOURMICA_RECIPIENT_ADDRESS must be set in the environment.")
if not FOURMICA_ETH_RPC_URL:
    raise SystemExit("FOURMICA_ETH_RPC_URL (or SEPOLIA RPC) must be set in the environment.")
if not FOURMICA_CONTRACT_ADDRESS:
    raise SystemExit("FOURMICA_CONTRACT_ADDRESS must be provided.")

base_operator_url = FOURMICA_OPERATOR.rstrip("/") + "/"
http_session = requests.Session()

w3 = Web3(Web3.HTTPProvider(FOURMICA_ETH_RPC_URL))
if not w3.is_connected():
    raise SystemExit(f"Unable to connect to Ethereum RPC at {FOURMICA_ETH_RPC_URL}")

with open(FOURMICA_ARTIFACT_PATH, "r", encoding="utf-8") as artifact_file:
    artifact = json.load(artifact_file)

core4mica_contract = w3.eth.contract(
    address=Web3.to_checksum_address(FOURMICA_CONTRACT_ADDRESS),
    abi=artifact["abi"],
)

IERC20_ARTIFACT_PATH = os.getenv(
    "FOURMICA_IERC20_ARTIFACT",
    os.path.join(
        os.path.expanduser("~"),
        "4mica-core",
        "contracts",
        "out",
        "IERC20.sol",
        "IERC20.json",
    ),
)
with open(IERC20_ARTIFACT_PATH, "r", encoding="utf-8") as erc20_file:
    erc20_abi = json.load(erc20_file)["abi"]

payer_account = w3.eth.account.from_key(FOURMICA_PRIVATE_KEY)
payer_address = payer_account.address
recipient_address = to_checksum_address(FOURMICA_RECIPIENT)

ZERO_ADDRESS = "0x0000000000000000000000000000000000000000"

if FOURMICA_USDC_ADDRESS:
    asset_address = Web3.to_checksum_address(FOURMICA_USDC_ADDRESS)
    erc20_contract_global = w3.eth.contract(address=asset_address, abi=erc20_abi)
    env_decimals = os.getenv("FOURMICA_USDC_DECIMALS")
    if env_decimals:
        try:
            asset_decimals = int(env_decimals)
        except ValueError:
            console.print(f"[yellow]⚠️ Invalid FOURMICA_USDC_DECIMALS value: {env_decimals}, defaulting to 6[/yellow]")
            asset_decimals = 6
    else:
        try:
            asset_decimals = erc20_contract_global.functions.decimals().call()
        except (ABIFunctionNotFound, ValueError):
            asset_decimals = 6
    asset_symbol = os.getenv("FOURMICA_ASSET_SYMBOL", "USDC")
else:
    asset_address = ZERO_ADDRESS
    erc20_contract_global = None
    asset_decimals = 18
    asset_symbol = os.getenv("FOURMICA_ASSET_SYMBOL", "ETH")

# ---------------------------------------------------------------------------
# Utilities
# ---------------------------------------------------------------------------
def eth_balance(addr: str) -> Decimal:
    return Decimal(w3.from_wei(w3.eth.get_balance(addr), "ether"))


def _build_base_tx(account) -> dict:
    latest_block = w3.eth.get_block("latest")
    base_fee = latest_block.get("baseFeePerGas") or w3.to_wei("1", "gwei")
    priority_fee = w3.to_wei("2", "gwei")
    return {
        "from": account.address,
        "nonce": w3.eth.get_transaction_count(account.address),
        "gas": 300_000,
        "maxPriorityFeePerGas": priority_fee,
        "maxFeePerGas": base_fee + priority_fee,
    }


def _send_tx(account, tx_data: dict) -> TxReceipt:
    signed = account.sign_transaction(tx_data)
    tx_hash = w3.eth.send_raw_transaction(signed.raw_transaction)
    return w3.eth.wait_for_transaction_receipt(tx_hash)


def _erc20_decimals(token_contract, fallback: int = 6) -> int:
    try:
        return token_contract.functions.decimals().call()
    except (ABIFunctionNotFound, ValueError):
        console.print("[yellow]⚠️ Token decimals() not available; using fallback[/yellow]")
        return fallback


def record_payment(
    private_key: str,
    tab_id: int,
    amount_wei: int,
    asset: str = "0x0000000000000000000000000000000000000000",
) -> TxReceipt:
    account = w3.eth.account.from_key(private_key)
    tx_data = _build_base_tx(account)
    tx = core4mica_contract.functions.recordPayment(
        tab_id,
        Web3.to_checksum_address(asset),
        amount_wei,
    ).build_transaction(tx_data)
    return _send_tx(account, tx)


def rest_get(path: str) -> Dict:
    url = urljoin(base_operator_url, path.lstrip("/"))
    response = http_session.get(url, timeout=30)
    response.raise_for_status()
    return response.json()


def rest_post(path: str, payload: Dict) -> Dict:
    url = urljoin(base_operator_url, path.lstrip("/"))
    response = http_session.post(url, json=payload, timeout=30)
    response.raise_for_status()
    return response.json()


@dataclass
class GuaranteeRecord:
    tab_id: int
    tab_id_hex: str
    req_id: int
    label: str
    amount_wei: int
    guarantee_payload: Dict
    request_latency: float
    verify_latency: float
    total_latency: float
    guarantee_id: str


def fetch_public_params() -> Dict:
    return rest_get("core/public-params")


def create_payment_tab(user_addr: str, recipient_addr: str, ttl: Optional[int]) -> Dict:
    payload: Dict[str, object] = {
        "user_address": user_addr,
        "recipient_address": recipient_addr,
        "erc20_token": asset_address if asset_address != ZERO_ADDRESS else None,
    }
    if ttl:
        payload["ttl"] = ttl
    return rest_post("core/payment-tabs", payload)


def fetch_tab_info(tab_id_hex: str) -> Dict:
    return rest_get(f"core/tabs/{tab_id_hex}")


# ---------------------------------------------------------------------------
# ChaosChain SDK demo steps (mirroring demo_base_install)
# ---------------------------------------------------------------------------


def demo_1_wallet_creation():
    from chaoschain_sdk import ChaosChainAgentSDK, NetworkConfig
    from chaoschain_sdk.types import AgentRole

    start_time = time.perf_counter()
    sdk = ChaosChainAgentSDK(
        agent_name="DemoAgent",
        agent_domain="demo.chaoschain.io",
        agent_role=AgentRole.SERVER,
        network=NetworkConfig.ETHEREUM_SEPOLIA,
        enable_process_integrity=False,
        enable_ap2=False,
    )
    creation_latency = time.perf_counter() - start_time

    try:
        balance = sdk.wallet_manager.w3.eth.get_balance(sdk.wallet_address)
        balance_eth = sdk.wallet_manager.w3.from_wei(balance, "ether")
        balance_text = f"{balance_eth:.4f} ETH"
    except Exception as exc:
        balance_text = f"[yellow]Unavailable ({exc})[/yellow]"

    presenter.section(
        "Wallet Creation & Management",
        description="Bootstrap an on-chain agent identity ready for Genesis Studio flows.",
        bullets=[
            "ChaosChain Agent SDK generated keys, RPC connectivity, and local persistence.",
        ],
        highlights=[
            SectionContent("Agent", sdk.agent_name),
            SectionContent("Wallet", f"[green]{sdk.wallet_address}[/green]"),
            SectionContent("Network", "[cyan]Ethereum Sepolia[/cyan]"),
            SectionContent("Setup Time", f"{creation_latency:.2f}s"),
            SectionContent("Balance", balance_text),
        ],
    )

    record_result(
        "Wallet Creation",
        "Success",
        latency=creation_latency,
        notes=f"Address: {sdk.wallet_address}",
        agent_name=sdk.agent_name,
        agent_wallet=sdk.wallet_address,
    )

    return sdk


def demo_2_erc8004_identity(sdk):
    description = (
        "Register the agent on the ERC-8004 identity registry so downstream services can verify it."
    )
    existing_agent_id = None
    try:
        with WaitBar(console, "Checking existing registration") as wait_check:
            existing_agent_id = sdk.chaos_agent.get_agent_id()
        if existing_agent_id:
            record_result(
                "Agent Registration",
                "Using existing",
                latency=wait_check.elapsed,
                notes=f"Agent ID: {existing_agent_id}",
                agent_name=sdk.agent_name,
                agent_wallet=sdk.wallet_address,
            )
            presenter.section(
                "ERC-8004 Identity",
                description=description,
                bullets=["Agent record already lives on Sepolia — no transaction required."],
                highlights=[
                    SectionContent("Status", "[cyan]Already registered[/cyan]"),
                    SectionContent("Agent ID", f"[green]{existing_agent_id}[/green]"),
                    SectionContent("Wallet", f"[green]{sdk.wallet_address}[/green]"),
                ],
            )
            return existing_agent_id
    except Exception as check_error:
        presenter.note(
            f"⚠️ Could not verify existing registration ({check_error}). Continuing with a fresh attempt.",
            style="yellow",
        )

    try:
        metadata = {
            "agentName": sdk.agent_name.encode("utf-8"),
            "agentDomain": sdk.agent_domain.encode("utf-8"),
        }

        with WaitBar(console, "Submitting ERC-8004 registration transaction") as wait:
            agent_id, tx_hash = sdk.chaos_agent.register_agent(
                token_uri="ipfs://QmDemo123",
                metadata=metadata,
            )

        if tx_hash == "already_registered":
            record_result(
                "Agent Registration",
                "Already registered",
                latency=wait.elapsed,
                notes=f"Wallet: {sdk.wallet_address}",
                agent_name=sdk.agent_name,
                agent_wallet=sdk.wallet_address,
            )
            presenter.section(
                "ERC-8004 Identity",
                description=description,
                bullets=["This wallet already owns an ERC-8004 profile with metadata."],
                highlights=[
                    SectionContent("Status", "[cyan]Metadata already present[/cyan]"),
                    SectionContent("Agent ID", f"[green]{agent_id}[/green]"),
                    SectionContent("Wallet", f"[green]{sdk.wallet_address}[/green]"),
                ],
            )
            return agent_id

        receipt = sdk.wallet_manager.w3.eth.get_transaction_receipt(tx_hash)
        record_result(
            "Agent Registration",
            "Success",
            latency=wait.elapsed,
            tx_hash=tx_hash,
            receipt=receipt,
            w3=sdk.wallet_manager.w3,
            notes=f"Agent ID: {agent_id}",
            agent_name=sdk.agent_name,
            agent_wallet=sdk.wallet_address,
        )
        presenter.section(
            "ERC-8004 Identity",
            description=description,
            bullets=[
                "Registered metadata pointer `ipfs://QmDemo123` with the identity contract.",
            ],
            highlights=[
                SectionContent("Status", "[green]Registered[/green]"),
                SectionContent("Agent ID", f"[green]{agent_id}[/green]"),
                SectionContent("Tx Hash", f"[cyan]{tx_hash}[/cyan]"),
                SectionContent("Metadata Keys", str(len(metadata))),
            ],
        )

        return agent_id

    except Exception as error:
        latency = (
            locals().get("wait").elapsed
            if "wait" in locals() and getattr(locals().get("wait"), "elapsed", None)
            else None
        )
        record_result(
            "Agent Registration",
            "Failed",
            latency=latency,
            notes=str(error),
            agent_name=sdk.agent_name,
            agent_wallet=sdk.wallet_address,
        )
        presenter.section(
            "ERC-8004 Identity",
            description=description,
            bullets=[f"Registration failed: {error}"],
            highlights=[
                SectionContent("Status", "[red]Registration failed[/red]"),
                SectionContent("Wallet", f"[green]{sdk.wallet_address}[/green]"),
            ],
        )
        presenter.note(
            "💰 Tip: fund the wallet via https://sepoliafaucet.com/ and rerun once balance is available.",
            style="yellow",
        )
        return None


def demo_2b_metadata(sdk, agent_id):
    if not agent_id:
        presenter.note(
            "⏭️ Skipping on-chain metadata showcase because the agent is not registered.",
            style="yellow",
        )
        return

    description = "Attach versioned metadata to the ERC-8004 identity and read it back."

    try:
        with WaitBar(console, "Submitting metadata update transaction") as wait:
            tx_hash = sdk.chaos_agent.set_agent_metadata("version", b"1.0.0")

        receipt = sdk.wallet_manager.w3.eth.get_transaction_receipt(tx_hash)
        record_result(
            "Metadata Update",
            "Success",
            latency=wait.elapsed,
            tx_hash=tx_hash,
            receipt=receipt,
            w3=sdk.wallet_manager.w3,
            notes="version=1.0.0",
            agent_name=sdk.agent_name,
            agent_wallet=sdk.wallet_address,
        )

        name = sdk.chaos_agent.get_agent_metadata("agentName")
        domain = sdk.chaos_agent.get_agent_metadata("agentDomain")
        version = sdk.chaos_agent.get_agent_metadata("version")
        presenter.section(
            "ERC-8004 Metadata",
            description=description,
            bullets=["Version tag written on-chain and retrieved using the metadata accessor."],
            highlights=[
                SectionContent("Status", "[green]Updated[/green]"),
                SectionContent("Tx Hash", f"[cyan]{tx_hash}[/cyan]"),
                SectionContent("Agent Name", name.decode("utf-8")),
                SectionContent("Agent Domain", domain.decode("utf-8")),
                SectionContent("Version", version.decode("utf-8")),
            ],
        )

    except Exception as error:
        latency = (
            locals().get("wait").elapsed
            if "wait" in locals() and getattr(locals().get("wait"), "elapsed", None)
            else None
        )
        record_result(
            "Metadata Update",
            "Failed",
            latency=latency,
            notes=str(error),
            agent_name=sdk.agent_name,
            agent_wallet=sdk.wallet_address,
        )
        presenter.note(f"⚠️ Metadata operations issue: {error}", style="yellow")


def demo_3_storage(sdk):
    description = "Push demo payloads to the local IPFS node and ensure they round-trip correctly."

    test_data = {
        "message": "Hello from ChaosChain SDK!",
        "timestamp": datetime.now().isoformat(),
        "demo": "ethereum_install",
    }

    start_time = time.perf_counter()
    try:
        import json as _json

        result = sdk.storage_manager.put(_json.dumps(test_data).encode())

        if result.success:
            retrieved = sdk.storage_manager.get(result.uri)
            if retrieved:
                elapsed = time.perf_counter() - start_time
                record_result(
                    "Local IPFS Storage",
                    "Success",
                    latency=elapsed,
                    notes=f"URI: {result.uri}",
                    agent_name=sdk.agent_name,
                    agent_wallet=sdk.wallet_address,
                )
                presenter.section(
                    "Local IPFS Storage",
                    description=description,
                    bullets=[
                        "Saved a JSON payload to the local node and pulled it back immediately.",
                    ],
                    highlights=[
                        SectionContent("Status", "[green]Round-trip success[/green]"),
                        SectionContent("IPFS URI", f"[green]{result.uri}[/green]"),
                        SectionContent("Elapsed", f"{elapsed:.2f}s"),
                    ],
                )
                return
            else:
                record_result(
                    "Local IPFS Storage",
                    "Failed",
                    latency=time.perf_counter() - start_time,
                    notes="Retrieval returned empty result",
                    agent_name=sdk.agent_name,
                    agent_wallet=sdk.wallet_address,
                )
                presenter.section(
                    "Local IPFS Storage",
                    description=description,
                    bullets=["Stored file but retrieval returned an empty payload."],
                    highlights=[
                        SectionContent("Status", "[yellow]Partial success[/yellow]"),
                        SectionContent("IPFS URI", f"[cyan]{result.uri}[/cyan]"),
                    ],
                )
                return
        elapsed = time.perf_counter() - start_time
        record_result(
            "Local IPFS Storage",
            "Failed",
            latency=elapsed,
            notes=str(result.error),
            agent_name=sdk.agent_name,
            agent_wallet=sdk.wallet_address,
        )
        presenter.section(
            "Local IPFS Storage",
            description=description,
            bullets=[f"Storage operation failed: {result.error}"],
            highlights=[
                SectionContent("Status", "[red]Storage failed[/red]"),
            ],
        )

    except Exception as error:
        record_result(
            "Local IPFS Storage",
            "Failed",
            latency=time.perf_counter() - start_time,
            notes=str(error),
            agent_name=sdk.agent_name,
            agent_wallet=sdk.wallet_address,
        )
        presenter.section(
            "Local IPFS Storage",
            description=description,
            bullets=[
                f"Local node not responding ({error}). Start IPFS Desktop or run `ipfs daemon` before rerunning."
            ],
            highlights=[
                SectionContent("Status", "[red]IPFS unavailable[/red]"),
            ],
        )


def demo_4_process_integrity():
    from chaoschain_sdk import ChaosChainAgentSDK, NetworkConfig
    from chaoschain_sdk.types import AgentRole

    start_time = time.perf_counter()
    sdk = ChaosChainAgentSDK(
        agent_name="IntegrityDemo",
        agent_domain="integrity.chaoschain.io",
        agent_role=AgentRole.SERVER,
        network=NetworkConfig.ETHEREUM_SEPOLIA,
        enable_process_integrity=True,
        enable_ap2=False,
    )
    latency = time.perf_counter() - start_time

    record_result(
        "Process Integrity Setup",
        "Success",
        latency=latency,
        notes="Integrity verifier active",
        agent_name=sdk.agent_name,
        agent_wallet=sdk.wallet_address,
    )
    presenter.section(
        "Process Integrity Verification",
        description="Turn on deterministic execution proofs for the agent runtime.",
        bullets=[
            "Local verifier records transcripts for each critical SDK action.",
            "Proof artifacts can be shared to external auditors or partners.",
        ],
        highlights=[
            SectionContent("Status", "[green]Verifier active[/green]"),
            SectionContent("Agent", sdk.agent_name),
            SectionContent("Setup Time", f"{latency:.2f}s"),
        ],
    )


def build_eip712_message(public_params: Dict, tab_id: int, req_id: int, amount_wei: int, timestamp: int):
    return {
        "types": {
            "EIP712Domain": [
                {"name": "name", "type": "string"},
                {"name": "version", "type": "string"},
                {"name": "chainId", "type": "uint256"},
            ],
            "PaymentGuarantee": [
                {"name": "user", "type": "address"},
                {"name": "recipient", "type": "address"},
                {"name": "tabId", "type": "uint256"},
                {"name": "reqId", "type": "uint256"},
                {"name": "amount", "type": "uint256"},
                {"name": "timestamp", "type": "uint64"},
            ],
        },
        "primaryType": "PaymentGuarantee",
        "domain": {
            "name": public_params["eip712_name"],
            "version": public_params["eip712_version"],
            "chainId": public_params["chain_id"],
        },
        "message": {
            "user": payer_address,
            "recipient": recipient_address,
            "tabId": tab_id,
            "reqId": req_id,
            "amount": amount_wei,
            "timestamp": timestamp,
        },
    }


def request_guarantee(
    public_params: Dict,
    tab_id_int: int,
    req_id: int,
    amount_wei: int,
    run_label: str,
    fixed_timestamp: Optional[int] = None,
) -> tuple[GuaranteeRecord, int]:
    timestamp = fixed_timestamp or int(datetime.now(timezone.utc).timestamp())
    typed_data = build_eip712_message(public_params, tab_id_int, req_id, amount_wei, timestamp)

    message = encode_typed_data(full_message=typed_data)
    signed = Account.sign_message(message, private_key=FOURMICA_PRIVATE_KEY)

    guarantee_request = {
        "claims": {
            "user_address": payer_address,
            "recipient_address": recipient_address,
            "tab_id": hex(tab_id_int),
            "req_id": hex(req_id),
            "amount": hex(amount_wei),
            "timestamp": timestamp,
            "asset_address": asset_address,
        },
        "signature": signed.signature.hex(),
        "scheme": "eip712",
    }

    with WaitBar(console, f"{run_label} · requesting credit guarantee") as request_wait:
        try:
            guarantee_response = rest_post("core/guarantees", guarantee_request)
        except requests.HTTPError as http_err:
            error_body = {}
            try:
                error_body = http_err.response.json()
            except Exception:
                pass
            raise RuntimeError(
                f"Guarantee request failed (status {http_err.response.status_code}): {error_body}"
            ) from http_err

    request_latency = request_wait.elapsed or 0.0

    with WaitBar(console, f"{run_label} · verifying BLS certificate") as verify_wait:
        public_key_raw = public_params["public_key"]
        if isinstance(public_key_raw, str):
            public_key_bytes = bytes.fromhex(public_key_raw)
        elif isinstance(public_key_raw, (bytes, bytearray)):
            public_key_bytes = bytes(public_key_raw)
        elif isinstance(public_key_raw, list):
            public_key_bytes = bytes(public_key_raw)
        else:
            raise TypeError("Unsupported public_key format from operator.")

        certificate_signature = bytes.fromhex(guarantee_response["signature"])
        certificate_claims = bytes.fromhex(guarantee_response["claims"])
        if not bls.Verify(public_key_bytes, certificate_claims, certificate_signature):
            raise ValueError("BLS signature verification failed")

    verify_latency = verify_wait.elapsed or 0.0

    return (
        GuaranteeRecord(
            tab_id=tab_id_int,
            tab_id_hex=hex(tab_id_int),
            req_id=req_id,
            label=run_label,
            amount_wei=amount_wei,
            guarantee_payload={
                "claims": guarantee_request["claims"],
                "bls_signature": guarantee_response["signature"],
            },
            request_latency=request_latency,
            verify_latency=verify_latency,
            total_latency=request_latency + verify_latency,
            guarantee_id=guarantee_response.get("id", str(uuid.uuid4())),
        ),
        timestamp,
    )


def settle_aggregate(total_amount_wei: int, tab_int: int):
    with WaitBar(console, "Recording aggregate payment on-chain") as wait:
        receipt = record_payment(
            FOURMICA_PRIVATE_KEY,
            tab_int,
            total_amount_wei,
            asset_address,
        )
    return receipt


def build_headline_panel(
    total_latency: float,
    avg_latency: float,
    total_gas_used: int,
) -> Panel:
    """Generate a bold recap panel for executive audiences."""
    gas_used_text = f"{total_gas_used:,}" if total_gas_used else "0"
    avg_latency_text = f"{avg_latency:.2f}s" if avg_latency else "—"

    body = (
        "[bold bright_white]Total Latency[/bold bright_white]\n"
        f"[bold cyan]{total_latency:.2f}s[/bold cyan]\n\n"
        "[bold bright_white]Avg Step Latency[/bold bright_white]\n"
        f"[bold cyan]{avg_latency_text}[/bold cyan]\n\n"
        "[bold bright_white]Total Gas Used[/bold bright_white]\n"
        f"[bold cyan]{gas_used_text}[/bold cyan]"
    )
    return Panel.fit(
        body,
        title="⚡ Credit Efficiency Recap",
        border_style="magenta",
        padding=(1, 6),
    )


def print_summary(
    guarantees: List[GuaranteeRecord],
    settlement_receipt,
    settlement_latency: Optional[float],
):
    if not demo_results:
        presenter.note("No demo steps were executed.", style="yellow")
        return

    summary_table = Table(show_header=True, header_style="bold cyan")
    summary_table.add_column("Step")
    summary_table.add_column("Status", justify="center")
    summary_table.add_column("Latency (s)", justify="right")
    summary_table.add_column("Highlight", overflow="fold")

    latencies = [result.latency for result in demo_results if result.latency is not None]
    total_latency = sum(latencies)
    measured_steps = len(latencies)
    avg_latency = total_latency / measured_steps if measured_steps else 0.0
    gas_samples = [result.gas_used for result in demo_results if result.gas_used]
    total_gas_used = sum(gas_samples)
    success_count = 0
    tx_entries = []

    for result in demo_results:
        latency_value = result.latency or 0.0
        status_lower = (result.status or "").lower()
        if "success" in status_lower:
            status_display = "[green]Success[/green]"
            success_count += 1
        elif "fail" in status_lower:
            status_display = "[red]Failed[/red]"
        elif "skip" in status_lower or "using" in status_lower:
            status_display = "[cyan]Skipped[/cyan]"
        else:
            status_display = result.status or "-"

        latency_text = f"{latency_value:.2f}" if result.latency is not None else "—"
        info_parts = []
        if result.notes:
            info_parts.append(_shorten(result.notes))
        info = " | ".join(info_parts) if info_parts else "—"

        summary_table.add_row(
            result.name,
            status_display,
            latency_text,
            info,
        )

        if result.tx_hash:
            tx_entries.append(
                (
                    result.name,
                    result.tx_hash,
                    result.gas_used,
                    result.gas_cost_eth,
                )
            )

    guarantee_table = None
    guarantee_latencies = [g.total_latency for g in guarantees if g.total_latency is not None]
    total_guarantee_latency = sum(guarantee_latencies)
    avg_guarantee_latency = (
        total_guarantee_latency / len(guarantee_latencies) if guarantee_latencies else 0.0
    )
    total_value_units = sum(g.amount_wei for g in guarantees)
    aggregate_value = (
        Decimal(total_value_units) / Decimal(10**asset_decimals) if total_value_units else Decimal("0")
    )
    avoided_transactions = max(len(guarantees) - 1, 0) if guarantees else 0

    if guarantees:
        guarantee_table = Table(show_header=True, header_style="bold cyan")
        guarantee_table.add_column("Credit Run", justify="left")
        guarantee_table.add_column("Guarantee ID", overflow="fold")
        guarantee_table.add_column("BLS Cycle (s)", justify="right")
        guarantee_table.add_column("Amount", justify="right")

        for guarantee in guarantees:
            amount = Decimal(guarantee.amount_wei) / Decimal(10**asset_decimals)
            cycle_text = f"{guarantee.total_latency:.2f}" if guarantee.total_latency is not None else "—"
            guarantee_table.add_row(
                guarantee.label,
                guarantee.guarantee_id,
                cycle_text,
                f"{amount:.6f} {asset_symbol}",
            )

    extras = [summary_table]
    if guarantee_table:
        extras.append(guarantee_table)
    extra_renderable = Group(*extras) if len(extras) > 1 else extras[0]

    total_steps = len(demo_results)
    highlight_items: List[SectionContent] = []
    if guarantees:
        highlight_items.append(SectionContent("Credit Runs", f"{len(guarantees)} BLS passes"))
        highlight_items.append(SectionContent("On-chain Tx Avoided", str(avoided_transactions)))
        highlight_items.append(SectionContent("Aggregate Value", f"{aggregate_value:.6f} {asset_symbol}"))
        if guarantee_latencies:
            highlight_items.append(
                SectionContent("Avg Credit Cycle", f"{avg_guarantee_latency:.2f}s")
            )
            highlight_items.append(
                SectionContent("Credit Latency Sum", f"{total_guarantee_latency:.2f}s")
            )
        if settlement_latency is not None:
            highlight_items.append(
                SectionContent("Settlement Finality", f"{settlement_latency:.2f}s")
            )

    highlight_items.extend(
        [
            SectionContent("Demo Steps", str(total_steps)),
            SectionContent("Successful", f"{success_count}/{total_steps}"),
            SectionContent("Total Latency", f"{total_latency:.2f}s"),
            SectionContent("Avg Step", f"{avg_latency:.2f}s"),
            SectionContent("On-chain Tx", str(len(tx_entries))),
            SectionContent("Total Gas Used", f"{total_gas_used:,}" if total_gas_used else "0"),
        ]
    )
    presenter.section(
        "4MICA Performance Snapshot",
        description="Off-chain guarantees collapsed into a single on-chain settlement, highlighting speed and cost efficiency.",
        highlights=highlight_items,
        extra=extra_renderable,
    )

    console.print(
        build_headline_panel(
            total_latency,
            avg_latency,
            total_gas_used,
        )
    )


# ---------------------------------------------------------------------------
# x402 Credit Payment via 4MICA
# ---------------------------------------------------------------------------


def demo_x402_credit_payment(sdk):
    asset_label = (
        f"[yellow]{asset_symbol}[/yellow] @ {asset_address}"
        if asset_address != ZERO_ADDRESS
        else "[yellow]ETH[/yellow]"
    )
    description = (
        "Aggregate 4MICA guarantees into a single on-chain settlement using Coinbase x402 credit."
    )
    presenter.section(
        "x402 Credit Payment (4MICA)",
        description=description,
        bullets=[
            "Reuse collateral to mint BLS-backed guarantees.",
            "Submit one settlement transaction after all verifications succeed.",
        ],
        highlights=[
            SectionContent("Operator", f"[cyan]{FOURMICA_OPERATOR}[/cyan]"),
            SectionContent("Collateral Asset", asset_label),
            SectionContent("Payer", f"[green]{payer_address}[/green]"),
            SectionContent("Recipient", f"[green]{recipient_address}[/green]"),
            SectionContent("Runs", str(FOURMICA_PAYMENT_COUNT)),
        ],
    )

    step_start = time.perf_counter()

    try:
        with WaitBar(console, "Fetching public parameters"):
            public_params = fetch_public_params()
        presenter.note("ℹ️ Loaded public parameters from operator.", style="green")
    except Exception as error:
        record_result(
            "x402 Credit Payment",
            "Failed",
            latency=time.perf_counter() - step_start,
            notes=str(error),
            agent_name="4MICA Payer",
            agent_wallet=payer_address,
        )
        presenter.section(
            "x402 Credit Payment (4MICA)",
            description=description,
            bullets=[f"Unable to fetch operator parameters: {error}"],
            highlights=[SectionContent("Status", "[red]Aborted[/red]")],
        )
        return [], None, None

    if asset_address != ZERO_ADDRESS:
        base_amount = Decimal(str(FOURMICA_AMOUNT_USDC))
    else:
        base_amount = Decimal(str(FOURMICA_AMOUNT_ETH))

    amount_units = int(base_amount * Decimal(10**asset_decimals))
    guarantees: List[GuaranteeRecord] = []
    settlement_receipt = None
    settlement_elapsed: Optional[float] = None
    total_amount_units = 0

    tab_start_timestamp: Optional[int] = None

    if FOURMICA_TAB_ID:
        if FOURMICA_TAB_ID.startswith("0x"):
            tab_id_int = int(FOURMICA_TAB_ID, 16)
        else:
            tab_id_int = int(FOURMICA_TAB_ID)
        tab_id_hex = hex(tab_id_int)
        presenter.note(f"Using existing tab {tab_id_hex}.", style="cyan")
        try:
            tab_details = fetch_tab_info(tab_id_hex)
            tab_start_timestamp = tab_details.get("start_timestamp")
        except Exception as fetch_error:
            presenter.note(f"⚠️ Could not fetch tab info: {fetch_error}", style="yellow")
    else:
        ttl = int(FOURMICA_TAB_TTL) if FOURMICA_TAB_TTL else None
        with WaitBar(console, "Creating payment tab"):
            tab_info = create_payment_tab(payer_address, recipient_address, ttl)
        tab_raw_id = tab_info["id"]
        tab_id_int = int(tab_raw_id, 16) if isinstance(tab_raw_id, str) else int(tab_raw_id)
        tab_id_hex = hex(tab_id_int)
        presenter.note(f"🆕 Created 4MICA tab {tab_id_hex}.", style="green")
        try:
            tab_details = fetch_tab_info(tab_id_hex)
            tab_start_timestamp = tab_details.get("start_timestamp")
        except Exception as fetch_error:
            presenter.note(f"⚠️ Could not fetch tab info: {fetch_error}", style="yellow")

    if tab_start_timestamp in (0, None):
        tab_start_timestamp = None

    for run_idx in range(FOURMICA_PAYMENT_COUNT):
        payment_label = f"Credit Payment {run_idx + 1}/{FOURMICA_PAYMENT_COUNT}"
        wait_title = (
            f"Executing 4MICA credit payment #{run_idx + 1} "
            f"({base_amount:.6f} {asset_symbol})"
        )
        try:
            with WaitBar(console, wait_title):
                guarantee, used_timestamp = request_guarantee(
                    public_params,
                    tab_id_int,
                    req_id=run_idx,
                    amount_wei=amount_units,
                    run_label=payment_label,
                    fixed_timestamp=tab_start_timestamp,
                )
            guarantees.append(guarantee)
            if tab_start_timestamp is None:
                tab_start_timestamp = used_timestamp
            presenter.note(
                f"🛡️ {payment_label} approved ({base_amount:.6f} {asset_symbol}).",
                style="green",
            )
        except RuntimeError as err:
            record_result(
                "x402 Credit Payment",
                "Failed",
                latency=time.perf_counter() - step_start,
                notes=str(err),
                agent_name="4MICA Payer",
                agent_wallet=payer_address,
            )
            presenter.note(
                f"❌ {payment_label} failed: {err}",
                style="red",
            )
            return [], None, settlement_elapsed

    if guarantees:
        total_amount_units = sum(g.amount_wei for g in guarantees)
        presenter.note(
            f"Aggregating {len(guarantees)} guarantees into settlement totaling "
            f"{Decimal(total_amount_units) / Decimal(10**asset_decimals):.6f} {asset_symbol}.",
            style="cyan",
        )
        settlement_prompt = (
            f"Recording aggregate payment on-chain ({Decimal(total_amount_units) / Decimal(10**asset_decimals):.6f} {asset_symbol})"
        )
        try:
            with WaitBar(console, settlement_prompt) as wait:
                settlement_receipt = settle_aggregate(total_amount_units, guarantees[0].tab_id)
            settlement_elapsed = wait.elapsed or 0.0
            presenter.note(
                f"✅ Settlement confirmed in {settlement_elapsed:.2f}s.",
                style="green",
            )
        except Exception as err:
            record_result(
                "x402 Credit Payment",
                "Failed",
                latency=time.perf_counter() - step_start,
                notes=f"Settlement error: {err}",
                agent_name="4MICA Payer",
                agent_wallet=payer_address,
            )
            presenter.note(f"❌ Settlement failed: {err}", style="red")
            return guarantees, None, settlement_elapsed

    aggregate_value = Decimal(total_amount_units) / Decimal(10**asset_decimals)
    notes = (
        f"{len(guarantees)} guarantees → 1 tx · "
        f"{aggregate_value:.6f} {asset_symbol}"
    )

    record_result(
        "x402 Credit Payment",
        "Success",
        latency=time.perf_counter() - step_start,
        tx_hash=settlement_receipt.transactionHash.hex() if settlement_receipt else None,
        receipt=settlement_receipt,
        w3=w3,
        notes=notes,
        agent_name="4MICA Payer",
        agent_wallet=payer_address,
    )
    return guarantees, settlement_receipt, settlement_elapsed

def main():
    try:
        demo_results.clear()
        print_header()

        sdk = demo_1_wallet_creation()

        if REGISTER_AGENT:
            agent_id = demo_2_erc8004_identity(sdk)
            demo_2b_metadata(sdk, agent_id)
        else:
            presenter.note(
                "⏭️ Skipping on-chain registration (DEMO_REGISTER_AGENT=false).",
                style="yellow",
            )
            record_result(
                "Agent Registration",
                "Skipped",
                notes="Using existing agent configuration",
                agent_name=sdk.agent_name,
                agent_wallet=sdk.wallet_address,
            )

        demo_3_storage(sdk)
        demo_4_process_integrity()

        guarantees, settlement_receipt, settlement_latency = demo_x402_credit_payment(sdk)

        print_summary(guarantees, settlement_receipt, settlement_latency)

    except KeyboardInterrupt:
        console.print("\n\n[yellow]Demo interrupted by user[/yellow]")
        sys.exit(0)
    except Exception as error:
        console.print(f"\n[red]❌ Demo error: {error}[/red]")
        import traceback

        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
