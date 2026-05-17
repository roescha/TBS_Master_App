# TBS Master App

Algorithmic trading system. Backend in `layers/` (active development).

- `layers/tbs_engine/` — purity engine package (modularised per RFT-004)
- `layers/tbs_orchestrator.py`, `layers/tbs_scanner.py` — orchestration + scanning
- `layers/ai_*.py`, `layers/ibkr_*.py`, `layers/yahoo_fundamentals.py`, `layers/finnhub_context.py` — data layer + AI context modules
- `tbs-frontend/` — deferred web UI (resumes after PEO Tier 1–3 completion)
- `docs/` — supporting reference data + per-spec artifacts (closed specs / handbacks / post-mortems)

Canonical living documents (Docs 1–9, PEO, EEM, Bug Register, SIR, Amendment Control Process) are maintained outside this repo as governance source-of-truth.