from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel
import random
import json
from typing import Optional
import asyncio
from fastapi.responses import StreamingResponse


from environment import get_environment_state
from skale_payment import send_payment, address
from agent import detect_crisis, investment_policy_explain, should_buy_premium_signal

app = FastAPI(title="AI Energy Capital Entity — SKALE x402")
templates = Jinja2Templates(directory="templates")

# ---------- Models ----------
class EpochRequest(BaseModel):
    risk_tolerance: float = 0.7
    force_crisis: Optional[str] = None  # "grid_failure" | "cloud_cover" | "price_crash" | None

class DemoRequest(BaseModel):
    risk_tolerance: float = 0.7


# ---------- State ----------
portfolio = {
    "cash": 1.0,
    "assets": [
        {"id": "SOLAR-1", "type": "solar", "capacity_kw": 100.0, "efficiency": 0.85, "acquisition_cost": 0.5}
    ],
    "nav_history": [],
    "info_spend_total": 0.0,
    "last_deploy_step": None  # ✅ Ajouté: track du dernier déploiement
}

valid_transactions: set[str] = set()

# ---------- Finance tuning ----------
ASSET_VALUE_MULTIPLIER = 0.004
DEPLOY_COST = 0.5
MIN_CASH_BUFFER = 1.0

MARKET_STRESS = 1.0  # 1.0 = normal, <1.0 = stress

# (Important pour drawdown visuel)
REVENUE_SCALE = 0.05
OPEX_PER_ASSET = 0.01

# ---------- Info marketplace ----------
PREMIUM_COST = 0.05  # coût du signal premium
PROVIDER_ADDRESS = address  # démo: paiement à soi-même; en prod => adresse du provider

# ---------- Optional: one-shot forced crisis for demo ----------
FORCE_NEXT_CRISIS = None  # "grid_failure" | "cloud_cover" | "price_crash" | None


# ---------- Helpers ----------
def calculate_nav(asset_multiplier: float) -> float:
    asset_value = sum(
        a["capacity_kw"] * a["efficiency"] * ASSET_VALUE_MULTIPLIER * asset_multiplier
        for a in portfolio["assets"]
    )
    return round(portfolio["cash"] + asset_value, 4)


def compute_drawdown_against_prev_hwm(current_nav: float) -> tuple[float, float]:
    prev_hwm = max([h["nav"] for h in portfolio["nav_history"]], default=None)
    if prev_hwm is None:
        prev_hwm = current_nav
    drawdown = (current_nav - prev_hwm) / prev_hwm if prev_hwm > 0 else 0.0
    drawdown = min(drawdown, 0.0)
    hwm = max(prev_hwm, current_nav)
    return drawdown, hwm


def get_market_regime(stress_level: float) -> str:
    if stress_level < 0.80:
        return "CRISIS"
    elif stress_level < 0.95:
        return "STRESS"
    else:
        return "NORMAL"


def simulate_basic_forecast(state: dict) -> dict:
    solar_true = state["solar_production"]
    price_true = state["energy_price"]
    solar_basic = solar_true * (1 + random.uniform(-0.20, 0.20))
    price_basic = price_true * (1 + random.uniform(-0.12, 0.12))
    return {"solar": max(solar_basic, 0.0), "price": max(price_basic, 0.0)}


def simulate_premium_forecast(state: dict) -> dict:
    solar_true = state["solar_production"]
    price_true = state["energy_price"]
    solar_premium = solar_true * (1 + random.uniform(-0.03, 0.03))
    price_premium = price_true * (1 + random.uniform(-0.02, 0.02))
    return {"solar": max(solar_premium, 0.0), "price": max(price_premium, 0.0)}


def estimate_evpi(state: dict, basic: dict, premium: dict) -> float:
    """
    EVPI (proxy): valeur marginale du premium:
    - meilleure prévision => meilleure décision => edge
    - + mitigation attendue d'une pénalité (ex blackout)
    """
    delta_solar = abs(basic["solar"] - state["solar_production"]) - abs(premium["solar"] - state["solar_production"])
    delta_price = abs(basic["price"] - state["energy_price"]) - abs(premium["price"] - state["energy_price"])

    info_gain = max(0.0, (0.6 * delta_solar + 1.0 * delta_price)) * 0.08  # scaling empirique
    expected_penalty_avoid = 0.20  # proxy mitigation
    return round(info_gain + expected_penalty_avoid, 4)


def reset_simulation():
    global MARKET_STRESS
    portfolio["cash"] = 1.0
    portfolio["assets"] = [{"id": "SOLAR-1", "type": "solar", "capacity_kw": 100.0, "efficiency": 0.85, "acquisition_cost": 0.5}]
    portfolio["nav_history"] = []
    portfolio["info_spend_total"] = 0.0
    portfolio["last_deploy_step"] = None  # ✅ Reset aussi
    MARKET_STRESS = 1.0


# ---------- Cinematic run state ----------
CINEMATIC_LAST = {
    "status": "idle",
    "story": [],
    "summary": {},
}

def _mk_story_event(label: str, epoch: dict) -> dict:
    return {
        "label": label,
        "step": epoch.get("step"),
        "nav": epoch.get("nav"),
        "hwm": epoch.get("hwm"),
        "drawdown": epoch.get("drawdown"),
        "regime": epoch.get("regime"),
        "crisis": epoch.get("crisis"),
        "used_premium": epoch.get("used_premium"),
        "evpi": epoch.get("evpi"),
        "info_spend": epoch.get("info_spend"),
        "net_edge": epoch.get("net_edge"),
        "decision": epoch.get("decision"),
        "cash": epoch.get("cash"),
        "asset_count": epoch.get("asset_count"),
        "tx_hash": epoch.get("tx_hash"),
        "premium_tx": epoch.get("premium_tx"),
    }

def _compute_cinematic_summary(story: list[dict]) -> dict:
    if not story:
        return {"ok": False, "reason": "no_story"}

    start = story[0]
    end = story[-1]

    # net edge cumulé
    net_edge = 0.0
    net_edge_total = 0.0
    premium_count = 0
    blackout_avoided = 0
    settlement_count = 0
    worst_dd = 0.0

    for s in story:
        ne = s.get("net_edge")
        if isinstance(ne, (int, float)):
            net_edge_total += float(ne)
        if s.get("used_premium"):
            premium_count += 1
        crisis = s.get("crisis") or ""
        if "avoided" in crisis.lower():
            blackout_avoided += 1
        if s.get("tx_hash"):
            settlement_count += 1
        dd = s.get("drawdown")
        if isinstance(dd, (int, float)):
            worst_dd = min(worst_dd, float(dd))

    nav_start = float(start["nav"]) if start.get("nav") is not None else 0.0
    nav_end = float(end["nav"]) if end.get("nav") is not None else 0.0

    return {
        "ok": True,
        "nav_start": round(nav_start, 4),
        "nav_end": round(nav_end, 4),
        "nav_delta": round(nav_end - nav_start, 4),
        "worst_drawdown": round(worst_dd, 4),
        "premium_epochs": premium_count,
        "net_edge_total": round(net_edge_total, 4),
        "blackout_avoided": blackout_avoided,
        "onchain_settlements": settlement_count,
        "final_decision": end.get("decision"),
        "final_regime": end.get("regime"),
        "final_assets": end.get("asset_count"),
        "final_cash": end.get("cash"),
    }


@app.post("/cinematic/run")
def cinematic_run(req: DemoRequest):
    """
    Storyboard "judge-proof":
    1) Reset
    2) Build HWM (2 epochs)
    3) Force premium condition (one epoch with normal regime)
    4) Shock: grid_failure
    5) Recovery: 3 epochs
    6) Try settlement: call /demo (SKALE tx) + 1 more epoch
    Returns: full story + compact summary
    """
    global CINEMATIC_LAST

    reset_simulation()
    CINEMATIC_LAST = {"status": "running", "story": [], "summary": {}}

    story = []
    rt = max(0.0, min(1.0, req.risk_tolerance))

    # 1) build high-water mark (makes drawdown meaningful)
    e1 = _run_epoch_internal(rt)
    story.append(_mk_story_event("Warmup-1 (build HWM)", e1))

    e2 = _run_epoch_internal(rt)
    story.append(_mk_story_event("Warmup-2 (build HWM)", e2))

    # 2) premium epoch (will trigger naturally if EVPI > cost)
    e3 = _run_epoch_internal(rt)
    story.append(_mk_story_event("Info Market (premium decision)", e3))

    # 3) shock
    e4 = _run_epoch_internal(rt, force_crisis="grid_failure")
    story.append(_mk_story_event("Shock (forced grid failure)", e4))

    # 4) recovery
    e5 = _run_epoch_internal(rt)
    story.append(_mk_story_event("Recovery-1", e5))

    e6 = _run_epoch_internal(rt)
    story.append(_mk_story_event("Recovery-2", e6))

    e7 = _run_epoch_internal(rt)
    story.append(_mk_story_event("Recovery-3", e7))

    # 5) settlement proof (on-chain)
    settle = run_demo()
    settle_tx = None
    if isinstance(settle, dict) and settle.get("status") == "success":
        settle_tx = settle.get("tx_hash")

    # one more epoch to show post-settlement state
    e8 = _run_epoch_internal(max(rt, 0.9))
    if settle_tx and not e8.get("tx_hash"):
        # annotate settlement tx if epoch didn't deploy
        e8["tx_hash"] = settle_tx

    story.append(_mk_story_event("On-chain settlement + final state", e8))

    summary = _compute_cinematic_summary(story)

    CINEMATIC_LAST = {"status": "done", "story": story, "summary": summary}
    return {"status": "ok", "story": story, "summary": summary}


@app.get("/cinematic/summary")
def cinematic_summary():
    """
    Simple summary endpoint for README/video overlay.
    """
    return CINEMATIC_LAST


@app.get("/cinematic/stream")
def cinematic_stream(risk_tolerance: float = 0.7):
    async def event_gen():
        reset_simulation()
        rt = max(0.0, min(1.0, float(risk_tolerance)))

        def sse(data: dict):
            return f"data: {json.dumps(data)}\n\n"

        # steps
        steps = [
            ("Warmup-1 (build HWM)", {"force": None}),
            ("Warmup-2 (build HWM)", {"force": None}),
            ("Info Market (premium decision)", {"force": None}),
            ("Shock (forced grid failure)", {"force": "grid_failure"}),
            ("Recovery-1", {"force": None}),
            ("Recovery-2", {"force": None}),
            ("Recovery-3", {"force": None}),
            ("On-chain settlement + final state", {"force": None}),
        ]

        # Stream each epoch + graph update
        for label, cfg in steps:
            epoch = _run_epoch_internal(rt, force_crisis=cfg["force"])
            payload = _mk_story_event(label, epoch)
            payload["type"] = "epoch"
            
            # ✅ ENVOIE AUSSI LES DONNÉES DU GRAPHIQUE
            payload["chart_update"] = {
                "nav_history": portfolio["nav_history"][-10:],  # last 10 points for perf
                "current_nav": payload["nav"],
                "step": payload["step"]
            }
            
            yield sse(payload)
            await asyncio.sleep(0.15)

        # Settlement (can take time)
        yield sse({"type": "status", "message": "⛓️ Sending SKALE settlement transaction..."})

        settle = run_demo()
        yield sse({"type": "settlement", "result": settle})

        # Final summary (avec graph complet)
        story = portfolio["nav_history"]
        story_events = []
        for i, e in enumerate(story[-len(steps):], start=0):
            story_events.append(_mk_story_event(steps[i][0], e))

        summary = _compute_cinematic_summary(story_events)
        
        # ✅ ENVOIE LE GRAPHIQUE COMPLET À LA FIN
        yield sse({
            "type": "summary", 
            "summary": summary,
            "chart_final": {
                "nav_history": portfolio["nav_history"],
                "total_steps": len(portfolio["nav_history"])
            }
        })

        yield sse({"type": "done"})

    return StreamingResponse(event_gen(), media_type="text/event-stream")


# ---------- Payment / x402 ----------
@app.post("/x402/pay")
def x402_pay():
    """
    L'agent paye le provider via SKALE. Retourne un tx_hash utilisable comme preuve.
    """
    try:
        tx_hash_bytes = send_payment(PROVIDER_ADDRESS, 0.001)  # tiny demo payment
        tx_hash = "0x" + tx_hash_bytes.hex()
        valid_transactions.add(tx_hash)
        return {
            "status": "paid",
            "tx_hash": tx_hash,
            "explorer": f"https://base-sepolia-testnet-explorer.skalenodes.com:10032/tx/  {tx_hash}"
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/premium/signal")
def premium_signal(tx_hash: str | None = None):
    """
    Service premium: renvoie forecast premium SI paiement prouvé.
    """
    if not tx_hash or tx_hash not in valid_transactions:
        raise HTTPException(status_code=402, detail="Payment Required (x402)")

    state = get_environment_state()
    premium = simulate_premium_forecast(state)
    return {
        "status": "ok",
        "data": premium,
        "provider_signature": "signed_by_skale_oracle_demo"
    }


@app.post("/force_crisis/{crisis_type}")
def force_crisis(crisis_type: str):
    global FORCE_NEXT_CRISIS
    if crisis_type not in ["grid_failure", "cloud_cover", "price_crash", "none"]:
        return {"status": "error", "message": "Invalid crisis type"}

    FORCE_NEXT_CRISIS = None if crisis_type == "none" else crisis_type
    return {"status": "ok", "next_crisis": FORCE_NEXT_CRISIS}


# ---------- Core: single epoch ----------
def _run_epoch_internal(risk_tolerance: float, force_crisis: Optional[str] = None) -> dict:
    global MARKET_STRESS, FORCE_NEXT_CRISIS

    risk_tolerance = max(0.0, min(1.0, risk_tolerance))

    # Force crisis one-shot if requested
    if force_crisis in ["grid_failure", "cloud_cover", "price_crash"]:
        FORCE_NEXT_CRISIS = force_crisis

    # 0) environment + forecasts
    state = get_environment_state()
    basic = simulate_basic_forecast(state)
    premium = simulate_premium_forecast(state)
    evpi = estimate_evpi(state, basic, premium)

    # 1) buy premium?
    used_premium = False
    info_spend = 0.0
    premium_tx = None

    if should_buy_premium_signal(
        cash=portfolio["cash"],
        premium_cost=PREMIUM_COST,
        evpi=evpi,
        risk_tolerance=risk_tolerance,
        min_cash_buffer=0.20
    ):
        pay = x402_pay()
        premium_tx = pay["tx_hash"]

        try:
            ps = premium_signal(tx_hash=premium_tx)
            premium_data = ps["data"]
            used_premium = True
            info_spend = PREMIUM_COST
            portfolio["cash"] = max(0.0, portfolio["cash"] - PREMIUM_COST)
            portfolio["info_spend_total"] += PREMIUM_COST

            # Use premium in place of basic for this epoch
            basic = premium_data
        except Exception:
            used_premium = False

    # 2) crisis sampling
    crisis = detect_crisis(force=FORCE_NEXT_CRISIS)
    FORCE_NEXT_CRISIS = None

    if crisis:
        crisis_message = crisis["message"]
    else:
        crisis_message = "✅ Stable Operations"

    # 2bis) mitigation: premium can avoid grid_failure
    if used_premium and crisis and crisis["type"] == "grid_failure":
        if random.random() < 0.60:
            crisis = None
            crisis_message = "🧠 Premium Ops: Blackout avoided (forecast-driven dispatch)"

    # 3) MARKET STRESS update
    if crisis:
        MARKET_STRESS *= crisis.get("asset_impact", 1.0)
        MARKET_STRESS = max(0.50, MARKET_STRESS)
    else:
        MARKET_STRESS = min(1.0, MARKET_STRESS + 0.08)

    asset_multiplier = MARKET_STRESS

    # 4) production + revenue (forecast-informed)
    total_revenue = 0.0
    for asset in portfolio["assets"]:
        solar_forecast = basic["solar"]
        price_forecast = basic["price"]

        prod = asset["capacity_kw"] * asset["efficiency"] * (solar_forecast / 100.0)
        price = price_forecast

        if crisis:
            if crisis["type"] == "cloud_cover":
                prod *= (1 - crisis["production_drop"])
            elif crisis["type"] == "price_crash":
                price *= (1 - crisis["price_drop"])
            elif crisis["type"] == "grid_failure":
                pass

        total_revenue += prod * price * REVENUE_SCALE

    # OPEX
    portfolio["cash"] -= OPEX_PER_ASSET * len(portfolio["assets"])

    # grid failure penalty once per epoch
    if crisis and crisis["type"] == "grid_failure":
        portfolio["cash"] -= crisis["cash_penalty"]
        total_revenue *= (1 - crisis.get("production_drop", 0.0))

    portfolio["cash"] += total_revenue
    portfolio["cash"] = max(portfolio["cash"], 0.0)

    # 5) NAV + drawdown
    current_nav = calculate_nav(asset_multiplier)
    drawdown, hwm = compute_drawdown_against_prev_hwm(current_nav)

    survival_mode = drawdown < -0.15

    net_edge = round(evpi - info_spend, 4)
    
    decision, rationale, meta = investment_policy_explain(
        cash=portfolio["cash"],
        drawdown=drawdown,
        risk_tolerance=risk_tolerance,
        crisis_active=bool(crisis),
        net_edge=net_edge,
        step=len(portfolio["nav_history"]),
        last_deploy_step=portfolio.get("last_deploy_step"),
        min_cash_buffer=MIN_CASH_BUFFER,
        deploy_cost=DEPLOY_COST,
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

            # ✅ Track du déploiement
            portfolio["last_deploy_step"] = len(portfolio["nav_history"])

            current_nav = calculate_nav(asset_multiplier)
            drawdown, hwm = compute_drawdown_against_prev_hwm(current_nav)
            survival_mode = drawdown < -0.15

        except Exception:
            decision = "deploy_failed"

    net_edge = round(evpi - info_spend, 4)

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

        "rationale": rationale,
        "policy_meta": meta,


        # Info arbitrage (load-bearing)
        "used_premium": used_premium,
        "evpi": evpi,
        "info_spend": round(info_spend, 4),
        "net_edge": net_edge,
        "info_spend_total": round(portfolio["info_spend_total"], 4),
        "premium_tx": premium_tx,

        # Regime
        "market_stress": round(MARKET_STRESS, 4),
        "regime": get_market_regime(MARKET_STRESS),

        # Forecasts (useful)
        "forecast_solar": round(basic["solar"], 3),
        "forecast_price": round(basic["price"], 4),
    }

    portfolio["nav_history"].append(epoch)
    return epoch


@app.post("/epoch")
def run_epoch(req: EpochRequest):
    return _run_epoch_internal(req.risk_tolerance, req.force_crisis)


# ---------- Cinematic demo runner ----------
@app.post("/storyboard/demo_run")
def storyboard_demo(req: DemoRequest):
    """
    Démo reproductible:
    1) 2 epochs normal (build HWM)
    2) 1 epoch: laisse le modèle acheter premium si EVPI le justifie
    3) force grid_failure (shock)
    4) 3 epochs recovery
    5) 1 epoch à risk élevé (re-deploy possible)
    """
    reset_simulation()

    steps = []
    rt = req.risk_tolerance

    steps.append(_run_epoch_internal(rt))
    steps.append(_run_epoch_internal(rt))

    # premium tends to happen naturally; no forcing here
    steps.append(_run_epoch_internal(rt))

    # force shock
    steps.append(_run_epoch_internal(rt, force_crisis="grid_failure"))

    # recovery
    steps.append(_run_epoch_internal(rt))
    steps.append(_run_epoch_internal(rt))
    steps.append(_run_epoch_internal(rt))

    # risk up => possible contrarian redeploy after recovery
    steps.append(_run_epoch_internal(max(rt, 0.9)))

    return {"status": "ok", "epochs": steps, "final": steps[-1]}


@app.post("/demo")
def run_demo():
    try:
        tx_hash_bytes = send_payment(address, 0.001)
        tx_hash = "0x" + tx_hash_bytes.hex()
        explorer_url = f"https://base-sepolia-testnet-explorer.skalenodes.com:10032/tx/  {tx_hash}"
        return {
            "status": "success",
            "message": "✅ SKALE settlement confirmed — capital deployment recorded on-chain",
            "tx_hash": tx_hash,
            "explorer": explorer_url
        }
    except Exception as e:
        return {"status": "error", "message": f"❌ Error: {str(e)}"}


# ---------- Dashboard ----------
@app.get("/dashboard", response_class=HTMLResponse)
def dashboard():
    nav_history = portfolio["nav_history"]
    current_nav = calculate_nav(MARKET_STRESS)

    if nav_history:
        last_epoch = nav_history[-1]
    else:
        last_epoch = {
            "step": 0,
            "nav": current_nav,
            "hwm": current_nav,
            "drawdown": 0.0,
            "crisis": "✅ Stable Operations",
            "survival_mode": False,
            "decision": "hold_cash",
            "cash": portfolio["cash"],
            "asset_count": len(portfolio["assets"]),
            "tx_hash": None,
            "market_stress": MARKET_STRESS,
            "regime": get_market_regime(MARKET_STRESS),
            "used_premium": False,
            "evpi": 0.0,
            "info_spend": 0.0,
            "net_edge": 0.0,
            "info_spend_total": portfolio["info_spend_total"],
            "premium_tx": None
        }

    context = {
        "request": {},
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