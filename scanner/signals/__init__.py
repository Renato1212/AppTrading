"""Real-time attention & market-reaction signal adapters.

Each adapter is best-effort: if a source is rate-limited or down, it returns
empty/neutral data instead of raising, so one failing signal never breaks a scan.
"""
