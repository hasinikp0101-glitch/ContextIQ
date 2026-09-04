"""Small, explicit vocabularies and concept links for relevance scoring.

These tables are intentionally simple so judges can inspect why a file
ranked highly. They are not a language model.
"""

from __future__ import annotations

# Multi-word phrases detected before tokenization (longest first).
PHRASES = (
    "environment variable",
    "environment variables",
    "status code",
)

# Terms kept as technical vocabulary (stored lowercase).
TECHNICAL_TERMS = {
    "authentication",
    "authorization",
    "jwt",
    "token",
    "login",
    "logout",
    "password",
    "session",
    "api",
    "http",
    "request",
    "response",
    "database",
    "sql",
    "mongodb",
    "postgresql",
    "postgres",
    "redis",
    "cache",
    "error",
    "exception",
    "bug",
    "test",
    "testing",
    "performance",
    "latency",
    "timeout",
    "configuration",
    "environment",
    "env",
    "cors",
    "middleware",
    "route",
    "endpoint",
    "frontend",
    "backend",
    "react",
    "javascript",
    "typescript",
    "python",
    "fastapi",
    "node",
    "express",
    "auth",
    "query",
    "mongoose",
    "jsonwebtoken",
}

# Related tokens for a concept. Matching is bidirectional in the scorer.
CONCEPT_MAP: dict[str, set[str]] = {
    "jwt": {
        "jwt",
        "jsonwebtoken",
        "token",
        "bearer",
        "auth",
        "authentication",
        "authorize",
        "verifytoken",
        "generatetoken",
    },
    "authentication": {
        "auth",
        "authentication",
        "authorization",
        "authorize",
        "login",
        "logout",
        "password",
        "session",
        "jwt",
        "token",
        "middleware",
        "authenticate",
        "passport",
    },
    "authorization": {
        "authorization",
        "authorize",
        "auth",
        "permission",
        "role",
        "rbac",
    },
    "database": {
        "database",
        "db",
        "sql",
        "query",
        "mongodb",
        "mongoose",
        "postgres",
        "postgresql",
        "redis",
        "sqlite",
        "sqlalchemy",
        "prisma",
        "sequelize",
        "model",
        "repository",
        "schema",
    },
    "api": {
        "api",
        "http",
        "endpoint",
        "route",
        "router",
        "request",
        "response",
        "express",
        "fastapi",
        "cors",
        "server",
        "rest",
    },
    "performance": {
        "performance",
        "slow",
        "latency",
        "timeout",
        "cache",
        "redis",
    },
    "testing": {
        "test",
        "testing",
        "unittest",
        "pytest",
        "spec",
        "assert",
    },
    "configuration": {
        "config",
        "configuration",
        "environment",
        "env",
        "settings",
        "dotenv",
    },
    "http": {
        "http",
        "request",
        "response",
        "api",
        "axios",
        "fetch",
        "requests",
    },
}

# Path/import/symbol tokens that support a primary intent or topic.
DOMAIN_TOKENS: dict[str, set[str]] = {
    "debugging": {
        "error",
        "exception",
        "debug",
        "fail",
        "handler",
    },
    "authentication": CONCEPT_MAP["authentication"] | CONCEPT_MAP["jwt"],
    "performance": CONCEPT_MAP["performance"],
    "testing": CONCEPT_MAP["testing"],
    "configuration": CONCEPT_MAP["configuration"],
    "database": CONCEPT_MAP["database"],
    "api": CONCEPT_MAP["api"],
    "general": set(),
}


def related_tokens(term: str) -> set[str]:
    """Return the term plus any concept-map neighbors."""
    normalized = term.lower().strip()
    related = {normalized}
    if normalized in CONCEPT_MAP:
        related |= CONCEPT_MAP[normalized]
    for key, values in CONCEPT_MAP.items():
        if normalized == key or normalized in values:
            related.add(key)
            related |= values
    return related
