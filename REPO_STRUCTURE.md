# Prompt Validator - Complete Repo Structure

This repository is organized to support the full phased rollout:

- Phase 1: Backend engine + layered APIs for all 5 personas
- Phase 2: MCP / LLM-native exposure layer
- Phase 3: Chat interfaces, starting with Microsoft Teams bot
- Phase 4: IDE / plugin integrations

## Folder map

```text
prompt_validator_complete_repo/
├── app/
│   ├── api/                    # existing FastAPI routes
│   ├── auth/                   # auth and persona mapping hooks
│   ├── config/                 # persona weights and common rules
│   ├── core/                   # settings, startup
│   ├── data/                   # seed data, SQL, mapping templates
│   ├── db/                     # DB init and persistence
│   ├── engines/                # scoring, feedback, autofix orchestration
│   ├── integrations/
│   │   ├── mcp/                # MCP exposure layer
│   │   ├── oauth/              # OAuth / org mapping placeholders
│   │   └── teams/              # Teams bot adapter placeholders
│   ├── middleware/             # auth, request logging, tracing
│   ├── models/                 # schemas and DB models
│   ├── repositories/           # DB access abstraction
│   ├── routers/                # future split routers per phase/channel
│   ├── services/               # rules engine, improver, history
│   └── utils/                  # shared helpers
├── frontend/
│   ├── index.html              # MVP UI
│   └── src/                    # scalable frontend layout for next phase
├── docs/
│   ├── source_of_truth/
│   │   ├── validator_framework/# first two core documents
│   │   └── prompt_guidelines/  # provider guideline documents
│   ├── architecture/           # solution design docs
│   ├── api/                    # endpoint contracts
│   ├── data_strategy/          # day-2 artifacts
│   ├── mcp/                    # day-4 MCP notes
│   ├── teams/                  # day-5 Teams notes
│   ├── testing/                # validation and QA plan
│   └── Prompt_Validator_MVP_BRD.docx
├── deploy/                     # docker / hosting manifests
├── examples/                   # sample prompts and expected outputs
├── scripts/                    # local setup, seed, packaging helpers
├── tests/
│   ├── unit/
│   ├── integration/
│   └── fixtures/
└── README.md
```
