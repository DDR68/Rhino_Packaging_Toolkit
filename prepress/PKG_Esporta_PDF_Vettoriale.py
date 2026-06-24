#! python 2
# -*- coding: utf-8 -*-

# =============================================================================
#  PKG ESPORTA PDF VETTORIALE  v1.4  -  Rhino 7 / 8  (IronPython 2.7)
#
#  Novita' v1.4:
#    - DIALOGO RINNOVATO: tabella con colore input (Rhino) e
#      trattamento output per-layer (Spot o CMYK).
#      Spot: nome colore, RGB editabili, sovrastampa per-layer.
#      CMYK: valori C/M/Y/K editabili (default da conversione,
#      override per crocini K100, cliche' etc.).
#      Default: tutti Spot. Margine in basso.
#    - PDF CMYK + Separation color space + ExtGState sovrastampa.
#
#  v1.3: dialogo base, CMYK, spot, overprint.
#  v1.2: testo riempito/centrato, frecce, gap linea quota.
#  v1.1: quote e testi. v1.0: curve vettoriali.
# =============================================================================

import Rhino
import scriptcontext as sc
import System
import System.Windows.Forms as WinForms
import System.Drawing as Drawing
import math

from Rhino.Geometry import (BoundingBox, LineCurve, ArcCurve,
                            PolylineCurve, NurbsCurve, PolyCurve,
                            BezierCurve, AnnotationBase, TextEntity,
                            Dimension, LinearDimension, Leader,
                            Curve, Plane, Point3d, Vector3d, Transform)

# =============================================================================
# COSTANTI
# =============================================================================
MM_TO_PT = 72.0 / 25.4
DEFAULT_MARGIN_MM = 10.0
DEFAULT_LINE_WIDTH_MM = 0.25
POLYLINE_ANGLE_TOL = 0.02
POLYLINE_DIST_TOL = 0.01
ARROW_WIDTH_RATIO = 0.35


# =============================================================================
# UTILITA'
# =============================================================================
def get_unit_scale():
    return Rhino.RhinoMath.UnitScale(
        sc.doc.ModelUnitSystem, Rhino.UnitSystem.Millimeters)

def fmt(v):
    return "%.4f" % v

def get_dimstyle(geo):
    try:
        ds = sc.doc.DimStyles.FindId(geo.DimensionStyleId)
        if ds is not None:
            return ds
    except Exception:
        pass
    return sc.doc.DimStyles.Current

def rgb_to_cmyk(r, g, b):
    """RGB 0-255 -> CMYK 0.0-1.0."""
    r1, g1, b1 = r / 255.0, g / 255.0, b / 255.0
    k = 1.0 - max(r1, g1, b1)
    if k >= 0.9999:
        return (0.0, 0.0, 0.0, 1.0)
    d = 1.0 - k
    return ((1.0 - r1 - k) / d, (1.0 - g1 - k) / d,
            (1.0 - b1 - k) / d, k)


# =============================================================================
# DIALOGO IMPOSTAZIONI
# =============================================================================
class LayerRow(object):
    """Controlli per una riga layer nel dialogo."""
    def __init__(self, parent, y, name, color):
        self.name = name
        self.input_color = Drawing.Color.FromArgb(255, color.R, color.G, color.B)

        # Preview colore input (dall'oggetto)
        pnl = WinForms.Panel()
        pnl.Location = Drawing.Point(6, y + 4)
        pnl.Size = Drawing.Size(18, 18)
        pnl.BackColor = self.input_color
        pnl.BorderStyle = WinForms.BorderStyle.FixedSingle
        parent.Controls.Add(pnl)

        # Nome layer
        lbl = WinForms.Label()
        lbl.Text = name
        lbl.Location = Drawing.Point(28, y + 5)
        lbl.Size = Drawing.Size(86, 18)
        parent.Controls.Add(lbl)

        # Tipo output
        self.combo = WinForms.ComboBox()
        self.combo.Items.AddRange(System.Array[System.Object](
            ["Spot", "CMYK"]))
        self.combo.SelectedIndex = 0
        self.combo.DropDownStyle = WinForms.ComboBoxStyle.DropDownList
        self.combo.Location = Drawing.Point(118, y + 2)
        self.combo.Size = Drawing.Size(56, 22)
        self.combo.SelectedIndexChanged += self.on_type_changed
        parent.Controls.Add(self.combo)

        # --- Controlli Spot: Nome + R/G/B ---
        self.spot_name = WinForms.TextBox()
        self.spot_name.Text = name
        self.spot_name.Location = Drawing.Point(180, y + 2)
        self.spot_name.Size = Drawing.Size(88, 22)
        parent.Controls.Add(self.spot_name)

        x = 274
        self.lbl_r = self._lbl(parent, "R", x, y + 5)
        self.nud_r = self._nud(parent, color.R, 0, 255, x + 13, y + 2)
        self.lbl_g = self._lbl(parent, "G", x + 60, y + 5)
        self.nud_g = self._nud(parent, color.G, 0, 255, x + 73, y + 2)
        self.lbl_b = self._lbl(parent, "B", x + 120, y + 5)
        self.nud_b = self._nud(parent, color.B, 0, 255, x + 133, y + 2)

        # --- Controlli CMYK: C/M/Y/K (stessa posizione, nascosti) ---
        cmyk = rgb_to_cmyk(color.R, color.G, color.B)
        x2 = 180
        self.lbl_c = self._lbl(parent, "C", x2, y + 5)
        self.nud_c = self._nud(parent, int(cmyk[0] * 100 + 0.5), 0, 100, x2 + 13, y + 2)
        self.lbl_m = self._lbl(parent, "M", x2 + 60, y + 5)
        self.nud_m = self._nud(parent, int(cmyk[1] * 100 + 0.5), 0, 100, x2 + 73, y + 2)
        self.lbl_y2 = self._lbl(parent, "Y", x2 + 120, y + 5)
        self.nud_y = self._nud(parent, int(cmyk[2] * 100 + 0.5), 0, 100, x2 + 133, y + 2)
        self.lbl_k = self._lbl(parent, "K", x2 + 180, y + 5)
        self.nud_k = self._nud(parent, int(cmyk[3] * 100 + 0.5), 0, 100, x2 + 193, y + 2)

        # OVP sempre visibile (sia Spot che CMYK)
        self.chk_ovp = WinForms.CheckBox()
        self.chk_ovp.Text = "OVP"
        self.chk_ovp.Location = Drawing.Point(470, y + 3)
        self.chk_ovp.Size = Drawing.Size(50, 20)
        self.chk_ovp.Checked = True
        parent.Controls.Add(self.chk_ovp)

        self._show_cmyk(False)

    def _lbl(self, parent, text, x, y):
        lbl = WinForms.Label()
        lbl.Text = text
        lbl.Location = Drawing.Point(x, y)
        lbl.Size = Drawing.Size(13, 16)
        parent.Controls.Add(lbl)
        return lbl

    def _nud(self, parent, val, lo, hi, x, y):
        nud = WinForms.NumericUpDown()
        nud.Location = Drawing.Point(x, y)
        nud.Size = Drawing.Size(44, 22)
        nud.Minimum = System.Decimal(lo)
        nud.Maximum = System.Decimal(hi)
        nud.DecimalPlaces = 0
        nud.Value = System.Decimal(max(lo, min(hi, int(val))))
        parent.Controls.Add(nud)
        return nud

    def _show_cmyk(self, show):
        for c in [self.lbl_c, self.nud_c, self.lbl_m, self.nud_m,
                  self.lbl_y2, self.nud_y, self.lbl_k, self.nud_k]:
            c.Visible = show
        for c in [self.spot_name, self.lbl_r, self.nud_r,
                  self.lbl_g, self.nud_g, self.lbl_b, self.nud_b]:
            c.Visible = not show

    def on_type_changed(self, sender, args):
        self._show_cmyk(self.combo.SelectedIndex == 1)

    def get_settings(self):
        ovp = self.chk_ovp.Checked
        if self.combo.SelectedIndex == 0:  # Spot
            r = int(self.nud_r.Value)
            g = int(self.nud_g.Value)
            b = int(self.nud_b.Value)
            return {
                'type': 'spot',
                'spot_name': self.spot_name.Text or self.name,
                'rgb': (r, g, b),
                'cmyk': rgb_to_cmyk(r, g, b),
                'overprint': ovp,
            }
        else:  # CMYK
            c = float(self.nud_c.Value) / 100.0
            m = float(self.nud_m.Value) / 100.0
            y = float(self.nud_y.Value) / 100.0
            k = float(self.nud_k.Value) / 100.0
            return {
                'type': 'cmyk',
                'cmyk': (c, m, y, k),
                'overprint': ovp,
            }


class ExportDialog(WinForms.Form):
    def __init__(self, layer_names_colors):
        self.result = None
        self.layer_rows = []

        self.Text = "PKG Esporta PDF Vettoriale"
        self.FormBorderStyle = WinForms.FormBorderStyle.FixedDialog
        self.MaximizeBox = False
        self.MinimizeBox = False
        self.StartPosition = WinForms.FormStartPosition.CenterScreen

        n = len(layer_names_colors)
        row_h = 28
        header_h = 50
        list_h = min(max(n * row_h + 8, 50), 350)  # max 350px, poi scroll
        footer_h = 80
        self.ClientSize = Drawing.Size(540, header_h + list_h + footer_h)

        # --- Intestazione ---
        lbl_title = WinForms.Label()
        lbl_title.Text = "Mappatura colori di output"
        lbl_title.Font = Drawing.Font(lbl_title.Font, Drawing.FontStyle.Bold)
        lbl_title.Location = Drawing.Point(10, 8)
        lbl_title.AutoSize = True
        self.Controls.Add(lbl_title)

        # Colonne header
        headers = [("Input", 6), ("Layer", 28), ("Output", 122),
                   ("Definizione colore", 260)]
        for txt, x in headers:
            lh = WinForms.Label()
            lh.Text = txt
            lh.Location = Drawing.Point(x, 28)
            lh.AutoSize = True
            lh.ForeColor = Drawing.Color.Gray
            lh.Font = Drawing.Font(lh.Font.FontFamily, 7.5)
            self.Controls.Add(lh)

        # --- Panel layer ---
        panel = WinForms.Panel()
        panel.Location = Drawing.Point(0, header_h)
        panel.Size = Drawing.Size(530, list_h)
        panel.AutoScroll = True
        panel.BorderStyle = WinForms.BorderStyle.FixedSingle
        self.Controls.Add(panel)

        for i, (name, color) in enumerate(layer_names_colors):
            lr = LayerRow(panel, i * row_h, name, color)
            self.layer_rows.append(lr)

        # --- Footer ---
        y_foot = header_h + list_h + 8

        # Separatore
        sep = WinForms.Label()
        sep.BorderStyle = WinForms.BorderStyle.Fixed3D
        sep.Location = Drawing.Point(10, y_foot)
        sep.Size = Drawing.Size(510, 2)
        self.Controls.Add(sep)

        # Margine
        lbl_m = WinForms.Label()
        lbl_m.Text = "Margine pagina:"
        lbl_m.Location = Drawing.Point(10, y_foot + 12)
        lbl_m.AutoSize = True
        self.Controls.Add(lbl_m)

        self.margin_box = WinForms.NumericUpDown()
        self.margin_box.Location = Drawing.Point(110, y_foot + 10)
        self.margin_box.Size = Drawing.Size(60, 22)
        self.margin_box.Minimum = System.Decimal(0)
        self.margin_box.Maximum = System.Decimal(200)
        self.margin_box.DecimalPlaces = 1
        self.margin_box.Value = System.Decimal(DEFAULT_MARGIN_MM)
        self.Controls.Add(self.margin_box)

        lbl_mm = WinForms.Label()
        lbl_mm.Text = "mm"
        lbl_mm.Location = Drawing.Point(174, y_foot + 12)
        lbl_mm.AutoSize = True
        self.Controls.Add(lbl_mm)

        # Pulsanti
        btn_ok = WinForms.Button()
        btn_ok.Text = "Esporta"
        btn_ok.Size = Drawing.Size(80, 28)
        btn_ok.Location = Drawing.Point(340, y_foot + 40)
        btn_ok.Click += self.on_ok
        self.Controls.Add(btn_ok)
        self.AcceptButton = btn_ok

        btn_cancel = WinForms.Button()
        btn_cancel.Text = "Annulla"
        btn_cancel.Size = Drawing.Size(80, 28)
        btn_cancel.Location = Drawing.Point(430, y_foot + 40)
        btn_cancel.Click += self.on_cancel
        self.Controls.Add(btn_cancel)
        self.CancelButton = btn_cancel

    def on_ok(self, sender, args):
        layers = {}
        for lr in self.layer_rows:
            layers[lr.name] = lr.get_settings()
        self.result = {
            'margin': float(self.margin_box.Value),
            'layers': layers,
        }
        self.DialogResult = WinForms.DialogResult.OK
        self.Close()

    def on_cancel(self, sender, args):
        self.result = None
        self.DialogResult = WinForms.DialogResult.Cancel
        self.Close()


# =============================================================================
# FRECCE
# =============================================================================
def make_arrowhead(tip, direction, length):
    width = length * ARROW_WIDTH_RATIO
    perp = Vector3d(-direction.Y, direction.X, 0.0)
    base = tip - direction * length
    c1 = base + perp * width * 0.5
    c2 = base - perp * width * 0.5
    pts = System.Collections.Generic.List[Point3d]()
    pts.Add(Point3d(tip.X, tip.Y, 0))
    pts.Add(Point3d(c1.X, c1.Y, 0))
    pts.Add(Point3d(c2.X, c2.Y, 0))
    pts.Add(Point3d(tip.X, tip.Y, 0))
    return PolylineCurve(pts)


# =============================================================================
# ESTRAZIONE CURVE DA ANNOTAZIONI
# =============================================================================
def close_text_outlines(curves):
    tol = sc.doc.ModelAbsoluteTolerance
    result = []
    for crv in curves:
        if crv is None:
            continue
        if crv.IsClosed:
            result.append(crv)
            continue
        try:
            close_seg = LineCurve(crv.PointAtEnd, crv.PointAtStart)
            joined = Curve.JoinCurves([crv, close_seg], tol)
            if joined and len(joined) > 0 and joined[0].IsClosed:
                result.append(joined[0])
                continue
        except Exception:
            pass
        result.append(crv)
    return result


def curves_from_annotation(geo):
    stroke = []
    fill = []
    dimstyle = get_dimstyle(geo)

    if isinstance(geo, TextEntity):
        try:
            result = geo.CreateCurves(dimstyle, False)
            if result and len(result) > 0:
                fill.extend(close_text_outlines(result))
                return (stroke, fill)
        except Exception:
            pass
        try:
            result = geo.Explode()
            if result:
                raw = [item for item in result if isinstance(item, Curve)]
                fill.extend(close_text_outlines(raw))
        except Exception:
            pass
        return (stroke, fill)

    if isinstance(geo, Dimension):
        arrow1 = arrow2 = text_3d = None
        text_half_w = 0.0
        text_height = dimstyle.TextHeight

        if isinstance(geo, LinearDimension):
            try:
                pts3d = geo.Get3dPoints()
                if pts3d[0]:
                    arrow1, arrow2, text_3d = pts3d[3], pts3d[4], pts3d[6]
            except Exception:
                pass

        # Testo
        try:
            text = None
            try:
                text = geo.GetDistanceDisplayText(
                    sc.doc.ModelUnitSystem, dimstyle)
            except Exception:
                pass
            if not text:
                text = geo.PlainText
            if text:
                font_name = "Arial"
                try:
                    font_name = dimstyle.Font.EnglishFaceName
                except Exception:
                    pass
                try:
                    text_height = geo.TextHeight
                except Exception:
                    pass
                std_plane = Plane(Point3d.Origin,
                                 Vector3d.XAxis, Vector3d.YAxis)
                tc = Curve.CreateTextOutlines(
                    text, font_name, text_height,
                    0, True, std_plane, 0.0,
                    sc.doc.ModelAbsoluteTolerance)
                if tc and len(tc) > 0:
                    tc = close_text_outlines(tc)
                    tb = BoundingBox.Empty
                    for crv in tc:
                        tb.Union(crv.GetBoundingBox(True))
                    bc = tb.Center
                    text_half_w = (tb.Max.X - tb.Min.X) / 2.0
                    xf1 = Transform.Translation(
                        Vector3d(-bc.X, -bc.Y, -bc.Z))
                    rot = 0.0
                    if arrow1 is not None and arrow2 is not None:
                        dd = arrow2 - arrow1
                        rot = math.atan2(dd.Y, dd.X)
                    xf2 = Transform.Rotation(
                        rot, Vector3d.ZAxis, Point3d.Origin)
                    if text_3d is None:
                        dp = geo.Plane
                        try:
                            tp2 = geo.TextPoint
                            text_3d = dp.PointAt(tp2.X, tp2.Y)
                        except Exception:
                            text_3d = dp.Origin
                    xf3 = Transform.Translation(
                        Vector3d(text_3d.X, text_3d.Y, text_3d.Z))
                    for crv in tc:
                        crv.Transform(xf1)
                        crv.Transform(xf2)
                        crv.Transform(xf3)
                    fill.extend(tc)
        except Exception:
            pass

        # Linee quota con gap
        if isinstance(geo, LinearDimension) and arrow1 is not None:
            tgm = text_height * 0.25
            try:
                tg = dimstyle.TextGap
                if tg > 0:
                    tgm = tg
            except Exception:
                pass
            gh = text_half_w + tgm
            dd = arrow2 - arrow1
            dl = dd.Length
            dd.Unitize()
            vt = text_3d - arrow1
            tc = vt.X * dd.X + vt.Y * dd.Y + vt.Z * dd.Z
            if tc - gh > 0.1:
                stroke.append(LineCurve(arrow1, arrow1 + dd * (tc - gh)))
            if tc + gh < dl - 0.1:
                stroke.append(LineCurve(arrow1 + dd * (tc + gh), arrow2))
        else:
            try:
                result = geo.GetDisplayLines(dimstyle, 1.0)
                if result[0]:
                    for line in result[1]:
                        stroke.append(LineCurve(line))
            except Exception:
                pass

        # Frecce
        if arrow1 is not None and arrow2 is not None:
            try:
                al = dimstyle.ArrowLength
                if al <= 0:
                    al = text_height * 0.5
                d1 = arrow1 - arrow2
                d1.Unitize()
                d2 = arrow2 - arrow1
                d2.Unitize()
                fill.append(make_arrowhead(arrow1, d1, al))
                fill.append(make_arrowhead(arrow2, d2, al))
            except Exception:
                pass
        return (stroke, fill)

    if isinstance(geo, Leader):
        try:
            pp = geo.Points3d
            if pp and len(pp) >= 2:
                pts = System.Collections.Generic.List[Point3d]()
                for p in pp:
                    pts.Add(p)
                stroke.append(PolylineCurve(pts))
        except Exception:
            pass
        try:
            result = geo.CreateCurves(dimstyle, False)
            if result and len(result) > 0:
                fill.extend(close_text_outlines(result))
        except Exception:
            pass
        return (stroke, fill)

    try:
        result = geo.CreateCurves(dimstyle, False)
        if result and len(result) > 0:
            fill.extend(close_text_outlines(result))
    except Exception:
        pass
    return (stroke, fill)


# =============================================================================
# GEOMETRIA: CURVE -> OPERATORI PDF
# =============================================================================
def transform_pt(pt, ox, oy, s):
    return ((pt.X + ox) * s, (pt.Y + oy) * s)

def arc_to_bezier_tuples(arc):
    angle = arc.Angle
    if abs(angle) < 1e-10:
        return []
    n_segs = max(1, int(math.ceil(abs(angle) / (math.pi / 2.0))))
    da = angle / n_segs
    plane = arc.Plane
    center = arc.Center
    radius = arc.Radius
    xa, ya = plane.XAxis, plane.YAxis
    a0 = arc.StartAngle
    result = []
    for i in range(n_segs):
        ai = a0 + i * da
        af = ai + da
        c0, s0 = math.cos(ai), math.sin(ai)
        c1, s1 = math.cos(af), math.sin(af)
        p0 = center + radius * c0 * xa + radius * s0 * ya
        p3 = center + radius * c1 * xa + radius * s1 * ya
        t0 = -s0 * xa + c0 * ya
        t1 = -s1 * xa + c1 * ya
        alpha = 4.0 / 3.0 * math.tan(da / 4.0) * radius
        result.append((p0, p0 + alpha * t0, p3 - alpha * t1, p3))
    return result

def segments_from_curve(curve):
    if isinstance(curve, PolyCurve):
        out = []
        for i in range(curve.SegmentCount):
            out.extend(segments_from_curve(curve.SegmentCurve(i)))
        return out
    return [curve]

def curve_to_pdf_path(curve, ox, oy, s, fill_mode=False):
    ops = []
    def tp(p):
        return transform_pt(p, ox, oy, s)
    def eop(closed):
        return "h" if fill_mode else ("s" if closed else "S")

    if isinstance(curve, LineCurve):
        x0, y0 = tp(curve.PointAtStart)
        x1, y1 = tp(curve.PointAtEnd)
        ops.append("%s %s m" % (fmt(x0), fmt(y0)))
        ops.append("%s %s l" % (fmt(x1), fmt(y1)))
        ops.append(eop(False))
        return ops
    if isinstance(curve, ArcCurve):
        bz = arc_to_bezier_tuples(curve.Arc)
        if not bz:
            return ops
        x0, y0 = tp(bz[0][0])
        ops.append("%s %s m" % (fmt(x0), fmt(y0)))
        for _, p1, p2, p3 in bz:
            x1, y1 = tp(p1); x2, y2 = tp(p2); x3, y3 = tp(p3)
            ops.append("%s %s %s %s %s %s c" % (
                fmt(x1), fmt(y1), fmt(x2), fmt(y2), fmt(x3), fmt(y3)))
        ops.append(eop(curve.IsClosed))
        return ops
    if isinstance(curve, PolylineCurve):
        pl = curve.ToPolyline()
        if pl.Count < 2:
            return ops
        x0, y0 = tp(pl[0])
        ops.append("%s %s m" % (fmt(x0), fmt(y0)))
        for i in range(1, pl.Count):
            xi, yi = tp(pl[i])
            ops.append("%s %s l" % (fmt(xi), fmt(yi)))
        ops.append(eop(curve.IsClosed))
        return ops

    nc = curve if isinstance(curve, NurbsCurve) else curve.ToNurbsCurve()
    if nc is not None:
        if nc.Degree == 1:
            pts = [nc.Points[j].Location for j in range(nc.Points.Count)]
            if len(pts) >= 2:
                x0, y0 = tp(pts[0])
                ops.append("%s %s m" % (fmt(x0), fmt(y0)))
                for pt in pts[1:]:
                    xi, yi = tp(pt)
                    ops.append("%s %s l" % (fmt(xi), fmt(yi)))
                ops.append(eop(nc.IsClosed))
                return ops
        if nc.Degree == 2:
            try:
                nc2 = nc.Duplicate()
                if nc2.IncreaseDegree(3):
                    nc = nc2
            except Exception:
                pass
        if nc.Degree == 3:
            try:
                beziers = BezierCurve.CreateCubicBeziers(nc)
                if beziers is not None and len(beziers) > 0:
                    x0, y0 = tp(beziers[0].GetControlVertex(0))
                    ops.append("%s %s m" % (fmt(x0), fmt(y0)))
                    for bz in beziers:
                        x1, y1 = tp(bz.GetControlVertex(1))
                        x2, y2 = tp(bz.GetControlVertex(2))
                        x3, y3 = tp(bz.GetControlVertex(3))
                        ops.append("%s %s %s %s %s %s c" % (
                            fmt(x1), fmt(y1), fmt(x2), fmt(y2),
                            fmt(x3), fmt(y3)))
                    ops.append(eop(nc.IsClosed))
                    return ops
            except Exception:
                pass

    # Fallback polilinea
    try:
        pc = curve.ToPolyline(0, 0, POLYLINE_ANGLE_TOL, 0.0, 0.0,
                              POLYLINE_DIST_TOL, 0.0, 0.0, True)
        if pc is not None:
            pl = pc.ToPolyline()
            if pl is not None and pl.Count >= 2:
                x0, y0 = tp(pl[0])
                ops.append("%s %s m" % (fmt(x0), fmt(y0)))
                for i in range(1, pl.Count):
                    xi, yi = tp(pl[i])
                    ops.append("%s %s l" % (fmt(xi), fmt(yi)))
                ops.append(eop(curve.IsClosed))
                return ops
    except Exception:
        pass

    # Ultra-fallback
    domain = curve.Domain
    n = max(int(curve.GetLength() / 0.05), 20)
    x0, y0 = tp(curve.PointAtStart)
    ops.append("%s %s m" % (fmt(x0), fmt(y0)))
    for i in range(1, n + 1):
        t = domain.T0 + (domain.T1 - domain.T0) * float(i) / float(n)
        xi, yi = tp(curve.PointAt(t))
        ops.append("%s %s l" % (fmt(xi), fmt(yi)))
    ops.append(eop(curve.IsClosed))
    return ops


# =============================================================================
# STILE OGGETTO
# =============================================================================
def get_obj_layer_name(obj):
    return sc.doc.Layers[obj.Attributes.LayerIndex].Name

def get_line_width_mm(obj):
    pw = obj.Attributes.PlotWeight
    if pw <= 0:
        pw = sc.doc.Layers[obj.Attributes.LayerIndex].PlotWeight
    if pw <= 0:
        pw = DEFAULT_LINE_WIDTH_MM
    return pw

def get_dash_pattern_pt(obj, unit_scale):
    lt_idx = obj.Attributes.LinetypeIndex
    if lt_idx < 0:
        lt_idx = sc.doc.Layers[obj.Attributes.LayerIndex].LinetypeIndex
    if lt_idx < 0 or lt_idx >= sc.doc.Linetypes.Count:
        return []
    lt = sc.doc.Linetypes[lt_idx]
    if lt.SegmentCount == 0:
        return []
    pattern = []
    for i in range(lt.SegmentCount):
        try:
            result = lt.GetSegment(i)
            seg_len = result[1]
        except Exception:
            seg_len = lt.PatternLength / lt.SegmentCount
        pt_len = abs(seg_len) * unit_scale * MM_TO_PT
        pattern.append(pt_len)
    return pattern


# =============================================================================
# COSTRUZIONE PDF
# =============================================================================
def build_pdf(objects, settings):
    margin_mm = settings['margin']
    layer_settings = settings['layers']  # {name: {type, cmyk, spot_name, rgb, overprint}}

    unit_scale = get_unit_scale()
    scale = unit_scale * MM_TO_PT

    # Bounding box
    bbox = BoundingBox.Empty
    for obj in objects:
        geo = obj.Geometry
        if geo is not None:
            bb = geo.GetBoundingBox(True)
            if bb.IsValid:
                bbox.Union(bb)
    if not bbox.IsValid:
        print("Nessuna geometria valida.")
        return None

    w_mm = (bbox.Max.X - bbox.Min.X) * unit_scale + 2.0 * margin_mm
    h_mm = (bbox.Max.Y - bbox.Min.Y) * unit_scale + 2.0 * margin_mm
    pw = w_mm * MM_TO_PT
    ph = h_mm * MM_TO_PT
    ox = -bbox.Min.X + margin_mm / unit_scale
    oy = -bbox.Min.Y + margin_mm / unit_scale
    print("Pagina: %.1f x %.1f mm" % (w_mm, h_mm))

    # Raccolta spot colors con RGB per alternativo fedele
    spot_list = []   # [(spot_name, r, g, b)]  valori 0-1
    spot_cs = {}     # layer_name -> "CS_N"
    spot_ovp = {}    # layer_name -> bool
    for lname, ls in layer_settings.items():
        if ls['type'] == 'spot':
            cs_key = "CS_%d" % len(spot_list)
            rgb = ls['rgb']  # (R, G, B) 0-255
            spot_list.append((ls['spot_name'],
                              rgb[0] / 255.0, rgb[1] / 255.0, rgb[2] / 255.0))
            spot_cs[lname] = cs_key
            spot_ovp[lname] = ls.get('overprint', True)

    # Content stream
    cl = ["q", "1 J", "1 j"]
    n_crv = n_ann = 0

    for obj in objects:
        geo = obj.Geometry
        if geo is None:
            continue
        lname = get_obj_layer_name(obj)
        lw_pt = get_line_width_mm(obj) * MM_TO_PT
        dash = get_dash_pattern_pt(obj, unit_scale)
        cl.append("%.4f w" % lw_pt)
        cl.append("[%s] 0 d" % " ".join("%.2f" % d for d in dash) if dash else "[] 0 d")

        # Colore
        is_spot = lname in spot_cs
        if is_spot:
            cs = spot_cs[lname]
            if spot_ovp.get(lname, True):
                cl.append("/GSOVP gs")
            else:
                cl.append("/GSNOVP gs")
            cl.append("/%s CS" % cs)
            cl.append("1 SCN")
            cl.append("/%s cs" % cs)
            cl.append("1 scn")
        else:
            ls = layer_settings.get(lname)
            cmyk_ovp = ls.get('overprint', False) if ls else False
            if cmyk_ovp:
                cl.append("/GSOVP gs")
            else:
                cl.append("/GSNOVP gs")
            if ls and 'cmyk' in ls:
                c, m, y, k = ls['cmyk']
            else:
                # Fallback: converti colore oggetto
                src = obj.Attributes.ColorSource
                if src == Rhino.DocObjects.ObjectColorSource.ColorFromLayer:
                    col = sc.doc.Layers[obj.Attributes.LayerIndex].Color
                else:
                    col = obj.Attributes.ObjectColor
                c, m, y, k = rgb_to_cmyk(col.R, col.G, col.B)
            cl.append("%.4f %.4f %.4f %.4f K" % (c, m, y, k))
            cl.append("%.4f %.4f %.4f %.4f k" % (c, m, y, k))

        if isinstance(geo, Curve):
            for seg in segments_from_curve(geo):
                cl.extend(curve_to_pdf_path(seg, ox, oy, scale, False))
            n_crv += 1
            continue

        if isinstance(geo, AnnotationBase):
            s_crvs, f_crvs = curves_from_annotation(geo)
            for crv in s_crvs:
                for seg in segments_from_curve(crv):
                    cl.extend(curve_to_pdf_path(seg, ox, oy, scale, False))
            if f_crvs:
                for crv in f_crvs:
                    if isinstance(crv, PolyCurve):
                        nc = crv.ToNurbsCurve()
                        if nc is not None:
                            crv = nc
                    cl.extend(curve_to_pdf_path(crv, ox, oy, scale, True))
                cl.append("f*")
            n_ann += 1

    cl.append("Q")
    print("Processati: %d curve, %d annotazioni." % (n_crv, n_ann))
    if spot_list:
        print("Spot: %s" % ", ".join(
            "%s (R%.0f G%.0f B%.0f)" % (s[0], s[1]*255, s[2]*255, s[3]*255)
            for s in spot_list))

    stream = "\n".join(cl)
    print("Stream: %d righe, %d bytes." % (len(cl), len(stream)))
    # Prime 15 righe del content stream per diagnostica
    for line in cl[:15]:
        print("  | %s" % line)

    # Assemblaggio PDF -- solo 6 oggetti, tint transform inline
    buf = bytearray()
    off = {}
    def w(t):
        buf.extend(t.encode("latin-1"))
    def p():
        return len(buf)

    n_obj = 6

    w("%%PDF-1.4\n")

    off[1] = p()
    w("1 0 obj\n<< /Type /Catalog /Pages 2 0 R >>\nendobj\n")
    off[2] = p()
    w("2 0 obj\n<< /Type /Pages /Kids [3 0 R] /Count 1 >>\nendobj\n")

    # Page con Resources (tint transform inline nell'array Separation)
    off[3] = p()
    w("3 0 obj\n")
    w("<< /Type /Page /Parent 2 0 R\n")
    w("   /MediaBox [0 0 %.2f %.2f]\n" % (pw, ph))
    w("   /Contents 4 0 R\n")
    w("   /Resources <<\n")
    if spot_list:
        w("     /ColorSpace <<\n")
        for i, (sn, sr, sg, sb) in enumerate(spot_list):
            safe = sn.replace(" ", "#20").replace("(", "#28").replace(")", "#29")
            w("       /CS_%d [/Separation /%s /DeviceRGB\n" % (i, safe))
            w("         << /FunctionType 2 /Domain [0 1]\n")
            w("            /C0 [1 1 1]\n")
            w("            /C1 [%.4f %.4f %.4f]\n" % (sr, sg, sb))
            w("            /N 1 >>]\n")
        w("     >>\n")
    w("     /ExtGState <<\n")
    w("       /GSOVP 5 0 R\n")
    w("       /GSNOVP 6 0 R\n")
    w("     >>\n")
    w("   >>\n")
    w(">>\n")
    w("endobj\n")

    off[4] = p()
    w("4 0 obj\n<< /Length %d >>\n" % len(stream))
    w("stream\n")
    w(stream)
    w("\nendstream\n")
    w("endobj\n")

    off[5] = p()
    w("5 0 obj\n<< /Type /ExtGState /OP true /op true /OPM 1 >>\nendobj\n")
    off[6] = p()
    w("6 0 obj\n<< /Type /ExtGState /OP false /op false >>\nendobj\n")

    xref = p()
    total = n_obj + 1
    w("xref\n0 %d\n" % total)
    w("0000000000 65535 f \n")
    for i in range(1, n_obj + 1):
        w("%010d 00000 n \n" % off[i])
    w("trailer\n<< /Size %d /Root 1 0 R >>\n" % total)
    w("startxref\n%d\n" % xref)
    w("%%%%EOF\n")

    return buf


# =============================================================================
# MAIN
# =============================================================================
def main():
    go = Rhino.Input.Custom.GetObject()
    go.SetCommandPrompt(
        "Seleziona curve, quote e testi da esportare in PDF vettoriale")
    go.GeometryFilter = (Rhino.DocObjects.ObjectType.Curve
                         | Rhino.DocObjects.ObjectType.Annotation)
    go.SubObjectSelect = False
    go.GroupSelect = True
    go.GetMultiple(1, 0)
    if go.CommandResult() != Rhino.Commands.Result.Success:
        return

    objects = [go.Object(i).Object() for i in range(go.ObjectCount)]
    if not objects:
        print("Nessun oggetto selezionato.")
        return
    print("%d oggetti selezionati." % len(objects))

    # Layer unici — colore dall'oggetto (non dal layer)
    layer_set = {}
    for obj in objects:
        idx = obj.Attributes.LayerIndex
        name = sc.doc.Layers[idx].Name
        if name not in layer_set:
            src = obj.Attributes.ColorSource
            if src == Rhino.DocObjects.ObjectColorSource.ColorFromObject:
                layer_set[name] = obj.Attributes.ObjectColor
            else:
                layer_set[name] = sc.doc.Layers[idx].Color
    layer_list = sorted(layer_set.items(), key=lambda x: x[0])

    for name, color in layer_list:
        print("  '%s': R=%d G=%d B=%d" % (name, color.R, color.G, color.B))

    dlg = ExportDialog(layer_list)
    if dlg.ShowDialog() != WinForms.DialogResult.OK or dlg.result is None:
        print("Annullato.")
        return

    pdf_data = build_pdf(objects, dlg.result)
    if pdf_data is None:
        return
    print("PDF: %d bytes." % len(pdf_data))

    fd = Rhino.UI.SaveFileDialog()
    fd.Filter = "PDF (*.pdf)|*.pdf"
    fd.Title = "Salva PDF vettoriale"
    fd.DefaultExt = "pdf"
    if not fd.ShowSaveDialog():
        print("Annullato.")
        return

    filepath = fd.FileName
    if not filepath.lower().endswith(".pdf"):
        filepath += ".pdf"
    try:
        with open(filepath, "wb") as f:
            f.write(bytes(pdf_data))
        print("Salvato: %s" % filepath)
    except Exception as e:
        print("Errore: %s" % str(e))

main()
