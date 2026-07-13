# System Architecture & Design

AlphaStreams V2 is designed as an **Event-Driven Modular Monolith** enforcing strict separation of concerns, decoupling of domains, and clean process segregation inside the container.

---

## 1. System Process Layout

This diagram shows how processes are orchestrated inside the single Docker container, how they interact with external sources, and how data persists/streams across services:

```mermaid
graph TD
    subgraph External [External Market Sources]
        GrowwAPI([Groww API - Primary Quotes])
        NseAPI([NSE India API - Market Fallback])
    end

    subgraph DockerContainer [Docker Container - supervisord Process Manager]
        subgraph Ingestion [Ingestion Context]
            CeleryTasks[Celery Tasks - Ingestion Worker]
            AdapterFactory[Adapter Factory - Pluggable Outbound Ports]
            GrowwAdapter[GrowwApiAdapter - Outbound Client]
            NseAdapter[NseApiAdapter - Stateful Client / Session Cache]
        end

        subgraph OptionsPipeline [Options Analytics Pipeline]
            RawTicks["stream:options.raw_fetched"]
            OptionsSub[Options Pricing Sub - Core Subscriber Daemon]
            CNPricer[Crank-Nicolson PDE Numerical Solver]
            BSMPricer[Black-Scholes-Merton Analytical Engine]
            PricedTicks["stream:options.priced"]
        end

        subgraph Database [Historical Store]
            TimescaleDB[(TimescaleDB - PostgreSQL Hypertable)]
        end

        subgraph CachePubSub [Cache & Live Broadcast]
            RedisCache[(Redis Cache - Key-Value Store)]
            RedisPubSub[(Redis Pub/Sub - Ephemeral Broadcast)]
        end

        subgraph Serving [API & WebSocket Serving]
            FastAPI[FastAPI Web Server - uvicorn / REST API]
            WSHub[WebSocket Hub - ASGI Connection Link]
        end
    end

    subgraph UserClient [Client Browser]
        WebUI[Web UI Dashboard - HTML/CSS/JS]
    end

    %% Flow lines
    %% External to Ingestion adapters
    GrowwAPI -.->|HTTP POST/GET| GrowwAdapter
    NseAPI -.->|HTTP GET / Session Cookies| NseAdapter

    %% Ingestion internal calls
    CeleryTasks -->|Invoke via Port| AdapterFactory
    AdapterFactory --> GrowwAdapter
    AdapterFactory --> NseAdapter
    GrowwAdapter -.->|Fallback on fail| NseAdapter

    %% Process flow
    CeleryTasks ==|Publish raw ticks|==> RawTicks
    CeleryTasks -->|Save raw options ticks| TimescaleDB
    RawTicks ==|Consume raw ticks|==> OptionsSub
    OptionsSub -->|Evaluate PDE| CNPricer
    OptionsSub -->|Evaluate Greeks| BSMPricer
    
    %% Output and updates
    OptionsSub ==|Update cache read model|==> RedisCache
    OptionsSub ==|Publish priced ticks|==> PricedTicks
    OptionsSub ==|Broadcast updates|==> RedisPubSub

    %% Serving
    RedisCache <-->|Read cache| FastAPI
    RedisPubSub ==|Push updates|==> WSHub

    %% Client Consumption
    FastAPI <-->|REST API requests| WebUI
    WSHub ==|WebSockets live feed|==> WebUI

    %% Force vertical ranking to align like a tree
    External ~~~ Ingestion
    Ingestion ~~~ OptionsPipeline
    OptionsPipeline ~~~ Database
    Database ~~~ CachePubSub
    CachePubSub ~~~ Serving
    Serving ~~~ UserClient
```

---

## 2. Logical Architecture (DDD & Hexagonal Layers)

This diagram shows the software design pattern, mapping the **Domain-Driven Design (DDD)** bounded contexts and the **Hexagonal (Ports and Adapters) Architecture** layers:

```mermaid
graph TD
    subgraph PrimaryAdapters [Primary Adapters - Drivers]
        WebUI["Web UI Dashboard (HTML/CSS/JS)"]
        FastAPI_Router["FastAPI Router / API Endpoints"]
        WS_Events["WebSocket Router"]
        Celery_Beat["Celery Beat (Scheduler)"]
    end

    subgraph Ports [Domain Ports - Interfaces]
        IMarketPort["IMarketPriceSourcePort"]
        IOptionPort["IOptionChainSourcePort"]
        IEventBusPort["IEventBusPort"]
    end

    subgraph CoreDomain [Core Domains - Business Logic]
        subgraph Ingestion_Ctx [Ingestion Domain]
            IngestService["Ingestion Service"]
            DTOs["Data Transfer Objects"]
        end
        subgraph Analytics_Ctx [Analytics Domain]
            SentimentService["Sentiment Service"]
            CNPricer["Crank-Nicolson PDE Pricer"]
            BSMPricer["BSM Pricer Engine"]
            PredictorService["MTF-CNN-LSTM Predictor"]
            ReadModel["Read Model Updater"]
        end
    end

    subgraph SecondaryAdapters [Secondary Adapters - Driven]
        NseAdapter["NseApiAdapter"]
        GrowwAdapter["GrowwApiAdapter"]
        RedisBus["Redis Event Bus Adapter"]
        TimescaleDB["TimescaleDB Database Adapter"]
        RedisCache["Redis Cache / DB Read Model"]
    end

    %% Connectors
    WebUI <--> FastAPI_Router
    WebUI <--> WS_Events
    FastAPI_Router --> Ports
    Celery_Beat --> IngestService
    IngestService --> Ports

    Ports --> CoreDomain

    %% Interfaces implemented by adapters
    IMarketPort -.-> GrowwAdapter
    IMarketPort -.-> NseAdapter
    IOptionPort -.-> GrowwAdapter
    IOptionPort -.-> NseAdapter
    IEventBusPort -.-> RedisBus

    %% Core interactions with resources
    Analytics_Ctx --> TimescaleDB
    Analytics_Ctx --> RedisCache
    Analytics_Ctx --> RedisBus
```

---

## 3. Domain Component Architectures

### A. Ingestion Domain Context
Responsible for task scheduling, pulling market metrics from third-party endpoints using appropriate protocol-level adapters, caching static values (e.g. dividends) to reduce HTTP request volume, and staging raw records onto durable Redis Streams.

```mermaid
graph TD
    CeleryBeat[Celery Beat Scheduler] -->|Triggers periodic tasks| CeleryWorker[Celery Tasks Worker]
    
    subgraph Ingestion_Domain [Ingestion Bounded Context]
        CeleryWorker -->|Fetch Option Chain| AdapterFactory[Adapter Factory]
        AdapterFactory -->|Instantiate adapter| GrowwAdapter[GrowwApiAdapter]
        AdapterFactory -->|Instantiate adapter| NseAdapter[NseApiAdapter]
        GrowwAdapter -.->|Failover Fallback| NseAdapter
    end

    subgraph Infrastructure [Shared Infrastructure]
        RedisCache[(Redis Cache - Dividend Cache)]
        RawTicksStream["stream:options.raw_fetched"]
    end

    GrowwAdapter -->|Check / Populate Cache| RedisCache
    CeleryWorker ==|Publish raw option ticks|==> RawTicksStream
```

### B. Analytics Domain Context
Consumes raw streams asynchronously using subscriber daemons, routes data through numerical evaluation engines, persists results in TimescaleDB, and publishes priced records onto processed streams to update cache layers.

```mermaid
graph TD
    subgraph Streams [Redis Streams - Messaging Bus]
        RawTicks["stream:options.raw_fetched"]
        PricedTicks["stream:options.priced"]
    end

    subgraph Analytics_Domain [Analytics Bounded Context]
        OptionsSub[Options Pricing Sub]

        subgraph Core_Engines [Mathematical Engines]
            CNPricer[Crank-Nicolson PDE Solver]
            BSMPricer[Black-Scholes-Merton Engine]
        end
    end

    subgraph Storage [Databases & Broadcast]
        TimescaleDB[(TimescaleDB Hypertable)]
        RedisCache[(Redis Cache - Read Models)]
        RedisPubSub[(Redis Pub/Sub)]
    end

    %% Flow Option Pricing
    RawTicks ==|Consume raw ticks|==> OptionsSub
    OptionsSub -->|Evaluate PDE| CNPricer
    OptionsSub -->|Evaluate Greeks| BSMPricer
    OptionsSub -->|Save option ticks| TimescaleDB
    OptionsSub ==|Update cache read model|==> RedisCache
    OptionsSub ==|Publish priced options|==> PricedTicks
    OptionsSub ==|Broadcast updates|==> RedisPubSub
```

### C. App / Serving Domain Context
Handles incoming client requests, serving REST endpoints by reading from cache and pushing updates in real-time to active user dashboards using WebSockets.

```mermaid
graph TD
    subgraph Storage [Infrastructure Layer]
        RedisCache[(Redis Cache - Read Models)]
        RedisPubSub[(Redis Pub/Sub - Live Feed)]
    end

    subgraph App_Domain [App/Serving Bounded Context]
        FastAPI[FastAPI Web Server]
        WSHub[WebSocket Hub]
    end

    subgraph Client [Client UI]
        WebUI[Option Chain Dashboard]
    end

    %% Reads & Queries
    FastAPI -->|Query Cache| RedisCache
    WSHub -->|Subscribe to updates| RedisPubSub

    %% Serving clients
    WebUI <-->|REST API requests / BSM Calculations| FastAPI
    WebUI <-->|WebSockets Live Feed| WSHub
```

---

## 4. Durable-First Event Model

Cross-domain correctness uses **Redis Streams** (durable, replayable, consumer-group semantics). Pub/Sub is used only for UX/live push.

### Durable streams (state/correctness path)

| Stream | Producer domain | Consumer domain | Notes |
|---|---|---|---|
*   `stream:market.price_trigger` | Ingestion | Analytics | Triggered market anomalies.
*   `stream:options.raw_fetched` | Ingestion | Analytics | Raw option chain ticks for PDE solver.
*   `stream:options.priced` | Analytics | App | Fair-priced option chain output.
*   `stream:analysis.completed` | Analytics | App | Analysis completion signal.
*   `stream:analysis.refresh_requested` | App | Ingestion | Async refresh command path.

### Dead-letter queues (DLQ)

| Stream | Purpose |
|---|---|
*   `stream:dlq:refresh_request` | Failed refresh request events.

### Ephemeral Pub/Sub mirrors (UX-only)

| Channel pattern | Purpose |
|---|---|
*   `market.price_updated.{symbol}` | Live price updates.
*   `market.options_updated.{symbol}` | Live options summary updates.
*   `market.price_trigger.{symbol}` | Live trigger notifications.
*   `alerts.dispatched.{symbol}` | Live alert dispatch notifications.
