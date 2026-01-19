# Part 2: Testing, Code Quality & AWS EC2 Deployment

In this section, you'll learn about the text summarization logic, comprehensive testing strategies, code quality tools, CI/CD with GitHub Actions, and deploying the application to AWS EC2.

---

## Table of Contents

1. [Project Structure for Production](#project-structure-for-production)
2. [Text Summarization Logic](#text-summarization-logic)
3. [API Endpoints Explanation](#api-endpoints-explanation)
4. [Production Dockerfile](#production-dockerfile)
5. [Code Quality Tools](#code-quality-tools)
6. [GitHub Actions Workflows](#github-actions-workflows)
7. [Testing with Pytest](#testing-with-pytest)
8. [AWS VPC Setup](#aws-vpc-setup)
9. [Subnet Configuration](#subnet-configuration)
10. [Internet Gateway (IGW)](#internet-gateway-igw)
11. [EC2 Instance Setup](#ec2-instance-setup)

---

## Project Structure for Production

```
text-summarization-serving
    project/
    ├── .github/
    │   └── workflows/
    │       └── main.yml              # CI/CD pipeline configuration
    ├── app/
    │   ├── __init__.py
    │   ├── main.py                   # FastAPI application entry point
    │   ├── config.py                 # Configuration management
    │   ├── db.py                     # Database connection setup
    │   ├── summarizer.py             # Text summarization logic
    │   ├── api/
    │   │   ├── __init__.py
    │   │   ├── ping.py               # Health check endpoint
    │   │   ├── summaries.py          # Summary CRUD endpoints
    │   │   └── crud.py               # Database operations
    │   └── models/
    │       ├── __init__.py
    │       ├── tortoise.py           # Tortoise ORM models
    │       └── pydantic.py           # Pydantic schemas
    ├── db/
    │   ├── Dockerfile                # PostgreSQL container config
    │   └── create.sql                # Database initialization
    ├── migrations/
    │   └── models/
    │       └── 0_20211227001140_init.sql
    ├── tests/
    │   ├── __init__.py
    │   ├── conftest.py               # Pytest fixtures
    │   ├── test_ping.py              # Health check tests
    │   ├── test_summaries.py         # Integration tests
    │   └── test_summaries_unit.py    # Unit tests
    ├── Dockerfile                    # Development container
    ├── Dockerfile.prod               # Production container (multi-stage)
    ├── entrypoint.sh                 # Container startup script
    ├── requirements.txt              # Production dependencies
    ├── requirements-dev.txt          # Development dependencies
    ├── pyproject.toml                # Aerich migration config
    ├── .coveragerc                   # Test coverage config
    └── .dockerignore                 # Docker build exclusions
    docker-compose.yml                # Multi-container orchestration
```

**Key Production Files:**

| File | Purpose |
|------|---------|
| `.github/workflows/main.yml` | CI/CD pipeline for automated testing and deployment |
| `Dockerfile.prod` | Multi-stage production build for smaller, secure images |
| `.coveragerc` | Test coverage configuration |
| `requirements-dev.txt` | Development tools (linting, testing) |

---

## Text Summarization Logic

The core functionality of the application is extracting and summarizing content from URLs using Natural Language Processing.

**project/app/summarizer.py**
```python
# project/app/summarizer.py


import nltk
from newspaper import Article

from app.models.tortoise import TextSummary


async def generate_summary(summary_id: int, url: str) -> None:
    article = Article(url)
    article.download()
    article.parse()

    try:
        nltk.data.find("tokenizers/punkt_tab")
    except LookupError:
        nltk.download("punkt_tab")
    finally:
        article.nlp()

    summary = article.summary

    await TextSummary.filter(id=summary_id).update(summary=summary)
```

**How It Works:**

| Step | Description |
|------|-------------|
| 1. Article Download | Uses `newspaper3k` to fetch the web page content |
| 2. Parsing | Extracts the article text from HTML |
| 3. NLTK Setup | Ensures the `punkt_tab` tokenizer is available |
| 4. NLP Processing | Applies natural language processing to generate a summary |
| 5. Database Update | Stores the generated summary in the database |

**Key Libraries:**

| Library | Purpose |
|---------|---------|
| `newspaper3k` | Article extraction from URLs, handles various website formats |
| `nltk` | Natural Language Toolkit for text processing |
| `punkt_tab` | Sentence tokenizer for breaking text into sentences |

This function runs as a **background task**, allowing the API to respond immediately while summarization happens asynchronously.

---

## API Endpoints Explanation

### Endpoint Overview

| Method | Endpoint | Description | Response Code |
|--------|----------|-------------|---------------|
| GET | `/ping` | Health check | 200 OK |
| POST | `/summaries/` | Create a new summary | 201 Created |
| GET | `/summaries/{id}/` | Get a specific summary | 200 OK |
| GET | `/summaries/` | Get all summaries | 200 OK |
| DELETE | `/summaries/{id}/` | Delete a summary | 200 OK |
| PUT | `/summaries/{id}/` | Update a summary | 200 OK |

### Health Check Endpoint

**project/app/api/ping.py**
```python
@router.get("/ping")
async def pong(settings: Settings = Depends(get_settings)):
    return {
        "ping": "pong",
        "environment": settings.environment,
        "testing": settings.testing,
    }
```

**Purpose:**
- Verifies the service is running
- Shows current environment (dev/prod)
- Useful for load balancer health checks

### Create Summary Endpoint

**project/app/api/summaries.py**
```python
@router.post("/", response_model=SummaryResponseSchema, status_code=201)
async def create_summary(
    payload: SummaryPayloadSchema, background_tasks: BackgroundTasks
) -> SummaryResponseSchema:
    summary_id = await crud.post(payload)
    background_tasks.add_task(generate_summary, summary_id, str(payload.url))
    response_object = {"id": summary_id, "url": payload.url}
    return response_object
```

**Flow:**
1. Receives URL in request body
2. Creates database record with empty summary
3. Schedules background task for summarization
4. Returns immediately with ID and URL

### Read Summary Endpoint

```python
@router.get("/{id}/", response_model=SummarySchema)
async def read_summary(id: int = Path(..., gt=0)) -> SummarySchema:
    summary = await crud.get(id)
    if not summary:
        raise HTTPException(status_code=404, detail="Summary not found")
    return summary
```

**Features:**
- `Path(..., gt=0)` validates ID is positive integer
- Returns 404 if summary not found
- Returns full summary object with timestamp

### Update Summary Endpoint

```python
@router.put("/{id}/", response_model=SummarySchema)
async def update_summary(
    payload: SummaryUpdatePayloadSchema, id: int = Path(..., gt=0)
) -> SummarySchema:
    summary = await crud.put(id, payload)
    if not summary:
        raise HTTPException(status_code=404, detail="Summary not found")
    return summary
```

**Requires:**
- Valid URL in payload
- Summary text in payload
- Existing record with given ID

### Delete Summary Endpoint

```python
@router.delete("/{id}/", response_model=SummaryResponseSchema)
async def delete_summary(id: int = Path(..., gt=0)) -> SummaryResponseSchema:
    summary = await crud.get(id)
    if not summary:
        raise HTTPException(status_code=404, detail="Summary not found")
    await crud.delete(id)
    return summary
```

**Behavior:**
- Checks if record exists before deletion
- Returns deleted record data
- Returns 404 if not found

---

## Production Dockerfile

The production Dockerfile uses multi-stage builds for smaller, more secure images.

**project/Dockerfile.prod**
```dockerfile
###########
# BUILDER #
###########

# pull official base image
FROM python:3.13.3-slim-bookworm AS builder

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
RUN pip wheel --no-cache-dir --no-deps --wheel-dir /usr/src/app/wheels -r requirements.txt

# lint
COPY . .
RUN pip install black==25.1.0 flake8==7.2.0 isort==6.0.1
RUN flake8 .
RUN black --exclude=migrations . --check
RUN isort . --check-only


#########
# FINAL #
#########

# pull official base image
FROM python:3.13.3-slim-bookworm

# create directory for the app user
RUN mkdir -p /home/app

# create the app user
RUN addgroup --system app && adduser --system --group app

# create the appropriate directories
ENV HOME=/home/app
ENV APP_HOME=/home/app/web
RUN mkdir $APP_HOME
WORKDIR $APP_HOME

# set environment variables
ENV PYTHONDONTWRITEBYTECODE 1
ENV PYTHONUNBUFFERED 1
ENV ENVIRONMENT prod
ENV TESTING 0

# install system dependencies
RUN apt-get update \
  && apt-get -y install netcat-traditional gcc postgresql \
  && apt-get clean

# install python dependencies
COPY --from=builder /usr/src/app/wheels /wheels
COPY --from=builder /usr/src/app/requirements.txt .
RUN pip install --upgrade pip
RUN pip install --no-cache /wheels/*
RUN pip install "gunicorn==22.0.0"

# add app
COPY . .

# chown all the files to the app user
RUN chown -R app:app $APP_HOME

# change to the app user
USER app

# run gunicorn
CMD gunicorn --bind 0.0.0.0:$PORT app.main:app -k uvicorn.workers.UvicornWorker
```

**Multi-Stage Build Explanation:**

| Stage | Purpose |
|-------|---------|
| **Builder** | Compiles dependencies, runs linting checks |
| **Final** | Contains only runtime dependencies, smaller image |

**Security Features:**

| Feature | Description |
|---------|-------------|
| Non-root user | Runs as `app` user instead of root |
| Minimal dependencies | Only production packages in final image |
| Pre-built wheels | Dependencies compiled in builder stage |

**Production Settings:**

| Setting | Value | Purpose |
|---------|-------|---------|
| `ENVIRONMENT` | prod | Indicates production mode |
| `TESTING` | 0 | Disables test mode |
| `gunicorn` | Process manager | Production-grade WSGI server |
| `UvicornWorker` | ASGI worker | Handles async requests |

---

## Code Quality Tools

### Overview

| Tool | Purpose | Command |
|------|---------|---------|
| **Black** | Code formatter | `black .` |
| **Flake8** | Linter (style guide enforcement) | `flake8 .` |
| **isort** | Import sorter | `isort .` |

### Black - Code Formatter

Black is an opinionated code formatter that enforces a consistent style.

```bash
# Format all files
docker-compose exec web black .

# Check without modifying (CI mode)
docker-compose exec web black . --check

# Exclude directories
docker-compose exec web black --exclude=migrations .
```

**Configuration in pyproject.toml:**
```toml
[tool.black]
line-length = 88
exclude = '''
/(
    migrations
)/
'''
```

### Flake8 - Linter

Flake8 checks code against PEP 8 style guide and finds common errors.

```bash
# Run linting
docker-compose exec web flake8 .

# Show specific error codes
docker-compose exec web flake8 . --show-source
```

**Configuration in setup.cfg or .flake8:**
```ini
[flake8]
max-line-length = 88
exclude = migrations
```

### isort - Import Sorter

isort automatically sorts and organizes imports.

```bash
# Sort imports
docker-compose exec web isort .

# Check without modifying
docker-compose exec web isort . --check-only

# Show diff
docker-compose exec web isort . --diff
```

**Configuration in pyproject.toml:**
```toml
[tool.isort]
profile = "black"
skip = ["migrations"]
```

### Running All Quality Checks

```bash
# Run all checks
docker-compose exec web flake8 .
docker-compose exec web black --exclude=migrations . --check
docker-compose exec web isort . --check-only
```

---

## GitHub Actions Workflows

GitHub Actions automates testing and deployment on every push.

**.github/workflows/main.yml**
```yaml
name: Continuous Integration and Delivery

on: [push]

env:
  IMAGE: ghcr.io/${{ github.repository }}/summarizer

jobs:

  build:
    name: Build Docker Image
    runs-on: ubuntu-latest
    steps:
      - name: Checkout
        uses: actions/checkout@v4
        with:
          ref: main
      - name: Log in to GitHub Packages
        run: echo ${GITHUB_TOKEN} | docker login -u ${GITHUB_ACTOR} --password-stdin ghcr.io
        env:
          GITHUB_TOKEN: ${{ secrets.GITHUB_TOKEN }}
      - name: Pull image
        run: |
          docker pull ${{ env.IMAGE }}:latest || true
      - name: Build image
        run: |
          docker build \
            --cache-from ${{ env.IMAGE }}:latest \
            --tag ${{ env.IMAGE }}:latest \
            --file ./project/Dockerfile.prod \
            "./project"
      - name: Push image
        run: |
          docker push ${{ env.IMAGE }}:latest

  test:
    name: Test Docker Image
    runs-on: ubuntu-latest
    needs: build
    steps:
      - name: Checkout
        uses: actions/checkout@v4
        with:
          ref: main
      - name: Log in to GitHub Packages
        run: echo ${GITHUB_TOKEN} | docker login -u ${GITHUB_ACTOR} --password-stdin ghcr.io
        env:
          GITHUB_TOKEN: ${{ secrets.GITHUB_TOKEN }}
      - name: Pull image
        run: |
          docker pull ${{ env.IMAGE }}:latest || true
      - name: Run container
        run: |
          docker run \
            -d \
            --name fastapi-tdd \
            -e PORT=8765 \
            -e ENVIRONMENT=dev \
            -e DATABASE_URL=sqlite://sqlite.db \
            -e DATABASE_TEST_URL=sqlite://sqlite.db \
            -p 5003:8765 \
            ${{ env.IMAGE }}:latest
      - name: Install requirements
        run: docker exec fastapi-tdd pip install -r requirements-dev.txt
      - name: Pytest
        run: docker exec fastapi-tdd python -m pytest .
      - name: Flake8
        run: docker exec fastapi-tdd python -m flake8 .
      - name: Black
        run: docker exec fastapi-tdd python -m black . --check
      - name: isort
        run: docker exec fastapi-tdd python -m isort . --check-only
```

**Workflow Stages:**

| Stage | Description |
|-------|-------------|
| **Build** | Builds Docker image and pushes to GitHub Container Registry |
| **Test** | Runs pytest, flake8, black, and isort checks |

**Key Features:**

| Feature | Purpose |
|---------|---------|
| `on: [push]` | Triggers on every push to any branch |
| `needs: build` | Test job waits for build job to complete |
| `--cache-from` | Uses previous image layers for faster builds |
| `GITHUB_TOKEN` | Automatic token for authentication |

---

## Testing with Pytest

### Test Configuration

**project/tests/conftest.py**
```python
# project/tests/conftest.py


import os

import pytest
from starlette.testclient import TestClient
from tortoise.contrib.fastapi import register_tortoise

from app.config import Settings, get_settings
from app.main import create_application


def get_settings_override():
    return Settings(testing=1, database_url=os.environ.get("DATABASE_TEST_URL"))


@pytest.fixture(scope="module")
def test_app():
    # set up
    app = create_application()
    app.dependency_overrides[get_settings] = get_settings_override
    with TestClient(app) as test_client:

        # testing
        yield test_client

    # tear down


@pytest.fixture(scope="module")
def test_app_with_db():
    # set up
    app = create_application()
    app.dependency_overrides[get_settings] = get_settings_override
    register_tortoise(
        app,
        db_url=os.environ.get("DATABASE_TEST_URL"),
        modules={"models": ["app.models.tortoise"]},
        generate_schemas=True,
        add_exception_handlers=True,
    )
    with TestClient(app) as test_client:

        # testing
        yield test_client

    # tear down
```

**Test Fixtures:**

| Fixture | Purpose |
|---------|---------|
| `test_app` | Basic test client without database (for unit tests) |
| `test_app_with_db` | Test client with database connection (for integration tests) |

The `dependency_overrides` feature allows injecting test configurations, pointing tests to `web_test` database.

### Health Check Test

**project/tests/test_ping.py**
```python
# project/tests/test_ping.py


def test_ping(test_app):
    response = test_app.get("/ping")
    assert response.status_code == 200
    assert response.json() == {"environment": "dev", "ping": "pong", "testing": True}
```

### Integration Tests

**project/tests/test_summaries.py**
```python
# project/tests/test_summaries.py


import json

import pytest

from app.api import crud, summaries


def test_create_summary(test_app, monkeypatch):
    test_request_payload = {"url": "https://foo.bar"}

    async def mock_post(payload):
        return 1

    monkeypatch.setattr(crud, "post", mock_post)

    from app.api import summaries

    monkeypatch.setattr(summaries, "generate_summary", lambda *args: None)

    response = test_app.post(
        "/summaries/",
        data=json.dumps(test_request_payload),
    )
    assert response.status_code == 201


def test_create_summaries_invalid_json(test_app):
    response = test_app.post("/summaries/", data=json.dumps({}))
    assert response.status_code == 422
    assert response.json() == {
        "detail": [
            {
                "type": "missing",
                "loc": ["body", "url"],
                "msg": "Field required",
                "input": {},
            }
        ]
    }

    response = test_app.post("/summaries/", data=json.dumps({"url": "invalid://url"}))
    assert response.status_code == 422
    assert (
        response.json()["detail"][0]["msg"] == "URL scheme should be 'http' or 'https'"
    )


def test_read_summary(test_app_with_db, monkeypatch):
    def mock_generate_summary(summary_id, url):
        return None

    monkeypatch.setattr(summaries, "generate_summary", mock_generate_summary)

    response = test_app_with_db.post(
        "/summaries/", data=json.dumps({"url": "https://foo.bar"})
    )
    summary_id = response.json()["id"]

    response = test_app_with_db.get(f"/summaries/{summary_id}/")
    assert response.status_code == 200

    response_dict = response.json()
    assert response_dict["id"] == summary_id
    assert response_dict["url"] == "https://foo.bar/"
    assert "summary" in response_dict
    assert response_dict["created_at"]


def test_read_summary_incorrect_id(test_app_with_db):
    response = test_app_with_db.get("/summaries/999/")
    assert response.status_code == 404
    assert response.json()["detail"] == "Summary not found"


def test_read_all_summaries(test_app_with_db, monkeypatch):
    def mock_generate_summary(summary_id, url):
        return None

    monkeypatch.setattr(summaries, "generate_summary", mock_generate_summary)

    response = test_app_with_db.post(
        "/summaries/", data=json.dumps({"url": "https://foo.bar"})
    )
    summary_id = response.json()["id"]

    response = test_app_with_db.get("/summaries/")
    assert response.status_code == 200

    response_list = response.json()
    assert len(list(filter(lambda d: d["id"] == summary_id, response_list))) == 1


def test_remove_summary(test_app_with_db, monkeypatch):
    def mock_generate_summary(summary_id, url):
        return None

    monkeypatch.setattr(summaries, "generate_summary", mock_generate_summary)

    response = test_app_with_db.post(
        "/summaries/", data=json.dumps({"url": "https://foo.bar"})
    )
    summary_id = response.json()["id"]

    response = test_app_with_db.delete(f"/summaries/{summary_id}/")
    assert response.status_code == 200
    assert response.json() == {"id": summary_id, "url": "https://foo.bar/"}


def test_update_summary(test_app_with_db, monkeypatch):
    def mock_generate_summary(summary_id, url):
        return None

    monkeypatch.setattr(summaries, "generate_summary", mock_generate_summary)

    response = test_app_with_db.post(
        "/summaries/", data=json.dumps({"url": "https://foo.bar/"})
    )
    summary_id = response.json()["id"]

    response = test_app_with_db.put(
        f"/summaries/{summary_id}/",
        data=json.dumps({"url": "https://foo.bar/", "summary": "updated!"}),
    )
    assert response.status_code == 200

    response_dict = response.json()
    assert response_dict["id"] == summary_id
    assert response_dict["url"] == "https://foo.bar/"
    assert response_dict["summary"] == "updated!"
    assert response_dict["created_at"]
```

### Unit Tests

**project/tests/test_summaries_unit.py**
```python
# project/tests/test_summaries_unit.py


import json
from datetime import datetime

import pytest

from app.api import crud, summaries


def test_create_summary(test_app, monkeypatch):
    test_request_payload = {"url": "https://foo.bar"}
    test_response_payload = {"id": 1, "url": "https://foo.bar/"}

    async def mock_post(payload):
        return 1

    monkeypatch.setattr(crud, "post", mock_post)

    def mock_generate_summary(summary_id, url):
        return None

    monkeypatch.setattr(summaries, "generate_summary", mock_generate_summary)

    response = test_app.post(
        "/summaries/",
        data=json.dumps(test_request_payload),
    )

    assert response.status_code == 201
    assert response.json() == test_response_payload


def test_read_summary(test_app, monkeypatch):
    test_data = {
        "id": 1,
        "url": "https://foo.bar",
        "summary": "summary",
        "created_at": datetime.utcnow().isoformat(),
    }

    async def mock_get(id):
        return test_data

    monkeypatch.setattr(crud, "get", mock_get)

    response = test_app.get("/summaries/1/")
    assert response.status_code == 200
    assert response.json() == test_data


def test_read_all_summaries(test_app, monkeypatch):
    test_data = [
        {
            "id": 1,
            "url": "https://foo.bar",
            "summary": "summary",
            "created_at": datetime.utcnow().isoformat(),
        },
        {
            "id": 2,
            "url": "https://testdrivenn.io",
            "summary": "summary",
            "created_at": datetime.utcnow().isoformat(),
        },
    ]

    async def mock_get_all():
        return test_data

    monkeypatch.setattr(crud, "get_all", mock_get_all)

    response = test_app.get("/summaries/")
    assert response.status_code == 200
    assert response.json() == test_data


def test_remove_summary(test_app, monkeypatch):
    async def mock_get(id):
        return {
            "id": 1,
            "url": "https://foo.bar",
            "summary": "summary",
            "created_at": datetime.utcnow().isoformat(),
        }

    monkeypatch.setattr(crud, "get", mock_get)

    async def mock_delete(id):
        return id

    monkeypatch.setattr(crud, "delete", mock_delete)

    response = test_app.delete("/summaries/1/")
    assert response.status_code == 200
    assert response.json() == {"id": 1, "url": "https://foo.bar/"}
```

### Coverage Configuration

**project/.coveragerc**
```ini
[run]
omit = tests/*
branch = True
```

### Running Tests

```bash
# Run all tests
docker-compose exec web python -m pytest

# Run with coverage report
docker-compose exec web python -m pytest --cov=app

# Run tests in parallel
docker-compose exec web python -m pytest -n auto

# Run specific test file
docker-compose exec web python -m pytest tests/test_summaries.py

# Run with verbose output
docker-compose exec web python -m pytest -v
```

---

## AWS VPC Setup

### What is a VPC?

A Virtual Private Cloud (VPC) is an isolated virtual network within AWS where you can launch your resources. It provides complete control over your networking environment.

### Creating the VPC

*To be furnished*

---

## Subnet Configuration

### What is a Subnet?

A subnet is a range of IP addresses within your VPC. Subnets allow you to partition your network and control traffic flow.

### Creating the Subnet

*To be furnished*

---

## Internet Gateway (IGW)

### What is an Internet Gateway?

An Internet Gateway enables communication between instances in your VPC and the internet. It provides a target for internet-routable traffic.

### Creating and Attaching the IGW

*To be furnished*

---

## EC2 Instance Setup

### What is EC2?

Amazon Elastic Compute Cloud (EC2) provides scalable computing capacity in the AWS cloud. We'll use an EC2 instance to host our FastAPI application.

### Launching the EC2 Instance

*To be furnished*

### Deploying the Application

*To be furnished*

---

## Summary

In Part 2 of this lab, you've learned how to:

1. **Understand the text summarization logic** using newspaper3k and NLTK
2. **Work with API endpoints** for full CRUD operations
3. **Build production Docker images** with multi-stage builds
4. **Use code quality tools** (Black, Flake8, isort) for consistent code
5. **Set up CI/CD pipelines** with GitHub Actions
6. **Write comprehensive tests** using pytest with fixtures and mocking
7. **Create an AWS VPC** for network isolation
8. **Configure subnets** for resource placement
9. **Set up an Internet Gateway** for internet connectivity
10. **Launch and configure an EC2 instance** to host the application

---
