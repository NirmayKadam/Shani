# ADR-001: Bounded Contexts

- **Status:** Accepted
- **Date:** 2026-04-14
- **Decision Makers:** Architecture group

## Context

The current code and data flow blend ingestion logic, NLP processing, and API concerns. This creates coupling, makes ownership unclear, and complicates independent scaling.

## Decision

We define three bounded contexts with explicit responsibilities:

1. **`ingestion`**
   - Collects market/news inputs (Indian Market primary).
   - Handles dynamic symbol retrieval and normalization.
   - Emits canonical ingestion events.

2. **`analytics`**
   - Consumes ingestion events.
   - Performs enrichment, FinBERT sentiment scoring.
   - Produces aggregates and updates read models.

3. **`app`**
   - Serves API and WebSockets via FastAPI.
   - Orchestrates async refresh flows.

## Interface Rules

- Inter-context communication occurs only through versioned contracts.
- Shared utilities are allowed only for non-domain concerns (logging, tracing, config loading).
- Domain models are not imported across contexts; integration uses explicit DTO/event schemas.

## Consequences

- **Positive:** clearer ownership, safer refactoring, independent deployment/scaling paths.
- **Trade-off:** additional contract/version management overhead.
- **Risk:** temporary duplication while extracting mixed modules.
