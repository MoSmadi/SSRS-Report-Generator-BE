#!/usr/bin/env python3
"""
Example: Using the SSRS RDL Generator API

This script shows practical examples of generating SSRS RDL files from SQL queries.
"""

import requests
import json
from pathlib import Path

# Configure the API endpoint
API_URL = "http://localhost:8000/report/ssrs-generate"


def generate_rdl(sql, output_path, db_name, report_name=None):
    """
    Generate an SSRS RDL file from a SQL query.
    
    Args:
        sql: Raw T-SQL query string
        output_path: Path where the .rdl file will be saved
        db_name: Database name to connect to
        report_name: Optional report title
        
    Returns:
        Response dictionary or None if failed
    """
    payload = {
        "sql": sql,
        "output_path": output_path,
        "db_name": db_name
    }
    
    if report_name:
        payload["report_name"] = report_name
    
    try:
        response = requests.post(API_URL, json=payload, timeout=30)
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        print(f"Error: {e}")
        if hasattr(e, 'response') and e.response is not None:
            print(f"Response: {e.response.text}")
        return None


def example_1_simple_query():
    """Example 1: Simple query without parameters"""
    print("\n" + "=" * 70)
    print("Example 1: Simple Query (No Parameters)")
    print("=" * 70)
    
    sql = """
    SELECT TOP 10
        ProductId,
        ProductName,
        Category,
        Price,
        InStock
    FROM dbo.Products
    ORDER BY Price DESC
    """
    
    result = generate_rdl(
        sql=sql,
        output_path="./output/products_report.rdl",
        db_name="devtang",
        report_name="Top Products"
    )
    
    if result:
        print(f"✅ Success!")
        print(f"   File saved: {result['saved_path']}")
        print(f"   Fields discovered: {[f['name'] for f in result['fields']]}")
        print(f"   Field types: {[f['rdlType'] for f in result['fields']]}")


def example_2_parameterized_query():
    """Example 2: Query with date parameters"""
    print("\n" + "=" * 70)
    print("Example 2: Parameterized Query")
    print("=" * 70)
    
    sql = """
    SELECT 
        OrderId,
        CustomerId,
        OrderDate,
        TotalAmount,
        Status
    FROM dbo.Orders
    WHERE OrderDate BETWEEN @StartDate AND @EndDate
        AND Status = @Status
    ORDER BY OrderDate DESC
    """
    
    result = generate_rdl(
        sql=sql,
        output_path="./output/orders_report.rdl",
        db_name="devtang",
        report_name="Orders Report"
    )
    
    if result:
        print(f"✅ Success!")
        print(f"   File saved: {result['saved_path']}")
        print(f"   Parameters detected: {[p['name'] for p in result['parameters']]}")
        print(f"   Fields: {len(result['fields'])}")


def example_3_aggregation_query():
    """Example 3: Aggregation query with GROUP BY"""
    print("\n" + "=" * 70)
    print("Example 3: Aggregation Query")
    print("=" * 70)
    
    sql = """
    SELECT 
        s.StoreName,
        s.Region,
        COUNT(DISTINCT o.OrderId) AS OrderCount,
        SUM(o.TotalAmount) AS TotalRevenue,
        AVG(o.TotalAmount) AS AverageOrderValue
    FROM dbo.Orders o
    INNER JOIN dbo.Stores s ON o.StoreId = s.Id
    WHERE o.OrderDate >= @FromDate
    GROUP BY s.StoreName, s.Region
    HAVING SUM(o.TotalAmount) > @MinRevenue
    ORDER BY TotalRevenue DESC
    """
    
    result = generate_rdl(
        sql=sql,
        output_path="./output/sales_by_store.rdl",
        db_name="devtang",
        report_name="Sales by Store"
    )
    
    if result:
        print(f"✅ Success!")
        print(f"   File saved: {result['saved_path']}")
        print(f"   Parameters: {[p['name'] for p in result['parameters']]}")
        print(f"   Aggregated fields: {[f['name'] for f in result['fields']]}")


def example_4_complex_join():
    """Example 4: Complex query with multiple joins"""
    print("\n" + "=" * 70)
    print("Example 4: Complex Join Query")
    print("=" * 70)
    
    sql = """
    SELECT 
        c.CustomerName,
        c.Email,
        o.OrderId,
        o.OrderDate,
        p.ProductName,
        oi.Quantity,
        oi.UnitPrice,
        (oi.Quantity * oi.UnitPrice) AS LineTotal
    FROM dbo.Customers c
    INNER JOIN dbo.Orders o ON c.Id = o.CustomerId
    INNER JOIN dbo.OrderItems oi ON o.Id = oi.OrderId
    INNER JOIN dbo.Products p ON oi.ProductId = p.Id
    WHERE o.OrderDate >= @ReportStartDate
        AND c.Region = @Region
    ORDER BY o.OrderDate DESC, c.CustomerName
    """
    
    result = generate_rdl(
        sql=sql,
        output_path="./output/customer_orders_detail.rdl",
        db_name="devtang",
        report_name="Customer Orders Detail"
    )
    
    if result:
        print(f"✅ Success!")
        print(f"   File saved: {result['saved_path']}")
        print(f"   Detected {len(result['parameters'])} parameters")
        print(f"   Detected {len(result['fields'])} fields")


def example_5_custom_data_source():
    """Example 5: Custom data source and dataset names"""
    print("\n" + "=" * 70)
    print("Example 5: Custom Data Source Names")
    print("=" * 70)
    
    sql = "SELECT EmployeeId, FullName, Department, Salary FROM dbo.Employees WHERE Salary > @MinSalary"
    
    payload = {
        "sql": sql,
        "output_path": "./output/employees_report.rdl",
        "db_name": "devtang",
        "report_name": "Employee List",
        "data_source_name": "HRDataSource",
        "data_set_name": "EmployeeDataSet"
    }
    
    try:
        response = requests.post(API_URL, json=payload, timeout=30)
        response.raise_for_status()
        result = response.json()
        
        print(f"✅ Success!")
        print(f"   File saved: {result['saved_path']}")
        print(f"   Data Source: {result['data_source']}")
        print(f"   Data Set: {result['data_set']}")
        print(f"   Report Name: {result['report_name']}")
        
    except requests.exceptions.RequestException as e:
        print(f"❌ Error: {e}")


def verify_rdl_file(file_path):
    """Verify that an RDL file was created and is valid XML"""
    print("\n" + "=" * 70)
    print("Verifying Generated RDL File")
    print("=" * 70)
    
    path = Path(file_path)
    
    if not path.exists():
        print(f"❌ File not found: {file_path}")
        return False
    
    print(f"✅ File exists: {file_path}")
    print(f"   Size: {path.stat().st_size:,} bytes")
    
    # Try to parse as XML
    try:
        import xml.etree.ElementTree as ET
        tree = ET.parse(file_path)
        root = tree.getroot()
        
        # Check namespace
        if 'reporting/2016/01/reportdefinition' in root.tag:
            print(f"✅ Valid SSRS 2016+ RDL namespace")
        
        # Count key elements
        data_sources = root.findall('.//{*}DataSource')
        data_sets = root.findall('.//{*}DataSet')
        tablixes = root.findall('.//{*}Tablix')
        
        print(f"   DataSources: {len(data_sources)}")
        print(f"   DataSets: {len(data_sets)}")
        print(f"   Tablixes: {len(tablixes)}")
        
        return True
        
    except Exception as e:
        print(f"❌ XML parsing error: {e}")
        return False


if __name__ == "__main__":
    print("\n" + "=" * 70)
    print("SSRS RDL Generator API - Usage Examples")
    print("=" * 70)
    print("\nPrerequisites:")
    print("  1. Server running: python3 -m uvicorn app.main:app --host 127.0.0.1 --port 8000")
    print("  2. SQL Server connection configured in .env")
    print("  3. Database 'devtang' accessible")
    
    # Create output directory
    Path("./output").mkdir(exist_ok=True)
    
    # Run examples
    try:
        example_1_simple_query()
        example_2_parameterized_query()
        example_3_aggregation_query()
        example_4_complex_join()
        example_5_custom_data_source()
        
        # Verify one of the generated files
        verify_rdl_file("./output/products_report.rdl")
        
    except KeyboardInterrupt:
        print("\n\nInterrupted by user")
    except Exception as e:
        print(f"\n\n❌ Unexpected error: {e}")
        import traceback
        traceback.print_exc()
    
    print("\n" + "=" * 70)
    print("Examples complete!")
    print("=" * 70)
    print("\nGenerated files can be opened in:")
    print("  - Power BI Report Builder")
    print("  - SQL Server Data Tools (SSDT)")
    print("  - Visual Studio with SSRS extensions")
    print()
