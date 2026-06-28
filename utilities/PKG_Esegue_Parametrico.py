#! python 2
# -*- coding: utf-8 -*-
# PKG_Esegue_Parametrico
# Versione: 2.2
# Compatibilita: Rhino 7 / Rhino 8 - IronPython 2.7 - RhinoCommn
#
# Ricostruisce un tracciato cartotecnico parametrico da un file TXT esportato
# da PKG_Esporta_Geometrie_Parametrico (Rhino_Packaging_Toolkit). Chiede il
# file, poi le variabili L P A S C E T, valuta le formule parametriche e
# ridisegna linee, archi, raccordi conici e curve libere.
#
# SPECCHIATURA A PASSI ANNIDATI (matrioska) - allineata all'esportatore v5.5:
#   - Gli assi NON sono geometria da fustellare. Una riga e' un ASSE se la
#     colonna Ruolo vale AsseSpecchio_Continuo / AsseSpecchio_Tratteggiato
#     (o il generico AsseSpecchio), con FALLBACK alla vecchia UserString 'A='.
#   - DUE TIPI di asse, distinti dal Ruolo:
#       * CONTINUO    -> simmetria: riflette e MANTIENE l'origine (scatola intera)
#       * TRATTEGGIATO-> patella:   riflette e CANCELLA l'origine (vive la copia)
#   - La colonna Blocco e' la LISTA (CSV) dei passi cui ogni curva partecipa;
#     per le linee-asse e' il passo che definiscono. I passi si eseguono UNO
#     ALLA VOLTA in ordine crescente (dal piu' interno 1 al piu' esterno): al
#     passo k si riflettono TUTTE le curve la cui lista di passi contiene k.
#     Una curva interna compare in piu' passi, quindi viene rispecchiata di
#     nuovo dal passo esterno (matrioska forward-carry): la simmetria finale
#     ingloba i risultati delle patelle.
#   - Gli assi sono di SERVIZIO: di norma NON vengono disegnati (opzione di
#     debug). Nel risultato finale non resta alcuna linea d'asse.
#
# RETROCOMPATIBILITA: file senza Blocco/Ruolo (vecchia convenzione 'A=' a
#   singolo asse) -> un unico passo CONTINUO su tutte le curve, come prima.

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

# colonne (0-based) del TXT - formato esportatore v5.x (22 colonne)
C_ID = 0
C_TIPO = 1
C_GEOM = 2
C_NOME = 3
C_LAYER = 4
C_X1 = 5
C_Y1 = 6
C_X2 = 7
C_Y2 = 8
C_R = 9
C_CX = 10
C_CY = 11
C_ANGS = 12
C_ANGE = 13
C_LEN = 14
C_DEG = 15
C_PTS = 16
C_CP = 17
C_SAMPLED = 18
C_BLOCCO = 19
C_RUOLO = 20
C_USER = 21

# Ruoli d'asse emessi dall'esportatore nella colonna Ruolo.
AXIS_ROLE_CONTINUOUS = "AsseSpecchio_Continuo"     # simmetria: mantiene origine
AXIS_ROLE_DASHED     = "AsseSpecchio_Tratteggiato"  # patella: cancella origine
AXIS_ROLE_GENERIC    = "AsseSpecchio"              # retrocompat. (= simmetria)
AXIS_ROLES = (AXIS_ROLE_CONTINUOUS, AXIS_ROLE_DASHED, AXIS_ROLE_GENERIC)

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
# Specchiatura: lettura colonne Blocco/Ruolo  [v2.2]
# ---------------------------------------------------------------------------

def parse_step_list(s):
    """Colonna Blocco -> set di interi (i passi). '-' o vuoto = set vuoto.
    Per le curve membre e' la LISTA dei passi (es. '1,2'); per le linee-asse
    e' il passo che definiscono (di norma un solo numero)."""
    out = set()
    if not s:
        return out
    s = s.strip()
    if s == "" or s == "-":
        return out
    for tok in s.split(","):
        tok = tok.strip()
        try:
            out.add(int(tok))
        except:
            pass
    return out


def axis_role_of(row, ud):
    """Ritorna il ruolo d'asse della riga, o None se NON e' un asse.
    Priorita': colonna Ruolo (esportatore v5.x); fallback: vecchia
    UserString 'A=' (la linea cyan di costruzione nei file storici)."""
    ruolo = ""
    if len(row) > C_RUOLO:
        ruolo = row[C_RUOLO].strip()
    if ruolo in AXIS_ROLES:
        return ruolo
    # Retrocompatibilita': linea di costruzione marcata con UserText 'A='.
    if "A" in ud:
        return AXIS_ROLE_GENERIC
    return None


def axis_mirror_seg(ud, row, V):
    """Estremi (Point3d, Point3d) della RETTA d'asse: prima dalle formule
    P1_param/P2_param (parametrico), poi dalle coordinate fisse del TXT."""
    p1 = parse_pair(ud.get("P1_param"), V)
    p2 = parse_pair(ud.get("P2_param"), V)
    if p1 is None:
        p1 = col_pt(row, C_X1, C_Y1)
    if p2 is None:
        p2 = col_pt(row, C_X2, C_Y2)
    return p1, p2


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
    f = codecs.open(path, "r", "utf-8-sig")  # -sig: scarta l'eventuale BOM
    try:
        for line in f:
            line = line.rstrip("\r\n")
            if line[:1] == u"\ufeff":
                line = line[1:]
            if line == "" or line.startswith("#"):
                continue
            rows.append(line.split("\t"))
    finally:
        f.close()
    return rows


# ---------------------------------------------------------------------------
# Header parametrico: default, range e dimensioni interne utili DAL TXT  [v2.2]
# ---------------------------------------------------------------------------

def parse_header(path):
    """Legge i blocchi commentati '#' in testa al TXT generati dall'esportatore:

      # VARIABILI PARAMETRICHE ...
      #   Var  Default  Min  Max  Descrizione
      #   L    300.00   -    -    Lunghezza
      ...
      # DIMENSIONI INTERNE UTILI ...
      #   Dim  Formula   Descrizione
      #   L    L-S*10    Lunghezza interna utile
      ...

    Ritorna (vars_list, dims_list):
      vars_list = [(var, default, min_o_None, max_o_None, descrizione)]
      dims_list = [(dim, formula, descrizione)]
    Liste vuote se i blocchi non sono presenti (TXT vecchio): in tal caso si
    usano i DEFAULTS interni come fallback."""
    vars_list = []
    dims_list = []
    section = None
    f = codecs.open(path, "r", "utf-8-sig")  # -sig: scarta l'eventuale BOM
    try:
        for raw in f:
            line = raw.rstrip("\r\n")
            # difesa extra: rimuovi un BOM residuo a inizio riga
            if line[:1] == u"\ufeff":
                line = line[1:]
            if not line.startswith("#"):
                if line.strip() == "":
                    continue
                break  # prima riga dati: header finito
            body = line[1:].strip()
            if body == "":
                continue
            up = body.upper()
            if up.startswith("VARIABILI PARAMETRICHE"):
                section = "vars"
                continue
            if up.startswith("DIMENSIONI INTERNE UTILI"):
                section = "dims"
                continue
            low = body.lower()
            if section == "vars":
                if low.startswith("var") and "default" in low:
                    continue  # riga di intestazione colonne
                toks = body.split()
                if len(toks) >= 4 and len(toks[0]) <= 3 and toks[0].isalpha():
                    dflt = to_float(toks[1])
                    if dflt is not None:
                        vars_list.append((
                            toks[0], dflt,
                            to_float(toks[2]), to_float(toks[3]),
                            " ".join(toks[4:]) if len(toks) > 4 else ""))
                    continue
                section = None
                continue
            if section == "dims":
                if low.startswith("dim") and "formula" in low:
                    continue  # riga di intestazione colonne
                toks = body.split()
                if len(toks) >= 2 and len(toks[0]) <= 3 and toks[0].isalpha():
                    dims_list.append((
                        toks[0], toks[1],
                        " ".join(toks[2:]) if len(toks) > 2 else ""))
                    continue
                section = None
                continue
    finally:
        f.close()
    return vars_list, dims_list


def _fmt_num(v):
    if v is None:
        return "n/d"
    return "%g" % v


def eval_quiet(expr, V):
    """Valuta una formula SENZA registrare errori in EVAL_ERRORS (per l'header,
    distinto dalle formule geometriche). Ritorna None se non interpretabile."""
    if not expr:
        return None
    env = {}
    for k in V:
        env[k] = float(V[k])
    try:
        return eval_expr(expr.strip(), env)
    except Exception:
        return None


def eval_dims(dims_list, V):
    """Valuta le formule delle dimensioni interne utili con le variabili V.
    Ritorna [(dim, formula, valore_o_None, descrizione)]."""
    out = []
    for (dim, formula, desc) in dims_list:
        out.append((dim, formula, eval_quiet(formula, V), desc))
    return out


def seed_vals(vars_list):
    """Valori iniziali delle variabili: default DICHIARATI NEL TXT (blocco
    VARIABILI PARAMETRICHE) con priorita'; fallback ai DEFAULTS interni per le
    variabili non dichiarate. La dict include sempre tutte le VARORDER, cosi'
    le formule (punti e dimensioni interne) non incontrano variabili ignote."""
    vals = dict(DEFAULTS)
    for (var, dflt, vmin, vmax, desc) in vars_list:
        vals[var] = dflt
    return vals


def display_var_order(vars_list):
    """Variabili da mostrare nel dialogo: quelle dichiarate nel TXT (nell'ordine
    del file); in mancanza dell'header, le VARORDER storiche."""
    if vars_list:
        return [v[0] for v in vars_list]
    return list(VARORDER)


def var_meta_map(vars_list):
    """{ var : (default, min, max, descrizione) } dal blocco VARIABILI."""
    m = {}
    for (var, dflt, vmin, vmax, desc) in vars_list:
        m[var] = (dflt, vmin, vmax, desc)
    return m


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
# Raccordi da note
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


def apply_fillets(items_in, fillet_notes, V):
    """Inserisce un raccordo dove le note lo indicano. Opera su TRIPLE
    [curva, layer, set_passi] e fa EREDITARE ai pezzi del raccordo l'unione
    dei passi delle due curve consumate (cosi' il raccordo resta coerente con
    la matrioska). Ritorna (nuova_lista_triple, n_applicati, n_falliti)."""
    items = []
    for c, li, ss in items_in:
        items.append([c, li, set(ss)])
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
        ss = set(items[i0][2]) | set(items[i1][2])
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
            items.append([rc, lay, set(ss)])
        applied += 1
    out = []
    for c, li, ss in items:
        out.append([c, li, set(ss)])
    return out, applied, failed


# ---------------------------------------------------------------------------
# Motore di specchiatura a passi annidati (matrioska)  [v2.2]
# ---------------------------------------------------------------------------

def run_steps(members, member_pts, axes, opts):
    """Esegue i passi di specchiatura in ordine crescente (interno->esterno).

      members     : list di [curva, layer, set_passi]
      member_pts  : list di [Point3d, set_passi]
      axes        : { passo : {"role", "seg", "curve"} }

    Per ogni passo k riflette TUTTE le curve/punti la cui lista di passi
    contiene k, rispetto alla retta dell'asse del passo:
      - TRATTEGGIATO (patella): sostituisce l'originale con la copia (la copia
        eredita la lista di passi, quindi resta disponibile per i passi
        successivi);
      - CONTINUO (simmetria): mantiene l'originale e AGGIUNGE la copia.
    Lo snapshot dei membri di un passo viene preso PRIMA di aggiungere le
    copie, cosi' un passo non rispecchia due volte i propri risultati.

    Ritorna (work_curve, work_pt, n_mirror, per_step) dove work_* sono le
    geometrie FINALI (originali + copie sopravvissute)."""
    work_c = [[c, li, set(ss)] for (c, li, ss) in members]
    work_p = [[p, set(ss)] for (p, ss) in member_pts]
    nmir = 0
    per_step = {}

    if not opts["mirror"] or not axes:
        return work_c, work_p, nmir, per_step

    # Trasformazioni di specchio (una per passo).
    xforms = {}
    for k, ax in axes.items():
        seg = ax["seg"]
        xforms[k] = make_mirror_xform(seg[0], seg[1]) if seg is not None else None

    for k in sorted(axes.keys()):
        xf = xforms.get(k)
        if xf is None:
            per_step[k] = 0
            continue
        dashed = (axes[k]["role"] == AXIS_ROLE_DASHED)

        sel_c = [it for it in work_c if k in it[2]]
        sel_p = [it for it in work_p if k in it[1]]
        cnt = 0

        for it in sel_c:
            c2 = it[0].DuplicateCurve()
            c2.Transform(xf)
            if dashed:
                it[0] = c2  # patella: l'originale "diventa" la copia ribaltata
            else:
                work_c.append([c2, it[1], set(it[2])])
            cnt += 1
            nmir += 1

        for it in sel_p:
            p2 = Point3d(it[0])
            p2.Transform(xf)
            if dashed:
                it[0] = p2
            else:
                work_p.append([p2, set(it[1])])
            cnt += 1
            nmir += 1

        per_step[k] = cnt

    return work_c, work_p, nmir, per_step


# ---------------------------------------------------------------------------
# Ricostruzione completa
# ---------------------------------------------------------------------------

def reconstruct(rows, V, opts, layers, pmap):
    del EVAL_ERRORS[:]
    created = []
    fallbacks = []
    members = []      # [curva, layer, set_passi]
    member_pts = []   # [Point3d, set_passi]
    fillet_notes = []
    axes = {}         # passo -> {"role", "seg", "curve"}
    legacy_axes = []  # [(role, seg, curve)] per file senza numero di passo
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
        role = axis_role_of(row, ud)
        steps_of_row = parse_step_list(row[C_BLOCCO] if len(row) > C_BLOCCO else "")

        # ----- Punti -----
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
                        member_pts.append([Point3d(x, y, 0.0), set(steps_of_row)])
                        counts["pt"] += 1
            continue

        # ----- Curve: costruzione geometrica -----
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

        # ----- Linea d'asse (di servizio, non fustellata) -----
        if role is not None:
            p1, p2 = axis_mirror_seg(ud, row, V)
            seg = (p1, p2) if (p1 is not None and p2 is not None) else None
            eff_role = (AXIS_ROLE_CONTINUOUS
                        if role == AXIS_ROLE_GENERIC else role)
            if steps_of_row:
                for k in steps_of_row:
                    axes[k] = {"role": eff_role, "seg": seg, "curve": crv}
            else:
                legacy_axes.append((eff_role, seg, crv))
            counts["axis"] += 1
            continue

        # ----- Curva membro -----
        if not is_param:
            fallbacks.append(row[C_ID])
            counts["fixed"] += 1
        else:
            counts["param"] += 1
            if ud.get("P1_param") is None or ud.get("P2_param") is None:
                counts["snapped"] += 1

        counts[kind] = counts.get(kind, 0) + 1
        li = layer_for_tipo(tipo, layers)
        members.append([crv, li, set(steps_of_row)])
        tkey = tipo if tipo in ("T", "C", "M", "F") else "T"
        counts[tkey] = counts.get(tkey, 0) + 1

    # ----- Raccordi (costruzione origine, PRIMA delle specchiature) -----
    if opts.get("fillets") and fillet_notes:
        members, counts["fillet"], counts["fillet_fail"] = apply_fillets(
            members, fillet_notes, V)

    # ----- Retrocompatibilita': nessun passo numerato ma asse legacy -----
    # File alla vecchia convenzione 'A=' (o AsseSpecchio senza numero): un
    # unico passo CONTINUO che rispecchia TUTTE le curve, come faceva la
    # versione storica dell'esecutore.
    if not axes and legacy_axes:
        eff_role, seg, ac = legacy_axes[0]
        axes[1] = {"role": AXIS_ROLE_CONTINUOUS, "seg": seg, "curve": ac}
        for m in members:
            m[2] = set([1])
        for mp in member_pts:
            mp[1] = set([1])

    # ----- Esecuzione passi (matrioska, interno -> esterno) -----
    work_c, work_p, nmir, per_step = run_steps(members, member_pts, axes, opts)

    # ----- Scrittura geometrie finali -----
    for c, li, ss in work_c:
        add_curve(c, li, created)

    npts = 0
    if work_p:
        pli = layers["points"]
        for p, ss in work_p:
            add_point(p, pli, created)
            npts += 1

    # ----- Assi: di servizio, disegnati solo come debug (opts['axis']) -----
    if opts["axis"]:
        seen = set()
        for k in sorted(axes.keys()):
            ac = axes[k]["curve"]
            if ac is None:
                continue
            key = id(ac)
            if key in seen:
                continue
            seen.add(key)
            add_curve(ac, layers["cyan"], created)

    # ----- Riepilogo passi per il report -----
    steps_info = []
    for k in sorted(axes.keys()):
        steps_info.append({
            "order": k,
            "role": axes[k]["role"],
            "mirrored": per_step.get(k, 0),
            "valid": axes[k]["seg"] is not None,
        })

    return created, counts, nmir, npts, fallbacks, steps_info


def report(vals, counts, nmir, npts, fb, steps_info, opts, ntot,
           dims_list, vmeta, disp_vars):
    print("=== PKG Esegue Parametrico v2.2 ===")
    varstr = "  ".join("%s=%g" % (k, vals.get(k, 0.0)) for k in disp_vars)
    print("Variabili: %s" % varstr)

    # Avvisi di range (min/max dichiarati nel TXT).
    for k in disp_vars:
        meta = vmeta.get(k)
        if not meta:
            continue
        _dflt, vmin, vmax, _desc = meta
        v = vals.get(k)
        if v is None:
            continue
        if vmin is not None and v < vmin - 1e-9:
            print("[RANGE] %s=%g sotto il minimo dichiarato (%g)" % (k, v, vmin))
        if vmax is not None and v > vmax + 1e-9:
            print("[RANGE] %s=%g sopra il massimo dichiarato (%g)" % (k, v, vmax))

    if dims_list:
        print("Dimensioni interne utili:")
        for (dim, formula, val, desc) in eval_dims(dims_list, vals):
            print("   %s = %s mm   (%s)  [%s]"
                  % (dim, _fmt_num(val), formula, desc))

    print("Curve: Taglio=%d Cordone=%d MezzoTaglio=%d Foratore=%d"
          % (counts.get("T", 0), counts.get("C", 0),
             counts.get("M", 0), counts.get("F", 0)))
    print("Geometrie: linee=%d archi=%d conici=%d libere=%d"
          % (counts.get("line", 0), counts.get("arc", 0),
             counts.get("conic", 0), counts.get("free", 0)))
    print("Ricostruzione: parametriche=%d (di cui orfani risolti=%d)  a coordinate fisse=%d"
          % (counts.get("param", 0), counts.get("snapped", 0), counts.get("fixed", 0)))

    if steps_info:
        if opts["mirror"]:
            print("Passi di specchiatura: %d (ordine = interno -> esterno)"
                  % len(steps_info))
            for s in steps_info:
                tt = ("tratteggiato/patella (cancella origine)"
                      if s["role"] == AXIS_ROLE_DASHED
                      else "continuo/simmetria (mantiene origine)")
                extra = "" if s["valid"] else "  [ASSE NON VALIDO: niente specchio]"
                print("   Passo %d: %s - geometrie riflesse=%d%s"
                      % (s["order"], tt, s["mirrored"], extra))
            print("Specchi totali applicati: %d" % nmir)
        else:
            print("Assi rilevati: %d (specchiatura disattivata)." % len(steps_info))
    else:
        print("Nessun asse di specchiatura rilevato (colonna Ruolo o UserText 'A='):"
              " nessuna specchiatura.")

    if counts.get("fillet", 0) or counts.get("fillet_fail", 0):
        msg = "Raccordi da note inseriti: %d" % counts.get("fillet", 0)
        if counts.get("fillet_fail", 0):
            msg += (" (non riusciti: %d - raggio incompatibile o punto ambiguo)"
                    % counts.get("fillet_fail", 0))
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

def get_inputs_eto(vals, opts, disp_vars, vmeta, dims_list):
    F = _ETOF
    D = _ETOD

    FALLBACK_LABELS = {"L": "lunghezza", "P": "profondita", "A": "altezza",
                       "S": "spessore", "C": "patella", "E": "smusso",
                       "T": "lembo"}

    class Dlg(F.Dialog[bool]):
        def __init__(self):
            self.Title = "PKG Esegue Parametrico v2.2 - Variabili"
            self.Padding = D.Padding(12)
            self.Resizable = False
            self.action = "close"
            self.result_vals = dict(vals)
            self.result_opts = dict(opts)
            self.tb = {}
            self.dim_labels = []  # [(formula, Label)]

            lay = F.DynamicLayout()
            lay.Spacing = D.Size(8, 6)

            banner = F.Label()
            if vmeta:
                banner.Text = "Default letti dal TXT (modello)"
            else:
                banner.Text = ("ATTENZIONE: header VARIABILI assente nel TXT, "
                               "uso i default interni")
            try:
                banner.Font = D.Font(D.SystemFont.Bold, 9)
            except:
                pass
            lay.AddRow(banner)
            lay.AddRow(None)

            for k in disp_vars:
                meta = vmeta.get(k, (None, None, None, ""))
                desc = meta[3] or FALLBACK_LABELS.get(k, "")
                vmin = meta[1]
                vmax = meta[2]
                lbl = F.Label()
                lbl.Text = "%s   %s" % (k, desc)
                lbl.VerticalAlignment = F.VerticalAlignment.Center
                t = F.TextBox()
                t.Text = ("%g" % vals.get(k, 0.0))
                t.Width = 90
                self.tb[k] = t
                t.TextChanged += self.on_change  # dopo aver impostato il testo
                hint = F.Label()
                if vmin is not None or vmax is not None:
                    hint.Text = "[min %s | max %s]" % (
                        _fmt_num(vmin) if vmin is not None else "-",
                        _fmt_num(vmax) if vmax is not None else "-")
                else:
                    hint.Text = ""
                hint.VerticalAlignment = F.VerticalAlignment.Center
                lay.AddRow(lbl, t, hint)

            # Pannello DIMENSIONI INTERNE UTILI (aggiornato live).
            if dims_list:
                lay.AddRow(None)
                sec = F.Label()
                sec.Text = "DIMENSIONI INTERNE UTILI (live)"
                try:
                    sec.Font = D.Font(D.SystemFont.Bold, 9)
                except:
                    pass
                lay.AddRow(sec)
                for (dim, formula, desc) in dims_list:
                    name = F.Label()
                    name.Text = "%s   %s" % (dim, desc)
                    name.VerticalAlignment = F.VerticalAlignment.Center
                    val = F.Label()
                    val.VerticalAlignment = F.VerticalAlignment.Center
                    self.dim_labels.append((formula, val))
                    lay.AddRow(name, val)

            self.cb_mirror = F.CheckBox()
            self.cb_mirror.Text = "Esegui specchiature (passi annidati)"
            self.cb_mirror.Checked = opts["mirror"]
            self.cb_axis = F.CheckBox()
            self.cb_axis.Text = "Disegna assi di costruzione (debug)"
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
            self.refresh_dims()

        def current_vals(self):
            """Variabili correnti: parte dal seed (ambiente completo) e
            sovrascrive con i valori digitati nelle textbox."""
            cv = dict(vals)
            for k in self.tb:
                fv = to_float_input(self.tb[k].Text)
                if fv is not None:
                    cv[k] = fv
            return cv

        def refresh_dims(self):
            if not self.dim_labels:
                return
            cv = self.current_vals()
            for formula, lbl in self.dim_labels:
                v = eval_quiet(formula, cv)
                lbl.Text = "= %s mm   (%s)" % (_fmt_num(v), formula)

        def on_change(self, s, e):
            try:
                self.refresh_dims()
            except:
                pass

        def on_apply(self, s, e):
            self.action = "apply"
            self.result_vals = self.current_vals()
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


def get_inputs_console(vals, opts, disp_vars, vmeta, dims_list):
    out = dict(vals)
    for k in disp_vars:
        meta = vmeta.get(k, (None, None, None, ""))
        desc = meta[3] or k
        gn = Rhino.Input.Custom.GetNumber()
        gn.SetCommandPrompt("Valore %s (%s)" % (k, desc))
        gn.SetDefaultNumber(float(vals.get(k, 0.0)))
        gn.AcceptNothing(True)
        gn.Get()
        if gn.CommandResult() != Rhino.Commands.Result.Success:
            return "close", out, opts
        out[k] = float(gn.Number())
    if dims_list:
        print("DIMENSIONI INTERNE UTILI:")
        for (dim, formula, val, desc) in eval_dims(dims_list, out):
            print("   %s = %s mm   (%s)  [%s]"
                  % (dim, _fmt_num(val), formula, desc))
    o = dict(opts)
    o["mirror"] = ask_yn("Esegui specchiature (passi annidati)?", opts["mirror"])
    o["axis"] = ask_yn("Disegna assi di costruzione (debug)?", opts["axis"])
    o["points"] = ask_yn("Disegna punti parametrici?", opts["points"])
    o["clear"] = ask_yn("Cancella ricostruzione precedente?", opts["clear"])
    o["fillets"] = ask_yn("Inserisci raccordi dalle note?", opts.get("fillets", True))
    return "apply", out, o


def get_inputs(vals, opts, disp_vars, vmeta, dims_list):
    if HAS_ETO:
        try:
            return get_inputs_eto(vals, opts, disp_vars, vmeta, dims_list)
        except:
            return get_inputs_console(vals, opts, disp_vars, vmeta, dims_list)
    return get_inputs_console(vals, opts, disp_vars, vmeta, dims_list)


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

    # Default, range e dimensioni interne utili PRESI DAL TXT (header v5.x).
    vars_list, dims_list = parse_header(path)
    disp_vars = display_var_order(vars_list)
    vmeta = var_meta_map(vars_list)
    vals = seed_vals(vars_list)
    if vars_list:
        print("Variabili lette dal TXT: %s"
              % ", ".join("%s=%g" % (v[0], v[1]) for v in vars_list))
    else:
        print("Header VARIABILI assente nel TXT: uso i default interni.")
    if dims_list:
        print("Dimensioni interne utili dichiarate: %d formula/e"
              % len(dims_list))

    # Default 'axis'=False: nel modello a passi gli assi sono di servizio e
    # non devono comparire nella fustella finale.
    opts = {"mirror": True, "axis": False, "points": False,
            "clear": True, "fillets": True}
    opts = load_opts(opts)

    while True:
        action, vals, opts = get_inputs(vals, opts, disp_vars, vmeta, dims_list)
        if action != "apply":
            break

        if opts["clear"]:
            clear_previous()

        created, counts, nmir, npts, fb, steps_info = reconstruct(
            rows, vals, opts, layers, pmap)

        if created:
            grp = sc.doc.Groups.Add()
            for gid in created:
                sc.doc.Groups.AddToGroup(grp, gid)

        save_opts(opts)
        sc.doc.Views.Redraw()
        report(vals, counts, nmir, npts, fb, steps_info, opts, len(created),
               dims_list, vmeta, disp_vars)

        if not HAS_ETO:
            if not ask_yn("Ripetere con altri valori?", False):
                break

    print("Terminato.")


if __name__ == "__main__":
    main()
