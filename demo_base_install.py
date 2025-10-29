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
import threading
import warnings
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import List, Optional

from rich.console import Console
from rich.panel import Panel
from rich.progress import (
    BarColumn,
    Progress,
    SpinnerColumn,
    TextColumn,
    TimeElapsedColumn,
)
from rich.table import Table

# Suppress Web3.py event parsing warnings (harmless ABI mismatches)
warnings.filterwarnings('ignore', message='.*MismatchedABI.*')
warnings.filterwarnings('ignore', message='.*encountered the following error during processing.*')

console = Console()


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

REGISTER_AGENT = os.getenv("DEMO_REGISTER_AGENT", "false").strip().lower() == "true"


class WaitBar:
    """Display a pulsing progress bar while long-running work completes."""

    def __init__(self, description: str):
        self.description = description
        self.elapsed: Optional[float] = None
        self._stop_event = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._start: Optional[float] = None
        self._progress: Optional[Progress] = None
        self._task_id: Optional[int] = None

    def __enter__(self):
        self._progress = Progress(
            SpinnerColumn(style="cyan"),
            BarColumn(bar_width=None, style="cyan"),
            TimeElapsedColumn(),
            TextColumn("[progress.description]{task.description}", style="white")
        )

        def runner():
            with self._progress:
                self._task_id = self._progress.add_task(self.description, total=100)
                progress_value = 0
                while not self._stop_event.is_set():
                    if self._task_id is not None:
                        progress_value = (progress_value + 2) % 100
                        self._progress.update(self._task_id, completed=progress_value)
                    time.sleep(0.1)

        self._thread = threading.Thread(target=runner, daemon=True)
        self._thread.start()
        self._start = time.perf_counter()
        return self

    def __exit__(self, exc_type, exc, tb):
        if self._start is None:
            self.elapsed = 0.0
        else:
            self.elapsed = time.perf_counter() - self._start
        self._stop_event.set()
        if self._thread is not None:
            self._thread.join()
        if self._progress and self._task_id is not None:
            try:
                self._progress.update(self._task_id, completed=100)
            except Exception:
                pass

        if exc_type is None:
            console.print(f"[green]✅ {self.description} completed in {self.elapsed:.2f}s[/green]")
        else:
            console.print(f"[red]❌ {self.description} failed after {self.elapsed:.2f}s[/red]")
        return False


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
    console.print("\n[bold]📋 Demo 1: Wallet Creation & Management[/bold]")
    console.print("=" * 80)
    
    from chaoschain_sdk import ChaosChainAgentSDK, NetworkConfig
    from chaoschain_sdk.types import AgentRole
    
    # Create SDK instance (auto-creates wallet)
    console.print("🔧 Creating ChaosChain Agent SDK...")
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
    
    console.print(f"✅ Wallet created!")
    console.print(f"   Address: [green]{sdk.wallet_address}[/green]")
    console.print(f"   Network: [cyan]Ethereum Sepolia[/cyan]")
    # Show wallet info table
    table = Table(title="Wallet Details")
    table.add_column("Property", style="cyan")
    table.add_column("Value", style="green")
    table.add_row("Address", sdk.wallet_address)
    table.add_row("Network", "Ethereum Sepolia (Chain ID: 11155111)")

    # Get balance from wallet manager
    try:
        balance = sdk.wallet_manager.w3.eth.get_balance(sdk.wallet_address)
        balance_eth = sdk.wallet_manager.w3.from_wei(balance, 'ether')
        table.add_row("Balance", f"{balance_eth:.4f} ETH")
    except Exception as e:
        table.add_row("Balance", f"Unable to fetch ({e})")
    
    console.print(table)
    
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
    console.print("\n[bold]📋 Demo 2: ERC-8004 Identity Registration[/bold]")
    console.print("=" * 80)
    
    from chaoschain_sdk.types import AgentRole
    
    console.print("🔧 Registering agent on ERC-8004 IdentityRegistry...")
    
    existing_agent_id = None
    try:
        with WaitBar("Checking existing registration") as wait_check:
            existing_agent_id = sdk.chaos_agent.get_agent_id()
        if existing_agent_id:
            console.print("✅ Agent already registered on-chain!")
            console.print(f"   Agent ID: [green]{existing_agent_id}[/green]")
            console.print(f"   Wallet: [cyan]{sdk.wallet_address}[/cyan]")
            record_result(
                "Agent Registration",
                "Using existing",
                latency=wait_check.elapsed,
                notes=f"Agent ID: {existing_agent_id}",
                agent_name=sdk.agent_name,
                agent_wallet=sdk.wallet_address
            )
            return existing_agent_id
    except Exception as check_error:
        console.print(f"[yellow]⚠️  Could not verify existing registration: {check_error}[/yellow]")
    
    try:
        # Register agent with metadata (ERC-8004 v1.0 compliant - new in v0.2.3!)
        metadata = {
            "agentName": sdk.agent_name.encode('utf-8'),
            "agentDomain": sdk.agent_domain.encode('utf-8')
        }
        
        with WaitBar("Submitting ERC-8004 registration transaction") as wait:
            agent_id, tx_hash = sdk.chaos_agent.register_agent(
                token_uri="ipfs://QmDemo123",
                metadata=metadata  # NEW: Metadata support!
            )
        
        if tx_hash == "already_registered":
            console.print("✅ Agent already registered with metadata on-chain!")
            console.print(f"   Wallet: [cyan]{sdk.wallet_address}[/cyan]")
            record_result(
                "Agent Registration",
                "Already registered",
                latency=wait.elapsed,
                notes=f"Wallet: {sdk.wallet_address}",
                agent_name=sdk.agent_name,
                agent_wallet=sdk.wallet_address
            )
            return agent_id
        
        console.print(f"✅ Agent registered with metadata!")
        console.print(f"   Transaction: [green]{tx_hash}[/green]")
        console.print(f"   Agent ID: [green]{agent_id}[/green]")
        console.print(f"   Metadata URI: [cyan]ipfs://QmDemo123[/cyan]")
        console.print(f"   On-chain Metadata: [yellow]{len(metadata)} entries[/yellow]")
        
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
        
        return agent_id
        
    except Exception as e:
        latency = locals().get("wait").elapsed if "wait" in locals() and getattr(locals().get("wait"), "elapsed", None) else None
        error_str = str(e).lower()
        if "insufficient funds" in error_str or "balance 0" in error_str:
            console.print("⚠️  Wallet needs testnet ETH for gas fees")
            console.print(f"   Wallet: [cyan]{sdk.wallet_address}[/cyan]")
            console.print(f"   Balance: [yellow]0.0000 ETH[/yellow]")
        elif "already registered" in error_str or "revert" in error_str:
            console.print("✅ Agent already registered!")
            console.print(f"   Wallet: [cyan]{sdk.wallet_address}[/cyan]")
        else:
            console.print(f"⚠️  Registration error: {e}")
        
        record_result(
            "Agent Registration",
            "Failed",
            latency=latency,
            notes=str(e),
            agent_name=sdk.agent_name,
            agent_wallet=sdk.wallet_address
        )
        
        console.print("\n[bold]💰 To register on-chain:[/bold]")
        console.print("   1. Get testnet ETH: [cyan]https://sepoliafaucet.com/[/cyan]")
        console.print(f"   2. Send to: [green]{sdk.wallet_address}[/green]")
        console.print("   3. Run this demo again")
        return None


def demo_2b_metadata(sdk, agent_id):
    """Demo 2b: ERC-8004 on-chain metadata (NEW in v0.2.3!)."""
    if not agent_id:
        console.print("\n[bold]📋 Demo 2b: ERC-8004 On-Chain Metadata[/bold]")
        console.print("=" * 80)
        console.print("⚠️  Skipped - agent not registered")
        return
    
    console.print("\n[bold]📋 Demo 2b: ERC-8004 On-Chain Metadata (NEW!)[/bold]")
    console.print("=" * 80)
    
    console.print("🔧 Setting additional metadata...")
    
    try:
        # Set additional metadata (requires testnet tokens)
        with WaitBar("Submitting metadata update transaction") as wait:
            tx_hash = sdk.chaos_agent.set_agent_metadata("version", b"1.0.0")
        console.print("✅ Metadata set successfully!")
        
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
        console.print("\n🔧 Reading on-chain metadata...")
        name = sdk.chaos_agent.get_agent_metadata("agentName")
        domain = sdk.chaos_agent.get_agent_metadata("agentDomain")
        version = sdk.chaos_agent.get_agent_metadata("version")
        
        console.print(f"✅ Metadata retrieved!")
        console.print(f"   Name: [green]{name.decode('utf-8')}[/green]")
        console.print(f"   Domain: [cyan]{domain.decode('utf-8')}[/cyan]")
        console.print(f"   Version: [yellow]{version.decode('utf-8')}[/yellow]")
        
    except Exception as e:
        latency = locals().get("wait").elapsed if "wait" in locals() and getattr(locals().get("wait"), "elapsed", None) else None
        error_str = str(e).lower()
        if "insufficient funds" in error_str:
            console.print("⚠️  Setting metadata requires testnet ETH (reading is free)")
        else:
            console.print(f"⚠️  Metadata operations: {e}")
        
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
    console.print("\n[bold]📋 Demo 3: Local IPFS Storage[/bold]")
    console.print("=" * 80)
    
    console.print("🔧 Testing local IPFS storage...")
    
    # Create test data
    test_data = {
        "message": "Hello from ChaosChain SDK!",
        "timestamp": datetime.now().isoformat(),
        "demo": "ethereum_install"
    }
    
    start_time = time.perf_counter()
    try:
        # Store data
        console.print("📤 Storing data to local IPFS...")
        import json
        result = sdk.storage_manager.put(json.dumps(test_data).encode())
        
        if result.success:
            console.print(f"✅ Data stored!")
            console.print(f"   URI: [green]{result.uri}[/green]")
            
            # Retrieve data
            console.print("📥 Retrieving data from local IPFS...")
            retrieved = sdk.storage_manager.get(result.uri)
            
            if retrieved:
                console.print("✅ Data retrieved successfully!")
                record_result(
                    "Local IPFS Storage",
                    "Success",
                    latency=time.perf_counter() - start_time,
                    notes=f"URI: {result.uri}"
                )
            else:
                console.print("⚠️  Could not retrieve data")
                record_result(
                    "Local IPFS Storage",
                    "Failed",
                    latency=time.perf_counter() - start_time,
                    notes="Retrieval returned empty result"
                )
        else:
            console.print(f"⚠️  Storage failed: {result.error}")
            record_result(
                "Local IPFS Storage",
                "Failed",
                latency=time.perf_counter() - start_time,
                notes=str(result.error)
            )
            
    except Exception as e:
        console.print(f"⚠️  Local IPFS not running: {e}")
        console.print("   To enable: install IPFS Desktop or run `ipfs daemon`")
        console.print("   Download: https://docs.ipfs.tech/install/")
        record_result(
            "Local IPFS Storage",
            "Failed",
            latency=time.perf_counter() - start_time,
            notes=str(e)
        )


def demo_4_process_integrity():
    """Demo 4: Process integrity verification."""
    console.print("\n[bold]📋 Demo 4: Process Integrity Verification[/bold]")
    console.print("=" * 80)
    
    from chaoschain_sdk import ChaosChainAgentSDK, NetworkConfig
    from chaoschain_sdk.types import AgentRole
    
    console.print("🔧 Creating SDK with process integrity enabled...")
    
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
    
    console.print("✅ Process integrity verifier initialized!")
    console.print(f"   Agent: [cyan]{sdk.agent_name}[/cyan]")
    console.print(f"   Verifier: [green]Local ChaosChain Process Integrity[/green]")
    
    console.print("\n[dim]Note: Process integrity generates cryptographic proofs for function executions[/dim]")
    console.print("[dim]      This ensures transparency and verifiability of AI agent operations[/dim]")
    
    record_result(
        "Process Integrity Setup",
        "Success",
        latency=latency,
        notes="Integrity verifier active"
    )


def demo_5_x402_payments():
    """Demo 5: x402 payment protocol."""
    console.print("\n[bold]📋 Demo 5: x402 Payment Protocol (Coinbase)[/bold]")
    console.print("=" * 80)
    
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
    
    console.print("✅ x402 Payment Manager initialized!")
    console.print(f"   Protocol: [cyan]Coinbase x402 v0.2.1+[/cyan]")
    console.print(f"   Token: [yellow]USDC (ERC-20)[/yellow]")
    console.print(f"   Treasury: [green]0x20E7B2A2c8969725b88Dd3EF3a11Bc3353C83F70[/green]")
    
    payer_agent = os.environ.get("X402_PAYER_AGENT", "DemoAgent")
    payment_amount = float(os.environ.get("X402_PAYMENT_AMOUNT_USDC", "0.001"))
    total_runs = int(os.environ.get("X402_PAYMENT_COUNT", "3"))

    console.print(f"\n💳 Payer agent: [cyan]{payer_agent}[/cyan]")
    console.print(f"🪙 Payment amount per run: [yellow]{payment_amount:.3f} USDC[/yellow]")
    console.print(f"🔁 Total runs: [cyan]{total_runs}[/cyan]")
    
    payment_manager = getattr(sdk, "payment_manager", None)
    if not payment_manager:
        console.print("[red]❌ Payment manager unavailable[/red]")
        record_result(
            "x402 Payment Execution",
            "Failed",
            latency=None,
            notes="Payment manager unavailable",
            agent_name=payer_agent,
            agent_wallet=sdk.wallet_manager.get_wallet_address(payer_agent)
        )
        return
    
    for run_index in range(1, total_runs + 1):
        console.print(f"\n[bold]🔧 Payment {run_index}/{total_runs}[/bold]")
        payment_proof = None
        payment_latency: Optional[float] = None
        last_error: Optional[Exception] = None

        console.print("   Creating x402 payment request...")
        try:
            if getattr(sdk, "a2a_x402", None):
                w3c_payment_request = sdk.create_x402_payment_request(
                    cart_id=f"demo-{int(time.time())}-{run_index}",
                    total_amount=payment_amount,
                    currency="USDC",
                    items=[{"name": f"ChaosChain Demo Service #{run_index}", "price": payment_amount}],
                    settlement_address=sdk.wallet_address
                )
                console.print(f"   Request ID: [cyan]{w3c_payment_request.id}[/cyan]")
                console.print(f"   Settlement address: [green]{w3c_payment_request.settlement_address}[/green]")
            else:
                console.print("   Using payment manager directly (no W3C wrapper)")
            
            manager_request = payment_manager.create_x402_payment_request(
                from_agent=payer_agent,
                to_agent=sdk.agent_name,
                amount=payment_amount,
                currency="USDC",
                service_description=f"Demo payment via x402 (run {run_index})"
            )
            
            with WaitBar(f"Executing x402 payment #{run_index} ({payment_amount:.3f} USDC)") as wait:
                payment_proof = payment_manager.execute_x402_payment(manager_request)
            payment_latency = wait.elapsed
        except PaymentError as e:
            console.print(f"[yellow]⚠️  x402 payment attempt failed: {e}[/yellow]")
            last_error = e
        except Exception as generic_error:
            console.print(f"[red]❌ Unexpected error during x402 payment: {generic_error}[/red]")
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
            console.print("[red]❌ Payment aborted[/red]")
            continue
        
        console.print("[green]✅ x402 payment executed on-chain![/green]")
        console.print(f"   Payment amount: [green]{payment_amount:.3f} USDC[/green]")
        
        main_tx = payment_proof.transaction_hash
        fee_tx = payment_proof.receipt_data.get("protocol_fee_tx") if payment_proof.receipt_data else None
        console.print(f"   Main payment tx: [green]{main_tx}[/green]")
        if fee_tx:
            console.print(f"   Protocol fee tx: [cyan]{fee_tx}[/cyan]")
        
        try:
            main_receipt = sdk.wallet_manager.w3.eth.get_transaction_receipt(main_tx)
        except Exception as receipt_error:
            console.print(f"[yellow]⚠️  Could not fetch main payment receipt: {receipt_error}[/yellow]")
            main_receipt = None
        
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


def print_summary():
    """Print demo summary."""
    console.print("\n" + "=" * 80)
    console.print("[bold green]🎉 Ethereum Install Demo Complete![/bold green]\n")
    
    if demo_results:
        metrics_table = Table(title="Demo Execution Metrics", show_lines=False)
        metrics_table.add_column("Step", style="cyan")
        metrics_table.add_column("Status", style="green")
        metrics_table.add_column("Agent", style="magenta")
        metrics_table.add_column("Wallet", style="yellow")
        metrics_table.add_column("Latency (s)", justify="right")
        metrics_table.add_column("Gas Used", justify="right")
        metrics_table.add_column("Gas Price (gwei)", justify="right")
        metrics_table.add_column("Gas Cost (ETH)", justify="right")
        metrics_table.add_column("Tx Hash", overflow="fold")
        metrics_table.add_column("Notes", overflow="fold")
        
        for result in demo_results:
            latency = f"{result.latency:.2f}" if result.latency is not None else "-"
            gas_used = f"{result.gas_used:,}" if result.gas_used is not None else "-"
            gas_price = f"{result.gas_price_gwei:.2f}" if result.gas_price_gwei is not None else "-"
            gas_cost = f"{result.gas_cost_eth:.6f}" if result.gas_cost_eth is not None else "-"
            tx_hash = result.tx_hash or "-"
            notes = result.notes or "-"
            agent = result.agent_name or "-"
            wallet = result.agent_wallet or "-"
            
            metrics_table.add_row(
                result.name,
                result.status,
                agent,
                wallet,
                latency,
                gas_used,
                tx_hash,
                notes
            )
        
        console.print()
        console.print(metrics_table)
    
    console.print()


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
            console.print("\n[bold]🛑 Skipping on-chain registration (DEMO_REGISTER_AGENT=false)[/bold]")
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
