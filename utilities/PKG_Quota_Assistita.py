#! python 2
# -*- coding: utf-8 -*-

# =============================================================================
#  PKG QUOTA ASSISTITA  v1.3  -  Rhino 7 / 8  (IronPython 2.7)
#
#  Novita' v1.3 (FIX BLOCCO "Preleva da quote"):
#    - In v1.2 il prelievo NASCONDEVA il dialogo modale e lanciava un
#      GetObject: ma un dialogo modale (ShowDialog) DISABILITA la finestra
#      principale di Rhino anche da nascosto, quindi il GetObject non
#      poteva ricevere ne' clic ne' Esc -> blocco totale.
#    - Ora il pulsante CHIUDE il dialogo restituendo il testo corrente; la
#      selezione delle quote avviene in contesto Rhino normale (pienamente
#      funzionante, Esc/Invio inclusi); il dialogo RIAPRE con il testo
#      conservato e le formule prelevate accodate. La quota provvisoria
#      resta visibile per tutta l'operazione e NON e' selezionabile come
#      sorgente (esclusa per Id, oltre a non avere formula).
#
#  Novita' v1.2:
#    - FINESTRA ALLARGATA (664 px utili): formule lunghe visibili per
#      intero nel campo e nella scomposizione.
#    - PRELEVA DA QUOTE: pulsante per selezionare in Rhino una o piu'
#      quote-funzione esistenti e ACCODARNE il testo nel campo formula.
#      Ogni formula composita viene avvolta tra parentesi (la convenzione
#      visiva dei gruppi) e concatenata con '+'; il segno si corregge a
#      mano se serve. Comodo per costruire una posizione come somma di
#      tratti gia' quotati.
#
#  Novita' v1.1:
#    - SCOMPOSIZIONE LIVE: la formula viene divisa nei TERMINI DI PRIMO
#      LIVELLO (i gruppi tra parentesi e i termini sciolti) e per ciascuno
#      il dialogo mostra valore e somma progressiva. Scrivendo ad esempio
#      "(L/2+S*2+1)+(A+S*3)" si vede:
#          (L/2+S*2+1)  =  52.0000    Sigma   52.0000
#          +(A+S*3)     = 151.5000    Sigma  203.5000
#      cosi' ogni gruppo (la piega, la patella, ...) e' verificabile da
#      solo, e la somma progressiva corrisponde alla posizione raggiunta
#      lungo il tracciato dopo ogni elemento.
#
#  Inserimento ASSISTITO delle quote-funzione per PKG_Annotator (>= v4.3).
#  Sostituisce il flusso "quota lineare standard + doppio clic + editing del
#  testo" con un flusso unico: tre clic, dialogo con verifica LIVE della
#  formula, conferma. Niente errori di battitura da ripescare dopo, niente
#  riedizione quota per quota.
#
#  FLUSSO PER OGNI QUOTA:
#    1. clic prima estremita'  (Invio/Esc = fine sessione)
#    2. clic seconda estremita'
#    3. clic posizione della linea di quota (anteprima dinamica; l'asse X o
#       Y e' dedotto dalla posizione, come nel comando _Dim; opzione "Asse"
#       per forzarlo)
#    4. dialogo: misura reale + campo formula con verifica live (verde =
#       combacia, arancio = entro 10x tolleranza, rosso = NON combacia) +
#       lista di CANDIDATI ESATTI gia' calcolati dalle variabili (clic per
#       inserire, doppio clic per confermare subito)
#    5. OK -> la quota e' creata con il testo sovrascritto = formula.
#
#  VARIABILI: lette dal Document User Text (chiavi PKG_L, PKG_P, ...) - le
#  stesse scritte da PKG_Annotator con "salva nel documento". Se mancano,
#  si apre il dialogo parametri (con opzione di salvarle nel documento).
#
#  QUOTE DI DEFINIZIONE: se la formula e' il solo nome di una variabile
#  (es. "L") e la misura NON combacia col valore a documento, il pulsante
#  "Definisci <var> = misura" adotta la misura come nuovo valore della
#  variabile (aggiornando il Document User Text). Utile per le prime quote
#  di un disegno nuovo.
#
#  CONTRATTO CON PKG_Annotator (_dim_info / collect_quote_constraints):
#    - la formula va nel testo sovrascritto (AnnotationBase.PlainText);
#    - l'asse e' dedotto da Plane.XAxis della LinearDimension:
#        XAxis == mondo +/-X -> quota 'X'; XAxis == mondo +/-Y -> quota 'Y';
#    - la verifica e' |misura lungo l'asse| vs |valore formula|, con la
#      stessa compare_value (tolleranza assoluta + componente relativa).
#  Le quote OBLIQUE (vincoli 'D', es. bisello E a 45 gradi) non sono gestite
#  da questo script: vanno inserite a mano come prima (restano comunque
#  lette e verificate da PKG_Annotator).
#
#  Convenzioni toolkit: solo RhinoCommon + scriptcontext (no
#  rhinoscriptsyntax), niente f-string, stringhe %, except Exception, ex.
# =============================================================================

import Rhino
import scriptcontext as sc
import System
import System.Windows.Forms as WinForms
import System.Drawing as Drawing
import math
import re
from Rhino.Geometry import Point3d, Point2d, Plane, Vector3d, LinearDimension

# -----------------------------------------------------------------------------
#  COSTANTI (allineate a PKG_Annotator v4.4)
# -----------------------------------------------------------------------------
DECIMALS    = 4
REL_EPS     = 1e-9                  # componente relativa della soglia "ok"
LAYER_QUOTE = "Quote"               # layer di destinazione delle quote
COLOR_QUOTE = Drawing.Color.FromArgb(105, 105, 105)

VAR_NAMES = ["L", "P", "A", "S", "C", "T", "E"]
VAR_LABELS = {
    "L": "Larghezza",
    "P": "Profondita",
    "A": "Altezza",
    "S": "Spessore cartone",
    "C": "Patella d'incollatura",
    "T": "Patella di chiusura (Tuck)",
    "E": "Bisello (misura configurabile)",
}
VAR_DEFAULTS = {
    "L": 100.0, "P": 60.0, "A": 150.0, "S": 0.5,
    "C": 12.0,  "T": 30.0, "E": 8.0,
}
THICKNESS_VARS = ["S", "E"]                       # multipli sensati solo qui
COMPOUND_TERMS = ["(L-S)", "(P-S)", "(A-S)"]
DOC_USERTEXT_PREFIX = "PKG_"

ALLOWED_FUNCS = {
    "abs":  abs,
    "sqrt": math.sqrt,
    "sin":  math.sin,
    "cos":  math.cos,
    "tan":  math.tan,
    "pi":   math.pi,
}

COLOR_OK      = Drawing.Color.FromArgb(0,   140, 0)
COLOR_APPROX  = Drawing.Color.FromArgb(190, 130, 0)
COLOR_ERR     = Drawing.Color.FromArgb(190, 30,  30)
COLOR_NEUTRAL = Drawing.Color.FromArgb(110, 110, 110)
COLOR_PREVIEW = Drawing.Color.FromArgb(0, 120, 200)   # anteprima dinamica

# -----------------------------------------------------------------------------
#  PARSER SICURO + CONFRONTO (identici a PKG_Annotator)
# -----------------------------------------------------------------------------
_SAFE_CHARS_RE = re.compile(r"^[0-9\.\+\-\*\/\(\)\,\s a-zA-Z_]+$")

def safe_eval(expr, vars_dict):
    if expr is None:
        return None, "vuoto"
    expr = expr.strip()
    if not expr:
        return None, "vuoto"
    if not _SAFE_CHARS_RE.match(expr):
        return None, "caratteri non ammessi"

    tokens = re.findall(r"[a-zA-Z_][a-zA-Z_0-9]*", expr)
    allowed_names = set(VAR_NAMES) | set(ALLOWED_FUNCS.keys())
    for tok in tokens:
        if tok not in allowed_names:
            return None, "simbolo sconosciuto: %s" % tok

    try:
        code = compile(expr, "<pkg_expr>", "eval")
    except Exception, ex:
        return None, "sintassi: %s" % ex

    ns = {"__builtins__": {}}
    ns.update(ALLOWED_FUNCS)
    ns.update(vars_dict)

    try:
        val = eval(code, ns, {})
    except ZeroDivisionError:
        return None, "divisione per zero"
    except Exception, ex:
        return None, "errore: %s" % ex

    try:
        val = float(val)
    except Exception, ex:
        return None, "risultato non numerico"
    return val, None


def compare_value(computed, real, tol):
    """Stessa logica di PKG_Annotator: soglia 'ok' = tolleranza assoluta del
    documento + componente relativa minima (REL_EPS * |reale|)."""
    delta = abs(computed - real)
    ok_tol = tol + REL_EPS * abs(real)
    if delta <= ok_tol:
        return "ok", delta
    elif delta <= tol * 10.0:
        return "approx", delta
    else:
        return "err", delta


def split_top_level_terms(expr):
    """Divide l'espressione nei termini ADDITIVI di primo livello,
    conservando il segno del termine:
        '(L/2+S*2+1)+(A+S*3)' -> ['(L/2+S*2+1)', '+(A+S*3)']
        'L-S-2'               -> ['L', '-S', '-2']
    I +/- dentro parentesi o subito dopo un operatore (segno unario,
    'S*-1', '(', ',') NON spezzano."""
    terms = []
    depth = 0
    cur = ""
    prev = ""                       # ultimo carattere significativo
    for ch in expr:
        if ch in "([":
            depth += 1
        elif ch in ")]":
            depth -= 1
        if (ch in "+-" and depth == 0 and cur.strip()
                and prev not in "*/+-(,"):
            terms.append(cur.strip())
            cur = ch                # il segno resta attaccato al termine
            prev = ch
            continue
        cur += ch
        if not ch.isspace():
            prev = ch
    if cur.strip():
        terms.append(cur.strip())
    return terms


# -----------------------------------------------------------------------------
#  VARIABILI DA/VERSO DOCUMENT USER TEXT (identiche a PKG_Annotator)
# -----------------------------------------------------------------------------
def load_params_from_doc():
    result = {}
    for name in VAR_NAMES:
        key = DOC_USERTEXT_PREFIX + name
        val = sc.doc.Strings.GetValue(key)
        if val is not None and val != "":
            try:
                result[name] = float(val.replace(",", "."))
            except ValueError:
                pass
    return result


def save_params_to_doc(vars_dict):
    for name in vars_dict:
        key = DOC_USERTEXT_PREFIX + name
        sc.doc.Strings.SetString(key, "%.6f" % vars_dict[name])


# -----------------------------------------------------------------------------
#  DIALOGO PARAMETRI (compatto)
# -----------------------------------------------------------------------------
def show_params_dialog(found):
    """Campi per le 7 variabili, precompilati con i valori a documento (se
    presenti) o i default. Ritorna (vars_dict, save_to_doc) o (None, False)."""
    form = WinForms.Form()
    form.Text = "Quota assistita - Parametri packaging"
    form.Width = 420
    form.Height = 420
    form.StartPosition = WinForms.FormStartPosition.CenterScreen
    form.FormBorderStyle = WinForms.FormBorderStyle.FixedDialog
    form.MaximizeBox = False
    form.BackColor = Drawing.Color.FromArgb(245, 245, 245)

    lbl = WinForms.Label()
    lbl.Text = ("Variabili non trovate (tutte) nel Document User Text.\n"
                "Controlla i valori e conferma.")
    lbl.Font = Drawing.Font("Segoe UI", 8)
    lbl.Location = Drawing.Point(14, 10)
    lbl.Size = Drawing.Size(380, 32)
    form.Controls.Add(lbl)

    boxes = {}
    y = 50
    for name in VAR_NAMES:
        lab = WinForms.Label()
        lab.Text = "%s - %s" % (name, VAR_LABELS[name])
        lab.Font = Drawing.Font("Segoe UI", 8)
        lab.Location = Drawing.Point(14, y + 3)
        lab.Size = Drawing.Size(250, 18)
        form.Controls.Add(lab)

        tb = WinForms.TextBox()
        tb.Font = Drawing.Font("Consolas", 9)
        tb.Location = Drawing.Point(280, y)
        tb.Size = Drawing.Size(110, 22)
        v = found.get(name, VAR_DEFAULTS[name])
        tb.Text = ("%g" % v)
        form.Controls.Add(tb)
        boxes[name] = tb
        y += 30

    chk = WinForms.CheckBox()
    chk.Text = "Salva nel documento (consigliato)"
    chk.Font = Drawing.Font("Segoe UI", 8)
    chk.Checked = True
    chk.Location = Drawing.Point(14, y + 4)
    chk.Size = Drawing.Size(260, 20)
    form.Controls.Add(chk)
    y += 32

    result = {"vars": None, "save": False}

    btn_ok = WinForms.Button()
    btn_ok.Text = "OK"
    btn_ok.Location = Drawing.Point(218, y)
    btn_ok.Size = Drawing.Size(80, 26)
    def on_ok(s, e):
        vals = {}
        for n in VAR_NAMES:
            try:
                vals[n] = float(boxes[n].Text.strip().replace(",", "."))
            except Exception, ex:
                WinForms.MessageBox.Show(
                    "Valore non valido per %s." % n, "Parametri",
                    WinForms.MessageBoxButtons.OK,
                    WinForms.MessageBoxIcon.Warning)
                return
        result["vars"] = vals
        result["save"] = bool(chk.Checked)
        form.Close()
    btn_ok.Click += on_ok
    form.Controls.Add(btn_ok)

    btn_no = WinForms.Button()
    btn_no.Text = "Annulla"
    btn_no.Location = Drawing.Point(310, y)
    btn_no.Size = Drawing.Size(80, 26)
    def on_no(s, e):
        form.Close()
    btn_no.Click += on_no
    form.Controls.Add(btn_no)

    form.AcceptButton = btn_ok
    form.CancelButton = btn_no
    form.ShowDialog()
    return result["vars"], result["save"]


# -----------------------------------------------------------------------------
#  CANDIDATI ESATTI (mini-motore allineato ai criteri v4.3:
#  variabili nulle escluse, multipli solo per gli spessori S/E)
# -----------------------------------------------------------------------------
def _base_terms(vars_dict, tol):
    """Lista [(expr, valore, complessita')] dei termini base non nulli."""
    terms = []
    for n in VAR_NAMES:
        v = vars_dict.get(n, 0.0)
        if abs(v) <= tol:
            continue                       # variabili nulle: mai suggerite
        terms.append((n, v, 1))
        terms.append((n + "/2", v / 2.0, 2))
        if n in THICKNESS_VARS:
            terms.append((n + "*2", v * 2.0, 2))
            terms.append((n + "*3", v * 3.0, 2))
    for ct in COMPOUND_TERMS:
        val, err = safe_eval(ct, vars_dict)
        if err is None and abs(val) > tol:
            terms.append((ct, val, 2))
            terms.append((ct + "/2", val / 2.0, 3))
    return terms


def exact_candidates(measured, vars_dict, tol, max_results=12):
    """Formule che combaciano ESATTAMENTE (status 'ok') con la misura.
    Singoli termini, somme e differenze (risultato positivo) di due termini.
    Le somme sono generate una sola volta (commutative); le coppie costruite
    sulla STESSA variabile (L-L/2, E*2-E, ...) sono escluse: algebricamente
    riducibili, sarebbero solo rumore. Ritorna [(expr, valore)] ordinata per
    complessita' crescente."""
    terms = _base_terms(vars_dict, tol)
    found = {}

    def vset(expr):
        return frozenset(re.findall(r"[A-Z]", expr))

    def try_add(expr, val, cplx):
        if val <= tol:
            return
        status, delta = compare_value(val, measured, tol)
        if status != "ok":
            return
        key = expr.replace(" ", "")
        if key not in found or cplx < found[key][2]:
            found[key] = (expr, val, cplx)

    for (e, v, c) in terms:
        try_add(e, v, c)

    n = len(terms)
    for i in range(n):
        e1, v1, c1 = terms[i]
        s1 = vset(e1)
        for j in range(n):
            if i == j:
                continue
            e2, v2, c2 = terms[j]
            s2 = vset(e2)
            if s1 == s2 and len(s1) == 1:
                continue                  # stessa variabile: riducibile
            if j > i:
                try_add("%s+%s" % (e1, e2), v1 + v2, c1 + c2 + 1)
            try_add("%s-%s" % (e1, e2), v1 - v2, c1 + c2 + 1)

    out = sorted(found.values(), key=lambda t: (t[2], len(t[0]), t[0]))
    return [(e, v) for (e, v, c) in out[:max_results]]


# -----------------------------------------------------------------------------
#  ASSE E GEOMETRIA DELLA QUOTA
# -----------------------------------------------------------------------------
def decide_axis(p1, p2, p3, tol, forced=None):
    """Deduce l'asse di misura ('X' o 'Y') dalla posizione della linea di
    quota, come il comando _Dim. 'forced' (X/Y) ha la precedenza."""
    if forced in ("X", "Y"):
        return forced
    dx = abs(p2.X - p1.X)
    dy = abs(p2.Y - p1.Y)
    if dy <= tol:
        return "X"
    if dx <= tol:
        return "Y"
    # estremi non allineati: decide la posizione del terzo punto.
    xmin, xmax = min(p1.X, p2.X), max(p1.X, p2.X)
    ymin, ymax = min(p1.Y, p2.Y), max(p1.Y, p2.Y)
    ox = 0.0
    if p3.X < xmin:
        ox = xmin - p3.X
    elif p3.X > xmax:
        ox = p3.X - xmax
    oy = 0.0
    if p3.Y < ymin:
        oy = ymin - p3.Y
    elif p3.Y > ymax:
        oy = p3.Y - ymax
    if oy > ox:
        return "X"          # linea di quota sopra/sotto -> misura orizzontale
    if ox > oy:
        return "Y"          # linea di quota a destra/sinistra -> verticale
    return "X" if dx >= dy else "Y"


def dim_plane_and_points(p1, p2, p3, axis):
    """Costruisce (plane, e1, e2, lp) per la LinearDimension.
    Il piano e' orientato cosi' che Plane.XAxis sia l'asse di misura: e' la
    convenzione che _dim_info di PKG_Annotator usa per classificare X/Y."""
    origin = Point3d(p1.X, p1.Y, 0.0)
    if axis == "X":
        plane = Plane(origin, Vector3d.XAxis, Vector3d.YAxis)
    else:
        plane = Plane(origin, Vector3d.YAxis, -Vector3d.XAxis)

    def to_uv(p):
        d = Point3d(p.X, p.Y, 0.0) - origin
        return (d * plane.XAxis, d * plane.YAxis)

    u1, v1 = to_uv(p1)
    u2, v2 = to_uv(p2)
    u3, v3 = to_uv(p3)
    e1 = Point2d(u1, v1)
    e2 = Point2d(u2, v2)
    lp = Point2d((u1 + u2) * 0.5, v3)     # linea di quota all'offset del clic
    return plane, e1, e2, lp


def measured_along(p1, p2, axis):
    if axis == "X":
        return abs(p2.X - p1.X)
    return abs(p2.Y - p1.Y)


# -----------------------------------------------------------------------------
#  GETPOINT CON ANTEPRIMA DINAMICA (terzo clic)
# -----------------------------------------------------------------------------
class GetDimLinePoint(Rhino.Input.Custom.GetPoint):
    """Anteprima della quota mentre si sceglie la posizione della linea."""
    def __init__(self, p1, p2, tol, forced_axis):
        self.p1 = p1
        self.p2 = p2
        self.tol = tol
        self.forced_axis = forced_axis

    def OnDynamicDraw(self, e):
        try:
            p3 = e.CurrentPoint
            ax = decide_axis(self.p1, self.p2, p3, self.tol, self.forced_axis)
            if ax == "X":
                a = Point3d(self.p1.X, p3.Y, 0.0)
                b = Point3d(self.p2.X, p3.Y, 0.0)
            else:
                a = Point3d(p3.X, self.p1.Y, 0.0)
                b = Point3d(p3.X, self.p2.Y, 0.0)
            e.Display.DrawLine(Point3d(self.p1.X, self.p1.Y, 0.0), a,
                               COLOR_PREVIEW)
            e.Display.DrawLine(Point3d(self.p2.X, self.p2.Y, 0.0), b,
                               COLOR_PREVIEW)
            e.Display.DrawLine(a, b, COLOR_PREVIEW)
            mid = Point3d((a.X + b.X) * 0.5, (a.Y + b.Y) * 0.5, 0.0)
            mis = measured_along(self.p1, self.p2, ax)
            e.Display.DrawDot(mid, "%s %.4g" % (ax, mis))
        except Exception, ex:
            pass
        Rhino.Input.Custom.GetPoint.OnDynamicDraw(self, e)


# -----------------------------------------------------------------------------
#  PRELIEVO FORMULE DA QUOTE ESISTENTI (v1.2)
# -----------------------------------------------------------------------------
def wrap_if_composite(expr):
    """Avvolge tra parentesi una formula con piu' termini di primo livello,
    se non e' gia' interamente racchiusa da UNA coppia di parentesi.
    E' la convenzione visiva dei gruppi: ogni tratto del tracciato resta
    riconoscibile dentro la formula composta."""
    expr = (expr or "").strip()
    if not expr:
        return expr
    if expr.startswith("(") and expr.endswith(")"):
        depth = 0
        wrapped = True
        for i in range(len(expr)):
            ch = expr[i]
            if ch == "(":
                depth += 1
            elif ch == ")":
                depth -= 1
                if depth == 0 and i < len(expr) - 1:
                    wrapped = False   # la prima parentesi chiude prima della fine
                    break
        if wrapped:
            return expr
    if len(split_top_level_terms(expr)) > 1:
        return "(" + expr + ")"
    return expr


def pick_dim_formulas(exclude_id=None):
    """Selezione in Rhino di una o piu' quote-funzione; ritorna la lista dei
    loro PlainText nell'ordine di selezione (solo quote LinearDimension con
    almeno una variabile nel testo; le altre sono saltate con avviso).
    'exclude_id': Guid da ignorare (la quota provvisoria in lavorazione)."""
    out = []
    go = Rhino.Input.Custom.GetObject()
    go.SetCommandPrompt(
        "Seleziona le quote da prelevare (Invio=conferma, Esc=annulla)")
    go.GeometryFilter = Rhino.DocObjects.ObjectType.Annotation
    go.SubObjectSelect = False
    go.EnablePreSelect(False, True)
    res = go.GetMultiple(1, 0)
    if res != Rhino.Input.GetResult.Object:
        return out
    for i in range(go.ObjectCount):
        obj = go.Object(i).Object()
        if obj is None:
            continue
        if exclude_id is not None and obj.Id == exclude_id:
            continue                      # quota provvisoria in lavorazione
        geo = obj.Geometry
        if not isinstance(geo, Rhino.Geometry.LinearDimension):
            print "Preleva: oggetto non LinearDimension, saltato."
            continue
        try:
            t = (geo.PlainText or "").strip()
        except Exception, ex:
            t = ""
        has_var = False
        for n in VAR_NAMES:
            if n in t:
                has_var = True
                break
        if not t or not has_var:
            print "Preleva: quota senza formula ('%s'), saltata." % t
            continue
        out.append(t)
    sc.doc.Objects.UnselectAll()
    sc.doc.Views.Redraw()
    return out


# -----------------------------------------------------------------------------
#  DIALOGO FORMULA CON VERIFICA LIVE
# -----------------------------------------------------------------------------
def show_formula_dialog(measured, axis, vars_dict, tol, count,
                        initial_text=""):
    """Ritorna (action, expr):
       action = 'ok' | 'skip' | 'end' | 'pickdims'
       expr   = formula confermata ('ok') oppure testo corrente del campo
                ('pickdims': il chiamante seleziona le quote e riapre il
                dialogo col testo arricchito).
    'initial_text' precompila il campo formula (riapertura dopo prelievo)."""
    fmt = "%." + str(DECIMALS) + "f"

    form = WinForms.Form()
    form.Text = "Quota assistita #%d - asse %s" % (count, axis)
    form.ClientSize = Drawing.Size(664, 448)   # v1.2: allargata
    form.StartPosition = WinForms.FormStartPosition.CenterScreen
    form.FormBorderStyle = WinForms.FormBorderStyle.FixedDialog
    form.MaximizeBox = False
    form.TopMost = True
    form.BackColor = Drawing.Color.FromArgb(245, 245, 245)

    lbl_mis = WinForms.Label()
    lbl_mis.Text = "Misura reale (asse %s):  %s mm" % (axis, fmt % measured)
    lbl_mis.Font = Drawing.Font("Segoe UI", 9, Drawing.FontStyle.Bold)
    lbl_mis.Location = Drawing.Point(14, 12)
    lbl_mis.Size = Drawing.Size(560, 20)
    form.Controls.Add(lbl_mis)

    lbl_vars = WinForms.Label()
    lbl_vars.Text = "  ".join("%s=%g" % (n, vars_dict.get(n, 0.0))
                              for n in VAR_NAMES)
    lbl_vars.Font = Drawing.Font("Consolas", 8)
    lbl_vars.ForeColor = COLOR_NEUTRAL
    lbl_vars.Location = Drawing.Point(14, 34)
    lbl_vars.Size = Drawing.Size(636, 16)
    form.Controls.Add(lbl_vars)

    lbl_f = WinForms.Label()
    lbl_f.Text = "Formula (testo della quota):"
    lbl_f.Font = Drawing.Font("Segoe UI", 8)
    lbl_f.Location = Drawing.Point(14, 58)
    lbl_f.Size = Drawing.Size(300, 16)
    form.Controls.Add(lbl_f)

    txt = WinForms.TextBox()
    txt.Font = Drawing.Font("Consolas", 11)
    txt.Location = Drawing.Point(14, 76)
    txt.Size = Drawing.Size(636, 26)
    form.Controls.Add(txt)

    lbl_fb = WinForms.Label()
    lbl_fb.Text = "(vuoto)"
    lbl_fb.Font = Drawing.Font("Consolas", 9)
    lbl_fb.ForeColor = COLOR_NEUTRAL
    lbl_fb.Location = Drawing.Point(14, 106)
    lbl_fb.Size = Drawing.Size(636, 18)
    form.Controls.Add(lbl_fb)

    lbl_dec = WinForms.Label()
    lbl_dec.Text = "Scomposizione (gruppi di primo livello):"
    lbl_dec.Font = Drawing.Font("Segoe UI", 8)
    lbl_dec.Location = Drawing.Point(14, 128)
    lbl_dec.Size = Drawing.Size(340, 16)
    form.Controls.Add(lbl_dec)

    lst_dec = WinForms.ListBox()
    lst_dec.Font = Drawing.Font("Consolas", 9)
    lst_dec.Location = Drawing.Point(14, 146)
    lst_dec.Size = Drawing.Size(636, 76)
    lst_dec.HorizontalScrollbar = True
    # 'None' e' parola chiave: l'enum va recuperato con getattr
    lst_dec.SelectionMode = getattr(WinForms.SelectionMode, "None")
    form.Controls.Add(lst_dec)

    lbl_sug = WinForms.Label()
    lbl_sug.Text = "Candidati esatti (clic = inserisci, doppio clic = OK):"
    lbl_sug.Font = Drawing.Font("Segoe UI", 8)
    lbl_sug.Location = Drawing.Point(14, 230)
    lbl_sug.Size = Drawing.Size(340, 16)
    form.Controls.Add(lbl_sug)

    lst = WinForms.ListBox()
    lst.Font = Drawing.Font("Consolas", 9)
    lst.Location = Drawing.Point(14, 248)
    lst.Size = Drawing.Size(636, 150)
    form.Controls.Add(lst)

    state = {"status": "empty", "exprs": []}
    result = {"action": "skip", "expr": ""}

    def fill_suggestions():
        lst.Items.Clear()
        state["exprs"] = []
        cands = exact_candidates(measured, vars_dict, tol)
        for (e, v) in cands:
            lst.Items.Add("%-34s = %s" % (e, fmt % v))
            state["exprs"].append(e)
        if not cands:
            lst.Items.Add("(nessun candidato esatto: digitare la formula)")

    btn_use = WinForms.Button()
    btn_use.Text = "Definisci variabile = misura"
    btn_use.Font = Drawing.Font("Segoe UI", 8)
    btn_use.Location = Drawing.Point(184, 410)
    btn_use.Size = Drawing.Size(210, 28)
    btn_use.Enabled = False
    form.Controls.Add(btn_use)

    def update_decomposition(expr):
        """Mostra valore e somma progressiva di ogni termine di primo
        livello: e' l'associazione visiva gruppo <-> elemento del tracciato."""
        lst_dec.Items.Clear()
        terms = split_top_level_terms(expr)
        if len(terms) < 2:
            if terms:
                lst_dec.Items.Add("(termine unico: nessuna scomposizione)")
            return
        cum = 0.0
        for t in terms:
            tv, terr = safe_eval(t, vars_dict)
            if terr is not None:
                lst_dec.Items.Add("%-34s   ?  (%s)" % (t, terr))
                continue
            cum += tv
            lst_dec.Items.Add("%-34s = %12s   Sigma %12s" % (
                t, fmt % tv, fmt % cum))

    def update_feedback(sender=None, e=None):
        expr = txt.Text.strip()
        btn_use.Enabled = False
        update_decomposition(expr)
        if not expr:
            state["status"] = "empty"
            lbl_fb.Text = "(vuoto)"
            lbl_fb.ForeColor = COLOR_NEUTRAL
            return
        val, err = safe_eval(expr, vars_dict)
        if err is not None:
            state["status"] = "err"
            lbl_fb.Text = "Errore: %s" % err
            lbl_fb.ForeColor = COLOR_ERR
            return
        status, delta = compare_value(abs(val), measured, tol)
        state["status"] = status
        if status == "ok":
            lbl_fb.Text = "= %s   OK (delta %.2e)" % (fmt % val, delta)
            lbl_fb.ForeColor = COLOR_OK
        elif status == "approx":
            lbl_fb.Text = "= %s   ~ entro 10x tolleranza (delta %.4f)" % (
                fmt % val, delta)
            lbl_fb.ForeColor = COLOR_APPROX
        else:
            lbl_fb.Text = "= %s   NON combacia (misura %s)" % (
                fmt % val, fmt % measured)
            lbl_fb.ForeColor = COLOR_ERR
            if expr in VAR_NAMES:
                btn_use.Enabled = True
                btn_use.Text = "Definisci %s = %s" % (expr, fmt % measured)

    txt.TextChanged += update_feedback

    def on_use(sender, e):
        name = txt.Text.strip()
        if name not in VAR_NAMES:
            return
        vars_dict[name] = round(measured, DECIMALS)
        save_params_to_doc(vars_dict)
        print "Quota assistita: %s = %s salvato nel documento." % (
            name, fmt % vars_dict[name])
        lbl_vars.Text = "  ".join("%s=%g" % (n, vars_dict.get(n, 0.0))
                                  for n in VAR_NAMES)
        fill_suggestions()
        update_feedback()
    btn_use.Click += on_use

    btn_pick_dim = WinForms.Button()
    btn_pick_dim.Text = "Preleva da quote"
    btn_pick_dim.Font = Drawing.Font("Segoe UI", 8)
    btn_pick_dim.Location = Drawing.Point(14, 410)
    btn_pick_dim.Size = Drawing.Size(160, 28)
    form.Controls.Add(btn_pick_dim)

    def on_pick_dims(sender, e):
        """v1.3: CHIUDE il dialogo chiedendo al chiamante di far selezionare
        le quote in contesto Rhino normale, poi riaprirlo col testo
        arricchito. (Un dialogo modale, anche nascosto, disabilita la
        finestra di Rhino: il GetObject non riceverebbe input.)"""
        result["action"] = "pickdims"
        result["expr"] = txt.Text.strip()
        form.Close()
    btn_pick_dim.Click += on_pick_dims

    def on_pick(sender, e):
        i = lst.SelectedIndex
        if 0 <= i < len(state["exprs"]):
            txt.Text = state["exprs"][i]
            txt.SelectionStart = len(txt.Text)
            txt.Focus()
    lst.SelectedIndexChanged += on_pick

    def accept():
        expr = txt.Text.strip()
        if not expr:
            WinForms.MessageBox.Show(
                "Formula vuota: usare 'Salta' per non inserire la quota.",
                "Quota assistita", WinForms.MessageBoxButtons.OK,
                WinForms.MessageBoxIcon.Information)
            return
        if state["status"] == "err":
            r = WinForms.MessageBox.Show(
                "La formula NON combacia con la misura.\n"
                "Inserire comunque la quota?",
                "Quota assistita - verifica fallita",
                WinForms.MessageBoxButtons.YesNo,
                WinForms.MessageBoxIcon.Warning)
            if r != WinForms.DialogResult.Yes:
                return
        result["action"] = "ok"
        result["expr"] = expr
        form.Close()

    def on_dblclick(sender, e):
        i = lst.SelectedIndex
        if 0 <= i < len(state["exprs"]):
            txt.Text = state["exprs"][i]
            accept()
    lst.DoubleClick += on_dblclick

    btn_ok = WinForms.Button()
    btn_ok.Text = "OK"
    btn_ok.Location = Drawing.Point(404, 410)
    btn_ok.Size = Drawing.Size(80, 28)
    btn_ok.Click += lambda s, e: accept()
    form.Controls.Add(btn_ok)

    btn_skip = WinForms.Button()
    btn_skip.Text = "Salta"
    btn_skip.Location = Drawing.Point(492, 410)
    btn_skip.Size = Drawing.Size(80, 28)
    def on_skip(s, e):
        result["action"] = "skip"
        form.Close()
    btn_skip.Click += on_skip
    form.Controls.Add(btn_skip)

    btn_end = WinForms.Button()
    btn_end.Text = "Fine"
    btn_end.Location = Drawing.Point(580, 410)
    btn_end.Size = Drawing.Size(80, 28)
    def on_end(s, e):
        result["action"] = "end"
        form.Close()
    btn_end.Click += on_end
    form.Controls.Add(btn_end)

    form.AcceptButton = btn_ok          # Invio = OK
    form.CancelButton = btn_skip        # Esc   = Salta

    fill_suggestions()
    if initial_text:
        txt.Text = initial_text           # scatena gia' update_feedback
        txt.SelectionStart = len(txt.Text)
    update_feedback()
    txt.Select()
    form.ShowDialog()
    return result["action"], result["expr"]


# -----------------------------------------------------------------------------
#  CREAZIONE / FINALIZZAZIONE QUOTA
# -----------------------------------------------------------------------------
def get_or_create_layer(name, color):
    idx = sc.doc.Layers.FindByFullPath(name, -1)
    if idx >= 0:
        return idx
    layer = Rhino.DocObjects.Layer()
    layer.Name  = name
    layer.Color = color
    return sc.doc.Layers.Add(layer)


def add_provisional_dimension(p1, p2, p3, axis, layer_index):
    """Crea SUBITO la quota (testo di default = misura) cosi' resta visibile
    mentre il dialogo e' aperto. Ritorna il Guid (o Guid.Empty)."""
    plane, e1, e2, lp = dim_plane_and_points(p1, p2, p3, axis)
    ld = LinearDimension(plane, e1, e2, lp)
    # NOTA: niente 'ld.Aligned = False'. Il costruttore crea gia' una quota
    # lineare (non allineata); su Rhino 6+ toccare il setter Aligned puo'
    # innescare un ricalcolo del piano dell'annotazione, alterando l'asse
    # di misura che _dim_info di PKG_Annotator legge da Plane.XAxis.
    attr = Rhino.DocObjects.ObjectAttributes()
    attr.LayerIndex = layer_index
    guid = sc.doc.Objects.AddLinearDimension(ld, attr)
    if guid != System.Guid.Empty:
        sc.doc.Views.Redraw()
    return guid


def rollback_dimension(guid):
    if guid is None or guid == System.Guid.Empty:
        return
    sc.doc.Objects.Delete(guid, True)
    sc.doc.Views.Redraw()


def finalize_dimension(guid, expr):
    """Sovrascrive il testo della quota con la formula (PlainText: e' la
    proprieta' che _dim_info di PKG_Annotator legge)."""
    if guid is None or guid == System.Guid.Empty:
        return False
    rh_obj = sc.doc.Objects.FindId(guid)
    if rh_obj is None:
        return False
    try:
        dim = rh_obj.Geometry
        dim.PlainText = expr
        if rh_obj.CommitChanges():
            sc.doc.Views.Redraw()
            return True
    except Exception, ex:
        pass
    # Fallback: Replace con una copia modificata.
    try:
        dim2 = rh_obj.Geometry.Duplicate()
        dim2.PlainText = expr
        oref = Rhino.DocObjects.ObjRef(rh_obj.Id)
        if sc.doc.Objects.Replace(oref, dim2):
            sc.doc.Views.Redraw()
            return True
    except Exception, ex:
        pass
    return False


# -----------------------------------------------------------------------------
def main():
    print "=" * 60
    print "PKG QUOTA ASSISTITA v1.0"
    print "=" * 60

    # --- variabili: documento -> dialogo se mancanti ---
    vars_dict = load_params_from_doc()
    missing = [n for n in VAR_NAMES if n not in vars_dict]
    if missing:
        vals, save = show_params_dialog(vars_dict)
        if vals is None:
            print "Quota assistita: annullato (parametri)."
            return
        vars_dict = vals
        if save:
            save_params_to_doc(vars_dict)
            print "Parametri salvati nel documento (PKG_*)."
    print "Variabili: " + "  ".join(
        "%s=%g" % (n, vars_dict.get(n, 0.0)) for n in VAR_NAMES)

    tol = sc.doc.ModelAbsoluteTolerance
    if tol <= 0:
        tol = 0.001

    idx_layer = get_or_create_layer(LAYER_QUOTE, COLOR_QUOTE)

    forced_axis = None      # None = Auto; persiste per la sessione
    axis_labels = ["Auto", "X", "Y"]
    count = 0

    while True:
        # --- 1) prima estremita' ---
        gp1 = Rhino.Input.Custom.GetPoint()
        gp1.SetCommandPrompt(
            "Quota #%d - prima estremita' (Invio=fine, Asse=%s)" % (
                count + 1, forced_axis or "Auto"))
        gp1.AcceptNothing(True)
        cur = 0 if forced_axis is None else axis_labels.index(forced_axis)
        opt_axis = gp1.AddOptionList("Asse", axis_labels, cur)
        res = gp1.Get()
        if res == Rhino.Input.GetResult.Option:
            sel = gp1.Option().CurrentListOptionIndex
            forced_axis = None if sel == 0 else axis_labels[sel]
            continue
        if res != Rhino.Input.GetResult.Point:
            break
        p1 = gp1.Point()

        # --- 2) seconda estremita' ---
        gp2 = Rhino.Input.Custom.GetPoint()
        gp2.SetCommandPrompt("Seconda estremita'")
        gp2.SetBasePoint(p1, True)
        gp2.DrawLineFromPoint(p1, True)
        if gp2.Get() != Rhino.Input.GetResult.Point:
            continue
        p2 = gp2.Point()
        if p1.DistanceTo(p2) <= tol:
            print "Estremita' coincidenti: quota ignorata."
            continue

        # --- 3) posizione della linea di quota (anteprima dinamica) ---
        gp3 = GetDimLinePoint(p1, p2, tol, forced_axis)
        gp3.SetCommandPrompt("Posizione linea di quota")
        if gp3.Get() != Rhino.Input.GetResult.Point:
            continue
        p3 = gp3.Point()

        axis = decide_axis(p1, p2, p3, tol, forced_axis)
        measured = measured_along(p1, p2, axis)
        if measured <= tol:
            print "Misura nulla lungo l'asse %s: quota ignorata." % axis
            continue

        # --- quota provvisoria visibile durante il dialogo ---
        guid = add_provisional_dimension(p1, p2, p3, axis, idx_layer)
        if guid == System.Guid.Empty:
            print "Creazione quota fallita."
            continue

        # dialogo formula; 'pickdims' = selezione quote e riapertura
        pending_text = ""
        while True:
            action, expr = show_formula_dialog(
                measured, axis, vars_dict, tol, count + 1,
                initial_text=pending_text)
            if action != "pickdims":
                break
            cur = expr
            formulas = pick_dim_formulas(exclude_id=guid)
            for f_ in formulas:
                piece = wrap_if_composite(f_)
                cur = piece if not cur else (cur + "+" + piece)
            pending_text = cur

        if action == "ok":
            if finalize_dimension(guid, expr):
                count += 1
                print "Quota #%d: asse %s, misura %.4f, formula '%s'." % (
                    count, axis, measured, expr)
            else:
                rollback_dimension(guid)
                print "ERRORE: impossibile scrivere il testo della quota."
        elif action == "skip":
            rollback_dimension(guid)
        else:                              # 'end'
            rollback_dimension(guid)
            break

    sc.doc.Views.Redraw()
    print "Quota assistita: %d quota/e funzione inserita/e." % count
    if count > 0:
        print ("Seleziona le quote e lancia PKG_Annotator per verifica, "
               "propagazione e creazione punti.")


if __name__ == "__main__":
    main()
