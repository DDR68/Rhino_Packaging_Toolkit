#! python 2
# -*- coding: utf-8 -*-
import Rhino
import scriptcontext as sc
import System


def get_selection():
    selected = list(sc.doc.Objects.GetSelectedObjects(False, False))
    if selected:
        return selected
    go = Rhino.Input.Custom.GetObject()
    go.SetCommandPrompt("Seleziona oggetti per il calcolo del formato")
    go.GroupSelect = True
    go.SubObjectSelect = False
    go.GetMultiple(1, 0)
    if go.CommandResult() != Rhino.Commands.Result.Success:
        return None
    result = []
    for i in range(go.ObjectCount):
        obj = go.Object(i).Object()
        if obj:
            result.append(obj)
    return result if result else None


def compute_bbox(objs):
    bbox = Rhino.Geometry.BoundingBox.Empty
    for obj in objs:
        geom = obj.Geometry
        if geom is not None:
            bbox.Union(geom.GetBoundingBox(True))
    return bbox if bbox.IsValid else None


def ensure_layer(name, r, g, b):
    idx = sc.doc.Layers.FindByFullPath(name, -1)
    if idx < 0:
        layer = Rhino.DocObjects.Layer()
        layer.Name = name
        layer.Color = System.Drawing.Color.FromArgb(r, g, b)
        idx = sc.doc.Layers.Add(layer)
    else:
        layer = sc.doc.Layers[idx]
        layer.Color = System.Drawing.Color.FromArgb(r, g, b)
        sc.doc.Layers.Modify(layer, idx, True)
    return idx


def main():
    sizes_cm = [
        (35, 25),
        (35, 50),
        (50, 70),
        (100, 70),
        (101, 71),
        (102, 72),
        (120, 80),
        (140, 100),
        (160, 120),
    ]

    objs = get_selection()
    if not objs:
        print("Nessun oggetto selezionato.")
        return

    bbox = compute_bbox(objs)
    if bbox is None:
        print("Impossibile calcolare il bounding box.")
        return

    bb_dx = bbox.Max.X - bbox.Min.X
    bb_dy = bbox.Max.Y - bbox.Min.Y

    bb_long = max(bb_dx, bb_dy)
    bb_short = min(bb_dx, bb_dy)

    scale = Rhino.RhinoMath.UnitScale(
        Rhino.UnitSystem.Centimeters, sc.doc.ModelUnitSystem
    )

    best = None
    best_area = float("inf")
    best_cm = None

    for w_cm, h_cm in sizes_cm:
        long_side = max(w_cm, h_cm) * scale
        short_side = min(w_cm, h_cm) * scale
        if long_side >= bb_long and short_side >= bb_short:
            area = long_side * short_side
            if area < best_area:
                best_area = area
                best = (long_side, short_side)
                best_cm = (max(w_cm, h_cm), min(w_cm, h_cm))

    if best is None:
        print(
            "Nessun formato standard contiene la selezione "
            "({0:.1f} x {1:.1f}).".format(bb_dx, bb_dy)
        )
        return

    if bb_dx >= bb_dy:
        rect_w, rect_h = best[0], best[1]
    else:
        rect_w, rect_h = best[1], best[0]

    cx = (bbox.Min.X + bbox.Max.X) * 0.5
    cy = (bbox.Min.Y + bbox.Max.Y) * 0.5
    z = bbox.Min.Z

    p0 = Rhino.Geometry.Point3d(cx - rect_w * 0.5, cy - rect_h * 0.5, z)
    p1 = Rhino.Geometry.Point3d(cx + rect_w * 0.5, cy - rect_h * 0.5, z)
    p2 = Rhino.Geometry.Point3d(cx + rect_w * 0.5, cy + rect_h * 0.5, z)
    p3 = Rhino.Geometry.Point3d(cx - rect_w * 0.5, cy + rect_h * 0.5, z)

    pline = Rhino.Geometry.Polyline([p0, p1, p2, p3, p0])
    crv = pline.ToNurbsCurve()
    if crv is None:
        print("Errore nella creazione della curva.")
        return

    layer_idx = ensure_layer("Quote", 105, 105, 105)

    attr = Rhino.DocObjects.ObjectAttributes()
    attr.LayerIndex = layer_idx
    attr.ColorSource = Rhino.DocObjects.ObjectColorSource.ColorFromObject
    attr.ObjectColor = System.Drawing.Color.FromArgb(105, 105, 105)

    guid = sc.doc.Objects.AddCurve(crv, attr)
    if guid == System.Guid.Empty:
        print("Errore nell'aggiunta della curva al documento.")
        return

    sc.doc.Views.Redraw()
    print(
        "Formato: {0}x{1} cm - Rettangolo aggiunto al livello 'Quote'.".format(
            int(best_cm[0]), int(best_cm[1])
        )
    )


main()
