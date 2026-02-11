import random

def get_environment_state():
    return {
        "solar_production": random.uniform(20, 100),   # kWh
        "energy_price": random.uniform(0.05, 0.30),    # €/kWh
        "consumption": random.uniform(30, 90)          # kWh
    }
