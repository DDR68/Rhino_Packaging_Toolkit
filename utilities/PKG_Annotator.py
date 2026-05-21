#! python 2
# -*- coding: utf-8 -*-

# =============================================================================
#  PACKAGING POINT ANNOTATOR  v4.0  -  Rhino 7 / 8  (IronPython 2.7)
#
#  Variabili packaging:
#    L = Larghezza         P = Profondita      A = Altezza
#    S = Spessore cartone  C = Patella d'incollatura (colla)
#    T = Patella di chiusura (Tuck)             E = Bisello (misura configurabile)
#
#  Novita' v4 rispetto a v3.0:
#    - VISIBILITA' AL CLIC: il Point viene creato e disegnato SUBITO dopo il
#      clic, prima di aprire il dialogo di annotazione. Cosi' il punto su cui
#      si sta lavorando e' sempre visibile nel viewport mentre si ragiona
#      sulla formula. (in v3 il punto veniva disegnato solo DOPO la conferma,
#      risultando invisibile durante tutta l'annotazione)
#    - ROLLBACK PULITO: se l'utente preme "Salta" o "Annulla tutto", il punto
#      provvisorio appena creato viene cancellato, senza lasciare oggetti
#      orfani privi di annotazione.
#    - L'aggancio alla logica di sovrascrittura per chiave geometrica resta
#      invariato: il punto provvisorio nasce gia' con il suo point_key.
#    - SUGGERIMENTO COORDINATA ZERO: se la coordinata target e' 0 (entro
#      tolleranza), il reverse lookup ritorna direttamente la sola costante
#      "0", saltando l'intera batteria combinatoria. Piu' veloce e piu'
#      leggibile dell'elenco di formule che si annullerebbero a zero.
#    - TERMINI COMPOSTI DI COMPENSAZIONE: il generatore di candidati ora sa
#      aggiungere binomi come (L-S), (P-S), (A-S) (lista COMPOUND_TERMS),
#      non solo variabili nude. Cosi' formule frequenti in cartotecnica come
#      'C+(L-S)+P+L+(P-S)' diventano raggiungibili dal reverse lookup.
#      Limite noto: la forma canonica tratta '(P-S)' e 'P-S' come monomi
#      distinti (nessun parser algebrico in IronPython 2.7).
#
#  Eredita da v3:
#    - Schema di naming geometrico: PKG_X+0112_Y-0030 (chiave posizionale)
#    - Nota utente solo in UserString "Nota", il nome resta una chiave pulita
#    - TextDot con altezza 10 e colore secondo completezza (grigio/giallo)
#    - Sovrascrittura automatica per chiave geometrica
#    - Reverse lookup "vicino geometrico" con pool di sorgenti
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

# Colori TextDot per stato di completezza (Punto 2)
COLOR_DOT_COMPLETE   = Drawing.Color.FromArgb(105, 105, 105)   # grigio: X e Y entrambi compilati e validi
COLOR_DOT_INCOMPLETE = Drawing.Color.FromArgb(220, 180, 0)     # giallo: mancanze (Nota esclusa dal calcolo)

VAR_NAMES = ["L", "P", "A", "S", "C", "T", "E"]

# Termini COMPOSTI aggiungibili nel reverse lookup (v4).
# In cartotecnica la compensazione di un lato per lo spessore del cartone
# (L-S), (P-S), (A-S) e' un'espressione frequentissima quanto una variabile
# nuda. Il generatore di candidati neighbor_candidates_from() aggiunge questi
# binomi accanto alle variabili semplici, cosi' formule come
# 'C+(L-S)+P+L+(P-S)' diventano raggiungibili partendo da 'C+(L-S)+P+L'.
# Per estendere (es. doppia compensazione), basta aggiungere qui le stringhe:
# es. "(L-S*2)", "(P-2*S)". Le versioni negative sono generate in automatico.
COMPOUND_TERMS = ["(L-S)", "(P-S)", "(A-S)"]
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


# -----------------------------------------------------------------------------
#  NAMING GEOMETRICO (Punto 4 + scelte v3)
# -----------------------------------------------------------------------------
def make_point_key(x, y):
    """Costruisce la chiave geometrica del punto, arrotondando al millimetro.
    Formato: PKG_X+0112_Y-0030  (segno esplicito, padding a 4 cifre).
    Copre +/- 9999 mm, sufficiente per ogni tracciato cartotecnico.
    """
    ix = int(round(x))
    iy = int(round(y))
    sx = "+" if ix >= 0 else "-"
    sy = "+" if iy >= 0 else "-"
    return "PKG_X%s%04d_Y%s%04d" % (sx, abs(ix), sy, abs(iy))


def make_dot_key(x, y):
    """Chiave per il TextDot associato a un punto. Stesso schema, prefisso diverso
    in modo che la sovrascrittura possa cancellarlo per match esatto."""
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
    delta = abs(computed - real)
    if delta <= tol:
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
def show_params_dialog():
    doc_params = load_params_from_doc()

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
        if name in doc_params:
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
#  REVERSE LOOKUP (Punto 3) - basato sul vicino geometrico
# -----------------------------------------------------------------------------
def collect_source_formulas(target_pt, k_neighbors=3, exclude_at_zero_dist=False, tol=1e-6):
    """Raccoglie un POOL di formule sorgenti per il reverse lookup.
    Strategia:
      1) Trova i k punti annotati piu' vicini al target (distanza euclidea).
      2) Raccoglie le X_param e Y_param dei k vicini, in ordine di vicinanza.
      3) Aggiunge in coda TUTTE le altre X_param e Y_param distinte presenti
         nel documento (pool "imparato dal documento"): cosi' se il vicino
         geometrico ha formula vuota, abbiamo comunque sorgenti plausibili
         derivate dall'uso reale.

    Ritorna (sources_x, sources_y) come liste ordinate per priorita',
    senza duplicati e senza stringhe vuote."""
    idx = sc.doc.Layers.FindByFullPath(LAYER_POINTS, -1)
    if idx < 0:
        return [], []

    entries = []
    all_ex = []
    all_ey = []

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
        entries.append((d, ex, ey))
        if ex: all_ex.append(ex)
        if ey: all_ey.append(ey)

    if not entries:
        return [], []

    entries.sort(key=lambda t: t[0])

    sources_x = []
    sources_y = []
    seen_x = set()
    seen_y = set()

    # FASE A: i primi k vicini (priorita' alta)
    for d, ex, ey in entries[:k_neighbors]:
        if ex and ex not in seen_x:
            sources_x.append(ex)
            seen_x.add(ex)
        if ey and ey not in seen_y:
            sources_y.append(ey)
            seen_y.add(ey)

    # FASE B: pool "imparato dal documento" (priorita' bassa, ma utile
    # quando il vicino geometrico ha formula vuota)
    for ex in all_ex:
        if ex and ex not in seen_x:
            sources_x.append(ex)
            seen_x.add(ex)
    for ey in all_ey:
        if ey and ey not in seen_y:
            sources_y.append(ey)
            seen_y.add(ey)

    return sources_x, sources_y


def find_nearest_annotated_point(target_pt, exclude_at_zero_dist=False, tol=1e-6):
    """Wrapper retrocompatibile: ritorna la PRIMA sorgente del pool
    (cioe' il vicino geometricamente piu' prossimo). Usato per il
    label informativo "Sorgente vicino" nel dialogo Suggerisci."""
    sx_list, sy_list = collect_source_formulas(
        target_pt, k_neighbors=1,
        exclude_at_zero_dist=exclude_at_zero_dist, tol=tol)
    ex = sx_list[0] if sx_list else None
    ey = sy_list[0] if sy_list else None
    return ex, ey, None


def split_top_level_terms(expr):
    """Spezza un'espressione nei suoi termini di somma di primo livello,
    rispettando le parentesi. Ogni termine porta con se' il proprio segno.
    Esempi:
        'C+L+P'      -> ['+C', '+L', '+P']
        'L-S*2'      -> ['+L', '-S*2']
        '(L-S*2)/2'  -> ['+(L-S*2)/2']
        'A+T-S'      -> ['+A', '+T', '-S']
    """
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


def canonical_form(expr):
    """Forma canonica di un'espressione: somma di monomi atomici di primo
    livello con coefficienti aggregati. Serve come chiave robusta per il
    filtro duplicati: 'C+L-S+E-E' e 'C+L-S' producono la stessa forma
    canonica e quindi vengono trattati come la stessa formula.

    Ritorna la stringa canonica (es. 'C+L-S', '2*L+S', '0').

    Limitazione consapevole: non e' una semplificazione algebrica completa
    (non riconosce L*2 == L+L), ma cattura il caso pratico dei termini che
    si annullano sommando segni opposti dello stesso monomio testuale.
    Riconosce inoltre i monomi puramente numerici come neutri se valgono 0
    (cosi' '0+S' viene canonicalizzato in 'S')."""
    terms = split_top_level_terms(expr)
    coeffs = {}
    for t in terms:
        if not t:
            continue
        if t[0] == "-":
            sign = -1
            mono = t[1:].strip()
        elif t[0] == "+":
            sign = 1
            mono = t[1:].strip()
        else:
            sign = 1
            mono = t.strip()
        if not mono:
            continue
        # Scarta monomi numerici pari a zero ('0', '0.0', '00')
        try:
            if float(mono) == 0.0:
                continue
        except ValueError:
            pass
        coeffs[mono] = coeffs.get(mono, 0) + sign

    # Rimuovi monomi con coefficiente zero (questo elimina '+E-E', 'L-L', ecc.)
    nonzero = {}
    for k, v in coeffs.items():
        if v != 0:
            nonzero[k] = v

    if not nonzero:
        return "0"

    keys_sorted = sorted(nonzero.keys())
    parts = []
    for k in keys_sorted:
        c = nonzero[k]
        if c == 1:
            parts.append("+" + k)
        elif c == -1:
            parts.append("-" + k)
        else:
            sign_str = "+" if c > 0 else ""
            parts.append("%s%d*%s" % (sign_str, c, k))
    canon = "".join(parts)
    if canon.startswith("+"):
        canon = canon[1:]
    return canon


def neighbor_candidates_from(expr_source):
    """Varianti della formula sorgente per riduzione e aggiunta di un termine.
    Filtri attivi:
      - Non aggiunge -V se +V e' gia' un termine di primo livello (e viceversa),
        per evitare candidati di auto-cancellazione tipo 'C+L+E-E'.
      - Include riduzione interna (rimozione di un termine in mezzo) oltre
        a riduzione di testa/coda.
    """
    candidates = []
    terms = split_top_level_terms(expr_source)
    if not terms:
        for v in VAR_NAMES:
            candidates.append(v)
            candidates.append("-" + v)
        return candidates

    existing = set(terms)  # contiene es. {'+C', '+L', '-S'}

    # 1) Riduzione di testa e coda
    if len(terms) > 1:
        candidates.append(join_terms(terms[:-1]))
        candidates.append(join_terms(terms[1:]))

    # 1bis) Riduzione interna: togli un termine al centro
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

    # 2bis) Aggiunta in coda dei termini COMPOSTI di compensazione (v4)
    # es. (P-S), (L-S), (A-S). Filtro: non ri-aggiungo un composto gia'
    # presente (evita 'C+(P-S)+(P-S)'); l'opposto '-(P-S)' viene comunque
    # collassato dalla forma canonica se ridondante.
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

    # 3bis) Aggiunta in testa dei termini COMPOSTI (v4)
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


def suggest_formulas(target, vars_dict, tol, source_exprs=None, max_results=15):
    """Reverse lookup parametrico.

    Parametri:
      target       : valore numerico target (X reale o Y reale del punto)
      vars_dict    : valori correnti delle variabili packaging
      tol          : tolleranza del documento
      source_exprs : LISTA di formule sorgente (ordinate per priorita',
                     tipicamente provenienti dai k vicini geometrici piu'
                     il pool "imparato dal documento"). Puo' essere anche
                     una stringa singola, per retrocompatibilita'.
      max_results  : numero massimo di candidati da ritornare

    Filtro duplicati: usa la FORMA CANONICA del candidato (cfr canonical_form)
    invece della stringa testuale. Cosi' 'C+L-S+E-E' e 'C+L-S' vengono
    riconosciuti come la stessa formula e il candidato ridondante viene
    scartato a favore del piu' breve.
    """
    canon_seen = set()
    matches = []

    # CASO SPECIALE (v4): target == 0.
    # Se la coordinata cercata e' zero (entro tolleranza), l'unico
    # suggerimento sensato e leggibile e' la costante "0". Evitiamo l'intera
    # batteria combinatoria: e' inutile cercare formule che valgono zero
    # (sarebbero solo termini che si annullano, gia' scartati altrove dal
    # filtro canonico canon == "0"). Ritorniamo subito, risparmiando lavoro.
    if abs(target) <= tol:
        return [("0", 0.0, 0.0, "ok")]

    # Retrocompatibilita': accetta singola stringa o lista
    if source_exprs is None:
        source_list = []
    elif isinstance(source_exprs, str):
        source_list = [source_exprs] if source_exprs else []
    else:
        source_list = [s for s in source_exprs if s]

    def try_candidate(expr_str):
        expr_str = expr_str.strip()
        if not expr_str:
            return
        # Canonicalizza per il filtro: collassa termini opposti e ordina
        canon = canonical_form(expr_str)
        # Scarta candidati banali (zero) e duplicati canonici
        if canon == "0" or canon in canon_seen:
            return
        canon_seen.add(canon)
        # Valuta la forma originale (mantiene la leggibilita' nell'UI)
        # Se la forma originale e' piu' lunga della canonica, preferiamo
        # la canonica come stringa visualizzata: e' piu' compatta e priva
        # di termini ridondanti.
        display_expr = canon if len(canon) < len(expr_str) else expr_str
        val, err = safe_eval(display_expr, vars_dict)
        if err is not None or val is None:
            return
        delta = abs(val - target)
        # Solo corrispondenze ESATTE entro la tolleranza del documento.
        # I candidati 'approx' (entro tol*10) sono stati rimossi perche'
        # generavano rumore visivo senza essere mai veri suggerimenti utili.
        if delta <= tol:
            matches.append((display_expr, val, delta, "ok"))

    # FASE 1: vicini di ciascuna sorgente nel pool
    # Iteriamo su tutte le sorgenti: la prima e' il vicino piu' prossimo,
    # le successive coprono i casi in cui il vicino euclideo non e' il
    # "vicino topologico" nel tracciato.
    for src in source_list:
        for cand in neighbor_candidates_from(src):
            try_candidate(cand)

    # FASE 2: fallback combinatorio (soglia alzata a 5 per essere generosi)
    if len(matches) < 5:
        var_items = list(vars_dict.items())
        for name, val in var_items:
            try_candidate(name)
            try_candidate("%s/2" % name)
            try_candidate("%s*2" % name)
            try_candidate("%s/3" % name)
            try_candidate("%s/4" % name)
        for i in range(len(var_items)):
            for j in range(len(var_items)):
                if i == j:
                    continue
                n1, _ = var_items[i]
                n2, _ = var_items[j]
                try_candidate("%s+%s" % (n1, n2))
                try_candidate("%s-%s" % (n1, n2))
                try_candidate("%s*2+%s" % (n1, n2))
                try_candidate("%s*2-%s" % (n1, n2))
                try_candidate("(%s-%s)/2" % (n1, n2))
                try_candidate("(%s+%s)/2" % (n1, n2))
                try_candidate("%s-%s*2" % (n1, n2))
                try_candidate("%s+%s*2" % (n1, n2))
        for pat in ("L+P+S","L+P-S","L-S*2","P-S*2","(L-S*2)/2","(P-S*2)/2",
                    "A+P+S","A+P-S","A-S*2","A+T","A+T-S","A+T+S",
                    "L+C","L-C","P+E","P-E"):
            try_candidate(pat)

    matches.sort(key=lambda t: t[2])
    return matches[:max_results]


# -----------------------------------------------------------------------------
def show_suggest_dialog(target_x, target_y, vars_dict, tol,
                        sources_x=None, sources_y=None,
                        source_ex=None, source_ey=None):
    """Dialog 'Suggerisci'. Accetta:
      - sources_x, sources_y: liste di formule sorgente (pool); preferite
      - source_ex, source_ey: stringhe singole (retrocompatibilita')
    Se entrambe le forme sono fornite, vengono unite (pool prima, singole dopo).
    """
    # Unifica gli input in liste
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

    # Mostra il pool di sorgenti (primi 3 per asse)
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
        # Tutti i match sono ora 'ok' (i candidati 'approx' sono stati rimossi),
        # quindi non serve un marker per distinguerli.
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
    """Dialogo di annotazione.
    preset_*    : valori di default nei campi (es. sovrascrittura)
    source_ex/ey: formula sorgente singola (retrocompatibilita')
    sources_x/y : pool di formule sorgenti, ordinato per priorita'
                  (usato dal bottone Suggerisci)."""
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

    # Triggera il feedback iniziale se i preset sono presenti
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
#  SOVRASCRITTURA (Punto 4) - basata sulla chiave geometrica
# -----------------------------------------------------------------------------
def find_existing_by_key(point_key, dot_key, tol):
    """Cerca punto e textdot esistenti con la chiave geometrica data.
    Ritorna (point_obj, dot_obj, preset_dict) dove preset_dict contiene
    X_param, Y_param, Nota del vecchio punto. Tutti i campi possono essere
    None se non trovato.

    Fallback: se il match esatto per nome fallisce, prova match in
    tolleranza geometrica sulle coordinate (copre casi di chiavi che
    differiscono di 1 mm per arrotondamento)."""
    idx_pts  = sc.doc.Layers.FindByFullPath(LAYER_POINTS, -1)
    idx_dots = sc.doc.Layers.FindByFullPath(LAYER_DOTS,   -1)

    found_pt = None
    found_dot = None
    preset = {"X_param": "", "Y_param": "", "Nota": ""}

    # Estraggo le coordinate dalla chiave per il fallback in tolleranza
    m = re.match(r"^PKG_X([+-])(\d+)_Y([+-])(\d+)$", point_key)
    if m:
        kx = int(m.group(2)) * (1 if m.group(1) == "+" else -1)
        ky = int(m.group(4)) * (1 if m.group(3) == "+" else -1)
    else:
        kx, ky = None, None

    tol_match = max(tol, 0.001) + 0.5  # 0.5 mm di slack per arrotondamenti

    for obj in sc.doc.Objects:
        if obj.IsDeleted:
            continue
        layer_idx = obj.Attributes.LayerIndex
        name = obj.Attributes.Name or ""

        # Match Point
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

        # Match TextDot
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
def show_summary_dialog(records):
    if not records:
        return

    form = WinForms.Form()
    form.Text = "Riepilogo sessione - PKG Annotator v4"
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
#  CREAZIONE / AGGIORNAMENTO PUNTO  (v4)
# -----------------------------------------------------------------------------
def create_provisional_point(pt, point_key, idx_pts):
    """Crea SUBITO il Point al clic, prima del dialogo (novita' v4).
    Il punto nasce gia' con il suo point_key e con UserString minimi che lo
    marcano come 'provvisorio'. Ritorna il GUID, oppure Guid.Empty se fallisce.

    Questo rende il punto visibile nel viewport mentre l'utente ragiona sulla
    formula. Se l'annotazione viene saltata/annullata, il punto verra'
    rimosso da rollback_provisional_point()."""
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
        sc.doc.Views.Redraw()  # forza il viewport a mostrare il punto subito
    return pt_guid


def rollback_provisional_point(pt_guid):
    """Cancella il punto provvisorio creato al clic, usato quando l'utente
    salta o annulla l'annotazione (novita' v4)."""
    if pt_guid is None or pt_guid == System.Guid.Empty:
        return
    sc.doc.Objects.Delete(pt_guid, True)
    sc.doc.Views.Redraw()


def finalize_point(pt_guid, point_key, x, y, expr_x, expr_y, sx, sy, note):
    """Aggiorna gli UserString del punto provvisorio gia' creato, rendendolo
    definitivo (rimuove il flag PKG_provvisorio). Ritorna l'oggetto Rhino
    aggiornato o None."""
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
    rh_obj.Attributes.SetUserString("PKG_provvisorio", "")  # non piu' provvisorio
    rh_obj.Attributes.Name = point_key  # chiave pulita, niente nota
    sc.doc.Objects.ModifyAttributes(rh_obj, rh_obj.Attributes, True)
    return rh_obj


# -----------------------------------------------------------------------------
def main():
    vars_dict, save_to_doc = show_params_dialog()
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

    fmt   = "%." + str(DECIMALS) + "f"
    count = 0
    records = []

    while True:
        gp = Rhino.Input.Custom.GetPoint()
        gp.SetCommandPrompt(
            "Punto #%d - calamita Fine/Medio  (Invio per terminare)" % (count + 1))
        gp.Get()

        if gp.CommandResult() != Rhino.Commands.Result.Success:
            break

        pt = gp.Point()
        x  = pt.X
        y  = pt.Y

        # === Chiavi geometriche del nuovo punto ===
        point_key = make_point_key(x, y)
        dot_key   = make_dot_key(x, y)

        # === Sovrascrittura (Punto 4): cerca e cancella eventuali duplicati ===
        # NB: la ricerca avviene PRIMA di creare il punto provvisorio, cosi'
        # find_existing_by_key non rischia di trovare il punto appena creato.
        old_pt_obj, old_dot_obj, preset = find_existing_by_key(point_key, dot_key, tol)
        is_overwrite = (old_pt_obj is not None)
        if is_overwrite:
            n_removed = delete_existing(old_pt_obj, old_dot_obj)
            print "PKG Annotator: sovrascrittura di %s (rimossi %d oggetto/i)." % (
                point_key, n_removed)
            sc.doc.Views.Redraw()

        # === VISIBILITA' AL CLIC (novita' v4) ===
        # Creo SUBITO il punto, prima del dialogo, cosi' e' visibile nel
        # viewport mentre ragiono sulla formula. Se poi salto/annullo, lo
        # rimuovo con rollback_provisional_point().
        prov_guid = create_provisional_point(pt, point_key, idx_pts)

        # === Reverse lookup sorgente: pool di vicini geometrici (Punto 3) ===
        # IMPORTANTE: escludo il punto provvisorio appena creato dalla raccolta
        # delle sorgenti. exclude_at_zero_dist=True scarta i punti a distanza
        # ~0 dal target, quindi il provvisorio (che e' esattamente sul target)
        # viene ignorato. Inoltre non ha ancora X_param/Y_param, quindi anche
        # se entrasse non aggiungerebbe sorgenti.
        sources_x, sources_y = collect_source_formulas(
            pt, k_neighbors=3, exclude_at_zero_dist=True, tol=tol)
        source_ex = sources_x[0] if sources_x else None
        source_ey = sources_y[0] if sources_y else None

        # Mostra dialogo. Se sovrascrittura, riproponi i valori vecchi come preset.
        expr_x, expr_y, note, sx, sy = show_param_dialog(
            x, y, vars_dict, tol,
            source_ex=source_ex, source_ey=source_ey,
            sources_x=sources_x, sources_y=sources_y,
            preset_ex=preset["X_param"],
            preset_ey=preset["Y_param"],
            preset_note=preset["Nota"])

        # === Gestione esito del dialogo ===
        if expr_x is None:
            # "Annulla tutto": rollback del provvisorio e uscita dal ciclo
            rollback_provisional_point(prov_guid)
            break

        if sx == "empty" and sy == "empty" and not expr_x and not expr_y and not note:
            # "Salta": l'utente non ha annotato nulla -> rollback del provvisorio
            # e passa al punto successivo senza creare TextDot ne' record.
            rollback_provisional_point(prov_guid)
            continue

        # === Finalizza il punto provvisorio (aggiorna gli UserString) ===
        finalize_point(prov_guid, point_key, x, y, expr_x, expr_y, sx, sy, note)

        # === Crea il TextDot, colore in base alla completezza (Punto 2) ===
        dot_text = build_dot_text(x, y, expr_x, expr_y, note, sx, sy)
        pt_dot   = Point3d(pt.X + DOT_OFFSET_X, pt.Y + DOT_OFFSET_Y, pt.Z)
        td       = TextDot(dot_text, pt_dot)
        td.FontHeight = DOT_HEIGHT
        td.FontFace   = DOT_FONT

        # Completezza: Nota esclusa dal calcolo
        # 'ok' e 'approx' contano come compilati; 'empty' e 'err' come mancanze
        x_complete = sx in ("ok", "approx")
        y_complete = sy in ("ok", "approx")
        dot_color = COLOR_DOT_COMPLETE if (x_complete and y_complete) else COLOR_DOT_INCOMPLETE

        attr_dot = Rhino.DocObjects.ObjectAttributes()
        attr_dot.LayerIndex  = idx_dots
        attr_dot.ColorSource = Rhino.DocObjects.ObjectColorSource.ColorFromObject
        attr_dot.ObjectColor = dot_color
        attr_dot.Name = dot_key  # chiave per match diretto in sovrascrittura

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

    print "PKG Annotator v4: %d punto/i creato/i o aggiornato/i." % count


if __name__ == "__main__":
    main()
