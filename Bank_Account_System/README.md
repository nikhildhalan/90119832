# Horizon Bank Account System

A runnable beginner capstone structure for account opening, balance enquiry, same-bank transfers, account statements and asynchronous notifications. It follows the attached Horizon Bank case study and uses Python 3.12+, FastAPI, PostgreSQL 16, Redis 7 and Apache Kafka 4.3.1. All bank/customer/account examples are fictional training data.

## Included

- app/ — FastAPI app, API routes, business validation, PostgreSQL repositories, Redis cache, Kafka events and notification consumer.
- db/01_schema.sql — schema, constraints, indexes, least-privilege application role and append-only ledger protection.
- db/02_seed.sql — sample customers, accounts, transfer rows and ledger.
- db/03_reconciliation.sql — balance/ledger and paired-transfer integrity queries.
- docker-compose.yml — PostgreSQL, Redis, Kafka and Kafka UI; PostgreSQL initializes schema and sample records on first start.
- scripts/create_topics.sh — creates the required Kafka topics.
- collections/Bank_Account_System.postman_collection.json — API request examples.
- docs/PROJECT_DOCUMENTATION.md — requirements, arch~itecture, API, data model, event contract, roadmap and operational notes.
- requirements.txt / requirements.lock.txt — Python dependencies; .venv/ is the local environment.

## Start

Run from this folder:

    docker compose up -d
    ./scripts/create_topics.sh
    source ../.venv/bin/activate
    uvicorn app.main:app --reload --port 8080

In a second terminal, start the notification consumer:

    source ../.venv/bin/activate
    python -m app.consumer

Open the API documentation at http://localhost:8080/docs and Kafka UI at http://localhost:8085. The health endpoint is http://localhost:8080/api/v1/health.

### Local connection settings

- PostgreSQL: localhost:5433 (container port 5432), database bankdb, application role bank_app / bank_app_pwd
- Redis: localhost:6379
- Kafka: localhost:9092
- Kafka UI: localhost:8085

These example credentials are only for local training. Do not use them in a deployed environment. .env.example documents environment-based settings; copy it to .env to customize local configuration. .env is ignored by Git.

## API quick examples

    curl http://localhost:8080/api/v1/accounts/501000000001

    curl -X POST http://localhost:8080/api/v1/transfers \
      -H 'Content-Type: application/json' \
      -H 'Idempotency-Key: demo-transfer-001' \
      -d '{"fromAccountNumber":"501000000001","toAccountNumber":"501000000002","amount":"2500.00","remarks":"Demo"}'

Import the Postman collection from collections/. Requests use the sample seed accounts.

## Stop / reset

Stop containers and retain training data:

    docker compose down

Reset database and Redis volumes and reinitialize the seed (this permanently deletes local training data):

    docker compose down -v
    docker compose up -d
    ./scripts/create_topics.sh

## Current readiness

The Python source compiles, the API imports and generates its OpenAPI routes, the Postman collection parses, and the Compose file validates. The containers and end-to-end flows have not been started or integration-tested in this session.

## Safety and project scope

This is a local learning project, not production banking software. It has no authentication or authorization. Keep it on a trusted local machine; do not expose its ports publicly or use real personal or financial data. The application uses exact decimal values, sorted PostgreSQL row locks, transactional balance/ledger updates and idempotency keys. Kafka publishing is after database commit as specified by the training brief; a transactional outbox is the recommended next improvement for eliminating the commit/publish gap.
