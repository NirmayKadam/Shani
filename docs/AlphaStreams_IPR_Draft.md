# AlphaStreams V2 — Intellectual Property Rights (IPR) Draft
## Copyright Registration & IP Protection Package

**Project Title:** AlphaStreams — Real-Time Quantitative Analytics & Option Pricing Engine  
**Internal Project Name (Codebase):** AlphaStreams V2 / Shani  
**Project Domain:** Quantitative Finance, Options Pricing, Algorithmic Trading Analytics  
**Authors (Shani Quant Research Team):**  
1. Hirdhay Jadhwani  
2. Siddharth Jogi  
3. Sumanyu Joshi  
4. Nirmay Kadam  

**Version:** 1.0  
**Date of Preparation:** 20 August 2026  

> [!CAUTION]
> **This document is a preparatory internal draft and does not constitute legal advice.** The Indian Copyright Office's official portal instructions, the Copyright Act 1957 (as amended), Copyright Rules 2013, and the authors' institutional IPR policy always control over the contents of this document. Consult qualified legal counsel before formal filing.

---

## Table of Contents

1. [Executive Summary](#1-executive-summary)
2. [IP Type Map — Applicable Rights](#2-ip-type-map--applicable-rights)
3. [Identification of Copyrightable Works](#3-identification-of-copyrightable-works)
4. [Work 1 — Computer Software (PDE Pricing Engine & Platform Codebase)](#4-work-1--computer-software-pde-pricing-engine--platform-codebase)
5. [Work 2 — Literary Work (Research Paper)](#5-work-2--literary-work-research-paper)
6. [Work 3 — Artistic Work (System Architecture Block Diagram)](#6-work-3--artistic-work-system-architecture-block-diagram)
7. [Authorship vs Ownership Analysis](#7-authorship-vs-ownership-analysis)
8. [Third-Party & Open-Source Register](#8-third-party--open-source-register)
9. [Patent Timing & Trade Secret Assessment](#9-patent-timing--trade-secret-assessment)
10. [Filing Workflow & Checklist](#10-filing-workflow--checklist)
11. [Recommended IPR Folder Structure](#11-recommended-ipr-folder-structure)
12. [Official References](#12-official-references)

---

## 1. Executive Summary

AlphaStreams V2 is an event-driven quantitative options analytics platform built for the Indian financial markets (NSE/BSE). The project comprises **three distinct, separately registrable copyrightable works**:

| # | Work | Copyright Class | Registration Status |
|---|------|----------------|-------------------|
| 1 | Platform source code (PDE pricing engine, backtesting framework, full-stack application) | **Computer Software** | To be filed |
| 2 | Research paper: *"Alpha Generation in Indian Index Derivatives: An Empirical Comparison of Crank-Nicolson PDE Solvers versus Retail Technical Indicators"* | **Literary Work** | To be filed |
| 3 | Original system architecture / block diagram(s) | **Artistic Work** | To be filed |

> [!IMPORTANT]
> **One application = one work.** The source code, the research paper, and the block diagram(s) each require **separate** copyright applications. They cannot be bundled into a single filing.

### What Copyright Protects — and What It Does Not

Copyright protects the **original expression** in each work — the specific source code text, the written prose and mathematical exposition in the paper, and the original visual arrangement of the diagram. Copyright does **not** protect:

- The underlying mathematical algorithms (e.g., Black-Scholes-Merton equations, Crank-Nicolson finite difference scheme, RSI/MACD indicator formulas)
- The abstract idea of using PDE solvers for options mispricing detection
- Trading strategy concepts or investment methodologies
- Standard technical indicator formulations (RSI, MACD, Bollinger Bands, ATR, Pivot Points)

---

## 2. IP Type Map — Applicable Rights

| IP Right | What It Protects | AlphaStreams Project Example | Action Required |
|----------|-----------------|----------------------------|----------------|
| **Copyright** | Original expression | Source code text, research paper, original diagrams, frontend UI artwork | Prepare works + file applications per §4, §5, §6 |
| **Patent** | Novel technical invention | Potentially: the specific combination of cubic-spline volatility surface calibration + $O(M)$ SuperLU pre-factorized CN-PDE + dynamic Indian statutory friction model as a unified system | Assess patentability **before** public disclosure (paper publication, arXiv preprint, conference presentation, public repo) |
| **Trademark** | Brand identifier | "AlphaStreams", "Shani", project logo | Conduct TM search; evaluate registration separately |
| **Trade Secret** | Confidential valuable information | Calibrated strategy parameters, proprietary epsilon buffer multipliers ($\kappa = 1.5$), optimal near-ATM strike window (150-point radius), 2-bar minimum hold logic, internal execution safeguard thresholds | Maintain confidentiality controls, restrict access |
| **Design** | Visual product appearance | Glassmorphic dark-theme dashboard UI (possible, but low priority for software) | Evaluate if UI is sufficiently distinctive |

---

## 3. Identification of Copyrightable Works

### 3.1 Original Contributions (Copyrightable Expression)

The following elements represent **original expression** authored by the team:

#### Source Code — Computer Software
1. **Crank-Nicolson PDE Numerical Solver** (`domains/analytics/domain/services/pde_solver.py`) — Original Python implementation of the 1D Black-Scholes PDE solver with CFL stability guards, SuperLU pre-factorization via `scipy.sparse.linalg.splu`, and adaptive grid refinement.
2. **BSM Analytical Calculator Domain Service** (`domains/analytics/domain/services/bsm_calculator.py`) — Original implementation of closed-form BSM pricing with continuous dividend yield and all five Greeks ($\Delta, \Gamma, \nu, \Theta, \rho$).
3. **Cubic Spline Volatility Surface Calibrator** (`domains/analytics/domain/services/volatility_surface.py`) — Original code resolving the volatility circularity problem via natural cubic spline cross-sectional interpolation.
4. **Indian Statutory Friction Model** (`research/models/friction_model.py`) — Original `IndianOptionsFrictionModel` class with `FrictionEstimate` dataclass, full round-trip cost decomposition (STT, exchange fees, stamp duty, SEBI fees, GST, brokerage, bid-ask spread), and dynamic epsilon threshold computation.
5. **Backtesting Engine & Strategy Implementations** (`research/backtest/engine.py`, `research/backtest/strategies.py`) — Original `BacktestEngine`, `RetailBaselineStrategy`, `PDEMispricingStrategy`, and `HybridFilterStrategy` implementations with position sizing, equity tracking, and exit logic.
6. **Event-Driven Domain Architecture** — Original modular monolith architecture code with DDD bounded contexts (Ingestion, Analytics, Notifications, Historical), Hexagonal Ports & Adapters pattern, Redis Streams/Pub/Sub event bus, and multi-channel notification dispatch.
7. **Market Data Adapter Factory & NSE/Groww Adapters** — Original adapter implementations including NSE session cookie rotation, Groww OAuth handling, and tiered fallback chain with fail-fast 503 policy.
8. **Technical Indicators Engine** — Original vectorized implementations of RSI, MACD, EMA, Bollinger Bands, ATR, and Classic Floor Pivot calculations.
9. **Frontend Dashboard** — Original glassmorphic dark-theme trading terminal UI (HTML5/CSS3/Vanilla JS) including client-side BSM simulator with Hastings' CDF polynomial approximation.
10. **Data Collection & Experiment Orchestration** (`research/data/collect_historical.py`, `research/run_experiment.py`) — Original data pipeline, experiment runner, and statistical analysis framework.

#### Research Paper — Literary Work
11. **IEEE LaTeX Manuscript** (`research/paper/main.tex`) — Original written exposition including mathematical formulation, experimental design, empirical results, VIX regime analysis, walk-forward validation, and conclusions.

#### Diagrams — Artistic Work
12. **System Architecture Diagrams** — Any original block diagrams, Mermaid flow charts, or sequence diagrams depicting the AlphaStreams pipeline (data ingestion → volatility surface calibration → PDE solver → friction model → strategy signal output → notification dispatch).

### 3.2 Non-Copyrightable Elements (Ideas, Algorithms, Methods)

The following are **ideas, mathematical formulas, or well-known algorithms** and are NOT protectable by copyright:

| Element | Classification | Reason |
|---------|---------------|--------|
| Black-Scholes-Merton equations ($d_1$, $d_2$, call/put formulas) | Published mathematical formula | Black & Scholes (1973), Merton (1973) |
| Crank-Nicolson finite difference scheme | Published numerical method | Crank & Nicolson (1947); Duffy (2006) |
| SuperLU sparse LU decomposition algorithm | Published numerical linear algebra | Li (2005); distributed via SciPy |
| RSI, MACD, Bollinger Bands, ATR indicator formulas | Well-known technical analysis heuristics | Wilder (1978), Appel (1979), Bollinger (2001) |
| Natural cubic spline interpolation | Standard numerical analysis method | de Boor (1978) |
| The concept of "using PDE pricing to detect option mispricings" | Abstract idea / trading methodology | Not copyrightable |
| India VIX regime classification thresholds | Data-driven categorization | Descriptive, not expressive |

---

## 4. Work 1 — Computer Software (PDE Pricing Engine & Platform Codebase)

### 4.1 Work Identification

```
TITLE:              AlphaStreams — Real-Time Quantitative Analytics & Option Pricing Engine
VERSION/DATE:       v2.0 / August 2026
CLASS:              Computer Software / Computer Programme
APPLICANT/OWNER:    [To be confirmed — see §7 Authorship vs Ownership]
AUTHORS:            Hirdhay Jadhwani, Siddharth Jogi, Sumanyu Joshi, Nirmay Kadam
LANGUAGE(S):        Python 3.11+, JavaScript (ES6+), HTML5, CSS3, SQL, LaTeX
PROJECT ID:         [Institutional project ID — to be filled]
```

### 4.2 Source Code PDF Preparation

Per current Copyright Office portal instructions:

- **If total source code exceeds 20 printed pages:** Submit PDF containing the **first 10 pages + last 10 pages** of the source code.
- **If total source code is fewer than 20 printed pages:** Submit the **entire source code**.

> [!WARNING]
> **Pre-submission sanitization is mandatory.** Before generating the source code PDF:
> - **Remove all API keys, tokens, passwords, private keys, TOTP secrets** from every file.
> - Remove the `.env` file contents entirely — do not include any configuration secrets.
> - Remove Groww JWT tokens, Supabase keys, and database credentials.
> - The submitted PDF must **not** be password-protected.
> - **No blacked-out or redacted portions** are permitted where the portal prohibits redaction.

#### Recommended Source Code Selection for 10+10 PDF

**First 10 pages** (core mathematical domain — highest originality):

| Priority | File | Content | Rationale |
|----------|------|---------|-----------|
| 1 | `domains/analytics/domain/services/pde_solver.py` | Crank-Nicolson PDE implementation with SuperLU factorization | Core novel implementation |
| 2 | `domains/analytics/domain/services/bsm_calculator.py` | BSM analytical pricing + Greeks | Core mathematical engine |
| 3 | `domains/analytics/domain/services/volatility_surface.py` | Cubic spline volatility surface calibration | Novel circularity resolution |
| 4 | `research/models/friction_model.py` | Indian statutory friction model | Original domain model |
| 5 | `research/backtest/strategies.py` | PDE and Hybrid strategy implementations | Original strategy expression |

**Last 10 pages** (infrastructure & platform — demonstrates system completeness):

| Priority | File | Content | Rationale |
|----------|------|---------|-----------|
| 1 | `domains/ingestion/infrastructure/outbound/nse_api_adapter.py` | NSE session management + cookie rotation | Original adapter logic |
| 2 | `domains/notifications/domain/services/rule_matcher.py` | Alert condition evaluation engine | Original domain service |
| 3 | `domains/analytics/infrastructure/options_subscriber.py` | Redis Stream consumer daemon | Original event pipeline |
| 4 | `shared/infrastructure/event_bus/redis_event_bus.py` | Redis Streams/Pub/Sub event bus | Original infrastructure |
| 5 | `frontend/app.js` (last pages) | Client-side BSM simulator with Hastings CDF | Original frontend math |

### 4.3 Software Copyright Filing Pack

| # | File | Purpose | Suggested Filename |
|---|------|---------|-------------------|
| 1 | Project identity cover page | Title, version, applicant, authors, project ID | `01_AlphaStreams_ProjectIdentity.pdf` |
| 2 | Source code PDF | First 10 + last 10 pages (or full if <20pp) | `02_AlphaStreams_SourceCode.pdf` |
| 3 | Object code (if requested) | Compiled/bytecode artifacts | `03_AlphaStreams_ObjectCode.pdf` |
| 4 | Author contribution statement | Individual contribution breakdown + signatures | `04_AlphaStreams_AuthorContribution.pdf` |
| 5 | Ownership NOC/Assignment | If author ≠ applicant/owner per institutional policy | `05_AlphaStreams_Ownership_NOC.pdf` |
| 6 | Third-party register | Open-source/dataset/API licence audit | `06_AlphaStreams_ThirdParty_Register.pdf` |
| 7 | Development record | Git history, milestones, commit timeline | `07_AlphaStreams_DevelopmentRecord.pdf` |
| 8 | Dependency notices | `requirements.txt` + licence attributions | `08_AlphaStreams_DependencyNotices.pdf` |

---

## 5. Work 2 — Literary Work (Research Paper)

### 5.1 Work Identification

```
TITLE:              Alpha Generation in Indian Index Derivatives: An Empirical
                    Comparison of Crank-Nicolson PDE Solvers versus Retail
                    Technical Indicators
VERSION/DATE:       v1.0 / August 2026
CLASS:              Literary Work
APPLICANT/OWNER:    [To be confirmed — see §7]
AUTHORS:            Hirdhay Jadhwani, Siddharth Jogi, Sumanyu Joshi, Nirmay Kadam
LANGUAGE:           English
TARGET VENUE:       IEEE Conference on Computational Intelligence for Financial
                    Engineering (CIFEr) / Journal of Computational Finance
```

### 5.2 Publication Status

| Question | Answer |
|----------|--------|
| Is the paper published? | **Assess at time of filing.** If submitted to arXiv/SSRN preprint server, this constitutes publication. If only circulated internally, mark as "Unpublished." |
| Date of first publication | Record exact date of first public availability (arXiv upload date, conference proceedings date, or journal publication date) |
| Country of first publication | India (if preprint uploaded from India) or as applicable |

### 5.3 Paper Copyright Filing Pack

| # | File | Purpose | Suggested Filename |
|---|------|---------|-------------------|
| 1 | Complete paper PDF | The literary work itself (compiled LaTeX → PDF) | `01_AlphaStreams_ResearchPaper.pdf` |
| 2 | Author contribution statement | Per-author contribution + signatures | `02_AlphaStreams_Paper_AuthorContribution.pdf` |
| 3 | Ownership NOC/Assignment | If required by institutional/conference policy | `03_AlphaStreams_Paper_Ownership_NOC.pdf` |
| 4 | Third-party register | Citations, referenced datasets, figure sources | `04_AlphaStreams_Paper_ThirdParty.pdf` |

> [!WARNING]
> **IEEE Copyright Transfer:** If the paper is accepted at an IEEE venue, IEEE typically requires a copyright transfer agreement. This may affect who holds copyright. Verify the IEEE publication agreement terms before filing a separate copyright registration to avoid conflicting ownership claims.

---

## 6. Work 3 — Artistic Work (System Architecture Block Diagram)

### 6.1 Work Identification

```
TITLE OF ARTISTIC WORK:     [Exact title of the original diagram, e.g.,
                             "System Architecture Block Diagram of AlphaStreams
                             Quantitative Options Analytics Platform"]
PROJECT TITLE:               AlphaStreams — Real-Time Quantitative Analytics &
                             Option Pricing Engine
CLASS OF WORK:               Artistic Work
TYPE:                        Original Block Diagram / System Architecture Diagram
AUTHOR(S):                   [Subset of team who actually created the diagram]
APPLICANT/OWNER:             [To be confirmed — see §7]
STATUS:                      Unpublished / Published [assess at filing time]
SOFTWARE/PROJECT CONTEXT:    Event-driven quantitative options pricing platform
                             for Indian NSE/BSE derivatives markets
```

### 6.2 Diagram Content Guidance

The diagram should depict the AlphaStreams data pipeline as an **original visual composition**:

```
Market Data Input (NSE/Groww APIs)
    → Ingestion Context (Session Management, Cookie Rotation, Adapter Factory)
        → Redis Streams (Durable Append-Only Log)
            → Analytics Context (Volatility Surface Calibration via Cubic Spline)
                → PDE Solver (Crank-Nicolson + SuperLU Factorization)
                    → BSM Greeks Engine (Δ, Γ, ν, Θ, ρ)
                        → Friction/Mispricing Engine (Dynamic ε Threshold)
                            → Strategy Signal Output / Notification Dispatch
                                → WebSocket Gateway → Client Dashboard
```

> [!IMPORTANT]
> **Originality Requirement:** The diagram must be an **original visual arrangement** created by the team — not a screenshot from a third-party tool's auto-generated output, not a copy from a textbook, and not a verbatim reproduction of a template. Standard symbols (boxes, arrows, connectors) are fine; the originality lies in the specific visual composition and arrangement depicting this system.

### 6.3 Diagram Preparation Checklist

- [ ] Exact project title displayed on the diagram
- [ ] Figure title (e.g., "Block Diagram of AlphaStreams Quantitative Options Analytics Platform")
- [ ] Clear, original boxes/arrows/labels/annotations
- [ ] Consistent typography and spacing
- [ ] Student/institution ID if required by policy
- [ ] Version and date on internal master copy
- [ ] No third-party watermarks or copyrighted templates
- [ ] **No passwords, API keys, or credentials** visible in diagram
- [ ] If the diagram is also used as a logo or brand asset, assess trademark implications separately

### 6.4 Diagram Filing Pack

| # | File | Purpose | Suggested Filename |
|---|------|---------|-------------------|
| 1 | Final block diagram (PDF/JPG) | The artistic work itself | `01_AlphaStreams_BlockDiagram.pdf` |
| 2 | High-res editable source | Internal evidence, master copy | `02_AlphaStreams_BlockDiagram_Source.svg` |
| 3 | Originality/ownership declaration | Supporting evidence | `03_AlphaStreams_BlockDiagram_Declaration.pdf` |
| 4 | Third-party material register | Rights audit for any imported icons/templates | `04_AlphaStreams_BlockDiagram_ThirdParty.pdf` |
| 5 | NOC/Assignment | Where ownership policy requires | `05_AlphaStreams_BlockDiagram_NOC.pdf` |

---

## 7. Authorship vs Ownership Analysis

> [!IMPORTANT]
> **This section must be resolved before filing any application.** The "Applicant / Copyright Owner" field on Form XIV has legal consequences. Verify institutional policy and any project agreements.

### 7.1 Author Identification

| Author | Likely Contribution Areas |
|--------|--------------------------|
| **Hirdhay Jadhwani** | [To be documented — e.g., PDE solver, backtesting engine] |
| **Siddharth Jogi** | [To be documented — e.g., ingestion adapters, notification domain] |
| **Sumanyu Joshi** | [To be documented — e.g., frontend dashboard, technical indicators] |
| **Nirmay Kadam** | [To be documented — e.g., architecture design, research paper, deployment] |

### 7.2 Ownership Scenarios

| Scenario | Ownership | Required Documentation |
|----------|-----------|----------------------|
| **Students own IP** (no institutional claim) | Authors are also owners; any author can be Applicant | Author contribution statement with signatures |
| **Institution claims ownership** | Institution is Applicant/Owner; students are Authors | NOC from institution, assignment deed if applicable, institutional IPR policy copy |
| **Faculty guide is co-author** | Add as Author if they made substantive creative contribution (supervising/advising alone is insufficient) | Verify whether actual code/text contribution exists |
| **Industry sponsor involved** | Check sponsor agreement for IP assignment clauses | Sponsor NOC, NDA terms, publication clearance |

### 7.3 Author Contribution Statement Template

```
PROJECT: AlphaStreams — Real-Time Quantitative Analytics & Option Pricing Engine

We, the undersigned authors, declare our individual contributions to the
copyrightable works of this project as follows:

Author              | Contribution Summary                    | Signature | Date
--------------------|-----------------------------------------|-----------|-----
Hirdhay Jadhwani    | [Specific modules, code, text authored] |           |
Siddharth Jogi      | [Specific modules, code, text authored] |           |
Sumanyu Joshi       | [Specific modules, code, text authored] |           |
Nirmay Kadam        | [Specific modules, code, text authored] |           |

We confirm that all third-party materials have been identified in the
Third-Party Register. We do not claim copyright over third-party code,
libraries, datasets, or APIs used in this project.
```

---

## 8. Third-Party & Open-Source Register

> [!WARNING]
> **Critical compliance requirement.** All third-party components must be identified and logged. None of these may be claimed as original work in any copyright application.

### 8.1 Open-Source Libraries (Python Runtime Dependencies)

| Component | Version | Source | Licence | Use | Modifications |
|-----------|---------|--------|---------|-----|--------------|
| FastAPI | ≥0.110.0 | [pypi.org/project/fastapi](https://pypi.org/project/fastapi/) | MIT | Web framework, REST/WS gateway | None — used as-is |
| Uvicorn | ≥0.29.0 | [pypi.org/project/uvicorn](https://pypi.org/project/uvicorn/) | BSD-3-Clause | ASGI server | None |
| SciPy | ≥1.12.0 | [scipy.org](https://scipy.org/) | BSD-3-Clause | `scipy.sparse.linalg.splu` (SuperLU bindings), `scipy.interpolate.CubicSpline` | None — called via API |
| NumPy | ≥1.26.0 | [numpy.org](https://numpy.org/) | BSD-3-Clause | Numerical array operations, grid construction | None |
| pandas | ≥2.2.0 | [pandas.pydata.org](https://pandas.pydata.org/) | BSD-3-Clause | DataFrame operations, backtesting data management | None |
| Redis (Python client) | ≥5.0.0 | [pypi.org/project/redis](https://pypi.org/project/redis/) | MIT | Cache, Streams, Pub/Sub client | None |
| Celery | ≥5.3.0 | [docs.celeryq.dev](https://docs.celeryq.dev/) | BSD-3-Clause | Distributed task queue | None |
| aiohttp | ≥3.9.0 | [pypi.org/project/aiohttp](https://pypi.org/project/aiohttp/) | Apache-2.0 | Async HTTP client for API adapters | None |
| httpx | ≥0.27.0 | [pypi.org/project/httpx](https://pypi.org/project/httpx/) | BSD-3-Clause | HTTP client | None |
| asyncpg | ≥0.29.0 | [pypi.org/project/asyncpg](https://pypi.org/project/asyncpg/) | Apache-2.0 | PostgreSQL async driver | None |
| yfinance | ≥0.2.36 | [pypi.org/project/yfinance](https://pypi.org/project/yfinance/) | Apache-2.0 | Historical OHLCV data retrieval | None |
| pydantic-settings | ≥2.2.0 | [pypi.org/project/pydantic-settings](https://pypi.org/project/pydantic-settings/) | MIT | Configuration management | None |
| openpyxl | ≥3.1.2 | [pypi.org/project/openpyxl](https://pypi.org/project/openpyxl/) | MIT | Excel export | None |
| pytz | ≥2024.1 | [pypi.org/project/pytz](https://pypi.org/project/pytz/) | MIT | Timezone handling | None |
| growwapi | ≥0.1.0 | [pypi.org/project/growwapi](https://pypi.org/project/growwapi/) | [Verify licence] | Groww broker integration | None |
| pyotp | ≥2.6.0 | [pypi.org/project/pyotp](https://pypi.org/project/pyotp/) | MIT | TOTP authentication | None |
| uvloop | ≥0.19.0 | [pypi.org/project/uvloop](https://pypi.org/project/uvloop/) | MIT/Apache-2.0 | High-perf event loop (Linux only) | None |
| websockets | ≥12.0 | [pypi.org/project/websockets](https://pypi.org/project/websockets/) | BSD-3-Clause | WebSocket protocol | None |
| Flower | ≥2.0.0 | [pypi.org/project/flower](https://pypi.org/project/flower/) | BSD-3-Clause | Celery monitoring | None |

### 8.2 Development & Research Dependencies

| Component | Version | Licence | Use |
|-----------|---------|---------|-----|
| pytest | ≥8.0.0 | MIT | Testing framework |
| pytest-asyncio | ≥0.23.0 | Apache-2.0 | Async test support |
| pytest-mock | ≥3.12.0 | MIT | Test mocking |
| matplotlib | ≥3.8.0 | PSF-based | Research figure generation |
| seaborn | ≥0.13.0 | BSD-3-Clause | Statistical plots |
| scikit-learn | ≥1.4.0 | BSD-3-Clause | Statistical analysis |

### 8.3 Infrastructure & Runtime Components

| Component | Source | Licence | Use |
|-----------|--------|---------|-----|
| PostgreSQL 15 | [postgresql.org](https://www.postgresql.org/) | PostgreSQL License (BSD-like) | Relational database |
| TimescaleDB | [timescale.com](https://www.timescale.com/) | Timescale License (Apache-2.0 for Community) | Time-series hypertable extension |
| Redis | [redis.io](https://redis.io/) | Redis Source Available License (RSAL) / BSD-3 (older) | In-memory cache, streams, pub/sub |
| Docker | [docker.com](https://www.docker.com/) | Apache-2.0 | Containerization |
| Supervisord | [supervisord.org](http://supervisord.org/) | BSD-like | Process management |
| SuperLU (C library) | [crd-legacy.lbl.gov](https://crd-legacy.lbl.gov/~xiaoye/SuperLU/) | BSD-3-Clause | Sparse LU factorization (accessed via SciPy bindings) |

### 8.4 Frontend Third-Party Components

| Component | Source | Licence | Use |
|-----------|--------|---------|-----|
| Supabase JS SDK | [supabase.com](https://supabase.com/) | Apache-2.0 | Client-side authentication, user profiles |
| SheetJS (XLSX) | [sheetjs.com](https://sheetjs.com/) | Apache-2.0 (Community) | Excel export from browser |
| Google Fonts | [fonts.google.com](https://fonts.google.com/) | SIL Open Font License | Typography |

### 8.5 Datasets

| Dataset | Source | Terms/Licence | Use | Restrictions |
|---------|--------|--------------|-----|-------------|
| NSE NIFTY 50 OHLCV (via yfinance) | Yahoo Finance / yfinance API | Yahoo Terms of Service | Historical price data for backtesting | Check Yahoo ToS for redistribution limits |
| NSE F&O Bhavcopy Archives | National Stock Exchange of India | NSE Data Terms | Option chain cross-sectional records | Check NSE data redistribution policy |
| NSE Live Option Chain API | nseindia.com | NSE website terms | Real-time option chain ingestion | Not for redistribution; session/cookie-based access |
| Groww API Market Data | Groww (broker API) | Groww API Terms | Live quotes and option chains | Broker-specific terms apply |

### 8.6 AI Assistance Disclosure

| Tool | Use | Institutional Policy |
|------|-----|---------------------|
| AI coding assistants (e.g., Claude, GitHub Copilot) | Code generation assistance, documentation drafting, architecture review | **Check institutional policy** on AI-assisted work. Record the nature of AI contribution and confirm human authorship of final copyrightable expression. |

> [!IMPORTANT]
> Under current Indian copyright law, only natural persons or legal entities (not AI tools) can be listed as "authors." AI-generated output may or may not be copyrightable depending on the degree of human creative contribution. The team must ensure and document that all submitted code and text reflects substantive human authorship.

---

## 9. Patent Timing & Trade Secret Assessment

### 9.1 Patentability Assessment

| Component | Potentially Novel? | Assessment |
|-----------|-------------------|------------|
| Cubic spline volatility surface + CN-PDE + dynamic statutory friction model as a unified computational system | **Possibly** | The individual mathematical techniques (cubic splines, Crank-Nicolson, SuperLU) are well-known. However, the **specific combination** applied as a unified system for Indian statutory friction-aware options mispricing detection may constitute a novel technical contribution. Requires formal patentability opinion from a qualified patent attorney. |
| Dynamic epsilon threshold computation ($\epsilon_t = \text{RoundTrip} \times \kappa$) | Unlikely | Mathematical formula / business method — generally not patentable under Indian Patents Act §3(k) (computer programs per se) and §3(m) (mathematical methods). |
| Hybrid "Quant-Mental" Filter combining PDE + RSI/MACD | Unlikely | Combination of known techniques without novel technical effect. |

### 9.2 Critical Patent Timing Warning

> [!CAUTION]
> **Public disclosure destroys patent novelty.** Under the Indian Patents Act 1970, filing must occur **before** any public disclosure. The following actions all constitute public disclosure:
> - Uploading the research paper to arXiv or SSRN
> - Publishing on GitHub as a public repository
> - Conference presentation, poster session, or demo
> - Project exhibition or public viva
> - Hosting the application on a publicly accessible URL
> 
> **If patentability is to be evaluated, it must be done BEFORE any of these events.**

### 9.3 Trade Secret Candidates

The following elements have commercial value and should be maintained under confidentiality:

| Element | Why It's Valuable | Protection Method |
|---------|------------------|------------------|
| Calibrated buffer multiplier ($\kappa = 1.5$) | Determines trade entry sensitivity | Restrict access; do not publish in paper |
| Near-ATM strike window (150-point radius) | Filters false PDE signals from illiquid wings | Restrict access; may publish in paper with caution |
| 2-bar minimum hold before mean-reversion exit | Prevents ghost trades that bleed friction | Bug fix with strategic value; restrict pre-publication |
| NSE session cookie rotation interval (600s) | Anti-detection scraping cadence | Do not publish; operational know-how |
| Risk engine thresholds (2% daily drawdown, 5% single-strike cap) | Execution safeguards for live trading | Internal operational parameter |

---

## 10. Filing Workflow & Checklist

### 10.1 Online Filing Process (Copyright Office Portal)

1. **Create/Login** to the official Copyright Office portal: [copyright.gov.in](https://copyright.gov.in/UserRegistration/frmLoginPage.aspx)
2. **Select** Online Copyright Registration
3. **Complete Form XIV** (applicant, work title, class, authors, publication status)
4. **Complete Statement of Particulars** (work description, language, rights ownership)
5. **Complete Statement of Further Particulars** (applicable for Software, Literary, and Artistic works)
6. **Prepare** applicant signature, work files, and supporting documents
7. **Upload** the work + all required supporting documents
8. **Pay** the prescribed fee via the portal
9. **Record the Diary Number** — retain submitted package copies
10. **Monitor** status for deficiencies; respond as required

### 10.2 Master Pre-Filing Checklist

#### General (All Works)
- [ ] Final project title is consistent across **all** documents and applications
- [ ] Applicant/owner confirmed under institutional IPR policy
- [ ] All four authors accurately identified with full legal names
- [ ] Original code/text/artwork clearly separated from third-party material
- [ ] Open-source library licences reviewed and logged in Third-Party Register
- [ ] Dataset terms of use reviewed (NSE Bhavcopy, yfinance, Groww API)
- [ ] AI assistance usage documented per institutional policy
- [ ] NOC/assignment agreements obtained where ownership requires
- [ ] Form XIV information prepared per official portal fields
- [ ] Uploaded files are **not** password-protected
- [ ] Copies of submission, receipt, fee proof, and Diary Number retained

#### Software-Specific
- [ ] Source code PDF follows current upload rules (first 10 + last 10 pages, or full if <20pp)
- [ ] **No API keys, tokens, passwords, TOTP secrets, or credentials** in submitted code
- [ ] No prohibited redacted/blacked-out portions
- [ ] Code formatted with readable font, page numbers, and cover page
- [ ] Programming languages listed (Python 3.11+, JavaScript ES6+, HTML5, CSS3, SQL)

#### Research Paper-Specific
- [ ] Paper compiled from LaTeX to clean PDF
- [ ] Publication status accurately recorded (published/unpublished)
- [ ] IEEE copyright transfer implications assessed if applicable
- [ ] All citations and bibliography entries are accurate

#### Block Diagram-Specific
- [ ] Diagram actually created by the team (not auto-generated by third-party tool)
- [ ] Exact title matches copyright application
- [ ] Saved in portal-accepted format (PDF or JPG)
- [ ] Editable master/source file retained (SVG, DrawIO, etc.)
- [ ] No confidential credentials visible
- [ ] Trademark implications considered if diagram doubles as logo/brand asset

#### Patent & Trade Secret Cross-Checks
- [ ] Patent/IPR cell consulted if any patentable invention exists
- [ ] Patent filing timeline evaluated **before** public disclosure
- [ ] Trade secret parameters identified and access-controlled
- [ ] Confidentiality measures in place for undisclosed calibration data

---

## 11. Recommended IPR Folder Structure

```
AlphaStreams_IPR/
├── 01_Project_Identity/
│   ├── AlphaStreams_ProjectIdentity.pdf
│   └── AlphaStreams_AuthorContribution.pdf
│
├── 02_Copyright_Software/
│   ├── AlphaStreams_SourceCode.pdf               # First 10 + Last 10 pages (sanitized)
│   ├── AlphaStreams_ObjectCode.pdf                # If portal requests
│   ├── FormXIV_Software_Copy.pdf                 # Saved copy from portal
│   ├── StatementOfParticulars_Software.pdf
│   └── StatementOfFurtherParticulars_Software.pdf
│
├── 03_Copyright_ResearchPaper/
│   ├── AlphaStreams_ResearchPaper.pdf             # Compiled IEEE manuscript
│   ├── FormXIV_Paper_Copy.pdf
│   ├── StatementOfParticulars_Paper.pdf
│   └── StatementOfFurtherParticulars_Paper.pdf
│
├── 04_Copyright_BlockDiagram/
│   ├── AlphaStreams_BlockDiagram.pdf              # Final diagram (PDF/JPG)
│   ├── AlphaStreams_BlockDiagram_Source.svg        # Editable master
│   ├── AlphaStreams_BlockDiagram_Declaration.pdf   # Originality statement
│   ├── FormXIV_Diagram_Copy.pdf
│   └── StatementOfParticulars_Diagram.pdf
│
├── 05_ThirdParty/
│   ├── OpenSource_Register.pdf                    # Full dependency audit (§8)
│   ├── Dataset_Terms_Register.pdf                 # NSE, yfinance, Groww terms
│   ├── AI_Assistance_Disclosure.pdf               # AI tool usage record
│   └── ThirdParty_Notices.pdf                     # Combined licence notices
│
├── 06_Ownership/
│   ├── Ownership_NOC.pdf                          # If institution claims ownership
│   ├── Assignment_Deed.pdf                        # If applicable
│   └── Institutional_IPR_Policy.pdf               # Reference copy
│
├── 07_Patent_Assessment/
│   ├── Invention_Disclosure_Form.pdf              # If patentability pursued
│   └── Patent_Timing_Assessment.pdf               # Pre-disclosure evaluation
│
├── 08_Development_Record/
│   ├── Git_Commit_History.pdf                     # `git log` extract with dates
│   ├── Development_Milestones.pdf                 # Timeline of major features
│   └── Architecture_Decision_Records.pdf          # Key design decisions
│
└── 09_Submission_Records/
    ├── Payment_Receipt_Software.pdf
    ├── Payment_Receipt_Paper.pdf
    ├── Payment_Receipt_Diagram.pdf
    ├── DiaryNumber_Software.pdf
    ├── DiaryNumber_Paper.pdf
    └── DiaryNumber_Diagram.pdf
```

---

## 12. Official References

> [!NOTE]
> Portal URLs, fee structures, and procedural rules are subject to change. Always verify against the official Copyright Office website before filing.

| Resource | URL |
|----------|-----|
| Copyright Office — Online Filing/Login | [copyright.gov.in/UserRegistration/frmLoginPage.aspx](https://copyright.gov.in/UserRegistration/frmLoginPage.aspx) |
| Copyright Office — Form XIV | [copyright.gov.in/Copyright_Rules_2013/formxiv.html](https://copyright.gov.in/Copyright_Rules_2013/formxiv.html) |
| Copyright Office — General Instructions | [copyright.gov.in/Copyright_Rules_2013/general_instructions.html](https://copyright.gov.in/Copyright_Rules_2013/general_instructions.html) |
| Copyright Rules 2013 — Chapter XIII / Rule 70 | [copyright.gov.in/Copyright_Rules_2013/chapter_xiii.html](https://copyright.gov.in/Copyright_Rules_2013/chapter_xiii.html) |
| Copyright Office — Download Forms/Documents | [copyright.gov.in/frmDownloadPage.aspx](https://copyright.gov.in/frmDownloadPage.aspx) |
| Copyright Office — FAQs | [copyright.gov.in/frmFAQ.aspx](https://copyright.gov.in/frmFAQ.aspx) |
| Copyright Office — Handbook of Copyright Law | [copyright.gov.in/documents/handbook.html](https://copyright.gov.in/documents/handbook.html) |
| Indian Patents Act 1970 — Section 3 (Non-patentable inventions) | [ipindia.gov.in](https://ipindia.gov.in/) |
| SEBI Regulations (RA/PMS/AIF) | [sebi.gov.in](https://www.sebi.gov.in/) |

---

## Appendix A: Originality & Ownership Declaration Template

```
DECLARATION OF ORIGINALITY AND OWNERSHIP

TITLE OF WORK:    [Exact title matching copyright application]
PROJECT:          AlphaStreams — Real-Time Quantitative Analytics &
                  Option Pricing Engine

Declaration: We, the undersigned author(s), declare that the work
identified above was created as an original [computer programme /
literary work / artistic work] for our [final-year / capstone /
research] project. We have identified all third-party material,
open-source libraries, datasets, images, APIs, templates, icons,
fonts, and AI-generated elements used in its preparation in the
accompanying Third-Party Register. We do not claim copyright
ownership over any third-party material.

Ownership of the copyright in this work is subject to:
(a) institutional IPR policy of [Institution Name],
(b) any project agreements or assignments, and
(c) any NOC or authorization obtained.

Author Name         | Roll No. | Contribution  | Signature | Date
--------------------|----------|---------------|-----------|-----
Hirdhay Jadhwani    |          |               |           |
Siddharth Jogi      |          |               |           |
Sumanyu Joshi       |          |               |           |
Nirmay Kadam        |          |               |           |

Faculty Guide (if applicable):
Name: _______________  Signature: ___________  Date: ___________
```

---

## Appendix B: Third-Party Material Declaration Template

```
THIRD-PARTY MATERIAL REGISTER

PROJECT: AlphaStreams V2

Element Used        | Source              | Licence        | Used As-Is/Modified | Action Taken
--------------------|---------------------|----------------|--------------------|--------------
SciPy (splu, spline)| scipy.org           | BSD-3-Clause   | As-is (API calls)  | Attribution
NumPy               | numpy.org           | BSD-3-Clause   | As-is              | Attribution
pandas              | pandas.pydata.org   | BSD-3-Clause   | As-is              | Attribution
FastAPI             | fastapi.tiangolo.com| MIT            | As-is              | Attribution
Redis               | redis.io            | RSAL/BSD-3     | As-is              | Attribution
PostgreSQL          | postgresql.org      | PostgreSQL Lic | As-is              | Attribution
TimescaleDB         | timescale.com       | Apache-2.0     | As-is              | Attribution
Supabase JS SDK     | supabase.com        | Apache-2.0     | As-is              | Attribution
NSE F&O Bhavcopy    | NSE India           | NSE Terms      | As-is              | Verify terms
yfinance data       | Yahoo Finance       | Yahoo ToS      | As-is              | Verify terms
[Add more rows as needed]
```

---

*Prepared by the AlphaStreams / Shani Quant Research Team — August 2026*  
*This document should be reviewed by qualified legal counsel before formal copyright application filing.*
