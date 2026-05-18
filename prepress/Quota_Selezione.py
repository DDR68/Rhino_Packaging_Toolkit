#! python 2
# -*- coding: utf-8 -*-
import Rhino
import Rhino.Geometry as rg
import Rhino.DocObjects as rd
import Rhino.Input.Custom as ric
import scriptcontext as sc
import System
import math


def get_or_create_layer(name, r, g, b):
    idx = sc.doc.Layers.FindByFullPath(name, -1)
    if idx < 0:
        layer = rd.Layer()
        layer.Name = name
        layer.Color = System.Drawing.Color.FromArgb(r, g, b)
        idx = sc.doc.Layers.Add(layer)
    return idx


def create_dim_style():
    style_name = "QuotaSelezione"

    # cerca stile esistente
    existing = sc.doc.DimStyles.FindName(style_name)
    if existing is not None:
        return existing.Index

    # conversione unita: tutto in unita documento
    scale = Rhino.RhinoMath.UnitScale(
        Rhino.UnitSystem.Millimeters, sc.doc.ModelUnitSystem
    )

    # Rhino 7: DimStyles.Add() vuole una stringa (nome stile)
    idx = sc.doc.DimStyles.Add(style_name)
    if idx < 0:
        print("Errore: impossibile creare DimensionStyle")
        return sc.doc.DimStyles.CurrentDimensionStyleIndex

    ds = sc.doc.DimStyles[idx]
    if ds is None:
        return sc.doc.DimStyles.CurrentDimensionStyleIndex

    ds.TextHeight = 10.0 * scale
    ds.ArrowLength = 8.0 * scale
    ds.TextGap = 2.0 * scale
    ds.ExtensionLineOffset = 2.0 * scale
    ds.ExtensionLineExtension = 0.0

    # testo allineato sulla linea di quota (InDimLine)
    ds.DimTextLocation = rd.DimensionStyle.TextLocation.InDimLine

    # elimina linee di estensione 1 e 2
    ds.SuppressExtension1 = True
    ds.SuppressExtension2 = True

    # suffisso mm
    ds.Suffix = " mm"

    # fattore di conversione: il valore quotato in mm
    unit_to_mm = Rhino.RhinoMath.UnitScale(
        sc.doc.ModelUnitSystem, Rhino.UnitSystem.Millimeters
    )
    ds.LengthFactor = unit_to_mm

    # risoluzione decimale
    ds.LengthResolution = 2

    # applica modifiche al documento
    sc.doc.DimStyles.Modify(ds, idx, True)

    return idx


def collect_selection():
    sel = list(sc.doc.Objects.GetSelectedObjects(False, False))
    curves = []
    dims = []
    for obj in sel:
        if obj is None:
            continue
        geom = obj.Geometry
        if geom is None:
            continue
        if isinstance(geom, rg.Curve):
            curves.append(obj)
        elif isinstance(geom, rg.LinearDimension):
            dims.append(obj)

    if len(curves) == 0 and len(dims) == 0:
        return None, None
    return curves, dims


def ask_selection():
    go = ric.GetObject()
    go.SetCommandPrompt("Seleziona curve e/o quote")
    go.GeometryFilter = (
        rd.ObjectType.Curve | rd.ObjectType.Annotation
    )
    go.SubObjectSelect = False
    go.GroupSelect = True
    go.EnablePreSelect(False, True)
    go.GetMultiple(1, 0)
    if go.CommandResult() != Rhino.Commands.Result.Success:
        return None, None

    curves = []
    dims = []
    for i in range(go.ObjectCount):
        obj = go.Object(i).Object()
        if obj is None:
            continue
        geom = obj.Geometry
        if geom is None:
            continue
        if isinstance(geom, rg.Curve):
            curves.append(obj)
        elif isinstance(geom, rg.LinearDimension):
            dims.append(obj)

    if len(curves) == 0 and len(dims) == 0:
        return None, None
    return curves, dims


def compute_curves_bbox(curves):
    pts = []
    for obj in curves:
        geom = obj.Geometry
        if geom is None:
            continue
        b = geom.GetBoundingBox(True)
        if b.IsValid:
            pts.append(b.Min)
            pts.append(b.Max)
    if len(pts) == 0:
        return rg.BoundingBox.Empty
    return rg.BoundingBox(pts)


def add_horizontal_dim(bbox, ds_idx, layer_idx, offset):
    """Quota orizzontale sul lato inferiore della BoundingBox."""
    style = sc.doc.DimStyles[ds_idx]
    if style is None:
        print("Errore: DimensionStyle non trovato")
        return False

    pt1 = rg.Point3d(bbox.Min.X, bbox.Min.Y, 0)
    pt2 = rg.Point3d(bbox.Max.X, bbox.Min.Y, 0)
    dim_pt = rg.Point3d(
        (bbox.Min.X + bbox.Max.X) * 0.5,
        bbox.Min.Y - offset,
        0
    )

    plane = rg.Plane.WorldXY
    horizontal = rg.Vector3d.XAxis

    dim = rg.LinearDimension.Create(
        rg.AnnotationType.Rotated,
        style,
        plane,
        horizontal,
        pt1,
        pt2,
        dim_pt,
        0.0
    )

    if dim is None:
        print("Errore: impossibile creare quota orizzontale")
        return False

    attr = rd.ObjectAttributes()
    attr.LayerIndex = layer_idx
    attr.ColorSource = rd.ObjectColorSource.ColorFromLayer

    guid = sc.doc.Objects.AddLinearDimension(dim, attr)
    if guid == System.Guid.Empty:
        print("Errore: impossibile aggiungere quota orizzontale al documento")
        return False
    return True


def add_vertical_dim(bbox, ds_idx, layer_idx, offset):
    """Quota verticale sul lato destro della BoundingBox."""
    style = sc.doc.DimStyles[ds_idx]
    if style is None:
        print("Errore: DimensionStyle non trovato")
        return False

    pt1 = rg.Point3d(bbox.Max.X, bbox.Min.Y, 0)
    pt2 = rg.Point3d(bbox.Max.X, bbox.Max.Y, 0)
    dim_pt = rg.Point3d(
        bbox.Max.X + offset,
        (bbox.Min.Y + bbox.Max.Y) * 0.5,
        0
    )

    plane = rg.Plane.WorldXY
    horizontal = rg.Vector3d.XAxis

    dim = rg.LinearDimension.Create(
        rg.AnnotationType.Rotated,
        style,
        plane,
        horizontal,
        pt1,
        pt2,
        dim_pt,
        math.pi / 2.0
    )

    if dim is None:
        print("Errore: impossibile creare quota verticale")
        return False

    attr = rd.ObjectAttributes()
    attr.LayerIndex = layer_idx
    attr.ColorSource = rd.ObjectColorSource.ColorFromLayer

    guid = sc.doc.Objects.AddLinearDimension(dim, attr)
    if guid == System.Guid.Empty:
        print("Errore: impossibile aggiungere quota verticale al documento")
        return False
    return True


def main():
    # 1. Verifica selezione attiva, altrimenti chiedi
    curves, dims = collect_selection()
    if curves is None:
        print("Nessuna selezione attiva, seleziona curve e/o quote...")
        curves, dims = ask_selection()
        if curves is None:
            print("Nessun oggetto valido selezionato.")
            return

    if len(curves) == 0:
        print("Nessuna curva nella selezione, impossibile calcolare BoundingBox.")
        return

    print("Curve selezionate: %d" % len(curves))
    if dims is not None and len(dims) > 0:
        print("Quote selezionate: %d" % len(dims))

    # 2. Calcola BoundingBox dalle curve
    bbox = compute_curves_bbox(curves)
    if not bbox.IsValid:
        print("Errore: BoundingBox non valida.")
        return

    print("BoundingBox Min: %.3f, %.3f" % (bbox.Min.X, bbox.Min.Y))
    print("BoundingBox Max: %.3f, %.3f" % (bbox.Max.X, bbox.Max.Y))

    # 3. Prepara layer e stile
    layer_idx = get_or_create_layer("Quote", 105, 105, 105)
    ds_idx = create_dim_style()

    # offset della linea di quota dalla bbox
    scale = Rhino.RhinoMath.UnitScale(
        Rhino.UnitSystem.Millimeters, sc.doc.ModelUnitSystem
    )
    offset = 15.0 * scale

    # 4. Quota lato inferiore (orizzontale)
    ok_h = add_horizontal_dim(bbox, ds_idx, layer_idx, offset)
    if ok_h:
        print("Quota orizzontale (lato inferiore) creata.")

    # 5. Quota lato destro (verticale)
    ok_v = add_vertical_dim(bbox, ds_idx, layer_idx, offset)
    if ok_v:
        print("Quota verticale (lato destro) creata.")

    sc.doc.Views.Redraw()

    if ok_h and ok_v:
        print("Quote create con successo.")
    else:
        print("Attenzione: alcune quote non sono state create.")


if __name__ == "__main__":
    main()
