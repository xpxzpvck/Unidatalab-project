FROM python:3.13-slim-bookworm

ARG ENVIRONMENT=development

ENV ENVIRONMENT=${ENVIRONMENT} \
  PYTHONFAULTHANDLER=1 \
  PYTHONUNBUFFERED=1 \
  PYTHONHASHSEED=random \
  PIP_NO_CACHE_DIR=off \
  PIP_DISABLE_PIP_VERSION_CHECK=on \
  PIP_DEFAULT_TIMEOUT=100 \
  POETRY_NO_INTERACTION=1 \
  POETRY_VIRTUALENVS_CREATE=false \
  POETRY_CACHE_DIR='/var/cache/pypoetry' \
  POETRY_HOME='/opt/poetry' \
  POETRY_VERSION=1.7.1

ENV PATH="$POETRY_HOME/bin:$PATH"

RUN apt-get update \
    && apt-get install -y --no-install-recommends curl \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

RUN curl -sSL https://install.python-poetry.org | python3 -

WORKDIR /code
COPY poetry.lock pyproject.toml /code/

RUN poetry install $(test "$ENVIRONMENT" = production && echo "--only=main") --no-interaction --no-ansi

COPY . /code

CMD ["python", "app/main.py"]