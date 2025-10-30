#!/usr/bin/env python3
"""
ChaosChain SDK - ETHEREUM INSTALL DEMO
===================================

What this demonstrates:
- ✅ ERC-8004 v1.0 agent identity & reputation
- ✅ x402 payment protocol (Coinbase official)
- ✅ Local IPFS storage (no external services)
- ✅ Process integrity verification
- ✅ Wallet creation & management

Requirements:
    pip install chaoschain-sdk

Optional (not required for this demo):
    - Google AP2 (for intent verification)
    - 0G Storage/Compute (for decentralized services)
    - Pinata/Irys (for cloud storage)

This demo shows the CORE functionality that works immediately
after installing the base SDK!
"""

import os
import sys
import time
import warnings
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import List, Optional

from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from demo_presenter import DemoNarrator, SectionContent, WaitBar

# Suppress Web3.py event parsing warnings (harmless ABI mismatches)
warnings.filterwarnings('ignore', message='.*MismatchedABI.*')
warnings.filterwarnings('ignore', message='.*encountered the following error during processing.*')

console = Console()
presenter = DemoNarrator(console)


@dataclass
class DemoStepResult:
    """Structured record for each demo step."""
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
    """Trim long strings for compact summary tables."""
    if not text or len(text) <= limit:
        return text or ""
    return text[: limit - 1] + "…"

REGISTER_AGENT = os.getenv("DEMO_REGISTER_AGENT", "false").strip().lower() == "true"


def record_result(
    name: str,
    status: str,
    *,
    latency: Optional[float] = None,
    tx_hash: Optional[str] = None,
    receipt: Optional[dict] = None,
    w3: Optional["Web3"] = None,
    notes: str = "",
    agent_name: Optional[str] = None,
    agent_wallet: Optional[str] = None
) -> None:
    """Append a result entry for later summary display."""
    gas_used: Optional[int] = None
    gas_price_gwei: Optional[float] = None
    gas_cost_eth: Optional[float] = None

    if receipt is not None and w3 is not None:
        gas_used = receipt.get("gasUsed")
        effective_price = receipt.get("effectiveGasPrice") or receipt.get("gasPrice")
        base_fee = receipt.get("effectiveGasPrice")
        if effective_price is None:
            try:
                tx = w3.eth.get_transaction(receipt["transactionHash"])
                max_fee_per_gas = tx.get("maxFeePerGas")
                max_priority = tx.get("maxPriorityFeePerGas")
                if max_fee_per_gas is not None and max_priority is not None:
                    effective_price = int(max_priority)
                    base_fee = int(max_fee_per_gas) - int(max_priority)
                else:
                    effective_price = tx.get("gasPrice")
            except Exception:
                effective_price = None
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
            tx_hash=tx_hash,
            notes=notes,
            agent_name=agent_name,
            agent_wallet=agent_wallet,
        )
    )

def load_env_file(path: str = ".env") -> None:
    """Load key=value pairs from a .env file without overriding existing env vars."""
    env_path = Path(path)
    if not env_path.exists():
        console.print(f"[yellow]⚠️  Environment file not found: {env_path}[/yellow]")
        return

    for raw_line in env_path.read_text().splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        if not key or key in os.environ:
            continue
        value = value.strip()
        if ((value.startswith('"') and value.endswith('"')) or
                (value.startswith("'") and value.endswith("'"))):
            value = value[1:-1]
        os.environ[key] = value


load_env_file()

# Set minimal environment variables for demo
# Using Ethereum Sepolia for reliable RPC connectivity
if "SEPOLIA_RPC_URL" not in os.environ:
    os.environ["SEPOLIA_RPC_URL"] = "https://ethereum-sepolia-rpc.publicnode.com"
os.environ.setdefault("ETHEREUM_SEPOLIA_RPC_URL", os.environ["SEPOLIA_RPC_URL"])


def print_header():
    """Print demo header."""
    header = Panel.fit(
        "\n[bold cyan]CHAOSCHAIN SDK - ETHEREUM INSTALL DEMO[/bold cyan]\n\n"
        "[yellow]What works out-of-the-box:[/yellow]\n"
        "  ✅ ERC-8004 v1.0 (Identity, Validation & Reputation)\n"
        "  ✅ x402 Payment Protocol (Coinbase)\n"
        "  ✅ Local IPFS Storage\n"
        "  ✅ Process Integrity Verification\n"
        "  ✅ Wallet Management\n\n"
        "[dim]No external services required![/dim]\n",
        title="🏆 Genesis Studio - Ethereum SDK",
        border_style="cyan"
    )
    console.print(header)


def demo_1_wallet_creation():
    """Demo 1: Create and manage wallets."""
    from chaoschain_sdk import ChaosChainAgentSDK, NetworkConfig
    from chaoschain_sdk.types import AgentRole

    start_time = time.perf_counter()
    sdk = ChaosChainAgentSDK(
        agent_name="DemoAgent",
        agent_domain="demo.chaoschain.io",
        agent_role=AgentRole.SERVER,
        network=NetworkConfig.ETHEREUM_SEPOLIA,
        enable_process_integrity=False,  # Keep it simple for demo 1
        enable_ap2=False  # Disable AP2 for this demo
    )
    creation_latency = time.perf_counter() - start_time

    try:
        balance = sdk.wallet_manager.w3.eth.get_balance(sdk.wallet_address)
        balance_eth = sdk.wallet_manager.w3.from_wei(balance, 'ether')
        balance_text = f"{balance_eth:.4f} ETH"
    except Exception as e:
        balance_text = f"[yellow]Unavailable ({e})[/yellow]"

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
        agent_wallet=sdk.wallet_address
    )
    
    return sdk


def demo_2_erc8004_identity(sdk):
    """Demo 2: ERC-8004 identity registration."""
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
                agent_wallet=sdk.wallet_address
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
            "agentName": sdk.agent_name.encode('utf-8'),
            "agentDomain": sdk.agent_domain.encode('utf-8')
        }

        with WaitBar(console, "Submitting ERC-8004 registration transaction") as wait:
            agent_id, tx_hash = sdk.chaos_agent.register_agent(
                token_uri="ipfs://QmDemo123",
                metadata=metadata
            )

        if tx_hash == "already_registered":
            record_result(
                "Agent Registration",
                "Already registered",
                latency=wait.elapsed,
                notes=f"Wallet: {sdk.wallet_address}",
                agent_name=sdk.agent_name,
                agent_wallet=sdk.wallet_address
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
            agent_wallet=sdk.wallet_address
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

    except Exception as e:
        latency = locals().get("wait").elapsed if "wait" in locals() and getattr(locals().get("wait"), "elapsed", None) else None
        error_str = str(e).lower()
        if "insufficient funds" in error_str or "balance 0" in error_str:
            bullet = "Sepolia faucet funds are required for the registration transaction."
        elif "already registered" in error_str or "revert" in error_str:
            bullet = "On-chain registry reports the agent as already registered."
        else:
            bullet = f"Encountered unexpected error: {e}"

        record_result(
            "Agent Registration",
            "Failed",
            latency=latency,
            notes=str(e),
            agent_name=sdk.agent_name,
            agent_wallet=sdk.wallet_address
        )
        presenter.section(
            "ERC-8004 Identity",
            description=description,
            bullets=[bullet],
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
    """Demo 2b: ERC-8004 on-chain metadata (NEW in v0.2.3!)."""
    if not agent_id:
        presenter.note(
            "⏭️ Skipping on-chain metadata showcase because the agent is not registered.",
            style="yellow",
        )
        return

    description = "Attach versioned metadata to the ERC-8004 identity and read it back."

    try:
        # Set additional metadata (requires testnet tokens)
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
            agent_wallet=sdk.wallet_address
        )

        # Read metadata back
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
                SectionContent("Agent Name", name.decode('utf-8')),
                SectionContent("Agent Domain", domain.decode('utf-8')),
                SectionContent("Version", version.decode('utf-8')),
            ],
        )

    except Exception as e:
        latency = locals().get("wait").elapsed if "wait" in locals() and getattr(locals().get("wait"), "elapsed", None) else None
        error_str = str(e).lower()
        if "insufficient funds" in error_str:
            presenter.note(
                "⚠️ Setting metadata requires a small Sepolia balance; reading existing metadata is free.",
                style="yellow",
            )
        else:
            presenter.note(f"⚠️ Metadata operations issue: {e}", style="yellow")

        record_result(
            "Metadata Update",
            "Failed",
            latency=latency,
            notes=str(e),
            agent_name=sdk.agent_name,
            agent_wallet=sdk.wallet_address
        )


def demo_3_storage(sdk):
    """Demo 3: Local IPFS storage."""
    description = "Push demo payloads to the local IPFS node and ensure they round-trip correctly."

    test_data = {
        "message": "Hello from ChaosChain SDK!",
        "timestamp": datetime.now().isoformat(),
        "demo": "ethereum_install"
    }
    
    start_time = time.perf_counter()
    elapsed: float
    try:
        import json
        result = sdk.storage_manager.put(json.dumps(test_data).encode())
        
        if result.success:
            retrieved = sdk.storage_manager.get(result.uri)
            if retrieved:
                elapsed = time.perf_counter() - start_time
                record_result(
                    "Local IPFS Storage",
                    "Success",
                    latency=elapsed,
                    notes=f"URI: {result.uri}"
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
                    notes="Retrieval returned empty result"
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
            notes=str(result.error)
        )
        presenter.section(
            "Local IPFS Storage",
            description=description,
            bullets=[f"Storage operation failed: {result.error}"],
            highlights=[
                SectionContent("Status", "[red]Storage failed[/red]"),
            ],
        )
    except Exception as e:
        record_result(
            "Local IPFS Storage",
            "Failed",
            latency=time.perf_counter() - start_time,
            notes=str(e)
        )
        presenter.section(
            "Local IPFS Storage",
            description=description,
            bullets=[
                f"Local node not responding ({e}). Start IPFS Desktop or run `ipfs daemon` before rerunning."
            ],
            highlights=[
                SectionContent("Status", "[red]IPFS unavailable[/red]"),
            ],
        )


def demo_4_process_integrity():
    """Demo 4: Process integrity verification."""
    from chaoschain_sdk import ChaosChainAgentSDK, NetworkConfig
    from chaoschain_sdk.types import AgentRole
    
    start_time = time.perf_counter()
    sdk = ChaosChainAgentSDK(
        agent_name="IntegrityDemo",
        agent_domain="integrity.chaoschain.io",
        agent_role=AgentRole.SERVER,
        network=NetworkConfig.ETHEREUM_SEPOLIA,
        enable_process_integrity=True,  # Enable process integrity
        enable_ap2=False  # Disable AP2 for this demo
    )
    latency = time.perf_counter() - start_time
    
    record_result(
        "Process Integrity Setup",
        "Success",
        latency=latency,
        notes="Integrity verifier active"
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


def demo_5_x402_payments():
    """Demo 5: x402 payment protocol."""
    from chaoschain_sdk import ChaosChainAgentSDK, NetworkConfig
    from chaoschain_sdk.types import AgentRole
    from chaoschain_sdk.exceptions import PaymentError
    
    sdk = ChaosChainAgentSDK(
        agent_name="PaymentDemo",
        agent_domain="payment.chaoschain.io",
        agent_role=AgentRole.SERVER,
        network=NetworkConfig.ETHEREUM_SEPOLIA,
        enable_ap2=True 
    )
    
    payer_agent = os.environ.get("X402_PAYER_AGENT", "DemoAgent")
    payment_amount = float(os.environ.get("X402_PAYMENT_AMOUNT_USDC", "0.001"))
    total_runs = int(os.environ.get("X402_PAYMENT_COUNT", "3"))
    description = (
        "Execute Coinbase x402 payments end-to-end, including request creation, proof collection, and on-chain settlement."
    )

    presenter.section(
        "x402 Payment Protocol (Coinbase)",
        description=description,
        bullets=[
            "Uses ChaosChain payment manager to orchestrate the x402 flow.",
            "Each run mints a payment request, executes it, and records proofs.",
        ],
        highlights=[
            SectionContent("Payer Agent", payer_agent),
            SectionContent("Amount Per Run", f"[yellow]{payment_amount:.3f} USDC[/yellow]"),
            SectionContent("Runs", str(total_runs)),
            SectionContent("Treasury", "[green]0x20E7B2A2c8969725b88Dd3EF3a11Bc3353C83F70[/green]"),
        ],
    )
    
    payment_manager = getattr(sdk, "payment_manager", None)
    if not payment_manager:
        record_result(
            "x402 Payment Execution",
            "Failed",
            latency=None,
            notes="Payment manager unavailable",
            agent_name=payer_agent,
            agent_wallet=sdk.wallet_manager.get_wallet_address(payer_agent)
        )
        presenter.note("❌ Payment manager unavailable — check SDK configuration.", style="red")
        return
    
    summary_rows = []
    successes = 0

    for run_index in range(1, total_runs + 1):
        payment_proof = None
        payment_latency: Optional[float] = None
        last_error: Optional[Exception] = None

        try:
            if getattr(sdk, "a2a_x402", None):
                w3c_payment_request = sdk.create_x402_payment_request(
                    cart_id=f"demo-{int(time.time())}-{run_index}",
                    total_amount=payment_amount,
                    currency="USDC",
                    items=[{"name": f"ChaosChain Demo Service #{run_index}", "price": payment_amount}],
                    settlement_address=sdk.wallet_address
                )
            else:
                w3c_payment_request = None
            
            manager_request = payment_manager.create_x402_payment_request(
                from_agent=payer_agent,
                to_agent=sdk.agent_name,
                amount=payment_amount,
                currency="USDC",
                service_description=f"Demo payment via x402 (run {run_index})"
            )
            
            wait_title = f"Executing x402 payment #{run_index} ({payment_amount:.3f} USDC)"
            with WaitBar(console, wait_title) as wait:
                payment_proof = payment_manager.execute_x402_payment(manager_request)
            payment_latency = wait.elapsed
        except PaymentError as e:
            last_error = e
        except Exception as generic_error:
            last_error = generic_error
        
        if not payment_proof:
            record_result(
                f"x402 Payment Execution #{run_index}",
                "Failed",
                latency=payment_latency,
                notes=str(last_error) if last_error else "Unknown error",
                agent_name=payer_agent,
                agent_wallet=sdk.wallet_manager.get_wallet_address(payer_agent)
            )
            summary_rows.append(
                (run_index, "[red]Failed[/red]", payment_latency, "—", str(last_error) if last_error else "Unknown error")
            )
            presenter.note(
                f"❌ Payment {run_index}/{total_runs} failed: {last_error}",
                style="red",
            )
            continue
        
        main_tx = payment_proof.transaction_hash
        fee_tx = payment_proof.receipt_data.get("protocol_fee_tx") if payment_proof.receipt_data else None
        try:
            main_receipt = sdk.wallet_manager.w3.eth.get_transaction_receipt(main_tx)
        except Exception as receipt_error:
            main_receipt = None
            presenter.note(
                f"⚠️ Could not fetch main payment receipt: {receipt_error}",
                style="yellow",
            )
        
        notes_parts = [f"Amount: {payment_amount:.3f} USDC"]
        if fee_tx:
            notes_parts.append(f"Fee tx: {fee_tx}")
        if payment_proof.receipt_data:
            protocol_fee = payment_proof.receipt_data.get("protocol_fee")
            if protocol_fee is not None:
                notes_parts.append(f"Protocol fee: {protocol_fee:.6f} USDC")
        
        record_result(
            f"x402 Payment Execution #{run_index}",
            "Success",
            latency=payment_latency,
            tx_hash=main_tx,
            receipt=main_receipt,
            w3=sdk.wallet_manager.w3 if main_receipt else None,
            notes=" | ".join(notes_parts),
            agent_name=payer_agent,
            agent_wallet=sdk.wallet_manager.get_wallet_address(payer_agent)
        )
        successes += 1
        summary_rows.append(
            (
                run_index,
                "[green]Success[/green]",
                payment_latency,
                main_tx,
                "Fee tx recorded" if fee_tx else "Single tx",
            )
        )
        presenter.note(
            f"✅ Payment {run_index}/{total_runs} settled (tx {main_tx}).",
            style="green",
        )

    if summary_rows:
        summary_table = Table(title=None, show_header=True, header_style="bold cyan")
        summary_table.add_column("Run", justify="right")
        summary_table.add_column("Status")
        summary_table.add_column("Latency (s)", justify="right")
        summary_table.add_column("Main Tx", overflow="fold")
        summary_table.add_column("Notes", overflow="fold")

        for run_index, status, latency, tx_hash, info in summary_rows:
            latency_text = f"{latency:.2f}" if latency is not None else "—"
            summary_table.add_row(str(run_index), status, latency_text, tx_hash, info)

        presenter.section(
            "x402 Payment Runs",
            description="Summary of Coinbase x402 demo executions.",
            highlights=[
                SectionContent("Successful Runs", f"{successes}/{len(summary_rows)}"),
                SectionContent("Amount per Run", f"{payment_amount:.3f} USDC"),
            ],
            extra=summary_table,
        )


def build_headline_panel(
    total_latency: float,
    avg_latency: float,
    total_gas_used: int,
) -> Panel:
    """Generate a boardroom-ready performance recap."""
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
        title="⚡ Base Install Performance",
        border_style="magenta",
        padding=(1, 6),
    )


def print_summary():
    """Print demo summary."""
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
        elif "using" in status_lower or "already" in status_lower:
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

    extras = [summary_table]
    extra_renderable = extras[0]

    total_steps = len(demo_results)
    highlight_items = [
        SectionContent("Demo Steps", str(total_steps)),
        SectionContent("Successful", f"{success_count}/{total_steps}"),
        SectionContent("Total Latency", f"{total_latency:.2f}s"),
        SectionContent("Avg Step", f"{avg_latency:.2f}s"),
        SectionContent("On-chain Tx", str(len(tx_entries))),
        SectionContent("Total Gas Used", f"{total_gas_used:,}" if total_gas_used else "0"),
    ]

    presenter.section(
        "Demo Summary",
        description="Performance snapshot for the base Ethereum install run on Sepolia.",
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


def main():
    """Run the Ethereum install demo."""
    try:
        global demo_results
        demo_results.clear()
        
        print_header()
        
        # Demo 1: Wallet
        sdk = demo_1_wallet_creation()
        
        agent_id = None
        if REGISTER_AGENT:
            # Demo 2: ERC-8004
            agent_id = demo_2_erc8004_identity(sdk)
            
            # Demo 2b: Metadata (NEW in v0.2.3!)
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
                agent_wallet=sdk.wallet_address
            )
        
        # Demo 3: Storage
        demo_3_storage(sdk)
        
        # Demo 4: Process Integrity
        demo_4_process_integrity()
        
        # Demo 5: x402
        demo_5_x402_payments()
        
        # Summary
        print_summary()
        
    except KeyboardInterrupt:
        console.print("\n\n[yellow]Demo interrupted by user[/yellow]")
        sys.exit(0)
    except Exception as e:
        console.print(f"\n[red]❌ Demo error: {e}[/red]")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
