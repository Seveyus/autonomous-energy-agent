from fastapi import FastAPI
from environment import get_environment_state
from agent import decide_action

app = FastAPI()

agent_budget = 1.0  # € initial

@app.get("/run")
def run_agent():
    global agent_budget

    state = get_environment_state()
    decision = decide_action(state, agent_budget)

    if decision == "buy_premium_data":
        agent_budget -= 0.05

    return {
        "environment": state,
        "decision": decision,
        "remaining_budget": agent_budget
    }
