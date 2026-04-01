# Prompt Validator MVP - Architecture & Design Flow

## 1. System Architecture (High-Level)

```mermaid
graph TB
    subgraph Clients["Channels"]
        WEB["Web UI<br/>(Vanilla HTML/CSS/JS)"]
        MCP["MCP Client<br/>(API Integration)"]
        TEAMS["MS Teams Bot"]
    end

    subgraph API["FastAPI Backend (app/main.py)"]
        CORS["CORS Middleware"]
        ROUTER["API Router<br/>/api/v1/*"]
    end

    subgraph Services["Core Services"]
        RE["Rules Engine<br/>(rules_engine.py)"]
        IMP["Improver<br/>(improver.py)"]
        PL["Persona Loader<br/>(persona_loader.py)"]
        GL["Guidelines Loader<br/>(prompt_guidelines_loader.py)"]
        HS["History Service<br/>(history_service.py)"]
    end

    subgraph Auth["Auth & Identity"]
        PM["Persona Mapping<br/>(persona_mapping.py)"]
        OAUTH["OAuth Provider<br/>(mock)"]
    end

    subgraph Config["Configuration (JSON)"]
        PC["persona_criteria_<br/>source_truth.json"]
        GC["prompt_guidelines_<br/>source_truth.json"]
    end

    subgraph Persistence["Dual Database Layer"]
        SQLite["SQLite<br/>(Local/Dev)"]
        MongoDB["MongoDB Atlas<br/>(Production)"]
    end

    subgraph Integration["Integration Adapters"]
        MCPS["MCP Server<br/>(mcp/server.py)"]
        TB["Teams Bot<br/>(teams/bot.py)"]
    end

    WEB -->|POST /validate| ROUTER
    MCP -->|POST /mcp/validate| ROUTER
    TEAMS -->|POST /teams/message| ROUTER

    ROUTER --> RE
    ROUTER --> IMP
    ROUTER --> MCPS
    ROUTER --> TB
    ROUTER --> PM

    MCPS --> RE
    MCPS --> IMP
    TB --> MCPS

    RE --> PL
    RE --> GL
    IMP --> PL
    PL --> PC
    GL --> GC
    PM --> OAUTH

    RE --> HS
    MCPS --> HS
    HS --> SQLite
    HS --> MongoDB
```

---

## 2. Core Validation Workflow

```mermaid
flowchart TD
    START(["User Submits Prompt"]) --> INPUT["ValidateRequest<br/>prompt_text, persona_id,<br/>user_email, auto_improve"]

    INPUT --> CHECK_EMAIL{user_email provided<br/>AND persona_0?}
    CHECK_EMAIL -->|Yes| RESOLVE["resolve_persona_for_user()<br/>Auto-detect persona from DB"]
    CHECK_EMAIL -->|No| USE_GIVEN["Use provided persona_id"]
    RESOLVE --> LOAD_PERSONA
    USE_GIVEN --> LOAD_PERSONA

    LOAD_PERSONA["get_persona(persona_id)<br/>Load weights + keyword checks<br/>from JSON config"] --> VALIDATE_EMPTY{prompt_text<br/>empty?}

    VALIDATE_EMPTY -->|Yes| ERROR["HTTP 400:<br/>prompt_text cannot be empty"]
    VALIDATE_EMPTY -->|No| EVAL

    subgraph EVAL["evaluate_prompt()"]
        direction TB
        E1["1. Load persona weights<br/>(clarity, context, specificity, ...)"] --> E2["2. Run base dimension checks<br/>(regex + keyword detection)"]
        E2 --> E3["3. Run persona-specific checks<br/>(P1: tech, P2: PM, P3: BA, P4: support)"]
        E3 --> E4["4. Calculate weighted score<br/>score = (sum_passed / total_weight) * 100"]
        E4 --> E5["5. Evaluate guidelines<br/>(strict_mode penalty checks)"]
        E5 --> E6["6. Apply penalties<br/>final = score - min(misses * 3, 15)"]
        E6 --> E7["7. Collect strengths + issues"]
    end

    EVAL --> AUTO{auto_improve<br/>= True?}
    AUTO -->|Yes| IMPROVE["improve_prompt()<br/>Template-based rewriting<br/>per persona role"]
    AUTO -->|No| SKIP["improved = original"]
    IMPROVE --> RATE
    SKIP --> RATE

    RATE["Rating:<br/>>= 85 Excellent<br/>>= 70 Good<br/>>= 50 Needs Improvement<br/>< 50 Poor"] --> SAVE

    subgraph SAVE["save_validation()"]
        direction TB
        S1["PromptValidationRecord"] --> S2["DimensionScoreRecord<br/>(one per dimension)"]
        S2 --> S3["PromptRewriteRecord"]
        S3 --> S4["ChannelUsageRecord"]
        S4 --> S5["FeedbackEventRecord"]
    end

    SAVE --> RESPONSE(["ValidateResponse<br/>score, rating, strengths,<br/>issues, improved_prompt,<br/>dimension_scores,<br/>guideline_evaluation"])

    style EVAL fill:#1a1a2e,stroke:#e94560,color:#fff
    style SAVE fill:#16213e,stroke:#0f3460,color:#fff
    style RESPONSE fill:#0f3460,stroke:#e94560,color:#fff
```

---

## 3. Persona-Specific Scoring Dimensions

```mermaid
graph LR
    subgraph BASE["Base Dimensions (All Personas)"]
        CL["clarity<br/>w:18"]
        CTX["context<br/>w:14"]
        SP["specificity<br/>w:14"]
        OF["output_format<br/>w:14"]
        AR["ambiguity_reduction<br/>w:14"]
        CON["constraints<br/>w:10"]
        ACT["actionability<br/>w:10"]
        ACC["accuracy<br/>w:7"]
    end

    subgraph P1["Persona 1: Developer/QA"]
        TP["technical_precision<br/>w:18"]
        EC["edge_cases<br/>w:18"]
        TEST["testability<br/>w:18"]
        REP1["reproducibility<br/>w:14"]
        RA["role_alignment<br/>w:14"]
    end

    subgraph P2["Persona 2: Technical PM"]
        REP2["reproducibility<br/>w:14"]
        PRI2["prioritization<br/>w:14"]
        TR2["traceability<br/>w:14"]
        BR2["business_relevance<br/>w:10"]
    end

    subgraph P3["Persona 3: Business Analyst"]
        BR3["business_relevance"]
        GR["grounding"]
        TR3["traceability"]
        PRI3["prioritization"]
    end

    subgraph P4["Persona 4: Support"]
        TE["tone_empathy"]
        COMP["compliance"]
        SPD["speed"]
    end

    BASE --> P1
    BASE --> P2
    BASE --> P3
    BASE --> P4

    style BASE fill:#2d3436,stroke:#74b9ff,color:#fff
    style P1 fill:#0984e3,stroke:#74b9ff,color:#fff
    style P2 fill:#6c5ce7,stroke:#a29bfe,color:#fff
    style P3 fill:#00b894,stroke:#55efc4,color:#fff
    style P4 fill:#e17055,stroke:#fab1a0,color:#fff
```

---

## 4. Multi-Channel Request Flow

```mermaid
sequenceDiagram
    participant U as User
    participant W as Web UI
    participant A as FastAPI Router
    participant PM as Persona Mapping
    participant RE as Rules Engine
    participant GL as Guidelines
    participant IM as Improver
    participant HS as History Service
    participant DB as Database

    Note over U,DB: === Web Channel ===
    U->>W: Enter prompt + select persona
    W->>A: POST /api/v1/validate
    A->>PM: resolve_persona_for_user(email)
    PM-->>A: resolved_persona_id
    A->>RE: evaluate_prompt(text, persona_id)
    RE->>GL: evaluate_guidelines(text)
    GL-->>RE: penalty + checks
    RE-->>A: score, dimensions, strengths, issues
    A->>IM: improve_prompt(text, persona_id, issues)
    IM-->>A: improved_prompt
    A->>HS: save_validation(all_data)
    HS->>DB: Insert 5 records
    DB-->>HS: OK
    A-->>W: ValidateResponse (JSON)
    W-->>U: Score + Diff View

    Note over U,DB: === MCP Channel ===
    U->>A: POST /api/v1/mcp/validate [x-api-key]
    A->>RE: (same validation pipeline)
    RE-->>A: results
    A-->>U: ValidateResponse (channel=mcp)

    Note over U,DB: === Teams Channel ===
    U->>A: POST /api/v1/teams/message [x-api-key]
    A->>PM: resolve_persona_for_user(email)
    A->>RE: (delegates to MCP server internally)
    RE-->>A: results
    A-->>U: Teams-formatted response
```

---

## 5. Database Schema (Entity Relationship)

```mermaid
erDiagram
    User {
        int id PK
        string email UK
        string display_name
        bool is_active
        datetime created_at
    }

    PersonaAssignment {
        int id PK
        string user_email FK
        string persona_id
        string source
        bool is_primary
        datetime created_at
    }

    PromptValidationRecord {
        int id PK
        string persona_id
        string channel
        text prompt_text
        float score
        string rating
        text issues_json
        text suggestions_json
        text improved_prompt
        string user_email
        int issue_count
        datetime created_at
    }

    DimensionScoreRecord {
        int id PK
        int validation_id FK
        string persona_id
        string dimension_name
        float score
        float weight
        bool passed
        text notes
        datetime created_at
    }

    PromptRewriteRecord {
        int id PK
        int validation_id FK
        string persona_id
        text original_prompt
        text improved_prompt
        string rewrite_strategy
        datetime created_at
    }

    ChannelUsageRecord {
        int id PK
        string channel
        string persona_id
        string user_email
        string event_type
        datetime created_at
    }

    FeedbackEventRecord {
        int id PK
        int validation_id FK
        string persona_id
        string event_type
        text message
        datetime created_at
    }

    User ||--o{ PersonaAssignment : "has"
    PromptValidationRecord ||--o{ DimensionScoreRecord : "has"
    PromptValidationRecord ||--o| PromptRewriteRecord : "has"
    PromptValidationRecord ||--o{ FeedbackEventRecord : "has"
    PromptValidationRecord }o--|| ChannelUsageRecord : "tracks"
```

---

## 6. Component Dependency Graph

```mermaid
graph TD
    MAIN["app/main.py<br/>(FastAPI App)"] --> ROUTES["app/api/routes.py"]
    MAIN --> DB_INIT["app/db/database.py"]
    MAIN --> SETTINGS["app/core/settings.py"]

    ROUTES --> RE["services/rules_engine.py"]
    ROUTES --> IMP["services/improver.py"]
    ROUTES --> HS["services/history_service.py"]
    ROUTES --> PL["services/persona_loader.py"]
    ROUTES --> GL_LOAD["services/prompt_guidelines_loader.py"]
    ROUTES --> PM["auth/persona_mapping.py"]
    ROUTES --> OAUTH["integrations/oauth/provider.py"]
    ROUTES --> MCP["integrations/mcp/server.py"]
    ROUTES --> TEAMS["integrations/teams/bot.py"]
    ROUTES --> REPO["repositories/validation_repository.py"]
    ROUTES --> SCHEMAS["models/schemas.py"]

    RE --> PL
    RE --> GL_LOAD
    IMP --> PL
    MCP --> RE
    MCP --> IMP
    MCP --> HS
    MCP --> PM
    TEAMS --> MCP
    TEAMS --> PM

    PL --> PC_JSON["config/persona_criteria_<br/>source_truth.json"]
    GL_LOAD --> GL_JSON["config/prompt_guidelines_<br/>source_truth.json"]

    HS --> DB_MODELS["models/db_models.py"]
    HS --> DB_INIT
    HS --> MONGO["db/mongo_db.py"]
    PM --> DB_MODELS
    REPO --> DB_INIT

    DB_INIT --> SETTINGS
    MONGO --> SETTINGS
    DB_MODELS --> DB_INIT

    style MAIN fill:#e94560,stroke:#fff,color:#fff
    style ROUTES fill:#0f3460,stroke:#fff,color:#fff
    style RE fill:#e94560,stroke:#fff,color:#fff
    style IMP fill:#e94560,stroke:#fff,color:#fff
    style HS fill:#16213e,stroke:#fff,color:#fff
```

---

## 7. Deployment Architecture

```mermaid
graph TB
    subgraph Vercel["Vercel Platform"]
        DEPLOY["Deployment Engine<br/>(vercel.json)"]
        FUNC["Serverless Function<br/>(Python/FastAPI)"]
        STATIC["Static Files<br/>(frontend/index.html)"]
    end

    subgraph External["External Services"]
        MONGO_ATLAS["MongoDB Atlas<br/>(Production DB)"]
    end

    subgraph Local["Local Development"]
        UVICORN["uvicorn app.main:app<br/>--reload"]
        SQLITE["SQLite<br/>(prompt_validator.db)"]
    end

    DEPLOY --> FUNC
    DEPLOY --> STATIC
    FUNC --> MONGO_ATLAS

    UVICORN --> SQLITE

    ENV["Environment Variables<br/>MONGODB_URI<br/>DATABASE_BACKEND<br/>API_KEY"] --> FUNC
    ENV --> UVICORN

    style Vercel fill:#1a1a2e,stroke:#e94560,color:#fff
    style External fill:#16213e,stroke:#0f3460,color:#fff
    style Local fill:#2d3436,stroke:#74b9ff,color:#fff
```

---

## 8. Scoring Algorithm Flow

```mermaid
flowchart LR
    INPUT["Prompt Text"] --> BASE_CHECK["Base Checks<br/>(8 dimensions)"]
    INPUT --> PERSONA_CHECK["Persona Checks<br/>(3-5 extra dims)"]
    INPUT --> GUIDELINE_CHECK["Guideline Checks<br/>(global strict rules)"]

    BASE_CHECK --> WEIGHTED["Weighted Sum<br/>score = passed_weight /<br/>total_weight * 100"]
    PERSONA_CHECK --> WEIGHTED

    GUIDELINE_CHECK --> PENALTY["Penalty<br/>min(misses * 3, 15)"]

    WEIGHTED --> FINAL["Final Score<br/>= weighted - penalty"]
    PENALTY --> FINAL

    FINAL --> RATING{Rating}
    RATING -->|>= 85| EX["Excellent"]
    RATING -->|>= 70| GOOD["Good"]
    RATING -->|>= 50| NI["Needs Improvement"]
    RATING -->|< 50| POOR["Poor"]

    style FINAL fill:#e94560,stroke:#fff,color:#fff
    style EX fill:#00b894,stroke:#fff,color:#fff
    style GOOD fill:#0984e3,stroke:#fff,color:#fff
    style NI fill:#fdcb6e,stroke:#fff,color:#000
    style POOR fill:#d63031,stroke:#fff,color:#fff
```

---

## 9. API Endpoint Map

```mermaid
graph LR
    subgraph Public["Public Endpoints"]
        H1["GET /health"]
        H2["GET /health/db"]
        P["GET /personas"]
        G["GET /guidelines"]
        V["POST /validate"]
        I["POST /improve"]
        HI["GET /history"]
    end

    subgraph Protected["Protected (x-api-key)"]
        AR["POST /auth/resolve"]
        AMP["POST /auth/map-persona"]
        MV["POST /mcp/validate"]
        TM["POST /teams/message"]
        AN["GET /analytics/summary"]
    end

    V --> RE["rules_engine"]
    V --> IMP["improver"]
    V --> HS["history_service"]
    I --> V

    MV --> MCP["mcp/server"]
    TM --> TB["teams/bot"]
    TB --> MCP

    AR --> OAUTH["oauth/provider"]
    AMP --> PM["persona_mapping"]
    AN --> REPO["validation_repository"]

    style Public fill:#16213e,stroke:#0f3460,color:#fff
    style Protected fill:#1a1a2e,stroke:#e94560,color:#fff
```

---

## Key Architectural Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Validation approach | Rules-based (regex/keyword) | Deterministic, fast, no LLM cost per validation |
| Improvement strategy | Template-based rewriting | Predictable structure, persona-specific context |
| Database | Dual SQLite/MongoDB | SQLite for dev speed, MongoDB Atlas for production scale |
| Auth | Mock OAuth + API key | MVP simplicity; swap to real OAuth later |
| Frontend | Vanilla HTML/CSS/JS | Zero build step, fast iteration for MVP |
| Integration pattern | Thin adapters over core | MCP and Teams reuse the same validation pipeline |
| Persona config | External JSON files | Non-developers can tune weights without code changes |
| Scoring | Weighted pass/fail per dimension | Transparent, explainable scores per persona |
