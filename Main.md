# Test-Driven Development with FastAPI and Docker

## Part 1: Local Development Setup

In this hands-on lab, you'll learn how to set up a local development environment for a text summarization service with Python, FastAPI, and Docker. The service will be exposed via a RESTful API that allows users to submit URLs and receive AI-generated summaries of the content.

---

## Table of Contents

1. [Project Overview](#project-overview)
2. [Project Structure](#project-structure)
3. [Docker Setup](#docker-setup)
4. [Database Configuration](#database-configuration)
5. [FastAPI Application Setup](#fastapi-application-setup)
6. [Configuration Management](#configuration-management)
7. [Database Integration with Tortoise ORM](#database-integration-with-tortoise-orm)
8. [Data Models](#data-models)
9. [RESTful API Routes](#restful-api-routes)
10. [Running the Application](#running-the-application)

---

## Project Overview

### What We're Building

A RESTful API service that:
- Accepts URLs via POST requests
- Extracts and summarizes the content from those URLs using NLP
- Stores summaries in a PostgreSQL database
- Provides full CRUD operations (Create, Read, Update, Delete) for summaries

### Technologies Used

| Technology | Purpose |
|------------|---------|
| **FastAPI** | Modern, fast web framework for building APIs |
| **Docker** | Containerization for consistent development environments |
| **PostgreSQL** | Relational database for storing summaries |
| **Tortoise ORM** | Async ORM for database operations |
| **Pydantic** | Data validation and serialization |
| **Pytest** | Testing framework |
| **newspaper3k** | Article extraction and NLP summarization |

---

## Project Structure

```
text-summarization-serving
    project/
    ├── app/
    │   ├── __init__.py
    │   ├── main.py              # FastAPI application entry point
    │   ├── config.py            # Configuration management
    │   ├── db.py                # Database connection setup
    │   ├── summarizer.py        # Text summarization logic
    │   ├── api/
    │   │   ├── __init__.py
    │   │   ├── ping.py          # Health check endpoint
    │   │   ├── summaries.py     # Summary CRUD endpoints
    │   │   └── crud.py          # Database operations
    │   └── models/
    │       ├── __init__.py
    │       ├── tortoise.py      # Tortoise ORM models
    │       └── pydantic.py      # Pydantic schemas
    ├── db/
    │   ├── Dockerfile           # PostgreSQL container config
    │   └── create.sql           # Database initialization
    ├── migrations/
    │   └── models/
    │       └── 0_20211227001140_init.sql
    ├── tests/
    │   ├── __init__.py
    │   ├── conftest.py          # Pytest fixtures
    │   ├── test_ping.py         # Health check tests
    │   ├── test_summaries.py    # Integration tests
    │   └── test_summaries_unit.py  # Unit tests
    ├── Dockerfile               # Web application container
    ├── entrypoint.sh            # Container startup script
    ├── requirements.txt         # Production dependencies
    ├── requirements-dev.txt     # Development dependencies
    ├── pyproject.toml           # Aerich migration config
    ├── .coveragerc              # Test coverage config
    └── .dockerignore            # Docker build exclusions
    docker-compose.yml           # Multi-container orchestration
```

---

## Docker Setup

### Docker Compose Configuration

The `docker-compose.yml` file orchestrates two services: the web application and the PostgreSQL database.

**docker-compose.yml**
```yaml
services:

  web:
    build: ./project
    command: uvicorn app.main:app --reload --workers 1 --host 0.0.0.0 --port 8000
    volumes:
      - ./project:/usr/src/app
    ports:
      - 8004:8000
    environment:
      - ENVIRONMENT=dev
      - TESTING=0
      - DATABASE_URL=postgres://postgres:postgres@web-db:5432/web_dev
      - DATABASE_TEST_URL=postgres://postgres:postgres@web-db:5432/web_test
    depends_on:
      - web-db

  web-db:
    build:
      context: ./project/db
      dockerfile: Dockerfile
    expose:
      - 5432
    environment:
      - POSTGRES_USER=postgres
      - POSTGRES_PASSWORD=postgres
```

**Key Configuration Points:**

| Setting | Description |
|---------|-------------|
| `build: ./project` | Builds the web service from the project directory |
| `--reload` | Enables hot reloading during development |
| `volumes` | Mounts local code for live updates |
| `ports: 8004:8000` | Maps container port 8000 to host port 8004 |
| `depends_on` | Ensures database starts before web service |
| `expose: 5432` | Makes PostgreSQL available to linked containers |

### Web Application Dockerfile

**project/Dockerfile**
```dockerfile
# pull official base image
FROM python:3.13.3-slim-bookworm

# set working directory
WORKDIR /usr/src/app

# set environment variables
ENV PYTHONDONTWRITEBYTECODE 1
ENV PYTHONUNBUFFERED 1

# install system dependencies
RUN apt-get update \
  && apt-get -y install netcat-traditional gcc postgresql \
  && apt-get clean

# install python dependencies
RUN pip install --upgrade pip
COPY ./requirements.txt .
COPY ./requirements-dev.txt .
RUN pip install -r requirements-dev.txt

# add app
COPY . .

# add entrypoint.sh
COPY ./entrypoint.sh .
RUN chmod +x /usr/src/app/entrypoint.sh

# run entrypoint.sh
ENTRYPOINT ["/usr/src/app/entrypoint.sh"]
```

**Environment Variables Explained:**

| Variable | Purpose |
|----------|---------|
| `PYTHONDONTWRITEBYTECODE=1` | Prevents Python from writing `.pyc` files |
| `PYTHONUNBUFFERED=1` | Ensures Python output is sent directly to terminal |

### Container Entrypoint Script

The entrypoint script ensures the database is ready before starting the application.

**project/entrypoint.sh**
```bash
#!/bin/sh

echo "Waiting for postgres..."

while ! nc -z web-db 5432; do
  sleep 0.1
done

echo "PostgreSQL started"

exec "$@"
```

This script uses `netcat` to poll the database port until PostgreSQL is accepting connections, preventing race conditions during startup.

### Docker Ignore File

**project/.dockerignore**
```
env
.dockerignore
Dockerfile
Dockerfile.prod
```

---

## Database Configuration

### PostgreSQL Dockerfile

**project/db/Dockerfile**
```dockerfile
# pull official base image
FROM postgres:17

# run create.sql on init
ADD create.sql /docker-entrypoint-initdb.d
```

Files placed in `/docker-entrypoint-initdb.d` are automatically executed when the PostgreSQL container initializes.

### Database Initialization Script

**project/db/create.sql**
```sql
CREATE DATABASE web_dev;
CREATE DATABASE web_test;
```

This creates two separate databases:
- `web_dev` - For development
- `web_test` - For running tests in isolation

---

## FastAPI Application Setup

### Main Application Entry Point

**project/app/main.py**
```python
# project/app/main.py


import logging

from fastapi import FastAPI

from app.api import ping, summaries
from app.db import init_db

log = logging.getLogger("uvicorn")


def create_application() -> FastAPI:
    application = FastAPI()
    application.include_router(ping.router)
    application.include_router(
        summaries.router, prefix="/summaries", tags=["summaries"]
    )

    return application


app = create_application()

init_db(app)
```

**Code Breakdown:**

| Component | Purpose |
|-----------|---------|
| `create_application()` | Factory function for creating the FastAPI instance |
| `include_router(ping.router)` | Registers the health check endpoint at root level |
| `include_router(summaries.router, prefix="/summaries")` | Registers summary endpoints under `/summaries` prefix |
| `tags=["summaries"]` | Groups endpoints in OpenAPI documentation |
| `init_db(app)` | Initializes database connection on startup |

---

## Configuration Management

### Settings with Pydantic

**project/app/config.py**
```python
# project/app/config.py

import logging
from functools import lru_cache

from pydantic import AnyUrl
from pydantic_settings import BaseSettings

log = logging.getLogger("uvicorn")


class Settings(BaseSettings):
    environment: str = "dev"
    testing: bool = 0
    database_url: AnyUrl = None


@lru_cache()
def get_settings() -> BaseSettings:
    log.info("Loading config settings from the environment...")
    return Settings()
```

**Key Features:**

| Feature | Description |
|---------|-------------|
| `BaseSettings` | Automatically reads from environment variables |
| `@lru_cache()` | Caches settings to avoid repeated environment reads |
| `AnyUrl` | Validates that `database_url` is a proper URL format |

Environment variables are automatically mapped to settings:
- `ENVIRONMENT` → `settings.environment`
- `TESTING` → `settings.testing`
- `DATABASE_URL` → `settings.database_url`

---

## Database Integration with Tortoise ORM

### Database Connection Setup

**project/app/db.py**
```python
# project/app/db.py


import logging
import os

from fastapi import FastAPI
from tortoise import Tortoise, run_async
from tortoise.contrib.fastapi import register_tortoise

log = logging.getLogger("uvicorn")


TORTOISE_ORM = {
    "connections": {"default": os.environ.get("DATABASE_URL")},
    "apps": {
        "models": {
            "models": ["app.models.tortoise", "aerich.models"],
            "default_connection": "default",
        },
    },
}


def init_db(app: FastAPI) -> None:
    register_tortoise(
        app,
        db_url=os.environ.get("DATABASE_URL"),
        modules={"models": ["app.models.tortoise"]},
        generate_schemas=False,
        add_exception_handlers=True,
    )


async def generate_schema() -> None:
    log.info("Initializing Tortoise...")

    await Tortoise.init(
        db_url=os.environ.get("DATABASE_URL"),
        modules={"models": ["models.tortoise"]},
    )
    log.info("Generating database schema via Tortoise...")
    await Tortoise.generate_schemas()
    await Tortoise.close_connections()


if __name__ == "__main__":
    run_async(generate_schema())
```

**Configuration Explained:**

| Setting | Purpose |
|---------|---------|
| `TORTOISE_ORM` | Configuration dict used by Aerich for migrations |
| `register_tortoise()` | Integrates Tortoise with FastAPI lifecycle |
| `generate_schemas=False` | Disables auto-schema generation (using migrations instead) |
| `add_exception_handlers=True` | Adds proper error handling for DB exceptions |

### Aerich Migration Configuration

**project/pyproject.toml**
```toml
[tool.aerich]
tortoise_orm = "app.db.TORTOISE_ORM"
location = "./migrations"
src_folder = "./."
```

### Initial Migration

**project/migrations/models/0_20211227001140_init.sql**
```python
from tortoise import BaseDBAsyncClient


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
        CREATE TABLE IF NOT EXISTS "textsummary" (
    "id" SERIAL NOT NULL PRIMARY KEY,
    "url" TEXT NOT NULL,
    "summary" TEXT NOT NULL,
    "created_at" TIMESTAMPTZ NOT NULL  DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS "aerich" (
    "id" SERIAL NOT NULL PRIMARY KEY,
    "version" VARCHAR(255) NOT NULL,
    "app" VARCHAR(100) NOT NULL,
    "content" JSONB NOT NULL
);"""


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
        """
```

---

## Data Models

### Tortoise ORM Model

**project/app/models/tortoise.py**
```python
# project/app/models/tortoise.py


from tortoise import fields, models
from tortoise.contrib.pydantic import pydantic_model_creator


class TextSummary(models.Model):
    url = fields.TextField()
    summary = fields.TextField()
    created_at = fields.DatetimeField(auto_now_add=True)

    def __str__(self):
        return self.url


SummarySchema = pydantic_model_creator(TextSummary)
```

**Model Fields:**

| Field | Type | Description |
|-------|------|-------------|
| `id` | Integer (auto) | Primary key, auto-generated |
| `url` | TextField | The URL that was summarized |
| `summary` | TextField | The generated summary text |
| `created_at` | DatetimeField | Timestamp, auto-set on creation |

`pydantic_model_creator(TextSummary)` automatically generates a Pydantic schema from the Tortoise model for API responses.

### Pydantic Schemas

**project/app/models/pydantic.py**
```python
# project/app/models/pydantic.py


from pydantic import AnyHttpUrl, BaseModel


class SummaryPayloadSchema(BaseModel):
    url: AnyHttpUrl


class SummaryResponseSchema(SummaryPayloadSchema):
    id: int


class SummaryUpdatePayloadSchema(SummaryPayloadSchema):
    summary: str
```

**Schema Purposes:**

| Schema | Used For |
|--------|----------|
| `SummaryPayloadSchema` | POST request body (creating new summary) |
| `SummaryResponseSchema` | POST response (returns id and url) |
| `SummaryUpdatePayloadSchema` | PUT request body (updating summary) |

`AnyHttpUrl` ensures only valid HTTP/HTTPS URLs are accepted.

---

## RESTful API Routes

### Health Check Endpoint

**project/app/api/ping.py**
```python
# project/app/api/ping.py
from fastapi import APIRouter, Depends

from app.config import Settings, get_settings

router = APIRouter()


@router.get("/ping")
async def pong(settings: Settings = Depends(get_settings)):
    return {
        "ping": "pong",
        "environment": settings.environment,
        "testing": settings.testing,
    }
```

This endpoint:
- Verifies the service is running
- Shows the current environment configuration
- Demonstrates FastAPI's dependency injection with `Depends(get_settings)`

### CRUD Operations

**project/app/api/crud.py**
```python
# project/app/api/crud.py


from typing import List, Union

from app.models.pydantic import SummaryPayloadSchema, SummaryUpdatePayloadSchema
from app.models.tortoise import TextSummary


async def post(payload: SummaryPayloadSchema) -> int:
    summary = TextSummary(url=payload.url, summary="")
    await summary.save()
    return summary.id


async def get(id: int) -> Union[dict, None]:
    summary = await TextSummary.filter(id=id).first().values()
    if summary:
        return summary
    return None


async def get_all() -> List:
    summaries = await TextSummary.all().values()
    return summaries


async def delete(id: int) -> int:
    summary = await TextSummary.filter(id=id).first().delete()
    return summary


async def put(id: int, payload: SummaryUpdatePayloadSchema) -> Union[dict, None]:
    summary = await TextSummary.filter(id=id).update(
        url=payload.url, summary=payload.summary
    )
    if summary:
        updated_summary = await TextSummary.filter(id=id).first().values()
        return updated_summary
    return None
```

**CRUD Functions:**

| Function | Operation | Returns |
|----------|-----------|---------|
| `post()` | Create new summary | ID of created record |
| `get()` | Read single summary | Summary dict or None |
| `get_all()` | Read all summaries | List of summary dicts |
| `delete()` | Delete a summary | Deletion count |
| `put()` | Update a summary | Updated summary dict or None |

### Summary API Endpoints

**project/app/api/summaries.py**
```python
# project/app/api/summaries.py


from typing import List

from fastapi import APIRouter, BackgroundTasks, HTTPException, Path

from app.api import crud
from app.models.tortoise import SummarySchema
from app.summarizer import generate_summary

from app.models.pydantic import (  # isort:skip
    SummaryPayloadSchema,
    SummaryResponseSchema,
    SummaryUpdatePayloadSchema,
)


router = APIRouter()


@router.post("/", response_model=SummaryResponseSchema, status_code=201)
async def create_summary(
    payload: SummaryPayloadSchema, background_tasks: BackgroundTasks
) -> SummaryResponseSchema:
    summary_id = await crud.post(payload)

    background_tasks.add_task(generate_summary, summary_id, str(payload.url))

    response_object = {"id": summary_id, "url": payload.url}
    return response_object


@router.get("/{id}/", response_model=SummarySchema)
async def read_summary(id: int = Path(..., gt=0)) -> SummarySchema:
    summary = await crud.get(id)
    if not summary:
        raise HTTPException(status_code=404, detail="Summary not found")

    return summary


@router.get("/", response_model=List[SummarySchema])
async def read_all_summaries() -> List[SummarySchema]:
    return await crud.get_all()


@router.delete("/{id}/", response_model=SummaryResponseSchema)
async def delete_summary(id: int = Path(..., gt=0)) -> SummaryResponseSchema:
    summary = await crud.get(id)
    if not summary:
        raise HTTPException(status_code=404, detail="Summary not found")

    await crud.delete(id)

    return summary


@router.put("/{id}/", response_model=SummarySchema)
async def update_summary(
    payload: SummaryUpdatePayloadSchema, id: int = Path(..., gt=0)
) -> SummarySchema:
    summary = await crud.put(id, payload)
    if not summary:
        raise HTTPException(status_code=404, detail="Summary not found")

    return summary
```

**API Endpoints Summary:**

| Method | Endpoint | Description | Response Code |
|--------|----------|-------------|---------------|
| POST | `/summaries/` | Create a new summary | 201 Created |
| GET | `/summaries/{id}/` | Get a specific summary | 200 OK |
| GET | `/summaries/` | Get all summaries | 200 OK |
| DELETE | `/summaries/{id}/` | Delete a summary | 200 OK |
| PUT | `/summaries/{id}/` | Update a summary | 200 OK |

**Key Features:**

- **Background Tasks**: The `generate_summary` function runs asynchronously after the response is sent
- **Path Validation**: `Path(..., gt=0)` ensures IDs are positive integers
- **HTTP Exceptions**: Proper 404 responses when resources aren't found
- **Response Models**: Type-safe response serialization

---

## Running the Application

### Dependencies

**project/requirements.txt**
```
aerich[toml]==0.8.2
aiosqlite==0.19.0
asyncpg==0.30.0
fastapi==0.115.12
gunicorn==22.0.0
httpx==0.28.1
lxml-html-clean==0.4.2
newspaper3k==0.2.8
pydantic-settings==2.8.1
tortoise-orm==0.25.0
uvicorn==0.34.1
```

**project/requirements-dev.txt**
```
black==25.1.0
flake8==7.2.0
isort==6.0.1
pytest==8.3.5
pytest-cov==6.1.1
pytest-xdist==3.6.1

-r requirements.txt
```

### Build and Run

```bash
# Build and start the containers
docker-compose up -d --build

# View logs
docker-compose logs -f

# Apply database migrations
docker-compose exec web aerich upgrade
```

### Run Tests

```bash
# Run all tests
docker-compose exec web python -m pytest

# Run with coverage report
docker-compose exec web python -m pytest --cov=app

# Run tests in parallel
docker-compose exec web python -m pytest -n auto
```

### Access the API

- **API Base URL**: http://localhost:8004
- **Health Check**: http://localhost:8004/ping
- **Interactive Docs**: http://localhost:8004/docs
- **OpenAPI Schema**: http://localhost:8004/openapi.json

### Example API Usage

```bash
# Create a summary
curl -X POST http://localhost:8004/summaries/ \
  -H "Content-Type: application/json" \
  -d '{"url": "https://example.com/article"}'

# Get a summary
curl http://localhost:8004/summaries/1/

# Get all summaries
curl http://localhost:8004/summaries/

# Update a summary
curl -X PUT http://localhost:8004/summaries/1/ \
  -H "Content-Type: application/json" \
  -d '{"url": "https://example.com/article", "summary": "Updated summary"}'

# Delete a summary
curl -X DELETE http://localhost:8004/summaries/1/
```

---

## Summary

In this part of the lab, you've learned how to:

1. **Set up a Dockerized local development environment** with FastAPI and PostgreSQL
2. **Configure Tortoise ORM** for async database operations
3. **Create Pydantic models** for request/response validation
4. **Build RESTful API endpoints** with full CRUD functionality
5. **Use dependency injection** for configuration management
6. **Run the application locally** with Docker Compose

The application now provides a fully functional local development environment for the text summarization API.

---

**Next: [Part 2 - Testing, Code Quality & Deployment](lab2.md)** covers text summarization logic, testing with pytest, code quality tools, GitHub workflows, and AWS EC2 deployment.
