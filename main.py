from fastapi import FastAPI
from environment import get_environment_state
from agent import decide_action, get_premium_data
from fastapi import HTTPException
from uuid import uuid4


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
def premium_weather(payment_id: str = None):

    if payment_id not in valid_payments:
        raise HTTPException(
            status_code=402,
            detail="Payment Required"
        )

    # données premium plus précises
    return {
        "solar_production_precise": 85.0  # valeur fixe pour démo
    }

@app.post("/pay")
def make_payment():

    payment_id = str(uuid4())
    valid_payments.add(payment_id)

    return {
        "status": "payment_successful",
        "payment_id": payment_id
    }
