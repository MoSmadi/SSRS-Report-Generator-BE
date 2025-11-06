"""RDL document builder using Jinja2 templates."""
from __future__ import annotations

from typing import Iterable

from jinja2 import Template

from .schemas import ChartSpec, ColumnDef, ParamDef

_RDL_TEMPLATE = Template(
    """<?xml version=\"1.0\" encoding=\"utf-8\"?>
<Report xmlns=\"{{ namespace }}\" xmlns:rd=\"http://schemas.microsoft.com/SQLServer/reporting/reportdesigner\">
  <AutoRefresh>0</AutoRefresh>
  <DataSources>
    <DataSource Name=\"{{ ds_name }}\">
      <DataSourceReference>{{ shared_ds_path }}</DataSourceReference>
    </DataSource>
  </DataSources>
  <DataSets>
    <DataSet Name=\"{{ dataset_name }}\">
      <Query>
        <DataSourceName>{{ ds_name }}</DataSourceName>
        <CommandText>{{ sql_text | e }}</CommandText>
      </Query>
      <Fields>
        {% for field in fields %}
        <Field Name=\"{{ field.name }}\">
          <DataField>{{ field.name }}</DataField>
          <rd:TypeName>{{ field.rdlType }}</rd:TypeName>
        </Field>
        {% endfor %}
      </Fields>
      {% if parameters %}
      <QueryParameters>
        {% for param in parameters %}
        <QueryParameter Name=\"{{ param.name }}\">
          <Value>=Parameters!{{ param.name }}.Value</Value>
        </QueryParameter>
        {% endfor %}
      </QueryParameters>
      {% endif %}
    </DataSet>
  </DataSets>
  {% if parameters %}
  <ReportParameters>
    {% for param in parameters %}
    <ReportParameter Name=\"{{ param.name }}\">
      <DataType>{{ param.rdlType }}</DataType>
      <Prompt>{{ param.prompt or param.name }}</Prompt>
      <Hidden>false</Hidden>
    </ReportParameter>
    {% endfor %}
  </ReportParameters>
  {% endif %}
  <Body>
    <ReportItems>
      <Tablix Name=\"MainTable\">
        <TablixBody>
          <TablixColumns>
            {% for field in fields %}<TablixColumn><Width>1in</Width></TablixColumn>{% endfor %}
          </TablixColumns>
          <TablixRows>
            <TablixRow>
              <Height>0.25in</Height>
              <TablixCells>
                {% for field in fields %}
                <TablixCell>
                  <CellContents>
                    <Textbox Name=\"Header{{ loop.index }}\">
                      <Value>{{ field.display_name }}</Value>
                      <Style><FontWeight>Bold</FontWeight></Style>
                    </Textbox>
                  </CellContents>
                </TablixCell>
                {% endfor %}
              </TablixCells>
            </TablixRow>
            <TablixRow>
              <Height>0.25in</Height>
              <TablixCells>
                {% for field in fields %}
                <TablixCell>
                  <CellContents>
                    <Textbox Name=\"Detail{{ loop.index }}\">
                      <Value>=Fields!{{ field.name }}.Value</Value>
                    </Textbox>
                  </CellContents>
                </TablixCell>
                {% endfor %}
              </TablixCells>
            </TablixRow>
          </TablixRows>
        </TablixBody>
        <DataSetName>{{ dataset_name }}</DataSetName>
      </Tablix>
      {% if chart %}
      <Chart Name=\"MainChart\">
        <ChartCategoryHierarchy>
          <ChartMembers>
            <ChartMember>
              <Label>=Fields!{{ chart.category }}.Value</Label>
            </ChartMember>
          </ChartMembers>
        </ChartCategoryHierarchy>
        <ChartSeriesHierarchy>
          <ChartMembers>
            {% for series in chart.series or ['Series'] %}
            <ChartMember>
              <Label>{{ series }}</Label>
            </ChartMember>
            {% endfor %}
          </ChartMembers>
        </ChartSeriesHierarchy>
        <ChartData>
          <ChartSeriesCollection>
            {% for value in chart.values %}
            <ChartSeries>
              <DataPoints>
                <DataPoint>
                  <DataValues>
                    <DataValue><Value>=Fields!{{ value }}.Value</Value></DataValue>
                  </DataValues>
                </DataPoint>
              </DataPoints>
            </ChartSeries>
            {% endfor %}
          </ChartSeriesCollection>
        </ChartData>
        <DataSetName>{{ dataset_name }}</DataSetName>
        <ChartType>{{ chart.type.title() }}</ChartType>
      </Chart>
      {% endif %}
    </ReportItems>
    <Height>4in</Height>
  </Body>
  <Width>8in</Width>
  <Page>
    <PageHeight>11in</PageHeight>
    <PageWidth>8.5in</PageWidth>
  </Page>
</Report>
"""
)


def build_rdl(
    namespace: str,
    ds_name: str,
    shared_ds_path: str,
    dataset_name: str,
    sql_text: str,
    parameters: Iterable[ParamDef],
    fields: Iterable[ColumnDef],
    chart: ChartSpec | None,
) -> bytes:
    rendered = _RDL_TEMPLATE.render(
        namespace=namespace,
        ds_name=ds_name,
        shared_ds_path=shared_ds_path,
        dataset_name=dataset_name,
        sql_text=sql_text,
        parameters=list(parameters),
        fields=list(fields),
        chart=chart,
    )
    return rendered.encode("utf-8")
