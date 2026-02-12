import random

# Pour la vidéo : 0.25–0.40
CRISIS_PROBABILITY = 0.35

CRISIS_EVENTS = [
    {
        "type": "cloud_cover",
        "message": "🌩️ Extreme Storm: Solar production -95%",
        "production_drop": 0.95,
        "asset_impact": 0.80,
        "cash_penalty": 0.0
    },
    {
        "type": "price_crash",
        "message": "📉 Market Collapse: Energy price -90%",
        "price_drop": 0.90,
        "asset_impact": 0.78,  # plus violent => drawdown visible
        "cash_penalty": 0.0
    },
    {
        "type": "grid_failure",
        "message": "⚡ Grid Blackout: Critical penalties (-1.50€)",
        "production_drop": 0.30,
        "asset_impact": 0.88,
        "cash_penalty": 4.00

    }
]


def detect_crisis(force: str | None = None):
    if force:
        for ev in CRISIS_EVENTS:
            if ev["type"] == force:
                return ev
        return None

    if random.random() < CRISIS_PROBABILITY:
        return random.choice(CRISIS_EVENTS)

    return None


def investment_policy(
    cash: float,
    drawdown: float,
    risk_tolerance: float,
    crisis_active: bool,
    min_cash_buffer: float = 1.0,
):
    """
    Finance-grade policy:
    - En crise: HOLD par défaut
    - MAIS: si drawdown profond + risque élevé -> contrarian "buy the dip"
    - Hors crise: investir si cash buffer ok et ROI projeté ok
    """

    # Hard survival: si drawdown > 30% => stop quoi qu’il arrive
    if drawdown < -0.30:
        return "hold_cash"

    # En crise, on ne freeze pas forcément:
    if crisis_active:
        # Contrarian mode: seulement si risk élevé + drawdown significatif + cash suffisant
        if risk_tolerance >= 0.7 and drawdown < -0.12 and cash >= (min_cash_buffer + 0.5):
            return "deploy_capital"
        return "hold_cash"

    # hors crise
    if cash < min_cash_buffer:
        return "hold_cash"

    projected_roi = random.uniform(-0.10, 0.25)
    threshold = 0.02 - (0.04 * risk_tolerance)  # rt=0.7 => ~ -0.008

    if projected_roi > threshold:
        return "deploy_capital"

    return "hold_cash"
