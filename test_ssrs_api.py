#!/usr/bin/env python3
"""
Test script for SSRS RDL Generator API

This script demonstrates how to use the SSRS RDL generation endpoint.
"""

import json
import requests
import sys

# API endpoint
BASE_URL = "http://127.0.0.1:8000"
ENDPOINT = f"{BASE_URL}/report/ssrs-generate"

# Test cases
test_cases = [
    {
        "name": "Simple query with parameter",
        "request": {
            "sql": "SELECT TOP 5 Id, Name, CreatedDate FROM dbo.TestTable WHERE CreatedDate >= @StartDate",
            "output_path": "/tmp/test_report_1.rdl",
            "db_name": "devtang",
            "report_name": "Test Report 1"
        }
    },
    {
        "name": "Query with multiple parameters",
        "request": {
            "sql": "SELECT Id, CustomerName FROM dbo.Customers WHERE CreatedAt BETWEEN @From AND @To ORDER BY CreatedAt DESC",
            "output_path": "/tmp/test_report_2.rdl",
            "db_name": "devtang",
            "report_name": "Customer Report"
        }
    },
    {
        "name": "Aggregation query",
        "request": {
            "sql": "SELECT StoreName, SUM(Sales) AS TotalSales FROM dbo.Sales WHERE SalesDate >= @Start GROUP BY StoreName",
            "output_path": "/tmp/test_report_3.rdl",
            "db_name": "devtang",
            "report_name": "Sales Summary"
        }
    }
]


def test_endpoint():
    """Test the SSRS generation endpoint."""
    
    # First, check if the server is running
    try:
        health_response = requests.get(f"{BASE_URL}/healthz", timeout=5)
        if health_response.status_code != 200:
            print("❌ Server is not healthy")
            return False
        print("✅ Server is running and healthy\n")
    except requests.exceptions.RequestException as e:
        print(f"❌ Cannot connect to server: {e}")
        print(f"   Make sure the server is running on {BASE_URL}")
        print(f"   Start with: python3 -m uvicorn app.main:app --host 127.0.0.1 --port 8000")
        return False
    
    # Run test cases
    for i, test_case in enumerate(test_cases, 1):
        print(f"Test {i}: {test_case['name']}")
        print("-" * 60)
        
        try:
            response = requests.post(ENDPOINT, json=test_case['request'], timeout=10)
            
            print(f"Status Code: {response.status_code}")
            
            if response.status_code == 200:
                result = response.json()
                print(f"✅ Success!")
                print(f"   Saved to: {result['saved_path']}")
                print(f"   Report name: {result['report_name']}")
                print(f"   Fields: {len(result['fields'])}")
                print(f"   Parameters: {len(result['parameters'])}")
                if result.get('fields'):
                    print(f"   Field names: {[f['name'] for f in result['fields']]}")
                if result.get('parameters'):
                    print(f"   Parameter names: {[p['name'] for p in result['parameters']]}")
                if result.get('notes'):
                    print(f"   Notes: {result['notes']}")
            else:
                print(f"❌ Error: {response.status_code}")
                print(f"   Response: {response.text}")
                
        except requests.exceptions.RequestException as e:
            print(f"❌ Request failed: {e}")
        
        print()
    
    return True


def test_validation():
    """Test input validation."""
    print("Testing Input Validation")
    print("-" * 60)
    
    invalid_cases = [
        {
            "name": "Empty SQL",
            "request": {"sql": "", "output_path": "/tmp/test.rdl", "db_name": "devtang"}
        },
        {
            "name": "Invalid output path",
            "request": {"sql": "SELECT 1", "output_path": "/tmp/test.txt", "db_name": "devtang"}
        },
        {
            "name": "Empty database name",
            "request": {"sql": "SELECT 1", "output_path": "/tmp/test.rdl", "db_name": ""}
        }
    ]
    
    for test_case in invalid_cases:
        print(f"\nTest: {test_case['name']}")
        try:
            response = requests.post(ENDPOINT, json=test_case['request'], timeout=5)
            if response.status_code == 400:
                print(f"✅ Correctly rejected with 400")
                print(f"   Message: {response.json().get('detail', 'N/A')}")
            else:
                print(f"❌ Unexpected status: {response.status_code}")
        except requests.exceptions.RequestException as e:
            print(f"❌ Request failed: {e}")
    
    print()


if __name__ == "__main__":
    print("=" * 60)
    print("SSRS RDL Generator API Test Suite")
    print("=" * 60)
    print()
    
    # Test main functionality
    if not test_endpoint():
        sys.exit(1)
    
    # Test validation
    test_validation()
    
    print("=" * 60)
    print("Testing complete!")
    print("=" * 60)
