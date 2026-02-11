# agent.py
import random
import requests

PREMIUM_DATA_COST = 0.05  # € simulé
ESTIMATION_ERROR_FACTOR = 0.15  # 15% erreur estimation basique
PREMIUM_ERROR_FACTOR = 0.02    # 2% erreur avec données premium
CRISIS_PROBABILITY = 0.15  

def decide_action(state, budget, risk_tolerance=0.7):
    """
    Décision stratégique basée sur :
    - Projection sur horizon (5 pas futurs)
    - Comparaison valeur attendue du premium
    - Risk tolerance (0.0 = conservateur → 1.0 = agressif)
    
    Returns:
        "buy_premium_data" | "use_basic_data"
    """
    forecast_horizon = 5
    
    # === 1. Projection SANS premium (erreur ±15%) ===
    projected_gain_basic = 0
    for _ in range(forecast_horizon):
        # Simule un état futur plausible
        simulated = {
            "solar_production": random.uniform(70, 95),
            "consumption": random.uniform(60, 80),
            "energy_price": random.uniform(0.10, 0.30)
        }
        
        # Erreur d'estimation basique
        error = random.uniform(-ESTIMATION_ERROR_FACTOR, ESTIMATION_ERROR_FACTOR)
        estimated_prod = simulated["solar_production"] * (1 + error)
        profit = (estimated_prod - simulated["consumption"]) * simulated["energy_price"]
        projected_gain_basic += profit
    
    # === 2. Projection AVEC premium (erreur ±2%) ===
    projected_gain_premium = 0
    for _ in range(forecast_horizon):
        simulated = {
            "solar_production": random.uniform(70, 95),
            "consumption": random.uniform(60, 80),
            "energy_price": random.uniform(0.10, 0.30)
        }
        
        # Précision chirurgicale avec premium
        error = random.uniform(-PREMIUM_ERROR_FACTOR, PREMIUM_ERROR_FACTOR)
        estimated_prod = simulated["solar_production"] * (1 + error)
        profit = (estimated_prod - simulated["consumption"]) * simulated["energy_price"]
        projected_gain_premium += profit
    
    # === 3. Valeur attendue nette du premium ===
    net_value = (projected_gain_premium - projected_gain_basic) - PREMIUM_DATA_COST
    
    # === 4. Seuil adaptatif selon risk tolerance ===
    # Conservateur (0.0) : achète même pour petite valeur positive
    # Agressif (1.0) : n'achète que si valeur très positive
    threshold = -0.02 + (0.08 * (1 - risk_tolerance))
    
    # Décision finale
    if net_value > threshold and budget >= PREMIUM_DATA_COST:
        return "buy_premium_data"
    else:
        return "use_basic_data"


def get_premium_data():
    """
    Workflow x402 intact – appel ton endpoint /x402/pay → /premium-weather
    """
    response = requests.get("http://127.0.0.1:8000/premium-weather")

    if response.status_code == 402:
        # Déclenche le paiement SKALE via x402
        payment = requests.post("http://127.0.0.1:8000/x402/pay")
        payment_json = payment.json()

        tx_hash = payment_json["tx_hash"]

        # Récupère les données premium après paiement
        response = requests.get(
            "http://127.0.0.1:8000/premium-weather",
            params={"tx_hash": tx_hash}
        )

        return {
            "data": response.json(),
            "transaction": payment_json
        }

    return {"data": response.json(), "transaction": None}

def detect_crisis():
    """Génère un événement de crise aléatoire avec impact économique"""
    if random.random() < CRISIS_PROBABILITY:
        crisis_type = random.choice([
            "cloud_cover",      # Production solaire effondrée
            "grid_failure",     # Impossible de vendre → pénalités
            "price_crash"       # Prix énergie s'effondre
        ])
        
        impact = {
            "cloud_cover": {"production_drop": 0.85, "message": "🌩️ Cloud cover: Solar production -85%"},
            "grid_failure": {"penalty": 0.30, "message": "⚡ Grid failure: Contract penalties -0.30€"},
            "price_crash": {"price_drop": 0.70, "message": "📉 Price crash: Energy price -70%"}
        }[crisis_type]
        
        return {"type": crisis_type, **impact}
    return None