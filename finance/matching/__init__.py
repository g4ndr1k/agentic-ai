"""finance.matching — generic matching engine public API.

Entry points:
  classify(domain, conn, source_row, **ctx) → Match | None
  suggest(domain, conn, unmapped, **ctx)    → list[dict]
  record_event(domain, conn, mapping_id, event) → None
  reset_run_state()

Each consumer domain is a thin adapter in finance.matching.domains.<name>.
"""
from finance.matching.engine import classify, reset_run_state, Match, TraceTree  # noqa: F401
from finance.matching.confidence import apply as record_event, Event  # noqa: F401
from finance.matching.suggest import Suggestion  # noqa: F401
