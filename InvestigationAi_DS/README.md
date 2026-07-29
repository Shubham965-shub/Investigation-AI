# InvestigationAI

A FastAPI backend that provides an agentic search service over quality and deviation data. It uses LangGraph to orchestrate keyword search, semantic (vector) search, AI reranking, and natural-language answer synthesis with citations. Data is stored in PostgreSQL with pgvector.

## Project structure

```
InvestigationAI/
├── .env.example          # Environment template (copy to .env)
|── src
    ├── config/               # Shared configuration
    │   ├── config.yaml       # Table names, columns, search limits
    │   └── settings.py       # Loads from .env
    ├── prompts/              # LLM prompt templates
    │   └── search_agent/
            ├── config.yaml       # Table names, columns, search limits
    │   └── settings.py
    └── agents/
        └── search_agent/
            ├── requirements.txt
            ├── src/
            │   ├── main.py   # Entry point (run with: python -m src.main)
            │   ├── api/      # FastAPI routes and app
            │   ├── db/       # PostgreSQL connection pool
            │   ├── graph/    # LangGraph search pipeline
            │   ├── llm/     # OpenAI client
            │   └── search/   # Keyword, semantic, rerank
        └── tests/
```

## Prerequisites

- Python 3.12+
- PostgreSQL with pgvector extension
- OpenAI API key

## Installation

### 1. Clone and create virtual environment

```bash
cd InvestigationAI
python -m venv .venv
source .venv/bin/activate   # On Windows: .venv\Scripts\activate
pip install -r agents/search_agent/requirements.txt
```

### 2. Database setup

Create the database and restore the data if backup available:

```bash
createdb invest_AI
pg_restore -d invest_AI Data_bkp.backup
```

Install pgvector and create the extension:

```bash
brew install pgvector
psql -d invest_AI -c "CREATE EXTENSION IF NOT EXISTS vector;"
```

### 3. Configuration

Copy the environment template and configure:

```bash
cp .env.example .env
```

Edit `.env` with your database credentials, `OPENAI_API_KEY`, and server settings. Customize `config/config.yaml` if your database schema differs from the defaults.

## Usage

Start the server in the virtual environment:

```bash
cd agents/Search_agent
python -m src.main
```

The API will be available at `http://localhost:8000`. Interactive docs at `http://localhost:8000/docs`.

## API Endpoints

### Search Agent
| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/search` | Agentic search pipeline (analyze → search → rerank → synthesize) |
| POST | `/api/cummulative_summary` | Cumulative summary for deviation IDs |
| POST | `/summary/root_cause_synthesizer` | Root cause summaries |
| POST | `/summary/capa_synthesizer` | CAPA (Corrective/Preventive Action) summaries |
| POST | `/summary/er_synthesizer` | Event record summaries |

### Problem Statement Evaluation
| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/ps/evaluate` | Evaluate problem statement quality and get improvement suggestions |
| POST | `/ps/generate_immediate_actions` | Generate immediate actions based on problem statement |
| POST | `/ps/extract/evaluate` | Extract and evaluate problem statement from DOCX file |
| POST | `/ps/v2/generate` | **V2 API** - Generate structured problem statement from trackwise fields |

### Critique Agent
| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/critique/critique_rci_plan` | Critique RCI plan with batch processing |
| POST | `/questionnaire/generate_questionnaire` | Generate questionnaire based on problem statement |

## Testing

### Run All Tests

```bash
# Run all tests
pytest tests/ -v

# Run with coverage report
pytest tests/ --cov=src/agents --cov-report=html

# Run specific test file
pytest tests/test_search_agent.py -v

# Run specific test class
pytest tests/test_critique_agent.py::TestCritiqueRCIPlanEndpoint -v

# Run with detailed output
pytest tests/ -vv --tb=long
```

### Test Structure

Tests are organized by agent type:
- `tests/conftest.py` - Shared fixtures and configuration
- `tests/test_search_agent.py` - Search agent API tests (~30 test cases)
- `tests/test_critique_agent.py` - Critique agent API tests (~20 test cases)
- `tests/test_problem_statement_evaluation.py` - PS evaluation V1 tests (~25 test cases)
- `tests/test_problem_statement_evaluation_v2.py` - PS evaluation V2 tests (~25 test cases)

Total: 100+ comprehensive test cases covering:
- Valid request handling
- Invalid input validation
- Edge cases and boundary conditions
- Error handling
- Response structure validation

### Problem Statement Evaluation V2 API

The V2 API provides structured problem statement generation from trackwise fields. Instead of free-text input, it takes structured event data and generates comprehensive problem statements.

**Supported Event Types:**
- Deviation
- OOS (Out of Specification)
- OOT (Out of Trend)
- Market Complaint

**Request Example:**

```bash
curl -X POST "http://localhost:8000/ps/v2/generate" \
  -H "Content-Type: application/json" \
  -d '{
    "event_type": "Deviation",
    "trackwise_fields": {
      "title": "Rough tablet surface",
      "observation_date": "2024-01-15",
      "failure_duration": "2 hours",
      "product_material_name": "Ranitidine Tablets 150mg",
      "description": "Rough surfaces observed on tablet coating during inspection",
      "observed_by": "IPQA Personnel",
      "observation_time": "10:30:00",
      "is_microbial_em_failure": false,
      "responsible_department": "QA"
    }
  }'
```

**Response Example:**

```json
{
  "event_type": "Deviation",
  "problem_statement": "Rough tablet surface. During in-process inspection on 2024-01-15 IPQA personnel observed an issue on Ranitidine Tablets 150mg. Rough surfaces observed on tablet coating during inspection. The issue persisted for: 2 hours.",
  "summary": "Rough tablet surface. During in-process inspection on 2024-01-15 IPQA personnel observed an issue on Ranitidine Tablets 150mg. Rough surfaces observed on...",
  "severity_level": "Medium",
  "key_findings": [
    "Description: Rough surfaces observed on tablet coating during inspection",
    "Observed on: 2024-01-15",
    "Product/Material: Ranitidine Tablets 150mg"
  ]
}
```

**Trackwise Fields by Event Type:**

See the detailed documentation in [Problem Statement Evaluation V2 Schemas](src/agents/problem_statement_evaluation/v2/api/schemas.py) for complete field definitions.



