"""Populate a reusable workbook and serialize a native, refreshable Excel PivotTable.

The explicit OOXML cache avoids unreliable PivotTable export in the template authoring tool.
The visible annual grid and cache are generated from the same asset schedule.
"""

from pathlib import Path
import openpyxl
from openpyxl.chart import Reference
from openpyxl.styles import Font, PatternFill
from openpyxl.worksheet.table import Table, TableStyleInfo
from openpyxl.pivot.cache import (
    CacheDefinition,
    CacheSource,
    WorksheetSource,
    CacheField,
    SharedItems,
)
from openpyxl.pivot.fields import Text, Number, Index
from openpyxl.pivot.record import RecordList, Record
from openpyxl.pivot.table import (
    TableDefinition,
    Location,
    PivotField,
    FieldItem,
    RowColField,
    RowColItem,
    DataField,
)

TEMPLATE = Path(__file__).resolve().parents[2] / "templates/lifecycle.xlsx"


def export_workbook(assets, path, as_of_year):
    book = openpyxl.load_workbook(TEMPLATE)
    sheet = book["Lifecycle"]
    source = book["Assets"]
    headers = ["asset_id", "system", "replacement_year", "lifecycle_cost_cad"]
    records = [list(row) for row in assets[headers].itertuples(index=False, name=None)]
    source.delete_rows(5, max(source.max_row - 4, 1))
    for row in records:
        source.append(row)
    end = 4 + len(records)
    table = Table(displayName="AssetSchedule", ref=f"A4:D{end}")
    table.tableStyleInfo = TableStyleInfo(name="TableStyleMedium2", showRowStripes=True)
    source.add_table(table)
    for row in source.iter_rows(min_row=5, max_row=end, min_col=4, max_col=4):
        row[0].number_format = '"$"#,##0'
    systems = ["Sanitary", "Stormwater", "Water"]
    years = list(
        range(as_of_year, max(assets.replacement_year.max(), as_of_year + 9) + 1)
    )
    # Remove template placeholders/notes before laying out a variable-height pivot.
    for row in sheet.iter_rows(min_row=6, max_row=max(21, len(years) + 10), max_col=5):
        for cell in row:
            cell.value = None
    grouped = assets.groupby(["replacement_year", "system"]).lifecycle_cost_cad.sum()
    for col, value in enumerate(["Lifecycle cost CAD", "System", None, None, None], 1):
        sheet.cell(5, col).value = value
    for col, value in enumerate(["Year", *systems, "Total CAD"], 1):
        sheet.cell(6, col, value)
    for cell in sheet[6][:5]:
        cell.fill = PatternFill("solid", fgColor="233E52")
        cell.font = Font(name="Arial", bold=True, color="FFFFFF", size=11)
    for year in years:
        row = 7 + year - as_of_year
        values = [round(float(grouped.get((year, system), 0)), 2) for system in systems]
        for col, value in enumerate([year, *values, round(sum(values), 2)], 1):
            sheet.cell(row, col, value)
    grand_row = 7 + len(years)
    totals = [
        round(float(assets.loc[assets.system == system, "lifecycle_cost_cad"].sum()), 2)
        for system in systems
    ]
    for col, value in enumerate(["Grand Total", *totals, round(sum(totals), 2)], 1):
        sheet.cell(grand_row, col, value)
    for row in sheet.iter_rows(min_row=7, max_row=grand_row, min_col=2, max_col=5):
        for cell in row:
            cell.number_format = '"$"#,##0'
    for cell in sheet[grand_row][:5]:
        cell.font = Font(name="Arial", bold=True, size=11)
    sheet.cell(
        24,
        7,
        "In Excel: select the PivotTable, then Data > Refresh All after editing Assets.",
    )
    sheet.cell(
        25,
        7,
        "Chart: first 10 years. Full lifecycle schedule: annual PivotTable at left.",
    )
    sheet.cell(
        26,
        7,
        "One replacement per asset; 2.5% annual inflation; sample costs, not a budget.",
    )
    sheet["A3"] = f"Synthetic assets | nominal CAD | base year {as_of_year}"
    # The template chart uses A5:D15, deliberately a readable ten-year window.
    chart = sheet._charts[0]
    chart.title = f"{as_of_year}-{as_of_year + 9} replacement cost (CAD)"
    for i, series in enumerate(chart.ser, 2):
        series.cat.strRef.f = "'Lifecycle'!$A$7:$A$16"
        column = openpyxl.utils.get_column_letter(i)
        series.val.numRef.f = f"'Lifecycle'!${column}$7:${column}$16"
    shared = [sorted(assets[h].unique().tolist()) for h in headers[:3]]
    shared[1] = systems
    shared[2] = years
    fields = [
        CacheField(
            name=h,
            sharedItems=SharedItems(
                _fields=[
                    Text(v=v) if isinstance(v, str) else Number(v=int(v))
                    for v in values
                ],
                containsString=isinstance(values[0], str),
                containsNumber=not isinstance(values[0], str),
                containsInteger=not isinstance(values[0], str),
                containsNonDate=True,
            ),
        )
        for h, values in zip(headers, shared)
    ]
    fields.append(
        CacheField(
            name=headers[3],
            sharedItems=SharedItems(containsNumber=True, containsNonDate=True),
        )
    )
    lookups = [{value: i for i, value in enumerate(values)} for values in shared]
    cache = CacheDefinition(
        cacheSource=CacheSource(
            type="worksheet",
            worksheetSource=WorksheetSource(ref=f"A4:D{end}", sheet="Assets"),
        ),
        cacheFields=fields,
        recordCount=len(records),
        saveData=True,
        refreshOnLoad=False,
        enableRefresh=True,
        createdVersion=6,
        refreshedVersion=6,
        minRefreshableVersion=3,
    )
    cache.records = RecordList(
        r=[
            Record(
                _fields=[Index(v=lookups[i][row[i]]) for i in range(3)]
                + [Number(v=row[3])]
            )
            for row in records
        ]
    )
    pivot = TableDefinition(
        name="LifecycleBySystemYear",
        cacheId=1,
        dataCaption="Lifecycle cost CAD",
        rowHeaderCaption="Year",
        colHeaderCaption="System",
        location=Location(
            ref=f"A5:E{grand_row}", firstHeaderRow=1, firstDataRow=2, firstDataCol=1
        ),
        pivotFields=[
            PivotField(dataField=False, defaultSubtotal=False),
            PivotField(
                axis="axisCol",
                defaultSubtotal=False,
                items=[FieldItem(x=i) for i in range(3)],
            ),
            PivotField(
                axis="axisRow",
                defaultSubtotal=False,
                items=[FieldItem(x=i) for i in range(len(shared[2]))],
            ),
            PivotField(dataField=True, defaultSubtotal=False),
        ],
        rowFields=[RowColField(x=2)],
        colFields=[RowColField(x=1)],
        dataFields=[
            DataField(name="Lifecycle cost CAD", fld=3, subtotal="sum", numFmtId=164)
        ],
        rowItems=[RowColItem(x=[Index(v=i)]) for i in range(len(shared[2]))]
        + [RowColItem(t="grand", x=[Index(v=0)])],
        colItems=[RowColItem(x=[Index(v=i)]) for i in range(3)]
        + [RowColItem(t="grand", x=[Index(v=0)])],
        rowGrandTotals=True,
        colGrandTotals=True,
        compact=False,
        compactData=False,
        gridDropZones=False,
    )
    pivot.cache = cache
    sheet.add_pivot(pivot)
    sheet.freeze_panes = "B7"
    sheet.print_options.horizontalCentered = True
    sheet.print_area = f"A1:S{grand_row}"
    sheet.sheet_properties.pageSetUpPr.fitToPage = True
    sheet.page_setup.orientation = "landscape"
    sheet.page_setup.paperSize = sheet.PAPERSIZE_A3
    sheet.page_setup.fitToWidth = 1
    sheet.page_setup.fitToHeight = 0
    source.print_area = "A1:D24"
    book.save(path)
