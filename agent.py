import random
import requests

PREMIUM_DATA_COST = 0.05
ESTIMATION_ERROR_FACTOR = 0.15
PREMIUM_ERROR_FACTOR = 0.02
CRISIS_PROBABILITY = 1.00

def decide_action(state, budget, risk_tolerance=0.7):
    forecast_horizon = 5
    
    # Projection SANS premium
    projected_gain_basic = 0
    for _ in range(forecast_horizon):
        simulated = {
            "solar_production": random.uniform(70, 95),
            "consumption": random.uniform(60, 80),
            "energy_price": random.uniform(0.10, 0.30)
        }
        error = random.uniform(-ESTIMATION_ERROR_FACTOR, ESTIMATION_ERROR_FACTOR)
        estimated_prod = simulated["solar_production"] * (1 + error)
        profit = (estimated_prod - simulated["consumption"]) * simulated["energy_price"]
        projected_gain_basic += profit
    
    # Projection AVEC premium
    projected_gain_premium = 0
    for _ in range(forecast_horizon):
        simulated = {
            "solar_production": random.uniform(70, 95),
            "consumption": random.uniform(60, 80),
            "energy_price": random.uniform(0.10, 0.30)
        }
        error = random.uniform(-PREMIUM_ERROR_FACTOR, PREMIUM_ERROR_FACTOR)
        estimated_prod = simulated["solar_production"] * (1 + error)
        profit = (estimated_prod - simulated["consumption"]) * simulated["energy_price"]
        projected_gain_premium += profit
    
    net_value = (projected_gain_premium - projected_gain_basic) - PREMIUM_DATA_COST
    threshold = -0.02 + (0.08 * (1 - risk_tolerance))
    
    if net_value > threshold and budget >= PREMIUM_DATA_COST:
        return "buy_premium_data"
    else:
        return "use_basic_data"

def get_premium_data():
    # Workflow simplifié pour ce hackathon (pas de vrai x402 requis pour la démo)
    return {"data": {"solar_production_precise": 85.0}, "transaction": None}

def detect_crisis():
    """Génère un événement de crise avec un impact DESTRUCTEUR pour la démo"""
    if random.random() < CRISIS_PROBABILITY:
        crisis_type = random.choice(["cloud_cover", "grid_failure", "price_crash"])
        impact = {
            "cloud_cover": {
                "production_drop": 0.95, 
                "message": "🌩️ Extreme Storm: Solar production halted (-95%)"
            },
            "grid_failure": {
                "penalty": 1.5,  # Grosse pénalité qui vide le cash
                "message": "⚡ Grid Blackout: Critical failure penalties (-1.50€)"
            },
            "price_crash": {
                "price_drop": 0.90, 
                "message": "📉 Market Collapse: Energy price near zero (-90%)"
            }
        }[crisis_type]
        return {"type": crisis_type, **impact}
    return None