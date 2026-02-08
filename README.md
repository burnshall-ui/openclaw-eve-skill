# EVE ESI Skill

An [OpenClaw](https://github.com/openclaw/openclaw) skill for interacting with the [EVE Online ESI API](https://developers.eveonline.com/api-explorer) (EVE Swagger Interface).

## What does it do?

- Query character info, wallet, assets, skills, clones, location, contracts, mail and more via the ESI API
- **Dashboard Config** — modular alert/report/market-tracking system per user
- Guide for the EVE SSO OAuth2 authentication flow
- Reusable Python scripts for ESI queries and config validation

## Structure

```
eve-esi/
├── SKILL.md                        # Skill instructions + curl examples
├── config/
│   ├── schema.json                 # JSON Schema for dashboard config (v1.0)
│   └── example-config.json         # Ready-to-use example config
├── references/
│   ├── authentication.md           # EVE SSO OAuth2 flow + scopes
│   └── endpoints.md                # All character endpoints
└── scripts/
    ├── esi_query.py                # ESI query helper (Python 3.8+)
    └── validate_config.py          # Config validator with scope checking
```

## Installation

Copy the `eve-esi/` folder into your OpenClaw skills directory.

## Quick Start

```bash
# Query wallet balance
curl -s -H "Authorization: Bearer $TOKEN" \
  "https://esi.evetech.net/latest/characters/$CHAR_ID/wallet/"

# Or use the bundled script
python eve-esi/scripts/esi_query.py --token "$TOKEN" \
  --endpoint "/characters/$CHAR_ID/wallet/" --pretty
```

## Dashboard Config

Set up personalized alerts, reports, and market tracking:

1. Copy `config/example-config.json` to `~/.openclaw/eve-dashboard-config.json`
2. Fill in your character data and preferences
3. Use `$ENV:VARIABLE_NAME` for tokens (never store secrets in plain text)
4. Validate with: `python eve-esi/scripts/validate_config.py ~/.openclaw/eve-dashboard-config.json`

See [config/schema.json](eve-esi/config/schema.json) for all available fields and defaults.
