# -*- coding: utf-8 -*-
import Rhino
import scriptcontext as sc
import System


def get_or_select_objects():
    """Verifica selezione attiva, altrimenti chiede selezione interattiva."""
    selected = list(sc.doc.Objects.GetSelectedObjects(False, False))
    valid = []
    if selected:
        for obj in selected:
            ot = obj.ObjectType
            if (ot == Rhino.DocObjects.ObjectType.Curve or
                    ot == Rhino.DocObjects.ObjectType.Annotation):
                valid.append(obj)
        if valid:
            return valid

    go = Rhino.Input.Custom.GetObject()
    go.SetCommandPrompt("Seleziona curve e quote")
    go.GeometryFilter = (Rhino.DocObjects.ObjectType.Curve |
                         Rhino.DocObjects.ObjectType.Annotation)
    go.SubObjectSelect = False
    go.GroupSelect = True
    go.GetMultiple(1, 0)
    if go.CommandResult() != Rhino.Commands.Result.Success:
        return None

    objs = []
    for i in range(go.ObjectCount):
        robj = go.Object(i).Object()
        if robj is not None:
            objs.append(robj)
    return objs if objs else None


def ensure_layer(name, color):
    """Crea il layer se non esiste, restituisce l'indice."""
    idx = sc.doc.Layers.FindByFullPath(name, -1)
    if idx >= 0:
        return idx
    layer = Rhino.DocObjects.Layer()
    layer.Name = name
    layer.Color = color
    idx = sc.doc.Layers.Add(layer)
    if idx < 0:
        raise Exception("Impossibile creare il layer '%s'" % name)
    return idx


def build_attributes(layer_idx, color, plot_weight_mm):
    """Attributi: colore da oggetto, tipo linea Continua da layer, larghezza stampa da oggetto."""
    attr = Rhino.DocObjects.ObjectAttributes()
    attr.LayerIndex = layer_idx
    attr.ColorSource = Rhino.DocObjects.ObjectColorSource.ColorFromObject
    attr.ObjectColor = color
    attr.LinetypeSource = Rhino.DocObjects.ObjectLinetypeSource.LinetypeFromLayer
    attr.PlotWeightSource = Rhino.DocObjects.ObjectPlotWeightSource.PlotWeightFromObject
    attr.PlotWeight = plot_weight_mm
    return attr


def add_crosshair(center, half, attr):
    """Disegna un crocino (due segmenti ortogonali) centrato su center."""
    p_left  = Rhino.Geometry.Point3d(center.X - half, center.Y, center.Z)
    p_right = Rhino.Geometry.Point3d(center.X + half, center.Y, center.Z)
    p_down  = Rhino.Geometry.Point3d(center.X, center.Y - half, center.Z)
    p_up    = Rhino.Geometry.Point3d(center.X, center.Y + half, center.Z)

    line_h = Rhino.Geometry.Line(p_left, p_right)
    line_v = Rhino.Geometry.Line(p_down, p_up)
    id_h = sc.doc.Objects.AddLine(line_h, attr)
    id_v = sc.doc.Objects.AddLine(line_v, attr)

    if id_h == System.Guid.Empty or id_v == System.Guid.Empty:
        print("Attenzione: crocino non aggiunto correttamente.")
        return False
    return True


def main():
    objs = get_or_select_objects()
    if not objs:
        print("Nessun oggetto valido selezionato. Operazione annullata.")
        return

    bbox = Rhino.Geometry.BoundingBox.Empty
    for obj in objs:
        geom = obj.Geometry
        if geom is None:
            continue
        b = geom.GetBoundingBox(True)
        if b.IsValid:
            bbox.Union(b)

    if not bbox.IsValid:
        print("BoundingBox non valida. Verificare la selezione.")
        return

    scale = Rhino.RhinoMath.UnitScale(
        Rhino.UnitSystem.Millimeters, sc.doc.ModelUnitSystem)
    half_size = 10.0 * scale

    blue = System.Drawing.Color.FromArgb(0, 0, 255)
    layer_idx = ensure_layer("Crocini", blue)
    attr = build_attributes(layer_idx, blue, 0.5)

    corners = [
        Rhino.Geometry.Point3d(bbox.Min.X, bbox.Min.Y, bbox.Min.Z),
        Rhino.Geometry.Point3d(bbox.Max.X, bbox.Min.Y, bbox.Min.Z),
        Rhino.Geometry.Point3d(bbox.Max.X, bbox.Max.Y, bbox.Min.Z),
        Rhino.Geometry.Point3d(bbox.Min.X, bbox.Max.Y, bbox.Min.Z),
    ]

    count = 0
    for corner in corners:
        if add_crosshair(corner, half_size, attr):
            count += 1

    sc.doc.Views.Redraw()
    print("%d crocini creati sugli angoli della BoundingBox." % count)


main()
