"""Schema discovery utilities for SSRS RDL generation."""
import re
from typing import List, Dict, Optional
import pyodbc


class FieldSpec:
    """Specification for a result set field."""
    
    def __init__(self, name: str, rdl_type: str):
        self.name = name
        self.rdl_type = rdl_type
    
    def __repr__(self):
        return f"FieldSpec(name={self.name!r}, rdl_type={self.rdl_type!r})"


def get_parameters(sql: str) -> List[str]:
    """
    Extract parameter names from SQL query.
    
    Scans for tokens of the form @ParamName (single @, not @@).
    De-duplicates while preserving order of first appearance.
    
    Args:
        sql: SQL query text
        
    Returns:
        List of parameter names (without leading @)
    """
    # Pattern to match @ParamName but not @@SERVERNAME
    pattern = r'(?<!@)@(\w+)'
    
    matches = re.findall(pattern, sql)
    
    # De-duplicate while preserving order
    seen = set()
    params = []
    for match in matches:
        if match not in seen:
            seen.add(match)
            params.append(match)
    
    return params


def sql_type_to_rdl_type(sql_type: str) -> str:
    """
    Map SQL Server type to RDL .NET type.
    
    Args:
        sql_type: SQL Server type name
        
    Returns:
        RDL .NET type (e.g., System.String, System.Int32, etc.)
    """
    sql_type_lower = sql_type.lower()
    
    # Integer types
    if sql_type_lower in ('int', 'smallint', 'tinyint'):
        return 'System.Int32'
    
    if sql_type_lower == 'bigint':
        return 'System.Int64'
    
    # Boolean
    if sql_type_lower == 'bit':
        return 'System.Boolean'
    
    # Decimal types
    if sql_type_lower in ('decimal', 'numeric', 'money', 'smallmoney'):
        return 'System.Decimal'
    
    # Floating point
    if sql_type_lower in ('float', 'real'):
        return 'System.Double'
    
    # Date/Time
    if sql_type_lower in ('date', 'datetime', 'datetime2', 'smalldatetime', 'time', 'datetimeoffset'):
        return 'System.DateTime'
    
    # Default to String for everything else
    return 'System.String'


def sanitize_field_name(name: str) -> str:
    """
    Make field name XML-safe: A-Z, 0-9, underscores only.
    Replace or strip other characters.
    
    Args:
        name: Original field name
        
    Returns:
        Sanitized field name
    """
    # Replace spaces and special chars with underscore
    sanitized = re.sub(r'[^A-Za-z0-9_]', '_', name)
    
    # Remove leading numbers or underscores
    sanitized = re.sub(r'^[0-9_]+', '', sanitized)
    
    # If empty after sanitization, use a default
    if not sanitized:
        sanitized = 'Field'
    
    return sanitized


def deduplicate_field_names(names: List[str]) -> List[str]:
    """
    De-duplicate field names by appending incremental suffixes.
    
    Args:
        names: List of field names (may contain duplicates)
        
    Returns:
        List of unique field names with suffixes where needed
    """
    seen: Dict[str, int] = {}
    result = []
    
    for name in names:
        if name not in seen:
            seen[name] = 1
            result.append(name)
        else:
            seen[name] += 1
            result.append(f"{name}_{seen[name]}")
    
    return result


def describe_result_set(sql: str, conn: pyodbc.Connection) -> tuple[List[FieldSpec], Optional[str]]:
    """
    Discover result set columns and types without retrieving data.
    
    Attempts in order:
    1. sp_describe_first_result_set (preferred)
    2. Schema-only execution (SET FMTONLY ON or cursor.description)
    3. Heuristic parsing of SELECT list
    
    Args:
        sql: SQL query text
        conn: pyodbc Connection object
        
    Returns:
        Tuple of (list of FieldSpec objects, optional note message)
    """
    # Try primary method: sp_describe_first_result_set
    try:
        fields, note = _describe_via_sp(sql, conn)
        if fields:
            return fields, note
    except Exception:
        pass  # Fall through to next method
    
    # Try fallback A: schema-only execution
    try:
        fields, note = _describe_via_schema_only(sql, conn)
        if fields:
            return fields, note
    except Exception:
        pass  # Fall through to next method
    
    # Fallback B: heuristic parsing
    fields, note = _describe_via_heuristic(sql)
    return fields, note


def _describe_via_sp(sql: str, conn: pyodbc.Connection) -> tuple[List[FieldSpec], Optional[str]]:
    """
    Use sp_describe_first_result_set to discover schema.
    
    Args:
        sql: SQL query text
        conn: pyodbc Connection object
        
    Returns:
        Tuple of (list of FieldSpec, optional note)
    """
    cursor = conn.cursor()
    
    # Escape single quotes in SQL
    escaped_sql = sql.replace("'", "''")
    
    # Execute sp_describe_first_result_set
    sp_query = f"EXEC sys.sp_describe_first_result_set @tsql = N'{escaped_sql}'"
    cursor.execute(sp_query)
    
    fields = []
    for row in cursor.fetchall():
        # Row structure from sp_describe_first_result_set:
        # is_hidden, column_ordinal, name, is_nullable, system_type_id, system_type_name, ...
        is_hidden = row.is_hidden if hasattr(row, 'is_hidden') else row[0]
        name = row.name if hasattr(row, 'name') else row[2]
        system_type_name = row.system_type_name if hasattr(row, 'system_type_name') else row[5]
        
        if is_hidden:
            continue
        
        if not name:
            continue
        
        # Clean up type name (remove precision/scale)
        base_type = system_type_name.split('(')[0] if system_type_name else 'nvarchar'
        rdl_type = sql_type_to_rdl_type(base_type)
        
        # Sanitize field name
        safe_name = sanitize_field_name(name)
        
        fields.append(FieldSpec(safe_name, rdl_type))
    
    # De-duplicate field names
    field_names = [f.name for f in fields]
    unique_names = deduplicate_field_names(field_names)
    
    for i, field in enumerate(fields):
        field.name = unique_names[i]
    
    return fields, None


def _describe_via_schema_only(sql: str, conn: pyodbc.Connection) -> tuple[List[FieldSpec], Optional[str]]:
    """
    Use SET FMTONLY ON or similar technique to get schema without data.
    
    Args:
        sql: SQL query text
        conn: pyodbc Connection object
        
    Returns:
        Tuple of (list of FieldSpec, optional note)
    """
    cursor = conn.cursor()
    
    # Try SET FMTONLY ON (older SQL Server)
    try:
        cursor.execute("SET FMTONLY ON")
        cursor.execute(sql)
        
        fields = []
        if cursor.description:
            for col in cursor.description:
                name = col[0]
                type_code = col[1]
                
                # Map pyodbc type code to SQL type
                rdl_type = _pyodbc_type_to_rdl(type_code)
                safe_name = sanitize_field_name(name)
                
                fields.append(FieldSpec(safe_name, rdl_type))
        
        cursor.execute("SET FMTONLY OFF")
        
        # De-duplicate
        field_names = [f.name for f in fields]
        unique_names = deduplicate_field_names(field_names)
        for i, field in enumerate(fields):
            field.name = unique_names[i]
        
        return fields, "schema discovered via FMTONLY"
    except Exception:
        pass
    
    return [], None


def _describe_via_heuristic(sql: str) -> tuple[List[FieldSpec], str]:
    """
    Parse SELECT list heuristically to extract field names.
    
    Args:
        sql: SQL query text
        
    Returns:
        Tuple of (list of FieldSpec with System.String types, note message)
    """
    # Find SELECT clause
    select_pattern = r'\bSELECT\s+(.*?)\s+FROM\b'
    match = re.search(select_pattern, sql, re.IGNORECASE | re.DOTALL)
    
    if not match:
        # No SELECT found, return a single placeholder field
        return [FieldSpec('Column1', 'System.String')], "schema inferred heuristically"
    
    select_list = match.group(1)
    
    # Split by comma at top level (not inside parentheses)
    columns = _split_select_list(select_list)
    
    fields = []
    for i, col in enumerate(columns):
        # Extract alias if present (AS alias or trailing identifier)
        alias_match = re.search(r'\bAS\s+(\w+)\s*$', col, re.IGNORECASE)
        if alias_match:
            name = alias_match.group(1)
        else:
            # Try to extract trailing identifier
            trailing_match = re.search(r'[\w\.]+$', col.strip())
            if trailing_match:
                name = trailing_match.group(0).split('.')[-1]  # Take last part if dotted
            else:
                name = f'Column{i+1}'
        
        safe_name = sanitize_field_name(name)
        fields.append(FieldSpec(safe_name, 'System.String'))
    
    # De-duplicate
    field_names = [f.name for f in fields]
    unique_names = deduplicate_field_names(field_names)
    for i, field in enumerate(fields):
        field.name = unique_names[i]
    
    return fields, "schema inferred heuristically"


def _split_select_list(select_list: str) -> List[str]:
    """
    Split SELECT list by commas at top level (not inside parentheses).
    
    Args:
        select_list: The SELECT projection text
        
    Returns:
        List of column expressions
    """
    depth = 0
    current = []
    columns = []
    
    for char in select_list:
        if char == '(':
            depth += 1
            current.append(char)
        elif char == ')':
            depth -= 1
            current.append(char)
        elif char == ',' and depth == 0:
            columns.append(''.join(current).strip())
            current = []
        else:
            current.append(char)
    
    # Add last column
    if current:
        columns.append(''.join(current).strip())
    
    return [col for col in columns if col]


def _pyodbc_type_to_rdl(type_code) -> str:
    """
    Map pyodbc type code to RDL .NET type.
    
    Args:
        type_code: pyodbc type code from cursor.description
        
    Returns:
        RDL .NET type string
    """
    # pyodbc type mapping (approximate)
    # This is a best-effort mapping
    import pyodbc
    
    if type_code == pyodbc.SQL_INTEGER or type_code == pyodbc.SQL_SMALLINT or type_code == pyodbc.SQL_TINYINT:
        return 'System.Int32'
    elif type_code == pyodbc.SQL_BIGINT:
        return 'System.Int64'
    elif type_code == pyodbc.SQL_BIT:
        return 'System.Boolean'
    elif type_code == pyodbc.SQL_DECIMAL or type_code == pyodbc.SQL_NUMERIC:
        return 'System.Decimal'
    elif type_code == pyodbc.SQL_FLOAT or type_code == pyodbc.SQL_REAL or type_code == pyodbc.SQL_DOUBLE:
        return 'System.Double'
    elif type_code == pyodbc.SQL_TYPE_TIMESTAMP or type_code == pyodbc.SQL_TYPE_DATE or type_code == pyodbc.SQL_TYPE_TIME:
        return 'System.DateTime'
    else:
        return 'System.String'
