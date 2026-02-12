# skale_payment.py
import os
from web3 import Web3

RPC_URL = os.getenv("SKALE_RPC_URL", "https://base-sepolia-testnet.skalenodes.com/v1/bite-v2-sandbox-2")
CHAIN_ID = int(os.getenv("SKALE_CHAIN_ID", "103698795"))

PRIVATE_KEY = os.getenv("PRIVATE_KEY")

w3 = Web3(Web3.HTTPProvider(RPC_URL))
if not w3.is_connected():
    raise ConnectionError("❌ Impossible de se connecter à SKALE RPC")

# Mode “read-only” si pas de clé
SKALE_PAYMENTS_ENABLED = bool(PRIVATE_KEY)

if SKALE_PAYMENTS_ENABLED:
    account = w3.eth.account.from_key(PRIVATE_KEY)
    address = account.address
else:
    address = "0x0000000000000000000000000000000000000000"

def send_payment(to_address: str, amount_ether: float = 0.001):
    """
    Envoie un paiement sur SKALE (si PRIVATE_KEY présente).
    """
    if not SKALE_PAYMENTS_ENABLED:
        raise RuntimeError("SKALE payments disabled (PRIVATE_KEY missing)")

    nonce = w3.eth.get_transaction_count(address)
    amount_wei = w3.to_wei(amount_ether, "ether")

    tx = {
        "nonce": nonce,
        "to": w3.to_checksum_address(to_address),
        "value": amount_wei,
        "gas": 21000,
        "gasPrice": w3.to_wei("0.1", "gwei"),
        "chainId": CHAIN_ID,
    }

    signed_tx = account.sign_transaction(tx)
    tx_hash = w3.eth.send_raw_transaction(signed_tx.raw_transaction)
    tx_receipt = w3.eth.wait_for_transaction_receipt(tx_hash)

    if tx_receipt.status != 1:
        raise RuntimeError("Transaction failed on-chain")

    return tx_hash
