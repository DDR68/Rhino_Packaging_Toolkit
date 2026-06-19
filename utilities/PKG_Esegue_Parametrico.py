#! python 2
# -*- coding: utf-8 -*-
"""
PKG_Genera_Da_TXT.py   v2.1
Rhino 7/8  |  IronPython 2.7  |  RhinoCommon

Workflow:
  1. Seleziona il file TXT (dialog file apre per primo)
  2. Estrae automaticamente L, P, A, S, C, T, E risolvendo il sistema
     lineare implicito nelle formule X_param/Y_param dei punti
  3. Apre il dialog con i valori pre-caricati + preview in tempo reale
  4. Genera le curve sui layer Taglio / Cordone / ... con tag di pulizia
  5. Supporta l'asse di specchiatura (linea con UserText chiave "A=")

Geometry builders (ironpython-examples.md):
  Line  → Line(p1, p2).ToNurbsCurve()                          (§14)
  Conic → NurbsCurve(3, True, order, n) + Point4d omogenee     (§12)
  Arc   → Arc(p1, p_mid, p2).ToNurbsCurve()  o  centro+angoli  (§13)
  Free  → NurbsCurve(3, True, order, n) + Point4d + knots      (§12)
"""
from __future__ import division

import Rhino
import Rhino.Geometry as rg
import scriptcontext as sc
import System
import System.Windows.Forms as WF
import System.Drawing as SD
import System.Drawing.Drawing2D as Drawing2D
import math
import re
import os
import codecs

_VERSION = "2.1"

# ── Tag oggetti generati ───────────────────────────────────────────
TAG_KEY = "PKG_GEN_TXT"
TAG_VAL = "1"

# ── Colonne TXT ────────────────────────────────────────────────────
C_TIPO, C_GEOM, C_LAYER = 1, 2, 4
C_X1, C_Y1, C_X2, C_Y2  = 5, 6, 7, 8

# ── Variabili parametriche ─────────────────────────────────────────
VAR_NAMES = ["L", "P", "A", "S", "C", "T", "E"]
DEFAULTS  = {"L": 50.0, "P": 25.0, "A": 80.0, "S": 0.5,
             "C": 18.0, "T": 18.0, "E": 3.0}

# ── Colori layer standard ──────────────────────────────────────────
LAYER_COLORS = {
    "Taglio":               SD.Color.Black,
    "Cordone":              SD.Color.FromArgb(255,   0,   0),
    "MezzoTaglio":          SD.Color.FromArgb(  0, 170,   0),
    "Foratore":             SD.Color.FromArgb(255, 140,   0),
    "PKG_Costruzione_Cyan": SD.Color.FromArgb(  0, 200, 200),
    "Predefinito":          SD.Color.FromArgb(128, 128, 128),
}

# Colori preview
_COL_TAGLIO  = SD.Color.Black
_COL_CORDONE = SD.Color.FromArgb(255,   0,   0)
_COL_AXIS    = SD.Color.FromArgb(  0, 200, 200)   # Cyan: asse specchiatura
_COL_OTHER   = SD.Color.FromArgb( 70, 130, 180)

ALLOWED_FUNCS = {
    "abs":  abs,  "sqrt": math.sqrt,
    "sin":  math.sin, "cos": math.cos, "tan": math.tan, "pi": math.pi,
}
_SAFE_RE = re.compile(r"^[0-9\.\+\-\*\/\(\)\,\s a-zA-Z_]+$")


# ═══════════════════════════════════════════════════════════════════
#  Parsing e valutazione
# ═══════════════════════════════════════════════════════════════════

def parse_ut(s):
    """'k1=v1;k2=v2;...' → dict."""
    d = {}
    if not s or s == "-":
        return d
    for kv in s.split(";"):
        if "=" in kv:
            k, v = kv.split("=", 1)
            d[k.strip()] = v.strip()
    return d


def safe_eval(expr, vd):
    """Valuta espressione parametrica PKG. Ritorna float o None."""
    if not expr or expr in ("-", "--", "non_associato"):
        return None
    expr = expr.strip()
    if not _SAFE_RE.match(expr):
        return None
    tokens = re.findall(r"[a-zA-Z_][a-zA-Z_0-9]*", expr)
    allowed = set(VAR_NAMES) | set(ALLOWED_FUNCS)
    for tok in tokens:
        if tok not in allowed:
            return None
    try:
        code = compile(expr, "<pkg>", "eval")
    except SyntaxError:
        return None
    ns = {"__builtins__": {}}
    ns.update(ALLOWED_FUNCS)
    ns.update(vd)
    try:
        return float(eval(code, ns, {}))
    except Exception:
        return None


def eval_pt(param_str, vd):
    """'(ex, ey)' → Point3d o None."""
    if not param_str:
        return None
    s = param_str.strip()
    # Cerca virgola al top-level delle parentesi esterne
    m = re.match(r"\(\s*(.+?),\s*(.+?)\s*\)\s*$", s)
    if not m:
        if s.startswith("(") and s.endswith(")"):
            inner = s[1:-1]
            depth = 0; split_pos = None
            for i, ch in enumerate(inner):
                if ch in "([":   depth += 1
                elif ch in ")]": depth -= 1
                elif ch == "," and depth == 0:
                    split_pos = i; break
            if split_pos is None:
                return None
            ex, ey = inner[:split_pos].strip(), inner[split_pos+1:].strip()
        else:
            return None
    else:
        ex, ey = m.group(1), m.group(2)
    x = safe_eval(ex, vd)
    y = safe_eval(ey, vd)
    if x is None or y is None:
        return None
    return rg.Point3d(x, y, 0.0)


# ═══════════════════════════════════════════════════════════════════
#  Derivazione automatica dei parametri dal TXT
# ═══════════════════════════════════════════════════════════════════

def derive_vars(rows):
    """
    Estrae L, P, A, S, C, T, E risolvendo iterativamente il sistema
    lineare dai punti parametrici del TXT.

    Metodo: per ogni formula con N incognite sintattiche,
    imposta TUTTE a 0 (val_zero), poi testa ognuna a 1.
    Se UNA SOLA ha coefficiente != 0 (le altre si cancellano
    algebricamente, es. (C+L-S)+S = C+L), risolve per quella.
    """
    pairs = []
    for row in rows:
        if len(row) < 6 or row[C_GEOM].strip() != "Point":
            continue
        ut = parse_ut(row[-1])
        for ax in ("X", "Y"):
            formula = ut.get("%s_param" % ax)
            reale   = ut.get("%s_reale" % ax)
            if formula and reale and formula.strip() not in ("0", "-", ""):
                try:
                    pairs.append((formula.strip(), float(reale)))
                except ValueError:
                    pass

    known  = {}
    for _it in range(20):
        changed = False
        for formula, target in pairs:
            if not _SAFE_RE.match(formula):
                continue
            tokens  = set(re.findall(r"[a-zA-Z_][a-zA-Z_0-9]*", formula))
            unknown = [v for v in VAR_NAMES if v in tokens and v not in known]
            if not unknown:
                continue

            # Namespace: noti + tutte le incognite a 0
            ns0 = {"__builtins__": {}}
            ns0.update(ALLOWED_FUNCS); ns0.update(known)
            for uv in unknown:
                ns0[uv] = 0.0

            try:
                code     = compile(formula, "<d>", "eval")
                val_zero = float(eval(code, ns0, {}))
            except Exception:
                continue

            # Coefficienti effettivi (cancellazioni algebriche → coeff=0)
            effective = []
            for uv in unknown:
                ns1 = dict(ns0); ns1[uv] = 1.0
                try:
                    coeff = float(eval(code, ns1, {})) - val_zero
                    if abs(coeff) > 1e-10:
                        effective.append((uv, coeff))
                except Exception:
                    pass

            if len(effective) == 1:
                var, coeff = effective[0]
                if var not in known:
                    known[var] = round((target - val_zero) / coeff, 6)
                    changed = True

        if not changed:
            break

    return known


# ═══════════════════════════════════════════════════════════════════
#  Dati per il preview
# ═══════════════════════════════════════════════════════════════════

def build_preview_curves(rows):
    """
    Lista di (tipo_T/C/..., 'line'|'conic'|'abs', data) per il preview.
    'abs' usa coordinate assolute (non scala con i parametri).
    """
    result = []
    for row in rows:
        if len(row) < 6:
            continue
        tipo = row[C_TIPO]
        if tipo == "P":
            continue
        geom = row[C_GEOM].strip()
        ut   = parse_ut(row[-1])

        # Asse di specchiatura → tipo "X" per colore Cyan nel preview
        if "A" in ut:
            p1s = ut.get("P1_param"); p2s = ut.get("P2_param")
            if p1s and p2s:
                result.append(("X", "line", ut))
            continue   # non aggiungere come curva normale

        has_p1 = bool(ut.get("P1_param"))
        has_p2 = bool(ut.get("P2_param"))
        tipo_orig = ut.get("Tipo_Originale", "")
        cmd       = ut.get("Comando", "")

        if has_p1 and has_p2:
            if tipo_orig == "Nurbs" or cmd == "_InterpCrv":
                result.append((tipo, "conic", ut))
            elif tipo_orig == "Arc" or cmd == "_Arc":
                result.append((tipo, "arc", ut))
            else:
                result.append((tipo, "line", ut))
        elif geom == "Line":
            # Fallback assoluto (non parametrico)
            try:
                x1, y1 = float(row[C_X1]), float(row[C_Y1])
                x2, y2 = float(row[C_X2]), float(row[C_Y2])
                result.append((tipo, "abs", (x1, y1, x2, y2)))
            except (ValueError, IndexError):
                pass
    return result


# ═══════════════════════════════════════════════════════════════════
#  Disegno preview
# ═══════════════════════════════════════════════════════════════════

def draw_preview(g, curves, vd, W, H):
    """Disegna il tracciato scalato nella Graphics del bitmap."""
    MARGIN = 10

    # Raccoglie tutti i punti per il bounding box
    all_pts = []
    for tipo, geom, data in curves:
        if geom in ("line", "conic"):
            ut = data
            p1 = eval_pt(ut.get("P1_param"), vd)
            p2 = eval_pt(ut.get("P2_param"), vd)
            if p1: all_pts.append((p1.X, p1.Y))
            if p2: all_pts.append((p2.X, p2.Y))
        elif geom == "abs":
            x1, y1, x2, y2 = data
            all_pts.extend([(x1, y1), (x2, y2)])

    if len(all_pts) < 2:
        return

    min_x = min(p[0] for p in all_pts)
    max_x = max(p[0] for p in all_pts)
    min_y = min(p[1] for p in all_pts)
    max_y = max(p[1] for p in all_pts)

    rx = max_x - min_x
    ry = max_y - min_y
    if rx < 1 or ry < 1:
        return

    avail_w = W - 2 * MARGIN
    avail_h = H - 2 * MARGIN
    scale = min(avail_w / rx, avail_h / ry)

    # Centra orizzontalmente e verticalmente
    ox = MARGIN + (avail_w - rx * scale) / 2.0
    oy = MARGIN + (avail_h - ry * scale) / 2.0

    def sc(x, y):
        """Model → screen (Y flippato)."""
        return (ox + (x - min_x) * scale,
                H  - oy - (y - min_y) * scale)

    pen_T = SD.Pen(_COL_TAGLIO,  1.0)
    pen_C = SD.Pen(_COL_CORDONE, 1.0)
    pen_X = SD.Pen(_COL_AXIS,    1.0)   # Cyan: asse specchiatura
    pen_O = SD.Pen(_COL_OTHER,   1.0)

    try:
        for tipo, geom, data in curves:
            pen = pen_T if tipo == "T" else (pen_C if tipo == "C" else (pen_X if tipo == "X" else pen_O))

            if geom == "line":
                ut = data
                p1 = eval_pt(ut.get("P1_param"), vd)
                p2 = eval_pt(ut.get("P2_param"), vd)
                if p1 and p2:
                    ax, ay = sc(p1.X, p1.Y)
                    bx, by = sc(p2.X, p2.Y)
                    g.DrawLine(pen, int(ax), int(ay), int(bx), int(by))

            elif geom == "conic":
                ut = data
                p1 = eval_pt(ut.get("P1_param"), vd)
                p2 = eval_pt(ut.get("P2_param"), vd)
                if p1 and p2:
                    try:
                        fu  = float(ut.get("CtrlProp_u", "0"))
                        fv  = float(ut.get("CtrlProp_v", "0"))
                        fw  = float(ut.get("CtrlPeso_w", "1.0"))
                        if fw < 1e-9:
                            fw = 1.0
                        dx  = p2.X - p1.X
                        dy  = p2.Y - p1.Y
                        cpx = p1.X + fu * dx
                        cpy = p1.Y + fv * dy
                        # Bezier RAZIONALE grado 2: pesi [1, fw, 1]
                        # Per fw=1 il denominatore = 1 → coincide col non-razionale
                        # Per fw<1 (archi circolari) corregge il rigonfiamento
                        N = 12
                        prev = sc(p1.X, p1.Y)
                        for i in range(1, N + 1):
                            t   = i / float(N)
                            mt  = 1.0 - t
                            wx  = mt*mt*p1.X + 2.0*mt*t*cpx*fw + t*t*p2.X
                            wy  = mt*mt*p1.Y + 2.0*mt*t*cpy*fw + t*t*p2.Y
                            w   = mt*mt       + 2.0*mt*t*fw     + t*t
                            curr = sc(wx / w, wy / w)
                            g.DrawLine(pen, int(prev[0]), int(prev[1]),
                                       int(curr[0]), int(curr[1]))
                            prev = curr
                    except Exception:
                        ax, ay = sc(p1.X, p1.Y)
                        bx, by = sc(p2.X, p2.Y)
                        g.DrawLine(pen, int(ax), int(ay), int(bx), int(by))

            elif geom == "arc":
                ut = data
                p1 = eval_pt(ut.get("P1_param"), vd)
                p2 = eval_pt(ut.get("P2_param"), vd)
                if p1 and p2:
                    centro = eval_pt(ut.get("Centro_param"), vd)
                    if centro:
                        r = math.sqrt((p1.X-centro.X)**2+(p1.Y-centro.Y)**2)
                        if r > 1e-9:
                            verso  = ut.get("Verso", "CCW")
                            ang1   = math.atan2(p1.Y-centro.Y, p1.X-centro.X)
                            ang2   = math.atan2(p2.Y-centro.Y, p2.X-centro.X)
                            if verso == "CCW":
                                span = ang2 - ang1
                                if span <= 0: span += 2.0*math.pi
                            else:
                                span = ang1 - ang2
                                if span <= 0: span += 2.0*math.pi
                                span = -span
                            N    = 16
                            prev = sc(p1.X, p1.Y)
                            for i in range(1, N + 1):
                                t   = i / float(N)
                                ang = ang1 + t * span
                                px  = centro.X + r * math.cos(ang)
                                py  = centro.Y + r * math.sin(ang)
                                curr = sc(px, py)
                                g.DrawLine(pen, int(prev[0]), int(prev[1]),
                                           int(curr[0]), int(curr[1]))
                                prev = curr

            elif geom == "abs":
                x1, y1, x2, y2 = data
                ax, ay = sc(x1, y1)
                bx, by = sc(x2, y2)
                g.DrawLine(pen, int(ax), int(ay), int(bx), int(by))

    finally:
        pen_T.Dispose()
        pen_C.Dispose()
        pen_X.Dispose()
        pen_O.Dispose()


# ═══════════════════════════════════════════════════════════════════
#  Dialog con preview live
# ═══════════════════════════════════════════════════════════════════

class _DlgParams(WF.Form):
    """
    Dialog parametri con preview a destra aggiornato in tempo reale.
    Carica i default già derivati dal TXT. Supporta asse/specchiatura.
    """
    _FIELDS = [
        ("L", "Larghezza pannello  L", "L"),
        ("P", "Profondita\u2019  P",   "P"),
        ("A", "Altezza  A",            "A"),
        ("S", "Spessore cartone  S",   "S"),
        (None, None, None),
        ("C", "Aletta incollaggio  C", "C"),
        ("T", "Lock inferiore  T",     "T"),
        ("E", "Smusso angoli  E",      "E"),
    ]

    def __init__(self, defaults, preview_curves, has_axis=False, has_fillets=False):
        self.SuspendLayout()
        self._tbs = {}
        self._preview_curves = preview_curves
        self._preview_bmp    = None

        # ── Form ──────────────────────────────────────────────────
        FORM_W, FORM_H = 548, 500
        self.Text            = u"PKG \u2013 Genera Da TXT   v%s" % _VERSION
        self.FormBorderStyle = WF.FormBorderStyle.FixedDialog
        self.MaximizeBox     = False
        self.MinimizeBox     = False
        self.StartPosition   = WF.FormStartPosition.CenterScreen
        self.ClientSize      = SD.Size(FORM_W, FORM_H)

        # ── Intestazione parametri ─────────────────────────────────
        LX = 10          # left origin X
        lbl_h = WF.Label()
        lbl_h.Text     = "Parametri [mm]:"
        lbl_h.Font     = SD.Font("Segoe UI", 9.0, SD.FontStyle.Bold)
        lbl_h.Location = SD.Point(LX, 12)
        lbl_h.Size     = SD.Size(225, 18)
        self.Controls.Add(lbl_h)

        y = 35
        for (key, label, _) in self._FIELDS:
            if key is None:
                sep = WF.Label()
                sep.BorderStyle = WF.BorderStyle.Fixed3D
                sep.Location    = SD.Point(LX, y + 5)
                sep.Size        = SD.Size(225, 2)
                self.Controls.Add(sep)
                y += 16
                continue

            lbl = WF.Label()
            lbl.Text     = label
            lbl.Location = SD.Point(LX, y + 3)
            lbl.Size     = SD.Size(148, 18)
            self.Controls.Add(lbl)

            val = defaults.get(key, DEFAULTS.get(key, 0.0))
            tb  = WF.TextBox()
            tb.Text      = ("%.4g" % val).replace(".", ",")
            tb.Location  = SD.Point(LX + 150, y)
            tb.Size      = SD.Size(75, 22)
            tb.TextAlign = WF.HorizontalAlignment.Right
            tb.TextChanged += self._on_change
            self.Controls.Add(tb)
            self._tbs[key] = tb
            y += 28

        # ── Separatore + Checkbox ──────────────────────────────────
        y += 6
        sep2 = WF.Label()
        sep2.BorderStyle = WF.BorderStyle.Fixed3D
        sep2.Location    = SD.Point(LX, y + 4)
        sep2.Size        = SD.Size(225, 2)
        self.Controls.Add(sep2)
        y += 14

        self._cb_mirror = WF.CheckBox()
        self._cb_mirror.Text     = "Specchia sull'asse"
        self._cb_mirror.Location = SD.Point(LX, y)
        self._cb_mirror.Size     = SD.Size(225, 20)
        self._cb_mirror.Enabled  = has_axis
        self._cb_mirror.Checked  = False
        self.Controls.Add(self._cb_mirror)
        y += 24

        self._cb_axis = WF.CheckBox()
        self._cb_axis.Text     = "Mostra asse di costruzione"
        self._cb_axis.Location = SD.Point(LX, y)
        self._cb_axis.Size     = SD.Size(225, 20)
        self._cb_axis.Enabled  = has_axis
        self._cb_axis.Checked  = False
        self.Controls.Add(self._cb_axis)
        y += 24

        self._cb_clear = WF.CheckBox()
        self._cb_clear.Text     = "Cancella generazione precedente"
        self._cb_clear.Location = SD.Point(LX, y)
        self._cb_clear.Size     = SD.Size(225, 20)
        self._cb_clear.Checked  = True
        self.Controls.Add(self._cb_clear)
        y += 24

        self._cb_fillets = WF.CheckBox()
        self._cb_fillets.Text     = "Calcola raccordi"
        self._cb_fillets.Location = SD.Point(LX, y)
        self._cb_fillets.Size     = SD.Size(225, 20)
        self._cb_fillets.Enabled  = has_fillets
        self._cb_fillets.Checked  = has_fillets
        self.Controls.Add(self._cb_fillets)

        # ── Preview ────────────────────────────────────────────────
        PX  = 240          # preview origin X
        PY  = 10
        PW  = FORM_W - PX - 10
        PH  = FORM_H - 130  # spazio per legenda + pulsanti

        lbl_prev = WF.Label()
        lbl_prev.Text      = "Preview"
        lbl_prev.Font      = SD.Font("Segoe UI", 8.0, SD.FontStyle.Italic)
        lbl_prev.ForeColor = SD.Color.FromArgb(80, 80, 80)
        lbl_prev.Location  = SD.Point(PX, PY)
        lbl_prev.Size      = SD.Size(PW, 16)
        lbl_prev.TextAlign = SD.ContentAlignment.MiddleCenter
        self.Controls.Add(lbl_prev)

        self._pb = WF.PictureBox()
        self._pb.Location    = SD.Point(PX, PY + 18)
        self._pb.Size        = SD.Size(PW, PH)
        self._pb.BorderStyle = WF.BorderStyle.Fixed3D
        self._pb.BackColor   = SD.Color.White
        self._pb.SizeMode    = WF.PictureBoxSizeMode.Normal
        self.Controls.Add(self._pb)

        # Legenda preview: 2 o 3 voci a seconda della presenza dell'asse
        leg_y = PY + 18 + PH + 2
        leg_font = SD.Font("Segoe UI", 7.5)
        if has_axis:
            third_W = PW // 3
            lbl_tag = WF.Label()
            lbl_tag.Text      = u"\u25a0 Taglio"
            lbl_tag.Font      = leg_font
            lbl_tag.ForeColor = SD.Color.Black
            lbl_tag.Location  = SD.Point(PX, leg_y)
            lbl_tag.Size      = SD.Size(third_W, 14)
            lbl_tag.TextAlign = SD.ContentAlignment.MiddleCenter
            self.Controls.Add(lbl_tag)

            lbl_cord = WF.Label()
            lbl_cord.Text      = u"\u25a0 Cordone"
            lbl_cord.Font      = leg_font
            lbl_cord.ForeColor = SD.Color.FromArgb(255, 0, 0)
            lbl_cord.Location  = SD.Point(PX + third_W, leg_y)
            lbl_cord.Size      = SD.Size(third_W, 14)
            lbl_cord.TextAlign = SD.ContentAlignment.MiddleCenter
            self.Controls.Add(lbl_cord)

            lbl_ax = WF.Label()
            lbl_ax.Text      = u"\u25a0 Asse"
            lbl_ax.Font      = leg_font
            lbl_ax.ForeColor = SD.Color.FromArgb(0, 200, 200)
            lbl_ax.Location  = SD.Point(PX + 2 * third_W, leg_y)
            lbl_ax.Size      = SD.Size(PW - 2 * third_W, 14)
            lbl_ax.TextAlign = SD.ContentAlignment.MiddleCenter
            self.Controls.Add(lbl_ax)
        else:
            half_W = PW // 2
            lbl_tag = WF.Label()
            lbl_tag.Text      = u"\u25a0 Taglio"
            lbl_tag.Font      = leg_font
            lbl_tag.ForeColor = SD.Color.Black
            lbl_tag.Location  = SD.Point(PX, leg_y)
            lbl_tag.Size      = SD.Size(half_W, 14)
            lbl_tag.TextAlign = SD.ContentAlignment.MiddleRight
            self.Controls.Add(lbl_tag)

            lbl_cord = WF.Label()
            lbl_cord.Text      = u"\u25a0 Cordone"
            lbl_cord.Font      = leg_font
            lbl_cord.ForeColor = SD.Color.FromArgb(255, 0, 0)
            lbl_cord.Location  = SD.Point(PX + half_W + 8, leg_y)
            lbl_cord.Size      = SD.Size(PW - half_W - 8, 14)
            lbl_cord.TextAlign = SD.ContentAlignment.MiddleLeft
            self.Controls.Add(lbl_cord)

        # ── Pulsanti ───────────────────────────────────────────────
        BY = FORM_H - 54   # pulsanti sempre visibili
        btn_ok = WF.Button()
        btn_ok.Text         = "Genera"
        btn_ok.DialogResult = WF.DialogResult.OK
        btn_ok.Location     = SD.Point(FORM_W // 2 - 100, BY)
        btn_ok.Size         = SD.Size(90, 28)
        self.Controls.Add(btn_ok)
        self.AcceptButton   = btn_ok

        btn_no = WF.Button()
        btn_no.Text         = "Annulla"
        btn_no.DialogResult = WF.DialogResult.Cancel
        btn_no.Location     = SD.Point(FORM_W // 2 + 10, BY)
        btn_no.Size         = SD.Size(90, 28)
        self.Controls.Add(btn_no)
        self.CancelButton   = btn_no

        self.ResumeLayout(False)
        self._refresh_preview()

    # ── Aggiornamento preview ──────────────────────────────────────
    def _on_change(self, s, e):
        self._refresh_preview()

    def _refresh_preview(self):
        vd = self._read_vd()
        W  = self._pb.Width
        H  = self._pb.Height
        if W <= 0 or H <= 0:
            return
        bmp = SD.Bitmap(W, H)
        g   = SD.Graphics.FromImage(bmp)
        try:
            g.SmoothingMode = Drawing2D.SmoothingMode.AntiAlias
            g.Clear(SD.Color.White)
            if vd and all(vd.get(k, 0) > 0 for k in ("L", "P", "A")):
                draw_preview(g, self._preview_curves, vd, W, H)
            else:
                font  = SD.Font("Segoe UI", 8.5)
                brush = SD.SolidBrush(SD.Color.FromArgb(160, 160, 160))
                sf    = SD.StringFormat()
                sf.Alignment     = SD.StringAlignment.Center
                sf.LineAlignment = SD.StringAlignment.Center
                g.DrawString("Inserisci valori L, P, A > 0",
                             font, brush,
                             SD.RectangleF(0, 0, W, H), sf)
                font.Dispose(); brush.Dispose()
        finally:
            g.Dispose()
        old = self._pb.Image
        self._pb.Image = bmp
        if old is not None:
            old.Dispose()

    # ── Lettura valori ─────────────────────────────────────────────
    def _read_vd(self):
        vd = {}
        for k, tb in self._tbs.items():
            raw = tb.Text.strip().replace(",", ".")
            try:
                vd[k] = float(raw)
            except ValueError:
                pass
        return vd

    def get_values(self):
        vd = {}
        for k, tb in self._tbs.items():
            raw = tb.Text.strip().replace(",", ".")
            try:
                vd[k] = float(raw)
            except ValueError:
                WF.MessageBox.Show(
                    "Valore non valido per '%s': '%s'" % (k, raw),
                    "Errore input",
                    WF.MessageBoxButtons.OK,
                    WF.MessageBoxIcon.Error)
                return None
        return vd

    def get_opts(self):
        return {
            "mirror":   bool(self._cb_mirror.Checked   and self._cb_mirror.Enabled),
            "axis":     bool(self._cb_axis.Checked     and self._cb_axis.Enabled),
            "clear":    bool(self._cb_clear.Checked),
            "fillets":  bool(self._cb_fillets.Checked  and self._cb_fillets.Enabled),
        }


# ═══════════════════════════════════════════════════════════════════
#  Costruttori di geometria
#  Regole da ironpython-examples.md:
#  §12 NurbsCurve razionale → NurbsCurve(3, True, order, n) + Point4d
#      MAI NurbsCurve.Create (non-razionale) + SetPoint(i, Point3d, w)
#  §14 Linea → Line(p1, p2).ToNurbsCurve()
#  §13 Arco  → Arc(cerchio, Interval).ToNurbsCurve()
# ═══════════════════════════════════════════════════════════════════

def build_line(ut, vd):
    """Linea retta parametrica da P1_param / P2_param."""
    p1 = eval_pt(ut.get("P1_param"), vd)
    p2 = eval_pt(ut.get("P2_param"), vd)
    if p1 and p2:
        # §14: Line(p1,p2).ToNurbsCurve() — non LineCurve
        return rg.Line(p1, p2).ToNurbsCurve(), None
    return None, "line: punti non valutabili"


def build_conic(ut, vd):
    """
    NURBS razionale grado 2 (raccordo conico / Bezier conica).
    §12 ironpython-examples.md:
      - Costruttore NurbsCurve(3, True, order, n_pts) per curva RAZIONALE
      - Knot vector clamped esplicito
      - Point4d in coordinate omogenee: Point4d(x*w, y*w, z*w, w)
      - MAI NurbsCurve.Create + SetPoint(i, Point3d, w) su curva non-razionale
    """
    p1 = eval_pt(ut.get("P1_param"), vd)
    p2 = eval_pt(ut.get("P2_param"), vd)
    if p1 is None or p2 is None:
        return None, "conic: P1/P2 non valutabili"
    try:
        fu = float(ut.get("CtrlProp_u", "0"))
        fv = float(ut.get("CtrlProp_v", "0"))
    except (ValueError, TypeError):
        return None, "conic: CtrlProp illeggibili"
    try:
        fw = float(ut.get("CtrlPeso_w", "1.0"))
        if fw < 1e-9:
            fw = 1.0
    except (ValueError, TypeError):
        fw = 1.0
    dx  = p2.X - p1.X
    dy  = p2.Y - p1.Y
    cpx = p1.X + fu * dx
    cpy = p1.Y + fv * dy

    # Curva NURBS razionale: dim=3, rational=True, order=3, n_pts=3
    degree = 2
    nc = rg.NurbsCurve(3, True, degree + 1, 3)

    # Knot vector clamped per grado 2 con 3 CP:
    # Knots.Count = n_pts + degree - 1 = 4  →  [0, 0, 1, 1]
    for i in range(nc.Knots.Count):
        nc.Knots[i] = 0.0 if i < degree else 1.0

    # Control points in coordinate omogenee  Point4d(x*w, y*w, z*w, w)
    nc.Points.SetPoint(0, rg.Point4d(p1.X,       p1.Y,       0.0, 1.0))
    nc.Points.SetPoint(1, rg.Point4d(cpx * fw,   cpy * fw,   0.0, fw ))
    nc.Points.SetPoint(2, rg.Point4d(p2.X,       p2.Y,       0.0, 1.0))

    if not nc.IsValid:
        return None, "conic: NurbsCurve non valida dopo costruzione"
    return nc, None


def _arc_pmid(p1, p2, centro, r, verso):
    """
    Calcola il punto medio di un arco dalla convenzione CW/CCW.
    Ritorna (Point3d_pmid, span_signed) o None.
    """
    ang1 = math.atan2(p1.Y - centro.Y, p1.X - centro.X)
    ang2 = math.atan2(p2.Y - centro.Y, p2.X - centro.X)
    if verso == "CCW":
        span = ang2 - ang1
        if span <= 0:
            span += 2.0 * math.pi
        amiddle = ang1 + span / 2.0
    else:                       # CW
        span = ang1 - ang2
        if span <= 0:
            span += 2.0 * math.pi
        amiddle = ang1 - span / 2.0
    pmx = centro.X + r * math.cos(amiddle)
    pmy = centro.Y + r * math.sin(amiddle)
    return rg.Point3d(pmx, pmy, 0.0), (-span if verso == "CW" else span)


def build_arc(ut, vd):
    """
    Arco parametrico.  Priorità:
      1. Centro_param (valutato con vd) + raggio da |P1-Centro| + pmid da CCW/CW
      2. Punto_medio fisso dal TXT (fallback)
      3. Centro_geom assoluto + Circle+Interval (ultimo fallback)
    """
    p1 = eval_pt(ut.get("P1_param"), vd)
    p2 = eval_pt(ut.get("P2_param"), vd)
    if p1 is None or p2 is None:
        return None, "arc: P1/P2 non valutabili"

    verso = ut.get("Verso", "CCW")

    # ── Approccio 1: centro parametrico + raggio + pmid calcolato ─────
    centro = eval_pt(ut.get("Centro_param"), vd)
    if centro is not None:
        r = math.sqrt((p1.X - centro.X) ** 2 + (p1.Y - centro.Y) ** 2)
        if r > 1e-9:
            p_mid, _ = _arc_pmid(p1, p2, centro, r, verso)
            try:
                arc = rg.Arc(p1, p_mid, p2)
                if arc.IsValid:
                    return arc.ToNurbsCurve(), None
            except Exception:
                pass

    # ── Approccio 2: Punto_medio fisso dal TXT ─────────────────────────
    pm_str = ut.get("Punto_medio")
    if pm_str:
        try:
            parts  = pm_str.split(",")
            mx, my = float(parts[0]), float(parts[1])
            p_mid  = rg.Point3d(mx, my, 0.0)
            arc    = rg.Arc(p1, p_mid, p2)
            if arc.IsValid:
                return arc.ToNurbsCurve(), None
        except Exception:
            pass

    # ── Approccio 3: Centro_geom assoluto + Circle+Interval ────────────
    cg = ut.get("Centro_geom")
    if cg:
        try:
            cx, cy = float(cg.split(",")[0]), float(cg.split(",")[1])
            r_num  = float(ut.get("Raggio", "0"))
            a0     = math.radians(float(ut.get("AngStart_deg", "0")))
            a1     = math.radians(float(ut.get("AngEnd_deg",   "0")))
            normal = rg.Vector3d(0, 0, -1) if verso == "CW" else rg.Vector3d(0, 0, 1)
            plane  = rg.Plane(rg.Point3d(cx, cy, 0.0), normal)
            iv     = rg.Interval(abs(a0), abs(a1))
            if iv.Length < 1e-9:
                iv = rg.Interval(0.0, 2.0 * math.pi)
            arc = rg.Arc(rg.Circle(plane, r_num), iv)
            if arc.IsValid:
                return arc.ToNurbsCurve(), None
        except Exception:
            pass

    return None, "arc: tutti gli approcci falliti"


def build_free(ut, vd):
    """
    NURBS libera da CtrlPoints (x,y,w|x,y,w|...) + Nodi opzionali.
    Costruzione con Point4d per il supporto razionale (§12).
    Gli estremi vengono spostati alle coordinate parametriche se disponibili.
    """
    cps_str = ut.get("CtrlPoints")
    if not cps_str:
        return None, "free: CtrlPoints assente"

    cps = []
    for tok in cps_str.split("|"):
        tok = tok.strip()
        if not tok:
            continue
        parts = tok.split(",")
        try:
            x = float(parts[0]); y = float(parts[1])
            w = float(parts[2]) if len(parts) >= 3 else 1.0
            cps.append((x, y, w))
        except (ValueError, IndexError):
            return None, "free: CP malformato '%s'" % tok
    if len(cps) < 2:
        return None, "free: meno di 2 CP"

    try:
        degree = int(ut.get("Grado", "3"))
    except (ValueError, TypeError):
        degree = 3
    degree = min(degree, len(cps) - 1)
    order  = degree + 1
    n_pts  = len(cps)

    # NurbsCurve razionale
    nc  = rg.NurbsCurve(3, True, order, n_pts)
    kc  = nc.Knots.Count
    nodi_str = ut.get("Nodi")
    if nodi_str:
        try:
            knots = [float(v) for v in nodi_str.split("|")]
            if len(knots) == kc:
                for i in range(kc):
                    nc.Knots[i] = knots[i]
            else:
                nodi_str = None  # incompatibile → default
        except Exception:
            nodi_str = None
    if not nodi_str:
        # Knot vector clamped uniforme
        inner = kc - 2 * degree
        for i in range(kc):
            if i < degree:
                nc.Knots[i] = 0.0
            elif i >= kc - degree:
                nc.Knots[i] = 1.0
            else:
                nc.Knots[i] = (i - degree + 1) / float(inner + 1)

    for i, (x, y, w) in enumerate(cps):
        if w is None or w < 1e-12:
            w = 1.0
        nc.Points.SetPoint(i, rg.Point4d(x * w, y * w, 0.0, w))

    if not nc.IsValid:
        return None, "free: NurbsCurve non valida"

    # Sposta gli estremi alle coordinate parametriche (se annotate)
    p1n = eval_pt(ut.get("P1_param"), vd)
    p2n = eval_pt(ut.get("P2_param"), vd)
    if p1n or p2n:
        o1 = rg.Point3d(cps[0][0],  cps[0][1],  0.0)
        o2 = rg.Point3d(cps[-1][0], cps[-1][1], 0.0)
        n1 = p1n if p1n else o1
        n2 = p2n if p2n else o2
        d_orig = o1.DistanceTo(o2)
        if d_orig > 1e-9:
            # Similitudine: traslazione + rotazione + scala uniforme
            vo = o2 - o1; vn = n2 - n1
            sc_f   = vn.Length / vo.Length if vo.Length > 1e-9 else 1.0
            t_pre  = rg.Transform.Translation(rg.Point3d.Origin - o1)
            ang    = rg.Vector3d.VectorAngle(vo, vn, rg.Plane.WorldXY)
            t_rot  = rg.Transform.Rotation(ang, rg.Vector3d.ZAxis, rg.Point3d.Origin)
            t_scl  = rg.Transform.Scale(rg.Point3d.Origin, sc_f)
            t_post = rg.Transform.Translation(n1 - rg.Point3d.Origin)
            xf = t_post * t_scl * t_rot * t_pre
            nc.Transform(xf)
    return nc, None


def build_from_absolute(cells):
    """
    Fallback per curve senza UserText parametrico.
    §14: Line(p1, p2).ToNurbsCurve()
    """
    try:
        p1 = rg.Point3d(float(cells[C_X1]), float(cells[C_Y1]), 0.0)
        p2 = rg.Point3d(float(cells[C_X2]), float(cells[C_Y2]), 0.0)
        return rg.Line(p1, p2).ToNurbsCurve(), None
    except Exception as ex:
        return None, "absolute: %s" % ex


def reconstruct(ut, cells, vd):
    """
    Dispatch principale.  Ordine di priorità:
      _Line       → build_line  (+ fallback assoluto se fallisce)
      _Arc        → build_arc
      _InterpCrv / Nurbs grado2 con CtrlProp → build_conic
      Nurbs con CtrlPoints                   → build_free
      geom=Line senza UserText               → build_from_absolute
    """
    cmd       = ut.get("Comando", "")
    tipo_orig = ut.get("Tipo_Originale", "")
    geom      = cells[C_GEOM].strip() if len(cells) > C_GEOM else ""

    # ── Linea retta ───────────────────────────────────────────────
    if cmd == "_Line":
        crv, err = build_line(ut, vd)
        if crv is not None:
            return crv, None
        # Fallback assoluto se i parametri non si valutano
        if geom == "Line":
            return build_from_absolute(cells)
        return None, err

    # ── Arco ──────────────────────────────────────────────────────
    if cmd == "_Arc" or tipo_orig == "Arc":
        return build_arc(ut, vd)

    # ── NURBS (conica o libera) ───────────────────────────────────
    if cmd == "_InterpCrv" or tipo_orig == "Nurbs":
        # Conica grado 2: ha CtrlProp_u/v/w
        if ut.get("CtrlProp_u") is not None or ut.get("CtrlPeso_w") is not None:
            return build_conic(ut, vd)
        # NURBS libera: ha CtrlPoints
        if ut.get("CtrlPoints"):
            return build_free(ut, vd)
        return None, "Nurbs: ne CtrlProp ne CtrlPoints"

    # ── Fallback per qualsiasi geometria Line senza UserText ──────
    if geom == "Line":
        return build_from_absolute(cells)

    return None, "tipo non gestito Cmd='%s' Geom='%s'" % (cmd, geom)


# ═══════════════════════════════════════════════════════════════════
#  Raccordi da Note di punto  (Nota=Raccordo Raggio N)
#  Logica identica a PKG_Esegue_Parametrico: i punti con Nota
#  descrivono angoli dove inserire un arco tangente di raggio R.
# ═══════════════════════════════════════════════════════════════════

def radius_from_note(note):
    """
    Estrae il raggio da una nota tipo 'Raccordo Raggio 5'.
    Cerca l'ultimo token numerico positivo dopo 'Raggio'.
    """
    low = note.lower()
    if "raccord" not in low or "raggio" not in low:
        return None
    for tok in reversed(note.replace(",", ".").split()):
        try:
            v = float(tok)
            if v > 0:
                return v
        except ValueError:
            pass
    return None


def collect_fillet_notes(rows):
    """
    Raccoglie i raccordi dai punti con Nota='Raccordo Raggio N'.
    Ritorna lista di (X_param_str, Y_param_str, raggio_float).
    La lista è vuota se nessun punto ha tale nota.
    """
    notes = []
    for row in rows:
        if len(row) < 6 or row[C_GEOM].strip() != "Point":
            continue
        ut   = parse_ut(row[-1])
        nota = ut.get("Nota", "")
        if not nota:
            continue
        R = radius_from_note(nota)
        if R is None:
            continue
        xp = ut.get("X_param")
        yp = ut.get("Y_param")
        if xp and yp:
            notes.append((xp.strip(), yp.strip(), R))
    return notes


def _other_end(crv, corner, tol=0.5):
    """Ritorna l'estremo di crv lontano da corner."""
    s = crv.PointAtStart
    e = crv.PointAtEnd
    return e if s.DistanceTo(corner) <= e.DistanceTo(corner) else s


def fillet_line_line(c0, c1, corner, R, atol):
    """
    Raccordo esatto retta–retta: arco di raggio R tangente alle due rette,
    con i segmenti accorciati ai punti di tangenza.
    Ritorna [NurbsCurve_line0, NurbsCurve_arc, NurbsCurve_line1] o None.
    Usa §14 Line.ToNurbsCurve() e §13 Arc.ToNurbsCurve().
    """
    oa = _other_end(c0, corner)
    ob = _other_end(c1, corner)
    dax = oa.X - corner.X;  day = oa.Y - corner.Y
    dbx = ob.X - corner.X;  dby = ob.Y - corner.Y
    la = math.sqrt(dax*dax + day*day)
    lb = math.sqrt(dbx*dbx + dby*dby)
    if la < 1e-9 or lb < 1e-9:
        return None
    dax /= la;  day /= la
    dbx /= lb;  dby /= lb
    cphi = max(-1.0, min(1.0, dax*dbx + day*dby))
    phi  = math.acos(cphi)
    if phi < 1e-4 or abs(phi - math.pi) < 1e-4:
        return None                           # linee parallele o coincidenti
    half = phi / 2.0
    dt   = R / math.tan(half)
    if dt >= la - 1e-6 or dt >= lb - 1e-6:
        return None                           # raggio troppo grande
    # Punti di tangenza
    ta = rg.Point3d(corner.X + dax*dt, corner.Y + day*dt, 0.0)
    tb = rg.Point3d(corner.X + dbx*dt, corner.Y + dby*dt, 0.0)
    # Centro dell'arco
    bx  = dax + dbx;  by = day + dby
    bl  = math.sqrt(bx*bx + by*by)
    if bl < 1e-9:
        return None
    bx /= bl;  by /= bl
    cdist  = R / math.sin(half)
    center = rg.Point3d(corner.X + bx*cdist, corner.Y + by*cdist, 0.0)
    vx = corner.X - center.X;  vy = corner.Y - center.Y
    vl = math.sqrt(vx*vx + vy*vy)
    if vl < 1e-9:
        return None
    # Punto intermedio dell'arco (punto del centro verso l'angolo)
    amid = rg.Point3d(center.X + vx/vl*R, center.Y + vy/vl*R, 0.0)
    arc  = rg.Arc(ta, amid, tb)
    if not arc.IsValid:
        return None
    # §14 + §13
    return [
        rg.Line(oa, ta).ToNurbsCurve(),
        arc.ToNurbsCurve(),
        rg.Line(ob, tb).ToNurbsCurve(),
    ]


def apply_fillets(real_list, fillet_notes, vd, atol, angtol):
    """
    Inserisce un raccordo per ogni nota. Per ogni angolo (X_param, Y_param, R):
      1. Trova le due curve che terminano in quell'angolo (entro tolc)
      2. Se entrambe sono linee rette: fillet_line_line esatto
      3. Fallback: Rhino.Geometry.Curve.CreateFilletCurves
      4. Sostituisce le due curve con [linea_troncata, arco, linea_troncata]
    Ritorna (lista_aggiornata, n_applicati, n_falliti).
    """
    items  = list(real_list)   # copia mutabile di [(crv, layer_idx)]
    tolc   = 0.25              # mm: raggio di ricerca vertice
    n_ok   = 0
    n_fail = 0

    for xp, yp, R in fillet_notes:
        cx = safe_eval(xp, vd)
        cy = safe_eval(yp, vd)
        if cx is None or cy is None:
            n_fail += 1
            continue
        corner = rg.Point3d(cx, cy, 0.0)

        # Trova indici delle curve che toccano questo angolo
        hits = []
        for idx, (crv, li) in enumerate(items):
            if crv is None:
                continue
            try:
                ds = crv.PointAtStart.DistanceTo(corner)
                de = crv.PointAtEnd.DistanceTo(corner)
                if min(ds, de) <= tolc:
                    hits.append(idx)
            except Exception:
                pass

        if len(hits) != 2:
            n_fail += 1
            continue

        i0, i1 = hits[0], hits[1]
        c0, lay = items[i0]
        c1, _   = items[i1]
        pieces  = None

        # Tentativo 1: raccordo analitico linea–linea
        try:
            if c0.IsLinear(atol) and c1.IsLinear(atol):
                pieces = fillet_line_line(c0, c1, corner, R, atol)
        except Exception:
            pieces = None

        # Tentativo 2: CreateFilletCurves di RhinoCommon
        if not pieces:
            try:
                res = Rhino.Geometry.Curve.CreateFilletCurves(
                    c0, corner, c1, corner, R,
                    False, True, False, atol, angtol)
                if res:
                    pieces = [rc for rc in res if rc is not None and rc.IsValid]
            except Exception:
                pieces = None

        if not pieces:
            n_fail += 1
            continue

        # Sostituisci le due curve originali con i pezzi del raccordo
        for ix in sorted([i0, i1], reverse=True):
            del items[ix]
        for rc in pieces:
            items.append((rc, lay))
        n_ok += 1

    return items, n_ok, n_fail


# ═══════════════════════════════════════════════════════════════════
#  Asse di specchiatura
# ═══════════════════════════════════════════════════════════════════

def make_mirror_xform(p1, p2):
    """Specchiatura rispetto alla retta p1→p2 (piano XY)."""
    d = p2 - p1
    if d.Length < 1e-9:
        return None
    d.Unitize()
    # Normale al piano di specchiatura (perpendicolare alla retta in XY)
    n = rg.Vector3d(-d.Y, d.X, 0.0)
    plane = rg.Plane(p1, n)
    return rg.Transform.Mirror(plane)


# ═══════════════════════════════════════════════════════════════════
#  Layer e Tag
# ═══════════════════════════════════════════════════════════════════

def get_or_create_layer(name, color):
    idx = sc.doc.Layers.FindByFullPath(name, -1)
    if idx >= 0:
        return idx
    lyr = Rhino.DocObjects.Layer()
    lyr.Name  = name
    lyr.Color = color
    return sc.doc.Layers.Add(lyr)


def mk_attr(layer_idx):
    attr = Rhino.DocObjects.ObjectAttributes()
    attr.LayerIndex  = layer_idx
    attr.ColorSource = Rhino.DocObjects.ObjectColorSource.ColorFromLayer
    attr.SetUserString(TAG_KEY, TAG_VAL)
    return attr


def clear_previous():
    """Elimina tutti gli oggetti taggati con TAG_KEY=TAG_VAL."""
    st = Rhino.DocObjects.ObjectEnumeratorSettings()
    st.IncludeLights = False
    to_del = []
    for obj in sc.doc.Objects.GetObjectList(st):
        try:
            if obj.Attributes.GetUserString(TAG_KEY) == TAG_VAL:
                to_del.append(obj.Id)
        except Exception:
            pass
    for gid in to_del:
        sc.doc.Objects.Delete(gid, True)
    return len(to_del)


# ═══════════════════════════════════════════════════════════════════
#  Lettura TXT
# ═══════════════════════════════════════════════════════════════════

def read_txt(path):
    """
    Legge il TXT (formato V5, 22 colonne).
    Ritorna (rows_all, axis_data).
    rows_all: lista di celle per ogni riga non-commento.
    axis_data: (cells, ut_dict) se trovato asse, else None.
    """
    rows = []
    f = codecs.open(path, "r", "utf-8")
    try:
        for raw in f:
            line = raw.rstrip("\r\n")
            if not line or line.startswith("#"):
                continue
            rows.append(line.split("\t"))
    finally:
        f.close()
    return rows


def find_axis(rows):
    """
    Cerca la linea con UserText chiave 'A' (es. 'A=').
    Ritorna (cells, ut_dict) per consentire la valutazione parametrica,
    o None se non trovata.
    """
    for row in rows:
        if len(row) < 6:
            continue
        ut = parse_ut(row[-1])
        if "A" in ut:
            return (row, ut)
    return None


def eval_axis(axis_data, vd):
    """
    Valuta gli estremi dell'asse con i parametri correnti (vd).
    Tenta prima P1_param/P2_param (parametrico), poi fallback assoluto.
    Ritorna (Point3d, Point3d) o None.
    """
    if axis_data is None:
        return None
    row, ut = axis_data
    p1 = eval_pt(ut.get("P1_param"), vd)
    p2 = eval_pt(ut.get("P2_param"), vd)
    if p1 is not None and p2 is not None:
        return (p1, p2)
    # Fallback: coordinate assolute dal TXT
    try:
        p1 = rg.Point3d(float(row[C_X1]), float(row[C_Y1]), 0.0)
        p2 = rg.Point3d(float(row[C_X2]), float(row[C_Y2]), 0.0)
        return (p1, p2)
    except Exception:
        return None


# ═══════════════════════════════════════════════════════════════════
#  Generazione in Rhino
# ═══════════════════════════════════════════════════════════════════

def generate(rows, vd, opts, axis_data, fillet_notes):
    """Ricostruisce e inserisce le curve nel documento Rhino."""
    if opts["clear"]:
        n_del = clear_previous()
        if n_del:
            print("Eliminati %d oggetti precedenti." % n_del)

    # Layer cache
    layer_cache = {}
    def layer_idx(name):
        if name not in layer_cache:
            col = LAYER_COLORS.get(name, LAYER_COLORS["Predefinito"])
            layer_cache[name] = get_or_create_layer(name, col)
        return layer_cache[name]

    # Transform di specchiatura (valutato con i parametri correnti)
    mirror_xf = None
    axis_pts = eval_axis(axis_data, vd)
    if opts["mirror"] and axis_pts is not None:
        mirror_xf = make_mirror_xform(axis_pts[0], axis_pts[1])

    # ── PASSO 1: costruzione curve ─────────────────────────────────
    real_list = []   # [(crv, layer_idx), ...]
    axis_crvs = []   # asse di costruzione (separato)
    n_abs     = 0
    reasons   = {}

    for row in rows:
        if len(row) < 6:
            continue
        tipo       = row[C_TIPO]
        if tipo == "P":
            continue
        layer_name = row[C_LAYER] if len(row) > C_LAYER else "Taglio"
        ut         = parse_ut(row[-1])

        # Asse di costruzione: separato
        if "A" in ut:
            if opts["axis"] and axis_pts is not None:
                # Linea Cyan parametrica: usa i punti valutati con vd
                try:
                    crv = rg.Line(axis_pts[0], axis_pts[1]).ToNurbsCurve()
                    axis_crvs.append((crv, layer_idx("PKG_Costruzione_Cyan")))
                except Exception:
                    pass
            continue

        crv, err = reconstruct(ut, row, vd)
        if crv is None:
            reasons[err] = reasons.get(err, 0) + 1
            continue

        if not ut.get("Comando") and not ut.get("P1_param"):
            n_abs += 1

        real_list.append((crv, layer_idx(layer_name)))

    # ── PASSO 2: raccordi ──────────────────────────────────────────
    n_fillet_ok   = 0
    n_fillet_fail = 0
    if opts.get("fillets") and fillet_notes:
        atol   = sc.doc.ModelAbsoluteTolerance
        angtol = sc.doc.ModelAngleToleranceRadians
        real_list, n_fillet_ok, n_fillet_fail = apply_fillets(
            real_list, fillet_notes, vd, atol, angtol)

    # ── PASSO 3: inserimento in Rhino ──────────────────────────────
    created = []
    n_ok    = 0

    # Asse di costruzione
    for crv, li in axis_crvs:
        gid = sc.doc.Objects.AddCurve(crv, mk_attr(li))
        if gid != System.Guid.Empty:
            created.append(gid)

    # Curve principali (+ specchiatura)
    for crv, li in real_list:
        attr = mk_attr(li)
        gid  = sc.doc.Objects.AddCurve(crv, attr)
        if gid != System.Guid.Empty:
            created.append(gid)
            n_ok += 1
            if mirror_xf is not None:
                crv2 = crv.DuplicateCurve()
                crv2.Transform(mirror_xf)
                gid2 = sc.doc.Objects.AddCurve(crv2, mk_attr(li))
                if gid2 != System.Guid.Empty:
                    created.append(gid2)
        else:
            reasons["AddCurve fallita"] = reasons.get("AddCurve fallita", 0) + 1

    # Raggruppa tutto
    if created:
        grp = sc.doc.Groups.Add()
        for gid in created:
            sc.doc.Groups.AddToGroup(grp, gid)

    sc.doc.Views.Redraw()

    # ── Report ─────────────────────────────────────────────────────
    print("\n" + "─" * 60)
    print("Curve generate:   %d" % n_ok)
    if mirror_xf is not None:
        print("  + specchiate:  %d  (tot. con mirror: %d)" % (n_ok, n_ok * 2))
    if n_abs:
        print("  di cui %d da coordinate assolute (non parametriche)" % n_abs)
    if n_fillet_ok or n_fillet_fail:
        if n_fillet_fail:
            print("Raccordi: %d applicati  (%d falliti: raggio incompatibile o angolo ambiguo)" % (
                  n_fillet_ok, n_fillet_fail))
        else:
            print("Raccordi: %d applicati" % n_fillet_ok)
    print("Layer: %s" % ", ".join(sorted(layer_cache)))
    if reasons:
        n_fail = sum(reasons.values())
        print("Non generate: %d" % n_fail)
        for k, v in sorted(reasons.items(), key=lambda x: -x[1]):
            print("  [%d] %s" % (v, k))
    print("Fatto.")


# ═══════════════════════════════════════════════════════════════════
#  Main
# ═══════════════════════════════════════════════════════════════════

def main():
    print("=" * 60)
    print("PKG_Genera_Da_TXT  v%s" % _VERSION)
    print("=" * 60)

    # 1 ── Scelta file (PRIMA del dialog parametri)
    fd = Rhino.UI.OpenFileDialog()
    fd.Filter = "PKG Text (*.txt)|*.txt"
    fd.Title  = "Seleziona il file TXT parametrico"
    if not fd.ShowOpenDialog():
        print("Annullato.")
        return
    path = fd.FileName
    print("\nFile: %s" % os.path.basename(path))

    # 2 ── Lettura e parsing
    try:
        rows = read_txt(path)
    except Exception as ex:
        print("[ERRORE] Lettura: %s" % ex)
        return
    print("Righe lette: %d" % len(rows))

    # 3 ── Derivazione automatica dei parametri
    derived = derive_vars(rows)
    if derived:
        print("Parametri derivati: " + "  ".join(
            "%s=%g" % (k, derived[k]) for k in VAR_NAMES if k in derived))
    else:
        print("Parametri non derivabili, uso default.")

    # Merge con default per eventuali variabili non trovate
    defaults = dict(DEFAULTS)
    defaults.update(derived)

    # 4 ── Asse di specchiatura
    axis_data = find_axis(rows)
    if axis_data:
        print("Asse di specchiatura trovato.")

    # 5 ── Raccordi da Note di punto
    fillet_notes = collect_fillet_notes(rows)
    if fillet_notes:
        print("Raccordi da Note: %d angoli trovati." % len(fillet_notes))

    # 6 ── Preview curves
    preview_curves = build_preview_curves(rows)

    # 7 ── Dialog con preview
    dlg = _DlgParams(defaults, preview_curves,
                     has_axis=(axis_data is not None),
                     has_fillets=(len(fillet_notes) > 0))
    if dlg.ShowDialog() != WF.DialogResult.OK:
        print("Annullato.")
        return

    vd = dlg.get_values()
    if vd is None:
        return
    opts = dlg.get_opts()

    print("\nParametri scelti: " + "  ".join(
          "%s=%g" % (k, vd[k]) for k in VAR_NAMES))

    # 8 ── Generazione
    generate(rows, vd, opts, axis_data, fillet_notes)


if __name__ == "__main__":
    main()
