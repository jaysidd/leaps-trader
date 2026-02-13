Opus 4.5 (claude-opus-4-5-20251101) — used for complex tasks:

Copilot interactive chat (copilot.py:450)
Copilot stock detail analysis (copilot.py:534)
Deep stock analysis (claude_service.py:551)
Strategy recommendation (claude_service.py:718)
Haiku 3.5 (claude-haiku-3-5-20241022) — used for quick tasks:

Quick scan, score explanations, failure explanations, metric tooltips
Sonnet 4 (claude-sonnet-4-20250514) — used for mid-tier tasks:

Morning briefs, batch analysis, market regime
Cost tracking is now model-aware — Opus 4.5 calls are tracked at $15/$75 per 1M tokens (5x Sonnet), so your $10/day budget will be consumed faster on complex analysis. You may want to increase CLAUDE_DAILY_BUDGET in your .env if you use the copilot chat frequently.