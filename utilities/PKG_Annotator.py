#! python 2
# -*- coding: utf-8 -*-

# =============================================================================
#  PACKAGING POINT ANNOTATOR  v4.8  -  Rhino 7 / 8  (IronPython 2.7)
#
#  Novita' v4.8 (TOLLERANZA DI COINCIDENZA 0.25mm - STOP AUTO-CANCELLAZIONE):
#    - I punti vicini non si cancellano piu' a vicenda. La sovrascrittura
#      (find_existing_by_key) basava l'identita' del punto sulla CHIAVE
#      arrotondata al millimetro: due punti diversi che cadevano nello stesso
#      mm condividevano la chiave (es. PKG_X+0010_Y+0005) e venivano trattati
#      come lo stesso punto, quindi il nuovo CANCELLAVA il vecchio anche a
#      distanze fino a ~1mm (e il match geometrico di riserva usava ~0.5mm).
#      Inaccettabile sui tracciati fitti: bisellini, patelle sottili, i due
#      lati di un'incisione.
#    - Ora l'identita' e' GEOMETRICA: si considera "lo stesso punto"
#      (-> sovrascrittura) SOLO un punto la cui distanza euclidea dal click e'
#      INFERIORE a OVERWRITE_TOL = 0.25mm. A 0.25mm o piu' i punti restano
#      DISTINTI. Tra piu' candidati entro soglia vince il piu' vicino. La
#      chiave torna a essere una semplice etichetta, non un criterio di
#      identita'.
#    - NOTA: make_point_key arrotonda ancora al mm, quindi due punti distinti
#      ma piu' vicini di ~1mm possono ancora condividere lo stesso NOME. Non
#      causa piu' cancellazioni (l'identita' e' la distanza reale); se servisse
#      un nome univoco sotto il mm, va affinata la risoluzione della chiave
#      (di concerto con lo script di esportazione che la legge).
#
#  Eredita da v4.7 (RIMOZIONE MOTORE DI SUGGERIMENTO + PULIZIA DOT):
#    - Tolto il motore di suggerimento (suggest_formulas, show_suggest_dialog
#      e gli helper canonical_form / neighbor_candidates_from / expr_for_gap /
#      find_farthest_source / collect_source_formulas). I candidati
#      combinatori "inventavano" formule non dichiarate; la fonte di verita'
#      sono le QUOTE assistite (sempre visibili a schermo) e i PUNTI gia'
#      annotati, di cui l'utente si assume la responsabilita'. Resta tutto
#      cio' che VERIFICA: precompilazione certa al 100% (certain_formulas_for),
#      validazione live (verde/giallo/rosso) e "Preleva -> X / Y" da quote e
#      punti. L'unica capacita' persa e' la proposta euristica; la copia da
#      punto allineato 'ok' resta dentro la precompilazione certa.
#    - Tolto il sottosistema TextDot residuo: niente piu' layer "Quote" creato
#      a vuoto a ogni avvio, niente make_dot_key / DOT_OFFSET / ramo dot in
#      find_existing_by_key. La migrazione cleanup_legacy_dots (rimozione dei
#      vecchi TextDot dai file pre-v4.4) RESTA: e' cio' che li elimina.
#
#  Novita' v4.6 (RIMOZIONE SPECCHIA CURVE):
#    - Tolta l'opzione "SpecchiaCurve" e tutta la logica di mirror delle
#      curve taggate "Proietta su X" lungo le linee cyan. Specchiava la
#      GEOMETRIA delle curve, non i PUNTI di annotazione: non era cio' che
#      serve. La simmetria del tracciato sara' gestita a valle, dallo
#      script parametrico, dopo il calcolo delle nuove misure (richiede
#      una modifica allo script di esportazione, non all'annotator).
#      L'annotator torna a occuparsi solo dei punti parametrici.
#
#  Eredita da v4.5 (PRELEVA DA QUOTE E DA PUNTI):
#    - Nel dialogo, "Preleva -> X" / "Preleva -> Y": accoda nel campo la
#      formula di quote-funzione (PlainText) e/o di punti annotati
#      (X_param o Y_param secondo l'asse).
#
#    - Nel dialogo di annotazione, accanto a "Suggerisci...", due pulsanti
#      "Preleva -> X" e "Preleva -> Y": si selezionano in Rhino una o piu'
#      QUOTE-funzione e/o PUNTI gia' annotati, e la formula giusta viene
#      ACCODATA nel campo corrispondente:
#        - da una quota-funzione: il suo PlainText;
#        - da un punto annotato:  la sua X_param se stai prelevando per X,
#          la Y_param se per Y (l'asse e' deciso dal pulsante premuto).
#      Ogni formula composita e' avvolta tra parentesi (convenzione visiva
#      dei gruppi) e concatenata con '+'; il segno si corregge a mano.
#      Comodo per costruire la posizione di un punto come somma dei tratti
#      gia' quotati o come "coordinata di un punto vicino +/- uno scarto".
#    - PATTERN ANTI-BLOCCO (lezione di Quota_Assistita v1.3): un dialogo
#      modale, anche nascosto, DISABILITA la finestra di Rhino e il
#      GetObject non riceverebbe input. Quindi il pulsante CHIUDE il
#      dialogo conservando il testo di X, Y e Nota; la selezione avviene
#      in contesto Rhino normale; il dialogo RIAPRE con i campi
#      conservati e la formula prelevata accodata al campo scelto.
#      Il punto provvisorio in lavorazione e' escluso dalla selezione.
#
#  Novita' v4.4 (LEGGIBILITA'):
#    - NIENTE PIU' TEXTDOT: le note testuali accanto ai punti toglievano
#      leggibilita' al tracciato e duplicavano informazioni gia' presenti
#      nelle UserString del punto (X_param/Y_param/X_status/Y_status/Nota).
#      Non vengono piu' create.
#    - COMPLETEZZA = COLORE DEL PUNTO: il Point stesso ora porta lo stato:
#        GRIGIO (105,105,105) = completo (X e Y entrambi ok/approx)
#        GIALLO (220,180,0)   = incompleto
#      Il punto provvisorio (appena cliccato, dialogo aperto) resta col
#      colore del layer (blu): tre stati distinguibili a colpo d'occhio.
#    - PULIZIA LEGACY: all'avvio lo script conta i TextDot delle versioni
#      precedenti (Name che inizia con 'PKG_DOT_') e chiede se rimuoverli
#      in blocco; in piu' RICOLORA automaticamente i punti gia' annotati
#      in base al loro X_status/Y_status, cosi' anche i file vecchi
#      adottano subito la nuova convenzione. La sovrascrittura puntuale
#      continua comunque a eliminare il TextDot legacy associato.
#    - PARSER: min() e max() ammessi nelle formule (allineamento con
#      PKG_Quota_Assistita >= v1.4). Esempio: min(L/2, (T+(P+S))/2)
#      per una patella che non deve mai superare meta' larghezza.
#    - finalize_point usa Attributes.Duplicate() prima di
#      ModifyAttributes (pattern robusto gia' adottato altrove).
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
from Rhino.Geometry import Point3d

# -----------------------------------------------------------------------------
DECIMALS     = 4
VERSION      = "4.8"
LAYER_POINTS = "PKG_Punti_Parametrici"
COLOR_POINTS = System.Drawing.Color.FromArgb(0, 80, 180)

# Soglia relativa minima aggiunta alla tolleranza assoluta nel confronto "ok"
# (Punto 1 v4.2). Sub-micron in pratica: blinda il confronto su coordinate di
# grande modulo senza allentare la precisione geometrica.
REL_EPS = 1e-9

# v4.8: soglia di COINCIDENZA per la sovrascrittura (mm). Due punti a distanza
# euclidea INFERIORE a questo valore sono lo stesso punto: il nuovo sovrascrive
# il vecchio. A 0.25mm o piu' restano distinti. (Prima l'identita' si basava
# sulla chiave arrotondata al mm: cancellava punti distanti fino a ~1mm.)
OVERWRITE_TOL = 0.25

# Colori del PUNTO per stato di completezza (v4.4: niente piu' TextDot,
# lo stato e' portato dal colore del Point stesso)
COLOR_PT_COMPLETE   = Drawing.Color.FromArgb(105, 105, 105)   # grigio: X e Y entrambi compilati e validi
COLOR_PT_INCOMPLETE = Drawing.Color.FromArgb(220, 180, 0)     # giallo: mancanze (Nota esclusa dal calcolo)

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
DOC_USERTEXT_PREFIX = "PKG_"

ALLOWED_FUNCS = {
    "abs":  abs,
    "sqrt": math.sqrt,
    "sin":  math.sin,
    "cos":  math.cos,
    "tan":  math.tan,
    "pi":   math.pi,
    # v4.4: formule condizionali (allineato a PKG_Quota_Assistita >= v1.4)
    # min = tetto (es. min(L/2, (T+(P+S))/2)), max = minimo garantito.
    "min":  min,
    "max":  max,
}

COLOR_OK      = Drawing.Color.FromArgb(0,   140, 0)
COLOR_APPROX  = Drawing.Color.FromArgb(190, 130, 0)
COLOR_ERR     = Drawing.Color.FromArgb(190, 30,  30)
COLOR_NEUTRAL = Drawing.Color.FromArgb(110, 110, 110)


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
#  ALGEBRA DELLE FORMULE - helper condivisi (quote, preleva, display)
# -----------------------------------------------------------------------------
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


# -----------------------------------------------------------------------------
#  PRELEVA DA QUOTE (v4.5, portato da PKG_Quota_Assistita v1.2/1.3)
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


def pick_formulas(axis, exclude_id=None):
    """Selezione in Rhino di QUOTE-funzione e/o PUNTI annotati; ritorna la
    lista delle formule da accodare, nell'ordine di selezione.
      - da una LinearDimension: il suo PlainText;
      - da un Point sul layer LAYER_POINTS: X_param se axis=='X',
        Y_param se axis=='Y'.
    Scarta gli oggetti senza formula valida (con avviso) e il punto
    provvisorio in lavorazione ('exclude_id'). 'axis' e' 'X' o 'Y'."""
    out = []
    idx_pts = sc.doc.Layers.FindByFullPath(LAYER_POINTS, -1)

    go = Rhino.Input.Custom.GetObject()
    go.SetCommandPrompt(
        "Seleziona quote-funzione e/o punti annotati per %s "
        "(Invio=conferma, Esc=annulla)" % axis)
    go.GeometryFilter = (Rhino.DocObjects.ObjectType.Annotation |
                         Rhino.DocObjects.ObjectType.Point)
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
            continue                          # punto provvisorio in lavorazione
        geo = obj.Geometry

        # --- QUOTA: PlainText ---
        if isinstance(geo, Rhino.Geometry.LinearDimension):
            try:
                t = (geo.PlainText or "").strip()
            except Exception, ex:
                t = ""
            if not t or not any(n in t for n in VAR_NAMES):
                print "Preleva: quota senza formula ('%s'), saltata." % t
                continue
            out.append(t)
            continue

        # --- PUNTO ANNOTATO: X_param / Y_param secondo l'asse ---
        if isinstance(geo, Rhino.Geometry.Point):
            if idx_pts >= 0 and obj.Attributes.LayerIndex != idx_pts:
                print "Preleva: punto fuori dal layer annotazioni, saltato."
                continue
            key = "X_param" if axis == "X" else "Y_param"
            f = obj.Attributes.GetUserString(key) or ""
            f = f.strip()
            if not f or f == "--":
                print "Preleva: punto senza %s, saltato." % key
                continue
            out.append(f)
            continue

        print "Preleva: oggetto non valido (ne' quota ne' punto), saltato."

    sc.doc.Objects.UnselectAll()
    sc.doc.Views.Redraw()
    return out


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


# -----------------------------------------------------------------------------
def show_param_dialog(x, y, vars_dict, tol,
                      preset_ex="", preset_ey="", preset_note=""):
    """Dialogo di annotazione con validazione live.
    Ritorna (action, expr_x, expr_y, note, sx, sy):
      action = 'ok' | 'skip' | 'cancel' | 'pick_x' | 'pick_y'
    Per 'pick_x'/'pick_y' i tre testi correnti (X, Y, Nota) vengono
    restituiti cosi' come sono: il chiamante fa selezionare le quote in
    contesto Rhino (il dialogo DEVE essere chiuso: un modale, anche
    nascosto, disabilita la finestra di Rhino) e riapre il dialogo con i
    campi conservati e la formula prelevata accodata."""
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

    # === Preleva da quote (v4.5): chiude il dialogo, il chiamante fa
    #     selezionare le quote e riapre col campo arricchito ===
    pick = {"action": None}

    btn_pick_x = WinForms.Button()
    btn_pick_x.Text = "Preleva -> X"
    btn_pick_x.Font = Drawing.Font("Segoe UI", 8)
    btn_pick_x.Location = Drawing.Point(14, 308)
    btn_pick_x.Size = Drawing.Size(92, 28)
    form.Controls.Add(btn_pick_x)

    btn_pick_y = WinForms.Button()
    btn_pick_y.Text = "Preleva -> Y"
    btn_pick_y.Font = Drawing.Font("Segoe UI", 8)
    btn_pick_y.Location = Drawing.Point(112, 308)
    btn_pick_y.Size = Drawing.Size(92, 28)
    form.Controls.Add(btn_pick_y)

    def on_pick_x(sender, e):
        pick["action"] = "pick_x"
        form.Close()
    btn_pick_x.Click += on_pick_x

    def on_pick_y(sender, e):
        pick["action"] = "pick_y"
        form.Close()
    btn_pick_y.Click += on_pick_y

    btn_ok = WinForms.Button()
    btn_ok.Text = "Conferma"
    btn_ok.Font = Drawing.Font("Segoe UI", 9, Drawing.FontStyle.Bold)
    btn_ok.BackColor = Drawing.Color.FromArgb(0, 100, 200)
    btn_ok.ForeColor = Drawing.Color.White
    btn_ok.FlatStyle = WinForms.FlatStyle.Flat
    btn_ok.Location = Drawing.Point(214, 308)
    btn_ok.Size = Drawing.Size(100, 28)
    btn_ok.DialogResult = WinForms.DialogResult.OK
    form.Controls.Add(btn_ok)
    form.AcceptButton = btn_ok

    btn_skip = WinForms.Button()
    btn_skip.Text = "Salta"
    btn_skip.Font = Drawing.Font("Segoe UI", 9)
    btn_skip.Location = Drawing.Point(324, 308)
    btn_skip.Size = Drawing.Size(70, 28)
    btn_skip.DialogResult = WinForms.DialogResult.Ignore
    form.Controls.Add(btn_skip)

    btn_cancel = WinForms.Button()
    btn_cancel.Text = "Annulla tutto"
    btn_cancel.Font = Drawing.Font("Segoe UI", 9)
    btn_cancel.ForeColor = Drawing.Color.FromArgb(180, 30, 30)
    btn_cancel.Location = Drawing.Point(404, 308)
    btn_cancel.Size = Drawing.Size(78, 28)
    btn_cancel.DialogResult = WinForms.DialogResult.Cancel
    form.Controls.Add(btn_cancel)
    form.CancelButton = btn_cancel

    txt_x.Select()
    if preset_ex:
        txt_x.SelectionStart = len(preset_ex)

    result = form.ShowDialog()

    cur = (txt_x.Text.strip(), txt_y.Text.strip(), txt_note.Text.strip(),
           state["sx"], state["sy"])

    if pick["action"] in ("pick_x", "pick_y"):
        return (pick["action"],) + cur
    if result == WinForms.DialogResult.OK:
        return ("ok",) + cur
    elif result == WinForms.DialogResult.Ignore:
        return ("skip", "", "", "", "empty", "empty")
    else:
        return ("cancel", None, None, None, None, None)


# -----------------------------------------------------------------------------
#  COMPLETEZZA -> COLORE DEL PUNTO (v4.4, sostituisce i TextDot)
# -----------------------------------------------------------------------------
def point_completeness_color(sx, sy):
    """Grigio se X e Y sono entrambi compilati e validi, giallo altrimenti."""
    x_complete = sx in ("ok", "approx")
    y_complete = sy in ("ok", "approx")
    if x_complete and y_complete:
        return COLOR_PT_COMPLETE
    return COLOR_PT_INCOMPLETE


def cleanup_legacy_dots():
    """Conta i TextDot delle versioni precedenti (Name 'PKG_DOT_...') e, su
    conferma, li rimuove in blocco. Il filtro sul prefisso del nome evita di
    toccare quote o altri oggetti sul layer. Ritorna il numero rimosso."""
    legacy = []
    for obj in sc.doc.Objects:
        if obj.IsDeleted:
            continue
        if not isinstance(obj.Geometry, Rhino.Geometry.TextDot):
            continue
        name = obj.Attributes.Name or ""
        if name.startswith("PKG_DOT_"):
            legacy.append(obj.Id)
    if not legacy:
        return 0
    r = WinForms.MessageBox.Show(
        ("Trovati %d TextDot legacy (note dei punti).\n"
         "Dalla v4.4 le note non vengono piu' create: la completezza\n"
         "e' indicata dal COLORE del punto (grigio = completo,\n"
         "giallo = incompleto).\n\n"
         "Rimuovere ora tutti i TextDot legacy?") % len(legacy),
        "PKG Annotator - pulizia note",
        WinForms.MessageBoxButtons.YesNo,
        WinForms.MessageBoxIcon.Question)
    if r != WinForms.DialogResult.Yes:
        return 0
    n = 0
    for gid in legacy:
        if sc.doc.Objects.Delete(gid, True):
            n += 1
    sc.doc.Views.Redraw()
    print "PKG Annotator: rimossi %d TextDot legacy." % n
    return n


def recolor_points_by_completeness(idx_pts):
    """Ricolora i punti annotati esistenti in base a X_status/Y_status, cosi'
    anche i file delle versioni precedenti adottano subito la convenzione
    grigio/giallo. I punti senza alcuno status (mai annotati) non vengono
    toccati. Ritorna il numero di punti ricolorati."""
    if idx_pts < 0:
        return 0
    n = 0
    for obj in sc.doc.Objects:
        if obj.IsDeleted or obj.Attributes.LayerIndex != idx_pts:
            continue
        if not isinstance(obj.Geometry, Rhino.Geometry.Point):
            continue
        sx = obj.Attributes.GetUserString("X_status")
        sy = obj.Attributes.GetUserString("Y_status")
        if not sx and not sy:
            continue                  # punto mai finalizzato: lascia stare
        color = point_completeness_color(sx or "", sy or "")
        attr = obj.Attributes.Duplicate()
        if (attr.ColorSource == Rhino.DocObjects.ObjectColorSource.ColorFromObject
                and attr.ObjectColor == color):
            continue                  # gia' a posto
        attr.ColorSource = Rhino.DocObjects.ObjectColorSource.ColorFromObject
        attr.ObjectColor = color
        if sc.doc.Objects.ModifyAttributes(obj, attr, True):
            n += 1
    if n > 0:
        sc.doc.Views.Redraw()
        print "PKG Annotator: ricolorati %d punto/i (grigio/giallo)." % n
    return n


# -----------------------------------------------------------------------------
#  SOVRASCRITTURA - basata sulla COINCIDENZA GEOMETRICA (v4.8)
# -----------------------------------------------------------------------------
def find_existing_by_key(x, y):
    """Cerca un punto annotato gia' presente COINCIDENTE col punto cliccato.

    v4.8: l'identita' del punto e' GEOMETRICA, non basata sulla chiave.
    Prima il confronto era sul nome (chiave arrotondata al mm) e, in subordine,
    sulla posizione con soglia ~0.5mm: due punti diversi nello stesso
    millimetro condividevano la chiave e si cancellavano a vicenda anche a
    ~1mm di distanza. Ora si considera "lo stesso punto" (-> sovrascrittura)
    SOLO un punto la cui distanza euclidea dal click e' INFERIORE a
    OVERWRITE_TOL (0.25mm); tra piu' candidati entro soglia vince il piu'
    vicino. Ritorna (punto_trovato | None, preset).

    Nota: la funzione e' chiamata in main() PRIMA della creazione del punto
    provvisorio del click corrente, quindi non c'e' rischio di trovare se
    stessi; nessun id da escludere."""
    idx_pts = sc.doc.Layers.FindByFullPath(LAYER_POINTS, -1)

    found_pt = None
    preset = {"X_param": "", "Y_param": "", "Nota": ""}
    if idx_pts < 0:
        return found_pt, preset

    tol2 = OVERWRITE_TOL * OVERWRITE_TOL      # confronto su distanza al quadrato
    best_d2 = None
    for obj in sc.doc.Objects:
        if obj.IsDeleted:
            continue
        if obj.Attributes.LayerIndex != idx_pts:
            continue
        if not isinstance(obj.Geometry, Rhino.Geometry.Point):
            continue
        p = obj.Geometry.Location
        dx = p.X - x
        dy = p.Y - y
        d2 = dx * dx + dy * dy
        if d2 < tol2 and (best_d2 is None or d2 < best_d2):
            best_d2 = d2
            found_pt = obj

    if found_pt is not None:
        preset["X_param"] = found_pt.Attributes.GetUserString("X_param") or ""
        preset["Y_param"] = found_pt.Attributes.GetUserString("Y_param") or ""
        preset["Nota"]    = found_pt.Attributes.GetUserString("Nota") or ""
        if preset["X_param"] == "--": preset["X_param"] = ""
        if preset["Y_param"] == "--": preset["Y_param"] = ""

    return found_pt, preset


def delete_existing(point_obj):
    """Cancella un Point precedentemente trovato."""
    n = 0
    if point_obj is not None:
        if sc.doc.Objects.Delete(point_obj.Id, True):
            n += 1
    return n


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


def apply_quote_points(nodes, vars_dict, tol, idx_pts):
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
        prov = create_provisional_point(pt, point_key, idx_pts)
        finalize_point(prov, point_key, x, y, ex, ey, "ok", "ok", "da quota")
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
        "PKG ANNOTATOR v" + VERSION + " - guida rapida\n\n"
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
        "classica: clic su un punto; se cade su un nodo-quota ancorato o e'\n"
        "allineato a un punto gia' 'ok', X/Y vengono PRECOMPILATE (da\n"
        "verificare e confermare). La completezza e' indicata dal COLORE\n"
        "del punto: GRIGIO = completo, GIALLO = incompleto (niente piu'\n"
        "note TextDot; quelle legacy vengono rimosse su conferma).\n"
        "Due punti vengono fusi (sovrascrittura) solo se a meno di 0.25mm;\n"
        "oltre quella soglia restano distinti (v4.8).\n"
        "Formule: min/max ammessi, es. min(L/2, (T+(P+S))/2).\n"
        "Nel dialogo, 'Preleva -> X' / 'Preleva -> Y' (v4.5): seleziona\n"
        "quote-funzione e/o punti gia' annotati; ne accoda la formula nel\n"
        "campo (dalle quote il testo, dai punti X_param o Y_param secondo\n"
        "l'asse). Il dialogo si chiude per la selezione e riapre da solo.\n"
        "Invio per terminare.\n\n"
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
    form.Text = "Riepilogo sessione - PKG Annotator v" + VERSION
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
    """Aggiorna gli UserString del punto provvisorio, rendendolo definitivo.
    v4.4: imposta anche il COLORE in base alla completezza (grigio = X e Y
    entrambi validi, giallo = incompleto) e usa Attributes.Duplicate()
    prima di ModifyAttributes (un riferimento vivo puo' essere ignorato)."""
    fmt = "%." + str(DECIMALS) + "f"
    if pt_guid == System.Guid.Empty:
        return None
    rh_obj = sc.doc.Objects.FindId(pt_guid)
    if not rh_obj:
        return None
    attr = rh_obj.Attributes.Duplicate()
    attr.SetUserString("X_reale",  fmt % x)
    attr.SetUserString("Y_reale",  fmt % y)
    attr.SetUserString("X_param",  expr_x if expr_x else "--")
    attr.SetUserString("Y_param",  expr_y if expr_y else "--")
    attr.SetUserString("X_status", sx)
    attr.SetUserString("Y_status", sy)
    attr.SetUserString("Nota",     note if note else "")
    attr.SetUserString("PKG_provvisorio", "")
    attr.Name = point_key
    attr.ColorSource = Rhino.DocObjects.ObjectColorSource.ColorFromObject
    attr.ObjectColor = point_completeness_color(sx, sy)
    sc.doc.Objects.ModifyAttributes(rh_obj, attr, True)
    return sc.doc.Objects.FindId(pt_guid)


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

    # === MIGRAZIONE v4.4: via i TextDot legacy, colore sui punti ===
    cleanup_legacy_dots()
    recolor_points_by_completeness(idx_pts)

    # === FASE QUOTE (v4.3): verifica + propagazione + creazione punti ===
    quote_nodes = {}
    if quote_constraints:
        nodes, n_ver, bad = propagate_quotes(quote_constraints, vars_dict, tol)
        quote_nodes = nodes          # restano in memoria per la precompilazione
        created, skipped, incomplete = apply_quote_points(
            nodes, vars_dict, tol, idx_pts)
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
            "Punto #%d - calamita Fine/Medio  (Invio=fine)" % (count + 1))
        gp.AcceptNothing(True)
        res = gp.Get()

        # Invio (Nothing) o Esc (Cancel) o altro -> termina la sessione
        if res != Rhino.Input.GetResult.Point:
            break

        pt = gp.Point()
        x  = pt.X
        y  = pt.Y

        # === Chiave geometrica del nuovo punto (etichetta, non identita') ===
        point_key = make_point_key(x, y)

        # === Sovrascrittura: cerca e cancella SOLO un punto realmente
        #     coincidente (distanza < OVERWRITE_TOL = 0.25mm, v4.8) ===
        old_pt_obj, preset = find_existing_by_key(x, y)
        is_overwrite = (old_pt_obj is not None)
        if is_overwrite:
            n_removed = delete_existing(old_pt_obj)
            print "PKG Annotator: sovrascrittura di %s (rimossi %d oggetto/i)." % (
                point_key, n_removed)
            sc.doc.Views.Redraw()

        # === VISIBILITA' AL CLIC ===
        prov_guid = create_provisional_point(pt, point_key, idx_pts)

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

        # === Dialogo con ciclo "Preleva da quote" (v4.5) ===
        # 'pick_x'/'pick_y': il dialogo si e' chiuso conservando i campi;
        # selezione quote in contesto Rhino, accodamento, riapertura.
        pending_ex   = pre_ex
        pending_ey   = pre_ey
        pending_note = preset["Nota"]
        while True:
            action, expr_x, expr_y, note, sx, sy = show_param_dialog(
                x, y, vars_dict, tol,
                preset_ex=pending_ex,
                preset_ey=pending_ey,
                preset_note=pending_note)
            if action not in ("pick_x", "pick_y"):
                break
            pending_ex, pending_ey, pending_note = expr_x, expr_y, note
            ax = "X" if action == "pick_x" else "Y"
            target = pending_ex if action == "pick_x" else pending_ey
            for f_ in pick_formulas(ax, exclude_id=prov_guid):
                piece = wrap_if_composite(f_)
                target = piece if not target else (target + "+" + piece)
            if action == "pick_x":
                pending_ex = target
            else:
                pending_ey = target

        # === Gestione esito del dialogo ===
        if action == "cancel" or expr_x is None:
            rollback_provisional_point(prov_guid)
            break

        if sx == "empty" and sy == "empty" and not expr_x and not expr_y and not note:
            rollback_provisional_point(prov_guid)
            continue

        # === Finalizza il punto provvisorio (v4.4: colore = completezza) ===
        finalize_point(prov_guid, point_key, x, y, expr_x, expr_y, sx, sy, note)

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

    print "PKG Annotator v%s: %d punto/i creato/i o aggiornato/i." % (VERSION, count)


if __name__ == "__main__":
    main()
