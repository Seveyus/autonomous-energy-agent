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
        "asset_impact": 0.78,
        "cash_penalty": 0.0
    },
    {
        "type": "grid_failure",
        "message": "⚡ Grid Blackout: Critical penalties (-4.00€)",
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


def should_buy_premium_signal(
    cash: float,
    premium_cost: float,
    evpi: float,
    risk_tolerance: float,
    min_cash_buffer: float = 0.30
) -> bool:
    """
    Décision d'achat d'information:
    - On achète si EVPI > coût * marge de sécurité.
    - Plus risk_tolerance est haut, plus on accepte des bets.
    """
    if cash < (premium_cost + min_cash_buffer):
        return False

    # marge de sécurité: risk_tolerance haut -> marge plus faible
    safety = 1.25 - (0.35 * risk_tolerance)  # rt=0.7 => ~1.005 ; rt=0.2 => ~1.18
    return evpi > premium_cost * safety


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

    if drawdown < -0.30:
        return "hold_cash"

    if crisis_active:
        if risk_tolerance >= 0.7 and drawdown < -0.12 and cash >= (min_cash_buffer + 0.5):
            return "deploy_capital"
        return "hold_cash"

    if cash < min_cash_buffer:
        return "hold_cash"

    projected_roi = random.uniform(-0.10, 0.25)
    threshold = 0.02 - (0.04 * risk_tolerance)

    if projected_roi > threshold:
        return "deploy_capital"

    return "hold_cash"
