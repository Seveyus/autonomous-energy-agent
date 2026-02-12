# skale_payment.py
import os
from web3 import Web3

RPC_URL = "https://base-sepolia-testnet.skalenodes.com/v1/bite-v2-sandbox-2"
CHAIN_ID = 103698795

PRIVATE_KEY = os.getenv("PRIVATE_KEY")
if not PRIVATE_KEY:
    raise ValueError("❌ PRIVATE_KEY non définie. Exécute : export PRIVATE_KEY='ta_clé'")

w3 = Web3(Web3.HTTPProvider(RPC_URL))
if not w3.is_connected():
    raise ConnectionError("❌ Impossible de se connecter à SKALE RPC")

account = w3.eth.account.from_key(PRIVATE_KEY)
address = account.address


def send_payment(to_address: str, amount_ether: float = 0.001):
    nonce = w3.eth.get_transaction_count(address)
    amount_wei = w3.to_wei(amount_ether, 'ether')

    tx = {
        'nonce': nonce,
        'to': w3.to_checksum_address(to_address),
        'value': amount_wei,
        'gas': 21000,
        'gasPrice': w3.to_wei('0.1', 'gwei'),
        'chainId': CHAIN_ID
    }

    signed_tx = account.sign_transaction(tx)
    tx_hash = w3.eth.send_raw_transaction(signed_tx.raw_transaction)

    # wait receipt for demo reliability
    w3.eth.wait_for_transaction_receipt(tx_hash)
    return tx_hash
