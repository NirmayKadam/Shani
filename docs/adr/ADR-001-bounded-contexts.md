# ADR-001: Bounded Contexts

- **Status:** Accepted
- **Date:** 2026-04-14
- **Decision Makers:** Architecture group

## Context

The current code and data flow blend ingestion logic, NLP processing, and API concerns. This creates coupling, makes ownership unclear, and complicates independent scaling.

## Decision

We define three bounded contexts with explicit responsibilities:

1. **`ingestion`**
   - Collects and normalizes external market/news/social inputs.
   - Handles connector reliability, deduplication, and basic schema validation.
   - Emits canonical ingestion events only.

2. **`nlp_logic`**
   - Consumes canonical ingestion events.
   - Performs enrichment, sentiment scoring, and feature extraction.
   - Produces model outputs and derived analytics events.

3. **`frontend_api`**
   - Serves UI and external consumers.
   - Aggregates read models and exposes query/command endpoints.
   - Must not run heavy NLP computations inline.

## Interface Rules

- Inter-context communication occurs only through versioned contracts.
- Shared utilities are allowed only for non-domain concerns (logging, tracing, config loading).
- Domain models are not imported across contexts; integration uses explicit DTO/event schemas.

## Consequences

- **Positive:** clearer ownership, safer refactoring, independent deployment/scaling paths.
- **Trade-off:** additional contract/version management overhead.
- **Risk:** temporary duplication while extracting mixed modules.
