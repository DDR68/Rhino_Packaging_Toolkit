#! python 2
# -*- coding: utf-8 -*-

# =============================================================================
#  PKG ESPORTA PDF VETTORIALE  v2.0  -  Rhino 7 / 8  (IronPython 2.7)
#
#  Novita' v2.0 (spessore per tipo di linea):
#    - RAGGRUPPAMENTO PER (COLORE, TRATTEGGIO): le righe del dialogo
#      ora distinguono linee continue e tratteggiate dello stesso
#      colore, perche' in Rhino hanno spesso plot weight diversi
#      (es. taglio continuo vs cordonatura tratteggiata). Ogni riga
#      legge il proprio spessore Rhino. Le tratteggiate sono marcate
#      con " (tr)" nella colonna "Layer in".
#    - SPESSORE PER-OGGETTO NEL PDF: il "w" viene scritto in base al
#      gruppo (colore, tratteggio) del singolo oggetto, non piu' un
#      unico valore per layer. ERA LA CAUSA per cui lo spessore letto
#      non si vedeva nel PDF: continue e tratteggiate dello stesso
#      colore collassavano su un unico spessore di layer.
#    - Continue e tratteggiate possono restare sullo stesso layer/spot
#      (stessa lastra) mantenendo spessori diversi.
#
#  Novita' v1.9:
#    - Lo spessore iniziale mostrato nella finestra di esportazione viene
#      letto da Rhino: ObjectAttributes.PlotWeight se lo spessore e' da
#      oggetto, altrimenti Layer.PlotWeight / per-viewport se disponibile.
#      Le regole hardcoded restano solo come fallback.
#
#  Novita' v1.8 (correzione dimensione stampa testi/quote):
#    - STILE EFFETTIVO CON OVERRIDE: get_dimstyle ora usa la proprieta'
#      AnnotationBase.DimensionStyle, che include gli override del
#      singolo oggetto (altezza testo, scala modificati nelle
#      proprieta'). Prima si usava solo lo stile padre via FindId,
#      ignorando gli override: ERA LA CAUSA principale della
#      differenza di dimensione rispetto a Rhino.
#    - SCALA REALE: get_annotation_scale ora usa
#      GetDimensionScale(doc, dimstyle, vport) invece della sola
#      proprieta' statica DimensionScale (spesso 1).
#    - DIAGNOSTICA: con DEBUG_ANNOT=True ogni testo/quota stampa
#      altezza padre / effettiva / geo / scala / altezza finale,
#      per verificare al volo cosa viene applicato.
#
#  v1.7: scala model space su testi/quote/frecce (parziale: usava
#    DimensionScale statico); dialogo HiDPI (AutoScaleMode.Font).
#  v1.6: persistenza globale (%APPDATA%), preselect, nome PDF dal
#    .3dm, "apri dopo l'export", fix obj.Id, warning collisione layer.
#  v1.5: regole di mappatura, dialogo rinnovato, OCG Illustrator.
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
import os
import json

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

# Diagnostica annotazioni: stampa altezze e scala per ogni testo/quota.
# Mettere a False per silenziare una volta verificato.
DEBUG_ANNOT = True


# =============================================================================
# REGOLE DI MAPPATURA (default hardcoded)
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
# PERSISTENZA PREFERENZE (%APPDATA%)
# =============================================================================
_user_rules = []   # popolato in main() da load_user_prefs()


def _prefs_dir():
    appdata = System.Environment.GetFolderPath(
        System.Environment.SpecialFolder.ApplicationData)
    return os.path.join(appdata, "PKG_ExportPDF")


def _prefs_path():
    return os.path.join(_prefs_dir(), "prefs.json")


def load_user_prefs():
    """Carica regole e preferenze da %APPDATA%/PKG_ExportPDF/prefs.json.
    Restituisce (rules_list, margin, open_after)."""
    try:
        path = _prefs_path()
        if not os.path.isfile(path):
            return ([], DEFAULT_MARGIN_MM, True)
        with open(path, "r") as f:
            data = json.load(f)
        rules = data.get("rules", [])
        for r in rules:
            r['match_color'] = tuple(r['match_color'])
            if 'rgb' in r:
                r['rgb'] = tuple(r['rgb'])
            if 'cmyk' in r:
                r['cmyk'] = tuple(r['cmyk'])
        margin = data.get("margin", DEFAULT_MARGIN_MM)
        open_after = data.get("open_after", True)
        return (rules, margin, open_after)
    except Exception as e:
        print("  [INFO] Nessuna preferenza salvata (%s)." % e)
        return ([], DEFAULT_MARGIN_MM, True)


def save_user_prefs(rows_settings, margin, open_after):
    """Salva le regole correnti e le preferenze in %APPDATA%."""
    try:
        d = _prefs_dir()
        if not os.path.isdir(d):
            os.makedirs(d)
        data = {
            "rules": [],
            "margin": margin,
            "open_after": open_after,
        }
        for s in rows_settings:
            entry = {
                'match_color': list(s['match_color']),
                'match_tolerance': 5,
                'match_dashed': bool(s.get('match_dashed', False)),
                'output_layer': s['output_layer'],
                'color_type': s['type'],
                'spot_name': s.get('spot_name', s['output_layer']),
                'rgb': list(s.get('rgb', s['match_color'])),
                'cmyk': list(s.get('cmyk', (0, 0, 0, 1))),
                'line_width': s['line_width'],
                'overprint': s['overprint'],
            }
            data["rules"].append(entry)
        path = _prefs_path()
        with open(path, "w") as f:
            json.dump(data, f, indent=2)
        print("Preferenze salvate in: %s" % path)
    except Exception as e:
        print("  [WARN] Salvataggio preferenze fallito: %s" % e)


# =============================================================================
# UTILITA'
# =============================================================================
def get_unit_scale():
    return Rhino.RhinoMath.UnitScale(
        sc.doc.ModelUnitSystem, Rhino.UnitSystem.Millimeters)

def fmt(v):
    return "%.4f" % v

def strip_rtf(text):
    """Estrae testo plain da una stringa RTF."""
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
    """Stile di quota EFFETTIVO dell'annotazione, con gli override del
    singolo oggetto inclusi (altezza testo, scala, ecc. modificati nelle
    proprieta'). La v1.5/1.6 usava solo lo stile padre via FindId, quindi
    ignorava gli override: e' la causa della dimensione diversa da Rhino."""
    # 1) Proprieta' DimensionStyle: include gli override; se non ci sono
    #    override restituisce lo stile padre.
    try:
        ds = geo.DimensionStyle
        _ = ds.TextHeight   # verifica che sia davvero uno stile (non un metodo)
        if ds is not None:
            return ds
    except Exception:
        pass
    # 2) Fallback: stile padre per Id
    try:
        ds = sc.doc.DimStyles.FindId(geo.DimensionStyleId)
        if ds is not None:
            return ds
    except Exception:
        pass
    return sc.doc.DimStyles.Current

def _active_viewport():
    try:
        return sc.doc.Views.ActiveView.ActiveViewport
    except Exception:
        return None

def get_annotation_scale(geo, dimstyle):
    """Fattore con cui Rhino MOSTRA/STAMPA l'annotazione.
    Usa AnnotationBase.GetDimensionScale(doc, dimstyle, vport), che
    restituisce la scala di visualizzazione reale (scala spazio modello /
    dettaglio). In fallback usa la proprieta' statica DimensionScale."""
    vport = _active_viewport()
    if vport is not None:
        try:
            s = geo.GetDimensionScale(sc.doc, dimstyle, vport)
            if s and s > 0:
                return float(s)
        except Exception:
            pass
    try:
        s = dimstyle.DimensionScale
        if s and s > 0:
            return float(s)
    except Exception:
        pass
    return 1.0

def _scale_curves(crvs, anchor, factor):
    """Scala in-place una lista di curve attorno a un punto di ancoraggio."""
    if abs(factor - 1.0) < 1e-9:
        return crvs
    xf = Transform.Scale(anchor, factor)
    for c in crvs:
        if c is not None:
            c.Transform(xf)
    return crvs

def rgb_to_cmyk(r, g, b):
    """RGB 0-255 -> CMYK 0.0-1.0.
    Nero puro -> nero di registro (C100 M100 Y100 K100)."""
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


def _valid_plot_weight_mm(value):
    """Normalizza uno spessore di stampa Rhino.
    RhinoCommon usa i millimetri: >0 = spessore valido, 0 = default Rhino,
    <0 = non stampare. Per 0/<0 restituiamo None e lasciamo il fallback
    alle regole del dialogo, senza inventare un valore non scritto in Rhino."""
    try:
        w = float(value)
    except Exception:
        return None
    if w > 0.0:
        return w
    return None


def _layer_per_viewport_plot_weight(layer):
    """Lettura difensiva dello spessore per-viewport, se presente.
    In Rhino 7/8 la firma puo' cambiare leggermente; se non disponibile
    si passa serenamente a layer.PlotWeight."""
    try:
        vport = _active_viewport()
        if vport is None:
            return None
        ids = []
        for attr_name in ["Id", "ViewportId"]:
            try:
                vid = getattr(vport, attr_name)
                if vid and vid not in ids:
                    ids.append(vid)
            except Exception:
                pass
        for vid in ids:
            try:
                w = _valid_plot_weight_mm(layer.GetPerViewportPlotWeight(vid))
                if w is not None:
                    return w
            except Exception:
                pass
    except Exception:
        pass
    return None


def get_effective_plot_weight_mm(obj):
    """Restituisce lo spessore di stampa effettivo Rhino in mm.
    Rispetta PlotWeightSource: da oggetto, da layer, o da parent/layer.
    Se Rhino indica 0 = default oppure -1 = non stampare, restituisce None."""
    try:
        attr = obj.Attributes
        src = attr.PlotWeightSource
    except Exception:
        attr = None
        src = None

    try:
        src_name = str(src)
    except Exception:
        src_name = ""

    # Spessore assegnato direttamente all'oggetto.
    if src_name.endswith("PlotWeightFromObject"):
        w_obj = _valid_plot_weight_mm(attr.PlotWeight)
        if w_obj is not None:
            return w_obj

    # Default: spessore dal layer. Anche PlotWeightFromParent, senza parent
    # gestibile qui, viene trattato come layer.
    try:
        layer = sc.doc.Layers[attr.LayerIndex]
        w_vp = _layer_per_viewport_plot_weight(layer)
        if w_vp is not None:
            return w_vp
        return _valid_plot_weight_mm(layer.PlotWeight)
    except Exception:
        pass

    return None


def get_group_plot_weight_mm(objects):
    """Spessore iniziale per una riga del dialogo.
    Se nel gruppo ci sono valori diversi, usa il primo valore valido ma
    restituisce anche la lista dei valori trovati per diagnostica."""
    vals = []
    for obj in objects:
        w = get_effective_plot_weight_mm(obj)
        if w is not None:
            vals.append(round(w, 4))
    if not vals:
        return (None, [])
    uniq = sorted(set(vals))
    return (vals[0], uniq)


def color_distance(c1, c2):
    """Distanza euclidea RGB."""
    return math.sqrt(
        (c1[0] - c2[0]) ** 2 +
        (c1[1] - c2[1]) ** 2 +
        (c1[2] - c2[2]) ** 2)


def find_matching_rule(r, g, b, is_dashed=None):
    """Trova la regola con match migliore.
    Cerca prima nelle regole utente salvate, poi nei default.
    Se la regola specifica 'match_dashed', deve combaciare con lo stato
    tratteggio dell'oggetto; le regole senza 'match_dashed' valgono per
    entrambi. A parita', si preferisce la regola piu' specifica (dash)."""
    for rules_list in [_user_rules, DEFAULT_RULES]:
        best = None
        best_dist = float('inf')
        best_specific = False
        for rule in rules_list:
            dist = color_distance((r, g, b), rule['match_color'])
            tol = rule.get('match_tolerance', 10)
            if dist > tol:
                continue
            rdash = rule.get('match_dashed', None)
            if rdash is not None and is_dashed is not None and rdash != is_dashed:
                continue  # regola per l'altro tipo di linea
            specific = (rdash is not None and is_dashed is not None
                        and rdash == is_dashed)
            if (specific and not best_specific) or \
               (specific == best_specific and dist < best_dist):
                best = rule
                best_dist = dist
                best_specific = specific
        if best is not None:
            return best
    return None


# =============================================================================
# DIALOGO IMPOSTAZIONI v1.6
# =============================================================================
class LayerRow(object):
    """Controlli per una riga di mappatura nel dialogo.
    Layout ingrandito: swatch, campi e controlli piu' grandi per una
    migliore leggibilita' (il font e' ereditato dal Panel contenitore)."""
    def __init__(self, parent, y, group_key, input_label, rule):
        # group_key = (rgb_tuple, is_dashed)
        self.group_key = group_key
        self.input_rgb = group_key[0]
        self.is_dashed = group_key[1]
        self.rule = rule

        ir, ig, ib = self.input_rgb
        self.input_color = Drawing.Color.FromArgb(255, ir, ig, ib)

        # -- Colore input (swatch) --
        pnl = WinForms.Panel()
        pnl.Location = Drawing.Point(8, y + 7)
        pnl.Size = Drawing.Size(24, 24)
        pnl.BackColor = self.input_color
        pnl.BorderStyle = WinForms.BorderStyle.FixedSingle
        parent.Controls.Add(pnl)

        # -- Label input (nome layer Rhino) --
        lbl = WinForms.Label()
        lbl.Text = input_label
        lbl.Location = Drawing.Point(42, y + 9)
        lbl.Size = Drawing.Size(118, 22)
        parent.Controls.Add(lbl)

        # -- Freccia --
        arr = WinForms.Label()
        arr.Text = unichr(0x2192)
        arr.Location = Drawing.Point(164, y + 6)
        arr.Size = Drawing.Size(24, 24)
        arr.Font = Drawing.Font(arr.Font.FontFamily, 13.0)
        parent.Controls.Add(arr)

        # -- Nome layer output (editable) --
        self.txt_output = WinForms.TextBox()
        self.txt_output.Text = rule.get('output_layer', input_label)
        self.txt_output.Location = Drawing.Point(192, y + 6)
        self.txt_output.Size = Drawing.Size(128, 26)
        parent.Controls.Add(self.txt_output)

        # -- Tipo output --
        self.combo = WinForms.ComboBox()
        self.combo.Items.AddRange(System.Array[System.Object](
            ["Spot", "CMYK"]))
        ct = rule.get('color_type', 'spot')
        self.combo.SelectedIndex = 0 if ct == 'spot' else 1
        self.combo.DropDownStyle = WinForms.ComboBoxStyle.DropDownList
        self.combo.Location = Drawing.Point(330, y + 6)
        self.combo.Size = Drawing.Size(86, 26)
        self.combo.SelectedIndexChanged += self.on_type_changed
        parent.Controls.Add(self.combo)

        # -- Controlli Spot: R/G/B --
        spot_rgb = rule.get('rgb', self.input_rgb)
        x = 426
        self.lbl_r = self._lbl(parent, "R", x, y + 9)
        self.nud_r = self._nud(parent, spot_rgb[0], 0, 255, x + 16, y + 6, 54)
        self.lbl_g = self._lbl(parent, "G", x + 76, y + 9)
        self.nud_g = self._nud(parent, spot_rgb[1], 0, 255, x + 92, y + 6, 54)
        self.lbl_b = self._lbl(parent, "B", x + 152, y + 9)
        self.nud_b = self._nud(parent, spot_rgb[2], 0, 255, x + 168, y + 6, 54)

        # -- Controlli CMYK: C/M/Y/K (stessa posizione, nascosti) --
        rule_cmyk = rule.get('cmyk', None)
        if rule_cmyk is None:
            rule_cmyk = rgb_to_cmyk(ir, ig, ib)
        x2 = 426
        self.lbl_c = self._lbl(parent, "C", x2, y + 9)
        self.nud_c = self._nud(parent, int(rule_cmyk[0] * 100 + 0.5),
                               0, 100, x2 + 16, y + 6, 50)
        self.lbl_m = self._lbl(parent, "M", x2 + 72, y + 9)
        self.nud_m = self._nud(parent, int(rule_cmyk[1] * 100 + 0.5),
                               0, 100, x2 + 90, y + 6, 50)
        self.lbl_y2 = self._lbl(parent, "Y", x2 + 146, y + 9)
        self.nud_y = self._nud(parent, int(rule_cmyk[2] * 100 + 0.5),
                               0, 100, x2 + 162, y + 6, 50)
        self.lbl_k = self._lbl(parent, "K", x2 + 218, y + 9)
        self.nud_k = self._nud(parent, int(rule_cmyk[3] * 100 + 0.5),
                               0, 100, x2 + 234, y + 6, 50)

        # -- Spessore linea (mm) --
        lw = rule.get('line_width', DEFAULT_LINE_WIDTH_MM)
        x_lw = 726
        self.lbl_lw = self._lbl(parent, "lw", x_lw, y + 9)
        self.nud_lw = WinForms.NumericUpDown()
        self.nud_lw.Location = Drawing.Point(x_lw + 24, y + 6)
        self.nud_lw.Size = Drawing.Size(62, 26)
        self.nud_lw.Minimum = System.Decimal(0)
        self.nud_lw.Maximum = System.Decimal(5)
        self.nud_lw.DecimalPlaces = 2
        self.nud_lw.Increment = System.Decimal(5) / System.Decimal(100)
        self.nud_lw.Value = System.Decimal(int(round(max(0.0, min(5.0, lw)) * 100))) / System.Decimal(100)
        parent.Controls.Add(self.nud_lw)

        lbl_mm = WinForms.Label()
        lbl_mm.Text = "mm"
        lbl_mm.Location = Drawing.Point(x_lw + 90, y + 9)
        lbl_mm.Size = Drawing.Size(28, 20)
        parent.Controls.Add(lbl_mm)

        # -- OVP (sovrastampa) --
        self.chk_ovp = WinForms.CheckBox()
        self.chk_ovp.Text = "OVP"
        self.chk_ovp.Location = Drawing.Point(852, y + 7)
        self.chk_ovp.Size = Drawing.Size(64, 24)
        self.chk_ovp.Checked = rule.get('overprint', True)
        parent.Controls.Add(self.chk_ovp)

        self._show_cmyk(ct == 'cmyk')

    def _lbl(self, parent, text, x, y):
        lbl = WinForms.Label()
        lbl.Text = text
        lbl.Location = Drawing.Point(x, y)
        lbl.Size = Drawing.Size(16, 20)
        parent.Controls.Add(lbl)
        return lbl

    def _nud(self, parent, val, lo, hi, x, y, w=54):
        nud = WinForms.NumericUpDown()
        nud.Location = Drawing.Point(x, y)
        nud.Size = Drawing.Size(w, 26)
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
                'spot_name': out_name,
                'rgb': (r, g, b),
                'cmyk': rgb_to_cmyk(r, g, b),
                'overprint': ovp,
                'line_width': lw,
                'match_color': self.input_rgb,
                'match_dashed': self.is_dashed,
                'group_key': self.group_key,
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
                'match_color': self.input_rgb,
                'match_dashed': self.is_dashed,
                'group_key': self.group_key,
            }


class ExportDialog(WinForms.Form):
    """Dialogo v2.0: mappatura colore input -> layer output.
    Layout ingrandito e finestra piu' larga per una migliore leggibilita'."""
    def __init__(self, rows_data, saved_margin, saved_open_after):
        """rows_data: [(group_key, input_label, matched_rule), ...]
        dove group_key = (rgb_tuple, is_dashed).
        saved_margin: margine caricato dalle preferenze.
        saved_open_after: stato checkbox caricato dalle preferenze."""
        self.result = None
        self.layer_rows = []
        self.rows_data = rows_data
        self._rows_settings = []   # popolato in on_ok per persistenza

        self.Text = "PKG Esporta PDF Vettoriale  v2.0"
        self.FormBorderStyle = WinForms.FormBorderStyle.FixedDialog
        self.MaximizeBox = False
        self.MinimizeBox = False
        self.StartPosition = WinForms.FormStartPosition.CenterScreen

        # Auto-scaling DPI: a risoluzioni/zoom diversi (es. 125/150% in
        # fabbrica) WinForms riscala in proporzione font e controlli, cosi'
        # le caselle non tagliano piu' le cifre. Il font del Form resta
        # quello di default (baseline 6x13) per non ri-scalare due volte:
        # l'ingrandimento e' gia' nelle coordinate e nel font del Panel.
        self.AutoScaleDimensions = Drawing.SizeF(6.0, 13.0)
        self.AutoScaleMode = WinForms.AutoScaleMode.Font

        # Font piu' grande applicato ai contenitori (non al Form) per
        # ingrandire il testo dei controlli senza alterare l'auto-scaling.
        try:
            ui_font = Drawing.Font("Segoe UI", 9.75)
        except Exception:
            ui_font = Drawing.Font(WinForms.Control.DefaultFont.FontFamily, 9.75)
        self._ui_font = ui_font

        client_w = 950
        panel_w = 940
        n = len(rows_data)
        row_h = 36
        header_h = 58
        list_h = min(max(n * row_h + 10, 60), 468)
        footer_h = 104
        self.ClientSize = Drawing.Size(client_w, header_h + list_h + footer_h)

        # --- Intestazione ---
        lbl_title = WinForms.Label()
        lbl_title.Text = ("Mappatura colori input  " + unichr(0x2192)
                          + "  livelli PDF output    [(tr) = linea tratteggiata]")
        lbl_title.Font = Drawing.Font(lbl_title.Font.FontFamily, 11.0,
                                      Drawing.FontStyle.Bold)
        lbl_title.Location = Drawing.Point(12, 10)
        lbl_title.AutoSize = True
        self.Controls.Add(lbl_title)

        # Colonne header (allineate alle colonne di LayerRow)
        headers = [("Input", 8), ("Layer in", 42),
                   ("Layer out", 192), ("Tipo", 330),
                   ("Colore", 426),
                   ("Spessore", 726), ("OVP", 852)]
        for txt, x in headers:
            if not txt:
                continue
            lh = WinForms.Label()
            lh.Text = txt
            lh.Location = Drawing.Point(x, 36)
            lh.AutoSize = True
            lh.ForeColor = Drawing.Color.Gray
            lh.Font = Drawing.Font(lh.Font.FontFamily, 8.5)
            self.Controls.Add(lh)

        # --- Panel layer ---
        panel = WinForms.Panel()
        panel.Location = Drawing.Point(0, header_h)
        panel.Size = Drawing.Size(panel_w, list_h)
        panel.AutoScroll = True
        panel.BorderStyle = WinForms.BorderStyle.FixedSingle
        panel.Font = ui_font  # ereditato da tutti i controlli delle righe
        self.Controls.Add(panel)

        for i, (group_key, input_label, rule) in enumerate(rows_data):
            lr = LayerRow(panel, i * row_h, group_key, input_label, rule)
            self.layer_rows.append(lr)

        # --- Footer ---
        y_foot = header_h + list_h + 10

        sep = WinForms.Label()
        sep.BorderStyle = WinForms.BorderStyle.Fixed3D
        sep.Location = Drawing.Point(12, y_foot)
        sep.Size = Drawing.Size(client_w - 24, 2)
        self.Controls.Add(sep)

        # Margine
        lbl_m = WinForms.Label()
        lbl_m.Text = "Margine pagina:"
        lbl_m.Location = Drawing.Point(12, y_foot + 16)
        lbl_m.AutoSize = True
        lbl_m.Font = ui_font
        self.Controls.Add(lbl_m)

        self.margin_box = WinForms.NumericUpDown()
        self.margin_box.Location = Drawing.Point(150, y_foot + 13)
        self.margin_box.Size = Drawing.Size(72, 26)
        self.margin_box.Font = ui_font
        self.margin_box.Minimum = System.Decimal(0)
        self.margin_box.Maximum = System.Decimal(200)
        self.margin_box.DecimalPlaces = 1
        self.margin_box.Value = System.Decimal(
            int(round(max(0.0, min(200.0, saved_margin)) * 10))
        ) / System.Decimal(10)
        self.Controls.Add(self.margin_box)

        lbl_mm = WinForms.Label()
        lbl_mm.Text = "mm"
        lbl_mm.Location = Drawing.Point(228, y_foot + 16)
        lbl_mm.AutoSize = True
        lbl_mm.Font = ui_font
        self.Controls.Add(lbl_mm)

        # Checkbox: Apri PDF dopo l'export
        self.chk_open = WinForms.CheckBox()
        self.chk_open.Text = "Apri PDF dopo l'export"
        self.chk_open.Location = Drawing.Point(330, y_foot + 15)
        self.chk_open.Size = Drawing.Size(240, 24)
        self.chk_open.Font = ui_font
        self.chk_open.Checked = saved_open_after
        self.Controls.Add(self.chk_open)

        # Pulsanti
        btn_ok = WinForms.Button()
        btn_ok.Text = "Esporta"
        btn_ok.Size = Drawing.Size(104, 34)
        btn_ok.Location = Drawing.Point(client_w - 224, y_foot + 46)
        btn_ok.Font = ui_font
        btn_ok.Click += self.on_ok
        self.Controls.Add(btn_ok)
        self.AcceptButton = btn_ok

        btn_cancel = WinForms.Button()
        btn_cancel.Text = "Annulla"
        btn_cancel.Size = Drawing.Size(104, 34)
        btn_cancel.Location = Drawing.Point(client_w - 112, y_foot + 46)
        btn_cancel.Font = ui_font
        btn_cancel.Click += self.on_cancel
        self.Controls.Add(btn_cancel)
        self.CancelButton = btn_cancel

    def on_ok(self, sender, args):
        layers = {}
        color_map = {}
        width_map = {}
        all_settings = []
        collisions = []

        for i, lr in enumerate(self.layer_rows):
            s = lr.get_settings()
            out_name = s['output_layer']
            gk = s['group_key']
            all_settings.append(s)

            # Collisione: stesso layer output con colore/tipo/overprint
            # diversi. Lo spessore NON e' piu' un conflitto: e' applicato
            # per-oggetto, quindi continue e tratteggiate possono condividere
            # lo stesso layer/spot con spessori diversi.
            if out_name in layers:
                prev = layers[out_name]
                if (prev.get('type') != s.get('type')
                    or prev.get('overprint') != s.get('overprint')
                    or prev.get('rgb') != s.get('rgb')
                    or prev.get('cmyk') != s.get('cmyk')):
                    if out_name not in collisions:
                        collisions.append(out_name)

            layers[out_name] = s
            color_map[gk] = out_name
            width_map[gk] = s['line_width']

        # Warning collisione
        if collisions:
            msg = ("Attenzione: i seguenti layer di output ricevono "
                   "colori/tipi diversi con impostazioni in conflitto:\n\n"
                   + ", ".join(collisions)
                   + "\n\nVerranno usate le impostazioni dell'ultima "
                   "riga (lo spessore resta per-oggetto). Continuare?")
            result = WinForms.MessageBox.Show(
                msg, "Collisione layer",
                WinForms.MessageBoxButtons.YesNo,
                WinForms.MessageBoxIcon.Warning)
            if result != WinForms.DialogResult.Yes:
                return

        self._rows_settings = all_settings
        self.result = {
            'margin': float(self.margin_box.Value),
            'layers': layers,
            'color_map': color_map,
            'width_map': width_map,
            'open_after': self.chk_open.Checked,
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

    if DEBUG_ANNOT:
        try:
            parent_ds = sc.doc.DimStyles.FindId(geo.DimensionStyleId)
            parent_h = parent_ds.TextHeight if parent_ds else -1
        except Exception:
            parent_h = -1
        try:
            eff_h = dimstyle.TextHeight
        except Exception:
            eff_h = -1
        try:
            geo_h = geo.TextHeight
        except Exception:
            geo_h = -1
        sc_factor = get_annotation_scale(geo, dimstyle)
        print("  [DBG] %s | h_padre=%.3f h_eff=%.3f h_geo=%.3f scala=%.3f "
              "-> altezza finale=%.3f" % (
                  type(geo).__name__, parent_h, eff_h, geo_h, sc_factor,
                  (geo_h if geo_h > 0 else eff_h) * sc_factor))

    try:
        pt = geo.PlainText
        if pt and pt.strip().startswith("{\\rtf"):
            print("  [SKIP] Annotazione RTF ignorata.")
            return (stroke, fill)
    except Exception:
        pass

    if isinstance(geo, TextEntity):
        dim_scale = get_annotation_scale(geo, dimstyle)
        try:
            anchor = geo.Plane.Origin
        except Exception:
            anchor = Point3d.Origin
        try:
            result = geo.CreateCurves(dimstyle, False)
            if result and len(result) > 0:
                crvs = list(result)
                _scale_curves(crvs, anchor, dim_scale)
                fill.extend(close_text_outlines(crvs))
                return (stroke, fill)
        except Exception:
            pass
        try:
            result = geo.Explode()
            if result:
                raw = [item for item in result if isinstance(item, Curve)]
                _scale_curves(raw, anchor, dim_scale)
                fill.extend(close_text_outlines(raw))
        except Exception:
            pass
        return (stroke, fill)

    if isinstance(geo, Dimension):
        dim_scale = get_annotation_scale(geo, dimstyle)
        arrow1 = arrow2 = text_3d = None
        text_half_w = 0.0
        text_height = dimstyle.TextHeight * dim_scale

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
                    text_height = geo.TextHeight * dim_scale
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
                    tgm = tg * dim_scale
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
                al = dimstyle.ArrowLength * dim_scale
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
        dim_scale = get_annotation_scale(geo, dimstyle)
        try:
            anchor = geo.Plane.Origin
        except Exception:
            anchor = Point3d.Origin
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
                crvs = list(result)
                _scale_curves(crvs, anchor, dim_scale)
                fill.extend(close_text_outlines(crvs))
        except Exception:
            pass
        return (stroke, fill)

    try:
        dim_scale = get_annotation_scale(geo, dimstyle)
        try:
            anchor = geo.Plane.Origin
        except Exception:
            anchor = Point3d.Origin
        result = geo.CreateCurves(dimstyle, False)
        if result and len(result) > 0:
            crvs = list(result)
            _scale_curves(crvs, anchor, dim_scale)
            fill.extend(close_text_outlines(crvs))
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
    """Pattern tratteggio in mm."""
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


def obj_is_dashed(obj):
    """True se l'oggetto usa un tipo di linea tratteggiato (non continuo).
    Riusa la stessa risoluzione oggetto->layer di get_dash_pattern_mm:
    pattern vuoto = continuo, pattern presente = tratteggiato."""
    try:
        return len(get_dash_pattern_mm(obj, 1.0)) > 0
    except Exception:
        return False


def pdf_safe_name(name):
    """Escape di un nome per PDF Name object."""
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
    width_map = settings.get('width_map', {})

    unit_scale = get_unit_scale()

    # Mappa ogni oggetto al suo layer output tramite la chiave composita
    # (colore, tratteggio). Usa obj.Id (GUID stabile).
    obj_output_layer = {}
    obj_group_key = {}
    for obj in objects:
        col = get_display_color(obj)
        rgb = (col.R, col.G, col.B)
        gk = (rgb, obj_is_dashed(obj))
        obj_group_key[obj.Id] = gk

        out_layer = color_map.get(gk, None)
        # Fallback 1: stesso colore, qualsiasi tratteggio
        if out_layer is None:
            for (m_rgb, m_dash), m_layer in color_map.items():
                if m_rgb == rgb:
                    out_layer = m_layer
                    break
        # Fallback 2: colore piu' vicino
        if out_layer is None:
            best_dist = float('inf')
            for (m_rgb, m_dash), m_layer in color_map.items():
                d = color_distance(rgb, m_rgb)
                if d < best_dist:
                    best_dist = d
                    out_layer = m_layer
        if out_layer is None:
            out_layer = "Altro"
        obj_output_layer[obj.Id] = out_layer

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
        ln = obj_output_layer[obj.Id]
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
        ln = obj_output_layer[obj.Id]
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

        # Spessore di fallback per il layer (se un oggetto non ha gruppo)
        lw_layer_default = DEFAULT_LINE_WIDTH_MM
        if ls and 'line_width' in ls:
            lw_layer_default = ls['line_width']

        for obj in layer_objects[lname]:
            geo = obj.Geometry
            dash = get_dash_pattern_mm(obj, unit_scale)

            # Spessore PER-OGGETTO: dipende dal gruppo (colore, tratteggio)
            # del singolo oggetto, non da un unico valore di layer. Cosi'
            # continue e tratteggiate dello stesso colore mantengono il
            # proprio spessore anche sulla stessa lastra.
            gk = obj_group_key.get(obj.Id)
            lw_mm = width_map.get(gk, lw_layer_default)

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
        tp = ls.get('type', '?') if ls else '?'
        n_obj = len(layer_objects.get(lname, []))
        # Spessori effettivi (per-oggetto) presenti nel layer
        lws = set()
        for obj in layer_objects.get(lname, []):
            gk = obj_group_key.get(obj.Id)
            lws.add(round(width_map.get(gk,
                          ls.get('line_width', DEFAULT_LINE_WIDTH_MM)
                          if ls else DEFAULT_LINE_WIDTH_MM), 3))
        if len(lws) <= 1:
            lw_txt = "%.2fmm" % (list(lws)[0] if lws else DEFAULT_LINE_WIDTH_MM)
        else:
            lw_txt = "spessori: " + ", ".join("%.2f" % v for v in sorted(lws))
        print("  '%s': %s, %s, %d oggetti" % (lname, tp, lw_txt, n_obj))
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
    n_obj = 6 + n_layers

    w("%%PDF-1.5\n")
    w("%%\xe2\xe3\xcf\xd3\n")

    # Obj 1: Catalog con OCProperties
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
    global _user_rules

    # Carica preferenze salvate
    saved_rules, saved_margin, saved_open_after = load_user_prefs()
    _user_rules = saved_rules
    if saved_rules:
        print("Caricate %d regole utente da %s" % (
            len(saved_rules), _prefs_path()))

    # Selezione oggetti (con supporto pre-selezione)
    go = Rhino.Input.Custom.GetObject()
    go.SetCommandPrompt(
        "Seleziona curve, quote e testi da esportare in PDF vettoriale")
    go.GeometryFilter = (Rhino.DocObjects.ObjectType.Curve
                         | Rhino.DocObjects.ObjectType.Annotation)
    go.SubObjectSelect = False
    go.GroupSelect = True
    go.EnablePreSelect(True, True)
    go.GetMultiple(1, 0)
    if go.CommandResult() != Rhino.Commands.Result.Success:
        return

    objects = [go.Object(i).Object() for i in range(go.ObjectCount)]
    if not objects:
        print("Nessun oggetto selezionato.")
        return
    print("%d oggetti selezionati." % len(objects))

    # Raggruppa oggetti per (colore display, tratteggio) = chiave di mappatura.
    # Continue e tratteggiate dello stesso colore diventano righe distinte,
    # perche' in Rhino hanno spesso plot weight diversi.
    color_groups = {}
    color_labels = {}
    for obj in objects:
        col = get_display_color(obj)
        rgb = (col.R, col.G, col.B)
        dashed = obj_is_dashed(obj)
        key = (rgb, dashed)
        if key not in color_groups:
            color_groups[key] = []
            color_labels[key] = get_obj_layer_name(obj)
        color_groups[key].append(obj)

    print("Gruppi (colore, tratteggio) trovati: %d" % len(color_groups))

    # Per ogni gruppo cerca una regola (utente -> default -> fallback)
    # e inizializza lo spessore con il Print Width reale di Rhino, se presente.
    rows_data = []
    for key in sorted(color_groups.keys()):
        rgb, dashed = key
        base_label = color_labels[key]
        # Etichetta mostrata nel dialogo: marca le tratteggiate con " (tr)"
        label = base_label + (" (tr)" if dashed else "")
        rule = find_matching_rule(rgb[0], rgb[1], rgb[2], dashed)
        tipo_txt = "tratteggiata" if dashed else "continua"
        if rule:
            row_rule = dict(rule)
            print("  R%d G%d B%d %s (%s) -> regola '%s'" % (
                rgb[0], rgb[1], rgb[2], tipo_txt, base_label,
                row_rule['output_layer']))
        else:
            print("  R%d G%d B%d %s (%s) -> nessuna regola (default)" % (
                rgb[0], rgb[1], rgb[2], tipo_txt, base_label))
            row_rule = {
                'output_layer': base_label,
                'color_type': 'spot',
                'spot_name': base_label,
                'rgb': rgb,
                'line_width': DEFAULT_LINE_WIDTH_MM,
                'overprint': True,
            }

        rhino_lw, all_lw = get_group_plot_weight_mm(color_groups[key])
        if rhino_lw is not None:
            # Il valore mostrato nella finestra parte dallo spessore stampa
            # Rhino del gruppo, non dalla regola hardcoded.
            row_rule['line_width'] = rhino_lw
            print("      spessore Rhino -> %.3f mm" % rhino_lw)
            if len(all_lw) > 1:
                print("      [WARN] stesso gruppo con piu' spessori Rhino: %s. "
                      "La riga usa %.3f mm." % (
                          ", ".join("%.3f" % v for v in all_lw), rhino_lw))
        else:
            print("      spessore Rhino non impostato: uso %.3f mm dalla regola" % (
                row_rule.get('line_width', DEFAULT_LINE_WIDTH_MM)))

        rows_data.append((key, label, row_rule))

    # Mostra dialogo (con preferenze salvate)
    dlg = ExportDialog(rows_data, saved_margin, saved_open_after)
    if dlg.ShowDialog() != WinForms.DialogResult.OK or dlg.result is None:
        print("Annullato.")
        return

    # Genera PDF
    pdf_data = build_pdf(objects, dlg.result)
    if pdf_data is None:
        return
    print("PDF: %d bytes." % len(pdf_data))

    # Salva PDF (con nome e cartella proposti dal .3dm)
    fd = Rhino.UI.SaveFileDialog()
    fd.Filter = "PDF (*.pdf)|*.pdf"
    fd.Title = "Salva PDF vettoriale"
    fd.DefaultExt = "pdf"
    doc_path = sc.doc.Path
    if doc_path:
        fd.InitialDirectory = os.path.dirname(doc_path)
        fd.FileName = os.path.splitext(
            os.path.basename(doc_path))[0] + ".pdf"
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
        print("Errore salvataggio: %s" % str(e))
        return

    # Salva preferenze (regole + margine + open_after)
    save_user_prefs(
        dlg._rows_settings,
        dlg.result['margin'],
        dlg.result['open_after'])

    # Apri PDF dopo l'export (se richiesto)
    if dlg.result.get('open_after', False):
        try:
            System.Diagnostics.Process.Start(filepath)
        except Exception as e:
            print("  [WARN] Impossibile aprire il PDF: %s" % e)

main()
