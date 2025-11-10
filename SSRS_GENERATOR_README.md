# SSRS RDL Generator API

A Python FastAPI service that generates SSRS RDL files from raw SQL queries.

## Overview

This API provides a single endpoint that:
1. Accepts a raw T-SQL query
2. Detects SQL parameters automatically
3. Discovers result set schema via database connection
4. Generates a minimal, valid SSRS 2016+ RDL file
5. Saves the RDL to a specified file path

**Key Features:**
- No Azure OpenAI dependency
- Automatic parameter detection using regex
- Schema discovery via `sp_describe_first_result_set` with fallbacks
- Minimal RDL output (no styling, formatting, or embellishments)
- Default SSRS layout behavior

## Requirements

- Python 3.10+
- FastAPI
- uvicorn
- pyodbc
- SQL Server with ODBC Driver 18

## Installation

1. **Install dependencies:**
```bash
pip install -r requirements.txt
```

The required packages are:
- `fastapi`
- `uvicorn`
- `pyodbc`
- `pydantic`
- `pydantic-settings`
- `python-dotenv`

2. **Configure SQL Server connection:**

Edit the `.env` file in the project root with your SQL Server connection details:

```env
SQLSERVER_HOST=your-sql-host-or-ip
SQLSERVER_PORT=1433
SQLSERVER_USER=your_username
SQLSERVER_PASSWORD=your_password
SQLSERVER_DRIVER=ODBC Driver 18 for SQL Server
```

**Note:** The API uses these stored credentials. You only specify the `db_name` in your requests.

## Running the Service

### Development Mode

```bash
python3 -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
```

### Production Mode

```bash
python3 -m uvicorn app.main:app --host 0.0.0.0 --port 8000
```

The API will be available at `http://localhost:8000`

## API Documentation

Once running, visit:
- Swagger UI: `http://localhost:8000/docs`
- ReDoc: `http://localhost:8000/redoc`

## Endpoint

### POST /report/ssrs-generate

Generates an SSRS RDL file from a raw SQL query.

#### Request Body

```json
{
  "sql": "<raw T-SQL text>",
  "output_path": "<absolute or relative file path to .rdl>",
  "db_name": "<database name, e.g., 'devtang'>",
  "report_name": "Optional report title, default 'AutoReport'",
  "data_source_name": "Optional, default 'AutoDataSource'",
  "data_set_name": "Optional, default 'AutoDataSet'"
}
```

**Required Fields:**
- `sql` - Raw T-SQL query (non-empty)
- `output_path` - File path ending in `.rdl`
- `db_name` - Database name (non-empty)

**Optional Fields:**
- `report_name` - Report title (default: "AutoReport")
- `data_source_name` - Data source name (default: "AutoDataSource")
- `data_set_name` - Dataset name (default: "AutoDataSet")

#### Success Response (200)

```json
{
  "status": "success",
  "saved_path": "<resolved output_path>",
  "report_name": "<final report name>",
  "data_source": "<data source name>",
  "data_set": "<data set name>",
  "fields": [
    {
      "name": "ColumnName",
      "rdlType": "System.String"
    }
  ],
  "parameters": [
    {
      "name": "ParamName",
      "type": "String"
    }
  ],
  "notes": []
}
```

#### Error Response (400/500)

```json
{
  "status": "error",
  "message": "<short explanation>"
}
```

## Examples

### Example 1: Simple Query with Parameters

**Request:**
```bash
curl -X POST "http://localhost:8000/report/ssrs-generate" \
  -H "Content-Type: application/json" \
  -d '{
    "sql": "SELECT TOP 5 Id, CreatedAt, CustomerName FROM dbo.Customers WHERE CreatedAt BETWEEN @From AND @To ORDER BY CreatedAt DESC",
    "output_path": "out/Customers_Last5.rdl",
    "db_name": "devtang"
  }'
```

**Expected Behavior:**
- Detects parameters: `@From`, `@To`
- Discovers columns: `Id` (System.Int32), `CreatedAt` (System.DateTime), `CustomerName` (System.String)
- Creates DataSource with connection to `devtang` database
- Creates DataSet with the SQL query
- Builds a Tablix with 3 columns (header + detail rows)
- Saves to `out/Customers_Last5.rdl`

### Example 2: Aggregation Query

**Request:**
```bash
curl -X POST "http://localhost:8000/report/ssrs-generate" \
  -H "Content-Type: application/json" \
  -d '{
    "sql": "SELECT s.StoreName, SUM(f.Sales) AS Sales FROM dbo.FactSales f JOIN dbo.Stores s ON s.Id=f.StoreId WHERE f.SalesDate >= @Start GROUP BY s.StoreName ORDER BY Sales DESC",
    "output_path": "/tmp/SalesByStore.rdl",
    "db_name": "devtang",
    "report_name": "Sales By Store"
  }'
```

**Expected Behavior:**
- Detects parameter: `@Start`
- Discovers fields: `StoreName` (System.String), `Sales` (System.Decimal)
- Builds minimal table report
- Saves to `/tmp/SalesByStore.rdl`

### Example 3: Using Python requests

```python
import requests

response = requests.post(
    "http://localhost:8000/report/ssrs-generate",
    json={
        "sql": "SELECT ProductId, ProductName, Price FROM Products WHERE CategoryId = @CategoryId",
        "output_path": "reports/Products.rdl",
        "db_name": "mydb",
        "report_name": "Product List"
    }
)

result = response.json()
print(f"Status: {result['status']}")
print(f"Saved to: {result['saved_path']}")
print(f"Fields: {result['fields']}")
print(f"Parameters: {result['parameters']}")
```

## How It Works

### 1. Parameter Detection

Uses regex pattern `(?<!@)@\w+` to find SQL parameters (single `@`, not `@@`).
- De-duplicates while preserving order
- All parameters typed as `String` by default
- Creates both `ReportParameters` and `QueryParameters`

### 2. Schema Discovery

Attempts in order:

**A. Primary Method - sp_describe_first_result_set:**
```sql
EXEC sys.sp_describe_first_result_set @tsql = N'<SQL>'
```
- Reads column names and SQL Server types
- Maps to RDL .NET types

**B. Fallback - Schema-only execution:**
- Uses `SET FMTONLY ON` if supported
- Reads `cursor.description`

**C. Fallback - Heuristic parsing:**
- Parses SELECT list
- Extracts column aliases
- All fields typed as `System.String`
- Adds note: "schema inferred heuristically"

### 3. Type Mapping

SQL Server types map to RDL .NET types:

| SQL Type | RDL Type |
|----------|----------|
| int, smallint, tinyint | System.Int32 |
| bigint | System.Int64 |
| bit | System.Boolean |
| decimal, numeric, money | System.Decimal |
| float, real | System.Double |
| date, datetime, datetime2 | System.DateTime |
| varchar, nvarchar, char, text | System.String |
| (unknown) | System.String |

### 4. RDL Generation

Creates a minimal SSRS 2016+ RDL with:
- One `DataSource` (embedded, no credentials)
- One `DataSet` with the raw SQL
- One `Tablix` with header row and detail row
- `ReportParameters` if SQL parameters detected
- No styling, formatting, or visual embellishments
- Default SSRS layout (1in column width, 0.25in row height)

### 5. Field Name Sanitization

- Only allows A-Z, 0-9, and underscores
- Replaces invalid characters with underscore
- De-duplicates by appending incremental suffixes

## File Structure

```
app/
├── conn.py                 # SQL Server connection utilities
├── schema_discovery.py     # Parameter detection and schema discovery
├── rdl_builder.py          # RDL XML generation
├── ssrs_api.py             # FastAPI endpoint implementation
└── main.py                 # Application entry point (includes router)
```

## Configuration

### Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `SQLSERVER_HOST` | SQL Server hostname or IP | (required) |
| `SQLSERVER_PORT` | SQL Server port | 1433 |
| `SQLSERVER_USER` | SQL Server username | (required) |
| `SQLSERVER_PASSWORD` | SQL Server password | (required) |
| `SQLSERVER_DRIVER` | ODBC driver name | ODBC Driver 18 for SQL Server |
| `SERVER_HOST` | API server host | 0.0.0.0 |
| `SERVER_PORT` | API server port | 8000 |
| `LOG_LEVEL` | Logging level | INFO |

### Connection Security

This is a **demo-grade** implementation:
- Credentials stored in `.env` file
- No credential rotation
- No path sandboxing
- No authentication on API endpoints
- Connection string includes `TrustServerCertificate=yes` and `Encrypt=no`

**Do not use in production without proper security hardening.**

## Testing

### Health Check

```bash
curl http://localhost:8000/healthz
```

Expected: `{"ok": true}`

### Test RDL Generation

1. Create a test database with sample data
2. Use the examples above to generate RDL files
3. Open the generated `.rdl` files in:
   - Power BI Report Builder
   - SQL Server Data Tools (SSDT)
   - Visual Studio with SSRS extensions

### Validation Checklist

- ✅ RDL opens in Report Builder/SSDT without errors
- ✅ Report shows correct columns
- ✅ Parameters prompt correctly (if present)
- ✅ Report runs and displays data when pointed at a live SSRS server
- ✅ No styles or formatting applied (minimal defaults)

## Troubleshooting

### Connection Errors

**Problem:** `Failed to connect to database`

**Solutions:**
- Verify `SQLSERVER_HOST`, `SQLSERVER_PORT`, `SQLSERVER_USER`, and `SQLSERVER_PASSWORD` in `.env`
- Ensure SQL Server allows remote connections
- Check firewall rules
- Verify ODBC Driver 18 is installed: `odbcinst -q -d`

### Schema Discovery Issues

**Problem:** `Failed to discover any fields`

**Solutions:**
- Ensure the SQL query is valid T-SQL
- Check if the database user has permissions to execute the query
- Look for `"schema inferred heuristically"` in response notes
- If using temp tables, the heuristic fallback will be used

### RDL Validation Errors

**Problem:** RDL doesn't open in Report Builder

**Solutions:**
- Check the generated RDL is valid XML: `xmllint --noout file.rdl`
- Ensure field names don't contain special characters
- Verify namespace is `http://schemas.microsoft.com/sqlserver/reporting/2016/01/reportdefinition`

## Limitations

This is a minimal implementation for demo purposes:

- ❌ No security or authentication
- ❌ No Azure OpenAI integration
- ❌ No styling or formatting
- ❌ No number/date formats
- ❌ No conditional formatting
- ❌ No page headers/footers
- ❌ No charts or visualizations
- ❌ No totals or aggregations in Tablix
- ❌ No multi-value parameters
- ❌ No parameter validation or available values
- ❌ All parameters typed as String
- ✅ Pure SQL-based RDL generation
- ✅ Automatic parameter and schema detection
- ✅ Valid, minimal SSRS reports

## License

This is demonstration code. Use at your own risk.

## Support

For issues or questions, check:
- API documentation: `http://localhost:8000/docs`
- Application logs for detailed error messages
- SQL Server error logs for connection issues
