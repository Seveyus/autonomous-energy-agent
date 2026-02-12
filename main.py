from fastapi import FastAPI, HTTPException
from environment import get_environment_state
from agent import decide_action, get_premium_data, detect_crisis
from skale_payment import send_payment, address
from fastapi.responses import HTMLResponse
import random
import json

app = FastAPI(title="AI Energy Capital Entity — SKALE x402")

# --- État Global ---
# Initialisation avec un historique vide mais correct pour le démarrage
portfolio = {
    "cash": 1.0,
    "assets": [
        {"id": "SOLAR-1", "type": "solar", "capacity_kw": 100, "efficiency": 0.85, "acquisition_cost": 0.5}
    ],
    "nav_history": [{"step": 0, "nav": 1.425, "drawdown": 0.0, "crisis": None, "survival_mode": False}]
}

def calculate_nav():
    """
    Calcul du Net Asset Value (Valeur Liquidative).
    CORRECTION : Valorisation conservatrice pour éviter l'effet 'Money Printer'.
    Valeur = Capacité * Efficacité * Facteur de marché (0.005)
    Exemple : 100kW * 0.85 * 0.005 = 0.425€ (pour un coût d'achat de 0.5€)
    L'agent doit donc produire pour rentabiliser l'investissement.
    """
    asset_value = sum(asset["capacity_kw"] * asset["efficiency"] * 0.005 for asset in portfolio["assets"])
    return round(portfolio["cash"] + asset_value, 4)

# Recalcul du NAV initial pour être cohérent avec la nouvelle formule
initial_nav = calculate_nav()
portfolio["nav_history"][0]["nav"] = initial_nav

@app.get("/run_epoch")
def run_epoch(risk_tolerance: float = 0.7):
    global portfolio
    
    # === 1. DÉTECTION DE CRISE ===
    crisis = detect_crisis()
    crisis_message = crisis["message"] if crisis else None
    
    # === 2. PRODUCTION D'ÉNERGIE ===
    total_production = 0
    total_revenue = 0
    
    for asset in portfolio["assets"]:
        state = get_environment_state()
        base_production = asset["capacity_kw"] * asset["efficiency"] * (state["solar_production"] / 100)
        price = state["energy_price"]
        
        # Appliquer l'impact de la crise
        if crisis:
            if crisis["type"] == "cloud_cover":
                base_production *= (1 - crisis["production_drop"])
            elif crisis["type"] == "price_crash":
                price *= (1 - crisis["price_drop"])
            elif crisis["type"] == "grid_failure":
                # Pénalité directe sur le cash
                portfolio["cash"] -= crisis["penalty"]
        
        revenue = base_production * price
        total_production += base_production
        total_revenue += revenue
    
    portfolio["cash"] += total_revenue
    
    # === 3. CALCUL NAV & DRAWDOWN (CORRIGÉ) ===
    current_nav = calculate_nav()
    
    # Trouver le High Water Mark (Plus haut historique) INCLUANT l'actuel
    all_navs = [entry["nav"] for entry in portfolio["nav_history"]]
    all_navs.append(current_nav)
    max_nav = max(all_navs)
    
    # Drawdown est toujours négatif ou zéro : (Actuel - Sommet) / Sommet
    if max_nav > 0:
        drawdown = (current_nav - max_nav) / max_nav
    else:
        drawdown = 0.0
        
    # Mode survie si NAV chute trop bas
    survival_mode = current_nav < 0.8  # Seuil ajusté
    
    # === 4. DÉPLOIEMENT DE CAPITAL ===
    decision = "hold_cash"
    tx_hash = None
    
    # On n'achète que si on a le cash ET qu'on n'est pas en mode survie
    if portfolio["cash"] >= 0.5 and not survival_mode:
        projected_roi = random.uniform(-0.1, 0.3)
        risk_adjusted_threshold = -0.05 + (0.15 * risk_tolerance)
        
        if projected_roi > risk_adjusted_threshold:
            try:
                # Paiement SKALE
                tx_hash_bytes = send_payment(address, 0.001)
                tx_hash = "0x" + tx_hash_bytes.hex()
                
                # Acquisition
                new_asset = {
                    "id": f"SOLAR-{len(portfolio['assets']) + 1}",
                    "type": "solar",
                    "capacity_kw": random.uniform(80, 120),
                    "efficiency": random.uniform(0.80, 0.92),
                    "acquisition_cost": 0.5
                }
                
                portfolio["cash"] -= 0.5
                portfolio["assets"].append(new_asset)
                decision = "deploy_capital"
                
                # Recalcul du NAV après achat (légère baisse due au spread achat/valeur)
                current_nav = calculate_nav()
                
            except Exception as e:
                decision = f"deploy_failed: {str(e)}"
    
    # === 5. LOGGING ===
    portfolio["nav_history"].append({
        "step": len(portfolio["nav_history"]),
        "nav": current_nav,
        "drawdown": round(drawdown, 4),
        "crisis": crisis_message,
        "survival_mode": survival_mode,
        "decision": decision,
        "cash": round(portfolio["cash"], 4),
        "asset_count": len(portfolio["assets"]),
        "tx_hash": tx_hash
    })
    
    return {
        "step": len(portfolio["nav_history"]) - 1,
        "decision": decision,
        "risk_tolerance": round(risk_tolerance, 2),
        "production_kwh": round(total_production, 2),
        "revenue": round(total_revenue, 4),
        "cash": round(portfolio["cash"], 4),
        "asset_count": len(portfolio["assets"]),
        "nav": current_nav,
        "drawdown": round(drawdown, 4),
        "crisis": crisis_message,
        "survival_mode": survival_mode,
        "tx_hash": tx_hash
    }

@app.get("/history")
def get_history():
    return portfolio["nav_history"]

@app.post("/x402/pay")
def x402_pay():
    try:
        tx_hash = send_payment(address, 0.001)
        tx_hash_hex = tx_hash.hex()
        return {
            "status": "paid",
            "tx_hash": tx_hash_hex,
            "explorer": f"https://base-sepolia-testnet-explorer.skalenodes.com:10032/tx/{tx_hash_hex}"
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/premium-weather")
def premium_weather(tx_hash: str = None):
    return {"solar_production_precise": 85.0}

@app.post("/demo")
def run_demo():
    try:
        tx_hash_bytes = send_payment(address, 0.001)
        tx_hash = "0x" + tx_hash_bytes.hex()
        explorer_url = f"https://base-sepolia-testnet-explorer.skalenodes.com:10032/tx/{tx_hash}"
        return {
            "status": "success",
            "message": "✅ SKALE settlement confirmed — capital deployment event recorded on-chain",
            "tx_hash": tx_hash,
            "explorer": explorer_url
        }
    except Exception as e:
        return {"status": "error", "message": f"❌ Erreur : {str(e)}"}

# ===== DASHBOARD =====
@app.get("/dashboard", response_class=HTMLResponse)
def dashboard():
    nav_history = portfolio["nav_history"]
    current_nav = calculate_nav()
    last_epoch = nav_history[-1] if nav_history else {}
    
    # Calcul du Max NAV pour l'affichage
    max_nav = max(entry["nav"] for entry in nav_history) if nav_history else current_nav
    
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
                /* Note: Drawdown est "positif" (vert) s'il est proche de 0, "négatif" (rouge) s'il est profond */
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
                            Drawdown: <span class="metric {'negative' if last_epoch.get('drawdown', 0) < -0.1 else 'positive'}">{last_epoch.get('drawdown', 0) * 100:.2f}%</span>
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
            // On injecte les données Python ici (Format validé)
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
                            tooltip: {{
                                backgroundColor: 'rgba(10, 10, 26, 0.95)',
                                titleColor: '#6a11cb',
                                bodyColor: '#e0e0ff',
                                borderColor: '#6a11cb',
                                borderWidth: 1
                            }}
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