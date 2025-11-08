# Natural Language to SSRS Backend

This service converts natural-language report requests into SQL Server queries, generates RDL report definitions, and publishes them to SQL Server Reporting Services (SSRS).

## Features
- FastAPI application exposing endpoints for intent inference, SQL generation, previewing results, and publishing SSRS reports.
- Jinja-powered RDL builder with optional chart support.
- Azure OpenAI integration (optional) for improved term-to-column mapping.
- SQL Server catalog helpers for shape validation and sampling.
- SOAP + REST clients for SSRS ReportService2010 and REST APIs.
- JSON-structured logging for traceable requests.

## Getting Started
1. Create and activate a virtual environment.
   ```bash
   python -m venv .venv
   source .venv/bin/activate
   ```
2. Install dependencies.
   ```bash
   pip install -r requirements.txt
   ```
3. Copy the example environment file and fill in credentials.
   ```bash
   cp .env.example .env
   ```
4. Run the API.
   ```bash
   uvicorn app.main:app --host ${SERVER_HOST:-0.0.0.0} --port ${SERVER_PORT:-8000}
   ```

### SQL Server connectivity
Set the same environment block used by the Node backend: `SQLSERVER_HOST`, `SQLSERVER_DATABASE`, `SQLSERVER_USER`, `SQLSERVER_PASSWORD`, and (optionally) `SQLSERVER_PORT` which defaults to `1433`. Toggle TLS options via `SQLSERVER_ENCRYPT` and `SQLSERVER_TRUST_CERT` (both default to `true`). The backend builds a standard `pyodbc` connection string from those values (or uses `SQLSERVER_CONN_STR` directly), so make sure the Microsoft ODBC Driver 18 for SQL Server (`msodbcsql18`) is installed on the host/container. The shared data source referenced in SSRS must already exist.

### SSRS requirements
- An SSRS instance reachable from this service.
- A shared data source at the path specified by `SHARED_DS_PATH`.
- SOAP endpoint accessible at `SSRS_SOAP_WSDL`.

## Example requests
```bash
# Health check
curl http://localhost:8000/healthz

# List customer databases
curl http://localhost:8000/report/customerDatabases

# Infer mappings from natural language
curl -X POST http://localhost:8000/report/inferFromNaturalLanguage \ 
  -H "Content-Type: application/json" \ 
  -d '{"db":"DemoDW","title":"Sales Trend","text":"Show monthly sales by region"}'

# Generate SQL
curl -X POST http://localhost:8000/report/generateSQL \ 
  -H "Content-Type: application/json" \ 
  -d '{"db":"DemoDW","mapping":[],"spec":{"metrics":["Sales"],"dimensions":["Region"]}}'

# Preview (expects actual SQL)
curl -X POST http://localhost:8000/report/preview \ 
  -H "Content-Type: application/json" \ 
  -d '{"db":"DemoDW","sql":"SELECT 1 AS Value","params":{},"limit":20}'

# Publish report (example payload skeleton)
curl -X POST http://localhost:8000/report/publishReport \ 
  -H "Content-Type: application/json" \ 
  -d @publish.json
```

## Testing
Run the tests with pytest:
```bash
pytest
```
