from fastapi import FastAPI
from environment import get_environment_state
from agent import decide_action, get_premium_data
from fastapi import HTTPException
from uuid import uuid4
from skale_payment import send_payment, address



app = FastAPI()

agent_budget = 1.0  # € initial

@app.get("/run")
def run_agent():
    global agent_budget

    state = get_environment_state()
    decision = decide_action(state, agent_budget)

    if decision == "buy_premium_data":
        agent_budget -= 0.05
        premium_data = get_premium_data()
    else:
        premium_data = None


    return {
    "environment": state,
    "decision": decision,
    "premium_data": premium_data,
    "remaining_budget": agent_budget
    }


# stockage simple des paiements validés
valid_payments = set()

@app.get("/premium-weather")
def premium_weather(tx_hash: str = None):

    if tx_hash not in valid_transactions:
        raise HTTPException(status_code=402, detail="Payment Required")

    return {
        "solar_production_precise": 85.0
    }

@app.post("/pay")
def make_payment():

    payment_id = str(uuid4())
    valid_payments.add(payment_id)

    return {
        "status": "payment_successful",
        "payment_id": payment_id
    }


valid_transactions = set()

@app.post("/x402/pay")
def x402_pay():

    tx_hash = send_payment(address, 0.001)
    tx_hash_hex = tx_hash.hex()

    valid_transactions.add(tx_hash_hex)

    return {
        "status": "paid",
        "tx_hash": tx_hash_hex,
        "explorer": f"https://base-sepolia-testnet-explorer.skalenodes.com:10032/tx/{tx_hash_hex}"
    }
