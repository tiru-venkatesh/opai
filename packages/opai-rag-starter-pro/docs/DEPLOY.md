# Deploying the API

## Docker Compose (single server)
```bash
cp deploy/.env.example .env      # set POSTGRES_PASSWORD, optionally ANTHROPIC_API_KEY
docker compose -f deploy/docker-compose.yml --env-file .env up --build -d
docker compose -f deploy/docker-compose.yml exec api opai-rag-pro keys create --name my-first-customer
```
The key is printed once. Only its SHA-256 is stored.

```bash
curl -H "Authorization: Bearer $KEY" -F files=@handbook.pdf http://localhost:8000/v1/documents
curl -H "Authorization: Bearer $KEY" -H 'content-type: application/json' \
     -d '{"question":"What is the refund policy?"}' http://localhost:8000/v1/ask
```

## Before exposing it to the internet
- Put it behind TLS (Caddy, nginx, or your platform's load balancer). The app does not terminate TLS.
- Keep the database private (the compose file publishes no Postgres port).
- Back up the `pgdata` volume. It holds documents and keys.
- Set `OPAI_RAG_DAILY_ASKS` to a number your LLM budget can afford per customer.
- The rate limiter is per process. With `--workers 2` a key can reach about twice the configured rate;
  use a gateway limit if you need it exact. The daily quota is exact (it lives in Postgres).
- If you switch embedders, the API refuses to mix them (HTTP 409). Create a fresh database and re-ingest.

## Operations
| Task | Command |
|---|---|
| List keys | `opai-rag-pro keys list` |
| Revoke a key | `opai-rag-pro keys revoke ID` |
| A key's usage today | `opai-rag-pro usage ID` |
| Which tenant owns data? | the key's namespace; clients cannot choose it |
