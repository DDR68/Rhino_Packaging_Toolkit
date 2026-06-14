#! python 2
# -*- coding: utf-8 -*-

# =============================================================================
#  PKG QUOTA ASSISTITA  v1.5  -  Rhino 7 / 8  (IronPython 2.7)
#
#  Novita' v1.5:
#    - CANDIDATI TANGENTE AUTOMATICI: quando un'estremita' cade su un
#      arco, il motore non si limita piu' a MOSTRARE raggio e centro:
#      calcola la distanza dall'ALTRA estremita' al CENTRO lungo l'asse
#      di misura, ne cerca le formule esatte col motore dei candidati,
#      deduce il segno (misura = centro+R -> tangente esterna,
#      misura = centro-R -> tangente interna) e propone direttamente
#          (formula_centro)+R_simbolico
#      in testa alla lista dei candidati, marcato '<- tangente arco'.
#    - RAGGIO SIMBOLICO: il raggio rilevato viene espresso con le
#      variabili quando possibile (variabile intera, meta', oppure
#      multiplo intero 2..8 degli spessori S/E: R=2 con S=0.5 -> 'S*4');
#      altrimenti resta numerico (costante di fabbricazione).
#    - Se la distanza al centro NON ha formula esatta (tipico: l'altra
#      estremita' non e' ancorata a un punto parametrico) nessun
#      candidato tangente viene proposto e la riga di comando suggerisce
#      di ancorare prima il centro o spostare l'estremita'.
#
#  Novita' v1.4:
#    - FORMULE CONDIZIONALI: min() e max() ammessi nelle formule.
#      Scenario tipico: la patella di chiusura cresce come (T+(P+S))/2
#      ma non deve MAI superare L/2:
#          min(L/2, (T+(P+S))/2)
#      Sotto la soglia vince il secondo termine, sopra vince L/2.
#      max() impone invece un minimo:  max(C, 12)  = mai meno di 12 mm.
#      I due si combinano:  min(L/2, max(E, (T+(P+S))/2)).
#      NOTA: min/max sono termini UNICI di primo livello, quindi la
#      scomposizione live e il prelievo da quote li trattano come gruppo.
#    - AGGANCIO PERPENDICOLARE (seconda estremita'): opzione
#      "Perpendicolare" nel prompt; si seleziona una linea o curva e la
#      seconda estremita' diventa il PIEDE della perpendicolare condotta
#      dalla prima estremita' sulla curva (Curve.ClosestPoint: il punto
#      piu' vicino su una curva liscia e' per definizione il piede della
#      perpendicolare). Nessun clic di posizionamento: il punto e' esatto.
#    - AGGANCIO PARALLELO (seconda estremita'): opzione "Parallela"; si
#      seleziona la direzione di riferimento (una linea, oppure una curva:
#      vale la tangente nel punto di selezione) e il clic successivo e'
#      VINCOLATO alla retta passante per la prima estremita' con quella
#      direzione (GetPoint.Constrain su Line).
#    - RILEVAMENTO TANGENTI SU RACCORDI: se un'estremita' cade su un arco
#      (tipicamente con osnap Tan su un raccordo), lo script interroga la
#      geometria sotto il punto e ne rileva CENTRO e RAGGIO, mostrandoli
#      nel dialogo insieme alle coordinate delle 4 tangenti assiali
#      (CX-R, CX+R, CY-R, CY+R): e' l'informazione che l'osnap conosce ma
#      non comunica allo script. Indispensabile coi raggi parametrici
#      (es. R=E): la tangente lungo X cade a CX+R, quindi il termine del
#      raggio va incluso nella formula (es. "(L-S)/2+E").
#      Le PolyCurve vengono esplose per scendere fino al segmento arco
#      (stessa logica dell'exporter V.3).
#    - GUIDA CON ESEMPI: opzione "Aiuto" al prompt della prima estremita'
#      apre una finestra con esempi pratici di tutti i casi sopra.
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
#    1. clic prima estremita'  (Invio/Esc = fine sessione; opzione "Aiuto")
#    2. clic seconda estremita'  (opzioni "Perpendicolare" / "Parallela")
#    3. clic posizione della linea di quota (anteprima dinamica; l'asse X o
#       Y e' dedotto dalla posizione, come nel comando _Dim; opzione "Asse"
#       per forzarlo)
#    4. dialogo: misura reale + eventuali archi rilevati sotto le
#       estremita' + campo formula con verifica live (verde = combacia,
#       arancio = entro 10x tolleranza, rosso = NON combacia) + lista di
#       CANDIDATI ESATTI gia' calcolati dalle variabili (clic per
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
#    - ATTENZIONE: se si adottano min/max nelle quote, anche il parser di
#      PKG_Annotator deve includerli in ALLOWED_FUNCS (stessa estensione).
#  Le quote OBLIQUE (vincoli 'D', es. bisello E a 45 gradi) non sono gestite
#  da questo script: vanno inserite a mano come prima (restano comunque
#  lette e verificate da PKG_Annotator).
#
#  Convenzioni toolkit: solo RhinoCommon + scriptcontext (no
#  rhinoscriptsyntax), niente f-string, stringhe %, except Exception, ex.
# =============================================================================

import Rhino
import Rhino.Geometry as rg
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

# v1.4: min/max per le formule condizionali (limiti superiori/inferiori).
# Se si usano nelle quote, estendere allo stesso modo ALLOWED_FUNCS in
# PKG_Annotator, che condivide il parser.
ALLOWED_FUNCS = {
    "abs":  abs,
    "sqrt": math.sqrt,
    "sin":  math.sin,
    "cos":  math.cos,
    "tan":  math.tan,
    "pi":   math.pi,
    "min":  min,
    "max":  max,
}

COLOR_OK      = Drawing.Color.FromArgb(0,   140, 0)
COLOR_APPROX  = Drawing.Color.FromArgb(190, 130, 0)
COLOR_ERR     = Drawing.Color.FromArgb(190, 30,  30)
COLOR_NEUTRAL = Drawing.Color.FromArgb(110, 110, 110)
COLOR_PREVIEW = Drawing.Color.FromArgb(0, 120, 200)   # anteprima dinamica
COLOR_GEOINFO = Drawing.Color.FromArgb(0, 100, 170)   # info archi rilevati

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
    'S*-1', '(', ',') NON spezzano. Le chiamate min(...)/max(...) restano
    quindi termini unici: le virgole non spezzano mai e i +/- interni sono
    protetti dalla profondita' delle parentesi."""
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
#  GUIDA CON ESEMPI (v1.4) - opzione "Aiuto" al prompt principale
# -----------------------------------------------------------------------------
HELP_TEXT = (
    "QUOTA ASSISTITA v1.5 - GUIDA RAPIDA\r\n"
    "===================================\r\n"
    "\r\n"
    "FLUSSO\r\n"
    "  1) clic prima estremita'   (Invio = fine sessione)\r\n"
    "  2) clic seconda estremita' (opzioni: Perpendicolare, Parallela)\r\n"
    "  3) clic posizione linea di quota (opzione Asse: Auto/X/Y)\r\n"
    "  4) dialogo formula con verifica live -> OK\r\n"
    "\r\n"
    "VARIABILI (Document User Text, chiavi PKG_*)\r\n"
    "  L=Larghezza  P=Profondita  A=Altezza  S=Spessore cartone\r\n"
    "  C=Patella incollatura  T=Patella chiusura (Tuck)  E=Bisello\r\n"
    "\r\n"
    "-------------------------------------------------------------\r\n"
    "FORMULE CONDIZIONALI: min() e max()\r\n"
    "-------------------------------------------------------------\r\n"
    "min(a, b) restituisce il piu' PICCOLO: impone un tetto.\r\n"
    "max(a, b) restituisce il piu' GRANDE: impone un minimo.\r\n"
    "\r\n"
    "Esempio 1 - patella con tetto a L/2:\r\n"
    "  La patella cresce come (T+(P+S))/2 ma non deve mai\r\n"
    "  superare meta' della larghezza.\r\n"
    "      min(L/2, (T+(P+S))/2)\r\n"
    "  Con L=100 P=60 S=0.5 T=30  ->  (30+60.5)/2 = 45.25\r\n"
    "  (sotto 50, vince la formula). Se P crescesse fino a far\r\n"
    "  superare 50, la quota resterebbe bloccata a L/2 = 50.\r\n"
    "\r\n"
    "Esempio 2 - larghezza minima garantita:\r\n"
    "      max(C, 12)\r\n"
    "  La patella d'incollatura segue C ma mai sotto 12 mm.\r\n"
    "\r\n"
    "Esempio 3 - limite inferiore E superiore insieme:\r\n"
    "      min(L/2, max(E, (T+(P+S))/2))\r\n"
    "\r\n"
    "NOTA: min/max valgono come UN solo gruppo nella\r\n"
    "scomposizione live e nel 'Preleva da quote'.\r\n"
    "Se si usano, PKG_Annotator deve avere lo stesso\r\n"
    "ALLOWED_FUNCS esteso, altrimenti segnalera' errore.\r\n"
    "\r\n"
    "-------------------------------------------------------------\r\n"
    "SECONDA ESTREMITA' - AGGANCIO PERPENDICOLARE\r\n"
    "-------------------------------------------------------------\r\n"
    "Al prompt della seconda estremita' cliccare l'opzione\r\n"
    "'Perpendicolare', poi selezionare la linea o curva di\r\n"
    "destinazione. La seconda estremita' diventa il PIEDE della\r\n"
    "perpendicolare condotta dalla prima estremita' sulla curva\r\n"
    "(Curve.ClosestPoint): nessun clic di posizionamento,\r\n"
    "il punto e' geometricamente esatto.\r\n"
    "\r\n"
    "Esempio: distanza di un foro dal bordo obliquo di una\r\n"
    "patella -> p1 = centro foro, opzione Perpendicolare,\r\n"
    "selezione del taglio obliquo.\r\n"
    "\r\n"
    "-------------------------------------------------------------\r\n"
    "SECONDA ESTREMITA' - AGGANCIO PARALLELO\r\n"
    "-------------------------------------------------------------\r\n"
    "Opzione 'Parallela': selezionare una linea (o una curva: vale\r\n"
    "la tangente nel punto di selezione). Il clic successivo e'\r\n"
    "VINCOLATO alla retta passante per la prima estremita' con\r\n"
    "quella direzione: utile per riportare una distanza lungo la\r\n"
    "stessa inclinazione di un bordo esistente.\r\n"
    "\r\n"
    "-------------------------------------------------------------\r\n"
    "TANGENTI SU RACCORDI (rilevamento automatico)\r\n"
    "-------------------------------------------------------------\r\n"
    "Se un'estremita' cade su un ARCO (tipico: osnap Tan su un\r\n"
    "raccordo), lo script rileva raggio e centro e li mostra nel\r\n"
    "dialogo, ad esempio:\r\n"
    "    P2 su arco: R=1.5  C=(120, 45.5)\r\n"
    "    tang.X 118.5 / 121.5   tang.Y 44 / 47\r\n"
    "La tangente verticale (misure lungo X) cade a CX-R o CX+R;\r\n"
    "quella orizzontale (lungo Y) a CY-R o CY+R.\r\n"
    "\r\n"
    "Esempio con raggio parametrico R=E: quota X dal centro del\r\n"
    "pannello alla tangente destra del raccordo ->\r\n"
    "    (L-S)/2+E\r\n"
    "Il termine del raggio (E) va incluso nella formula: e'\r\n"
    "esattamente l'informazione che l'osnap aggancia ma non\r\n"
    "comunica, e che ora il dialogo rende visibile.\r\n"
    "\r\n"
    "CANDIDATI AUTOMATICI (v1.5): se la distanza dall'altra\r\n"
    "estremita' al CENTRO ha una formula esatta, i candidati\r\n"
    "'(formula_centro)+R' compaiono DA SOLI in testa alla lista,\r\n"
    "marcati '<- tangente arco', con R gia' simbolico quando\r\n"
    "possibile (es. R=2 con S=0.5 -> S*4; multipli 2..8 di S/E).\r\n"
    "Se NON compaiono, l'altra estremita' non e' su un punto\r\n"
    "parametrico: ancorarla a un cordone/spigolo, oppure quotare\r\n"
    "prima il centro (osnap Cen) e usare 'Preleva da quote'.\r\n"
)


def show_help():
    form = WinForms.Form()
    form.Text = "Quota assistita v1.5 - Guida ed esempi"
    form.ClientSize = Drawing.Size(620, 560)
    form.StartPosition = WinForms.FormStartPosition.CenterScreen
    form.MaximizeBox = False
    form.BackColor = Drawing.Color.FromArgb(245, 245, 245)

    txt = WinForms.TextBox()
    txt.Multiline = True
    txt.ReadOnly = True
    txt.ScrollBars = WinForms.ScrollBars.Vertical
    txt.Font = Drawing.Font("Consolas", 9)
    txt.Location = Drawing.Point(10, 10)
    txt.Size = Drawing.Size(600, 504)
    txt.Text = HELP_TEXT
    form.Controls.Add(txt)

    btn = WinForms.Button()
    btn.Text = "Chiudi"
    btn.Location = Drawing.Point(530, 524)
    btn.Size = Drawing.Size(80, 28)
    btn.Click += lambda s, e: form.Close()
    form.Controls.Add(btn)
    form.CancelButton = btn

    form.ShowDialog()
    # deseleziona il testo evidenziato di default
    txt.SelectionLength = 0


# -----------------------------------------------------------------------------
#  ISPEZIONE GEOMETRICA SOTTO IL PUNTO CLICCATO (v1.4)
#  L'osnap (Tan, Perp, ...) aggancia il punto ma non dice SU QUALE oggetto:
#  qui si interroga il documento a posteriori, scendendo nelle PolyCurve
#  fino al segmento elementare (stessa logica dell'exporter V.3).
# -----------------------------------------------------------------------------
def explode_curve(curve):
    if isinstance(curve, rg.PolyCurve):
        segments = []
        for i in range(curve.SegmentCount):
            seg = curve.SegmentCurve(i)
            if seg is not None:
                segments.extend(explode_curve(seg))
        return segments
    if isinstance(curve, rg.PolylineCurve):
        pl = curve.ToPolyline()
        if pl is not None and pl.Count > 1:
            lines = []
            for i in range(pl.Count - 1):
                lines.append(rg.LineCurve(pl[i], pl[i + 1]))
            return lines
        return [curve]
    return [curve]


def inspect_point(pt, tol):
    """Cerca la curva del documento passante per pt (entro 10x tolleranza).
    Ritorna ('Arc', Arc) / ('Line', curve) / ('Curve', curve) per la curva
    PIU' VICINA al punto, oppure None se non c'e' nulla sotto."""
    hit_tol = max(tol * 10.0, 0.01)
    best = None
    best_d = hit_tol
    try:
        it = sc.doc.Objects.GetObjectList(Rhino.DocObjects.ObjectType.Curve)
    except Exception, ex:
        return None
    for obj in it:
        crv = obj.Geometry
        if crv is None:
            continue
        bb = crv.GetBoundingBox(True)
        if not bb.IsValid:
            continue
        # quick reject sul bounding box gonfiato (performance su file grandi)
        if (pt.X < bb.Min.X - hit_tol or pt.X > bb.Max.X + hit_tol or
                pt.Y < bb.Min.Y - hit_tol or pt.Y > bb.Max.Y + hit_tol):
            continue
        for seg in explode_curve(crv):
            try:
                rc, t = seg.ClosestPoint(pt)
            except Exception, ex:
                continue
            if not rc:
                continue
            d = seg.PointAt(t).DistanceTo(pt)
            if d >= best_d:
                continue
            ok_arc, arc = seg.TryGetArc(tol)
            if ok_arc:
                best = ("Arc", arc)
            elif seg.IsLinear(Rhino.RhinoMath.ZeroTolerance):
                best = ("Line", seg)
            else:
                best = ("Curve", seg)
            best_d = d
    return best


def detect_endpoint_arc(pt, tol):
    """Arco sotto il punto cliccato (o None)."""
    hit = inspect_point(pt, tol)
    if hit is None or hit[0] != "Arc":
        return None
    return hit[1]


def describe_arc(label, arc):
    """Stringa informativa per il dialogo: raggio, centro e coordinate
    delle 4 tangenti assiali dell'arco rilevato."""
    cx = arc.Center.X
    cy = arc.Center.Y
    r = arc.Radius
    return ("%s su arco: R=%.4g  C=(%.4g, %.4g)   "
            "tang.X %.4g / %.4g   tang.Y %.4g / %.4g" % (
                label, r, cx, cy, cx - r, cx + r, cy - r, cy + r))


def radius_expression(r, vars_dict, tol):
    """Espressione simbolica del raggio, se esiste: una variabile, la sua
    meta', oppure un multiplo intero 2..8 degli spessori S/E (R=2 con
    S=0.5 -> 'S*4'). Altrimenti il valore numerico (costante di
    fabbricazione)."""
    matches = []
    for n in VAR_NAMES:
        v = vars_dict.get(n, 0.0)
        if abs(v) <= tol:
            continue
        cands = [(n, v, 1), (n + "/2", v / 2.0, 2)]
        if n in THICKNESS_VARS:
            for k in range(2, 9):
                cands.append(("%s*%d" % (n, k), v * k, 2))
        for (e, val, c) in cands:
            if abs(val - r) <= tol + REL_EPS * abs(r):
                matches.append((c, len(e), e))
    if matches:
        matches.sort()
        return matches[0][2]
    return "%g" % r


def tangent_candidates(p1, p2, arcs, axis, measured, vars_dict, tol,
                       max_results=6):
    """v1.5: candidati 'centro +/- raggio' per le estremita' su arco.
    La tangente assiale cade SEMPRE a CX+/-R (o CY+/-R): si misura la
    distanza dall'ALTRA estremita' al centro lungo l'asse, si cercano le
    formule esatte di quella distanza, si esprime R in simboli e si
    deduce il segno confrontando la misura. Ritorna [(expr, valore)];
    se il centro non e' parametrico, avvisa in riga di comando."""
    out = []
    other = {"P1": p2, "P2": p1}
    for label in ("P1", "P2"):
        arc = arcs.get(label)
        if arc is None:
            continue
        if axis == "X":
            c = arc.Center.X
            o = other[label].X
        else:
            c = arc.Center.Y
            o = other[label].Y
        d_center = abs(c - o)
        r = arc.Radius
        st_plus, _d1 = compare_value(d_center + r, measured, tol)
        st_minus, _d2 = compare_value(d_center - r, measured, tol)
        if st_plus == "ok":
            sign = "+"
        elif st_minus == "ok":
            sign = "-"
        else:
            continue      # l'estremita' non e' una tangente assiale
        r_expr = radius_expression(r, vars_dict, tol)
        cents = exact_candidates(d_center, vars_dict, tol, max_results=4)
        if not cents:
            print ("Tangente %s: distanza al centro %.4f lungo %s SENZA "
                   "formula esatta - ancorare l'altra estremita' a un "
                   "punto parametrico (o quotare prima il centro)."
                   % (label, d_center, axis))
            continue
        for (ce, cv) in cents:
            expr = "%s%s%s" % (wrap_if_composite(ce), sign, r_expr)
            val = cv + r if sign == "+" else cv - r
            out.append((expr, val))
        if len(out) >= max_results:
            break
    return out[:max_results]


# -----------------------------------------------------------------------------
#  AGGANCI SECONDA ESTREMITA' (v1.4): PERPENDICOLARE E PARALLELO
# -----------------------------------------------------------------------------
def pick_reference_curve(prompt):
    """Selezione singola di una curva di riferimento.
    Ritorna (curve, punto_di_selezione) oppure (None, None)."""
    go = Rhino.Input.Custom.GetObject()
    go.SetCommandPrompt(prompt)
    go.GeometryFilter = Rhino.DocObjects.ObjectType.Curve
    go.SubObjectSelect = False
    go.EnablePreSelect(False, True)
    if go.Get() != Rhino.Input.GetResult.Object:
        return None, None
    objref = go.Object(0)
    crv = objref.Curve()
    pick = None
    try:
        sp = objref.SelectionPoint()
        if sp is not None and sp.IsValid:
            pick = sp
    except Exception, ex:
        pick = None
    sc.doc.Objects.UnselectAll()
    sc.doc.Views.Redraw()
    return crv, pick


def endpoint_perpendicular(p1, tol):
    """Seconda estremita' = piede della perpendicolare da p1 sulla curva
    selezionata (Curve.ClosestPoint). Ritorna Point3d o None."""
    crv, _pick = pick_reference_curve(
        "Linea/curva di destinazione per l'aggancio perpendicolare")
    if crv is None:
        return None
    rc, t = crv.ClosestPoint(p1)
    if not rc:
        print "Perpendicolare: proiezione fallita."
        return None
    p2 = crv.PointAt(t)
    if p1.DistanceTo(p2) <= tol:
        print "Perpendicolare: la prima estremita' giace gia' sulla curva."
        return None
    print "Perpendicolare: piede a (%.4f, %.4f)." % (p2.X, p2.Y)
    return Point3d(p2.X, p2.Y, 0.0)


def endpoint_parallel(p1, tol):
    """Seconda estremita' su retta per p1 parallela alla direzione di una
    linea di riferimento (o alla tangente di una curva nel punto di
    selezione). Il clic e' vincolato alla retta. Ritorna Point3d o None."""
    crv, pick = pick_reference_curve(
        "Linea/curva di riferimento per la direzione parallela")
    if crv is None:
        return None
    if crv.IsLinear(Rhino.RhinoMath.ZeroTolerance):
        d = crv.PointAtEnd - crv.PointAtStart
        v = Vector3d(d.X, d.Y, 0.0)
    else:
        base = pick if pick is not None else p1
        rc, t = crv.ClosestPoint(base)
        if not rc:
            print "Parallela: impossibile valutare la tangente."
            return None
        tg = crv.TangentAt(t)
        v = Vector3d(tg.X, tg.Y, 0.0)
    if not v.Unitize():
        print "Parallela: direzione di riferimento nulla."
        return None

    ext = 1e5
    ln = rg.Line(
        Point3d(p1.X - v.X * ext, p1.Y - v.Y * ext, 0.0),
        Point3d(p1.X + v.X * ext, p1.Y + v.Y * ext, 0.0))

    gp = Rhino.Input.Custom.GetPoint()
    gp.SetCommandPrompt(
        "Seconda estremita' sulla parallela (direzione %.4g, %.4g)" % (
            v.X, v.Y))
    gp.SetBasePoint(p1, True)
    gp.DrawLineFromPoint(p1, True)
    gp.Constrain(ln)
    if gp.Get() != Rhino.Input.GetResult.Point:
        return None
    p2 = gp.Point()
    if p1.DistanceTo(p2) <= tol:
        print "Parallela: estremita' coincidenti."
        return None
    return Point3d(p2.X, p2.Y, 0.0)


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
#  DIALOGO FORMULA CON VERIFICA LIVE
# -----------------------------------------------------------------------------
def show_formula_dialog(measured, axis, vars_dict, tol, count,
                        initial_text="", geo_lines=None,
                        extra_candidates=None):
    """Ritorna (action, expr):
       action = 'ok' | 'skip' | 'end' | 'pickdims'
       expr   = formula confermata ('ok') oppure testo corrente del campo
                ('pickdims': il chiamante seleziona le quote e riapre il
                dialogo col testo arricchito).
    'initial_text' precompila il campo formula (riapertura dopo prelievo).
    'geo_lines'  (v1.4): righe informative sugli archi rilevati sotto le
                 estremita' (raggio, centro, tangenti assiali).
    'extra_candidates' (v1.5): candidati 'centro +/- raggio' delle
                 tangenti, mostrati in testa alla lista."""
    fmt = "%." + str(DECIMALS) + "f"

    form = WinForms.Form()
    form.Text = "Quota assistita #%d - asse %s" % (count, axis)
    form.ClientSize = Drawing.Size(664, 484)   # v1.4: +36px per info archi
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

    # v1.4: archi rilevati sotto le estremita' (raggio/centro/tangenti)
    lbl_geo = WinForms.Label()
    if geo_lines:
        lbl_geo.Text = "\n".join(geo_lines)
    else:
        lbl_geo.Text = "(nessun arco rilevato sotto le estremita')"
    lbl_geo.Font = Drawing.Font("Consolas", 8)
    lbl_geo.ForeColor = COLOR_GEOINFO if geo_lines else COLOR_NEUTRAL
    lbl_geo.Location = Drawing.Point(14, 52)
    lbl_geo.Size = Drawing.Size(636, 32)
    form.Controls.Add(lbl_geo)

    lbl_f = WinForms.Label()
    lbl_f.Text = "Formula (testo della quota):"
    lbl_f.Font = Drawing.Font("Segoe UI", 8)
    lbl_f.Location = Drawing.Point(14, 88)
    lbl_f.Size = Drawing.Size(300, 16)
    form.Controls.Add(lbl_f)

    txt = WinForms.TextBox()
    txt.Font = Drawing.Font("Consolas", 11)
    txt.Location = Drawing.Point(14, 106)
    txt.Size = Drawing.Size(636, 26)
    form.Controls.Add(txt)

    lbl_fb = WinForms.Label()
    lbl_fb.Text = "(vuoto)"
    lbl_fb.Font = Drawing.Font("Consolas", 9)
    lbl_fb.ForeColor = COLOR_NEUTRAL
    lbl_fb.Location = Drawing.Point(14, 136)
    lbl_fb.Size = Drawing.Size(636, 18)
    form.Controls.Add(lbl_fb)

    lbl_dec = WinForms.Label()
    lbl_dec.Text = "Scomposizione (gruppi di primo livello):"
    lbl_dec.Font = Drawing.Font("Segoe UI", 8)
    lbl_dec.Location = Drawing.Point(14, 158)
    lbl_dec.Size = Drawing.Size(340, 16)
    form.Controls.Add(lbl_dec)

    lst_dec = WinForms.ListBox()
    lst_dec.Font = Drawing.Font("Consolas", 9)
    lst_dec.Location = Drawing.Point(14, 176)
    lst_dec.Size = Drawing.Size(636, 76)
    lst_dec.HorizontalScrollbar = True
    # 'None' e' parola chiave: l'enum va recuperato con getattr
    lst_dec.SelectionMode = getattr(WinForms.SelectionMode, "None")
    form.Controls.Add(lst_dec)

    lbl_sug = WinForms.Label()
    lbl_sug.Text = "Candidati esatti (clic = inserisci, doppio clic = OK):"
    lbl_sug.Font = Drawing.Font("Segoe UI", 8)
    lbl_sug.Location = Drawing.Point(14, 260)
    lbl_sug.Size = Drawing.Size(340, 16)
    form.Controls.Add(lbl_sug)

    lst = WinForms.ListBox()
    lst.Font = Drawing.Font("Consolas", 9)
    lst.Location = Drawing.Point(14, 278)
    lst.Size = Drawing.Size(636, 150)
    form.Controls.Add(lst)

    state = {"status": "empty", "exprs": []}
    result = {"action": "skip", "expr": ""}

    def fill_suggestions():
        lst.Items.Clear()
        state["exprs"] = []
        if extra_candidates:
            for (e, v) in extra_candidates:
                lst.Items.Add("%-34s = %s   <- tangente arco" % (
                    e, fmt % v))
                state["exprs"].append(e)
        cands = exact_candidates(measured, vars_dict, tol)
        for (e, v) in cands:
            lst.Items.Add("%-34s = %s" % (e, fmt % v))
            state["exprs"].append(e)
        if not state["exprs"]:
            lst.Items.Add("(nessun candidato esatto: digitare la formula)")

    btn_use = WinForms.Button()
    btn_use.Text = "Definisci variabile = misura"
    btn_use.Font = Drawing.Font("Segoe UI", 8)
    btn_use.Location = Drawing.Point(184, 446)
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
    btn_pick_dim.Location = Drawing.Point(14, 446)
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
    btn_ok.Location = Drawing.Point(404, 446)
    btn_ok.Size = Drawing.Size(80, 28)
    btn_ok.Click += lambda s, e: accept()
    form.Controls.Add(btn_ok)

    btn_skip = WinForms.Button()
    btn_skip.Text = "Salta"
    btn_skip.Location = Drawing.Point(492, 446)
    btn_skip.Size = Drawing.Size(80, 28)
    def on_skip(s, e):
        result["action"] = "skip"
        form.Close()
    btn_skip.Click += on_skip
    form.Controls.Add(btn_skip)

    btn_end = WinForms.Button()
    btn_end.Text = "Fine"
    btn_end.Location = Drawing.Point(580, 446)
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
    print "PKG QUOTA ASSISTITA v1.5"
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
    print ("Opzioni: 'Aiuto' (guida ed esempi), 'Asse' (X/Y forzato); "
           "2a estremita': 'Perpendicolare' / 'Parallela'.")

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
        opt_help = gp1.AddOption("Aiuto")
        res = gp1.Get()
        if res == Rhino.Input.GetResult.Option:
            idx = gp1.OptionIndex()
            if idx == opt_help:
                show_help()
                continue
            sel = gp1.Option().CurrentListOptionIndex
            forced_axis = None if sel == 0 else axis_labels[sel]
            continue
        if res != Rhino.Input.GetResult.Point:
            break
        p1 = gp1.Point()

        # --- 2) seconda estremita' (v1.4: opzioni Perpendicolare/Parallela) ---
        p2 = None
        retry = True
        while retry:
            retry = False
            gp2 = Rhino.Input.Custom.GetPoint()
            gp2.SetCommandPrompt("Seconda estremita'")
            gp2.SetBasePoint(p1, True)
            gp2.DrawLineFromPoint(p1, True)
            opt_perp = gp2.AddOption("Perpendicolare")
            opt_par  = gp2.AddOption("Parallela")
            res2 = gp2.Get()
            if res2 == Rhino.Input.GetResult.Option:
                idx2 = gp2.OptionIndex()
                if idx2 == opt_perp:
                    p2 = endpoint_perpendicular(p1, tol)
                elif idx2 == opt_par:
                    p2 = endpoint_parallel(p1, tol)
                if p2 is None:
                    retry = True      # annullato: ritorna al prompt
                continue
            if res2 == Rhino.Input.GetResult.Point:
                p2 = gp2.Point()
        if p2 is None:
            continue
        if p1.DistanceTo(p2) <= tol:
            print "Estremita' coincidenti: quota ignorata."
            continue

        # --- v1.4/v1.5: ispezione archi sotto le estremita' ---
        geo_lines = []
        arcs = {}
        for (lab, pt) in (("P1", p1), ("P2", p2)):
            arc = detect_endpoint_arc(pt, tol)
            arcs[lab] = arc
            if arc is not None:
                info = describe_arc(lab, arc)
                geo_lines.append(info)
                print info

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

        # --- v1.5: candidati tangente (centro +/- raggio) ---
        tang_cands = tangent_candidates(p1, p2, arcs, axis, measured,
                                        vars_dict, tol)

        # dialogo formula; 'pickdims' = selezione quote e riapertura
        pending_text = ""
        while True:
            action, expr = show_formula_dialog(
                measured, axis, vars_dict, tol, count + 1,
                initial_text=pending_text, geo_lines=geo_lines,
                extra_candidates=tang_cands)
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
