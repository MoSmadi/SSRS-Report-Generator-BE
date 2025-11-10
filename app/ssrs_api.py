"""SSRS RDL generation API endpoint."""
import logging
import os
from pathlib import Path
from typing import List, Optional, Dict, Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from .conn import open_connection
from .schema_discovery import get_parameters, describe_result_set
from .rdl_builder import build_rdl
from .config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()

router = APIRouter(prefix="/report", tags=["ssrs"])


class SSRSGenerateRequest(BaseModel):
    """Request schema for SSRS RDL generation."""
    sql: str = Field(..., description="Raw T-SQL query text")
    output_path: str = Field(..., description="Absolute or relative file path to .rdl file")
    db_name: str = Field(..., description="Database name (e.g., 'devtang')")
    report_name: Optional[str] = Field(default="AutoReport", description="Report title")
    data_source_name: Optional[str] = Field(default="AutoDataSource", description="Data source name")
    data_set_name: Optional[str] = Field(default="AutoDataSet", description="Data set name")


class FieldInfo(BaseModel):
    """Field information in response."""
    name: str
    rdlType: str


class ParameterInfo(BaseModel):
    """Parameter information in response."""
    name: str
    type: str


class SSRSGenerateResponse(BaseModel):
    """Response schema for SSRS RDL generation."""
    status: str
    saved_path: str
    report_name: str
    data_source: str
    data_set: str
    fields: List[FieldInfo]
    parameters: List[ParameterInfo]
    notes: List[str] = Field(default_factory=list)


class SSRSErrorResponse(BaseModel):
    """Error response schema."""
    status: str = "error"
    message: str


@router.post("/ssrs-generate", response_model=SSRSGenerateResponse, responses={
    400: {"model": SSRSErrorResponse},
    500: {"model": SSRSErrorResponse}
})
def ssrs_generate(request: SSRSGenerateRequest) -> SSRSGenerateResponse:
    """
    Generate an SSRS RDL file from a raw SQL query.
    
    This endpoint:
    1. Validates input
    2. Detects SQL parameters
    3. Discovers result set schema via database connection
    4. Builds a minimal SSRS 2016+ RDL document
    5. Writes the RDL to the specified output path
    6. Returns metadata about the generated report
    """
    # Validate inputs
    if not request.sql or not request.sql.strip():
        raise HTTPException(status_code=400, detail="SQL query cannot be empty")
    
    if not request.output_path.endswith('.rdl'):
        raise HTTPException(status_code=400, detail="output_path must end with .rdl")
    
    if not request.db_name or not request.db_name.strip():
        raise HTTPException(status_code=400, detail="db_name cannot be empty")
    
    # Use defaults if not provided
    report_name = request.report_name or "AutoReport"
    data_source_name = request.data_source_name or "AutoDataSource"
    data_set_name = request.data_set_name or "AutoDataSet"
    
    notes: List[str] = []
    
    try:
        # Step 1: Detect parameters
        logger.info(f"Detecting parameters in SQL for database: {request.db_name}")
        parameters = get_parameters(request.sql)
        logger.info(f"Detected {len(parameters)} parameters: {parameters}")
        
        # Step 2: Discover schema
        logger.info(f"Connecting to database: {request.db_name}")
        try:
            conn = open_connection(request.db_name)
        except Exception as e:
            logger.error(f"Failed to connect to database: {e}")
            raise HTTPException(
                status_code=500, 
                detail=f"Failed to connect to database '{request.db_name}': {str(e)}"
            )
        
        try:
            logger.info("Discovering result set schema")
            fields, note = describe_result_set(request.sql, conn)
            
            if note:
                notes.append(note)
            
            if not fields:
                # Shouldn't happen as heuristic always returns at least one field
                raise HTTPException(
                    status_code=500,
                    detail="Failed to discover any fields from the query"
                )
            
            logger.info(f"Discovered {len(fields)} fields: {[f.name for f in fields]}")
            
        finally:
            conn.close()
        
        # Step 3: Build RDL
        logger.info("Building RDL document")
        server_value = f"{settings.sql_server_host},{settings.sql_server_port}"
        
        rdl_content = build_rdl(
            report_name=report_name,
            data_source_name=data_source_name,
            data_set_name=data_set_name,
            server_value=server_value,
            db_name=request.db_name,
            sql=request.sql,
            fields=fields,
            parameters=parameters
        )
        
        # Step 4: Write to file
        logger.info(f"Writing RDL to: {request.output_path}")
        output_file = Path(request.output_path)
        
        # Create directory if needed
        output_file.parent.mkdir(parents=True, exist_ok=True)
        
        # Write file (UTF-8 encoding)
        output_file.write_text(rdl_content, encoding='utf-8')
        
        # Resolve absolute path for response
        saved_path = str(output_file.resolve())
        
        logger.info(f"Successfully generated RDL: {saved_path}")
        
        # Step 5: Build response
        response = SSRSGenerateResponse(
            status="success",
            saved_path=saved_path,
            report_name=report_name,
            data_source=data_source_name,
            data_set=data_set_name,
            fields=[FieldInfo(name=f.name, rdlType=f.rdl_type) for f in fields],
            parameters=[ParameterInfo(name=p, type="String") for p in parameters],
            notes=notes
        )
        
        return response
        
    except HTTPException:
        # Re-raise HTTP exceptions as-is
        raise
    except Exception as e:
        # Catch-all for unexpected errors
        logger.exception("Unexpected error during SSRS generation")
        raise HTTPException(
            status_code=500,
            detail=f"Internal error: {str(e)}"
        )
