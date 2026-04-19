# -*- coding: utf-8 -*-
"""
Script: Esporta_Geometrie_Semplice_V.3.py
Versione: 3.0
Compatibilita: Rhino 7/8 - IronPython 2.7 - RhinoCommon

Correzioni rispetto alla V.2:
- FIX: angoli arco con Normal.Z < 0 (piano locale invertito)
  arc.StartAngle/EndAngle sono SEMPRE positivi nel piano locale,
  ma quando il piano e capovolto (Normal.Z<0) gli angoli vanno negati
  per indicare sweep CW nel piano globale XY.
- PolyCurve esplosa in segmenti individuali
- isinstance() prima di TryGet per rilevamento tipo affidabile
- Centro arco esportato (CX, CY)
- Pesi NURBS inclusi per curve razionali
- Punti campionati per curve complesse

Se lanciato SENZA selezione: mostra finestra di aiuto.
"""

import Rhino
import Rhino.Geometry as rg
import scriptcontext as sc
import math
import os


# ============================================================
#  HELP DIALOG
# ============================================================

def show_help():
    import Eto.Forms as ef
    import Eto.Drawing as ed

    dlg = ef.Dialog()
    dlg.Title = "Esporta Geometrie Semplice v3.0 - Guida"
    dlg.Padding = ed.Padding(16)
    dlg.MinimumSize = ed.Size(580, 480)
    dlg.Resizable = True

    layout = ef.DynamicLayout()
    layout.Spacing = ed.Size(8, 8)

    title = ef.Label()
    title.Text = "ESPORTA GEOMETRIE SEMPLICE v3.0"
    title.Font = ed.Font(ed.SystemFont.Bold, 13)
    layout.AddRow(title)
    layout.AddRow(ef.Label(Text=""))

    help_text = (
        "UTILIZZO\n"
        "Selezionare le curve, poi lanciare lo script.\n"
        "Senza selezione si apre questa guida.\n\n"
        "NOVITA v3.0\n"
        "- FIX: angoli arco corretti per archi con piano invertito\n"
        "  (Normal.Z < 0 => angoli negati per sweep CW)\n"
        "- PolyCurve esplosa automaticamente in segmenti\n"
        "- Archi: centro (CX,CY) esportato\n"
        "- Nurbs: pesi CP inclusi se razionali\n"
        "- Punti campionati per curve complesse\n\n"
        "TIPI\n"
        "T=Taglio  C=Cordone  M=MezzoTaglio  F=Foratore\n\n"
        "CONVENZIONI COLORE\n"
        "Nero(0,0,0) = Taglio\n"
        "Rosso(255,0,0) = Cordone\n"
        "Verde(0,255,0) = MezzoTaglio\n"
        "Blu(0,0,255) = Foratore\n\n"
        "FORMATO OUTPUT\n"
        "ID  Tipo  Geom  X1  Y1  X2  Y2  R  CX  CY  AngS  AngE  Len  [extra]\n"
        "Nurbs: + Deg  Pts  CP(x,y[,w];...)  [Sampled(x,y;...)]\n"
        "Poly: + Vertici(x,y;...)\n"
    )
    lbl = ef.Label()
    lbl.Text = help_text
    layout.AddRow(lbl)

    btn = ef.Button()
    btn.Text = "Chiudi"
    btn.Click += lambda s, e: dlg.Close()
    layout.AddRow(None, btn)

    dlg.Content = layout
    dlg.ShowModal()


# ============================================================
#  UTILITIES
# ============================================================

DECIMALS = 1

def fmt(val, decimals=None):
    if decimals is None:
        decimals = DECIMALS
    return str(round(val, decimals))

def fmt_pt(pt):
    return "%s\t%s" % (fmt(pt.X), fmt(pt.Y))

def classify_curve(obj):
    layer = sc.doc.Layers[obj.Attributes.LayerIndex]
    lname = layer.Name.lower().strip()

    if "mezzotaglio" in lname or "mezzo_taglio" in lname or "mezzo taglio" in lname:
        return "M"
    if "foratore" in lname or "foratura" in lname:
        return "F"
    if "cordone" in lname or "cordonatura" in lname or "piega" in lname:
        return "C"
    if "taglio" in lname or "cut" in lname or "fustella" in lname:
        return "T"

    attr = obj.Attributes
    if attr.ColorSource == Rhino.DocObjects.ObjectColorSource.ColorFromLayer:
        color = layer.Color
    else:
        color = attr.ObjectColor

    r, g, b = int(color.R), int(color.G), int(color.B)

    if r > 200 and g < 60 and b < 60:
        return "C"
    if r < 60 and g > 200 and b < 60:
        return "M"
    if r < 60 and g < 60 and b > 200:
        return "F"
    return "T"


# ============================================================
#  EXPLODE: PolyCurve -> segmenti singoli
# ============================================================

def explode_curve(curve):
    if isinstance(curve, rg.PolyCurve):
        segments = []
        for i in range(curve.SegmentCount):
            seg = curve.SegmentCurve(i)
            if seg is not None:
                segments.extend(explode_curve(seg))
        return segments

    if isinstance(curve, rg.PolylineCurve):
        pl = curve.ToPolyline()
        if pl is not None and pl.Count > 1:
            lines = []
            for i in range(pl.Count - 1):
                line = rg.LineCurve(pl[i], pl[i + 1])
                lines.append(line)
            return lines
        return [curve]

    return [curve]


# ============================================================
#  EXTRACT ARC ANGLES (con correzione piano invertito)
# ============================================================

def extract_arc_data(arc):
    """Estrae dati arco con angoli corretti per il piano globale XY.
    
    arc.StartAngle e arc.EndAngle sono misurati nel piano LOCALE dell'arco
    e sono sempre positivi (0..2pi). Se il piano e invertito (Normal.Z < 0)
    l'arco appare CW nel piano globale XY e gli angoli vanno negati.
    """
    cx = arc.Center.X
    cy = arc.Center.Y
    start_deg = math.degrees(arc.StartAngle)
    end_deg = math.degrees(arc.EndAngle)

    # Correzione: se il piano dell'arco e capovolto, gli angoli
    # nel sistema globale sono negativi (sweep clockwise)
    if arc.Plane.Normal.Z < 0:
        start_deg = -start_deg
        end_deg = -end_deg

    return {
        "R": fmt(arc.Radius),
        "CX": fmt(cx),
        "CY": fmt(cy),
        "AngStart": fmt(start_deg),
        "AngEnd": fmt(end_deg),
    }


# ============================================================
#  DETECT GEOMETRY
# ============================================================

def detect_geometry(curve):
    # 1) LineCurve esplicita
    if isinstance(curve, rg.LineCurve):
        return "Line", {}

    # 2) Qualsiasi curva lineare
    if curve.IsLinear():
        return "Line", {}

    # 3) ArcCurve esplicita
    if isinstance(curve, rg.ArcCurve):
        return "Arc", extract_arc_data(curve.Arc)

    # 4) TryGetArc (nurbs che rappresentano archi)
    success, arc = curve.TryGetArc()
    if success:
        return "Arc", extract_arc_data(arc)

    # 5) Polilinea residua
    success_pl, polyline = curve.TryGetPolyline()
    if success_pl:
        pts_str = ";".join(
            "%s,%s" % (fmt(polyline[i].X), fmt(polyline[i].Y))
            for i in range(polyline.Count)
        )
        return "Poly", {"Pts": pts_str}

    # 6) NurbsCurve
    nurbs = curve if isinstance(curve, rg.NurbsCurve) else curve.ToNurbsCurve()
    if nurbs is not None:
        deg = nurbs.Degree
        is_rational = nurbs.IsRational
        n_pts = nurbs.Points.Count

        cp_parts = []
        for i in range(n_pts):
            cp = nurbs.Points[i]
            pt = cp.Location
            if is_rational:
                w = round(cp.Weight, 4)
                cp_parts.append("%s,%s,%s" % (fmt(pt.X), fmt(pt.Y), w))
            else:
                cp_parts.append("%s,%s" % (fmt(pt.X), fmt(pt.Y)))
        cp_str = ";".join(cp_parts)

        extras = {"Deg": str(deg), "Pts": str(n_pts), "CP": cp_str}

        if deg > 2 or n_pts > 4:
            n_samples = max(20, n_pts * 4)
            domain = nurbs.Domain
            sampled = []
            for i in range(n_samples + 1):
                t = domain.T0 + (domain.T1 - domain.T0) * i / n_samples
                sp = nurbs.PointAt(t)
                sampled.append("%s,%s" % (fmt(sp.X), fmt(sp.Y)))
            extras["Sampled"] = ";".join(sampled)

        return "Nurbs", extras

    return "Unknown", {}


# ============================================================
#  FORMAT ROW
# ============================================================

def format_row(idx, tipo, curve):
    geom_tag, extras = detect_geometry(curve)
    length = fmt(curve.GetLength())
    x1y1 = fmt_pt(curve.PointAtStart)
    x2y2 = fmt_pt(curve.PointAtEnd)

    r_val = extras.get("R", "_")
    cx_val = extras.get("CX", "_")
    cy_val = extras.get("CY", "_")
    ang_s = extras.get("AngStart", "_")
    ang_e = extras.get("AngEnd", "_")

    row = "%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s" % (
        idx, tipo, geom_tag,
        x1y1, x2y2,
        r_val, cx_val, cy_val, ang_s, ang_e
    )
    row += "\t%s" % length

    if geom_tag == "Nurbs":
        row += "\t%s\t%s\t%s" % (
            extras.get("Deg", "_"),
            extras.get("Pts", "_"),
            extras.get("CP", "_")
        )
        if "Sampled" in extras:
            row += "\t%s" % extras["Sampled"]

    if geom_tag == "Poly":
        row += "\t%s" % extras.get("Pts", "_")

    return row


# ============================================================
#  EXPORT
# ============================================================

def export_curves(curve_objs):
    doc_name = sc.doc.Name or "senza_nome"
    unit_str = str(sc.doc.ModelUnitSystem)

    all_bbox = rg.BoundingBox.Empty
    for obj in curve_objs:
        bb = obj.Geometry.GetBoundingBox(True)
        if bb.IsValid:
            all_bbox.Union(bb)

    if all_bbox.IsValid:
        bbox_w = round(all_bbox.Max.X - all_bbox.Min.X, 1)
        bbox_h = round(all_bbox.Max.Y - all_bbox.Min.Y, 1)
        bbox_str = "%s x %s" % (bbox_w, bbox_h)
    else:
        bbox_str = "n/a"

    lines = []
    lines.append("# %s | bbox: %s | unita: %s" % (doc_name, bbox_str, unit_str))
    lines.append("# Tipo: T=Taglio  C=Cordone  M=MezzoTaglio  F=Foratore")
    lines.append("# ID\tTipo\tGeom\tX1\tY1\tX2\tY2\tR\tCX\tCY\tAngS\tAngE\tLen\t...")

    n_original = len(curve_objs)
    n_exploded = 0
    n_total = 0

    for obj in curve_objs:
        curve = obj.Geometry
        if curve is None:
            continue

        tipo = classify_curve(obj)
        segments = explode_curve(curve)

        if len(segments) > 1:
            n_exploded += 1

        for seg in segments:
            row = format_row(n_total, tipo, seg)
            lines.append(row)
            n_total += 1

    lines[0] = "# %s | bbox: %s | obj: %d | segm: %d | exploded: %d | unita: %s" % (
        doc_name, bbox_str, n_original, n_total, n_exploded, unit_str)

    doc_path = sc.doc.Path
    folder = os.path.dirname(doc_path) if doc_path else ""

    fd = Rhino.UI.SaveFileDialog()
    fd.Title = "Salva esportazione geometrie v3"
    fd.Filter = "TXT (*.txt)|*.txt"
    fd.DefaultExt = "txt"
    fd.FileName = "geometrie_export_v3.txt"
    if folder:
        fd.InitialDirectory = folder

    if not fd.ShowSaveDialog():
        print("Salvataggio annullato.")
        return

    filepath = fd.FileName
    with open(filepath, "w") as f:
        f.write("\n".join(lines))

    print("")
    print("Esportazione completata: %s" % filepath)
    print("Oggetti originali: %d" % n_original)
    print("Segmenti esportati: %d" % n_total)
    if n_exploded > 0:
        print("PolyCurve esplosi: %d" % n_exploded)
    if all_bbox.IsValid:
        print("Ingombro: %s" % bbox_str)


# ============================================================
#  MAIN
# ============================================================

def main():
    print("=" * 50)
    print("ESPORTA GEOMETRIE SEMPLICE v3.0")
    print("=" * 50)

    selected = list(sc.doc.Objects.GetSelectedObjects(False, False))
    curve_objs = []
    for obj in selected:
        if obj.ObjectType == Rhino.DocObjects.ObjectType.Curve:
            curve_objs.append(obj)

    if not curve_objs:
        print("Nessuna curva selezionata - apertura guida.")
        show_help()
        return

    print("Curve selezionate: %d" % len(curve_objs))
    export_curves(curve_objs)


if __name__ == "__main__":
    main()
