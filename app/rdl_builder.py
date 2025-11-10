"""RDL XML builder for SSRS 2016+ reports."""
import uuid
from typing import List
from .schema_discovery import FieldSpec


def build_rdl(
    report_name: str,
    data_source_name: str,
    data_set_name: str,
    server_value: str,
    db_name: str,
    sql: str,
    fields: List[FieldSpec],
    parameters: List[str]
) -> str:
    """
    Build a proper SSRS 2016+ RDL document.
    
    Args:
        report_name: Report title
        data_source_name: Data source name
        data_set_name: Data set name
        server_value: SQL Server host
        db_name: Database name
        sql: Raw SQL query text
        fields: List of FieldSpec objects
        parameters: List of parameter names (without @)
        
    Returns:
        RDL XML as string
    """
    # Use string template for proper SSRS structure
    report_id = str(uuid.uuid4())
    
    # Build fields XML
    fields_xml = _build_fields_xml(fields)
    
    # Build query parameters XML
    query_params_xml = _build_query_parameters_xml(parameters) if parameters else ""
    
    # Build report parameters XML
    report_params_xml = _build_report_parameters_xml(parameters) if parameters else ""
    
    # Build tablix XML
    tablix_xml = _build_tablix_xml(data_set_name, fields)
    
    # Escape SQL for XML
    sql_escaped = sql.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;').replace('"', '&quot;').replace("'", '&apos;')
    
    # Build complete RDL
    rdl = f'''<?xml version="1.0" encoding="utf-8"?>
<Report xmlns="http://schemas.microsoft.com/sqlserver/reporting/2016/01/reportdefinition" xmlns:rd="http://schemas.microsoft.com/SQLServer/reporting/reportdesigner">
\t<AutoRefresh>0</AutoRefresh>
\t<DataSources>
\t\t<DataSource Name="{data_source_name}">
\t\t\t<ConnectionProperties>
\t\t\t\t<DataProvider>SQL</DataProvider>
\t\t\t\t<ConnectString>Data Source={server_value};Initial Catalog={db_name};</ConnectString>
\t\t\t</ConnectionProperties>
\t\t</DataSource>
\t</DataSources>
\t<DataSets>
\t\t<DataSet Name="{data_set_name}">
\t\t\t<Query>
\t\t\t\t<DataSourceName>{data_source_name}</DataSourceName>
\t\t\t\t<CommandType>Text</CommandType>
\t\t\t\t<CommandText>{sql_escaped}</CommandText>{query_params_xml}
\t\t\t</Query>
\t\t\t<Fields>{fields_xml}
\t\t\t</Fields>
\t\t</DataSet>
\t</DataSets>{report_params_xml}
\t<ReportSections>
\t\t<ReportSection>
\t\t\t<Body>
\t\t\t\t<ReportItems>{tablix_xml}
\t\t\t\t</ReportItems>
\t\t\t\t<Height>2in</Height>
\t\t\t\t<Style />
\t\t\t</Body>
\t\t\t<Width>{len(fields)}in</Width>
\t\t\t<Page>
\t\t\t\t<PageHeight>11in</PageHeight>
\t\t\t\t<PageWidth>8.5in</PageWidth>
\t\t\t\t<LeftMargin>0.5in</LeftMargin>
\t\t\t\t<RightMargin>0.5in</RightMargin>
\t\t\t\t<TopMargin>0.5in</TopMargin>
\t\t\t\t<BottomMargin>0.5in</BottomMargin>
\t\t\t\t<Style />
\t\t\t</Page>
\t\t</ReportSection>
\t</ReportSections>
\t<Language>=User!Language</Language>
\t<rd:ReportUnitType>Inch</rd:ReportUnitType>
\t<rd:ReportID>{report_id}</rd:ReportID>
</Report>'''
    
    return rdl


def _build_fields_xml(fields: List[FieldSpec]) -> str:
    """Build Fields XML section."""
    fields_xml_parts = []
    for field in fields:
        fields_xml_parts.append(f'''
				<Field Name="{field.name}">
					<DataField>{field.name}</DataField>
					<rd:TypeName>{field.rdl_type}</rd:TypeName>
				</Field>''')
    return ''.join(fields_xml_parts)


def _build_query_parameters_xml(parameters: List[str]) -> str:
    """Build QueryParameters XML section."""
    params_xml_parts = ['\n				<QueryParameters>']
    for param in parameters:
        params_xml_parts.append(f'''
					<QueryParameter Name="@{param}">
						<Value>=Parameters!{param}.Value</Value>
					</QueryParameter>''')
    params_xml_parts.append('\n				</QueryParameters>')
    return ''.join(params_xml_parts)


def _build_report_parameters_xml(parameters: List[str]) -> str:
    """Build ReportParameters XML section."""
    params_xml_parts = ['\n	<ReportParameters>']
    for param in parameters:
        params_xml_parts.append(f'''
		<ReportParameter Name="{param}">
			<DataType>String</DataType>
			<Nullable>true</Nullable>
			<Prompt>{param}</Prompt>
		</ReportParameter>''')
    params_xml_parts.append('\n	</ReportParameters>')
    return ''.join(params_xml_parts)


def _build_tablix_xml(data_set_name: str, fields: List[FieldSpec]) -> str:
    """Build Tablix XML with proper SSRS 2016+ structure."""
    
    # Build columns
    columns_xml = ''.join([f'''
						<TablixColumn>
							<Width>1in</Width>
						</TablixColumn>''' for _ in fields])
    
    # Build header row cells
    header_cells = []
    for i, field in enumerate(fields, 1):
        header_cells.append(f'''
							<TablixCell>
								<CellContents>
									<Textbox Name="Header_{i}">
										<CanGrow>true</CanGrow>
										<KeepTogether>true</KeepTogether>
										<Paragraphs>
											<Paragraph>
												<TextRuns>
													<TextRun>
														<Value>{field.name}</Value>
														<Style />
													</TextRun>
												</TextRuns>
												<Style />
											</Paragraph>
										</Paragraphs>
										<rd:DefaultName>Header_{i}</rd:DefaultName>
										<Style>
											<Border>
												<Style>None</Style>
											</Border>
											<PaddingLeft>2pt</PaddingLeft>
											<PaddingRight>2pt</PaddingRight>
											<PaddingTop>2pt</PaddingTop>
											<PaddingBottom>2pt</PaddingBottom>
										</Style>
									</Textbox>
								</CellContents>
							</TablixCell>''')
    
    # Build detail row cells
    detail_cells = []
    for i, field in enumerate(fields, 1):
        detail_cells.append(f'''
							<TablixCell>
								<CellContents>
									<Textbox Name="Detail_{i}">
										<CanGrow>true</CanGrow>
										<KeepTogether>true</KeepTogether>
										<Paragraphs>
											<Paragraph>
												<TextRuns>
													<TextRun>
														<Value>=Fields!{field.name}.Value</Value>
														<Style />
													</TextRun>
												</TextRuns>
												<Style />
											</Paragraph>
										</Paragraphs>
										<rd:DefaultName>Detail_{i}</rd:DefaultName>
										<Style>
											<Border>
												<Style>None</Style>
											</Border>
											<PaddingLeft>2pt</PaddingLeft>
											<PaddingRight>2pt</PaddingRight>
											<PaddingTop>2pt</PaddingTop>
											<PaddingBottom>2pt</PaddingBottom>
										</Style>
									</Textbox>
								</CellContents>
							</TablixCell>''')
    
    # Build column hierarchy members
    column_members = ''.join(['''
							<TablixMember />''' for _ in fields])
    
    # Complete tablix XML
    tablix = f'''
					<Tablix Name="Table1">
						<TablixBody>
							<TablixColumns>{columns_xml}
							</TablixColumns>
							<TablixRows>
								<TablixRow>
									<Height>0.25in</Height>
									<TablixCells>{''.join(header_cells)}
									</TablixCells>
								</TablixRow>
								<TablixRow>
									<Height>0.25in</Height>
									<TablixCells>{''.join(detail_cells)}
									</TablixCells>
								</TablixRow>
							</TablixRows>
						</TablixBody>
						<DataSetName>{data_set_name}</DataSetName>
						<TablixColumnHierarchy>
							<TablixMembers>{column_members}
							</TablixMembers>
						</TablixColumnHierarchy>
						<TablixRowHierarchy>
							<TablixMembers>
								<TablixMember>
									<KeepWithGroup>After</KeepWithGroup>
								</TablixMember>
								<TablixMember>
									<Group Name="Details" />
								</TablixMember>
							</TablixMembers>
						</TablixRowHierarchy>
						<Height>0.5in</Height>
						<Width>{len(fields)}in</Width>
						<Style>
							<Border>
								<Style>None</Style>
							</Border>
						</Style>
					</Tablix>'''
    
    return tablix
