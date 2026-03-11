import asyncio
from ai_event_radar import run_risk_radar
result = asyncio.run(run_risk_radar("CRDO", "CREDO"))
import json
print(json.dumps(result, indent=2))
