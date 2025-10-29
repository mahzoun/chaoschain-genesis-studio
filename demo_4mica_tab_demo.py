#!/usr/bin/env python3
"""
ChaosChain SDK - 4Mica Tab Payment Demo
=======================================

Demonstrates 4Mica's guaranteed payment flow:
    1. Approve and deposit ERC20 collateral (e.g. USDC)
    2. Create a tab through the 4Mica operator
    3. Sign a payment guarantee (EIP-712)
    4. Obtain and verify the operator's BLS certificate
"""

import binascii
import json
import os
import sys
import time
import uuid
import warnings
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from rich.console import Console

warnings.filterwarnings("ignore", message=".*MismatchedABI.*")
warnings.filterwarnings("ignore", message=".*encountered the following error during processing.*")

console = Console()

DEFAULT_FOURMICA_SETTINGS = {
    "rpc_url": "http://localhost:8545",
    "contract_address": "0xccccfbf08b27fa867b7ed2d6175679c2caeb1c79",
    "operator_url": "http://localhost:3000",
    "payer_private_key": "0xac0974bec39a17e36ba4a6b4d238ff944bacb478cbed5efcae784d7bf4f2ff80",
    "recipient_address": "0xf39Fd6e51aad88F6F4ce6aB8827279cffFb92266",
    "payment_amount_wei": "20000000000000",
    "tab_ttl_seconds": "3600",
    "asset_address": "0x1c7D4B196Cb0C7B01d743Fbc6116a902379C7238",
}

ERC20_ABI = [
    {
        "constant": True,
        "inputs": [{"name": "account", "type": "address"}],
        "name": "balanceOf",
        "outputs": [{"name": "", "type": "uint256"}],
        "stateMutability": "view",
        "type": "function",
    },
    {
        "constant": True,
        "inputs": [
            {"name": "owner", "type": "address"},
            {"name": "spender", "type": "address"},
        ],
        "name": "allowance",
        "outputs": [{"name": "", "type": "uint256"}],
        "stateMutability": "view",
        "type": "function",
    },
    {
        "constant": False,
        "inputs": [
            {"name": "spender", "type": "address"},
            {"name": "value", "type": "uint256"},
        ],
        "name": "approve",
        "outputs": [{"name": "", "type": "bool"}],
        "stateMutability": "nonpayable",
        "type": "function",
    },
    {
        "constant": False,
        "inputs": [
            {"name": "recipient", "type": "address"},
            {"name": "amount", "type": "uint256"},
        ],
        "name": "transfer",
        "outputs": [{"name": "", "type": "bool"}],
        "stateMutability": "nonpayable",
        "type": "function",
    },
]


@dataclass
class FourMicaConfig:
    rpc_url: str
    contract_address: str
    operator_url: str
    payer_private_key: str
    recipient_address: str
    payment_amount_wei: int
    tab_ttl_seconds: Optional[int]
    artifact_path: Path
    asset_address: str


def _parse_int(value: str) -> int:
    value = value.strip()
    base = 16 if value.lower().startswith("0x") else 10
    return int(value, base)


def _decode_hex_bytes(value) -> bytes:
    if isinstance(value, (bytes, bytearray)):
        return bytes(value)
    if isinstance(value, list):
        return bytes(value)
    if isinstance(value, str):
        cleaned = value[2:] if value.lower().startswith("0x") else value
        return binascii.unhexlify(cleaned)
    raise TypeError(f"Unsupported value type for hex decoding: {type(value)!r}")


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
        if not key:
            continue
        value = value.strip()
        if ((value.startswith('"') and value.endswith('"')) or (value.startswith("'") and value.endswith("'"))):
            value = value[1:-1]
        os.environ.setdefault(key, value)


def _build_tx_params(w3, address: str, gas_limit: int) -> dict:
    latest_block = w3.eth.get_block("latest")
    base_fee = latest_block.get("baseFeePerGas")
    priority_fee = w3.to_wei(os.getenv("FOURMICA_PRIORITY_FEE_GWEI", "1"), "gwei")

    params = {
        "from": address,
        "nonce": w3.eth.get_transaction_count(address, "pending"),
        "gas": gas_limit,
        "chainId": w3.eth.chain_id,
    }

    if base_fee is None:
        params["gasPrice"] = w3.eth.gas_price
    else:
        params["maxPriorityFeePerGas"] = priority_fee
        params["maxFeePerGas"] = base_fee + priority_fee

    return params


def load_4mica_config_from_env() -> tuple[Optional[FourMicaConfig], list[str]]:
    errors: list[str] = []

    rpc_url = os.getenv("FOURMICA_ETH_RPC_URL") or os.getenv("RPC_URL") or DEFAULT_FOURMICA_SETTINGS["rpc_url"]
    contract_address = (
        os.getenv("FOURMICA_CONTRACT_ADDRESS")
        or os.getenv("CONTRACT_ADDRESS")
        or DEFAULT_FOURMICA_SETTINGS["contract_address"]
    )
    operator_url = (
        os.getenv("FOURMICA_OPERATOR_URL")
        or os.getenv("OPERATOR_URL")
        or DEFAULT_FOURMICA_SETTINGS["operator_url"]
    )
    payer_private_key = (
        os.getenv("FOURMICA_PAYER_PRIVATE_KEY")
        or os.getenv("FOURMICA_USER_PRIVATE_KEY")
        or os.getenv("PRIVATE_KEY")
        or DEFAULT_FOURMICA_SETTINGS["payer_private_key"]
    )
    recipient_address = (
        os.getenv("FOURMICA_RECIPIENT_ADDRESS")
        or os.getenv("RECIPIENT_ADDRESS")
        or DEFAULT_FOURMICA_SETTINGS["recipient_address"]
    )
    asset_address = (
        os.getenv("FOURMICA_ASSET_ADDRESS")
        or os.getenv("USDC_CONTRACT_ADDRESS")
        or DEFAULT_FOURMICA_SETTINGS["asset_address"]
    )
    if not asset_address:
        errors.append("Set FOURMICA_ASSET_ADDRESS (ERC20 token address for collateral).")

    amount_wei_env = os.getenv("FOURMICA_PAYMENT_AMOUNT_WEI", DEFAULT_FOURMICA_SETTINGS["payment_amount_wei"])
    try:
        payment_amount_wei = _parse_int(amount_wei_env)
    except Exception:
        errors.append(f"Invalid FOURMICA_PAYMENT_AMOUNT_WEI: {amount_wei_env}")
        payment_amount_wei = 0

    ttl_env = os.getenv("FOURMICA_TAB_TTL_SECONDS", DEFAULT_FOURMICA_SETTINGS["tab_ttl_seconds"])
    tab_ttl_seconds = None
    if ttl_env:
        try:
            tab_ttl_seconds = int(ttl_env)
        except ValueError:
            errors.append(f"Invalid FOURMICA_TAB_TTL_SECONDS: {ttl_env}")

    artifact_default = "~/4mica-core/contracts/out/Core4Mica.sol/Core4Mica.json"
    artifact_path_str = os.getenv("FOURMICA_CORE_ARTIFACT", artifact_default)
    artifact_path = Path(os.path.expanduser(artifact_path_str))
    if not artifact_path.exists():
        errors.append(f"Core4Mica artifact not found at {artifact_path}")

    if payment_amount_wei <= 0:
        errors.append("Payment amount must be greater than zero.")

    if errors:
        return None, errors

    return (
        FourMicaConfig(
            rpc_url=rpc_url,
            contract_address=contract_address,
            operator_url=operator_url,
            payer_private_key=payer_private_key,
            recipient_address=recipient_address,
            payment_amount_wei=payment_amount_wei,
            tab_ttl_seconds=tab_ttl_seconds,
            artifact_path=artifact_path,
            asset_address=asset_address,
        ),
        [],
    )


def print_header():
    console.print(
        "\n[bold cyan]CHAOSCHAIN SDK - 4Mica Tab Payment Demo[/bold cyan]\n"
        "  ✅ ERC20 deposit\n"
        "  ✅ Tab creation\n"
        "  ✅ Guarantee signing & verification\n"
    )


def demo_4mica_payment():
    load_env_file()

    try:
        import httpx
        from eth_account import Account
        from eth_account.messages import encode_typed_data
        from eth_utils import to_checksum_address
        from py_ecc.bls import G2Basic as bls
        from web3 import Web3
        from web3.middleware import geth_poa_middleware  # type: ignore
    except ImportError as exc:
        console.print(f"[red]❌ Missing dependency: {exc.name}[/red]")
        console.print("   pip install web3 httpx eth-account py-ecc")
        sys.exit(1)

    config, errors = load_4mica_config_from_env()
    if errors or config is None:
        console.print("[red]❌ 4Mica configuration errors:[/red]")
        for err in errors:
            console.print(f"   • {err}")
        sys.exit(1)

    w3 = Web3(Web3.HTTPProvider(config.rpc_url))
    if not w3.is_connected():
        console.print(f"[red]❌ Unable to connect to Ethereum RPC at {config.rpc_url}[/red]")
        sys.exit(1)

    try:
        w3.middleware_onion.inject(geth_poa_middleware, layer=0)
    except Exception:
        pass

    with config.artifact_path.open("r", encoding="utf-8") as fh:
        artifact = json.load(fh)
    contract = w3.eth.contract(
        address=Web3.to_checksum_address(config.contract_address),
        abi=artifact["abi"],
    )

    erc20 = w3.eth.contract(
        address=Web3.to_checksum_address(config.asset_address),
        abi=ERC20_ABI,
    )

    payer_account = Account.from_key(config.payer_private_key)
    payer_address = to_checksum_address(payer_account.address)
    recipient_address = to_checksum_address(config.recipient_address)

    console.print(f"\n🔑 Payer: [cyan]{payer_address}[/cyan]")
    console.print(f"🎯 Recipient: [cyan]{recipient_address}[/cyan]")
    console.print(f"💰 Collateral asset: [cyan]{config.asset_address}[/cyan]")
    console.print(f"💵 Payment amount (token units): [green]{config.payment_amount_wei}[/green]")

    balance = erc20.functions.balanceOf(payer_address).call()
    console.print(f"   ERC20 balance: [cyan]{balance} token units[/cyan]")
    if balance < config.payment_amount_wei:
        console.print("[red]❌ Insufficient ERC20 balance for deposit[/red]")
        sys.exit(1)

    allowance = erc20.functions.allowance(payer_address, config.contract_address).call()
    if allowance < config.payment_amount_wei:
        console.print("[cyan]🔄 Approving ERC20 allowance...[/cyan]")
        approve_params = _build_tx_params(w3, payer_address, 80_000)
        approve_tx = erc20.functions.approve(
            config.contract_address, config.payment_amount_wei
        ).build_transaction(approve_params)
        signed_approve = payer_account.sign_transaction(approve_tx)
        approve_hash = w3.eth.send_raw_transaction(signed_approve.rawTransaction)
        w3.eth.wait_for_transaction_receipt(approve_hash)
        console.print(f"[green]✅ Approval confirmed[/green] [dim]{approve_hash.hex()}[/dim]")

    console.print("[cyan]🏦 Depositing collateral via depositStablecoin...[/cyan]")
    deposit_params = _build_tx_params(w3, payer_address, 200_000)
    deposit_tx = contract.functions.depositStablecoin(
        Web3.to_checksum_address(config.asset_address),
        config.payment_amount_wei,
    ).build_transaction(deposit_params)
    signed_deposit = payer_account.sign_transaction(deposit_tx)
    deposit_hash = w3.eth.send_raw_transaction(signed_deposit.rawTransaction)
    deposit_receipt = w3.eth.wait_for_transaction_receipt(deposit_hash)
    console.print(f"[green]✅ Collateral deposited[/green] [dim]{deposit_hash.hex()}[/dim]")

    collateral = contract.functions.getUser(payer_address).call()
    console.print(f"   Collateral stored: [cyan]{collateral[0]}[/cyan]")

    def operator_call(method: str, params=None):
        payload = {
            "jsonrpc": "2.0",
            "id": str(uuid.uuid4()),
            "method": method,
            "params": params or [],
        }
        response = httpx.post(config.operator_url, json=payload, timeout=20.0)
        response.raise_for_status()
        data = response.json()
        if "error" in data:
            raise RuntimeError(data["error"])
        return data["result"]

    public_params = operator_call("core_getPublicParams")

    tab_request = {
        "user_address": payer_address,
        "recipient_address": recipient_address,
        "erc20_token": config.asset_address,
    }
    if config.tab_ttl_seconds is not None:
        tab_request["ttl"] = config.tab_ttl_seconds

    tab_result = operator_call("core_createPaymentTab", [tab_request])
    tab_id_raw = tab_result.get("id")
    tab_id_int = _parse_int(tab_id_raw) if isinstance(tab_id_raw, str) else int(tab_id_raw)
    console.print(f"\n🧾 Tab created: [cyan]{tab_id_raw}[/cyan]")

    timestamp = int(time.time())
    req_id_int = 0

    claims_payload = {
        "user_address": payer_address,
        "recipient_address": recipient_address,
        "tab_id": tab_id_raw if isinstance(tab_id_raw, str) else hex(tab_id_int),
        "req_id": str(req_id_int),
        "amount": str(config.payment_amount_wei),
        "timestamp": timestamp,
        "asset_address": config.asset_address,
    }

    chain_id = public_params.get("chain_id")
    if isinstance(chain_id, str):
        chain_id = _parse_int(chain_id)

    typed_data = {
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
            "name": public_params.get("eip712_name", "4Mica"),
            "version": public_params.get("eip712_version", "1"),
            "chainId": chain_id or w3.eth.chain_id,
        },
        "message": {
            "user": payer_address,
            "recipient": recipient_address,
            "tabId": tab_id_int,
            "reqId": req_id_int,
            "amount": config.payment_amount_wei,
            "timestamp": timestamp,
        },
    }

    typed_message = encode_typed_data(full_message=typed_data)
    signed = payer_account.sign_message(typed_message)

    guarantee = operator_call(
        "core_issueGuarantee",
        [
            {
                "claims": claims_payload,
                "signature": signed.signature.hex(),
                "scheme": "eip712",
            }
        ],
    )

    public_key_bytes = _decode_hex_bytes(public_params.get("public_key"))
    signature_bytes = _decode_hex_bytes(guarantee.get("signature"))
    claims_bytes = _decode_hex_bytes(guarantee.get("claims"))

    bls_valid = bls.Verify(public_key_bytes, claims_bytes, signature_bytes)

    status = contract.functions.getPaymentStatus(tab_id_int).call()

    console.print("\n[bold green]✅ Guarantee issued[/bold green]")
    console.print(f"   Tab ID: [cyan]{tab_id_raw}[/cyan]")
    console.print(f"   Amount: [green]{config.payment_amount_wei} wei[/green]")
    console.print(f"   Asset: [cyan]{config.asset_address}[/cyan]")
    console.print(f"   BLS Valid: {'✅' if bls_valid else '❌'}")
    console.print(f"   Paid (on-chain): {status[0]}")
    console.print(f"   Remunerated: {status[1]}")

    guarantee_path = Path("guarantee.json")
    guarantee_payload = {
        "claims": claims_payload,
        "signature": guarantee.get("signature"),
        "claims_bytes": guarantee.get("claims"),
        "timestamp": timestamp,
    }
    guarantee_path.write_text(json.dumps(guarantee_payload, indent=2), encoding="utf-8")
    console.print(f"\n[green]📄 Guarantee saved to {guarantee_path}[/green]")


def main():
    try:
        print_header()
        demo_4mica_payment()
    except KeyboardInterrupt:
        console.print("\n[yellow]Demo interrupted by user[/yellow]")
        sys.exit(0)
    except Exception as exc:
        console.print(f"\n[red]❌ Demo error: {exc}[/red]")
        raise


if __name__ == "__main__":
    main()
