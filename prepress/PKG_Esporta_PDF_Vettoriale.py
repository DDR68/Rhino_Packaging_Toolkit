#! python 2
# -*- coding: utf-8 -*-

# =============================================================================
#  PKG ESPORTA PDF VETTORIALE  v1.5  -  Rhino 7 / 8  (IronPython 2.7)
#
#  Novita' v1.5:
#    - REGOLE DI MAPPATURA: ogni colore input (Rhino) viene rimappato
#      su un layer PDF di output con nome, colore, spessore e
#      sovrastampa definiti. Regole di default hardcoded.
#    - DIALOGO RINNOVATO: tabella Input -> Output con layer di
#      destinazione, tipo colore (Spot/CMYK), valori colore,
#      spessore linea per-layer, sovrastampa per-layer.
#    - COMPATIBILITA' ILLUSTRATOR: OCG con /Intent /Design e
#      /Usage/CreatorInfo cosi' Illustrator riconosce i livelli
#      nativamente (non solo Acrobat Reader).
#    - PDF CMYK + Separation color space + ExtGState sovrastampa.
#
#  v1.4: dialogo per-layer, CMYK/Spot, overprint.
#  v1.3: dialogo base. v1.2: testo riempito/centrato, frecce,
#  gap linea quota.
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
# REGOLE DI MAPPATURA (default)
#
# Ogni regola mappa un colore input (RGB Rhino) a un layer PDF di output.
# match_color: RGB da cercare (0-255)
# match_tolerance: distanza euclidea massima per il match
# output_layer: nome del livello PDF di destinazione
# color_type: 'spot' o 'cmyk'
# spot_name: nome colore spot (usato se color_type == 'spot')
# rgb: RGB di anteprima spot (0-255)
# cmyk: valori CMYK (0.0-1.0) (usato se color_type == 'cmyk')
# line_width: spessore linea in mm
# overprint: sovrastampa (True/False)
# =============================================================================
DEFAULT_RULES = [
    {
        'match_color': (255, 0, 255),
        'match_tolerance': 15,
        'output_layer': 'Tracciato',
        'color_type': 'spot',
        'spot_name': 'Tracciato',
        'rgb': (255, 0, 255),
        'line_width': 0.25,
        'overprint': True,
    },
    {
        'match_color': (0, 190, 255),
        'match_tolerance': 25,
        'output_layer': 'Quote',
        'color_type': 'spot',
        'spot_name': 'Quote',
        'rgb': (0, 190, 255),
        'line_width': 0.15,
        'overprint': True,
    },
    {
        'match_color': (0, 0, 0),
        'match_tolerance': 10,
        'output_layer': 'Crocini',
        'color_type': 'cmyk',
        'cmyk': (1.0, 1.0, 1.0, 1.0),
        'line_width': 0.10,
        'overprint': False,
    },
]


# =============================================================================
# UTILITA'
# =============================================================================
def get_unit_scale():
    return Rhino.RhinoMath.UnitScale(
        sc.doc.ModelUnitSystem, Rhino.UnitSystem.Millimeters)

def fmt(v):
    return "%.4f" % v

def strip_rtf(text):
    """Estrae testo plain da una stringa RTF.
    Alcune annotazioni Rhino 7/8 memorizzano testo in formato RTF;
    se passato a CreateTextOutlines il markup viene renderizzato."""
    if not text or not text.startswith("{\\rtf"):
        return text
    try:
        rtb = WinForms.RichTextBox()
        rtb.Rtf = text
        result = rtb.Text
        rtb.Dispose()
        return result
    except Exception:
        return text

def get_dimstyle(geo):
    try:
        ds = sc.doc.DimStyles.FindId(geo.DimensionStyleId)
        if ds is not None:
            return ds
    except Exception:
        pass
    return sc.doc.DimStyles.Current

def rgb_to_cmyk(r, g, b):
    """RGB 0-255 -> CMYK 0.0-1.0.
    Nero puro -> nero di registro (C100 M100 Y100 K100)
    per comparire su tutte le lastre colore."""
    r1, g1, b1 = r / 255.0, g / 255.0, b / 255.0
    k = 1.0 - max(r1, g1, b1)
    if k >= 0.9999:
        return (1.0, 1.0, 1.0, 1.0)
    d = 1.0 - k
    return ((1.0 - r1 - k) / d, (1.0 - g1 - k) / d,
            (1.0 - b1 - k) / d, k)


def get_display_color(obj):
    """Restituisce il colore effettivo dell'oggetto (da oggetto o layer)."""
    src = obj.Attributes.ColorSource
    if src == Rhino.DocObjects.ObjectColorSource.ColorFromObject:
        return obj.Attributes.ObjectColor
    return sc.doc.Layers[obj.Attributes.LayerIndex].Color


def color_distance(c1, c2):
    """Distanza euclidea RGB."""
    return math.sqrt(
        (c1[0] - c2[0]) ** 2 +
        (c1[1] - c2[1]) ** 2 +
        (c1[2] - c2[2]) ** 2)


def find_matching_rule(r, g, b):
    """Trova la regola con match migliore, None se nessuna entro tolleranza."""
    best = None
    best_dist = float('inf')
    for rule in DEFAULT_RULES:
        dist = color_distance((r, g, b), rule['match_color'])
        tol = rule.get('match_tolerance', 10)
        if dist <= tol and dist < best_dist:
            best = rule
            best_dist = dist
    return best


# =============================================================================
# DIALOGO IMPOSTAZIONI v1.5
# =============================================================================
class LayerRow(object):
    """Controlli per una riga di mappatura nel dialogo."""
    def __init__(self, parent, y, input_rgb, input_label, rule):
        self.input_rgb = input_rgb
        self.rule = rule

        ir, ig, ib = input_rgb
        self.input_color = Drawing.Color.FromArgb(255, ir, ig, ib)

        # -- Colore input (swatch) --
        pnl = WinForms.Panel()
        pnl.Location = Drawing.Point(6, y + 4)
        pnl.Size = Drawing.Size(18, 18)
        pnl.BackColor = self.input_color
        pnl.BorderStyle = WinForms.BorderStyle.FixedSingle
        parent.Controls.Add(pnl)

        # -- Label input (nome layer Rhino) --
        lbl = WinForms.Label()
        lbl.Text = input_label
        lbl.Location = Drawing.Point(28, y + 5)
        lbl.Size = Drawing.Size(78, 18)
        parent.Controls.Add(lbl)

        # -- Freccia --
        arr = WinForms.Label()
        arr.Text = unichr(0x2192)  # freccia destra
        arr.Location = Drawing.Point(108, y + 4)
        arr.Size = Drawing.Size(16, 18)
        arr.Font = Drawing.Font(arr.Font.FontFamily, 10.0)
        parent.Controls.Add(arr)

        # -- Nome layer output (editable) --
        self.txt_output = WinForms.TextBox()
        self.txt_output.Text = rule.get('output_layer', input_label)
        self.txt_output.Location = Drawing.Point(126, y + 2)
        self.txt_output.Size = Drawing.Size(82, 22)
        parent.Controls.Add(self.txt_output)

        # -- Tipo output --
        self.combo = WinForms.ComboBox()
        self.combo.Items.AddRange(System.Array[System.Object](
            ["Spot", "CMYK"]))
        ct = rule.get('color_type', 'spot')
        self.combo.SelectedIndex = 0 if ct == 'spot' else 1
        self.combo.DropDownStyle = WinForms.ComboBoxStyle.DropDownList
        self.combo.Location = Drawing.Point(212, y + 2)
        self.combo.Size = Drawing.Size(56, 22)
        self.combo.SelectedIndexChanged += self.on_type_changed
        parent.Controls.Add(self.combo)

        # -- Controlli Spot: R/G/B --
        spot_rgb = rule.get('rgb', input_rgb)
        x = 274
        self.lbl_r = self._lbl(parent, "R", x, y + 5)
        self.nud_r = self._nud(parent, spot_rgb[0], 0, 255, x + 13, y + 2, 42)
        self.lbl_g = self._lbl(parent, "G", x + 58, y + 5)
        self.nud_g = self._nud(parent, spot_rgb[1], 0, 255, x + 71, y + 2, 42)
        self.lbl_b = self._lbl(parent, "B", x + 116, y + 5)
        self.nud_b = self._nud(parent, spot_rgb[2], 0, 255, x + 129, y + 2, 42)

        # -- Controlli CMYK: C/M/Y/K (stessa posizione, nascosti) --
        rule_cmyk = rule.get('cmyk', None)
        if rule_cmyk is None:
            rule_cmyk = rgb_to_cmyk(ir, ig, ib)
        x2 = 274
        self.lbl_c = self._lbl(parent, "C", x2, y + 5)
        self.nud_c = self._nud(parent, int(rule_cmyk[0] * 100 + 0.5),
                               0, 100, x2 + 13, y + 2, 40)
        self.lbl_m = self._lbl(parent, "M", x2 + 56, y + 5)
        self.nud_m = self._nud(parent, int(rule_cmyk[1] * 100 + 0.5),
                               0, 100, x2 + 69, y + 2, 40)
        self.lbl_y2 = self._lbl(parent, "Y", x2 + 112, y + 5)
        self.nud_y = self._nud(parent, int(rule_cmyk[2] * 100 + 0.5),
                               0, 100, x2 + 125, y + 2, 40)
        self.lbl_k = self._lbl(parent, "K", x2 + 168, y + 5)
        self.nud_k = self._nud(parent, int(rule_cmyk[3] * 100 + 0.5),
                               0, 100, x2 + 181, y + 2, 40)

        # -- Spessore linea (mm) --
        lw = rule.get('line_width', DEFAULT_LINE_WIDTH_MM)
        x_lw = 506
        self.lbl_lw = self._lbl(parent, "lw", x_lw, y + 5)
        self.nud_lw = WinForms.NumericUpDown()
        self.nud_lw.Location = Drawing.Point(x_lw + 18, y + 2)
        self.nud_lw.Size = Drawing.Size(50, 22)
        self.nud_lw.Minimum = System.Decimal(0)
        self.nud_lw.Maximum = System.Decimal(5)
        self.nud_lw.DecimalPlaces = 2
        self.nud_lw.Increment = System.Decimal(5) / System.Decimal(100)
        self.nud_lw.Value = System.Decimal(int(round(max(0.0, min(5.0, lw)) * 100))) / System.Decimal(100)
        parent.Controls.Add(self.nud_lw)

        lbl_mm = WinForms.Label()
        lbl_mm.Text = "mm"
        lbl_mm.Location = Drawing.Point(x_lw + 70, y + 5)
        lbl_mm.Size = Drawing.Size(22, 16)
        parent.Controls.Add(lbl_mm)

        # -- OVP (sovrastampa) --
        self.chk_ovp = WinForms.CheckBox()
        self.chk_ovp.Text = "OVP"
        self.chk_ovp.Location = Drawing.Point(602, y + 3)
        self.chk_ovp.Size = Drawing.Size(50, 20)
        self.chk_ovp.Checked = rule.get('overprint', True)
        parent.Controls.Add(self.chk_ovp)

        self._show_cmyk(ct == 'cmyk')

    def _lbl(self, parent, text, x, y):
        lbl = WinForms.Label()
        lbl.Text = text
        lbl.Location = Drawing.Point(x, y)
        lbl.Size = Drawing.Size(14, 16)
        parent.Controls.Add(lbl)
        return lbl

    def _nud(self, parent, val, lo, hi, x, y, w=44):
        nud = WinForms.NumericUpDown()
        nud.Location = Drawing.Point(x, y)
        nud.Size = Drawing.Size(w, 22)
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
        for c in [self.lbl_r, self.nud_r,
                  self.lbl_g, self.nud_g, self.lbl_b, self.nud_b]:
            c.Visible = not show

    def on_type_changed(self, sender, args):
        self._show_cmyk(self.combo.SelectedIndex == 1)

    def get_settings(self):
        ovp = self.chk_ovp.Checked
        out_name = self.txt_output.Text.strip() or "Layer"
        lw = float(self.nud_lw.Value)
        if self.combo.SelectedIndex == 0:  # Spot
            r = int(self.nud_r.Value)
            g = int(self.nud_g.Value)
            b = int(self.nud_b.Value)
            return {
                'type': 'spot',
                'output_layer': out_name,
                'spot_name': out_name,  # nome layer = nome spot
                'rgb': (r, g, b),
                'cmyk': rgb_to_cmyk(r, g, b),
                'overprint': ovp,
                'line_width': lw,
            }
        else:  # CMYK
            c = float(self.nud_c.Value) / 100.0
            m = float(self.nud_m.Value) / 100.0
            y = float(self.nud_y.Value) / 100.0
            k = float(self.nud_k.Value) / 100.0
            return {
                'type': 'cmyk',
                'output_layer': out_name,
                'cmyk': (c, m, y, k),
                'overprint': ovp,
                'line_width': lw,
            }


class ExportDialog(WinForms.Form):
    """Dialogo v1.5: mappatura colore input -> layer output."""
    def __init__(self, rows_data):
        """rows_data: [(input_rgb, input_label, matched_rule), ...]"""
        self.result = None
        self.layer_rows = []
        self.rows_data = rows_data

        self.Text = "PKG Esporta PDF Vettoriale  v1.5"
        self.FormBorderStyle = WinForms.FormBorderStyle.FixedDialog
        self.MaximizeBox = False
        self.MinimizeBox = False
        self.StartPosition = WinForms.FormStartPosition.CenterScreen

        n = len(rows_data)
        row_h = 28
        header_h = 50
        list_h = min(max(n * row_h + 8, 50), 350)
        footer_h = 80
        self.ClientSize = Drawing.Size(670, header_h + list_h + footer_h)

        # --- Intestazione ---
        lbl_title = WinForms.Label()
        lbl_title.Text = "Mappatura colori input  " + unichr(0x2192) + "  livelli PDF output"
        lbl_title.Font = Drawing.Font(lbl_title.Font, Drawing.FontStyle.Bold)
        lbl_title.Location = Drawing.Point(10, 8)
        lbl_title.AutoSize = True
        self.Controls.Add(lbl_title)

        # Colonne header
        headers = [("Input", 6), ("Layer in", 28),
                   ("", 110),
                   ("Layer out", 126), ("Tipo", 214),
                   ("Colore", 280),
                   ("Spessore", 510), ("", 602)]
        for txt, x in headers:
            if not txt:
                continue
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
        panel.Size = Drawing.Size(660, list_h)
        panel.AutoScroll = True
        panel.BorderStyle = WinForms.BorderStyle.FixedSingle
        self.Controls.Add(panel)

        for i, (input_rgb, input_label, rule) in enumerate(rows_data):
            lr = LayerRow(panel, i * row_h, input_rgb, input_label, rule)
            self.layer_rows.append(lr)

        # --- Footer ---
        y_foot = header_h + list_h + 8

        sep = WinForms.Label()
        sep.BorderStyle = WinForms.BorderStyle.Fixed3D
        sep.Location = Drawing.Point(10, y_foot)
        sep.Size = Drawing.Size(640, 2)
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
        btn_ok.Location = Drawing.Point(470, y_foot + 40)
        btn_ok.Click += self.on_ok
        self.Controls.Add(btn_ok)
        self.AcceptButton = btn_ok

        btn_cancel = WinForms.Button()
        btn_cancel.Text = "Annulla"
        btn_cancel.Size = Drawing.Size(80, 28)
        btn_cancel.Location = Drawing.Point(560, y_foot + 40)
        btn_cancel.Click += self.on_cancel
        self.Controls.Add(btn_cancel)
        self.CancelButton = btn_cancel

    def on_ok(self, sender, args):
        layers = {}
        color_map = {}
        for i, lr in enumerate(self.layer_rows):
            s = lr.get_settings()
            out_name = s['output_layer']
            layers[out_name] = s
            # Mappa il colore input -> layer output
            color_map[lr.input_rgb] = out_name
        self.result = {
            'margin': float(self.margin_box.Value),
            'layers': layers,
            'color_map': color_map,
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

    # Salta annotazioni con markup RTF grezzo
    try:
        pt = geo.PlainText
        if pt and pt.strip().startswith("{\\rtf"):
            print("  [SKIP] Annotazione RTF ignorata.")
            return (stroke, fill)
    except Exception:
        pass

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
            text = strip_rtf(text)
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

def get_dash_pattern_mm(obj, unit_scale):
    """Pattern tratteggio in mm (il CTM nel content stream converte a pt)."""
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
        seg_len = None
        try:
            result = lt.GetSegment(i)
            seg_len = abs(float(result[0]))
        except Exception:
            pass
        if seg_len is None or seg_len < 0.001:
            seg_len = abs(lt.PatternLength / lt.SegmentCount)
        mm_len = seg_len * unit_scale
        pattern.append(max(mm_len, 0.01))
    return pattern


def pdf_safe_name(name):
    """Escape di un nome per PDF Name object.
    '#' va escaped PRIMA degli altri caratteri speciali."""
    out = []
    for ch in name:
        o = ord(ch)
        if ch == '#':
            out.append('#23')
        elif ch == ' ':
            out.append('#20')
        elif ch == '(':
            out.append('#28')
        elif ch == ')':
            out.append('#29')
        elif ch == '/':
            out.append('#2F')
        elif o < 33 or o > 126:
            out.append('#%02X' % o)
        else:
            out.append(ch)
    return ''.join(out)


# =============================================================================
# COSTRUZIONE PDF
# =============================================================================
def build_pdf(objects, settings):
    margin_mm = settings['margin']
    layer_settings = settings['layers']
    color_map = settings['color_map']

    unit_scale = get_unit_scale()

    # Mappa ogni oggetto al suo layer output tramite il colore
    obj_output_layer = {}
    for obj in objects:
        col = get_display_color(obj)
        key = (col.R, col.G, col.B)
        out_layer = color_map.get(key, None)
        if out_layer is None:
            # Fallback: prova con tolleranza minima
            best_dist = float('inf')
            for map_rgb, map_layer in color_map.items():
                d = color_distance(key, map_rgb)
                if d < best_dist:
                    best_dist = d
                    out_layer = map_layer
            if out_layer is None:
                out_layer = "Altro"
        obj_output_layer[id(obj)] = out_layer

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

    # Layer output ordinati (preserva ordine di apparizione)
    layer_names_ordered = []
    layer_ocg = {}
    for obj in objects:
        ln = obj_output_layer[id(obj)]
        if ln not in layer_ocg:
            layer_ocg[ln] = "OC_%d" % len(layer_names_ordered)
            layer_names_ordered.append(ln)

    # Raccolta spot colors
    spot_list = []
    spot_cs = {}
    spot_ovp = {}
    for lname in layer_names_ordered:
        ls = layer_settings.get(lname)
        if ls and ls['type'] == 'spot':
            cs_key = "CS_%d" % len(spot_list)
            rgb = ls['rgb']
            spot_list.append((ls['spot_name'],
                              rgb[0] / 255.0, rgb[1] / 255.0, rgb[2] / 255.0))
            spot_cs[lname] = cs_key
            spot_ovp[lname] = ls.get('overprint', True)

    # Raggruppa oggetti per layer output
    layer_objects = {}
    for obj in objects:
        geo = obj.Geometry
        if geo is None:
            continue
        ln = obj_output_layer[id(obj)]
        if ln not in layer_objects:
            layer_objects[ln] = []
        layer_objects[ln].append(obj)

    # Scala in mm
    scale_mm = unit_scale

    # Content stream: CTM mm->pt + BDC/EMC per layer
    cl = ["q", "1 J", "1 j"]
    cl.append("%.6f 0 0 %.6f 0 0 cm" % (MM_TO_PT, MM_TO_PT))

    n_crv = n_ann = 0

    for lname in layer_names_ordered:
        if lname not in layer_objects:
            continue

        cl.append("/OC /%s BDC" % layer_ocg[lname])

        # Colore layer
        is_spot = lname in spot_cs
        ls = layer_settings.get(lname)
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
            cmyk_ovp = ls.get('overprint', False) if ls else False
            if cmyk_ovp:
                cl.append("/GSOVP gs")
            else:
                cl.append("/GSNOVP gs")
            if ls and 'cmyk' in ls:
                c, m, y, k = ls['cmyk']
            else:
                c, m, y, k = 0, 0, 0, 1
            cl.append("%.4f %.4f %.4f %.4f K" % (c, m, y, k))
            cl.append("%.4f %.4f %.4f %.4f k" % (c, m, y, k))

        # Spessore dal dialogo (override per-layer)
        lw_mm = DEFAULT_LINE_WIDTH_MM
        if ls and 'line_width' in ls:
            lw_mm = ls['line_width']

        for obj in layer_objects[lname]:
            geo = obj.Geometry
            dash = get_dash_pattern_mm(obj, unit_scale)

            cl.append("%.4f w" % lw_mm)
            if dash:
                cl.append("[%s] 0 d" % " ".join("%.4f" % d for d in dash))
            else:
                cl.append("[] 0 d")

            if isinstance(geo, Curve):
                for seg in segments_from_curve(geo):
                    cl.extend(curve_to_pdf_path(
                        seg, ox, oy, scale_mm, False))
                n_crv += 1

            elif isinstance(geo, AnnotationBase):
                s_crvs, f_crvs = curves_from_annotation(geo)
                for crv in s_crvs:
                    for seg in segments_from_curve(crv):
                        cl.extend(curve_to_pdf_path(
                            seg, ox, oy, scale_mm, False))
                if f_crvs:
                    for crv in f_crvs:
                        if isinstance(crv, PolyCurve):
                            nc = crv.ToNurbsCurve()
                            if nc is not None:
                                crv = nc
                        cl.extend(curve_to_pdf_path(
                            crv, ox, oy, scale_mm, True))
                    cl.append("f*")
                n_ann += 1

        cl.append("EMC")

    cl.append("Q")
    print("Processati: %d curve, %d annotazioni. Livelli output: %d." % (
        n_crv, n_ann, len(layer_names_ordered)))
    for lname in layer_names_ordered:
        ls = layer_settings.get(lname)
        lw = ls.get('line_width', DEFAULT_LINE_WIDTH_MM) if ls else DEFAULT_LINE_WIDTH_MM
        tp = ls.get('type', '?') if ls else '?'
        n_obj = len(layer_objects.get(lname, []))
        print("  '%s': %s, lw=%.2fmm, %d oggetti" % (lname, tp, lw, n_obj))
    if spot_list:
        print("Spot: %s" % ", ".join(
            "%s (R%.0f G%.0f B%.0f)" % (s[0], s[1]*255, s[2]*255, s[3]*255)
            for s in spot_list))

    stream = "\n".join(cl)
    print("Stream: %d righe, %d bytes." % (len(cl), len(stream)))
    for line in cl[:15]:
        print("  | %s" % line)

    # =========================================================================
    # ASSEMBLAGGIO PDF con OCG potenziato per compatibilita' Illustrator
    # =========================================================================
    buf = bytearray()
    off = {}
    def w(t):
        buf.extend(t.encode("latin-1"))
    def p():
        return len(buf)

    n_layers = len(layer_names_ordered)
    n_obj = 6 + n_layers  # 1-6 fissi + OCG per layer

    w("%%PDF-1.5\n")
    w("%%\xe2\xe3\xcf\xd3\n")  # marker binario (best practice)

    # Obj 1: Catalog con OCProperties potenziato
    off[1] = p()
    w("1 0 obj\n<< /Type /Catalog /Pages 2 0 R\n")
    if n_layers > 0:
        ocg_refs = " ".join("%d 0 R" % (7 + i) for i in range(n_layers))
        w("   /OCProperties <<\n")
        w("     /OCGs [%s]\n" % ocg_refs)
        w("     /D << /Name (Livelli)\n")
        w("          /Intent /Design\n")
        w("          /Order [%s]\n" % ocg_refs)
        w("          /ON [%s]\n" % ocg_refs)
        w("          /ListMode /AllPages >>\n")
        w("   >>\n")
    w(">>\nendobj\n")

    off[2] = p()
    w("2 0 obj\n<< /Type /Pages /Kids [3 0 R] /Count 1 >>\nendobj\n")

    # Obj 3: Page con Resources
    off[3] = p()
    w("3 0 obj\n<< /Type /Page /Parent 2 0 R\n")
    w("   /MediaBox [0 0 %.2f %.2f]\n" % (pw, ph))
    w("   /Contents 4 0 R\n")
    w("   /Resources <<\n")
    if spot_list:
        w("     /ColorSpace <<\n")
        for i, (sn, sr, sg, sb) in enumerate(spot_list):
            safe = pdf_safe_name(sn)
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
    if n_layers > 0:
        w("     /Properties <<\n")
        for i, ln in enumerate(layer_names_ordered):
            w("       /%s %d 0 R\n" % (layer_ocg[ln], 7 + i))
        w("     >>\n")
    w("   >>\n>>\nendobj\n")

    # Obj 4: Content stream
    off[4] = p()
    w("4 0 obj\n<< /Length %d >>\n" % len(stream))
    w("stream\n")
    w(stream)
    w("\nendstream\nendobj\n")

    # Obj 5-6: ExtGState
    off[5] = p()
    w("5 0 obj\n<< /Type /ExtGState /OP true /op true /OPM 1 >>\nendobj\n")
    off[6] = p()
    w("6 0 obj\n<< /Type /ExtGState /OP false /op false >>\nendobj\n")

    # Obj 7+: OCG objects con Intent e Usage per Illustrator
    for i, ln in enumerate(layer_names_ordered):
        obj_num = 7 + i
        off[obj_num] = p()
        safe_name = ln.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
        w("%d 0 obj\n" % obj_num)
        w("<< /Type /OCG\n")
        w("   /Name (%s)\n" % safe_name)
        w("   /Intent [/View /Design]\n")
        w("   /Usage << /CreatorInfo <<\n")
        w("     /Creator (PKG Esporta PDF Vettoriale)\n")
        w("     /Subtype /Artwork >> >>\n")
        w(">>\nendobj\n")

    # Xref
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

    # Raggruppa oggetti per colore display (chiave di mappatura)
    color_groups = {}   # (R,G,B) -> [obj, ...]
    color_labels = {}   # (R,G,B) -> label (nome primo layer Rhino incontrato)
    for obj in objects:
        col = get_display_color(obj)
        key = (col.R, col.G, col.B)
        if key not in color_groups:
            color_groups[key] = []
            color_labels[key] = get_obj_layer_name(obj)
        color_groups[key].append(obj)

    print("Colori unici trovati: %d" % len(color_groups))

    # Per ogni colore unico, cerca una regola di default
    rows_data = []
    for rgb in sorted(color_groups.keys()):
        label = color_labels[rgb]
        rule = find_matching_rule(*rgb)
        if rule:
            print("  R%d G%d B%d (%s) -> regola '%s'" % (
                rgb[0], rgb[1], rgb[2], label, rule['output_layer']))
            rows_data.append((rgb, label, dict(rule)))  # copia per sicurezza
        else:
            print("  R%d G%d B%d (%s) -> nessuna regola (default)" % (
                rgb[0], rgb[1], rgb[2], label))
            # Default: spot con nome del layer Rhino
            default = {
                'output_layer': label,
                'color_type': 'spot',
                'spot_name': label,
                'rgb': rgb,
                'line_width': DEFAULT_LINE_WIDTH_MM,
                'overprint': True,
            }
            rows_data.append((rgb, label, default))

    # Mostra dialogo
    dlg = ExportDialog(rows_data)
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
