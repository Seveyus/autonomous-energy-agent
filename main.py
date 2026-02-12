from fastapi import FastAPI
from fastapi.responses import HTMLResponse
import random
import json

from environment import get_environment_state
from skale_payment import send_payment, address
from agent import detect_crisis, investment_policy

app = FastAPI(title="AI Energy Capital Entity — SKALE x402")

portfolio = {
    "cash": 1.0,
    "assets": [
        {"id": "SOLAR-1", "type": "solar", "capacity_kw": 100.0, "efficiency": 0.85, "acquisition_cost": 0.5}
    ],
    "nav_history": []
}

# --- Finance tuning
ASSET_VALUE_MULTIPLIER = 0.004
DEPLOY_COST = 0.5
MIN_CASH_BUFFER = 1.0
MARKET_STRESS = 1.0  # 1.0 = normal, <1 = marché stressé (impacte la valeur des assets)
REVENUE_SCALE = 0.01   # 🔥 clé: rend les € par epoch réalistes
OPEX_PER_ASSET = 0.15  # coût fixe par asset/epoch



# --- DEMO MODE ---
# Force crise seulement sur le prochain epoch, puis revient à None automatiquement
FORCE_NEXT_CRISIS = None  # "grid_failure" | "cloud_cover" | "price_crash" | None


def calculate_nav(asset_multiplier: float = 1.0) -> float:
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
    dd = (current_nav - hwm) / hwm
    return min(dd, 0.0)


@app.post("/force_crisis/{crisis_type}")
def force_crisis(crisis_type: str):
    """
    Force une crise pour le prochain epoch seulement.
    """
    global FORCE_NEXT_CRISIS
    if crisis_type not in ["grid_failure", "cloud_cover", "price_crash", "none"]:
        return {"status": "error", "message": "Invalid crisis type"}

    FORCE_NEXT_CRISIS = None if crisis_type == "none" else crisis_type
    return {"status": "ok", "next_crisis": FORCE_NEXT_CRISIS}

@app.get("/run_epoch")
def run_epoch(risk_tolerance: float = 0.7):
    global FORCE_NEXT_CRISIS, MARKET_STRESS

    # 1) crisis sampling (one-shot force)
    crisis = detect_crisis(force=FORCE_NEXT_CRISIS)
    FORCE_NEXT_CRISIS = None  # reset after one epoch
    crisis_message = crisis["message"] if crisis else None

    # 1bis) MARKET STRESS (sticky shock + slow recovery)
    # crise => MARKET_STRESS baisse, sinon il remonte doucement
    if crisis:
        MARKET_STRESS *= crisis.get("asset_impact", 1.0)
        # clamp pour éviter de tomber à 0
        MARKET_STRESS = max(0.50, MARKET_STRESS)
    else:
        # récupération lente vers 1.0
        MARKET_STRESS = min(1.0, MARKET_STRESS + 0.05)

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

    # OPEX (maintenance, assurance, opérations)
    portfolio["cash"] -= OPEX_PER_ASSET * len(portfolio["assets"])

    # grid failure penalty once per epoch
    if crisis and crisis["type"] == "grid_failure":
        portfolio["cash"] -= crisis["cash_penalty"]
        total_revenue *= (1 - crisis.get("production_drop", 0.0))

    portfolio["cash"] += total_revenue
    portfolio["cash"] = max(portfolio["cash"], 0.0)

    # 3) NAV + HWM + DRAWDOWN (HWM PREVIOUS, not including current)
    prev_hwm = max([h["nav"] for h in portfolio["nav_history"]], default=None)
    current_nav = calculate_nav(asset_multiplier)

    if prev_hwm is None:
        prev_hwm = current_nav  # first epoch

    # drawdown against PREVIOUS high water mark
    drawdown = (current_nav - prev_hwm) / prev_hwm if prev_hwm > 0 else 0.0
    drawdown = min(drawdown, 0.0)  # never positive

    # now update HWM for display/logging
    hwm = max(prev_hwm, current_nav)

    # survival flag (UX) — based on drawdown
    survival_mode = drawdown < -0.20

    # 4) decision
    decision = investment_policy(
        cash=portfolio["cash"],
        drawdown=drawdown,
        risk_tolerance=risk_tolerance,
        crisis_active=bool(crisis),
        min_cash_buffer=MIN_CASH_BUFFER
    )

    tx_hash = None

    # 5) execute deploy with SKALE settlement
    # (optional: avoid deploying during survival)
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

            # Recompute NAV after buying (still under same market stress)
            current_nav = calculate_nav(asset_multiplier)

            # drawdown must still be against previous hwm (prev_hwm), not including current
            drawdown = (current_nav - prev_hwm) / prev_hwm if prev_hwm > 0 else 0.0
            drawdown = min(drawdown, 0.0)
            hwm = max(prev_hwm, current_nav)
            survival_mode = drawdown < -0.20

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
        "market_stress": round(MARKET_STRESS, 4)
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
    current_nav = calculate_nav()
    last_epoch = nav_history[-1] if nav_history else {}

    max_nav = compute_high_water_mark(nav_history, current_nav) if nav_history else current_nav

    html = f"""
    <html>
        <head>
            <title>⚡ AI Energy Capital Entity — Control Room</title>
            <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
            <style>
                * {{ margin: 0; padding: 0; box-sizing: border-box; }}
                body {{ 
                    font-family: 'Segoe UI', Arial, sans-serif; 
                    background: #0a0a1a; 
                    color: #e0e0ff; 
                    padding: 20px; 
                }}
                .container {{ max-width: 1400px; margin: 0 auto; }}
                .header {{ text-align: center; margin-bottom: 30px; padding: 25px; border-bottom: 1px solid rgba(106, 17, 203, 0.3); }}
                .header h1 {{ 
                    font-size: 2.8em; 
                    margin-bottom: 10px; 
                    background: linear-gradient(90deg, #6a11cb 0%, #2575fc 100%);
                    -webkit-background-clip: text; 
                    -webkit-text-fill-color: transparent; 
                }}
                .header .subtitle {{ 
                    color: #aaa; 
                    font-size: 1.3em; 
                    max-width: 800px; 
                    margin: 0 auto; 
                    line-height: 1.6;
                }}
                .header .subtitle span {{ color: #00ff99; font-weight: bold; }}
                
                .grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(320px, 1fr)); gap: 25px; margin-bottom: 25px; }}
                .card {{ 
                    background: linear-gradient(145deg, #111122, #0f0f1a); 
                    padding: 28px; 
                    border-radius: 16px; 
                    box-shadow: 0 10px 30px rgba(0, 20, 40, 0.5); 
                    border: 1px solid rgba(106, 17, 203, 0.3); 
                }}
                .card h2 {{ 
                    font-size: 1.6em; 
                    margin-bottom: 20px; 
                    color: #6a11cb; 
                }}
                
                .metric {{ font-size: 2.4em; font-weight: bold; margin: 15px 0; background: linear-gradient(90deg, #6a11cb, #2575fc); -webkit-background-clip: text; -webkit-text-fill-color: transparent; }}
                .metric.smaller {{ font-size: 1.8em; }}
                .metric.positive {{ color: #00ff99; }}
                .metric.negative {{ color: #ff5252; }}
                
                .crisis-banner {{ 
                    background: rgba(255, 87, 34, 0.15); 
                    border-left: 4px solid #ff5722; 
                    padding: 12px; 
                    border-radius: 0 8px 8px 0; 
                    margin: 15px 0; 
                    font-weight: bold;
                }}
                .survival-banner {{ 
                    background: rgba(255, 165, 0, 0.15); 
                    border-left: 4px solid #ffa500; 
                    padding: 12px; 
                    border-radius: 0 8px 8px 0; 
                    margin: 15px 0; 
                    font-weight: bold;
                }}
                
                .slider-container {{ margin: 25px 0; }}
                .slider-label {{ display: flex; justify-content: space-between; margin-bottom: 12px; font-weight: bold; }}
                input[type="range"] {{ 
                    width: 100%; 
                    height: 10px; 
                    border-radius: 5px; 
                    background: linear-gradient(90deg, #ff1744 0%, #ff9100 50%, #00e676 100%); 
                    outline: none; 
                    -webkit-appearance: none; 
                }}
                input[type="range"]::-webkit-slider-thumb {{ 
                    -webkit-appearance: none; 
                    width: 28px; 
                    height: 28px; 
                    border-radius: 50%; 
                    background: white; 
                    cursor: pointer; 
                    box-shadow: 0 0 12px rgba(255, 255, 255, 0.8); 
                }}
                
                button {{ 
                    background: linear-gradient(90deg, #6a11cb, #2575fc); 
                    border: none; 
                    padding: 16px 40px; 
                    color: white; 
                    font-weight: bold; 
                    font-size: 1.2em; 
                    border-radius: 12px; 
                    cursor: pointer; 
                    margin: 12px 5px; 
                    transition: all 0.3s; 
                    box-shadow: 0 6px 20px rgba(106, 17, 203, 0.4); 
                }}
                button:hover {{ transform: translateY(-3px); box-shadow: 0 8px 25px rgba(106, 17, 203, 0.6); }}
                button:disabled {{ opacity: 0.6; cursor: not-allowed; }}
                
                .tx-badge {{ 
                    display: inline-block; 
                    background: rgba(106, 17, 203, 0.15); 
                    padding: 10px 18px; 
                    border-radius: 8px; 
                    font-family: monospace; 
                    font-size: 0.9em; 
                    margin-top: 12px; 
                    word-break: break-all; 
                    border: 1px solid rgba(106, 17, 203, 0.3);
                }}
                .tx-badge a {{ color: #6a11cb; text-decoration: none; font-weight: bold; }}
                
                .chart-container {{ position: relative; height: 380px; margin-top: 20px; }}
                .asset-item {{ 
                    padding: 12px; 
                    margin: 8px 0; 
                    background: rgba(106, 17, 203, 0.08); 
                    border-radius: 10px; 
                    border-left: 4px solid #6a11cb; 
                }}
                .asset-item.solar {{ border-left-color: #ff9100; background: rgba(255, 145, 0, 0.08); }}
                
                .philosophy {{ 
                    background: rgba(0, 20, 40, 0.6); 
                    border-left: 4px solid #6a11cb; 
                    padding: 20px; 
                    border-radius: 0 12px 12px 0; 
                    margin: 25px 0; 
                    font-style: italic; 
                    line-height: 1.7;
                }}
            </style>
        </head>
        <body>
            <div class="container">
                <div class="header">
                    <h1>⚡ AI ENERGY CAPITAL ENTITY</h1>
                    <p class="subtitle">Autonomous on-chain capital allocator for energy assets — Powered by <span>SKALE x402</span></p>
                </div>

                <div class="grid">
                    <div class="card">
                        <h2>📊 Net Asset Value</h2>
                        <div class="metric">{current_nav:.4f} €</div>
                        <p style="color: #aaa; font-size: 1.05em;">
                            High Water Mark: {max_nav:.4f} €<br>
                            Drawdown: <span class="metric {'negative' if last_epoch.get('drawdown', 0) < 0 else 'positive'}">{last_epoch.get('drawdown', 0) * 100:.2f}%</span>
                        </p>
                        {f'<div class="crisis-banner">{last_epoch.get("crisis")}</div>' if last_epoch.get("crisis") else ''}
                        {f'<div class="survival-banner">🛡️ SURVIVAL MODE ACTIVE — Capital preservation priority</div>' if last_epoch.get("survival_mode") else ''}
                    </div>

                    <div class="card">
                        <h2>🏭 Energy Assets</h2>
                        <div class="metric">{len(portfolio['assets'])}</div>
                        <p style="color: #aaa; font-size: 1.05em;">
                            Tokenized production capacity<br>
                            Total: {sum(a['capacity_kw'] for a in portfolio['assets']):.1f} kW
                        </p>
                        <div style="margin-top: 15px;">
                            {"".join([
                                f'<div class="asset-item solar">⚡ {a["id"]} | {a["capacity_kw"]:.0f} kW | {a["efficiency"]:.0%} eff.</div>'
                                for a in portfolio['assets'][-3:]
                            ])}
                        </div>
                    </div>

                    <div class="card">
                        <h2>💰 Treasury</h2>
                        <div class="metric smaller">{portfolio['cash']:.4f} €</div>
                        <p style="color: #aaa; font-size: 1.05em;">
                            Liquid reserves<br>
                            Available for capital deployment
                        </p>
                        <p><b>Last Decision:</b> {last_epoch.get('decision', 'N/A').replace('_', ' ').title()}</p>
                        {f'''
                        <div class="tx-badge">
                            <b>SKALE TX:</b> <a href="https://base-sepolia-testnet-explorer.skalenodes.com:10032/tx/{last_epoch.get("tx_hash")}" target="_blank">
                                {last_epoch.get("tx_hash")[:12]}...
                            </a>
                        </div>
                        ''' if last_epoch.get("tx_hash") else ''}
                    </div>
                </div>

                <div class="grid">
                    <div class="card">
                        <h2>🎛️ Capital Allocation</h2>
                        <div class="philosophy">
                            "Optimizing for <strong>long-term capital growth under uncertainty</strong> — not short-term profit maximization."
                        </div>
                        <div class="slider-container">
                            <div class="slider-label">
                                <span>Risk Tolerance</span>
                                <span id="riskValue">0.7</span>
                            </div>
                            <input type="range" min="0" max="1" step="0.1" value="0.7" id="riskSlider">
                            <p style="color: #aaa; font-size: 0.9em; margin-top: 10px;">
                                <span style="color: #ff1744;">← Capital Preservation</span> | 
                                <span style="color: #00e676;">Growth →</span>
                            </p>
                        </div>

                        <button onclick="runEpoch()" id="runBtn">▶ Run Capital Epoch</button>
                        <button onclick="runDemo()" id="demoBtn">🚀 SKALE Settlement Demo</button>

                        <div id="result" style="margin-top: 20px; min-height: 80px;"></div>
                    </div>

                    <div class="card">
                        <h2>📈 NAV Growth Curve</h2>
                        <div class="chart-container">
                            <canvas id="navChart"></canvas>
                        </div>
                    </div>
                </div>
            </div>

            <script>
            const navData = {json.dumps(nav_history)};

            if (navData.length > 0) {{
                const ctx = document.getElementById('navChart').getContext('2d');
                new Chart(ctx, {{
                    type: 'line',
                    data: {{
                        labels: navData.map(h => "Epoch " + h.step),
                        datasets: [{{
                            label: 'NAV (€)',
                            data: navData.map(h => h.nav),
                            borderColor: '#6a11cb',
                            backgroundColor: 'rgba(106, 17, 203, 0.1)',
                            borderWidth: 4,
                            tension: 0.3,
                            fill: true,
                            pointRadius: 5,
                            pointBackgroundColor: '#6a11cb'
                        }}]
                    }},
                    options: {{
                        responsive: true,
                        maintainAspectRatio: false,
                        plugins: {{
                            legend: {{ labels: {{ color: '#e0e0ff', font: {{ size: 14 }} }} }},
                        }},
                        scales: {{
                            x: {{ ticks: {{ color: '#888' }}, grid: {{ color: 'rgba(106, 17, 203, 0.1)' }} }},
                            y: {{ ticks: {{ color: '#888' }}, grid: {{ color: 'rgba(106, 17, 203, 0.1)' }} }}
                        }}
                    }}
                }});
            }}

            const slider = document.getElementById('riskSlider');
            const riskValue = document.getElementById('riskValue');
            slider.oninput = function() {{ riskValue.innerText = this.value; }};

            async function runEpoch() {{
                const btn = document.getElementById('runBtn');
                const resDiv = document.getElementById('result');
                const risk = slider.value;

                btn.disabled = true;
                btn.innerHTML = '⏳ Executing...';
                resDiv.innerHTML = '';

                try {{
                    const res = await fetch(`/run_epoch?risk_tolerance=${{risk}}`);
                    const data = await res.json();

                    let crisisHtml = '';
                    if (data.crisis) {{
                        crisisHtml = `<div class="crisis-banner">${{data.crisis}}</div>`;
                    }}
                    if (data.survival_mode) {{
                        crisisHtml += `<div class="survival-banner">🛡️ SURVIVAL MODE ACTIVE</div>`;
                    }}

                    resDiv.innerHTML = `
                        <p style="color: #00e676; font-weight: bold;">✅ Epoch ${{data.step}} completed</p>
                        <p>NAV: ${{data.nav.toFixed(4)}} € | Drawdown: ${{(data.drawdown * 100).toFixed(2)}}%</p>
                        <p>Decision: <strong>${{data.decision.replace('_', ' ')}}</strong></p>
                        ${{crisisHtml}}
                        ${{data.tx_hash ? `<div class="tx-badge"><a href="https://base-sepolia-testnet-explorer.skalenodes.com:10032/tx/${{data.tx_hash}}" target="_blank">TX: ${{data.tx_hash.substring(0, 14)}}...</a></div>` : ''}}
                    `;

                    setTimeout(() => {{ location.reload(); }}, 1800);
                }} catch (error) {{
                    resDiv.innerHTML = `<p style="color: #ff5252;">❌ Error: ${{error.message}}</p>`;
                    btn.disabled = false;
                    btn.innerHTML = '▶ Run Capital Epoch';
                }}
            }}

            async function runDemo() {{
                const btn = document.getElementById('demoBtn');
                const resDiv = document.getElementById('result');

                btn.disabled = true;
                btn.innerHTML = '⏳ Settling...';
                resDiv.innerHTML = '';

                try {{
                    const res = await fetch('/demo', {{ method: 'POST' }});
                    const data = await res.json();

                    if (data.status === 'success') {{
                        resDiv.innerHTML = `
                            <p style="color: #00e676; font-weight: bold;">${{data.message}}</p>
                            <p style="font-size: 0.95em; margin: 10px 0;"><b>Settlement TX:</b> ${{data.tx_hash.substring(0, 18)}}...</p>
                            <a href="${{data.explorer}}" target="_blank" style="display: inline-block; margin-top: 12px; padding: 10px 20px; background: linear-gradient(90deg, #6a11cb, #2575fc); color: white; border-radius: 10px; text-decoration: none; font-weight: bold;">
                                🔍 View SKALE Settlement
                            </a>
                        `;
                    }} else {{
                        resDiv.innerHTML = `<p style="color: #ff5252;">${{data.message}}</p>`;
                    }}
                }} catch (error) {{
                    resDiv.innerHTML = `<p style="color: #ff5252;">❌ Network error: ${{error.message}}</p>`;
                }} finally {{
                    btn.disabled = false;
                    btn.innerHTML = '🚀 SKALE Settlement Demo';
                }}
            }}
            </script>
        </body>
    </html>
    """
    return html
