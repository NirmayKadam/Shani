# Event Topics Catalog

Canonical topic inventory for cross-domain events.

## Durable stream topics (Redis Streams)

| Topic name | Producer | Consumer | Payload schema |
| --- | --- | --- | --- |
| `stream:headlines.fetched` | `domains.ingestion.application.tasks` | `domains.analytics.infrastructure.event_subscriber` | `HeadlineFetchedV1` |
| `stream:market.price_updated` | `domains.ingestion.application.tasks` | `domains.analytics.infrastructure.event_subscriber` | `PriceUpdatedV1` |
| `stream:market.options_updated` | `domains.ingestion.application.tasks` | `domains.analytics.infrastructure.event_subscriber` | `OptionsUpdatedV1` |
| `stream:market.price_trigger` | `domains.ingestion.application.tasks` | `domains.analytics.infrastructure.event_subscriber` | `PriceTriggerV1` |
| `stream:sentiment.scored` | `domains.analytics.infrastructure.event_subscriber` | - | `SentimentScoredV1` |
| `stream:sentiment.aggregate_updated` | `domains.analytics.infrastructure.event_subscriber` | `domains.analytics.infrastructure.read_model_updater` | `AggregateUpdatedV1` |
| `stream:analysis.refresh_requested` | `domains.analytics.api` | `domains.ingestion.application.tasks` | `AnalysisRefreshRequestedV1` |
| `stream:dlq:ingestion_to_analytics` | `DurableEventStream` | Operators | DLQ envelope |

## Ephemeral pub/sub topics (Redis Pub/Sub)

| Topic name | Producer | Consumer | Payload schema |
| --- | --- | --- | --- |
| `headlines.fetched.{symbol}` | `domains.ingestion.application.tasks` | `domains.analytics.api.events_router` | `HeadlineFetchedV1` |
| `market.price_updated.{symbol}` | `domains.ingestion.application.tasks` | `domains.analytics.api.events_router` | `PriceUpdatedV1` |
| `market.options_updated.{symbol}` | `domains.ingestion.application.tasks` | `domains.analytics.api.events_router` | `OptionsUpdatedV1` |
| `market.price_trigger.{symbol}` | `domains.ingestion.application.tasks` | `domains.analytics.api.events_router` | `PriceTriggerV1` |
| `sentiment.scored.{symbol}` | `domains.analytics.infrastructure.event_subscriber` | `domains.analytics.api.events_router` | `SentimentScoredV1` |
| `sentiment.aggregate_updated.{symbol}` | `domains.analytics.infrastructure.event_subscriber` | `domains.analytics.api.events_router` | `AggregateUpdatedV1` |
