# ContextForge

> AI doesn't need more context. It needs the right context.

ContextForge is an AI-powered developer context optimization layer that sits between a codebase and an LLM. Instead of sending an entire repository to an AI model, ContextForge analyzes the developer's question, identifies relevant parts of the codebase, selects context within a token budget, compresses unnecessary content, measures the optimization, and sends the resulting context to an LLM through Featherless.ai.

## Problem

AI-assisted debugging often requires providing an LLM with repository context. Sending the entire codebase can introduce irrelevant files, excessive token usage, higher inference costs, slower processing, and important files being buried in noise.

The same repository also requires different context depending on the developer's question.

The problem is not giving AI more context. It is giving AI the right context.

## Solution

ContextForge creates a query-aware context pipeline that determines which parts of a repository are most useful for a specific developer question.

```text
Repository
    |
    v
Repository Scanner
    |
    v
File Filter
    |
    v
Code Structure Analyzer
    |
    v
Query / Intent Analyzer
    |
    v
Relevance Scoring
    |
    v
Token-Budget Context Selection
    |
    v
Context Compression
    |
    v
Token & Cost Metrics
    |
    v
Featherless.ai
    |
    v
AI Diagnosis

How It Works
1. Repository Scanning

ContextForge recursively scans the target repository and identifies source, configuration, test, documentation, and other supported files.

Common repository noise such as Git metadata, virtual environments, dependency directories, build output, caches, compiled files, and lock files is excluded.

2. File Filtering

The filtering stage removes unnecessary or unsafe content before deeper analysis.

This includes binary files, media files, generated files, build artifacts, cache files, oversized files, unsupported files, and sensitive environment files.

3. Code Structure Analysis

ContextForge extracts structural information from supported source files, including:

Imports
Functions
Classes
Symbols
Exports
Line counts
Syntax errors

Python analysis uses the Python AST, while JavaScript and TypeScript use lightweight structural analysis.

4. Query and Intent Analysis

The developer's question is analyzed to identify relevant:

Keywords
Technical terms
Intent
Actions
Topics

For example:

Why is the Google OAuth login failing?

can be interpreted as a debugging query related to authentication and OAuth.

5. Relevance Scoring

Candidate files are ranked using multiple signals:

File path relevance
Import relationships
Symbol matches
Query term matches
Query intent
File role

The resulting scores determine which files are most likely to contain useful debugging context.

6. Token-Budget Selection

ContextForge selects relevant files while respecting a configurable token budget.

Files that have no meaningful relevance or cannot fit within the available budget are excluded with an explanation.

7. Context Compression

Selected context is processed to remove unnecessary content such as license boilerplate, copyright boilerplate, pure comments, excessive blank lines, and trailing whitespace while preserving useful code structure.

8. Optimization Metrics

ContextForge measures the resulting optimization, including:

Files analyzed
Files selected
Files excluded
Original tokens
Optimized tokens
Tokens saved
Token reduction percentage
Compression ratio
Character savings
Line savings
9. LLM Diagnosis

The optimized context and developer query are sent through the backend to Featherless.ai.

The resulting AI diagnosis is displayed in the ContextForge dashboard alongside the selected context and optimization metrics.

Key Features
Query-aware repository context selection
Code-aware relevance scoring
Token-budget-aware selection
Deterministic context optimization
Context compression
Token and cost metrics
Selected and excluded file explanations
Optimized context inspection
Featherless.ai LLM integration
Developer-focused dashboard
Backend API with typed request and response models
Sensitive environment file filtering
Architecture
                    Developer
                        |
                        v
              React + TypeScript
                  Dashboard
                        |
                        v
                     FastAPI
                     Backend
                        |
          +-------------+-------------+
          |                           |
          v                           v
   ContextForge Engine           LLM Adapter
          |                           |
          v                           v
   Repository Scanner           Featherless.ai
          |
          v
      File Filter
          |
          v
     Code Analyzer
          |
          v
     Query Analyzer
          |
          v
    Relevance Scorer
          |
          v
    Context Selector
          |
          v
      Compressor
          |
          v
     Metrics Engine
          |
          v
      LLM Adapter
Tech Stack
Frontend
React
TypeScript
Vite
Tailwind CSS
Lucide React
Backend
Python
FastAPI
Pydantic
Uvicorn
Code Analysis
Python AST
Lightweight JavaScript and TypeScript structural analysis
Context Optimization
Deterministic relevance scoring
Token-budget-aware selection
Rule-based context compression
tiktoken
AI
Featherless.ai
OpenAI-compatible API
Testing
Pytest
API integration tests
Pipeline component tests
Project Structure
ContextIQ/
├── backend/
│   ├── app/
│   │   ├── analyzer/
│   │   ├── api/
│   │   ├── compressor/
│   │   ├── llm/
│   │   ├── metrics/
│   │   ├── optimizer/
│   │   ├── relevance/
│   │   └── scanner/
│   ├── tests/
│   ├── requirements.txt
│   └── .env.example
│
├── frontend/
│   ├── src/
│   │   ├── api/
│   │   ├── components/
│   │   └── utils/
│   ├── package.json
│   └── vite.config.ts
│
├── samples/
├── README.md
├── LICENSE
└── .gitignore
API
Health Check
GET /api/health

Example response:

{
  "status": "healthy",
  "service": "ContextForge API",
  "version": "0.1.0"
}

Analyze Repository
POST /api/projects/analyze

Request:

{
  "project_path": "/path/to/project"
}

The endpoint returns repository statistics and code analysis information.

Optimize Context
POST /api/context/optimize

Request:

{
  "project_path": "/path/to/project",
  "query": "Why is the Google OAuth login failing?",
  "token_budget": 3000
}

The response contains query analysis, selected files, excluded files, optimized context, and optimization metrics.

Ask LLM
POST /api/llm/ask

Request:

{
  "optimized_context": "...",
  "query": "Why is the Google OAuth login failing?"
}

The backend sends the optimized context to Featherless.ai and returns the resulting AI diagnosis.

Local Development
Prerequisites
Python 3.x
Node.js 18+
npm
Git
Featherless.ai API key
Backend
cd backend
python -m venv .venv

Windows PowerShell:

.\.venv\Scripts\Activate.ps1

Install dependencies:

pip install -r requirements.txt

Create a .env file from .env.example and configure the Featherless API key.

Start the backend:

uvicorn app.main:app --reload --port 8000

Backend:

http://127.0.0.1:8000
Frontend

Open another terminal:

cd frontend
npm install
npm run dev

Frontend:

http://localhost:5173
Testing

Run the backend test suite:

cd backend
.\.venv\Scripts\Activate.ps1
python -m pytest

The test suite covers repository scanning, file filtering, code analysis, query analysis, relevance scoring, context selection, compression, metrics, API endpoints, and LLM integration.

Example Workflow

ContextForge can analyze an existing codebase without modifying the target repository.

For example, given a Flask application:

flask-example/
├── webapp/
│   ├── app/
│   │   ├── api/
│   │   ├── dao/
│   │   ├── model/
│   │   ├── oauth/
│   │   └── util/
│   └── tests/
└── README.md

A developer can ask:

Why is the Google OAuth login failing?

ContextForge analyzes the repository and prioritizes files related to OAuth and authentication.

A different question such as:

Why is the user API returning the wrong user when fetching by ID?

produces a different context selection.

This demonstrates the central concept:

The same repository does not require the same context for every question.

Security

ContextForge excludes sensitive environment files such as:

.env
.env.local
.env.development
.env.production
.env.test

The Featherless API key is stored only on the backend and is never exposed to the frontend.

Local environment files are excluded from version control.

Why ContextForge?

ContextForge is not a generic chatbot or repository summarizer.

It focuses on the context-selection problem in AI-assisted software development.

Traditional approach:

Repository
    |
    v
Send everything
    |
    v
LLM

ContextForge:

Repository
    |
    v
Understand
    |
    v
Filter
    |
    v
Analyze
    |
    v
Rank
    |
    v
Select
    |
    v
Compress
    |
    v
Measure
    |
    v
LLM

The process is observable and measurable. Developers can inspect:

Which files were selected
Why files were selected
Which files were excluded
Why files were excluded
How the token budget was used
How many tokens were saved
What optimized context was sent to the model
Current Limitations
Deterministic relevance scoring rather than a learned ranking model
Lightweight JavaScript and TypeScript structural analysis
Rule-based compression
Limited language coverage
Local repository path input
No persistent project database
No IDE extension
Future Scope

Potential improvements include:

Embedding-based semantic retrieval
AST-based dependency graphs
LLM-assisted relevance re-ranking
Git diff-aware context selection
Advanced context compression
Additional programming language support
VS Code integration

Hackathon

Built for Build by Sunset 2026 at SNIST.

ContextForge was conceived and developed specifically for the hackathon and uses Featherless.ai as its LLM inference layer.

Team

Hasya
Hasini
Rajeswari

## Submission Resources

- [Project Drive Folder](https://drive.google.com/drive/folders/1wPqrt9udkGOSd_a_YJVRgsDt0n3K_p7w?usp=sharing)

License

This project is licensed under the MIT License.

See LICENSE for details.