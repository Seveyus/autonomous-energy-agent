from fastapi import FastAPI, HTTPException
from uuid import uuid4
from environment import get_environment_state
from agent import decide_action, get_premium_data
from skale_payment import send_payment, address
from fastapi.responses import HTMLResponse
import random
import json

app = FastAPI(title="Agentic Commerce Energy Node")

# --- État Global ---
agent_budget = 1.0
history = []
valid_transactions = set()

# ===== PORTFOLIO STATE =====
portfolio = {
    "cash": 1.0,  # €
    "assets": [
        {"id": "SOLAR-1", "type": "solar", "capacity_kw": 100, "efficiency": 0.85, "acquisition_cost": 0.5}
    ],
    "energy_tokens": 0,
    "nav_history": [{"step": 0, "nav": 1.0}]  # Net Asset Value history
}

def calculate_nav():
    """Net Asset Value = cash + valeur des actifs"""
    asset_value = sum(asset["capacity_kw"] * 0.01 for asset in portfolio["assets"])  # 0.01€/kW simplifié
    return round(portfolio["cash"] + asset_value, 4)

@app.get("/run_epoch")
def run_epoch(risk_tolerance: float = 0.7):
    """
    Un "epoch" = 1 cycle de production + décision stratégique
    """
    global portfolio
    
    # === 1. PRODUCTION D'ÉNERGIE (revenus passifs) ===
    total_production = 0
    total_revenue = 0
    
    for asset in portfolio["assets"]:
        state = get_environment_state()
        production = asset["capacity_kw"] * asset["efficiency"] * (state["solar_production"] / 100)
        revenue = production * state["energy_price"]
        
        total_production += production
        total_revenue += revenue
    
    portfolio["cash"] += total_revenue
    
    # === 2. DÉCISION STRATÉGIQUE : réinvestir ? ===
    nav = calculate_nav()
    decision = "hold_cash"
    tx_hash = None
    
    # Logique de réinvestissement autonome
    if portfolio["cash"] >= 0.5:  # Seuil de déploiement de capital
        # Simule la valeur attendue d'un nouvel actif
        projected_roi = random.uniform(-0.1, 0.3)  # ROI incertain
        
        # Risk tolerance ajuste l'appétit pour le risque
        risk_adjusted_threshold = -0.05 + (0.15 * risk_tolerance)
        
        if projected_roi > risk_adjusted_threshold:
            # === 3. DÉPLOIEMENT DE CAPITAL (via SKALE) ===
            try:
                # Paiement SKALE réel = preuve de déploiement de capital
                tx_hash_bytes = send_payment(address, 0.001)
                tx_hash = "0x" + tx_hash_bytes.hex()
                valid_transactions.add(tx_hash)
                
                # Acquisition d'un nouvel actif
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
                
            except Exception as e:
                decision = f"deploy_failed: {str(e)}"
    
    # === 4. LOG NAV ===
    nav = calculate_nav()
    portfolio["nav_history"].append({
        "step": len(portfolio["nav_history"]),
        "nav": nav,
        "decision": decision,
        "cash": round(portfolio["cash"], 4),
        "asset_count": len(portfolio["assets"])
    })
    
    return {
        "step": len(portfolio["nav_history"]) - 1,
        "decision": decision,
        "risk_tolerance": round(risk_tolerance, 2),
        "production_kwh": round(total_production, 2),
        "revenue": round(total_revenue, 4),
        "cash": round(portfolio["cash"], 4),
        "asset_count": len(portfolio["assets"]),
        "nav": nav,
        "tx_hash": tx_hash
    }

@app.get("/history")
def get_history():
    return {
        "total_steps": len(history),
        "total_net_profit": sum(item["net_profit"] for item in history),
        "logs": history
    }

@app.post("/x402/pay")
def x402_pay():
    try:
        tx_hash = send_payment(address, 0.001)
        tx_hash_hex = tx_hash.hex()
        valid_transactions.add(tx_hash_hex)
        return {
            "status": "paid",
            "tx_hash": tx_hash_hex,
            "explorer": f"https://base-sepolia-testnet-explorer.skalenodes.com:10032/tx/{tx_hash_hex}"
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/premium-weather")
def premium_weather(tx_hash: str = None):
    if tx_hash not in valid_transactions:
        raise HTTPException(status_code=402, detail="Payment Required - x402 workflow")
    return {
        "solar_production_precise": 85.0,
        "provider_signature": "signed_by_skale_oracle"
    }

@app.post("/demo")
def run_demo():
    try:
        tx_hash_bytes = send_payment("0xACB50534AcC7C5CD74b776B97d0c91Dc0D602AA3", 0.001)
        tx_hash = "0x" + tx_hash_bytes.hex()
        explorer_url = f"https://base-sepolia-testnet-explorer.skalenodes.com:10032/tx/{tx_hash}"
        return {
            "status": "success",
            "message": "✅ SKALE settlement confirmed",
            "tx_hash": tx_hash,
            "explorer": explorer_url
        }
    except Exception as e:
        print(f"❌ Erreur dans /demo : {e}")
        import traceback
        traceback.print_exc()
        return {
            "status": "error",
            "message": f"❌ Erreur : {str(e)}"
        }

@app.get("/dashboard", response_class=HTMLResponse)
def dashboard():
    nav_history = portfolio["nav_history"]
    current_nav = calculate_nav()
    last_epoch = nav_history[-1] if nav_history else {}
    
    # JSON pour Chart.js
    import json
    nav_json = json.dumps(nav_history)
    
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
                .header {{ text-align: center; margin-bottom: 30px; padding: 25px; border-bottom: 1px solid rgba(0, 204, 255, 0.3); }}
                .header h1 {{ 
                    font-size: 2.8em; 
                    margin-bottom: 10px; 
                    background: linear-gradient(90deg, #6a11cb 0%, #2575fc 100%);
                    -webkit-background-clip: text; 
                    -webkit-text-fill-color: transparent; 
                    letter-spacing: -0.5px;
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
                    transition: transform 0.3s ease;
                }}
                .card:hover {{ transform: translateY(-3px); border-color: rgba(106, 17, 203, 0.6); }}
                .card h2 {{ 
                    font-size: 1.6em; 
                    margin-bottom: 20px; 
                    color: #6a11cb; 
                    display: flex; 
                    align-items: center; 
                    gap: 10px;
                }}
                .card h2 svg {{ width: 24px; height: 24px; }}
                
                .metric {{ font-size: 2.4em; font-weight: bold; margin: 15px 0; background: linear-gradient(90deg, #6a11cb, #2575fc); -webkit-background-clip: text; -webkit-text-fill-color: transparent; }}
                .metric.smaller {{ font-size: 1.8em; }}
                .metric.growth {{ color: #00ff99; }}
                
                .decision-badge {{ 
                    display: inline-block; 
                    padding: 8px 20px; 
                    border-radius: 24px; 
                    font-weight: bold; 
                    margin: 8px 0; 
                    font-size: 1.1em;
                }}
                .decision-badge.deploy {{ 
                    background: linear-gradient(90deg, #00c853, #64dd17); 
                    color: #0a2a0a; 
                }}
                .decision-badge.hold {{ 
                    background: linear-gradient(90deg, #2979ff, #448aff); 
                    color: #e0e0ff; 
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
                    display: inline-flex; 
                    align-items: center; 
                    gap: 10px;
                }}
                button:hover {{ 
                    transform: translateY(-3px); 
                    box-shadow: 0 8px 25px rgba(106, 17, 203, 0.6); 
                }}
                button:disabled {{ opacity: 0.6; cursor: not-allowed; transform: none; }}
                
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
                .tx-badge a:hover {{ text-decoration: underline; }}
                
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
                .philosophy strong {{ color: #00ff99; }}
                
                @media (max-width: 768px) {{
                    .grid {{ grid-template-columns: 1fr; }}
                    .header h1 {{ font-size: 2.2em; }}
                    .metric {{ font-size: 2em; }}
                }}
            </style>
        </head>
        <body>
            <div class="container">
                <div class="header">
                    <h1>⚡ AI ENERGY CAPITAL ENTITY</h1>
                    <p class="subtitle">Autonomous capital allocation on <span>SKALE x402</span> — This is not an agent. This is a proto-economic organism.</p>
                </div>

                <!-- Row 1: NAV + Assets + Cash -->
                <div class="grid">
                    <div class="card">
                        <h2>📊 Net Asset Value</h2>
                        <div class="metric growth">{current_nav:.4f} €</div>
                        <p style="color: #aaa; font-size: 1.05em;">
                            Autonomous capital growth<br>
                            <span style="color: #00ff99;">+{current_nav - 1.0:.4f} €</span> since inception
                        </p>
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
                                for a in portfolio['assets'][-3:]  # Last 3 assets
                            ])}
                            {"" if len(portfolio['assets']) > 3 else ""}
                        </div>
                    </div>

                    <div class="card">
                        <h2>💰 Treasury</h2>
                        <div class="metric smaller">{portfolio['cash']:.4f} €</div>
                        <p style="color: #aaa; font-size: 1.05em;">
                            Liquid reserves<br>
                            Available for capital deployment
                        </p>
                        {f'''
                        <div class="decision-badge {'deploy' if last_epoch.get('decision', '').startswith('deploy') else 'hold'}">
                            ▶️ Last: {last_epoch.get('decision', 'N/A').replace('_', ' ')}
                        </div>
                        ''' if last_epoch else ''}
                    </div>
                </div>

                <!-- Row 2: Controls + Chart -->
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

                        <button onclick="runEpoch()" id="runBtn">
                            <svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" stroke-width="2">
                                <path d="M5 3l14 9-14 9V3z"></path>
                            </svg>
                            Run Capital Epoch
                        </button>
                        <button onclick="runDemo()" id="demoBtn">
                            <svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" stroke-width="2">
                                <path d="M12 8V4l8 8-8 8v-4H4V8z"></path>
                            </svg>
                            SKALE Settlement Demo
                        </button>
                        
                        <div id="result" style="margin-top: 20px; min-height: 80px;"></div>
                    </div>

                    <div class="card">
                        <h2>📈 NAV Growth Curve</h2>
                        <div class="chart-container">
                            <canvas id="navChart"></canvas>
                        </div>
                    </div>
                </div>

                <!-- Row 3: Philosophy -->
                <div class="card">
                    <h2>🧠 Economic Architecture</h2>
                    <ul style="padding-left: 25px; line-height: 2.0; font-size: 1.1em;">
                        <li>Autonomous <strong>production</strong> → generates cash flow</li>
                        <li>Strategic <strong>capital allocation</strong> → deploys reserves into new assets</li>
                        <li>On-chain <strong>settlement</strong> → SKALE x402 for capital deployment events</li>
                        <li>Uncertainty-aware <strong>decision making</strong> → risk tolerance modulates investment appetite</li>
                    </ul>
                    <p style="margin-top: 20px; padding: 15px; background: rgba(0, 30, 60, 0.4); border-radius: 10px; font-style: italic;">
                        This entity owns assets, generates revenue, and reinvests autonomously — 
                        <strong>a machine-native economic actor</strong> with on-chain treasury operations.
                    </p>
                </div>

            </div>

            <script>
            // ========== NAV Chart ==========
            const navData = {nav_json};
            
            if (navData.length > 0) {{
                const ctx = document.getElementById('navChart').getContext('2d');
                
                new Chart(ctx, {{
                    type: 'line',
                    data: {{
                        labels: navData.map(h => "Epoch " + h.step),
                        datasets: [{{
                            label: 'Net Asset Value (€)',
                            data: navData.map(h => h.nav),
                            borderColor: '#6a11cb',
                            backgroundColor: 'rgba(106, 17, 203, 0.1)',
                            borderWidth: 4,
                            tension: 0.3,
                            fill: true,
                            pointRadius: 5,
                            pointBackgroundColor: '#6a11cb',
                            pointHoverRadius: 8
                        }}]
                    }},
                    options: {{
                        responsive: true,
                        maintainAspectRatio: false,
                        plugins: {{
                            legend: {{ 
                                labels: {{ color: '#e0e0ff', font: {{ size: 14 }} }} 
                            }},
                            tooltip: {{
                                backgroundColor: 'rgba(10, 10, 26, 0.95)',
                                titleColor: '#6a11cb',
                                bodyColor: '#e0e0ff',
                                borderColor: '#6a11cb',
                                borderWidth: 1,
                                padding: 12
                            }}
                        }},
                        scales: {{
                            x: {{ 
                                ticks: {{ color: '#888', font: {{ size: 12 }} }},
                                grid: {{ color: 'rgba(106, 17, 203, 0.1)' }}
                            }},
                            y: {{ 
                                ticks: {{ color: '#888', font: {{ size: 12 }} }},
                                grid: {{ color: 'rgba(106, 17, 203, 0.1)' }}
                            }}
                        }}
                    }}
                }});
            }}

            // ========== Risk Slider ==========
            const slider = document.getElementById('riskSlider');
            const riskValue = document.getElementById('riskValue');
            
            slider.oninput = function() {{
                riskValue.innerText = this.value;
            }};

            // ========== Run Epoch ==========
            async function runEpoch() {{
                const btn = document.getElementById('runBtn');
                const resDiv = document.getElementById('result');
                
                const risk = slider.value;
                btn.disabled = true;
                btn.innerHTML = '<svg viewBox="0 0 24 24" width="20" height="20" stroke="white" stroke-width="2" fill="none"><circle cx="12" cy="12" r="8" stroke-dasharray="15" stroke-dashoffset="0" transform="rotate(0 12 12)"><animateTransform attributeName="transform" type="rotate" from="0 12 12" to="360 12 12" dur="1s" repeatCount="indefinite"/></circle></svg> Executing...';
                resDiv.innerHTML = '';
                
                try {{
                    const res = await fetch(`/run_epoch?risk_tolerance=${{risk}}`);
                    const data = await res.json();
                    
                    if (data.detail) {{
                        resDiv.innerHTML = `<p style="color: #ff5252;">❌ ${{data.detail}}</p>`;
                    }} else {{
                        const badgeClass = data.decision.includes('deploy') ? 'deploy' : 'hold';
                        const badgeText = data.decision.replace('_', ' ').replace('deploy', '🚀 DEPLOY').replace('hold', '⏸️ HOLD');
                        
                        let txHtml = '';
                        if (data.tx_hash) {{
                            txHtml = `<div class="tx-badge"><a href="https://base-sepolia-testnet-explorer.skalenodes.com:10032/tx/${{data.tx_hash}}" target="_blank">TX: ${{data.tx_hash.substring(0, 14)}}...</a></div>`;
                        }}
                        
                        resDiv.innerHTML = `
                            <p style="color: #00e676; font-weight: bold;">✅ Epoch ${{data.step}} completed</p>
                            <p><span class="decision-badge ${{badgeClass}}">{{$badgeText}}</span></p>
                            <p>Production: ${{data.production_kwh.toFixed(1)}} kWh → Revenue: ${{data.revenue.toFixed(4)}} €</p>
                            <p>NAV: ${{data.nav.toFixed(4)}} € | Assets: ${{data.asset_count}}</p>
                            ${{txHtml}}
                        `;
                    }}
                    
                    setTimeout(() => {{ location.reload(); }}, 1800);
                    
                }} catch (error) {{
                    resDiv.innerHTML = `<p style="color: #ff5252;">❌ Error: ${{error.message}}</p>`;
                    btn.disabled = false;
                    btn.innerHTML = '<svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" stroke-width="2"><path d="M5 3l14 9-14 9V3z"></path></svg> Run Capital Epoch';
                }}
            }}

            // ========== Quick Demo ==========
            async function runDemo() {{
                const btn = document.getElementById('demoBtn');
                const resDiv = document.getElementById('result');
                
                btn.disabled = true;
                btn.innerHTML = '<svg viewBox="0 0 24 24" width="20" height="20" stroke="white" stroke-width="2" fill="none"><circle cx="12" cy="12" r="8" stroke-dasharray="15" stroke-dashoffset="0" transform="rotate(0 12 12)"><animateTransform attributeName="transform" type="rotate" from="0 12 12" to="360 12 12" dur="1s" repeatCount="indefinite"/></circle></svg> Settling...';
                resDiv.innerHTML = '';
                
                try {{
                    const res = await fetch('/demo', {{ method: 'POST' }});
                    const data = await res.json();
                    
                    if (data.status === 'success') {{
                        resDiv.innerHTML = `
                            <p style="color: #00e676; font-weight: bold;">${{data.message}}</p>
                            <p style="font-size: 0.95em; margin: 10px 0;"><b>Settlement TX:</b> ${{data.tx_hash.substring(0, 18)}}...</p>
                            <a href="${{data.explorer}}" target="_blank" style="display: inline-block; margin-top: 12px; padding: 10px 20px; background: linear-gradient(90deg, #6a11cb, #2575fc); color: white; border-radius: 10px; text-decoration: none; font-weight: bold; box-shadow: 0 4px 15px rgba(106, 17, 203, 0.4);">
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
                    btn.innerHTML = '<svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" stroke-width="2"><path d="M12 8V4l8 8-8 8v-4H4V8z"></path></svg> SKALE Settlement Demo';
                }}
            }}
            </script>
        </body>
    </html>
    """
    
    return html