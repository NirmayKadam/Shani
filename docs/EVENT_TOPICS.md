# Event Topics Catalog

Canonical topic inventory for cross-domain events, including transport durability and payload contracts.

## Durable stream topics (Redis Streams)

| Topic name | Producer | Consumer | Payload schema | Durability level |
|---|---|---|---|---|
| `stream:headlines.fetched` | `app.domain.ingestion.application.tasks` | `app.domain.nlp_logic.infrastructure.event_subscriber` (consumer group: `cg:ingestion_to_nlp`) | `HeadlineFetchedV1` (`HeadlineFetchedEvent` alias) | **Durable stream** |
| `stream:market.price_trigger` | `app.domain.ingestion.application.tasks` | `app.domain.nlp_logic.infrastructure.event_subscriber` (consumer group: `cg:ingestion_to_nlp`) | `PriceTriggerV1` (`PriceTriggerEvent` alias) | **Durable stream** |
| `stream:sentiment.scored` | `app.domain.nlp_logic.infrastructure.event_subscriber` | Downstream durable consumers (none currently implemented in-repo) | `SentimentScoredV1` (`SentimentScoredEvent` alias) | **Durable stream** |
| `stream:sentiment.aggregate_updated` | `app.domain.nlp_logic.infrastructure.event_subscriber` | Downstream durable consumers (none currently implemented in-repo) | `AggregateUpdatedV1` (`AggregateUpdatedEvent` alias) | **Durable stream** |
| `stream:dlq:ingestion_to_nlp` | `DurableEventStream.retry_or_dead_letter` | Operators / replay tooling | DLQ envelope (`original_stream`, `original_message_id`, `retry_count`, `error`, `payload`) | **Durable stream** |
| `stream:dlq:nlp_to_api` | Reserved | Operators / replay tooling | DLQ envelope (`original_stream`, `original_message_id`, `retry_count`, `error`, `payload`) | **Durable stream** |

## Ephemeral pub/sub topics (Redis Pub/Sub)

| Topic name | Producer | Consumer | Payload schema | Durability level |
|---|---|---|---|---|
| `headlines.fetched.{symbol}` | `app.domain.ingestion.application.tasks` | Frontend websocket router (`app.domain.frontend_api.interfaces.routers.websocket`) | `HeadlineFetchedV1` (`HeadlineFetchedEvent` alias) | **Ephemeral pubsub** |
| `market.price_updated.{symbol}` | `app.domain.ingestion.application.tasks` | Frontend websocket router | `PriceUpdatedV1` (`PriceUpdatedEvent` alias) | **Ephemeral pubsub** |
| `market.options_updated.{symbol}` | `app.domain.ingestion.application.tasks` | Frontend websocket router | `OptionsUpdatedV1` (`OptionsUpdatedEvent` alias) | **Ephemeral pubsub** |
| `market.price_trigger.{symbol}` | `app.domain.ingestion.application.tasks` | Frontend websocket router; NLP subscriber (legacy real-time hook) | `PriceTriggerV1` (`PriceTriggerEvent` alias) | **Ephemeral pubsub** |
| `sentiment.scored.{symbol}` | `app.domain.nlp_logic.infrastructure.event_subscriber` | Frontend websocket router | `SentimentScoredV1` (`SentimentScoredEvent` alias) | **Ephemeral pubsub** |
| `sentiment.aggregate_updated.{symbol}` | `app.domain.nlp_logic.infrastructure.event_subscriber` | Frontend websocket router | `AggregateUpdatedV1` (`AggregateUpdatedEvent` alias) | **Ephemeral pubsub** |

## Payload versioning policy

All domain payload contracts include:

- `event_type`: canonical event discriminator.
- `schema_version`: currently `"v1"`.

Current concrete versions are defined in `app/shared/event_bus/contracts.py` as:

- `HeadlineFetchedV1`
- `PriceUpdatedV1`
- `OptionsUpdatedV1`
- `PriceTriggerV1`
- `SentimentScoredV1`
- `AggregateUpdatedV1`
