# Autonomous Energy Capital Agent

An agent that allocates capital in a simulated energy market and treats
**information as something it has to pay for**. Before each decision it computes
the expected value of a premium forecast and buys one only when that value
exceeds its price; otherwise it acts on the free, noisier signal.

```
if EVPI(premium_signal) > cost
   and cash buffer is safe
   and not in survival mode
→ buy the premium signal, allocate on the better forecast
else
→ allocate on the free signal
```

The policy is conditioned on risk tolerance, market regime, current drawdown and
that information edge, and every decision emits a human-readable rationale
rather than a bare action, so the reasoning can be audited after the fact.

## What it does

- **Simulated market** (`environment.py`) — solar production, prices, and
  injected crisis events such as a grid failure.
- **Decision policy** (`agent.py`) — crisis detection, EVPI calculation, a
  drawdown-aware survival mode, and a cash buffer that must survive the
  allocation before capital is deployed.
- **Settlement** (`skale_payment.py`) — micropayments and on-chain settlement of
  capital deployments. Fully optional: set `ENABLE_ONCHAIN=false` and the agent
  runs as a pure simulation.
- **Dashboard** (`templates/dashboard.html`) — NAV curve, asset state, and the
  information market, streamed over SSE.

## Running it

```bash
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env          # ENABLE_ONCHAIN=false for simulation only
uvicorn main:app --port 8000
```

| Endpoint | Purpose |
|---|---|
| `GET /dashboard` | NAV curve, assets, information market |
| `POST /epoch` | Run one allocation epoch |
| `POST /cinematic/run` | Scripted run: warmup → premium purchase → shock → recovery |
| `GET /cinematic/stream` | SSE stream of that run |

## Status and limits

**Archived.** This was a two-day prototype and is kept for the idea rather than
the implementation.

- The market is synthetic. No real price feed, no backtest against historical
  data, and no claim that the policy would hold on real prices.
- 713 lines and a single test. The EVPI calculation is the interesting part; the
  surrounding machinery is not hardened.
- The on-chain path is a demonstration of settlement mechanics, not a
  production integration.
- There is no hosted deployment.

The idea it was built to test — that an agent should decide when information is
worth paying for, rather than consuming whatever forecast it is handed — is the
earliest version of a line of work continued in later projects.

## Licence

MIT.
