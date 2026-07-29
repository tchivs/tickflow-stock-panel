# Security Policy

## Reporting a Vulnerability

Do not open a public issue for a suspected vulnerability and do not include credentials, API keys, private market data, or model artifacts in a report. Use a private GitHub security advisory for this repository, or contact the repository owner through GitHub with the affected version, reproduction steps, impact, and a minimal proof of concept.

## Security Boundaries

AthenaQuant is a self-hosted single-user research service. Its security model depends on:

- Keeping `.env`, `data/`, operational SQLite databases, checkpoints, and generated reports out of version control.
- Setting `AUTH_PASSWORD` before exposing a fresh deployment to the public internet.
- Treating browser-provided fields as intent only; the server owns identities, authorization, evidence bindings, and lifecycle transitions.
- Running optional Forecast workers with provisioned, pinned assets only. Remote code and runtime model downloads are not supported.
- Reviewing custom data-provider mappings and strategy code before enabling them in a trusted deployment.

The application is not a brokerage, custody, execution, or trading-advice service. Do not expose it as one.
