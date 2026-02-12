from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
import random
import json
from pathlib import Path

from environment import get_environment_state
from skale_payment import send_payment, address
from agent import detect_crisis, investment_policy

app = FastAPI(title="AI Energy Capital Entity — SKALE x402")

# --- Templates
templates = Jinja2Templates(directory="templates")

portfolio = {
    "cash": 1.0,
    "assets": [
         {"id": "SOLAR-1", "type": "solar", "capacity_kw": 100.0, "efficiency": 0.85, "acquisition_cost": 0.5}
    ],
    "nav_history": []
}

# --- Finance tuning
ASSET_VALUE_MULTIPLIER =  0.004
DEPLOY_COST = 0.5
MIN_CASH_BUFFER = 1.0
MARKET_STRESS = 1.0  # 1.0 = normal, <1.0 = stress, >1.0 = boom

REVENUE_SCALE = 0.05  # Multiplie la production pour simuler des gains/pertes
OPEX_PER_ASSET = 0.01  # Coût opérationnel par actif par époque


def calculate_nav(asset_multiplier: float) -> float:
    asset_value = sum(
        a["capacity_kw"] * a["efficiency"] * ASSET_VALUE_MULTIPLIER * asset_multiplier
        for a in portfolio["assets"]
    )
    return round(portfolio["cash"] + asset_value, 4)


def compute_high_water_mark(history, current_nav: float) -> float:
    if not history:
        return current_nav
    return max([h["nav"] for h in history] + [current_nav])


def compute_drawdown(current_nav: float, hwm: float) -> float:
    if hwm <= 0:
        return 0.0
    return min((current_nav - hwm) / hwm, 0.0)


def get_market_regime(stress_level: float) -> str:
    if stress_level < 0.80:
        return "CRISIS"
    elif stress_level < 0.95:
        return "STRESS"
    else:
        return "NORMAL"


@app.post("/epoch")
def run_epoch(risk_tolerance: float = 0.7):
    global MARKET_STRESS

    crisis = detect_crisis()
    crisis_message = crisis["message"] if crisis else "✅ Stable Operations"

    # 1) MARKET STRESS update
    if crisis:
        MARKET_STRESS *= crisis.get("asset_impact", 1.0)
        MARKET_STRESS = max(0.50, MARKET_STRESS)
    else:
        # Récupération plus rapide (modifié)
        MARKET_STRESS = min(1.0, MARKET_STRESS + 0.08) # 0.05 -> 0.08

    asset_multiplier = MARKET_STRESS

    # 2) production + revenue
    total_revenue = 0.0

    for asset in portfolio["assets"]:
        state = get_environment_state()
        prod = asset["capacity_kw"] * asset["efficiency"] * (state["solar_production"] / 100.0)
        price = state["energy_price"]

        if crisis:
            if crisis["type"] == "cloud_cover":
                prod *= (1 - crisis["production_drop"])
            elif crisis["type"] == "price_crash":
                price *= (1 - crisis["price_drop"])
            elif crisis["type"] == "grid_failure":
                 pass

        total_revenue += prod * price * REVENUE_SCALE

    portfolio["cash"] -= OPEX_PER_ASSET * len(portfolio["assets"])

    if crisis and crisis["type"] == "grid_failure":
        portfolio["cash"] -= crisis["cash_penalty"]
        total_revenue *= (1 - crisis.get("production_drop", 0.0))

    portfolio["cash"] += total_revenue
    portfolio["cash"] = max(portfolio["cash"], 0.0)

    # 3) NAV + HWM + DRAWDOWN
    prev_hwm = max([h["nav"] for h in portfolio["nav_history"]], default=None)
    current_nav = calculate_nav(asset_multiplier)

    if prev_hwm is None:
         prev_hwm = current_nav

    drawdown = (current_nav - prev_hwm) / prev_hwm if prev_hwm > 0 else 0.0
    drawdown = min(drawdown, 0.0)

    hwm = max(prev_hwm, current_nav)

    # Seuil de survie ajusté (modifié)
    survival_mode = drawdown < -0.15 # -0.20 -> -0.15

    # 4) decision
    decision = investment_policy(
        cash=portfolio["cash"],
        drawdown=drawdown,
        risk_tolerance=risk_tolerance,
        crisis_active=bool(crisis),
        min_cash_buffer=MIN_CASH_BUFFER
    )

    tx_hash = None

    if decision == "deploy_capital" and not survival_mode and portfolio["cash"] >= (DEPLOY_COST + MIN_CASH_BUFFER):
        try:
            tx_hash_bytes = send_payment(address, 0.001)
            tx_hash = "0x" + tx_hash_bytes.hex()

            portfolio["cash"] -= DEPLOY_COST

            portfolio["assets"].append({
                "id": f"SOLAR-{len(portfolio['assets'])+1}",
                "type": "solar",
                "capacity_kw": round(random.uniform(80, 120), 2),
                "efficiency": round(random.uniform(0.80, 0.92), 2),
                "acquisition_cost": DEPLOY_COST
            })

            current_nav = calculate_nav(asset_multiplier)
            drawdown = (current_nav - prev_hwm) / prev_hwm if prev_hwm > 0 else 0.0
            drawdown = min(drawdown, 0.0)
            hwm = max(prev_hwm, current_nav)
            survival_mode = drawdown  < -0.15

        except Exception:
            decision = "deploy_failed"

    epoch = {
        "step": len(portfolio["nav_history"]),
        "nav": current_nav,
        "hwm": round(hwm, 4),
        "drawdown": round(drawdown, 4),
        "crisis": crisis_message,
        "survival_mode": survival_mode,
        "decision": decision,
        "cash": round(portfolio["cash"], 4),
        "asset_count": len(portfolio["assets"]),
        "tx_hash": tx_hash,
        "market_stress": round(MARKET_STRESS, 4),
        "regime": get_market_regime(MARKET_STRESS) # Ajout du regime
    }

    portfolio["nav_history"].append(epoch)
    return epoch


@app.post("/demo")
def run_demo():
    try:
        tx_hash_bytes = send_payment(address, 0.001)
        tx_hash = "0x" + tx_hash_bytes.hex()
        explorer_url = f"https://base-sepolia-testnet-explorer.skalenodes.com:10032/tx/{tx_hash}"
        return {
            "status": "success",
            "message": "✅ SKALE settlement confirmed — capital deployment recorded on-chain",
            "tx_hash": tx_hash,
            "explorer": explorer_url
        }
    except Exception as e:
        return {"status": "error", "message": f"❌ Error: {str(e)}"}


# ===== DASHBOARD =====
@app.get("/dashboard", response_class=HTMLResponse)
def dashboard():
    nav_history = portfolio["nav_history"]
    current_nav = calculate_nav(MARKET_STRESS)
    last_epoch = nav_history[-1] if nav_history else {
        "step": 0,
        "nav": current_nav,
        "hwm": current_nav,
        "drawdown": 0.0,
        "crisis": "",
        "survival_mode": False,
        "decision": "hold_cash",
        "cash": portfolio["cash"],
        "asset_count": len(portfolio["assets"]),
        "tx_hash": None,
        "market_stress": MARKET_STRESS,
        "regime": get_market_regime(MARKET_STRESS)
    }

    context = {
        "request": {},  # FastAPI requires this for Jinja2
        "current_nav": f"{current_nav:.4f}",
        "max_nav": f"{last_epoch['hwm']:.4f}",
        "cash": f"{portfolio['cash']:.4f}",
        "asset_count": len(portfolio["assets"]),
        "total_capacity": f"{sum(a['capacity_kw'] for a in portfolio['assets']):.1f}",
        "last_assets": portfolio["assets"][-3:],
        "last_epoch": last_epoch,
        "nav_history_json": json.dumps(nav_history),
    }

    return templates.TemplateResponse("dashboard.html", context)
