# QA Verification Pack

This pack verifies the FastAPI backend end-to-end and ensures the public contracts remain stable.

## Setup
1. Copy the environment template and provide real values.
   ```bash
   cd qa
   cp .env.example .env
   # edit .env as needed
   ```
2. Create/activate a Python 3.10+ environment with `requests` and `pytest` installed.

## Usage
- `make smoke`
  - Loads `.env` and runs `smoke_check.py` for a sequential sanity sweep:
    1. Lists customer databases.
    2. Infers intent from NL text.
    3. Generates SQL.
    4. Runs a preview query.
    5. Attempts to publish a report.
  - If SSRS is unreachable the script reports a soft warning (`SSRS unavailable`) but still exits 0 as long as request payload validation passes.
- `make contracts`
  - Executes pytest-based contract tests in `contract_tests/` verifying response shapes and error envelopes.
- `make all`
  - Runs smoke then contracts.

## Postman Collection
Import `postman/ReportBuilder_BE.postman_collection.json` into Postman. The collection uses variables `API_BASE`, `DB`, `TITLE`, etc., to chain requests. Each request stores useful artifacts (SQL, parameters, columns) for subsequent steps. On publish it prints the render URL in the console.

## Interpreting Results
- **Smoke tests fail early** if required endpoints are missing or return unexpected data. Review the printed JSON payloads for mismatches.
- **Contract tests** fail if responses deviate from the documented schemas or if negative cases are handled incorrectly.
- **SSRS errors**: If the backend returns an SSRS connectivity error, smoke tests mark the publish step as a warning, while contract tests xfail the SSRS portion (if enabled).

Happy testing!
