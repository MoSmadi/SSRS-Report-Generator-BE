#!/usr/bin/env python3
"""
Test script to generate and validate new RDL structure.
"""
import sys
import os

# Add app to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.rdl_builder import build_rdl
from app.schema_discovery import FieldSpec

def test_rdl_generation():
    """Test RDL generation with sample data."""
    
    # Create test fields
    fields = [
        FieldSpec(name='ItemName', rdl_type='System.String'),
        FieldSpec(name='Quantity', rdl_type='System.Int32'),
        FieldSpec(name='Price', rdl_type='System.Decimal')
    ]
    
    # Create test SQL
    sql = 'SELECT ItemName, Quantity, Price FROM Inventory WHERE Quantity > 0'
    
    # Generate RDL
    print("Generating RDL...")
    rdl = build_rdl(
        report_name='TestReport',
        data_source_name='DataSource1',
        data_set_name='DataSet1',
        server_value='localhost',
        db_name='TestDB',
        sql=sql,
        fields=fields,
        parameters=[]
    )
    
    # Write to file
    output_path = '/tmp/test_generated_rdl.xml'
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(rdl)
    
    print(f"✅ RDL generated successfully!")
    print(f"📄 Saved to: {output_path}")
    print(f"📏 Length: {len(rdl)} characters")
    
    # Check for critical elements
    print("\n🔍 Checking for critical SSRS 2016+ structures:")
    checks = {
        'ReportSections': '<ReportSections>' in rdl,
        'Paragraphs': '<Paragraphs>' in rdl,
        'TextRuns': '<TextRuns>' in rdl,
        'TablixMember with KeepWithGroup': '<KeepWithGroup>After</KeepWithGroup>' in rdl,
        'TablixMember with Group': '<Group Name="Details"' in rdl,
        'Page element': '<Page>' in rdl,
        'CanGrow property': '<CanGrow>true</CanGrow>' in rdl,
        'Style element': '<Style>' in rdl,
        'Proper namespace': 'xmlns:rd="http://schemas.microsoft.com/SQLServer/reporting/reportdesigner"' in rdl
    }
    
    all_pass = True
    for check, result in checks.items():
        status = '✅' if result else '❌'
        print(f"  {status} {check}")
        if not result:
            all_pass = False
    
    # Try to parse as XML
    print("\n🔍 XML Validation:")
    try:
        import xml.etree.ElementTree as ET
        ET.fromstring(rdl)
        print("  ✅ Valid XML structure")
    except Exception as e:
        print(f"  ❌ XML parsing error: {e}")
        all_pass = False
    
    # Show first 1000 characters
    print("\n📝 First 1000 characters:")
    print(rdl[:1000])
    
    if all_pass:
        print("\n✅ All checks passed!")
    else:
        print("\n❌ Some checks failed")
    
    return all_pass

if __name__ == '__main__':
    try:
        success = test_rdl_generation()
        sys.exit(0 if success else 1)
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
