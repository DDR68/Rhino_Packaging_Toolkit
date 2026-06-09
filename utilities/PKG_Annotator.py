#! python 2
# -*- coding: utf-8 -*-

# =============================================================================
#  PACKAGING POINT ANNOTATOR  v4.3  -  Rhino 7 / 8  (IronPython 2.7)
#
#  Novita' v4.3 (motore di suggerimento):
#    - fase COSTRUTTIVA: vicino reale + scarto geometrico (somma di pannelli)
#    - sorgenti ordinate PER ASSE (X: vicini allineati in orizzontale,
#      Y: vicini allineati in verticale)
#    - variabili a valore nullo (es. T=0) escluse da tutti i suggerimenti
#    - multipli (X*2, X*3) limitati agli spessori S, E
#    - chiave canonica RAZIONALE (espande (P-S), fonde P/2+P/2 -> P)
#    - display fedele alla sequenza dei pannelli (mai aggregato in 2*L)
#
#  Variabili packaging:
#    L = Larghezza         P = Profondita      A = Altezza
#    S = Spessore cartone  C = Patella d'incollatura (colla)
#    T = Patella di chiusura (Tuck)             E = Bisello (misura configurabile)
#
#  Novita' v4.2 rispetto a v4.0:
#    [1] PRECISIONE / CONFRONTO ROBUSTO PER FORMULE LUNGHE
#        La lunghezza della formula NON pregiudica il confronto: il parser usa
#        compile()/eval() (nessun limite pratico di lunghezza) e il confronto e'
#        in float64 sul valore reale grezzo del punto (pt.X/pt.Y), non su valori
#        arrotondati. L'errore di rappresentazione accumulato su una somma di
#        molti termini resta dell'ordine di 1e-11 mm, ben sotto ogni tolleranza
#        geometrica. Per blindare il caso di tolleranza documento molto stretta
#        su coordinate di grande modulo, la soglia "ok" ora e':
#            ok_tol = tol + 1e-9 * |valore_reale|
#        Componente relativa minima (sub-micron) che NON allenta la precisione
#        geometrica ma rende il confronto indipendente dalla lunghezza/scala.
#
#    [2] ANCORA "PIU' LONTANO DA 0" -> RIFERIMENTI IN SOTTRAZIONE
#        Speculare al caso target==0 (che ritorna "0"), il reverse lookup ora
#        individua, tra le SOLE formule realmente presenti nel documento, quella
#        il cui valore assoluto e' massimo lungo l'asse (il punto piu' lontano
#        da 0). La usa come ANCORA e genera candidati per sottrazione
#        (ancora - V, ancora - (L-S), ...) con priorita' massima. Cosi' i punti
#        intermedi vengono espressi come "totale - scarto" SENZA inventare nulla:
#        l'ancora e' una formula esistente, non una combinazione fabbricata.
#        Il fallback combinatorio (che invece "inventa") resta solo come ultima
#        risorsa, con priorita' piu' bassa.
#
#    [3] SPECCHIA CURVE TAGGATE (mirror lungo una linea)
#        Nuova opzione "SpecchiaCurve" nel prompt di acquisizione punti.
#        Specchia gruppi di linee/curve lungo una linea di proiezione:
#          - le CURVE da specchiare portano una UserString con valore
#            "Proietta su A" (oppure B, C...);
#          - la LINEA di proiezione e' colorata CIANO e porta una UserString
#            con valore "A" (oppure B, C...).
#        Ogni curva "Proietta su X" viene specchiata sulla linea cyan "X".
#        Il riflesso e' creato sul lato opposto della linea (piano di mirror
#        contenente la linea e l'asse Z del mondo). La nota "Proietta su X" sul
#        duplicato viene sostituita con "Specchiato da X" per non rispecchiarlo
#        di nuovo. Semplifica molto l'inserimento del mezzo simmetrico.
#
#  Eredita da v4.0:
#    - VISIBILITA' AL CLIC: il Point e' creato e disegnato SUBITO dopo il clic.
#    - ROLLBACK PULITO su "Salta"/"Annulla tutto".
#    - SUGGERIMENTO COORDINATA ZERO: target 0 -> ritorna la sola costante "0".
#    - TERMINI COMPOSTI DI COMPENSAZIONE: (L-S), (P-S), (A-S) nei candidati.
#    - Naming geometrico PKG_X+0112_Y-0030, nota in UserString "Nota".
#    - TextDot colore per completezza, sovrascrittura per chiave geometrica.
#    - Reverse lookup "vicino geometrico" con pool di sorgenti.
# =============================================================================

import Rhino
import scriptcontext as sc
import System
import System.Windows.Forms as WinForms
import System.Drawing as Drawing
import math
import re
from Rhino.Geometry import Point3d, TextDot

# -----------------------------------------------------------------------------
DECIMALS     = 4
DOT_HEIGHT   = 10
DOT_FONT     = "Consolas"
LAYER_POINTS = "PKG_Punti_Parametrici"
LAYER_DOTS   = "Quote"
COLOR_POINTS = System.Drawing.Color.FromArgb(0, 80, 180)
COLOR_DOTS   = System.Drawing.Color.FromArgb(105, 105, 105)
DOT_OFFSET_X = 5.0
DOT_OFFSET_Y = 3.0

# Soglia relativa minima aggiunta alla tolleranza assoluta nel confronto "ok"
# (Punto 1 v4.2). Sub-micron in pratica: blinda il confronto su coordinate di
# grande modulo senza allentare la precisione geometrica.
REL_EPS = 1e-9

# Colori TextDot per stato di completezza
COLOR_DOT_COMPLETE   = Drawing.Color.FromArgb(105, 105, 105)   # grigio: X e Y entrambi compilati e validi
COLOR_DOT_INCOMPLETE = Drawing.Color.FromArgb(220, 180, 0)     # giallo: mancanze (Nota esclusa dal calcolo)

VAR_NAMES = ["L", "P", "A", "S", "C", "T", "E"]

# Termini COMPOSTI aggiungibili nel reverse lookup.
COMPOUND_TERMS = ["(L-S)", "(P-S)", "(A-S)"]

# Variabili di SPESSORE: per queste i multipli (S*2, S*3, E*2) hanno senso
# fisico (compensazioni di spessore del materiale). Per le altre (L, P, A, C)
# un multiplo come L*2 o P*3 non corrisponde a nulla nel blank e indurrebbe
# in errore: i pannelli ripetuti si scrivono come somma (C+P-S+L+P+L).
THICKNESS_VARS = ["S", "E"]
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

# Regex per il riconoscimento delle note di proiezione (Punto 3 v4.2)
_PROIETTA_RE = re.compile(r"^\s*proietta\s+su\s+(.+?)\s*$", re.IGNORECASE)


# -----------------------------------------------------------------------------
#  NAMING GEOMETRICO
# -----------------------------------------------------------------------------
def make_point_key(x, y):
    """Costruisce la chiave geometrica del punto, arrotondando al millimetro.
    Formato: PKG_X+0112_Y-0030  (segno esplicito, padding a 4 cifre)."""
    ix = int(round(x))
    iy = int(round(y))
    sx = "+" if ix >= 0 else "-"
    sy = "+" if iy >= 0 else "-"
    return "PKG_X%s%04d_Y%s%04d" % (sx, abs(ix), sy, abs(iy))


def make_dot_key(x, y):
    """Chiave per il TextDot associato a un punto."""
    ix = int(round(x))
    iy = int(round(y))
    sx = "+" if ix >= 0 else "-"
    sy = "+" if iy >= 0 else "-"
    return "PKG_DOT_X%s%04d_Y%s%04d" % (sx, abs(ix), sy, abs(iy))


# -----------------------------------------------------------------------------
#  PARSER SICURO
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
    except Exception:
        return None, "risultato non numerico"

    return val, None


def compare_value(computed, real, tol):
    """Confronto valore calcolato vs reale (Punto 1 v4.2).

    Soglia "ok": tolleranza assoluta del documento PIU' una componente
    relativa minima (REL_EPS * |real|) che assorbe l'errore di rappresentazione
    float su coordinate di grande modulo. NON allenta la precisione geometrica
    (resta ben sotto il micron) ma rende il confronto robusto a prescindere
    dalla LUNGHEZZA della formula o dalla scala del modello.
    """
    delta = abs(computed - real)
    ok_tol = tol + REL_EPS * abs(real)
    if delta <= ok_tol:
        return "ok", delta
    elif delta <= tol * 10.0:
        return "approx", delta
    else:
        return "err", delta


# -----------------------------------------------------------------------------
def get_or_create_layer(name, color):
    idx = sc.doc.Layers.FindByFullPath(name, -1)
    if idx >= 0:
        return idx
    layer = Rhino.DocObjects.Layer()
    layer.Name  = name
    layer.Color = color
    return sc.doc.Layers.Add(layer)


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
def show_params_dialog(preset=None, conflict_names=None):
    """Dialog parametri. 'preset' (opzionale): valori derivati dalle QUOTE di
    definizione (testo quota = nome variabile); hanno precedenza sui valori
    del documento e sono evidenziati in azzurro. 'conflict_names': variabili
    con quote discordi, evidenziate in ROSSO perche' il valore proposto (il
    piu' frequente) va controllato dall'utente."""
    doc_params = load_params_from_doc()
    preset = preset or {}
    conflict_names = conflict_names or set()

    form = WinForms.Form()
    form.Text = "Parametri Packaging - Configurazione"
    form.Width = 460
    form.Height = 460
    form.MinimumSize = Drawing.Size(460, 460)
    form.MaximumSize = Drawing.Size(460, 460)
    form.StartPosition = WinForms.FormStartPosition.CenterScreen
    form.FormBorderStyle = WinForms.FormBorderStyle.FixedDialog
    form.MaximizeBox = False
    form.BackColor = Drawing.Color.FromArgb(245, 245, 245)

    lbl_title = WinForms.Label()
    lbl_title.Text = "Imposta i valori delle variabili packaging"
    lbl_title.Font = Drawing.Font("Segoe UI", 9, Drawing.FontStyle.Bold)
    lbl_title.Location = Drawing.Point(14, 12)
    lbl_title.Size = Drawing.Size(420, 20)
    form.Controls.Add(lbl_title)

    lbl_sub = WinForms.Label()
    lbl_sub.Text = "I valori in Document User Text sono stati caricati (se presenti). Modifica e conferma."
    lbl_sub.Font = Drawing.Font("Segoe UI", 8)
    lbl_sub.ForeColor = COLOR_NEUTRAL
    lbl_sub.Location = Drawing.Point(14, 32)
    lbl_sub.Size = Drawing.Size(420, 32)
    form.Controls.Add(lbl_sub)

    boxes = {}
    y = 72
    for name in VAR_NAMES:
        lbl_var = WinForms.Label()
        lbl_var.Text = "%s  =" % name
        lbl_var.Font = Drawing.Font("Consolas", 10, Drawing.FontStyle.Bold)
        lbl_var.ForeColor = COLOR_POINTS
        lbl_var.Location = Drawing.Point(14, y)
        lbl_var.Size = Drawing.Size(40, 22)
        form.Controls.Add(lbl_var)

        txt = WinForms.TextBox()
        txt.Font = Drawing.Font("Consolas", 10)
        txt.Location = Drawing.Point(58, y - 2)
        txt.Size = Drawing.Size(90, 24)
        if name in conflict_names:
            txt.Text = "%g" % preset.get(name, VAR_DEFAULTS[name])
            txt.BackColor = Drawing.Color.FromArgb(250, 220, 220)   # rosso: quote discordi
        elif name in preset:
            txt.Text = "%g" % preset[name]
            txt.BackColor = Drawing.Color.FromArgb(224, 238, 250)   # azzurro: da quota
        elif name in doc_params:
            txt.Text = "%g" % doc_params[name]
            txt.BackColor = Drawing.Color.FromArgb(232, 245, 232)
        else:
            txt.Text = "%g" % VAR_DEFAULTS[name]
        form.Controls.Add(txt)
        boxes[name] = txt

        lbl_desc = WinForms.Label()
        lbl_desc.Text = VAR_LABELS[name]
        lbl_desc.Font = Drawing.Font("Segoe UI", 9)
        lbl_desc.Location = Drawing.Point(160, y)
        lbl_desc.Size = Drawing.Size(280, 22)
        form.Controls.Add(lbl_desc)

        y += 32

    cb_save = WinForms.CheckBox()
    cb_save.Text = "Salva i valori nei Document User Text (chiavi PKG_*)"
    cb_save.Font = Drawing.Font("Segoe UI", 9)
    cb_save.Location = Drawing.Point(14, y + 8)
    cb_save.Size = Drawing.Size(420, 22)
    cb_save.Checked = True
    form.Controls.Add(cb_save)

    btn_ok = WinForms.Button()
    btn_ok.Text = "Avvia sessione"
    btn_ok.Font = Drawing.Font("Segoe UI", 9, Drawing.FontStyle.Bold)
    btn_ok.BackColor = Drawing.Color.FromArgb(0, 100, 200)
    btn_ok.ForeColor = Drawing.Color.White
    btn_ok.FlatStyle = WinForms.FlatStyle.Flat
    btn_ok.Location = Drawing.Point(230, y + 40)
    btn_ok.Size = Drawing.Size(120, 30)
    btn_ok.DialogResult = WinForms.DialogResult.OK
    form.Controls.Add(btn_ok)
    form.AcceptButton = btn_ok

    btn_cancel = WinForms.Button()
    btn_cancel.Text = "Annulla"
    btn_cancel.Font = Drawing.Font("Segoe UI", 9)
    btn_cancel.Location = Drawing.Point(355, y + 40)
    btn_cancel.Size = Drawing.Size(80, 30)
    btn_cancel.DialogResult = WinForms.DialogResult.Cancel
    form.Controls.Add(btn_cancel)
    form.CancelButton = btn_cancel

    result = form.ShowDialog()
    if result != WinForms.DialogResult.OK:
        return None, False

    out = {}
    for name in VAR_NAMES:
        raw = boxes[name].Text.strip().replace(",", ".")
        try:
            out[name] = float(raw)
        except ValueError:
            WinForms.MessageBox.Show(
                "Valore non valido per %s: '%s'. Uso default %s." % (
                    name, raw, VAR_DEFAULTS[name]),
                "Parametri Packaging",
                WinForms.MessageBoxButtons.OK,
                WinForms.MessageBoxIcon.Warning)
            out[name] = VAR_DEFAULTS[name]

    return out, cb_save.Checked


# -----------------------------------------------------------------------------
#  REVERSE LOOKUP - basato sul vicino geometrico
# -----------------------------------------------------------------------------
def collect_source_formulas(target_pt, k_neighbors=3, exclude_at_zero_dist=False, tol=1e-6):
    """Raccoglie un POOL di formule sorgenti per il reverse lookup.
    Ritorna (sources_x, sources_y) ordinate per priorita', senza duplicati
    e senza stringhe vuote."""
    idx = sc.doc.Layers.FindByFullPath(LAYER_POINTS, -1)
    if idx < 0:
        return [], []

    entries = []

    for obj in sc.doc.Objects:
        if obj.IsDeleted:
            continue
        if obj.Attributes.LayerIndex != idx:
            continue
        if not isinstance(obj.Geometry, Rhino.Geometry.Point):
            continue
        p = obj.Geometry.Location
        dx = p.X - target_pt.X
        dy = p.Y - target_pt.Y
        d = math.sqrt(dx * dx + dy * dy)
        if exclude_at_zero_dist and d <= tol:
            continue
        ex = obj.Attributes.GetUserString("X_param") or ""
        ey = obj.Attributes.GetUserString("Y_param") or ""
        if ex == "--": ex = ""
        if ey == "--": ey = ""
        entries.append((abs(dx), abs(dy), ex, ey))

    if not entries:
        return [], []

    # Ordinamento PER ASSE (v4.3). Per la formula X il vicino piu' informativo
    # e' quello allineato in ORIZZONTALE (|dy| minimo: il gap in X e' la
    # larghezza di un pannello); per la Y quello allineato in VERTICALE
    # (|dx| minimo: il gap in Y e' l'altezza di un pannello). E' il motivo per
    # cui con l'ordinamento euclideo unico la X usciva bene e la Y spesso no.
    entries_x = sorted(entries, key=lambda t: (t[1], t[0]))
    entries_y = sorted(entries, key=lambda t: (t[0], t[1]))

    sources_x = []
    sources_y = []
    seen_x = set()
    seen_y = set()

    for adx, ady, ex, ey in entries_x:
        if ex and ex not in seen_x:
            sources_x.append(ex)
            seen_x.add(ex)
    for adx, ady, ex, ey in entries_y:
        if ey and ey not in seen_y:
            sources_y.append(ey)
            seen_y.add(ey)

    return sources_x, sources_y


def find_nearest_annotated_point(target_pt, exclude_at_zero_dist=False, tol=1e-6):
    """Wrapper retrocompatibile: ritorna la PRIMA sorgente del pool."""
    sx_list, sy_list = collect_source_formulas(
        target_pt, k_neighbors=1,
        exclude_at_zero_dist=exclude_at_zero_dist, tol=tol)
    ex = sx_list[0] if sx_list else None
    ey = sy_list[0] if sy_list else None
    return ex, ey, None


def split_top_level_terms(expr):
    """Spezza un'espressione nei suoi termini di somma di primo livello,
    rispettando le parentesi. Ogni termine porta con se' il proprio segno."""
    expr = expr.strip()
    if not expr:
        return []
    terms = []
    depth = 0
    current = ""
    sign = "+"
    i = 0
    if expr[0] in "+-":
        sign = expr[0]
        i = 1
    while i < len(expr):
        ch = expr[i]
        if ch == "(":
            depth += 1
            current += ch
        elif ch == ")":
            depth -= 1
            current += ch
        elif ch in "+-" and depth == 0:
            terms.append(sign + current.strip())
            sign = ch
            current = ""
        else:
            current += ch
        i += 1
    if current.strip():
        terms.append(sign + current.strip())
    return terms


def join_terms(terms):
    """Inverso di split_top_level_terms."""
    if not terms:
        return ""
    out = terms[0].lstrip("+")
    for t in terms[1:]:
        if t.startswith("+"):
            out += "+" + t[1:]
        else:
            out += t
    return out


_MONO_RE = re.compile(r"^([A-Z])$|^([A-Z])/(\d+)$|^([A-Z])\*(\d+)$|^(\d+)\*([A-Z])$")


def _gcd(a, b):
    while b:
        a, b = b, a % b
    return a


def _expand_signed_terms(expr, outer_sign, out):
    """Espande ricorsivamente i termini additivi di primo livello aprendo le
    parentesi che avvolgono una somma: '-(P-S)' -> -P, +S. Le parentesi
    ridondanti attorno a un singolo monomio ('(P/2)') vengono rimosse."""
    for t in split_top_level_terms(expr):
        if not t:
            continue
        if t[0] == "-":
            s = -outer_sign
            body = t[1:].strip()
        elif t[0] == "+":
            s = outer_sign
            body = t[1:].strip()
        else:
            s = outer_sign
            body = t.strip()
        if not body:
            continue
        if body.startswith("(") and body.endswith(")"):
            depth = 0
            wraps = True
            for i in range(len(body)):
                ch = body[i]
                if ch == "(":
                    depth += 1
                elif ch == ")":
                    depth -= 1
                    if depth == 0 and i < len(body) - 1:
                        wraps = False
                        break
            if wraps:
                inner = body[1:-1].strip()
                if len(split_top_level_terms(inner)) > 1:
                    _expand_signed_terms(inner, s, out)
                    continue
                body = inner
        out.append((s, body))


def canonical_form(expr):
    """CHIAVE canonica per confronto e deduplicazione (NON per il display).
    Espande le parentesi additive e aggrega i monomi X, X/n, X*n, n*X con
    coefficienti RAZIONALI. Cosi' 'C+(P-S)+L' e 'C+P-S+L' hanno la stessa
    chiave, e '(P/2)+A+P/2' coincide con 'A+P'. I monomi non riconosciuti
    restano atomi opachi. Ritorna '0' se tutto si annulla."""
    pairs = []
    try:
        _expand_signed_terms(expr, 1, pairs)
    except Exception, ex:
        return expr.strip()
    coeffs = {}
    for s, body in pairs:
        is_num = False
        fv = 0.0
        try:
            fv = float(body)
            is_num = True
        except ValueError:
            pass
        if is_num:
            if fv == 0.0:
                continue
            key = "#" + body
            num, den = s, 1
        else:
            m = _MONO_RE.match(body.replace(" ", ""))
            if m:
                if m.group(1):
                    key, num, den = m.group(1), s, 1
                elif m.group(2):
                    key, num, den = m.group(2), s, int(m.group(3))
                elif m.group(4):
                    key, num, den = m.group(4), s * int(m.group(5)), 1
                else:
                    key, num, den = m.group(7), s * int(m.group(6)), 1
            else:
                key, num, den = body, s, 1
        on, od = coeffs.get(key, (0, 1))
        n2 = on * den + num * od
        d2 = od * den
        if n2 == 0:
            coeffs[key] = (0, 1)
        else:
            g = _gcd(abs(n2), d2)
            coeffs[key] = (n2 // g, d2 // g)

    parts = []
    for key in sorted(coeffs.keys()):
        num, den = coeffs[key]
        if num == 0:
            continue
        parts.append("%s:%d/%d" % (key, num, den))
    if not parts:
        return "0"
    return "|".join(parts)


def simplify_display(expr):
    """Semplificazione SOLO di facciata: elimina le coppie di termini opposti
    di primo livello (es. '...-S+S') PRESERVANDO l'ordine dei pannelli.
    Non aggrega mai i coefficienti: 'C+P-S+L+P+L' resta scritto cosi',
    non diventa 'C+2*P+2*L-S'."""
    terms = split_top_level_terms(expr)
    norm = []
    for t in terms:
        if not t:
            continue
        if t[0] in "+-":
            norm.append(t)
        else:
            norm.append("+" + t)
    removed = [False] * len(norm)
    for i in range(len(norm)):
        if removed[i]:
            continue
        if norm[i][0] == "+":
            opp = "-" + norm[i][1:]
        else:
            opp = "+" + norm[i][1:]
        for j in range(i + 1, len(norm)):
            if not removed[j] and norm[j] == opp:
                removed[i] = True
                removed[j] = True
                break
    kept = []
    for i in range(len(norm)):
        if not removed[i]:
            kept.append(norm[i])
    if not kept:
        return "0"
    return join_terms(kept)


def neighbor_candidates_from(expr_source):
    """Varianti della formula sorgente per riduzione e aggiunta di un termine."""
    candidates = []
    terms = split_top_level_terms(expr_source)
    if not terms:
        for v in VAR_NAMES:
            candidates.append(v)
            candidates.append("-" + v)
        return candidates

    existing = set(terms)

    # 1) Riduzione di testa e coda
    if len(terms) > 1:
        candidates.append(join_terms(terms[:-1]))
        candidates.append(join_terms(terms[1:]))

    # 1bis) Riduzione interna
    if len(terms) > 2:
        for i in range(1, len(terms) - 1):
            candidates.append(join_terms(terms[:i] + terms[i+1:]))

    # 2) Aggiunta in coda, con filtro strutturale
    for v in VAR_NAMES:
        plus  = "+" + v
        minus = "-" + v
        if minus not in existing:
            candidates.append(join_terms(terms + [plus]))
        if plus not in existing:
            candidates.append(join_terms(terms + [minus]))

    # 2bis) Aggiunta in coda dei termini COMPOSTI di compensazione
    for c in COMPOUND_TERMS:
        plus  = "+" + c
        minus = "-" + c
        if plus not in existing:
            candidates.append(join_terms(terms + [plus]))
        if minus not in existing:
            candidates.append(join_terms(terms + [minus]))

    # 3) Aggiunta in testa, stesso filtro
    for v in VAR_NAMES:
        plus  = "+" + v
        minus = "-" + v
        if minus not in existing:
            candidates.append(join_terms([plus] + terms))
        if plus not in existing:
            candidates.append(join_terms([minus] + terms))

    # 3bis) Aggiunta in testa dei termini COMPOSTI
    for c in COMPOUND_TERMS:
        plus  = "+" + c
        minus = "-" + c
        if plus not in existing:
            candidates.append(join_terms([plus] + terms))
        if minus not in existing:
            candidates.append(join_terms([minus] + terms))

    # 4) La sorgente stessa
    candidates.append(join_terms(terms))

    return candidates


def find_farthest_source(source_list, vars_dict):
    """Punto 2 (v4.2). Tra le SOLE formule sorgenti gia' presenti nel documento,
    restituisce quella il cui valore assoluto e' massimo (il punto piu' lontano
    da 0 lungo l'asse). Serve come ANCORA per i riferimenti in sottrazione.
    NON inventa formule: sceglie solo tra quelle reali."""
    best = None
    best_abs = -1.0
    for s in source_list:
        if not s:
            continue
        val, err = safe_eval(s, vars_dict)
        if err is not None or val is None:
            continue
        if abs(val) > best_abs:
            best_abs = abs(val)
            best = s
    return best


def expr_for_gap(gap, vars_dict, tol):
    """Termini (col segno) il cui VALORE eguaglia 'gap', con la loro classe di
    COMPLESSITA': 0 = variabile singola (un pannello), 1 = composto/mezzo/
    multiplo di spessore, 2 = combinazione di due variabili. Ritorna una lista
    di tuple (termine, complessita'). Serve a costruire 'vicino + termine' =
    target; il termine deve valere lo scarto reale entro tolleranza."""
    out = []
    seen = set()

    def add(s, val, cplx):
        if abs(val - gap) <= tol:
            c = canonical_form(s)
            if c and c != "0" and c not in seen:
                seen.add(c)
                out.append((s, cplx))

    # 0) variabili singole (il caso piu' comune: un pannello). Le variabili di
    #    valore nullo (es. T non usata) si saltano: non spostano il valore e
    #    introdurrebbero solo termini spuri.
    for n in VAR_NAMES:
        v = vars_dict.get(n)
        if v is None or abs(v) <= tol:
            continue
        add("+" + n, v, 0)
        add("-" + n, -v, 0)

    # 1) termini composti di compensazione ((P-S), (A-S), ...)
    for c in COMPOUND_TERMS:
        cv, e = safe_eval(c, vars_dict)
        if e is None and cv is not None:
            add("+" + c, cv, 1)
            add("-" + c, -cv, 1)

    # 1bis) mezzi (mezzerie) per tutte le variabili; doppi/tripli SOLO per gli
    #    spessori (S, E): L*2 o P*3 non hanno senso fisico nel blank.
    for n in VAR_NAMES:
        v = vars_dict.get(n)
        if v is None or abs(v) <= tol:
            continue
        add("+" + n + "/2", v / 2.0, 1)
        add("-" + n + "/2", -v / 2.0, 1)
        if n in THICKNESS_VARS:
            add("+" + n + "*2", v * 2.0, 1)
            add("-" + n + "*2", -v * 2.0, 1)
            add("+" + n + "*3", v * 3.0, 1)
            add("-" + n + "*3", -v * 3.0, 1)

    # 2) combinazioni di due variabili (scarto di due pannelli)
    for i in range(len(VAR_NAMES)):
        a = vars_dict.get(VAR_NAMES[i])
        if a is None or abs(a) <= tol:
            continue
        na = VAR_NAMES[i]
        for j in range(i, len(VAR_NAMES)):
            b = vars_dict.get(VAR_NAMES[j])
            if b is None or abs(b) <= tol:
                continue
            nb = VAR_NAMES[j]
            add("+%s+%s" % (na, nb), a + b, 2)
            add("+%s-%s" % (na, nb), a - b, 2)
            add("-%s+%s" % (na, nb), -a + b, 2)
            add("-%s-%s" % (na, nb), -a - b, 2)

    return out


def suggest_formulas(target, vars_dict, tol, source_exprs=None, max_results=15):
    """Reverse lookup parametrico.

    Priorita' dei candidati:
      prio 0 -> COSTRUTTIVO: vicino reale +/- lo scarto geometrico reale
                (il punto come somma cumulativa di pannelli); piu' l'ancora
                "piu' lontano da 0" e i suoi riferimenti in sottrazione
                (Punto 2 v4.2). Tutto derivato da formule REALI del documento;
      prio 1 -> vicini geometrici e pool imparato dal documento (REALI);
      prio 2 -> fallback combinatorio (INVENTATO, ultima risorsa).
    L'ordinamento finale e' (prio, delta, lunghezza), cosi' i candidati
    costruttivi reali precedono sempre quelli fabbricati. Filtro duplicati
    sulla FORMA CANONICA.
    """
    canon_seen = set()
    matches = []  # (display_expr, val, delta, status, prio)

    # CASO SPECIALE: target == 0 -> unico suggerimento sensato e' "0".
    if abs(target) <= tol:
        return [("0", 0.0, 0.0, "ok")]

    # Retrocompatibilita': accetta singola stringa o lista
    if source_exprs is None:
        source_list = []
    elif isinstance(source_exprs, str):
        source_list = [source_exprs] if source_exprs else []
    else:
        source_list = [s for s in source_exprs if s]

    # Soglia "ok" robusta (Punto 1 v4.2): assoluta + relativa minima.
    ok_tol = tol + REL_EPS * abs(target)

    # Variabili "morte": valore ~0 (es. T non usata). Un termine che le contiene
    # non sposta il valore (es. +T con T=0) ma sfuggirebbe al filtro canonico,
    # comparendo come suggerimento-rumore. Le si scarta in modo DINAMICO: se la
    # variabile diventa != 0 torna subito utilizzabile. I nomi sono lettere
    # singole, quindi il test di appartenenza nella forma canonica e' sicuro.
    dead_vars = set(n for n in VAR_NAMES
                    if vars_dict.get(n) is None or abs(vars_dict.get(n, 0.0)) <= ok_tol)

    def display_rank(s):
        # Preferenza di scrittura: meno termini, poi piu' corta.
        return (len(split_top_level_terms(s)), len(s))

    canon_index = {}  # chiave canonica -> indice in matches

    def try_candidate(expr_str, prio, rank2=10 ** 6):
        expr_str = expr_str.strip()
        if not expr_str:
            return
        canon = canonical_form(expr_str)
        if canon == "0":
            return
        for dv in dead_vars:                 # scarta termini con variabili morte
            if dv in canon:
                return
        display_expr = simplify_display(expr_str)
        if canon in canon_seen:
            # Stessa formula in altra veste: adotta la scrittura piu' pulita
            # E il rango migliore -- la stessa formula puo' arrivare prima per
            # una via tortuosa (rango alto) e poi per quella diretta.
            idx = canon_index.get(canon)
            if idx is not None:
                old = matches[idx]
                new_disp = old[0]
                if display_rank(display_expr) < display_rank(old[0]):
                    new_disp = display_expr
                new_prio, new_rank = old[4], old[5]
                if (prio, rank2) < (old[4], old[5]):
                    new_prio, new_rank = prio, rank2
                matches[idx] = (new_disp, old[1], old[2], old[3], new_prio, new_rank)
            return
        canon_seen.add(canon)
        val, err = safe_eval(display_expr, vars_dict)
        if err is not None or val is None:
            return
        delta = abs(val - target)
        if delta <= ok_tol:
            canon_index[canon] = len(matches)
            matches.append((display_expr, val, delta, "ok", prio, rank2))

    # === FASE 0a (COSTRUTTIVO): vicino reale + scarto geometrico reale ===
    # Per i vicini piu' prossimi calcola lo scarto col target e cerca il
    # termine che lo copre: 'src +/- termine'. Riproduce il blank come somma
    # cumulativa di larghezze di pannello -> candidato fisicamente corretto.
    # Limitato ai primi vicini (collect_source_formulas li ordina per distanza)
    # sia per pertinenza sia per costo. Il sotto-ordine rank2 = (indice vicino,
    # complessita' del termine) fa vincere lo SCARTO PIU' SEMPLICE (gap zero o
    # un pannello singolo) e, a parita', il vicino piu' prossimo. La semplicita'
    # del termine DOMINA la vicinanza: un vicino allineato ma raggiunto con una
    # combinazione a due variabili non deve battere un vicino con gap nullo o
    # a un solo pannello.
    for ni, src in enumerate(source_list[:8]):
        v_src, e_src = safe_eval(src, vars_dict)
        if e_src is not None or v_src is None:
            continue
        src_terms = split_top_level_terms(src)
        gap = target - v_src
        if abs(gap) <= ok_tol:
            try_candidate(join_terms(src_terms), 0, ni)        # gap zero: top
            continue
        for ti, (term, cplx) in enumerate(expr_for_gap(gap, vars_dict, ok_tol)):
            try_candidate(join_terms(src_terms + [term]), 0,
                          (cplx * 16 + ti + 1) * 32 + ni)

    # === FASE 0b (PUNTO 2 v4.2): ANCORA "PIU' LONTANO DA 0" -> SOTTRAZIONE ===
    # Individua tra le formule reali quella di modulo massimo e genera
    # esplicitamente i riferimenti in sottrazione (ancora - V, ancora - (L-S)).
    # Priorita' 0: precedono ogni altro candidato a parita' di delta.
    farthest = find_farthest_source(source_list, vars_dict)
    if farthest:
        f_terms = split_top_level_terms(farthest)
        try_candidate(join_terms(f_terms), 0)                 # l'ancora stessa
        for v in VAR_NAMES:                                   # ancora - variabile
            try_candidate(join_terms(f_terms + ["-" + v]), 0)
        for c in COMPOUND_TERMS:                              # ancora - composto
            try_candidate(join_terms(f_terms + ["-" + c]), 0)

    # === FASE 1: vicini/pool reali (priorita' 1) ===
    for src in source_list:
        for cand in neighbor_candidates_from(src):
            try_candidate(cand, 1)

    # === FASE 2: fallback combinatorio INVENTATO (priorita' 2) ===
    if len(matches) < 5:
        # Solo variabili VIVE; multipli (X*2) solo per gli spessori S, E:
        # L*2 o P*3 non corrispondono a nulla di fisico nel blank.
        var_items = [(n, v) for (n, v) in vars_dict.items()
                     if v is not None and abs(v) > ok_tol]
        for name, val in var_items:
            try_candidate(name, 2)
            try_candidate("%s/2" % name, 2)
            if name in THICKNESS_VARS:
                try_candidate("%s*2" % name, 2)
                try_candidate("%s*3" % name, 2)
            try_candidate("%s/3" % name, 2)
            try_candidate("%s/4" % name, 2)
        for i in range(len(var_items)):
            for j in range(len(var_items)):
                if i == j:
                    continue
                n1, _ = var_items[i]
                n2, _ = var_items[j]
                try_candidate("%s+%s" % (n1, n2), 2)
                try_candidate("%s-%s" % (n1, n2), 2)
                if n1 in THICKNESS_VARS:
                    try_candidate("%s*2+%s" % (n1, n2), 2)
                    try_candidate("%s*2-%s" % (n1, n2), 2)
                try_candidate("(%s-%s)/2" % (n1, n2), 2)
                try_candidate("(%s+%s)/2" % (n1, n2), 2)
                if n2 in THICKNESS_VARS:
                    try_candidate("%s-%s*2" % (n1, n2), 2)
                    try_candidate("%s+%s*2" % (n1, n2), 2)
        for pat in ("L+P+S","L+P-S","L-S*2","P-S*2","(L-S*2)/2","(P-S*2)/2",
                    "A+P+S","A+P-S","A-S*2","A+T","A+T-S","A+T+S",
                    "L+C","L-C","P+E","P-E"):
            try_candidate(pat, 2)

    # Ordina per (priorita', sotto-ordine rank2, delta arrotondato, lunghezza).
    # rank2 fa emergere, fra i costruttivi, il vicino piu' prossimo con lo
    # scarto piu' semplice; per gli altri (default alto) decide delta/lunghezza.
    matches.sort(key=lambda t: (t[4], t[5], round(t[2], 9), len(t[0])))
    return [(e, v, d, s) for (e, v, d, s, p, r) in matches[:max_results]]


# -----------------------------------------------------------------------------
def show_suggest_dialog(target_x, target_y, vars_dict, tol,
                        sources_x=None, sources_y=None,
                        source_ex=None, source_ey=None):
    """Dialog 'Suggerisci'."""
    src_x_list = []
    src_y_list = []
    if sources_x:
        src_x_list.extend([s for s in sources_x if s])
    if sources_y:
        src_y_list.extend([s for s in sources_y if s])
    if source_ex and source_ex not in src_x_list:
        src_x_list.append(source_ex)
    if source_ey and source_ey not in src_y_list:
        src_y_list.append(source_ey)

    matches_x = suggest_formulas(target_x, vars_dict, tol, source_exprs=src_x_list)
    matches_y = suggest_formulas(target_y, vars_dict, tol, source_exprs=src_y_list)

    form = WinForms.Form()
    form.Text = "Suggerisci formula - reverse lookup (vicino geometrico)"
    form.Width = 720
    form.Height = 480
    form.StartPosition = WinForms.FormStartPosition.CenterScreen
    form.FormBorderStyle = WinForms.FormBorderStyle.FixedDialog
    form.MaximizeBox = False
    form.BackColor = Drawing.Color.FromArgb(245, 245, 245)

    fmt = "%." + str(DECIMALS) + "f"

    lbl_info = WinForms.Label()
    lbl_info.Text = ("Coordinate reali:  X = " + (fmt % target_x) +
                     "    Y = " + (fmt % target_y) +
                     "    (tol = " + (fmt % tol) + ")")
    lbl_info.Font = Drawing.Font("Consolas", 10, Drawing.FontStyle.Bold)
    lbl_info.ForeColor = COLOR_POINTS
    lbl_info.Location = Drawing.Point(14, 12)
    lbl_info.Size = Drawing.Size(680, 22)
    form.Controls.Add(lbl_info)

    def fmt_src(lst, max_show=3):
        if not lst:
            return "-"
        if len(lst) <= max_show:
            return ", ".join(lst)
        return ", ".join(lst[:max_show]) + " (+%d)" % (len(lst) - max_show)

    src_info = "Sorgenti X: %s   |   Sorgenti Y: %s" % (
        fmt_src(src_x_list), fmt_src(src_y_list))
    if not src_x_list and not src_y_list:
        src_info = "Nessuna sorgente disponibile (fallback combinatorio)"

    lbl_src = WinForms.Label()
    lbl_src.Text = src_info
    lbl_src.Font = Drawing.Font("Consolas", 8)
    lbl_src.ForeColor = COLOR_NEUTRAL
    lbl_src.Location = Drawing.Point(14, 34)
    lbl_src.Size = Drawing.Size(680, 16)
    form.Controls.Add(lbl_src)

    lbl_x = WinForms.Label()
    lbl_x.Text = "Candidati per X:"
    lbl_x.Font = Drawing.Font("Segoe UI", 9, Drawing.FontStyle.Bold)
    lbl_x.Location = Drawing.Point(14, 54)
    lbl_x.Size = Drawing.Size(340, 20)
    form.Controls.Add(lbl_x)

    lst_x = WinForms.ListBox()
    lst_x.Font = Drawing.Font("Consolas", 9)
    lst_x.Location = Drawing.Point(14, 76)
    lst_x.Size = Drawing.Size(340, 310)
    if not matches_x:
        lst_x.Items.Add("(nessun match trovato)")
    for expr, val, delta, status in matches_x:
        lst_x.Items.Add("%-30s = %10s" % (expr, fmt % val))
    form.Controls.Add(lst_x)

    lbl_y = WinForms.Label()
    lbl_y.Text = "Candidati per Y:"
    lbl_y.Font = Drawing.Font("Segoe UI", 9, Drawing.FontStyle.Bold)
    lbl_y.Location = Drawing.Point(366, 54)
    lbl_y.Size = Drawing.Size(340, 20)
    form.Controls.Add(lbl_y)

    lst_y = WinForms.ListBox()
    lst_y.Font = Drawing.Font("Consolas", 9)
    lst_y.Location = Drawing.Point(366, 76)
    lst_y.Size = Drawing.Size(340, 310)
    if not matches_y:
        lst_y.Items.Add("(nessun match trovato)")
    for expr, val, delta, status in matches_y:
        lst_y.Items.Add("%-30s = %10s" % (expr, fmt % val))
    form.Controls.Add(lst_y)

    btn_use = WinForms.Button()
    btn_use.Text = "Usa selezione"
    btn_use.Font = Drawing.Font("Segoe UI", 9, Drawing.FontStyle.Bold)
    btn_use.BackColor = Drawing.Color.FromArgb(0, 100, 200)
    btn_use.ForeColor = Drawing.Color.White
    btn_use.FlatStyle = WinForms.FlatStyle.Flat
    btn_use.Location = Drawing.Point(500, 400)
    btn_use.Size = Drawing.Size(110, 28)
    btn_use.DialogResult = WinForms.DialogResult.OK
    form.Controls.Add(btn_use)
    form.AcceptButton = btn_use

    btn_close = WinForms.Button()
    btn_close.Text = "Chiudi"
    btn_close.Font = Drawing.Font("Segoe UI", 9)
    btn_close.Location = Drawing.Point(615, 400)
    btn_close.Size = Drawing.Size(90, 28)
    btn_close.DialogResult = WinForms.DialogResult.Cancel
    form.Controls.Add(btn_close)
    form.CancelButton = btn_close

    result = form.ShowDialog()
    if result != WinForms.DialogResult.OK:
        return None, None

    sel_x = ""
    sel_y = ""
    if lst_x.SelectedIndex >= 0 and matches_x:
        if lst_x.SelectedIndex < len(matches_x):
            sel_x = matches_x[lst_x.SelectedIndex][0]
    if lst_y.SelectedIndex >= 0 and matches_y:
        if lst_y.SelectedIndex < len(matches_y):
            sel_y = matches_y[lst_y.SelectedIndex][0]
    return sel_x, sel_y


# -----------------------------------------------------------------------------
def show_param_dialog(x, y, vars_dict, tol,
                      source_ex=None, source_ey=None,
                      sources_x=None, sources_y=None,
                      preset_ex="", preset_ey="", preset_note=""):
    """Dialogo di annotazione con validazione live."""
    fmt = "%." + str(DECIMALS) + "f"

    form = WinForms.Form()
    form.Text = "Annotazione Parametrica - Validazione Live"
    form.Width = 620
    form.Height = 380
    form.MinimumSize = Drawing.Size(620, 380)
    form.MaximumSize = Drawing.Size(620, 380)
    form.StartPosition = WinForms.FormStartPosition.CenterScreen
    form.FormBorderStyle = WinForms.FormBorderStyle.FixedDialog
    form.MaximizeBox = False
    form.MinimizeBox = False
    form.BackColor = Drawing.Color.FromArgb(245, 245, 245)

    lbl_title = WinForms.Label()
    lbl_title.Text = "Coordinate reali del punto"
    lbl_title.Font = Drawing.Font("Segoe UI", 9, Drawing.FontStyle.Bold)
    lbl_title.Location = Drawing.Point(14, 12)
    lbl_title.Size = Drawing.Size(580, 18)
    form.Controls.Add(lbl_title)

    panel_coords = WinForms.Panel()
    panel_coords.Location = Drawing.Point(12, 32)
    panel_coords.Size = Drawing.Size(586, 42)
    panel_coords.BackColor = Drawing.Color.White
    panel_coords.BorderStyle = WinForms.BorderStyle.FixedSingle
    form.Controls.Add(panel_coords)

    key_preview = make_point_key(x, y)
    lbl_coords = WinForms.Label()
    lbl_coords.Text = "  X = " + (fmt % x) + "        Y = " + (fmt % y) + "        " + key_preview
    lbl_coords.Font = Drawing.Font("Consolas", 10)
    lbl_coords.ForeColor = COLOR_POINTS
    lbl_coords.Location = Drawing.Point(4, 10)
    lbl_coords.Size = Drawing.Size(580, 22)
    panel_coords.Controls.Add(lbl_coords)

    var_summary = "  ".join(["%s=%g" % (n, vars_dict[n]) for n in VAR_NAMES])
    lbl_hint = WinForms.Label()
    lbl_hint.Text = "Variabili attive:  " + var_summary
    lbl_hint.Font = Drawing.Font("Consolas", 8)
    lbl_hint.ForeColor = COLOR_NEUTRAL
    lbl_hint.Location = Drawing.Point(14, 82)
    lbl_hint.Size = Drawing.Size(586, 18)
    form.Controls.Add(lbl_hint)

    lbl_x = WinForms.Label()
    lbl_x.Text = "X ="
    lbl_x.Font = Drawing.Font("Consolas", 10, Drawing.FontStyle.Bold)
    lbl_x.Location = Drawing.Point(14, 116)
    lbl_x.Size = Drawing.Size(36, 24)
    form.Controls.Add(lbl_x)

    txt_x = WinForms.TextBox()
    txt_x.Font = Drawing.Font("Consolas", 10)
    txt_x.Location = Drawing.Point(54, 114)
    txt_x.Size = Drawing.Size(260, 24)
    txt_x.Text = preset_ex
    form.Controls.Add(txt_x)

    lbl_x_feedback = WinForms.Label()
    lbl_x_feedback.Font = Drawing.Font("Consolas", 9, Drawing.FontStyle.Bold)
    lbl_x_feedback.Location = Drawing.Point(322, 117)
    lbl_x_feedback.Size = Drawing.Size(276, 22)
    lbl_x_feedback.Text = "(in attesa...)"
    lbl_x_feedback.ForeColor = COLOR_NEUTRAL
    form.Controls.Add(lbl_x_feedback)

    lbl_y = WinForms.Label()
    lbl_y.Text = "Y ="
    lbl_y.Font = Drawing.Font("Consolas", 10, Drawing.FontStyle.Bold)
    lbl_y.Location = Drawing.Point(14, 154)
    lbl_y.Size = Drawing.Size(36, 24)
    form.Controls.Add(lbl_y)

    txt_y = WinForms.TextBox()
    txt_y.Font = Drawing.Font("Consolas", 10)
    txt_y.Location = Drawing.Point(54, 152)
    txt_y.Size = Drawing.Size(260, 24)
    txt_y.Text = preset_ey
    form.Controls.Add(txt_y)

    lbl_y_feedback = WinForms.Label()
    lbl_y_feedback.Font = Drawing.Font("Consolas", 9, Drawing.FontStyle.Bold)
    lbl_y_feedback.Location = Drawing.Point(322, 155)
    lbl_y_feedback.Size = Drawing.Size(276, 22)
    lbl_y_feedback.Text = "(in attesa...)"
    lbl_y_feedback.ForeColor = COLOR_NEUTRAL
    form.Controls.Add(lbl_y_feedback)

    lbl_note = WinForms.Label()
    lbl_note.Text = "Etichetta / nota (opzionale, non concorre alla completezza):"
    lbl_note.Font = Drawing.Font("Segoe UI", 8)
    lbl_note.Location = Drawing.Point(14, 192)
    lbl_note.Size = Drawing.Size(400, 16)
    form.Controls.Add(lbl_note)

    txt_note = WinForms.TextBox()
    txt_note.Font = Drawing.Font("Segoe UI", 9)
    txt_note.Location = Drawing.Point(14, 210)
    txt_note.Size = Drawing.Size(584, 22)
    txt_note.Text = preset_note
    form.Controls.Add(txt_note)

    state = {"sx": "empty", "sy": "empty"}

    def update_feedback(txt_box, lbl_feedback, target_val, which):
        expr = txt_box.Text
        if not expr.strip():
            lbl_feedback.Text = "(in attesa...)"
            lbl_feedback.ForeColor = COLOR_NEUTRAL
            state[which] = "empty"
            return
        val, err = safe_eval(expr, vars_dict)
        if err is not None:
            lbl_feedback.Text = "ERRORE: " + err
            lbl_feedback.ForeColor = COLOR_ERR
            state[which] = "err"
            return
        status, delta = compare_value(val, target_val, tol)
        if status == "ok":
            lbl_feedback.Text = "OK   = " + (fmt % val) + "  (d=" + (fmt % delta) + ")"
            lbl_feedback.ForeColor = COLOR_OK
        elif status == "approx":
            lbl_feedback.Text = "~    = " + (fmt % val) + "  (d=" + (fmt % delta) + ")"
            lbl_feedback.ForeColor = COLOR_APPROX
        else:
            lbl_feedback.Text = "NO   = " + (fmt % val) + "  (d=" + (fmt % delta) + ")"
            lbl_feedback.ForeColor = COLOR_ERR
        state[which] = status

    def on_x_changed(sender, e):
        update_feedback(txt_x, lbl_x_feedback, x, "sx")

    def on_y_changed(sender, e):
        update_feedback(txt_y, lbl_y_feedback, y, "sy")

    txt_x.TextChanged += on_x_changed
    txt_y.TextChanged += on_y_changed

    if preset_ex:
        update_feedback(txt_x, lbl_x_feedback, x, "sx")
    if preset_ey:
        update_feedback(txt_y, lbl_y_feedback, y, "sy")

    btn_suggest = WinForms.Button()
    btn_suggest.Text = "Suggerisci..."
    btn_suggest.Font = Drawing.Font("Segoe UI", 9)
    btn_suggest.Location = Drawing.Point(14, 308)
    btn_suggest.Size = Drawing.Size(110, 28)
    form.Controls.Add(btn_suggest)

    def on_suggest(sender, e):
        sx, sy = show_suggest_dialog(x, y, vars_dict, tol,
                                     sources_x=sources_x, sources_y=sources_y,
                                     source_ex=source_ex, source_ey=source_ey)
        if sx is not None and sx:
            txt_x.Text = sx
        if sy is not None and sy:
            txt_y.Text = sy

    btn_suggest.Click += on_suggest

    btn_ok = WinForms.Button()
    btn_ok.Text = "Conferma"
    btn_ok.Font = Drawing.Font("Segoe UI", 9, Drawing.FontStyle.Bold)
    btn_ok.BackColor = Drawing.Color.FromArgb(0, 100, 200)
    btn_ok.ForeColor = Drawing.Color.White
    btn_ok.FlatStyle = WinForms.FlatStyle.Flat
    btn_ok.Location = Drawing.Point(330, 308)
    btn_ok.Size = Drawing.Size(100, 28)
    btn_ok.DialogResult = WinForms.DialogResult.OK
    form.Controls.Add(btn_ok)
    form.AcceptButton = btn_ok

    btn_skip = WinForms.Button()
    btn_skip.Text = "Salta"
    btn_skip.Font = Drawing.Font("Segoe UI", 9)
    btn_skip.Location = Drawing.Point(440, 308)
    btn_skip.Size = Drawing.Size(70, 28)
    btn_skip.DialogResult = WinForms.DialogResult.Ignore
    form.Controls.Add(btn_skip)

    btn_cancel = WinForms.Button()
    btn_cancel.Text = "Annulla tutto"
    btn_cancel.Font = Drawing.Font("Segoe UI", 9)
    btn_cancel.ForeColor = Drawing.Color.FromArgb(180, 30, 30)
    btn_cancel.Location = Drawing.Point(520, 308)
    btn_cancel.Size = Drawing.Size(78, 28)
    btn_cancel.DialogResult = WinForms.DialogResult.Cancel
    form.Controls.Add(btn_cancel)
    form.CancelButton = btn_cancel

    txt_x.Select()
    if preset_ex:
        txt_x.SelectionStart = len(preset_ex)

    result = form.ShowDialog()

    if result == WinForms.DialogResult.OK:
        return (txt_x.Text.strip(), txt_y.Text.strip(),
                txt_note.Text.strip(), state["sx"], state["sy"])
    elif result == WinForms.DialogResult.Ignore:
        return "", "", "", "empty", "empty"
    else:
        return None, None, None, None, None


# -----------------------------------------------------------------------------
def build_dot_text(x, y, ex, ey, note, status_x, status_y):
    fmt = "%." + str(DECIMALS) + "f"
    lines = []
    if note:
        lines.append("[ " + note + " ]")
    mark_x = ""
    if status_x == "ok":       mark_x = " OK"
    elif status_x == "approx": mark_x = " ~"
    elif status_x == "err":    mark_x = " !"
    mark_y = ""
    if status_y == "ok":       mark_y = " OK"
    elif status_y == "approx": mark_y = " ~"
    elif status_y == "err":    mark_y = " !"

    lines.append("X = " + (fmt % x) + mark_x)
    if ex:
        lines.append("    ( " + ex + " )")
    lines.append("Y = " + (fmt % y) + mark_y)
    if ey:
        lines.append("    ( " + ey + " )")
    return "\n".join(lines)


# -----------------------------------------------------------------------------
#  SOVRASCRITTURA - basata sulla chiave geometrica
# -----------------------------------------------------------------------------
def find_existing_by_key(point_key, dot_key, tol):
    """Cerca punto e textdot esistenti con la chiave geometrica data."""
    idx_pts  = sc.doc.Layers.FindByFullPath(LAYER_POINTS, -1)
    idx_dots = sc.doc.Layers.FindByFullPath(LAYER_DOTS,   -1)

    found_pt = None
    found_dot = None
    preset = {"X_param": "", "Y_param": "", "Nota": ""}

    m = re.match(r"^PKG_X([+-])(\d+)_Y([+-])(\d+)$", point_key)
    if m:
        kx = int(m.group(2)) * (1 if m.group(1) == "+" else -1)
        ky = int(m.group(4)) * (1 if m.group(3) == "+" else -1)
    else:
        kx, ky = None, None

    tol_match = max(tol, 0.001) + 0.5

    for obj in sc.doc.Objects:
        if obj.IsDeleted:
            continue
        layer_idx = obj.Attributes.LayerIndex
        name = obj.Attributes.Name or ""

        if layer_idx == idx_pts and isinstance(obj.Geometry, Rhino.Geometry.Point):
            hit = False
            if name == point_key:
                hit = True
            elif kx is not None:
                p = obj.Geometry.Location
                if abs(p.X - kx) <= tol_match and abs(p.Y - ky) <= tol_match:
                    hit = True
            if hit and found_pt is None:
                found_pt = obj
                preset["X_param"] = obj.Attributes.GetUserString("X_param") or ""
                preset["Y_param"] = obj.Attributes.GetUserString("Y_param") or ""
                preset["Nota"]    = obj.Attributes.GetUserString("Nota") or ""
                if preset["X_param"] == "--": preset["X_param"] = ""
                if preset["Y_param"] == "--": preset["Y_param"] = ""

        elif layer_idx == idx_dots and isinstance(obj.Geometry, Rhino.Geometry.TextDot):
            hit = False
            if name == dot_key:
                hit = True
            elif kx is not None:
                p = obj.Geometry.Point
                expected_x = kx + DOT_OFFSET_X
                expected_y = ky + DOT_OFFSET_Y
                if abs(p.X - expected_x) <= tol_match and abs(p.Y - expected_y) <= tol_match:
                    hit = True
            if hit and found_dot is None:
                found_dot = obj

    return found_pt, found_dot, preset


def delete_existing(point_obj, dot_obj):
    """Cancella un Point e un TextDot precedentemente trovati."""
    n = 0
    if point_obj is not None:
        if sc.doc.Objects.Delete(point_obj.Id, True):
            n += 1
    if dot_obj is not None:
        if sc.doc.Objects.Delete(dot_obj.Id, True):
            n += 1
    return n


# -----------------------------------------------------------------------------
#  SPECCHIA CURVE TAGGATE (Punto 3 v4.2)
# -----------------------------------------------------------------------------
def _object_userstrings(obj):
    """Lista [(key, value), ...] di tutte le UserString dell'oggetto."""
    out = []
    try:
        coll = obj.Attributes.GetUserStrings()
    except Exception:
        coll = None
    if coll is not None:
        try:
            keys = list(coll.AllKeys)
        except Exception:
            keys = []
        for k in keys:
            if k is None:
                continue
            v = coll.Get(k)
            if v:
                out.append((k, v))
    return out


def _is_cyan(obj):
    """True se il colore di visualizzazione dell'oggetto e' ciano (0,255,255),
    con tolleranza (R basso, G e B alti). Risolve anche il colore ByLayer."""
    c = None
    try:
        c = obj.Attributes.DrawColor(sc.doc)
    except Exception:
        try:
            c = obj.Attributes.ObjectColor
        except Exception:
            return False
    if c is None:
        return False
    return (c.R <= 80) and (c.G >= 160) and (c.B >= 160)


def mirror_transform_for_curve(crv):
    """Costruisce il Transform di mirror rispetto alla retta definita dalla
    curva 'crv' (usa start/end). Il piano di mirror contiene la linea e l'asse
    Z del mondo (lavoro 2D in XY: il riflesso e' sul lato opposto della linea).
    Ritorna None se la linea e' degenere o verticale rispetto a Z."""
    p0 = crv.PointAtStart
    p1 = crv.PointAtEnd
    d = p1 - p0
    if d.Length < 1e-9:
        return None
    if not d.Unitize():
        return None
    up = Rhino.Geometry.Vector3d.ZAxis
    normal = Rhino.Geometry.Vector3d.CrossProduct(d, up)
    if normal.Length < 1e-9:
        return None
    if not normal.Unitize():
        return None
    return Rhino.Geometry.Transform.Mirror(p0, normal)


def mirror_tagged_curves(tol):
    """Specchia gruppi di curve lungo le rispettive linee di proiezione.

      - CURVE da specchiare: UserString con CHIAVE (o valore, o Nome) "Proietta
        su X" -- nella convenzione d'uso il tag e' nella CHIAVE con valore vuoto.
      - LINEA di proiezione: colore CIANO, con CHIAVE (o valore, o Nome) "X".

    Ogni curva "Proietta su X" e' specchiata sulla linea cyan "X". Il duplicato
    eredita gli attributi (layer, ecc.); il tag "Proietta su X" viene RIMOSSO e
    sostituito da "Specchiato da X" per evitare un nuovo mirror successivo.

    Robustezza (v4.2): l'asse e' accettato solo se la sua etichetta coincide
    ESATTAMENTE con una realmente referenziata da una "Proietta su X". Cosi' le
    chiavi di pipeline (Status, Comando, P1_id, ...) non vengono mai scambiate
    per assi. Il mirror e' una riflessione 2D rispetto alla retta della linea
    cyan: vale per QUALSIASI orientamento (orizzontale, verticale, obliquo).
    """
    # Chiavi del pipeline da NON confondere con un'etichetta d'asse.
    reserved = set([
        "X_REALE", "Y_REALE", "X_PARAM", "Y_PARAM", "X_STATUS", "Y_STATUS",
        "P1_ID", "P2_ID", "P1_PARAM", "P2_PARAM", "STATUS", "COMANDO",
        "LUNGHEZZA", "TIPO_ORIGINALE", "SEQID", "NOME", "LAYER",
    ])

    axes = {}              # LABEL -> curve_geo (linea di proiezione cyan)
    axis_seen_twice = set()
    to_mirror = []         # (obj, geo, LABEL, src_key)
    cyan_curves = []       # (obj, geo, us, name) da risolvere dopo
    valid_labels = set()   # etichette REALMENTE referenziate da "Proietta su X"

    def _find_proietta(us, name):
        """Cerca 'Proietta su X' tra CHIAVI e VALORI delle UserString e nel
        Nome. Ritorna (LABEL_upper, storage_key) oppure (None, None)."""
        for k, v in us:
            for field in (k, v):
                if not field:
                    continue
                m = _PROIETTA_RE.match(field.strip())
                if m:
                    return m.group(1).strip().upper(), k
        if name:
            m = _PROIETTA_RE.match(name.strip())
            if m:
                return m.group(1).strip().upper(), "__name__"
        return None, None

    for obj in sc.doc.Objects:
        if obj.IsDeleted:
            continue
        geo = obj.Geometry
        if not isinstance(geo, Rhino.Geometry.Curve):
            continue

        us = _object_userstrings(obj)
        name = obj.Attributes.Name or ""

        # 1) Curva da specchiare? "Proietta su X" su chiave/valore/Nome.
        proj_label, proj_key = _find_proietta(us, name)
        if proj_label:
            to_mirror.append((obj, geo, proj_label, proj_key))
            valid_labels.add(proj_label)
            continue  # una "Proietta su" non e' anche un asse

        # 2) Possibile asse cyan: risolto dopo, contro valid_labels.
        if _is_cyan(obj):
            cyan_curves.append((obj, geo, us, name))

    # --- risoluzione assi: solo linee cyan la cui CHIAVE/valore/Nome coincide
    #     ESATTAMENTE con un'etichetta referenziata. ---
    for obj, geo, us, name in cyan_curves:
        lab = None
        for k, v in us:
            for field in (k, v):
                if not field:
                    continue
                f = field.strip().upper()
                if f and f not in reserved and f in valid_labels:
                    lab = f
                    break
            if lab:
                break
        if lab is None and name and name.strip().upper() in valid_labels:
            lab = name.strip().upper()
        if lab:
            if lab in axes:
                axis_seen_twice.add(lab)
            else:
                axes[lab] = geo

    # --- nessuna curva taggata: avvisa e termina ---
    if not to_mirror:
        WinForms.MessageBox.Show(
            "Nessuna curva con tag 'Proietta su <etichetta>' trovata.\n\n"
            "Assegna alle curve da specchiare una UserString con CHIAVE\n"
            "'Proietta su A' (o B, C...) e disegna la linea di proiezione in\n"
            "colore CIANO con UserString di CHIAVE 'A' (o B, C...).",
            "Specchia curve taggate",
            WinForms.MessageBoxButtons.OK,
            WinForms.MessageBoxIcon.Information)
        return

    # --- applica il mirror ---
    created = 0
    new_ids = []
    unmatched = []

    for obj, geo, label, src_key in to_mirror:
        if label not in axes:
            unmatched.append(label)
            continue
        xform = mirror_transform_for_curve(axes[label])
        if xform is None:
            unmatched.append(label)
            continue
        dup = geo.DuplicateCurve()
        if dup is None:
            continue
        if not dup.Transform(xform):
            continue
        attr = obj.Attributes.Duplicate()   # Duplicate() richiesto da RhinoCommon
        if src_key == "__name__":
            attr.Name = ""
        elif src_key is not None:
            # Con il tag sulla CHIAVE, cambiarne il valore non basta: la chiave
            # 'Proietta su X' continuerebbe a combaciare e la curva verrebbe
            # ri-specchiata. La si RIMUOVE: passare None a SetUserString cancella
            # la UserString in RhinoCommon.
            attr.SetUserString(src_key, None)
        # Marcatore anti ri-mirror con valore NON vuoto (un valore vuoto sarebbe
        # rimosso da RhinoCommon).
        attr.SetUserString("Specchiato da %s" % label, "si")
        new_id = sc.doc.Objects.AddCurve(dup, attr)
        if new_id != System.Guid.Empty:
            created += 1
            new_ids.append(new_id)

    if new_ids:
        sc.doc.Objects.UnselectAll()
        for nid in new_ids:
            sc.doc.Objects.Select(nid)
    sc.doc.Views.Redraw()

    # --- report ---
    msg = "Specchiate %d curva/e su %d totali." % (created, len(to_mirror))
    if unmatched:
        uniq = sorted(set(unmatched))
        msg += ("\n\nEtichette senza linea di proiezione cyan corrispondente:\n  "
                + ", ".join(uniq))
    if axis_seen_twice:
        msg += ("\n\nEtichette con piu' di una linea cyan (usata la prima):\n  "
                + ", ".join(sorted(axis_seen_twice)))
    print "PKG Annotator v4.2 - mirror: %d/%d curve specchiate." % (
        created, len(to_mirror))
    WinForms.MessageBox.Show(msg, "Specchia curve taggate",
                             WinForms.MessageBoxButtons.OK,
                             WinForms.MessageBoxIcon.Information)


# =============================================================================
#  QUOTE-FUNZIONE (v4.3): lettura LinearDimension con testo sovrascritto
# =============================================================================
def _dim_info(obj, tol):
    """Estrae da una LinearDimension: punti di definizione (mondo), asse di
    misura ('X' orizzontale, 'Y' verticale, 'D' obliqua) e testo sovrascritto.
    Ritorna dict oppure None se non e' una quota-funzione utilizzabile."""
    geo = obj.Geometry
    if not isinstance(geo, Rhino.Geometry.LinearDimension):
        return None
    try:
        txt = (geo.PlainText or "").strip()
    except Exception, ex:
        return None
    if not txt:
        return None
    # Niente lettere di variabile -> quota normale (numero), non ci riguarda.
    has_var = False
    for n in VAR_NAMES:
        if n in txt:
            has_var = True
            break
    if not has_var:
        return None
    try:
        e1 = geo.ExtensionLine1End
        e2 = geo.ExtensionLine2End
        pl = geo.Plane
        p1 = pl.PointAt(e1.X, e1.Y)
        p2 = pl.PointAt(e2.X, e2.Y)
        d = pl.XAxis     # direzione di misura della quota
    except Exception, ex:
        return None
    ax = "D"
    if abs(d.Y) <= 1e-9 and abs(d.Z) <= 1e-9:
        ax = "X"
    elif abs(d.X) <= 1e-9 and abs(d.Z) <= 1e-9:
        ax = "Y"
    return {"p1": p1, "p2": p2, "axis": ax, "text": txt, "id": obj.Id}


def _nkey(x, y):
    return (round(x, 6), round(y, 6))


def collect_quote_constraints(objs, tol):
    """Dalle quote selezionate ricava:
      var_defs   - {nome: valore} dalle quote il cui testo E' un nome variabile.
                   Con quote discordi vince il valore PIU' FREQUENTE (voto di
                   maggioranza), non il primo letto: una singola quota sbagliata
                   non deve dettare il valore.
      conflicts  - [(nome, [(valore, occorrenze), ...])] per le variabili con
                   quote discordi, ordinati per frequenza decrescente
      constraints- vincoli (k1, k2, axis, formula, p1, p2)
    """
    var_votes = {}
    constraints = []
    for obj in objs:
        info = _dim_info(obj, tol)
        if info is None:
            continue
        p1, p2, ax, txt = info["p1"], info["p2"], info["axis"], info["text"]
        if ax == "X":
            measured = abs(p2.X - p1.X)
        elif ax == "Y":
            measured = abs(p2.Y - p1.Y)
        else:
            measured = p1.DistanceTo(p2)
        if txt in VAR_NAMES and ax != "D":
            # quota di DEFINIZIONE: il testo e' il nome della variabile.
            # Solo quote ORTOGONALI: un'obliqua misurerebbe la diagonale
            # (es. 'E' sul bisellino a 45 gradi = E*1.414) e inquinerebbe
            # il valore. Le oblique con nome-variabile restano vincoli.
            v = round(measured, DECIMALS)
            if txt not in var_votes:
                var_votes[txt] = {}
            var_votes[txt][v] = var_votes[txt].get(v, 0) + 1
            # una definizione e' anche un vincolo: la si tiene
        constraints.append((_nkey(p1.X, p1.Y), _nkey(p2.X, p2.Y),
                            ax, txt, p1, p2))

    var_defs = {}
    conflicts = []
    for name in var_votes:
        votes = sorted(var_votes[name].items(),
                       key=lambda t: (-t[1], -t[0]))   # frequenza, poi valore
        var_defs[name] = votes[0][0]
        if len(votes) > 1:
            conflicts.append((name, votes))
    return var_defs, conflicts, constraints


def _chain_formula(known, f, positive):
    """Costruisce 'known +/- f' avvolgendo f tra parentesi se ha piu' termini,
    e ripulisce le cancellazioni di facciata."""
    ftxt = f.strip()
    if len(split_top_level_terms(ftxt)) > 1:
        ftxt = "(" + ftxt + ")"
    if known == "0":
        expr = ("" if positive else "-") + ftxt
    else:
        expr = known + ("+" if positive else "-") + ftxt
    return simplify_display(expr)


def propagate_quotes(constraints, vars_dict, tol):
    """Propaga le formule lungo il grafo delle quote, con VERIFICA numerica a
    ogni passo (stessa compare_value dell'inserimento punti).

    Ancore: punti gia' annotati (X_param/Y_param) e coordinate a 0.
    Regole:
      - quota X tra A e B: se X(A) nota -> X(B) = X(A) +/- formula, assegnata
        SOLO se il valore ricalcolato coincide con la coordinata reale;
      - se i due punti sono sulla stessa riga (dY~0), la Y si COPIA (e
        simmetricamente la X sulle quote Y in colonna);
      - ogni quota e' comunque verificata: |misura| vs |formula|; se non
        tornano viene segnalata e NON propaga;
      - quote oblique ('D'): solo verifica della distanza, niente propagazione.
    Ritorna (nodes, n_verified, bad) dove nodes = {key: [x, y, ex, ey]}.
    """
    nodes = {}     # key -> [x, y, ex, ey]
    X = {}
    Y = {}

    def ensure(k, x, y):
        if k not in nodes:
            nodes[k] = [x, y, None, None]

    # --- semi: punti annotati esistenti + coordinate a zero ---
    idx = sc.doc.Layers.FindByFullPath(LAYER_POINTS, -1)
    if idx >= 0:
        for obj in sc.doc.Objects:
            if obj.IsDeleted or obj.Attributes.LayerIndex != idx:
                continue
            if not isinstance(obj.Geometry, Rhino.Geometry.Point):
                continue
            p = obj.Geometry.Location
            k = _nkey(p.X, p.Y)
            ex = obj.Attributes.GetUserString("X_param") or ""
            ey = obj.Attributes.GetUserString("Y_param") or ""
            if ex and ex != "--":
                X[k] = ex
            if ey and ey != "--":
                Y[k] = ey

    for (k1, k2, ax, f, p1, p2) in constraints:
        ensure(k1, p1.X, p1.Y)
        ensure(k2, p2.X, p2.Y)
    for k in nodes:
        if abs(nodes[k][0]) <= tol and k not in X:
            X[k] = "0"
        if abs(nodes[k][1]) <= tol and k not in Y:
            Y[k] = "0"

    bad = []
    bad_keys = set()
    n_verified = 0
    verified_once = set()

    def _propagate(coordmap, k1, k2, f, real, c1, c2):
        """Propaga lungo un asse: se la coordinata e' nota a un estremo,
        incatena 'nota +/- f' e assegna SOLO se il ricalcolo coincide con la
        coordinata reale dell'altro estremo. Ritorna True se cambia."""
        if k1 in coordmap and k2 not in coordmap:
            expr = _chain_formula(coordmap[k1], f, real > 0)
            val, e2 = safe_eval(expr, vars_dict)
            if e2 is None and val is not None:
                okp, _ = compare_value(val, c2, tol)
                if okp == "ok":
                    coordmap[k2] = expr
                    return True
        elif k2 in coordmap and k1 not in coordmap:
            expr = _chain_formula(coordmap[k2], f, real < 0)
            val, e2 = safe_eval(expr, vars_dict)
            if e2 is None and val is not None:
                okp, _ = compare_value(val, c1, tol)
                if okp == "ok":
                    coordmap[k1] = expr
                    return True
        return False

    def _copy(coordmap, k1, k2):
        """Coordinata condivisa (delta ~0): si copia attraverso la quota."""
        if k1 in coordmap and k2 not in coordmap:
            coordmap[k2] = coordmap[k1]
            return True
        if k2 in coordmap and k1 not in coordmap:
            coordmap[k1] = coordmap[k2]
            return True
        return False

    changed = True
    while changed:
        changed = False
        for (k1, k2, ax, f, p1, p2) in constraints:
            fv, err = safe_eval(f, vars_dict)
            qid = (k1, k2, ax, f)
            if err is not None or fv is None:
                if qid not in bad_keys:
                    bad_keys.add(qid)
                    bad.append((ax, f, p1, p2, "formula non valutabile: %s" % err))
                continue
            x1, y1 = nodes[k1][0], nodes[k1][1]
            x2, y2 = nodes[k2][0], nodes[k2][1]
            rx = x2 - x1
            ry = y2 - y1

            do_x = False
            do_y = False
            if ax == "X":
                okv, _ = compare_value(abs(fv), abs(rx), tol)
                if okv != "ok":
                    if qid not in bad_keys:
                        bad_keys.add(qid)
                        bad.append((ax, f, p1, p2,
                                    "misura %.4f != formula %.4f" % (abs(rx), abs(fv))))
                    continue
                do_x = True
            elif ax == "Y":
                okv, _ = compare_value(abs(fv), abs(ry), tol)
                if okv != "ok":
                    if qid not in bad_keys:
                        bad_keys.add(qid)
                        bad.append((ax, f, p1, p2,
                                    "misura %.4f != formula %.4f" % (abs(ry), abs(fv))))
                    continue
                do_y = True
            else:
                # QUOTA OBLIQUA: la formula puo' descrivere la distanza pura
                # OPPURE una porzione parziale lungo X e/o Y (caso tipico: il
                # bisellino a 45 gradi quotato 'E', dove dX = dY = E).
                dist = p1.DistanceTo(p2)
                okd, _ = compare_value(abs(fv), dist, tol)
                okx, _ = compare_value(abs(fv), abs(rx), tol)
                oky, _ = compare_value(abs(fv), abs(ry), tol)
                if okx == "ok":
                    do_x = True
                if oky == "ok":
                    do_y = True
                if not do_x and not do_y:
                    if okd == "ok":
                        # distanza pura: SOLO verifica, niente propagazione
                        if qid not in verified_once:
                            verified_once.add(qid)
                            n_verified += 1
                        continue
                    if qid not in bad_keys:
                        bad_keys.add(qid)
                        bad.append((ax, f, p1, p2,
                                    "dist %.4f, dX %.4f, dY %.4f != formula %.4f"
                                    % (dist, abs(rx), abs(ry), abs(fv))))
                    continue

            if qid not in verified_once:
                verified_once.add(qid)
                n_verified += 1

            if do_x:
                changed = _propagate(X, k1, k2, f, rx, x1, x2) or changed
                if abs(ry) <= tol:             # stessa riga: la Y si copia
                    changed = _copy(Y, k1, k2) or changed
            if do_y:
                changed = _propagate(Y, k1, k2, f, ry, y1, y2) or changed
                if abs(rx) <= tol:             # stessa colonna: la X si copia
                    changed = _copy(X, k1, k2) or changed

    for k in nodes:
        nodes[k][2] = X.get(k)
        nodes[k][3] = Y.get(k)
    return nodes, n_verified, bad


def apply_quote_points(nodes, vars_dict, tol, idx_pts, idx_dots):
    """Crea i punti annotati derivati dalle quote. SOLO i punti COMPLETI
    (X_param e Y_param entrambe note): un punto mezzo vuoto non e' conosciuto
    parametricamente e non va inserito. Non tocca i punti gia' esistenti
    (che fanno da ancore). Ritorna (creati, gia_presenti, incompleti)."""
    existing = set()
    if idx_pts >= 0:
        for obj in sc.doc.Objects:
            if obj.IsDeleted or obj.Attributes.LayerIndex != idx_pts:
                continue
            if not isinstance(obj.Geometry, Rhino.Geometry.Point):
                continue
            p = obj.Geometry.Location
            existing.add(_nkey(p.X, p.Y))

    created = 0
    skipped = 0
    incomplete = 0
    for k in sorted(nodes.keys()):
        x, y, ex, ey = nodes[k]
        if ex is None and ey is None:
            continue                  # nodo mai raggiunto: non conta
        if k in existing:
            skipped += 1
            continue
        if not ex or not ey:
            incomplete += 1           # raggiunto a meta': NON si crea
            continue
        pt = Point3d(x, y, 0.0)
        point_key = make_point_key(x, y)
        dot_key = make_dot_key(x, y)
        prov = create_provisional_point(pt, point_key, idx_pts)
        finalize_point(prov, point_key, x, y, ex, ey, "ok", "ok", "da quota")
        dot_text = build_dot_text(x, y, ex, ey, "da quota", "ok", "ok")
        pt_dot = Point3d(x + DOT_OFFSET_X, y + DOT_OFFSET_Y, 0.0)
        td = TextDot(dot_text, pt_dot)
        td.FontHeight = DOT_HEIGHT
        td.FontFace = DOT_FONT
        attr_dot = Rhino.DocObjects.ObjectAttributes()
        attr_dot.LayerIndex = idx_dots
        attr_dot.ColorSource = Rhino.DocObjects.ObjectColorSource.ColorFromObject
        attr_dot.ObjectColor = COLOR_DOT_COMPLETE
        attr_dot.Name = dot_key
        sc.doc.Objects.AddTextDot(td, attr_dot)
        created += 1
    return created, skipped, incomplete


def certain_formulas_for(pt, quote_nodes, tol):
    """Formule CERTE (100%) per PRECOMPILARE il dialog al clic di un punto.
    Ritorna (ex, ey), ciascuna None se non c'e' certezza per quell'asse.

    Fonti, in ordine di forza:
      1. coordinata a zero -> "0";
      2. nodo del grafo QUOTE coincidente col punto cliccato: la formula e'
         dichiarata dalle quote e gia' verificata in propagazione (e' qui che
         i nodi 'raggiunti a meta'' tornano utili: non creati come punti, ma
         pronti a precompilare il loro asse al clic);
      3. copia da un punto annotato ESATTAMENTE allineato e con stato 'ok'
         (stessa colonna -> X, stessa riga -> Y): coordinata identica,
         formula identica. Si prende il piu' vicino.
    Tutto cio' che non e' certo resta ai suggerimenti: qui niente euristica.
    """
    ex = None
    ey = None
    if abs(pt.X) <= tol:
        ex = "0"
    if abs(pt.Y) <= tol:
        ey = "0"

    # 2) nodo quote coincidente
    if quote_nodes and (ex is None or ey is None):
        for k in quote_nodes:
            nx, ny, nex, ney = quote_nodes[k]
            if abs(nx - pt.X) <= tol and abs(ny - pt.Y) <= tol:
                if ex is None and nex:
                    ex = nex
                if ey is None and ney:
                    ey = ney
                break

    if ex is not None and ey is not None:
        return ex, ey

    # 3) copia da punti annotati allineati (solo stato 'ok')
    idx = sc.doc.Layers.FindByFullPath(LAYER_POINTS, -1)
    if idx >= 0:
        best_dx = None   # distanza lungo Y del miglior allineato in colonna
        best_dy = None   # distanza lungo X del miglior allineato in riga
        cand_ex = None
        cand_ey = None
        for obj in sc.doc.Objects:
            if obj.IsDeleted or obj.Attributes.LayerIndex != idx:
                continue
            if not isinstance(obj.Geometry, Rhino.Geometry.Point):
                continue
            p = obj.Geometry.Location
            dx = abs(p.X - pt.X)
            dy = abs(p.Y - pt.Y)
            if dx <= tol and dy <= tol:
                continue   # punto coincidente: e' il caso sovrascrittura
            if ex is None and dx <= tol:
                e = obj.Attributes.GetUserString("X_param") or ""
                s = obj.Attributes.GetUserString("X_status") or ""
                if e and e != "--" and s == "ok":
                    if best_dx is None or dy < best_dx:
                        best_dx = dy
                        cand_ex = e
            if ey is None and dy <= tol:
                e = obj.Attributes.GetUserString("Y_param") or ""
                s = obj.Attributes.GetUserString("Y_status") or ""
                if e and e != "--" and s == "ok":
                    if best_dy is None or dx < best_dy:
                        best_dy = dx
                        cand_ey = e
        if ex is None and cand_ex:
            ex = cand_ex
        if ey is None and cand_ey:
            ey = cand_ey

    return ex, ey


def show_quote_report(var_defs, conflicts, n_constraints, n_verified, bad,
                      created, skipped, incomplete):
    lines = ["QUOTE-FUNZIONE - rapporto", ""]
    if var_defs:
        defs = ", ".join("%s=%g" % (n, var_defs[n]) for n in sorted(var_defs))
        lines.append("Variabili definite dalle quote: " + defs)
    if conflicts:
        lines.append("QUOTE DI DEFINIZIONE DISCORDI (usato il valore piu' frequente):")
        for (n, votes) in conflicts:
            vt = ", ".join("%g (x%d)" % (v, c) for (v, c) in votes)
            lines.append("  %s: %s" % (n, vt))
    lines.append("Vincoli letti: %d  -  verificati: %d" % (n_constraints, n_verified))
    lines.append("Punti creati (completi): %d  -  gia' presenti: %d" % (created, skipped))
    if incomplete:
        lines.append("Punti raggiunti solo a meta' (NON creati): %d" % incomplete)
        lines.append("  (manca una quota o un'ancora sull'altro asse)")
    if bad:
        lines.append("")
        lines.append("QUOTE NON CONFORMI (segnalate, non propagate):")
        for (ax, f, p1, p2, why) in bad:
            lines.append("  [%s] '%s'  (%.1f,%.1f)->(%.1f,%.1f): %s" % (
                ax, f, p1.X, p1.Y, p2.X, p2.Y, why))
    msg = "\n".join(lines)
    if bad or conflicts:
        icon = WinForms.MessageBoxIcon.Warning
    else:
        icon = WinForms.MessageBoxIcon.Information
    WinForms.MessageBox.Show(msg, "PKG Annotator - quote", 
                             WinForms.MessageBoxButtons.OK, icon)


def show_help_dialog():
    """Avvio SENZA selezione: mostra l'help. Ritorna True per continuare con
    la sessione classica punto-per-punto, False per uscire."""
    msg = (
        "PKG ANNOTATOR v4.3 - guida rapida\n\n"
        "AVVIO CON SELEZIONE (consigliato):\n"
        "  Seleziona le QUOTE-funzione (e le geometrie) PRIMA di avviare.\n"
        "  - Quota con testo = nome variabile (L, P, A, S, C, T, E):\n"
        "      DEFINISCE il valore della variabile (precompila il dialog).\n"
        "  - Quota con testo = formula (es. (P/2), L+S):\n"
        "      DICHIARA la relazione tra i due punti quotati. Lo script la\n"
        "      VERIFICA sulle coordinate reali e, partendo dalle ancore\n"
        "      (punti gia' annotati e coordinate a 0), PROPAGA le formule\n"
        "      creando i punti annotati. Le quote che non tornano vengono\n"
        "      segnalate e non propagano.\n"
        "  Quote orizzontali -> vincolano la X; verticali -> la Y.\n"
        "  Quote OBLIQUE: se la formula corrisponde alla distanza -> solo\n"
        "  verifica; se corrisponde a dX e/o dY (es. 'E' sul bisellino a 45\n"
        "  gradi, dove dX = dY = E) -> propaga su quegli assi.\n\n"
        "AVVIO SENZA SELEZIONE: questa guida, poi (se Continua) la sessione\n"
        "classica: clic su un punto, suggerimento di X_param/Y_param dai\n"
        "vicini annotati, conferma, TextDot quotato. Opzioni nel prompt:\n"
        "SpecchiaCurve (mirror su linee cyan taggate), Invio per terminare.\n\n"
        "Continuare con la sessione punto-per-punto?")
    r = WinForms.MessageBox.Show(msg, "PKG Annotator - help",
                                 WinForms.MessageBoxButtons.YesNo,
                                 WinForms.MessageBoxIcon.Information)
    return r == WinForms.DialogResult.Yes


# -----------------------------------------------------------------------------
def show_summary_dialog(records):
    if not records:
        return

    form = WinForms.Form()
    form.Text = "Riepilogo sessione - PKG Annotator v4.2"
    form.Width = 780
    form.Height = 480
    form.StartPosition = WinForms.FormStartPosition.CenterScreen
    form.BackColor = Drawing.Color.FromArgb(245, 245, 245)

    counts = {"ok": 0, "approx": 0, "err": 0, "empty": 0}
    for r in records:
        counts[r["sx"]] = counts.get(r["sx"], 0) + 1
        counts[r["sy"]] = counts.get(r["sy"], 0) + 1

    lbl_stats = WinForms.Label()
    lbl_stats.Text = ("Punti: %d   |   OK: %d   Approx: %d   Errori: %d   Vuoti: %d" % (
        len(records), counts["ok"], counts["approx"], counts["err"], counts["empty"]))
    lbl_stats.Font = Drawing.Font("Segoe UI", 9, Drawing.FontStyle.Bold)
    lbl_stats.Location = Drawing.Point(14, 12)
    lbl_stats.Size = Drawing.Size(740, 22)
    form.Controls.Add(lbl_stats)

    grid = WinForms.DataGridView()
    grid.Location = Drawing.Point(14, 40)
    grid.Size = Drawing.Size(740, 360)
    grid.ColumnCount = 7
    grid.RowHeadersVisible = False
    grid.AllowUserToAddRows = False
    grid.SelectionMode = WinForms.DataGridViewSelectionMode.FullRowSelect
    grid.Font = Drawing.Font("Consolas", 9)
    grid.Columns[0].HeaderText = "Nome (chiave)"
    grid.Columns[1].HeaderText = "X reale"
    grid.Columns[2].HeaderText = "X param"
    grid.Columns[3].HeaderText = "St.X"
    grid.Columns[4].HeaderText = "Y reale"
    grid.Columns[5].HeaderText = "Y param"
    grid.Columns[6].HeaderText = "St.Y"
    grid.Columns[0].Width = 180
    grid.Columns[1].Width = 80
    grid.Columns[2].Width = 130
    grid.Columns[3].Width = 50
    grid.Columns[4].Width = 80
    grid.Columns[5].Width = 130
    grid.Columns[6].Width = 50

    fmt = "%." + str(DECIMALS) + "f"
    status_labels = {"ok": "OK", "approx": "~", "err": "!", "empty": "."}

    for r in records:
        idx = grid.Rows.Add(
            r["name"],
            fmt % r["x"],
            r["ex"] if r["ex"] else "-",
            status_labels.get(r["sx"], "."),
            fmt % r["y"],
            r["ey"] if r["ey"] else "-",
            status_labels.get(r["sy"], "."))
        row = grid.Rows[idx]
        for col, st in [(3, r["sx"]), (6, r["sy"])]:
            if st == "ok":
                row.Cells[col].Style.BackColor = Drawing.Color.FromArgb(220, 245, 220)
            elif st == "approx":
                row.Cells[col].Style.BackColor = Drawing.Color.FromArgb(252, 240, 200)
            elif st == "err":
                row.Cells[col].Style.BackColor = Drawing.Color.FromArgb(252, 220, 220)

    form.Controls.Add(grid)
    form.ShowDialog()


# -----------------------------------------------------------------------------
#  CREAZIONE / AGGIORNAMENTO PUNTO
# -----------------------------------------------------------------------------
def create_provisional_point(pt, point_key, idx_pts):
    """Crea SUBITO il Point al clic, prima del dialogo (visibilita' al clic)."""
    fmt = "%." + str(DECIMALS) + "f"
    attr_pt = Rhino.DocObjects.ObjectAttributes()
    attr_pt.LayerIndex  = idx_pts
    attr_pt.ColorSource = Rhino.DocObjects.ObjectColorSource.ColorFromLayer
    attr_pt.Name = point_key

    pt_guid = sc.doc.Objects.AddPoint(pt, attr_pt)
    if pt_guid != System.Guid.Empty:
        rh_obj = sc.doc.Objects.FindId(pt_guid)
        if rh_obj:
            rh_obj.Attributes.SetUserString("X_reale", fmt % pt.X)
            rh_obj.Attributes.SetUserString("Y_reale", fmt % pt.Y)
            rh_obj.Attributes.SetUserString("PKG_provvisorio", "1")
            sc.doc.Objects.ModifyAttributes(rh_obj, rh_obj.Attributes, True)
        sc.doc.Views.Redraw()
    return pt_guid


def rollback_provisional_point(pt_guid):
    """Cancella il punto provvisorio creato al clic (su Salta/Annulla)."""
    if pt_guid is None or pt_guid == System.Guid.Empty:
        return
    sc.doc.Objects.Delete(pt_guid, True)
    sc.doc.Views.Redraw()


def finalize_point(pt_guid, point_key, x, y, expr_x, expr_y, sx, sy, note):
    """Aggiorna gli UserString del punto provvisorio, rendendolo definitivo."""
    fmt = "%." + str(DECIMALS) + "f"
    if pt_guid == System.Guid.Empty:
        return None
    rh_obj = sc.doc.Objects.FindId(pt_guid)
    if not rh_obj:
        return None
    rh_obj.Attributes.SetUserString("X_reale",  fmt % x)
    rh_obj.Attributes.SetUserString("Y_reale",  fmt % y)
    rh_obj.Attributes.SetUserString("X_param",  expr_x if expr_x else "--")
    rh_obj.Attributes.SetUserString("Y_param",  expr_y if expr_y else "--")
    rh_obj.Attributes.SetUserString("X_status", sx)
    rh_obj.Attributes.SetUserString("Y_status", sy)
    rh_obj.Attributes.SetUserString("Nota",     note if note else "")
    rh_obj.Attributes.SetUserString("PKG_provvisorio", "")
    rh_obj.Attributes.Name = point_key
    sc.doc.Objects.ModifyAttributes(rh_obj, rh_obj.Attributes, True)
    return rh_obj


# -----------------------------------------------------------------------------
def main():
    # === AVVIO (v4.3) ===
    # CON selezione: si leggono le QUOTE-funzione selezionate (definizione
    # variabili + vincoli), si precompila il dialog, si verificano e propagano
    # le formule creando i punti. SENZA selezione: help, poi sessione classica.
    pre_sel = []
    try:
        pre_sel = list(sc.doc.Objects.GetSelectedObjects(False, False))
    except Exception, ex:
        pre_sel = []

    quote_defs = {}
    quote_conflicts = []
    quote_constraints = []
    if pre_sel:
        quote_defs, quote_conflicts, quote_constraints = \
            collect_quote_constraints(pre_sel, sc.doc.ModelAbsoluteTolerance or 0.001)
    else:
        if not show_help_dialog():
            print "PKG Annotator: chiuso dall'help."
            return

    # AVVISO PRIMA del dialog: quote di definizione discordi. L'utente deve
    # poterle correggere nel campo (evidenziato in rosso), non scoprirlo a
    # propagazione gia' avvenuta.
    conflict_names = set()
    if quote_conflicts:
        wl = ["Quote di definizione DISCORDI - controlla i campi in rosso:", ""]
        for (n, votes) in quote_conflicts:
            conflict_names.add(n)
            vt = ", ".join("%g (x%d)" % (v, c) for (v, c) in votes)
            wl.append("  %s: %s  -> proposto %g" % (n, vt, quote_defs[n]))
        WinForms.MessageBox.Show("\n".join(wl), "PKG Annotator - quote discordi",
                                 WinForms.MessageBoxButtons.OK,
                                 WinForms.MessageBoxIcon.Warning)

    vars_dict, save_to_doc = show_params_dialog(preset=quote_defs,
                                                conflict_names=conflict_names)
    if vars_dict is None:
        print "PKG Annotator: annullato."
        return

    if save_to_doc:
        save_params_to_doc(vars_dict)

    tol = sc.doc.ModelAbsoluteTolerance
    if tol <= 0:
        tol = 0.001

    idx_pts  = get_or_create_layer(LAYER_POINTS, COLOR_POINTS)
    idx_dots = get_or_create_layer(LAYER_DOTS,   COLOR_DOTS)

    # === FASE QUOTE (v4.3): verifica + propagazione + creazione punti ===
    quote_nodes = {}
    if quote_constraints:
        nodes, n_ver, bad = propagate_quotes(quote_constraints, vars_dict, tol)
        quote_nodes = nodes          # restano in memoria per la precompilazione
        created, skipped, incomplete = apply_quote_points(
            nodes, vars_dict, tol, idx_pts, idx_dots)
        sc.doc.Views.Redraw()
        show_quote_report(quote_defs, quote_conflicts,
                          len(quote_constraints), n_ver, bad,
                          created, skipped, incomplete)

    # La selezione d'avvio intralcerebbe il clic dei punti: via tutto prima
    # della sessione punto-per-punto.
    if pre_sel:
        try:
            sc.doc.Objects.UnselectAll()
            sc.doc.Views.Redraw()
        except Exception, ex:
            pass

    fmt   = "%." + str(DECIMALS) + "f"
    count = 0
    records = []

    while True:
        gp = Rhino.Input.Custom.GetPoint()
        gp.SetCommandPrompt(
            "Punto #%d - calamita Fine/Medio  (Invio=fine, opzione SpecchiaCurve)" % (count + 1))
        gp.AcceptNothing(True)
        idx_opt_mirror = gp.AddOption("SpecchiaCurve")
        res = gp.Get()

        # Opzione "SpecchiaCurve" (Punto 3 v4.2)
        if res == Rhino.Input.GetResult.Option:
            if gp.OptionIndex() == idx_opt_mirror:
                mirror_tagged_curves(tol)
            continue

        # Invio (Nothing) o Esc (Cancel) o altro -> termina la sessione
        if res != Rhino.Input.GetResult.Point:
            break

        pt = gp.Point()
        x  = pt.X
        y  = pt.Y

        # === Chiavi geometriche del nuovo punto ===
        point_key = make_point_key(x, y)
        dot_key   = make_dot_key(x, y)

        # === Sovrascrittura: cerca e cancella eventuali duplicati ===
        old_pt_obj, old_dot_obj, preset = find_existing_by_key(point_key, dot_key, tol)
        is_overwrite = (old_pt_obj is not None)
        if is_overwrite:
            n_removed = delete_existing(old_pt_obj, old_dot_obj)
            print "PKG Annotator: sovrascrittura di %s (rimossi %d oggetto/i)." % (
                point_key, n_removed)
            sc.doc.Views.Redraw()

        # === VISIBILITA' AL CLIC ===
        prov_guid = create_provisional_point(pt, point_key, idx_pts)

        # === Reverse lookup sorgente: pool di vicini geometrici ===
        sources_x, sources_y = collect_source_formulas(
            pt, k_neighbors=3, exclude_at_zero_dist=True, tol=tol)
        source_ex = sources_x[0] if sources_x else None
        source_ey = sources_y[0] if sources_y else None

        # === PRECOMPILAZIONE CERTA (v4.3) ===
        # Se il punto non e' una sovrascrittura (o lo e' solo in parte), i
        # campi si precompilano SOLO con formule certe al 100%: zero, nodi del
        # grafo quote, copia da punti esattamente allineati. Il feedback live
        # del dialog le mostra subito verdi; basta confermare.
        pre_ex = preset["X_param"]
        pre_ey = preset["Y_param"]
        if not pre_ex or not pre_ey:
            cert_ex, cert_ey = certain_formulas_for(pt, quote_nodes, tol)
            if not pre_ex and cert_ex:
                pre_ex = cert_ex
            if not pre_ey and cert_ey:
                pre_ey = cert_ey

        expr_x, expr_y, note, sx, sy = show_param_dialog(
            x, y, vars_dict, tol,
            source_ex=source_ex, source_ey=source_ey,
            sources_x=sources_x, sources_y=sources_y,
            preset_ex=pre_ex,
            preset_ey=pre_ey,
            preset_note=preset["Nota"])

        # === Gestione esito del dialogo ===
        if expr_x is None:
            rollback_provisional_point(prov_guid)
            break

        if sx == "empty" and sy == "empty" and not expr_x and not expr_y and not note:
            rollback_provisional_point(prov_guid)
            continue

        # === Finalizza il punto provvisorio ===
        finalize_point(prov_guid, point_key, x, y, expr_x, expr_y, sx, sy, note)

        # === Crea il TextDot, colore in base alla completezza ===
        dot_text = build_dot_text(x, y, expr_x, expr_y, note, sx, sy)
        pt_dot   = Point3d(pt.X + DOT_OFFSET_X, pt.Y + DOT_OFFSET_Y, pt.Z)
        td       = TextDot(dot_text, pt_dot)
        td.FontHeight = DOT_HEIGHT
        td.FontFace   = DOT_FONT

        x_complete = sx in ("ok", "approx")
        y_complete = sy in ("ok", "approx")
        dot_color = COLOR_DOT_COMPLETE if (x_complete and y_complete) else COLOR_DOT_INCOMPLETE

        attr_dot = Rhino.DocObjects.ObjectAttributes()
        attr_dot.LayerIndex  = idx_dots
        attr_dot.ColorSource = Rhino.DocObjects.ObjectColorSource.ColorFromObject
        attr_dot.ObjectColor = dot_color
        attr_dot.Name = dot_key

        sc.doc.Objects.AddTextDot(td, attr_dot)

        records.append({
            "name": point_key, "x": x, "y": y,
            "ex": expr_x, "ey": expr_y,
            "sx": sx, "sy": sy, "note": note,
        })

        sc.doc.Views.Redraw()
        count += 1

    sc.doc.Views.Redraw()

    if count > 0:
        show_summary_dialog(records)

    print "PKG Annotator v4.2: %d punto/i creato/i o aggiornato/i." % count


if __name__ == "__main__":
    main()
