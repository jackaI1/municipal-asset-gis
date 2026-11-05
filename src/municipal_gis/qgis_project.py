"""Create a portable QGIS project and an A3 landscape print layout with PyQGIS."""

import argparse
import json
import math
import os
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
# A standalone, shareable GeoPackage must not depend on WAL sidecar files.
# QGIS otherwise mixes pooled NOLOCK readers with WAL-capable connections.
os.environ["OGR_SQLITE_JOURNAL"] = "DELETE"
from qgis.PyQt.QtGui import QColor, QFont
from qgis.core import (
    Qgis,
    QgsApplication,
    QgsProject,
    QgsVectorLayer,
    QgsCoordinateReferenceSystem,
    QgsLineSymbol,
    QgsRendererCategory,
    QgsCategorizedSymbolRenderer,
    QgsRendererRange,
    QgsGraduatedSymbolRenderer,
    QgsPrintLayout,
    QgsLayoutItemMap,
    QgsLayoutItemLabel,
    QgsLayoutItemLegend,
    QgsLayoutItemScaleBar,
    QgsLayoutPoint,
    QgsLayoutSize,
    QgsLayoutExporter,
    QgsLayoutItemPage,
    QgsReferencedRectangle,
)

COLORS = ["#177C66", "#73A857", "#E1AD38", "#D46B32", "#A12B3A"]


def create_project(output):
    output = Path(output).resolve()
    project = QgsProject.instance()
    project.clear()
    project.setCrs(QgsCoordinateReferenceSystem("EPSG:26917"))
    project.setFilePathStorage(Qgis.FilePathType.Relative)
    project.setTitle("Waterloo synthetic utility replacement planning")
    package = output / "assets.gpkg"
    root = project.layerTreeRoot()
    age_group = root.addGroup("Age view (turn on to inspect)")
    condition_group = root.addGroup("Condition view")
    condition_layers = []
    for system in ["Water", "Sanitary", "Stormwater"]:
        for view in ["condition", "age"]:
            layer = QgsVectorLayer(
                f"{package}|layername=assets", f"{system} | {view}", "ogr"
            )
            if not layer.isValid():
                raise RuntimeError("Cannot load asset layer")
            if not layer.setSubsetString(f"\"system\" = '{system}'"):
                raise RuntimeError(f"Cannot filter {system} assets")
            if view == "condition":
                categories = [
                    QgsRendererCategory(
                        i,
                        QgsLineSymbol.createSimple(
                            {"line_color": color, "line_width": "0.65"}
                        ),
                        f"{i} {label}",
                    )
                    for i, color, label in zip(
                        range(1, 6),
                        COLORS,
                        ["Good", "Fair", "Moderate", "Poor", "Very poor"],
                    )
                ]
                layer.setRenderer(QgsCategorizedSymbolRenderer("condition", categories))
            else:
                ranges = [
                    QgsRendererRange(
                        low,
                        high,
                        QgsLineSymbol.createSimple(
                            {"line_color": color, "line_width": "0.65"}
                        ),
                        label,
                    )
                    for low, high, color, label in [
                        (0, 20, "#C8DDF0", "0-20 years"),
                        (20, 40, "#86AFCF", "21-40 years"),
                        (40, 60, "#4D7EA8", "41-60 years"),
                        (60, 350, "#21446A", "61+ years"),
                    ]
                ]
                layer.setRenderer(QgsGraduatedSymbolRenderer("age_years", ranges))
            layer.setDisplayExpression('"asset_id"')
            layer.setMapTipTemplate(
                '<b>[% "asset_id" %]</b><br>Priority: [% "priority_score" %]/100<br>Age: [% "age_years" %] years<br>Replacement year: [% "replacement_year" %]'
            )
            project.addMapLayer(layer, False)
            (condition_group if view == "condition" else age_group).addLayer(layer)
            if view == "condition":
                condition_layers.append(layer)
    age_group.setItemVisibilityChecked(False)
    roads = QgsVectorLayer(
        f"{package}|layername=roads", "Public roads | City of Waterloo", "ogr"
    )
    if (
        not roads.isValid()
        or roads.featureCount() <= 0
        or roads.crs().authid() != "EPSG:26917"
    ):
        raise RuntimeError("Cannot read projected road features")
    roads.renderer().setSymbol(
        QgsLineSymbol.createSimple({"line_color": "#BFC8CE", "line_width": "0.25"})
    )
    project.addMapLayer(roads)
    # Roads remain beneath the utility layers in the canvas.
    root.setHasCustomLayerOrder(True)
    root.setCustomLayerOrder(
        condition_layers + [roads] + [n.layer() for n in age_group.findLayers()]
    )
    extent = roads.extent()
    if extent.isEmpty() or not all(
        math.isfinite(v)
        for v in [
            extent.xMinimum(),
            extent.xMaximum(),
            extent.yMinimum(),
            extent.yMaximum(),
        ]
    ):
        raise RuntimeError("Road extent is empty or non-finite")
    extent.scale(1.08)
    project.viewSettings().setDefaultViewExtent(
        QgsReferencedRectangle(extent, project.crs())
    )
    layout = QgsPrintLayout(project)
    layout.initializeDefaults()
    layout.setName("Replacement planning | A3")
    layout.pageCollection().page(0).setPageSize("A3", QgsLayoutItemPage.Landscape)

    def label(text, x, y, width, height, size=11, bold=False):
        item = QgsLayoutItemLabel(layout)
        item.setText(text)
        item.setFont(QFont("DejaVu Sans", size, QFont.Bold if bold else QFont.Normal))
        item.setFontColor(QColor("#233E52"))
        layout.addLayoutItem(item)
        item.attemptMove(QgsLayoutPoint(x, y))
        item.attemptResize(QgsLayoutSize(width, height))
        return item

    label("WATERLOO | UTILITY REPLACEMENT", 12, 8, 390, 15, 22, True)
    label(
        "Synthetic asset registry on public Ontario road geometry", 12, 24, 390, 10, 12
    )
    map_item = QgsLayoutItemMap(layout)
    map_item.setId("main_map")
    layout.addLayoutItem(map_item)
    map_item.attemptMove(QgsLayoutPoint(12, 42))
    map_item.attemptResize(QgsLayoutSize(285, 225))
    map_item.setCrs(project.crs())
    map_item.setLayers(condition_layers + [roads])
    map_item.setKeepLayerSet(True)
    map_item.zoomToExtent(extent)
    map_item.setBackgroundColor(QColor("#F5F7F8"))
    map_item.setBackgroundEnabled(True)
    map_item.setFrameEnabled(True)
    label("CONDITION", 308, 43, 95, 10, 13, True)
    legend = QgsLayoutItemLegend(layout)
    legend.setTitle("")
    legend.setAutoUpdateModel(False)
    # One condition legend is enough because all three systems use the same scale.
    legend.model().rootGroup().clear()
    legend.model().rootGroup().addLayer(condition_layers[0])
    layout.addLayoutItem(legend)
    legend.attemptMove(QgsLayoutPoint(308, 57))
    legend.attemptResize(QgsLayoutSize(95, 55))
    label("N ↑", 274, 45, 20, 12, 15, True)
    scale = QgsLayoutItemScaleBar(layout)
    scale.setId("scale_bar")
    scale.setStyle("Single Box")
    scale.setLinkedMap(map_item)
    scale.applyDefaultSize()
    scale.setNumberOfSegments(2)
    scale.setNumberOfSegmentsLeft(0)
    scale.setUnits(Qgis.DistanceUnit.Meters)
    scale.setUnitsPerSegment(250)
    scale.setUnitLabel("m")
    scale.setFont(QFont("DejaVu Sans", 9))
    layout.addLayoutItem(scale)
    scale.attemptMove(QgsLayoutPoint(20, 251))
    summary = (
        json.loads((output / "summary.json").read_text())
        if (output / "summary.json").exists()
        else None
    )
    if summary:
        label(
            f"{summary['assets']:,} synthetic assets\n{summary['length_km']:,.1f} km of pipe\n{summary['due_now']:,} due in {summary['base_year']}\n${summary['replacement_cost_cad'] / 1e6:,.1f}M current replacement cost",
            308,
            124,
            99,
            37,
            11,
        )
    label("READING THIS MAP", 308, 166, 95, 10, 12, True)
    label(
        "Water, sanitary and stormwater\nare drawn on road corridors.\nOffsets separate invented pipes.\n\nPriority: 60% condition, 30% age,\n10% unit cost exposure.\n\nAge view is available in the\nQGIS Layers panel.",
        308,
        179,
        99,
        65,
        10,
    )
    label(
        "SYNTHETIC DATA | NOT FOR EXCAVATION OR MUNICIPAL BUDGETS",
        12,
        273,
        390,
        8,
        11,
        True,
    )
    label(
        "Roads: City of Waterloo Open Data Licence | NAD83 / UTM 17N (metres) | Sample costs in CAD",
        12,
        283,
        395,
        7,
        9,
    )
    project.layoutManager().addLayout(layout)
    if not project.write(str(output / "municipal_assets.qgz")):
        raise RuntimeError("QGIS save failed")
    exporter = QgsLayoutExporter(layout)
    settings = QgsLayoutExporter.PdfExportSettings()
    settings.dpi = 180
    if (
        exporter.exportToPdf(str(output / "replacement_map.pdf"), settings)
        != QgsLayoutExporter.Success
    ):
        raise RuntimeError("PDF export failed")
    settings = QgsLayoutExporter.ImageExportSettings()
    settings.dpi = 110
    if (
        exporter.exportToImage(str(output / "replacement_map.png"), settings)
        != QgsLayoutExporter.Success
    ):
        raise RuntimeError("PNG export failed")
    project.clear()
    print("Created QGIS project, A3 print layout, PDF and PNG")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=Path("outputs"))
    args = parser.parse_args()
    app = QgsApplication([], False)
    app.initQgis()
    try:
        create_project(args.out)
    finally:
        app.exitQgis()


if __name__ == "__main__":
    main()
