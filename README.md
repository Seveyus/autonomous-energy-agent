# ⚡ AI Energy Capital Entity (SKALE x402) — Autonomous On-Chain Energy Allocator

An **autonomous economic agent** that:
- holds treasury,
- owns tokenized energy assets (solar capacity),
- buys **premium information** via **micropayments** (x402-style),
- survives crises with **risk + drawdown-aware policy**,
- and settles on-chain on **SKALE** — deployed on **Google Cloud Run**.

This is not “an energy optimizer script”.  
It behaves like a **mini energy hedge fund**, with **NAV / High-Water Mark / Drawdown**, **regimes**, and a **cinematic storyboard demo**.

---

## 🚀 What it demonstrates (Hackathon fit)

### AI Readiness
- Decision policy conditioned on **risk tolerance**, **market regime**, **drawdown**, and **info edge**.
- Rationales are surfaced to the UI (auditability).

### Commerce Realism
- **Pay-per-call** logic: the agent spends to buy premium forecasts when **EVPI** (Expected Value of Perfect Information) exceeds cost.
- **On-chain settlement**: premium purchase and capital deployment generate **SKALE transactions**.

### Sponsor Integrations
- **SKALE**: on-chain micropayments & settlement (tx links in dashboard).
- **Google Cloud**: production deployment on **Cloud Run** (containerized FastAPI).

---

## 🧠 Core Idea

**Information is a traded commodity.**  
The agent becomes an “information arbitrageur”: it purchases better signals only when the **marginal value** exceeds cost — otherwise it stays on free forecasts.

In crises, it switches to **capital preservation** (“Survival Mode”) based on drawdown thresholds.

---

## 🖥️ Dashboard

The dashboard acts like a control room:
- NAV / HWM / Drawdown
- Treasury (cash)
- Energy assets (capacity + efficiency)
- Market regime (NORMAL / STRESS / CRISIS)
- Info market panel: EVPI, cost, net edge, total info spend
- Cinematic demo: step-by-step logs (storyboard), then final NAV curve

---

## 📦 Repo Structure

- `main.py` — FastAPI app, endpoints, orchestration
- `agent.py` — crisis sampling, info edge signal (EVPI), investment policy + rationale
- `environment.py` — simulated market state
- `skale_payment.py` — Web3 payment helper (SKALE)
- `templates/dashboard.html` — UI
- `Dockerfile` — Cloud Run container
- `requirements.txt` — dependencies

---

## ✅ Run locally

```bash
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# (optional) set env vars locally
cp .env.example .env
# edit .env

uvicorn main:app --reload --host 0.0.0.0 --port 8000

Open:

🔌 Key Endpoints

GET /dashboard — UI

POST /epoch — run one allocation epoch (respects risk_tolerance)

POST /cinematic/run — run a multi-step scenario (warmup → premium → shock → recovery)

GET /cinematic/stream — SSE live logs for cinematic storyboard

POST /force_crisis/{type} — force next crisis (demo control)

POST /x402/pay — on-chain payment (SKALE)

☁️ Deploy to Google Cloud Run (Dockerfile)
gcloud run deploy autonomous-energy-agent \
  --source . \
  --region europe-west1 \
  --allow-unauthenticated


Set env vars in Cloud Run:

ENABLE_ONCHAIN=true

SKALE_RPC_URL=...

PRIVATE_KEY=... (use Secret Manager)

