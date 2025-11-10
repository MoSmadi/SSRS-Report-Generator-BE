# SSRS RDL Generator - Quick Start Guide

## 🚀 Quick Start

### 1. Start the Server
```bash
cd /Users/mohammadsmadi/backend
python3 -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

### 2. Test the Endpoint
```bash
curl http://localhost:8000/healthz
# Expected: {"ok":true}
```

### 3. Generate Your First RDL

**Using curl:**
```bash
curl -X POST "http://localhost:8000/report/ssrs-generate" \
  -H "Content-Type: application/json" \
  -d '{
    "sql": "SELECT TOP 10 Id, Name, Price FROM dbo.Products",
    "output_path": "./reports/products.rdl",
    "db_name": "devtang",
    "report_name": "Product List"
  }'
```

**Using Python:**
```python
import requests

response = requests.post(
    "http://localhost:8000/report/ssrs-generate",
    json={
        "sql": "SELECT Id, Name FROM dbo.Products WHERE Price > @MinPrice",
        "output_path": "./reports/products.rdl",
        "db_name": "devtang"
    }
)

result = response.json()
print(f"Saved to: {result['saved_path']}")
```

## 📋 Request Format

```json
{
  "sql": "SELECT ... WHERE ... @Param",
  "output_path": "/path/to/file.rdl",
  "db_name": "database_name",
  "report_name": "Optional Report Title",
  "data_source_name": "Optional DataSource Name",
  "data_set_name": "Optional DataSet Name"
}
```

### Required Fields
- `sql` - Raw T-SQL query (non-empty)
- `output_path` - Path ending in `.rdl`
- `db_name` - Database name (non-empty)

### Optional Fields
- `report_name` - Defaults to "AutoReport"
- `data_source_name` - Defaults to "AutoDataSource"
- `data_set_name` - Defaults to "AutoDataSet"

## ✅ Response Format

**Success (200):**
```json
{
  "status": "success",
  "saved_path": "/absolute/path/to/file.rdl",
  "report_name": "Report Name",
  "data_source": "DataSource Name",
  "data_set": "DataSet Name",
  "fields": [
    {"name": "Id", "rdlType": "System.Int32"},
    {"name": "Name", "rdlType": "System.String"}
  ],
  "parameters": [
    {"name": "MinPrice", "type": "String"}
  ],
  "notes": []
}
```

**Error (400/500):**
```json
{
  "status": "error",
  "message": "Error description"
}
```

## 🔧 Configuration

Edit `.env` file:
```env
SQLSERVER_HOST=your-server.com
SQLSERVER_PORT=1433
SQLSERVER_USER=username
SQLSERVER_PASSWORD=password
```

## 📝 SQL Features

### ✅ Supported
- SELECT queries with JOINs
- WHERE clauses with parameters (@ParamName)
- GROUP BY and aggregations
- ORDER BY
- Subqueries
- CTEs (Common Table Expressions)

### ⚠️ Parameter Detection
- Automatically detects `@ParamName` (single @)
- Ignores `@@SERVERNAME` (double @@)
- All parameters typed as String
- De-duplicates parameters

### 📊 Type Mapping
| SQL Type | RDL Type |
|----------|----------|
| int, smallint, tinyint | System.Int32 |
| bigint | System.Int64 |
| bit | System.Boolean |
| decimal, numeric, money | System.Decimal |
| float, real | System.Double |
| date, datetime, datetime2 | System.DateTime |
| varchar, nvarchar, text | System.String |

## 🎯 Common Use Cases

### Case 1: Simple Data Export
```sql
SELECT * FROM dbo.MyTable
```

### Case 2: Filtered Report
```sql
SELECT * FROM dbo.Orders 
WHERE OrderDate >= @StartDate 
  AND Status = @Status
```

### Case 3: Summary Report
```sql
SELECT 
  Region,
  COUNT(*) AS OrderCount,
  SUM(Amount) AS TotalAmount
FROM dbo.Orders
WHERE OrderDate >= @ReportDate
GROUP BY Region
```

### Case 4: Detail Report with Joins
```sql
SELECT 
  c.CustomerName,
  o.OrderDate,
  p.ProductName,
  oi.Quantity,
  oi.Price
FROM dbo.Customers c
JOIN dbo.Orders o ON c.Id = o.CustomerId
JOIN dbo.OrderItems oi ON o.Id = oi.OrderId
JOIN dbo.Products p ON oi.ProductId = p.Id
WHERE o.OrderDate >= @FromDate
```

## 🐛 Troubleshooting

### Server won't start
```bash
# Check if port is in use
lsof -i :8000

# Use different port
python3 -m uvicorn app.main:app --host 127.0.0.1 --port 8001
```

### Connection errors
```bash
# Test SQL connection
python3 -c "from app.conn import open_connection; conn = open_connection('devtang'); print('Connected!')"
```

### RDL won't open
```bash
# Validate XML
xmllint --noout /path/to/file.rdl

# Check file exists
ls -lh /path/to/file.rdl
```

## 📚 Additional Resources

- Full Documentation: `SSRS_GENERATOR_README.md`
- Test Script: `test_ssrs_api.py`
- Examples: `examples_ssrs_api.py`
- API Docs: http://localhost:8000/docs

## 🔗 Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/healthz` | GET | Health check |
| `/report/ssrs-generate` | POST | Generate RDL |
| `/docs` | GET | API documentation |

## 💡 Tips

1. **Create output directory first:**
   ```bash
   mkdir -p ./reports
   ```

2. **Test with simple query first:**
   ```sql
   SELECT TOP 1 * FROM sys.tables
   ```

3. **Check server logs for errors:**
   Server prints detailed logs in terminal

4. **Restart server after .env changes:**
   Press Ctrl+C and restart uvicorn

5. **Use absolute paths for reliability:**
   ```json
   "output_path": "/tmp/my_report.rdl"
   ```

## ⚡ Quick Tests

```bash
# Health check
curl http://localhost:8000/healthz

# Simple generation
curl -X POST http://localhost:8000/report/ssrs-generate \
  -H "Content-Type: application/json" \
  -d '{"sql":"SELECT 1 AS Test","output_path":"/tmp/test.rdl","db_name":"devtang"}'

# Check generated file
ls -lh /tmp/test.rdl
head -20 /tmp/test.rdl
```

---

**Need Help?** Check the logs, review SSRS_GENERATOR_README.md, or inspect the API docs at `/docs`
