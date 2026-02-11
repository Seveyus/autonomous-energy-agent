# skale_payment.py
import os
from web3 import Web3

# ===== CONFIG SKALE BITE V2 SANDBOX 2 =====
RPC_URL = "https://base-sepolia-testnet.skalenodes.com/v1/bite-v2-sandbox-2"
CHAIN_ID = 103698795

# Clé privée depuis variable d'environnement (NE JAMAIS COMMITTER)
PRIVATE_KEY = os.getenv("PRIVATE_KEY")
if not PRIVATE_KEY:
    raise ValueError("❌ PRIVATE_KEY non définie. Exécute : export PRIVATE_KEY='ta_clé'")

# Connexion Web3
w3 = Web3(Web3.HTTPProvider(RPC_URL))
if not w3.is_connected():
    raise ConnectionError("❌ Impossible de se connecter à SKALE RPC")

# Compte
account = w3.eth.account.from_key(PRIVATE_KEY)
address = account.address

print(f"✅ Connecté à SKALE (Chain ID: {w3.eth.chain_id})")
print(f"👛 Adresse : {address}")
print(f"💰 Solde   : {w3.from_wei(w3.eth.get_balance(address), 'ether')} sFUEL\n")

def send_payment(to_address: str, amount_ether: float = 0.001):
    """
    Envoie un paiement sur SKALE
    """
    nonce = w3.eth.get_transaction_count(address)
    amount_wei = w3.to_wei(amount_ether, 'ether')

    tx = {
        'nonce': nonce,
        'to': w3.to_checksum_address(to_address),
        'value': amount_wei,
        'gas': 21000,
        'gasPrice': w3.to_wei('0.1', 'gwei'),  # SKALE = gaz très bas
        'chainId': CHAIN_ID
    }

    signed_tx = account.sign_transaction(tx)
    tx_hash = w3.eth.send_raw_transaction(signed_tx.raw_transaction)
    
    # Attendre la confirmation
    tx_receipt = w3.eth.wait_for_transaction_receipt(tx_hash)
    
    print(f"✅ Transaction confirmée !")
    print(f"🔗 Hash    : {w3.to_hex(tx_hash)}")
    print(f"📊 Statut  : {'Succès' if tx_receipt.status == 1 else 'Échec'}")
    print(f"🌐 Explorer: https://base-sepolia-testnet-explorer.skalenodes.com:10032/tx/{w3.to_hex(tx_hash)}")
    
    return tx_hash

if __name__ == "__main__":
    # Envoie 0.001 sFUEL à toi-même (démo simple)
    send_payment(address, 0.001)