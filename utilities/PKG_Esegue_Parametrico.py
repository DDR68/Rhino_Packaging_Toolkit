#! python 2
# -*- coding: utf-8 -*-
# PKG_Ricostruisci_Parametrico
# Ricostruisce un tracciato cartotecnico parametrico da un file TXT esportato
# (Rhino_Packaging_Toolkit). Chiede il file, poi le variabili L P A S C E T,
# valuta le formule parametriche e ridisegna linee, archi, raccordi conici e
# curve libere. Se trova la linea cyan di costruzione (UserText "A=") la usa
# come asse di specchiatura; l'asse non vive nel tracciato finale.
#
# IronPython 2.7 / RhinoCommon - Rhino 7 e 8.

from __future__ import division

import math
import codecs

import Rhino
import Rhino.UI
import scriptcontext as sc
import System
from Rhino.Geometry import Point3d, Point4d, Vector3d, Line, Arc, Circle
from Rhino.Geometry import Plane, NurbsCurve, Interval, Transform

# ---------------------------------------------------------------------------
# Costanti
# ---------------------------------------------------------------------------

VARORDER = ["L", "P", "A", "S", "C", "E", "T"]
DEFAULTS = {"L": 300.0, "P": 203.0, "A": 85.0, "S": 2.0,
            "C": 0.0, "E": 0.0, "T": 0.0}
OPTKEYS = {"mirror": "PKG_OPT_MIRROR", "axis": "PKG_OPT_AXIS",
           "points": "PKG_OPT_POINTS", "clear": "PKG_OPT_CLEAR",
           "fillets": "PKG_OPT_FILLETS"}
TAG_KEY = "PKG_GEN"
TAG_VAL = "1"

# colonne (0-based) del TXT
C_ID = 0
C_TIPO = 1
C_GEOM = 2
C_LAYER = 4
C_X1 = 5
C_Y1 = 6
C_X2 = 7
C_Y2 = 8
C_R = 9
C_CP = 17
C_USER = 21

HAS_ETO = True
try:
    import Eto.Forms as _ETOF
    import Eto.Drawing as _ETOD
except:
    HAS_ETO = False

# Formule che non e' stato possibile interpretare (diagnostica visibile)
EVAL_ERRORS = []

# ---------------------------------------------------------------------------
# Valutatore di espressioni parametriche (parser proprio, niente eval)
# Gestisce: numeri, variabili L P A S C E T, operatori + - * / , parentesi,
# meno e piu' unari. Deterministico e indipendente da IronPython.
# ---------------------------------------------------------------------------

def _tokenize(s):
    toks = []
    i = 0
    n = len(s)
    while i < n:
        ch = s[i]
        if ch == " " or ch == "\t":
            i += 1
            continue
        if ch in "()+-*/":
            toks.append(("op", ch))
            i += 1
            continue
        if ch.isdigit() or ch == ".":
            j = i
            while j < n and (s[j].isdigit() or s[j] == "."):
                j += 1
            toks.append(("num", float(s[i:j])))
            i = j
            continue
        if ch.isalpha() or ch == "_":
            j = i
            while j < n and (s[j].isalnum() or s[j] == "_"):
                j += 1
            toks.append(("name", s[i:j]))
            i = j
            continue
        raise ValueError("carattere non valido '%s'" % ch)
    return toks


class _Parser(object):
    def __init__(self, toks, env):
        self.t = toks
        self.i = 0
        self.env = env

    def _peek(self):
        if self.i < len(self.t):
            return self.t[self.i]
        return (None, None)

    def _next(self):
        tok = self.t[self.i]
        self.i += 1
        return tok

    def parse_expr(self):
        v = self._term()
        while True:
            k, o = self._peek()
            if k == "op" and (o == "+" or o == "-"):
                self._next()
                r = self._term()
                v = v + r if o == "+" else v - r
            else:
                break
        return v

    def _term(self):
        v = self._factor()
        while True:
            k, o = self._peek()
            if k == "op" and (o == "*" or o == "/"):
                self._next()
                r = self._factor()
                v = v * r if o == "*" else v / r
            else:
                break
        return v

    def _factor(self):
        k, o = self._peek()
        if k == "op" and (o == "+" or o == "-"):
            self._next()
            v = self._factor()
            return v if o == "+" else -v
        return self._primary()

    def _primary(self):
        k, o = self._peek()
        if k == "num":
            self._next()
            return o
        if k == "name":
            self._next()
            if o in self.env:
                return float(self.env[o])
            up = o.upper()
            if up in self.env:
                return float(self.env[up])
            raise ValueError("variabile sconosciuta '%s'" % o)
        if k == "op" and o == "(":
            self._next()
            v = self.parse_expr()
            k2, o2 = self._peek()
            if not (k2 == "op" and o2 == ")"):
                raise ValueError("parentesi ')' mancante")
            self._next()
            return v
        raise ValueError("token inatteso")


def eval_expr(expr, env):
    toks = _tokenize(expr)
    if not toks:
        return None
    p = _Parser(toks, env)
    v = p.parse_expr()
    if p.i != len(toks):
        raise ValueError("token residui in '%s'" % expr)
    return float(v)


# ---------------------------------------------------------------------------
# Helper numerici e di parsing
# ---------------------------------------------------------------------------

def to_float(s):
    if s is None:
        return None
    s = str(s).strip()
    if s == "" or s == "-":
        return None
    try:
        return float(s)
    except:
        return None


def to_float_input(s):
    """Come to_float ma accetta anche la virgola decimale (formato italiano)."""
    if s is None:
        return None
    s = str(s).strip().replace(",", ".")
    if s == "" or s == "-":
        return None
    try:
        return float(s)
    except:
        return None


def col_f(row, i):
    if i >= len(row):
        return None
    return to_float(row[i])


def col_pt(row, ix, iy):
    x = col_f(row, ix)
    y = col_f(row, iy)
    if x is None or y is None:
        return None
    return Point3d(x, y, 0.0)


def evf(expr, V):
    """Valuta una formula scalare con le variabili (tutte float).
    In caso di formula non interpretabile la registra in EVAL_ERRORS."""
    if expr is None:
        return None
    expr = expr.strip()
    if expr == "" or expr == "-":
        return None
    env = {}
    for k in V:
        env[k] = float(V[k])
    try:
        return eval_expr(expr, env)
    except Exception as e:
        EVAL_ERRORS.append((expr, str(e)))
        return None


def strip_outer(s):
    """Toglie una sola coppia di parentesi se avvolge tutta la stringa."""
    s = s.strip()
    if len(s) >= 2 and s[0] == "(" and s[-1] == ")":
        depth = 0
        for i in range(len(s)):
            ch = s[i]
            if ch == "(":
                depth += 1
            elif ch == ")":
                depth -= 1
                if depth == 0 and i < len(s) - 1:
                    return s
        return s[1:-1]
    return s


def split_top_comma(s):
    """Divide su virgola a profondita di parentesi 0."""
    parts = []
    depth = 0
    cur = []
    for ch in s:
        if ch == "(":
            depth += 1
            cur.append(ch)
        elif ch == ")":
            depth -= 1
            cur.append(ch)
        elif ch == "," and depth == 0:
            parts.append("".join(cur))
            cur = []
        else:
            cur.append(ch)
    parts.append("".join(cur))
    return parts


def parse_pair(s, V):
    """(expr_x, expr_y) -> Point3d valutato con le variabili."""
    if not s:
        return None
    inner = strip_outer(s)
    parts = split_top_comma(inner)
    if len(parts) != 2:
        return None
    x = evf(parts[0], V)
    y = evf(parts[1], V)
    if x is None or y is None:
        return None
    return Point3d(x, y, 0.0)


def parse_userdict(s):
    """Blocco UserText 'k=v;k=v;...' -> dizionario. 'A= ' -> chiave 'A'."""
    d = {}
    for tok in s.split(";"):
        tok = tok.strip()
        if tok == "":
            continue
        if "=" in tok:
            k, _, v = tok.partition("=")
            d[k.strip()] = v.strip()
        else:
            d[tok] = ""
    return d


def parse_ctrlpoints(s):
    """CtrlPoints UserText: 'x,y,w|x,y,w|...' (separatore lista = '|')."""
    out = []
    for tok in s.split("|"):
        tok = tok.strip()
        if tok == "":
            continue
        p = tok.split(",")
        if len(p) >= 3:
            out.append((to_float(p[0]), to_float(p[1]), to_float(p[2])))
        elif len(p) == 2:
            out.append((to_float(p[0]), to_float(p[1]), 1.0))
    return out


def parse_cp_col(s):
    """Colonna CP del TXT: 'x,y,w;x,y,w;...' (separatore lista = ';')."""
    out = []
    for tok in s.split(";"):
        tok = tok.strip()
        if tok == "":
            continue
        p = tok.split(",")
        if len(p) >= 3:
            out.append((to_float(p[0]), to_float(p[1]), to_float(p[2])))
        elif len(p) == 2:
            out.append((to_float(p[0]), to_float(p[1]), 1.0))
    return out


def parse_knots(s):
    out = []
    for x in s.split("|"):
        v = to_float(x)
        if v is not None:
            out.append(v)
    return out


# ---------------------------------------------------------------------------
# Trasformazioni
# ---------------------------------------------------------------------------

def make_mirror_xform(p1, p2):
    """Specchiatura rispetto alla retta infinita passante per p1, p2 (piano XY)."""
    d = p2 - p1
    if d.Length < 1e-9:
        return None
    d.Unitize()
    n = Vector3d.CrossProduct(d, Vector3d.ZAxis)
    if n.Length < 1e-9:
        return None
    n.Unitize()
    return Transform.Mirror(p1, n)


def similarity_xform(o1, o2, n1, n2):
    """Similitudine (traslazione+rotazione+scala uniforme) che mappa
    il segmento (o1,o2) sul segmento (n1,n2). Con variabili base e' identita'."""
    vo = o2 - o1
    vn = n2 - n1
    lo = vo.Length
    ln = vn.Length
    if lo < 1e-9:
        return Transform.Translation(n1 - o1)
    t1 = Transform.Translation(Point3d.Origin - o1)
    ang = Vector3d.VectorAngle(vo, vn, Plane.WorldXY)
    rot = Transform.Rotation(ang, Vector3d.ZAxis, Point3d.Origin)
    sc_f = ln / lo
    scl = Transform.Scale(Point3d.Origin, sc_f)
    t2 = Transform.Translation(n1 - Point3d.Origin)
    return t2 * scl * rot * t1


# ---------------------------------------------------------------------------
# Costruttori di geometria. Ognuno ritorna (curva_o_None, e_parametrica)
# ---------------------------------------------------------------------------

def make_nurbs(cps, deg, knots):
    """NURBS razionale da control point (x,y,w) e nodi opzionali."""
    n = len(cps)
    if n < 2:
        return None
    if n < deg + 1:
        deg = n - 1
    order = deg + 1
    nc = NurbsCurve(3, True, order, n)
    kc = nc.Knots.Count
    if knots is not None and len(knots) == kc:
        for i in range(kc):
            nc.Knots[i] = knots[i]
    else:
        for i in range(kc):
            if i < deg:
                nc.Knots[i] = 0.0
            elif i >= kc - deg:
                nc.Knots[i] = 1.0
            else:
                nc.Knots[i] = float(i - deg + 1)
    for i in range(n):
        x = cps[i][0]
        y = cps[i][1]
        w = cps[i][2]
        if w is None:
            w = 1.0
        nc.Points.SetPoint(i, Point4d(x * w, y * w, 0.0, w))
    if not nc.IsValid:
        return None
    return nc


def build_point_map(rows):
    """Mappa dei punti parametrici: (x_base, y_base, X_param, Y_param)
    presi dalle righe Point del TXT. Serve a ricondurre a forma parametrica
    gli estremi dei segmenti privi di P1_param/P2_param."""
    pm = []
    for row in rows:
        if len(row) <= C_USER:
            continue
        if row[C_GEOM].strip() != "Point":
            continue
        ud = parse_userdict(row[C_USER])
        xe = ud.get("X_param")
        ye = ud.get("Y_param")
        bx = col_f(row, C_X1)
        by = col_f(row, C_Y1)
        if xe and ye and bx is not None and by is not None:
            pm.append((bx, by, xe, ye))
    return pm


def resolve_orphan(bx, by, V, pmap, tol=3.0):
    """Per un estremo senza formula, trova il punto parametrico piu' vicino
    (entro tol mm alle coordinate standard) e ne valuta la formula."""
    best = None
    bd = tol
    for px, py, xe, ye in pmap:
        dd = math.sqrt((px - bx) * (px - bx) + (py - by) * (py - by))
        if dd <= bd:
            bd = dd
            best = (xe, ye)
    if best is None:
        return None
    x = evf(best[0], V)
    y = evf(best[1], V)
    if x is None or y is None:
        return None
    return Point3d(x, y, 0.0)


def endpoint(ud, key, row, ix, iy, V, pmap):
    """Ritorna (Point3d, e_parametrico). Ordine: formula diretta ->
    punto parametrico vicino (orfano risolto) -> coordinate fisse."""
    p = parse_pair(ud.get(key), V)
    if p is not None:
        return p, True
    bx = col_f(row, ix)
    by = col_f(row, iy)
    if bx is None or by is None:
        return None, False
    rp = resolve_orphan(bx, by, V, pmap)
    if rp is not None:
        return rp, True
    return Point3d(bx, by, 0.0), False


def build_line(ud, row, V, pmap):
    p1, a1 = endpoint(ud, "P1_param", row, C_X1, C_Y1, V, pmap)
    p2, a2 = endpoint(ud, "P2_param", row, C_X2, C_Y2, V, pmap)
    if p1 is None or p2 is None:
        return None, False
    if p1.DistanceTo(p2) < 1e-9:
        return None, False
    return Line(p1, p2).ToNurbsCurve(), (a1 and a2)


def build_arc(ud, row, V, pmap):
    """Arco a raggio fisso con estremi parametrici. Lato del bulge dedotto
    dalla geometria originale (Punto_medio). Semicerchi (sweep ~180) scalati
    in raggio col raddoppio della corda per restare validi."""
    p1, a1 = endpoint(ud, "P1_param", row, C_X1, C_Y1, V, pmap)
    p2, a2 = endpoint(ud, "P2_param", row, C_X2, C_Y2, V, pmap)
    if p1 is None or p2 is None:
        return None, False
    param = (a1 and a2)

    o1 = col_pt(row, C_X1, C_Y1)
    o2 = col_pt(row, C_X2, C_Y2)
    omid = None
    pm = ud.get("Punto_medio")
    if pm:
        sp = pm.split(",")
        if len(sp) >= 2:
            mx = to_float(sp[0])
            my = to_float(sp[1])
            if mx is not None and my is not None:
                omid = Point3d(mx, my, 0.0)

    R = to_float(ud.get("Raggio"))
    if R is None:
        R = col_f(row, C_R)

    a0 = to_float(ud.get("AngStart_deg"))
    a1 = to_float(ud.get("AngEnd_deg"))
    sweep = None
    if a0 is not None and a1 is not None:
        sweep = abs(a1 - a0)

    side = 1.0
    if o1 is not None and o2 is not None and omid is not None:
        vx = o2.X - o1.X
        vy = o2.Y - o1.Y
        wx = omid.X - o1.X
        wy = omid.Y - o1.Y
        cr = vx * wy - vy * wx
        side = 1.0 if cr >= 0.0 else -1.0

    chord = p1.DistanceTo(p2)
    if chord < 1e-9:
        return None, False
    midx = (p1.X + p2.X) / 2.0
    midy = (p1.Y + p2.Y) / 2.0
    ux = (p2.X - p1.X) / chord
    uy = (p2.Y - p1.Y) / chord
    nx = -uy * side
    ny = ux * side
    half = chord / 2.0

    is_semi = (sweep is not None and abs(sweep - 180.0) < 1.0)
    if R is not None and abs(half - R) < 1e-3:
        is_semi = True

    if is_semi or R is None or R < half:
        sagitta = half
    else:
        sagitta = R - math.sqrt(max(0.0, R * R - half * half))

    pmid = Point3d(midx + nx * sagitta, midy + ny * sagitta, 0.0)
    arc = Arc(p1, pmid, p2)
    if not arc.IsValid:
        return None, False
    return arc.ToNurbsCurve(), param


def build_conic(ud, row, V, pmap):
    """Raccordo conico: NURBS grado 2, 3 CP. CP centrale come frazione (u,v)
    del rettangolo degli estremi, con peso w. Pienamente parametrico."""
    p1, a1 = endpoint(ud, "P1_param", row, C_X1, C_Y1, V, pmap)
    p2, a2 = endpoint(ud, "P2_param", row, C_X2, C_Y2, V, pmap)
    if p1 is None or p2 is None:
        return None, False
    param = (a1 and a2)

    u = to_float(ud.get("CtrlProp_u"))
    v = to_float(ud.get("CtrlProp_v"))
    w = to_float(ud.get("CtrlPeso_w"))
    if u is not None and v is not None and w is not None and w > 1e-9:
        cx = p1.X + u * (p2.X - p1.X)
        cy = p1.Y + v * (p2.Y - p1.Y)
        nc = NurbsCurve(3, True, 3, 3)
        for i in range(nc.Knots.Count):
            nc.Knots[i] = 0.0 if i < 2 else 1.0
        nc.Points.SetPoint(0, Point4d(p1.X, p1.Y, 0.0, 1.0))
        nc.Points.SetPoint(1, Point4d(cx * w, cy * w, 0.0, w))
        nc.Points.SetPoint(2, Point4d(p2.X, p2.Y, 0.0, 1.0))
        if nc.IsValid:
            return nc, param

    # caso degenere / fallback: CP assoluti dalla colonna + similitudine
    cps = parse_cp_col(row[C_CP]) if len(row) > C_CP else []
    if len(cps) >= 3:
        nc = make_nurbs(cps, 2, None)
        if nc is not None:
            o1 = Point3d(cps[0][0], cps[0][1], 0.0)
            o2 = Point3d(cps[-1][0], cps[-1][1], 0.0)
            nc.Transform(similarity_xform(o1, o2, p1, p2))
            return nc, param
    return None, False


def build_free(ud, row, V, pmap):
    """Curva libera (NURBS grado >2): ricostruita da CtrlPoints + Nodi assoluti,
    poi similitudine sugli estremi parametrici per restare connessa."""
    cpstr = ud.get("CtrlPoints")
    if cpstr:
        cps = parse_ctrlpoints(cpstr)
    elif len(row) > C_CP:
        cps = parse_cp_col(row[C_CP])
    else:
        cps = []
    if len(cps) < 2:
        return None, False

    deg_v = to_float(ud.get("Grado"))
    deg = int(deg_v) if deg_v is not None else (len(cps) - 1)
    knots = parse_knots(ud.get("Nodi")) if ud.get("Nodi") else None

    nc = make_nurbs(cps, deg, knots)
    if nc is None:
        return None, False

    n1, a1 = endpoint(ud, "P1_param", row, C_X1, C_Y1, V, pmap)
    n2, a2 = endpoint(ud, "P2_param", row, C_X2, C_Y2, V, pmap)
    param = (a1 and a2)
    if n1 is None:
        n1 = Point3d(cps[0][0], cps[0][1], 0.0)
    if n2 is None:
        n2 = Point3d(cps[-1][0], cps[-1][1], 0.0)
    o1 = Point3d(cps[0][0], cps[0][1], 0.0)
    o2 = Point3d(cps[-1][0], cps[-1][1], 0.0)
    nc.Transform(similarity_xform(o1, o2, n1, n2))
    return nc, param


# ---------------------------------------------------------------------------
# Layer e attributi
# ---------------------------------------------------------------------------

def get_or_create_layer(nome, r, g, b):
    idx = sc.doc.Layers.FindByFullPath(nome, -1)
    if idx >= 0:
        return idx
    layer = Rhino.DocObjects.Layer()
    layer.Name = nome
    layer.Color = System.Drawing.Color.FromArgb(r, g, b)
    return sc.doc.Layers.Add(layer)


def ensure_layers():
    return {
        "Taglio": get_or_create_layer("Taglio", 0, 0, 0),
        "Cordone": get_or_create_layer("Cordone", 255, 0, 0),
        "MezzoTaglio": get_or_create_layer("MezzoTaglio", 0, 170, 0),
        "Foratore": get_or_create_layer("Foratore", 255, 140, 0),
        "cyan": get_or_create_layer("PKG_Costruzione_Cyan", 0, 200, 200),
        "points": get_or_create_layer("PKG_Punti_Parametrici", 128, 128, 128),
    }


def layer_for_tipo(tipo, layers):
    if tipo == "C":
        return layers["Cordone"]
    if tipo == "M":
        return layers["MezzoTaglio"]
    if tipo == "F":
        return layers["Foratore"]
    return layers["Taglio"]


def mk_attr(layer_idx):
    attr = Rhino.DocObjects.ObjectAttributes()
    attr.LayerIndex = layer_idx
    attr.ColorSource = Rhino.DocObjects.ObjectColorSource.ColorFromLayer
    attr.SetUserString(TAG_KEY, TAG_VAL)
    return attr


def add_curve(crv, layer_idx, created):
    gid = sc.doc.Objects.AddCurve(crv, mk_attr(layer_idx))
    if gid != System.Guid.Empty:
        created.append(gid)


def add_point(pt, layer_idx, created):
    gid = sc.doc.Objects.AddPoint(pt, mk_attr(layer_idx))
    if gid != System.Guid.Empty:
        created.append(gid)


def clear_previous():
    st = Rhino.DocObjects.ObjectEnumeratorSettings()
    st.IncludeLights = False
    st.IncludeGrips = False
    ids = []
    for obj in sc.doc.Objects.GetObjectList(st):
        try:
            if obj.Attributes.GetUserString(TAG_KEY) == TAG_VAL:
                ids.append(obj.Id)
        except:
            pass
    for gid in ids:
        sc.doc.Objects.Delete(gid, True)
    return len(ids)


# ---------------------------------------------------------------------------
# Lettura file e persistenza variabili/opzioni
# ---------------------------------------------------------------------------

def load_rows(path):
    rows = []
    f = codecs.open(path, "r", "utf-8")
    try:
        for line in f:
            line = line.rstrip("\r\n")
            if line == "" or line.startswith("#"):
                continue
            rows.append(line.split("\t"))
    finally:
        f.close()
    return rows


def load_defaults():
    vals = {}
    for k in VARORDER:
        s = sc.doc.Strings.GetValue(k)
        v = to_float(s) if s is not None else None
        vals[k] = v if v is not None else DEFAULTS[k]
    return vals


def save_vals(vals):
    for k in VARORDER:
        sc.doc.Strings.SetString(k, ("%g" % vals[k]))


def load_opts(opts):
    o = dict(opts)
    for k in OPTKEYS:
        s = sc.doc.Strings.GetValue(OPTKEYS[k])
        if s is not None:
            o[k] = (s == "1")
    return o


def save_opts(opts):
    for k in OPTKEYS:
        sc.doc.Strings.SetString(OPTKEYS[k], "1" if opts[k] else "0")


def pick_file():
    dlg = Rhino.UI.OpenFileDialog()
    dlg.Title = "Scegli il file TXT parametrico"
    dlg.Filter = "File parametrico (*.txt)|*.txt|Tutti i file (*.*)|*.*"
    if dlg.ShowOpenDialog():
        return dlg.FileName
    return None


# ---------------------------------------------------------------------------
# Ricostruzione completa
# ---------------------------------------------------------------------------

def radius_from_note(note):
    """Estrae il raggio da una nota tipo 'Raccordo Raggio 5' / 'Raccorda Raggio 10'."""
    low = note.lower()
    if "raccord" not in low or "raggio" not in low:
        return None
    for tok in reversed(note.replace(",", ".").split()):
        v = to_float(tok)
        if v is not None and v > 0:
            return v
    return None


def _other_end(crv, corner):
    s = crv.PointAtStart
    e = crv.PointAtEnd
    if s.DistanceTo(corner) <= e.DistanceTo(corner):
        return e
    return s


def fillet_line_line(c0, c1, corner, R):
    """Raccordo esatto retta-retta: arco di raggio R tangente, con le due
    rette accorciate ai punti di tangenza. Ritorna [retta0, arco, retta1]."""
    oa = _other_end(c0, corner)
    ob = _other_end(c1, corner)
    dax = oa.X - corner.X
    day = oa.Y - corner.Y
    dbx = ob.X - corner.X
    dby = ob.Y - corner.Y
    la = math.sqrt(dax * dax + day * day)
    lb = math.sqrt(dbx * dbx + dby * dby)
    if la < 1e-9 or lb < 1e-9:
        return None
    dax /= la
    day /= la
    dbx /= lb
    dby /= lb
    cphi = dax * dbx + day * dby
    if cphi > 1.0:
        cphi = 1.0
    if cphi < -1.0:
        cphi = -1.0
    phi = math.acos(cphi)
    if phi < 1e-4 or abs(phi - math.pi) < 1e-4:
        return None
    half = phi / 2.0
    dt = R / math.tan(half)
    if dt >= la - 1e-6 or dt >= lb - 1e-6:
        return None
    ta = Point3d(corner.X + dax * dt, corner.Y + day * dt, 0.0)
    tb = Point3d(corner.X + dbx * dt, corner.Y + dby * dt, 0.0)
    bx = dax + dbx
    by = day + dby
    bl = math.sqrt(bx * bx + by * by)
    if bl < 1e-9:
        return None
    bx /= bl
    by /= bl
    cdist = R / math.sin(half)
    center = Point3d(corner.X + bx * cdist, corner.Y + by * cdist, 0.0)
    vx = corner.X - center.X
    vy = corner.Y - center.Y
    vl = math.sqrt(vx * vx + vy * vy)
    if vl < 1e-9:
        return None
    amid = Point3d(center.X + vx / vl * R, center.Y + vy / vl * R, 0.0)
    arc = Arc(ta, amid, tb)
    if not arc.IsValid:
        return None
    out = []
    out.append(Line(oa, ta).ToNurbsCurve())
    out.append(arc.ToNurbsCurve())
    out.append(Line(ob, tb).ToNurbsCurve())
    return out


def apply_fillets(real, fillet_notes, V):
    """Inserisce un raccordo dove le note lo indicano. Ritorna
    (nuova_lista_curve, n_applicati, n_falliti)."""
    items = []
    for c, li in real:
        items.append([c, li])
    applied = 0
    failed = 0
    tolc = 0.2
    atol = sc.doc.ModelAbsoluteTolerance
    angtol = sc.doc.ModelAngleToleranceRadians
    for xp, yp, R in fillet_notes:
        cx = evf(xp, V)
        cy = evf(yp, V)
        if cx is None or cy is None:
            continue
        corner = Point3d(cx, cy, 0.0)
        hits = []
        for idx in range(len(items)):
            crv = items[idx][0]
            if crv is None:
                continue
            d = min(crv.PointAtStart.DistanceTo(corner),
                    crv.PointAtEnd.DistanceTo(corner))
            if d <= tolc:
                hits.append(idx)
        if len(hits) != 2:
            failed += 1
            continue
        i0 = hits[0]
        i1 = hits[1]
        c0 = items[i0][0]
        c1 = items[i1][0]
        lay = items[i0][1]
        pieces = None
        if c0.IsLinear(atol) and c1.IsLinear(atol):
            pieces = fillet_line_line(c0, c1, corner, R)
        if pieces is None:
            try:
                res = Rhino.Geometry.Curve.CreateFilletCurves(
                    c0, corner, c1, corner, R, False, True, False, atol, angtol)
                if res and len(res) > 0:
                    pieces = []
                    for rc in res:
                        if rc is not None and rc.IsValid:
                            pieces.append(rc)
            except:
                pieces = None
        if not pieces:
            failed += 1
            continue
        for ix in sorted([i0, i1], reverse=True):
            del items[ix]
        for rc in pieces:
            items.append([rc, lay])
        applied += 1
    out = []
    for c, li in items:
        out.append((c, li))
    return out, applied, failed


def reconstruct(rows, V, opts, layers, pmap):
    del EVAL_ERRORS[:]
    created = []
    fallbacks = []
    real = []
    pts = []
    fillet_notes = []
    axis_seg = None
    axis_curve = None
    counts = {"line": 0, "arc": 0, "conic": 0, "free": 0,
              "T": 0, "C": 0, "M": 0, "F": 0, "axis": 0, "pt": 0,
              "param": 0, "fixed": 0, "snapped": 0,
              "fillet": 0, "fillet_fail": 0}

    for row in rows:
        if len(row) < 5:
            continue
        tipo = row[C_TIPO].strip()
        geom = row[C_GEOM].strip()
        udstr = row[C_USER] if len(row) > C_USER else ""
        ud = parse_userdict(udstr) if udstr else {}
        is_axis = ("A" in ud)

        if geom == "Point":
            if tipo == "P":
                note = ud.get("Nota")
                if note:
                    rr = radius_from_note(note)
                    if rr is not None and ud.get("X_param") and ud.get("Y_param"):
                        fillet_notes.append((ud["X_param"], ud["Y_param"], rr))
            if opts["points"] and tipo == "P":
                xp = ud.get("X_param")
                yp = ud.get("Y_param")
                if xp and yp:
                    x = evf(xp, V)
                    y = evf(yp, V)
                    if x is not None and y is not None:
                        pts.append(Point3d(x, y, 0.0))
                        counts["pt"] += 1
            continue

        crv = None
        is_param = False
        kind = None
        if geom == "Line":
            crv, is_param = build_line(ud, row, V, pmap)
            kind = "line"
        elif geom == "Arc":
            crv, is_param = build_arc(ud, row, V, pmap)
            kind = "arc"
        elif geom == "Nurbs":
            if "CtrlPoints" in ud:
                crv, is_param = build_free(ud, row, V, pmap)
                kind = "free"
            elif ("CtrlProp_u" in ud) or ("CtrlProp_v" in ud):
                crv, is_param = build_conic(ud, row, V, pmap)
                kind = "conic"
            else:
                crv, is_param = build_free(ud, row, V, pmap)
                kind = "free"
        else:
            continue

        if crv is None:
            continue

        if is_axis:
            p1 = parse_pair(ud.get("P1_param"), V)
            p2 = parse_pair(ud.get("P2_param"), V)
            if p1 is None:
                p1 = col_pt(row, C_X1, C_Y1)
            if p2 is None:
                p2 = col_pt(row, C_X2, C_Y2)
            if p1 is not None and p2 is not None:
                axis_seg = (p1, p2)
            axis_curve = crv
            counts["axis"] += 1
            continue

        if not is_param:
            fallbacks.append(row[C_ID])
            counts["fixed"] += 1
        else:
            counts["param"] += 1
            if ud.get("P1_param") is None or ud.get("P2_param") is None:
                counts["snapped"] += 1

        counts[kind] = counts.get(kind, 0) + 1
        li = layer_for_tipo(tipo, layers)
        real.append((crv, li))
        tkey = tipo if tipo in ("T", "C", "M", "F") else "T"
        counts[tkey] = counts.get(tkey, 0) + 1

    if opts.get("fillets") and fillet_notes:
        real, counts["fillet"], counts["fillet_fail"] = apply_fillets(
            real, fillet_notes, V)

    mirror_xf = None
    if opts["mirror"] and axis_seg is not None:
        mirror_xf = make_mirror_xform(axis_seg[0], axis_seg[1])

    for crv, li in real:
        add_curve(crv, li, created)

    nmir = 0
    if mirror_xf is not None:
        for crv, li in real:
            c2 = crv.DuplicateCurve()
            c2.Transform(mirror_xf)
            add_curve(c2, li, created)
            nmir += 1

    npts = 0
    if pts:
        pli = layers["points"]
        for p in pts:
            add_point(p, pli, created)
            npts += 1
        if mirror_xf is not None:
            for p in pts:
                p2 = Point3d(p)
                p2.Transform(mirror_xf)
                add_point(p2, pli, created)
                npts += 1

    if opts["axis"] and axis_curve is not None:
        add_curve(axis_curve, layers["cyan"], created)

    return created, counts, nmir, npts, fallbacks, (axis_seg is not None)


def report(vals, counts, nmir, npts, fb, has_axis, opts, ntot):
    print("=== PKG Parametrico ===")
    print("Variabili: L=%g P=%g A=%g S=%g C=%g E=%g T=%g"
          % (vals["L"], vals["P"], vals["A"], vals["S"],
             vals["C"], vals["E"], vals["T"]))
    print("Curve: Taglio=%d Cordone=%d MezzoTaglio=%d Foratore=%d"
          % (counts.get("T", 0), counts.get("C", 0),
             counts.get("M", 0), counts.get("F", 0)))
    print("Geometrie: linee=%d archi=%d conici=%d libere=%d"
          % (counts.get("line", 0), counts.get("arc", 0),
             counts.get("conic", 0), counts.get("free", 0)))
    print("Ricostruzione: parametriche=%d (di cui orfani risolti=%d)  a coordinate fisse=%d"
          % (counts.get("param", 0), counts.get("snapped", 0), counts.get("fixed", 0)))
    if has_axis:
        if opts["mirror"]:
            print("Asse cyan trovato: tracciato specchiato (%d curve)." % nmir)
        else:
            print("Asse cyan trovato (specchiatura disattivata).")
    else:
        print("Nessun asse cyan (UserText 'A=') trovato: nessuna specchiatura.")
    if counts.get("fillet", 0) or counts.get("fillet_fail", 0):
        msg = "Raccordi da note inseriti: %d" % counts.get("fillet", 0)
        if counts.get("fillet_fail", 0):
            msg += " (non riusciti: %d - raggio incompatibile o punto ambiguo)" % counts.get("fillet_fail", 0)
        print(msg)
    if npts:
        print("Punti parametrici: %d" % npts)
    if fb:
        print("NOTA: %d segmenti senza formula nel TXT, a coordinate fisse (ID: %s)."
              % (len(fb), ", ".join(fb)))
    if EVAL_ERRORS:
        print("ATTENZIONE: %d formule NON interpretate. Esempi:" % len(EVAL_ERRORS))
        seen = []
        for ex, msg in EVAL_ERRORS:
            if ex in seen:
                continue
            seen.append(ex)
            print("   '%s'  ->  %s" % (ex, msg))
            if len(seen) >= 5:
                break
    print("Totale oggetti generati: %d" % ntot)


# ---------------------------------------------------------------------------
# Interfaccia: dialogo variabili (Eto) con fallback a console
# ---------------------------------------------------------------------------

def get_inputs_eto(vals, opts):
    F = _ETOF
    D = _ETOD

    class Dlg(F.Dialog[bool]):
        def __init__(self):
            self.Title = "PKG Parametrico - Variabili"
            self.Padding = D.Padding(12)
            self.Resizable = False
            self.action = "close"
            self.result_vals = dict(vals)
            self.result_opts = dict(opts)
            self.tb = {}

            labels = {"L": "L   lunghezza", "P": "P   profondita",
                      "A": "A   altezza", "S": "S   spessore",
                      "C": "C   patella", "E": "E   smusso",
                      "T": "T   lembo"}

            lay = F.DynamicLayout()
            lay.Spacing = D.Size(8, 6)
            for k in VARORDER:
                t = F.TextBox()
                t.Text = ("%g" % vals[k])
                t.Width = 110
                self.tb[k] = t
                lbl = F.Label()
                lbl.Text = labels[k]
                lbl.VerticalAlignment = F.VerticalAlignment.Center
                lay.AddRow(lbl, t)

            self.cb_mirror = F.CheckBox()
            self.cb_mirror.Text = "Specchia sull'asse cyan"
            self.cb_mirror.Checked = opts["mirror"]
            self.cb_axis = F.CheckBox()
            self.cb_axis.Text = "Disegna asse di costruzione (cyan)"
            self.cb_axis.Checked = opts["axis"]
            self.cb_points = F.CheckBox()
            self.cb_points.Text = "Disegna punti parametrici"
            self.cb_points.Checked = opts["points"]
            self.cb_clear = F.CheckBox()
            self.cb_clear.Text = "Cancella ricostruzione precedente"
            self.cb_clear.Checked = opts["clear"]
            self.cb_fillet = F.CheckBox()
            self.cb_fillet.Text = "Inserisci raccordi (da note)"
            self.cb_fillet.Checked = opts.get("fillets", True)

            lay.AddRow(None)
            lay.AddRow(self.cb_mirror)
            lay.AddRow(self.cb_axis)
            lay.AddRow(self.cb_points)
            lay.AddRow(self.cb_fillet)
            lay.AddRow(self.cb_clear)
            lay.AddRow(None)

            b_apply = F.Button()
            b_apply.Text = "Applica"
            b_close = F.Button()
            b_close.Text = "Chiudi"
            b_apply.Click += self.on_apply
            b_close.Click += self.on_close

            brow = F.DynamicLayout()
            brow.Spacing = D.Size(8, 0)
            brow.AddRow(None, b_apply, b_close)
            lay.AddRow(brow)

            self.Content = lay
            self.DefaultButton = b_apply
            self.AbortButton = b_close

        def on_apply(self, s, e):
            self.action = "apply"
            for k in self.tb:
                fv = to_float_input(self.tb[k].Text)
                if fv is not None:
                    self.result_vals[k] = fv
            self.result_opts["mirror"] = bool(self.cb_mirror.Checked)
            self.result_opts["axis"] = bool(self.cb_axis.Checked)
            self.result_opts["points"] = bool(self.cb_points.Checked)
            self.result_opts["clear"] = bool(self.cb_clear.Checked)
            self.result_opts["fillets"] = bool(self.cb_fillet.Checked)
            self.Close(True)

        def on_close(self, s, e):
            self.action = "close"
            self.Close(False)

    dlg = Dlg()
    try:
        dlg.ShowModal(Rhino.UI.RhinoEtoApp.MainWindow)
    except:
        dlg.ShowModal()
    return dlg.action, dlg.result_vals, dlg.result_opts


def ask_yn(prompt, default):
    gs = Rhino.Input.Custom.GetString()
    gs.SetCommandPrompt(prompt + " (s/n)")
    gs.SetDefaultString("s" if default else "n")
    gs.AcceptNothing(True)
    gs.Get()
    if gs.CommandResult() != Rhino.Commands.Result.Success:
        return default
    v = gs.StringResult().strip().lower()
    if v == "":
        return default
    return v.startswith("s") or v.startswith("y")


def get_inputs_console(vals, opts):
    out = dict(vals)
    for k in VARORDER:
        gn = Rhino.Input.Custom.GetNumber()
        gn.SetCommandPrompt("Valore %s" % k)
        gn.SetDefaultNumber(float(vals[k]))
        gn.AcceptNothing(True)
        gn.Get()
        if gn.CommandResult() != Rhino.Commands.Result.Success:
            return "close", out, opts
        out[k] = float(gn.Number())
    o = dict(opts)
    o["mirror"] = ask_yn("Specchia sull'asse cyan?", opts["mirror"])
    o["axis"] = ask_yn("Disegna asse cyan?", opts["axis"])
    o["points"] = ask_yn("Disegna punti parametrici?", opts["points"])
    o["clear"] = ask_yn("Cancella ricostruzione precedente?", opts["clear"])
    o["fillets"] = ask_yn("Inserisci raccordi dalle note?", opts.get("fillets", True))
    return "apply", out, o


def get_inputs(vals, opts):
    if HAS_ETO:
        try:
            return get_inputs_eto(vals, opts)
        except:
            return get_inputs_console(vals, opts)
    return get_inputs_console(vals, opts)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    layers = ensure_layers()

    path = pick_file()
    if not path:
        print("Nessun file selezionato.")
        return

    rows = load_rows(path)
    if not rows:
        print("File vuoto o illeggibile.")
        return
    pmap = build_point_map(rows)

    vals = load_defaults()
    opts = {"mirror": True, "axis": True, "points": False,
            "clear": True, "fillets": True}
    opts = load_opts(opts)

    while True:
        action, vals, opts = get_inputs(vals, opts)
        if action != "apply":
            break

        if opts["clear"]:
            clear_previous()

        created, counts, nmir, npts, fb, has_axis = reconstruct(
            rows, vals, opts, layers, pmap)

        if created:
            grp = sc.doc.Groups.Add()
            for gid in created:
                sc.doc.Groups.AddToGroup(grp, gid)

        save_vals(vals)
        save_opts(opts)
        sc.doc.Views.Redraw()
        report(vals, counts, nmir, npts, fb, has_axis, opts, len(created))

        if not HAS_ETO:
            if not ask_yn("Ripetere con altri valori?", False):
                break

    print("Terminato.")


if __name__ == "__main__":
    main()
