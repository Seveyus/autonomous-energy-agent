PREMIUM_DATA_COST = 0.05  # € simulé
ESTIMATION_ERROR_FACTOR = 0.15  # 15% erreur estimation
import requests

def decide_action(state, budget):

    # estimation sans données premium
    estimated_production = state["solar_production"] * (1 - ESTIMATION_ERROR_FACTOR)

    # estimation perte potentielle
    potential_loss = abs(state["solar_production"] - estimated_production) * state["energy_price"]

    if potential_loss > PREMIUM_DATA_COST and budget >= PREMIUM_DATA_COST:
        return "buy_premium_data"
    else:
        return "use_basic_data"

def get_premium_data():

    response = requests.get("http://127.0.0.1:8000/premium-weather")

    if response.status_code == 402:

        payment = requests.post("http://127.0.0.1:8000/x402/pay")
        payment_json = payment.json()

        tx_hash = payment_json["tx_hash"]

        response = requests.get(
            "http://127.0.0.1:8000/premium-weather",
            params={"tx_hash": tx_hash}
        )

        return {
            "data": response.json(),
            "transaction": payment_json
        }

    return {"data": response.json(), "transaction": None}
