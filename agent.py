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


def investment_policy_explain(
    cash: float,
    drawdown: float,
    risk_tolerance: float,
    crisis_active: bool,
    net_edge: float,
    step: int,
    last_deploy_step: int | None,
    min_cash_buffer: float = 1.0,
    deploy_cost: float = 1.0,
):
    rationale = []
    meta = {}

    # thresholds
    normal_threshold = 0.12 - 0.06 * risk_tolerance
    crisis_threshold = 0.20
    dip_threshold = 0.25

    meta["threshold_normal"] = round(normal_threshold, 4)
    meta["threshold_crisis"] = round(crisis_threshold, 4)
    meta["threshold_dip"] = round(dip_threshold, 4)

    # cooldown
    COOLDOWN = 2 if risk_tolerance < 0.75 else 1
    meta["cooldown"] = COOLDOWN

    # hard kill-switch
    if drawdown <= -0.30:
        rationale.append(f"Drawdown {drawdown:.2%} <= -30% → capital preservation")
        return "hold_cash", rationale, meta

    # feasibility
    if cash < (deploy_cost + min_cash_buffer):
        rationale.append(f"Cash {cash:.2f} < deploy_cost+buffer ({deploy_cost+min_cash_buffer:.2f})")
        return "hold_cash", rationale, meta

    # cooldown active
    if last_deploy_step is not None:
        since = step - last_deploy_step
        remaining = max(0, COOLDOWN - since)
        meta["cooldown_remaining"] = remaining
        if since <= COOLDOWN:
            rationale.append(f"Cooldown active: last deploy at epoch {last_deploy_step} (since={since})")
            return "hold_cash", rationale, meta
    else:
        meta["cooldown_remaining"] = 0

    # drawdown regime
    if drawdown <= -0.10:
        rationale.append(f"Risk control: drawdown {drawdown:.2%} <= -10%")
        if (not crisis_active) and risk_tolerance >= 0.8 and net_edge >= dip_threshold:
            rationale.append(f"Contrarian allowed: net_edge {net_edge:.3f} >= {dip_threshold:.2f} and risk_tolerance {risk_tolerance:.2f}")
            return "deploy_capital", rationale, meta
        rationale.append("Hold cash: signal not strong enough for contrarian buy")
        return "hold_cash", rationale, meta

    # crisis regime
    if crisis_active:
        rationale.append("Crisis regime: default HOLD")
        if risk_tolerance >= 0.75 and net_edge >= crisis_threshold:
            rationale.append(f"Deploy allowed: net_edge {net_edge:.3f} >= {crisis_threshold:.2f} and risk_tolerance {risk_tolerance:.2f}")
            return "deploy_capital", rationale, meta
        rationale.append(f"Hold: net_edge {net_edge:.3f} below crisis threshold {crisis_threshold:.2f}")
        return "hold_cash", rationale, meta

    # normal regime
    rationale.append("Normal regime")
    rationale.append(f"net_edge {net_edge:.3f} vs threshold {normal_threshold:.3f}")

    if net_edge >= normal_threshold:
        rationale.append("Deploy: expected edge clears threshold")
        return "deploy_capital", rationale, meta

    rationale.append("Hold: edge below threshold")
    return "hold_cash", rationale, meta


# Backward-compat: some code imports investment_policy
investment_policy = investment_policy_explain
