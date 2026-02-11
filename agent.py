PREMIUM_DATA_COST = 0.05  # € simulé
ESTIMATION_ERROR_FACTOR = 0.15  # 15% erreur estimation

def decide_action(state, budget):

    # estimation sans données premium
    estimated_production = state["solar_production"] * (1 - ESTIMATION_ERROR_FACTOR)

    # estimation perte potentielle
    potential_loss = abs(state["solar_production"] - estimated_production) * state["energy_price"]

    if potential_loss > PREMIUM_DATA_COST and budget >= PREMIUM_DATA_COST:
        return "buy_premium_data"
    else:
        return "use_basic_data"
