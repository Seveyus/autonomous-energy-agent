from fastapi import FastAPI, HTTPException
from uuid import uuid4
from environment import get_environment_state
from agent import decide_action, get_premium_data
from skale_payment import send_payment, address
from fastapi.responses import HTMLResponse
import web3
from agent import PREMIUM_DATA_COST, ESTIMATION_ERROR_FACTOR
import random


app = FastAPI(title="Agentic Commerce Energy Node")

# --- État Global ---
agent_budget = 1.0  # Budget initial en sFUEL ou monnaie simulée
history = []
valid_transactions = set()


@app.get("/run")
def run_agent(risk_tolerance: float = 0.7):
    """
    risk_tolerance: 0.0 (conservateur) → 1.0 (agressif)
    """
    global agent_budget

    if agent_budget <= 0:
        return {"error": "Budget exhausted"}

    # 1. Perception de l'environnement
    state = get_environment_state()
    solar = state["solar_production"]
    price = state["energy_price"]
    consumption = state["consumption"]

    # 2. Décision stratégique
    decision = decide_action(state, agent_budget, risk_tolerance)
    
    premium_data = None
    tx_hash = None

    if decision == "buy_premium_data":
        # 3. Workflow x402 (paiement SKALE réel)
        try:
            premium_response = get_premium_data()
            premium_data = premium_response["data"]
            if premium_response["transaction"]:
                tx_hash = premium_response["transaction"]["tx_hash"]
            
            agent_budget -= PREMIUM_DATA_COST
            if tx_hash:
                valid_transactions.add(tx_hash)
        except Exception as e:
            return {"error": f"Payment failed: {str(e)}"}

    # 4. Calcul économique
    error_basic = random.uniform(-ESTIMATION_ERROR_FACTOR, ESTIMATION_ERROR_FACTOR)
    estimated_prod_basic = solar * (1 + error_basic)
    basic_profit = (estimated_prod_basic - consumption) * price

    if premium_data:  # ✅ CORRIGÉ : pas de typo
        precise_prod = premium_data.get("solar_production_precise", solar)
        premium_profit = (precise_prod - consumption) * price
        net_profit = premium_profit - PREMIUM_DATA_COST
    else:
        premium_profit = basic_profit
        net_profit = basic_profit

    # 5. Archivage
    log_entry = {
        "step": len(history) + 1,
        "decision": decision,
        "risk_tolerance": round(risk_tolerance, 2),
        "tx_hash": tx_hash,
        "basic_profit_estimate": round(basic_profit, 4),
        "premium_profit": round(premium_profit, 4),
        "net_profit": round(net_profit, 4),
        "remaining_budget": round(agent_budget, 4),
        "solar": round(solar, 2),
        "price": round(price, 4)
    }
    history.append(log_entry)

    return log_entry

@app.get("/history")
def get_history():
    return {
        "total_steps": len(history),
        "total_net_profit": sum(item["net_profit"] for item in history),
        "logs": history
    }

@app.post("/x402/pay")
def x402_pay():
    """Endpoint déclenché par l'agent pour valider un paiement sur SKALE"""
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
    """Le service qui ne délivre la donnée que si le paiement est prouvé"""
    if tx_hash not in valid_transactions:
        raise HTTPException(status_code=402, detail="Payment Required - x402 workflow")

    return {
        "solar_production_precise": 85.0,
        "provider_signature": "signed_by_skale_oracle"
    }
@app.post("/demo")
def run_demo():
    """
    Démo 1-clic pour les juges : utilise ta fonction send_payment existante
    """
    try:
        # Appelle TA fonction send_payment (elle retourne des bytes)
        tx_hash_bytes = send_payment("0xACB50534AcC7C5CD74b776B97d0c91Dc0D602AA3", 0.001)
        
        # ✅ CORRECTION : ajouter "0x" au début
        tx_hash = "0x" + tx_hash_bytes.hex()
        
        explorer_url = f"https://base-sepolia-testnet-explorer.skalenodes.com:10032/tx/{tx_hash}"
        
        return {
            "status": "success",
            "message": "✅ Transaction SKALE confirmée !",
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
    last = history[-1] if history else {}
    total_net_profit = round(sum(item.get("net_profit", 0) for item in history), 4)
    
    # Template HTML avec JS séparé (pas de conflit d'accolades)
    html = f"""
    <html>
        <head>
            <title>Autonomous Energy Agent</title>
            <style>
                body {{ font-family: Arial; padding: 40px; background: #111; color: #eee; }}
                .card {{ background: #1e1e1e; padding: 20px; margin-bottom: 20px; border-radius: 8px; }}
                .green {{ color: #00ff99; }}
                .red {{ color: #ff5555; }}
                a {{ color: #00ccff; text-decoration: none; }}
                a:hover {{ text-decoration: underline; }}
                button {{ 
                    padding: 12px 24px; 
                    background: #00ccff; 
                    border: none; 
                    border-radius: 6px; 
                    color: #111; 
                    font-weight: bold; 
                    cursor: pointer; 
                    margin: 20px 0;
                }}
                button:hover {{ background: #00aacc; }}
                #result {{ margin-top: 20px; padding: 15px; background: #2a2a2a; border-radius: 6px; }}
            </style>
        </head>
        <body>
            <h1>⚡ Autonomous Energy Market Agent</h1>

            <div class="card">
                <h2>💰 Budget Remaining: {agent_budget:.2f}</h2>
            </div>

            <div class="card">
                <h3>🧠 Last Decision</h3>
                <p>Decision: <b>{last.get("decision", "N/A")}</b></p>
                <p>Basic Profit Estimate: {last.get("basic_profit_estimate", 0)}</p>
                <p>Premium Profit: {last.get("premium_profit", 0)}</p>
                <p><b>Net Profit: <span class="green">{last.get("net_profit", 0)}</span></b></p>
                <p>Transaction: 
                    <a href="https://base-sepolia-testnet-explorer.skalenodes.com:10032/tx/{last.get("tx_hash", "")}" target="_blank">
                        {last.get("tx_hash", "None")}
                    </a>
                </p>
            </div>

            <div class="card">
                <h3>📈 Total Net Profit</h3>
                <p class="green">{total_net_profit}</p>
            </div>

            <div class="card">
                <h3>📊 History</h3>
                <ul>
                    {"".join([
                        f"<li>Step {h.get('step', '?')} | {h.get('decision', 'N/A')} | Net: {h.get('net_profit', 0):.2f} | Budget: {h.get('remaining_budget', 0):.2f}</li>"
                        for h in history
                    ])}
                </ul>
            </div>

            <div class="card">
                <h3>🎯 Quick Demo (for judges)</h3>
                <button onclick="runDemo()">🚀 Run Demo (10 seconds)</button>
                <div id="result"></div>
            </div>

            <script>
            async function runDemo() {{
                const button = document.querySelector('button');
                button.disabled = true;
                button.textContent = "⏳ Sending...";
                
                try {{
                    const res = await fetch('/demo', {{ method: 'POST' }});
                    const data = await res.json();
                    
                    const resultDiv = document.getElementById('result');
                    if (data.status === 'success') {{
                        resultDiv.innerHTML = `
                            <p style="color: #00ff99;">${{data.message}}</p>
                            <p><b>Tx Hash:</b> ${{data.tx_hash}}</p>
                            <a href="${{data.explorer}}" target="_blank" style="display: inline-block; margin-top: 10px; padding: 10px; background: #00ccff; color: #111; border-radius: 4px;">
                                🔍 View on Explorer
                            </a>
                        `;
                    }} else {{
                        resultDiv.innerHTML = `<p style="color: #ff5555;">${{data.message}}</p>`;
                    }}
                }} catch (error) {{
                    document.getElementById('result').innerHTML = `<p style="color: #ff5555;">❌ Network error: ${{error.message}}</p>`;
                }} finally {{
                    button.disabled = false;
                    button.textContent = "🚀 Run Demo (10 seconds)";
                }}
            }}
            </script>
        </body>
    </html>
    """
    
    return html