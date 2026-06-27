#! python 2
# -*- coding: utf-8 -*-
"""
Script: Esporta_Geometrie_Parametrico.py
Versione: 5.6
Compatibilita: Rhino 7 / Rhino 8 - IronPython 2.7 - RhinoCommon (no rhinoscriptsyntax)

NOVITA V.5.6 rispetto a V.5.5:
  - [Variabili parametriche] Il TXT esportato dichiara ora in testa le
    VARIABILI PARAMETRICHE del modello con valore di Default, Min, Max e
    Descrizione. Le variabili sono estratte automaticamente dalle formule
    dei punti parametrici (lettere maiuscole singole: L, P, A, S, C,
    T, E, ...) e presentate in un dialogo Eto dove l'utente le compila.
    I campi partono VUOTI (i valori sono specifici del modello); le
    descrizioni hanno solo il nome generico (materiali e vincoli sono a
    carico dell'utente). I campi lasciati vuoti sono emessi come '-' nel
    TXT.
  - [Prompt LLM] Il prompt embedded istruisce l'LLM a leggere default e
    range dalla sezione '# VARIABILI PARAMETRICHE', a usarli come valori
    iniziali per GetNumber e a validare l'input contro il range con avviso
    e ri-richiesta se fuori range.

UNIFICA:
  - Aggiorna_UserText_Parametrico (propagazione punti parametrici -> curve)
  - Esporta_Geometrie_Semplice V.4 (export TXT tab-separated)

AGGIUNTE (robustezza e usabilita'):
  - [Raccordi conici] Per le NURBS quadratiche (grado 2, 3 CP) salva la
    firma di forma (CtrlProp_u, CtrlProp_v, CtrlPeso_w): il raccordo e'
    interamente parametrico e si riadatta ai parametri.
  - [Archi robusti] Salva Punto_medio (tre punti) + Centro_geom assoluto:
    ricostruzione univoca, immune ad ambiguita' di verso.
  - [Curve libere] Per le NURBS non quadratiche salva CtrlPoints (x,y,w,
    separati da '|') + Nodi: ricostruzione geometrica esatta.
  - [Prompt LLM] Opzione (checkbox nel dialogo) per anteporre al TXT un
    prompt che istruisce un LLM a generare lo script parametrico dai dati.
    Il file diventa autoportante (istruzioni + dati). Vedi _llm_prompt_header.

NOVITA V.5.5 rispetto a V.5.4:
  - [Membership dai GRUPPI Rhino] La membership delle specchiature ora deriva
    dai gruppi Rhino (_Group): ogni gruppo che contiene una linea cyan definisce
    un PASSO; la linea cyan ne e' l'asse e ne fissa il tipo. Un oggetto puo'
    appartenere a piu' gruppi: e' cosi' che si rappresentano le MATRIOSKE
    (annidamento). La vecchia UserString 'Blocco' resta come FALLBACK quando
    nella selezione non ci sono gruppi Rhino.
  - [Colonna Blocco = lista passi] Per ogni curva la colonna Blocco contiene
    ora la LISTA (CSV) dei passi a cui partecipa (es. '1,2'): una curva interna
    compare in piu' passi perche' il passo esterno la rispecchia di nuovo. Per
    le linee-asse la colonna contiene il passo che definiscono.
  - [Ordine = annidamento] I passi sono ordinati dal piu' INTERNO (meno membri)
    al piu' ESTERNO (piu' membri); a parita', le patelle (tratteggiate) prima
    della simmetria (continua). Coerente col modello matrioska confermato:
    il passo esterno riflette anche i risultati dei passi interni.
  - [Riepilogo a 'Passi'] Il riepilogo in testa al TXT elenca i Passi con
    ordine, tipo d'asse, forma parametrica e n. membri, e dichiara la regola
    matrioska. Aggiornato anche il prompt LLM.
  - [Diagnostica] La diagnostica mostra ora, per ogni linea cyan/lineare, i
    gruppi Rhino di appartenenza e i passi calcolati. Avviso se una linea asse
    e' priva di gruppo (non entra nell'ordine di specchiatura).

NOVITA V.5.4 rispetto a V.5.3:
  - [Specchiatura: continua vs tratteggiata] L'asse cyan di un blocco e' ora
    classificato per TIPO DI LINEA:
      * linea CONTINUA  -> asse di SIMMETRIA: le geometrie vengono riflesse e
        gli originali RESTANO (scatola intera). Ruolo TXT: AsseSpecchio_Continuo.
      * linea TRATTEGGIATA -> asse di PATELLA: le geometrie vengono riflesse e
        gli originali vengono CANCELLATI (vive solo la copia). Ruolo TXT:
        AsseSpecchio_Tratteggiato.
    Il tipo di linea e' riconosciuto dalla STRUTTURA del pattern (SegmentCount/
    PatternLength del Linetype effettivo, per-oggetto o per-layer), NON dal nome:
    robusto a lingua, template e file di terzi. Indice -1 o linetype continuo del
    documento = continuo; qualsiasi pattern con segmenti = tratteggiato.
  - [Esecuzione sequenziale annidata] I blocchi sono "matrioske": eseguiti uno
    alla volta in ordine crescente di numero, dal piu' interno (patelle,
    tratteggiate) al piu' esterno (simmetria finale, continua). Ogni blocco N
    opera su TUTTO cio' che esiste dopo i blocchi 1..N-1. Il numero di blocco e'
    l'ordine di esecuzione e va ricordato passo per passo. Nessuna diramazione:
    la sequenza e' lineare.
  - [Errore bloccante] Se un blocco contiene per errore SIA una linea continua
    SIA una tratteggiata, l'export viene ABORTITO (nessun file scritto) con un
    messaggio chiaro: un blocco ammette un solo asse.
  - [Report] Conteggio delle curve selezionate prive di 'Blocco' quando la
    specchiatura e' in uso (segnala possibili annotazioni mancanti).
  - [Prompt LLM] Riscritte le sezioni sugli assi e sulla specchiatura per
    distinguere patella (cancella origine) da simmetria (mantiene origine) e per
    imporre l'esecuzione sequenziale accumulativa in ordine di blocco.

NOVITA V.5.3 rispetto a V.5.2:
  - [Specchiatura] L'export riconosce i BLOCCHI DI SPECCHIATURA: gli oggetti
    con UserString 'Blocco'=N (N = ordine di esecuzione) sono raggruppati;
    dentro ogni blocco la linea CYAN e' l'asse di riflessione. Nuove colonne
    'Blocco' e 'Ruolo' (AsseSpecchio sulla linea cyan) e un riepilogo blocchi
    in testa al TXT (asse: coordinate + forma parametrica se gli estremi sono
    punti annotati). NESSUNA geometria viene specchiata in Rhino: e' lo script
    parametrico generato dall'LLM a riflettere, in ordine di blocco. Caso
    gestito: SCATOLA INTERA (origine + copia restano entrambe). Le PATELLE
    (origine che sparisce) sono rimandate.
  - [Prompt LLM] Riscritto e ampliato: riconoscimento degli assi (Ruolo o
    layer non strutturale = linea cyan); specchiatura come ULTIMA operazione
    con l'asse RICOSTRUITO dalla formula e poi CANCELLATO (non resta nella
    fustella); semantica del raggio di raccordo nei punti (un termine di
    raggio marca la tangenza di un arco); variabili L, P, A, S con default e
    input GetNumber; auto-verifica del combaciamento sull'asse.
  - [Precisione pair_id] L'identificatore dei punti passa da millimetro intero
    a 0.001 mm (la stessa risoluzione del match geometrico), cosi' due vertici
    vicini - tipici con bevel e spessore - non collassano piu' sullo stesso
    id. Formato leggibile: PKG_X+0100.000_Y-0030.500.

NOVITA V.5.2 rispetto a V.5.1 (correzioni):
  - [FIX stale su curve SALTATE] Una curva che NON supera la propagazione
    (estremo orfano, tipo non gestito, ...) ma possiede gia' UserText
    parametrico da una passata precedente viene RIPULITA (PARAM_KEYS
    rimosse). In V.5.1 la pulizia avveniva solo dentro _write_user_text,
    cioe' solo per le curve ri-propagate con successo: una curva spostata,
    modificata, o un duplicato specchiato (SpecchiaCurve di PKG_Annotator
    <= v4.3) che ereditava lo UserText dell'originale veniva esportata con
    formule di una geometria che non esiste piu' e Status=associato.
    Le curve ripulite sono conteggiate nel report ('param_stale_ripuliti').
  - [Contratto pair_id] PKG_Annotator >= v4.4 scrive esplicitamente la
    UserString 'pair_id' sui punti. Il fallback dalle coordinate
    (make_pair_id_from_xy) resta per i punti annotati con QUALSIASI
    versione precedente (fino alla v4.3 inclusa la chiave non era scritta).

NOVITA V.5.1 rispetto a V.5.0 (correzioni):
  - [FIX stale-ref] Dopo la propagazione (ModifyAttributes) gli oggetti curva
    vengono RI-LETTI dal documento via FindId(obj.Id) prima dell'export.
    In V.5.0 l'export rileggeva lo UserText dallo stesso riferimento Python
    catturato prima della modifica: in RhinoCommon quel riferimento puo'
    essere stale e restituire attributi non aggiornati, producendo
    UserText='-' nel TXT pur dopo una propagazione riuscita.
  - [FIX angoli] La propagazione (_ut_for_arc) ora applica la STESSA
    convenzione di segno dell'export: arco CW (Plane.Normal.Z<0) -> angoli
    negativi. In V.5.0 la propagazione scriveva angoli RAW e l'export li
    invertiva, generando due rappresentazioni discordanti nello stesso file.
  - [FIX pulizia] Prima di scrivere il nuovo UserText parametrico su una
    curva, le chiavi parametriche precedenti vengono rimosse (PARAM_KEYS),
    cosi' un arco ri-elaborato come 'parziale' non conserva un Centro_id
    della passata precedente.
  - [FIX pair_id fallback] _collect_param_points: se il punto non ha la
    chiave 'pair_id' (annotato con PKG_Annotator < v4.1), l'id viene
    ricostruito dalle coordinate con lo stesso schema dell'annotator
    (PKG_X+0100_Y+0000), garantendo retrocompatibilita'.

NOVITA V.5 rispetto a V.4:
  - Prima dell'export, propaga le espressioni parametriche dai punti del
    layer PKG_Punti_Parametrici alle curve della selezione.
  - I punti parametrici con X_status o Y_status diversi da 'ok' sono
    esclusi dal pool sorgente.

WORKFLOW:
  1. Seleziona le curve da esportare.
  2. Lancia lo script.
  3. Scegli se esportare dopo il report di propagazione.
  4. Seleziona il path del TXT di output.
"""

import Rhino
import Rhino.Geometry as rg
import Rhino.DocObjects as rd
import scriptcontext as sc
import math
import os
import re


# ============================================================
#  COSTANTI PROPAGAZIONE PARAMETRICA
# ============================================================

TOL_SNAP        = 0.001   # mm: tolleranza per match punto<->estremo
ROUND_DIGITS    = 3       # cifre per chiave dizionario (coerente con TOL_SNAP)
LAYER_PUNTI     = "PKG_Punti_Parametrici"
STATUS_OK       = "ok"    # valore atteso in X_status / Y_status

# FIX v5.1: chiavi parametriche scritte dalla propagazione. Servono per
# ripulire lo UserText di una curva prima di riscriverlo, evitando residui
# di una passata precedente (es. Centro_id rimasto su un arco diventato
# parziale).
PARAM_KEYS = [
    "Comando", "Tipo_Originale",
    "P1_param", "P2_param", "P1_id", "P2_id",
    "Centro_param", "Centro_id", "Centro_geom", "Punto_medio",
    "Raggio", "Circonferenza",
    "AngStart_deg", "AngEnd_deg", "Verso",
    "CtrlProp_u", "CtrlProp_v", "CtrlPeso_w", "CtrlOff_x", "CtrlOff_y",
    "CtrlPoints", "Nodi",
    "Lunghezza", "Grado", "NumPunti", "Nota", "Status",
]


# ============================================================
#  COSTANTI SPECCHIATURA (linee cyan + blocchi)  [v5.3]
# ============================================================

# Numero di blocco nel testo utente dell'oggetto: raggruppa le geometrie che
# condividono lo stesso asse di specchiatura e ne indica l'ORDINE di
# esecuzione (1, 2, ...). Chiave proposta; rinominala qui se nel disegno usi
# un altro nome.
MIRROR_BLOCK_KEY = "Blocco"

# Ruolo emesso nel TXT sulla linea d'asse (per l'LLM: non e' geometria da
# tracciare, e' solo l'asse di riflessione).
MIRROR_ROLE_KEY  = "Ruolo"
MIRROR_AXIS_ROLE = "AsseSpecchio"           # ruolo generico (retrocompat.)

# v5.4: ruoli distinti per tipo di linea dell'asse cyan.
#   continua    -> simmetria: riflette e MANTIENE gli originali (scatola intera)
#   tratteggiata-> patella:   riflette e CANCELLA gli originali (vive la copia)
AXIS_ROLE_CONTINUOUS = "AsseSpecchio_Continuo"
AXIS_ROLE_DASHED     = "AsseSpecchio_Tratteggiato"

# La linea di specchiatura e' riconosciuta dal COLORE cyan (0,255,255), per
# oggetto o per layer. Tolleranza per-canale ampia ma sicura (il blu 0,0,255
# resta escluso: ha G lontano da 255).
COLOR_CYAN_RGB = (0, 255, 255)
CYAN_CH_TOL    = 40


# ============================================================
#  COSTANTI VARIABILI PARAMETRICHE  [v5.6]
# ============================================================

# Variabili packaging riconosciute. L'ordine e' quello di presentazione
# nel dialogo e nel TXT. Se nelle formule compaiono variabili non in
# lista, vengono aggiunte in coda (con placeholder vuoti).
PACKAGING_VARS_ORDER = ["L", "P", "A", "S", "C", "T", "E"]

# Placeholder per il dialogo. I valori sono tutti a 0: vanno compilati
# dall'utente col valore del MODELLO corrente (cambiano da modello a
# modello). Le descrizioni sono i nomi standard; l'utente puo'
# sovrascriverle nel dialogo e vengono salvate nel TXT.
PACKAGING_VAR_HINTS = {
    "L": {"default": 0.0, "min": 0.0, "max": 0.0,
           "desc": "Lunghezza"},
    "P": {"default": 0.0, "min": 0.0, "max": 0.0,
           "desc": "Profondita'"},
    "A": {"default": 0.0, "min": 0.0, "max": 0.0,
           "desc": "Altezza"},
    "S": {"default": 0.0, "min": 0.0, "max": 0.0,
           "desc": "Spessore Cartone"},
    "C": {"default": 0.0, "min": 0.0, "max": 0.0,
           "desc": "Lembo di Incollatura"},
    "T": {"default": 0.0, "min": 0.0, "max": 0.0,
           "desc": "Lembo di Chiusura"},
    "E": {"default": 0.0, "min": 0.0, "max": 0.0,
           "desc": "Bisello / Scarico Interno"},
}

# Pattern per estrarre variabili packaging dalle formule parametriche:
# lettera MAIUSCOLA singola non preceduta/seguita da lettera/underscore,
# cosi' 'PKG' non matcha ma 'L', 'L/2', 'P+S' si'.
_VAR_RE = re.compile(r'(?<![A-Za-z_])([A-Z])(?![A-Za-z_])')

# Variabili ammesse nelle espressioni di Min/Max (range).
# Derivato da PACKAGING_VARS_ORDER: L P A S C T E.
# Solo queste lettere maiuscole sono accettate nelle formule;
# qualsiasi altra lettera genera un errore di validazione.
ALLOWED_RANGE_VARS = set(PACKAGING_VARS_ORDER)   # {L,P,A,S,C,T,E}


# ============================================================
#  HELP DIALOG (Eto.Forms)
# ============================================================

def show_help():
    """Mostra finestra di aiuto con convenzioni colore e formato export."""
    import Eto.Forms as ef
    import Eto.Drawing as ed

    dlg = ef.Dialog()
    dlg.Title = "Esporta Geometrie Parametrico v5.6 - Guida"
    dlg.Padding = ed.Padding(16)
    dlg.MinimumSize = ed.Size(680, 560)
    dlg.Resizable = True

    layout = ef.DynamicLayout()
    layout.Spacing = ed.Size(8, 8)
    layout.DefaultSpacing = ed.Size(4, 4)

    title = ef.Label()
    title.Text = "ESPORTA GEOMETRIE PARAMETRICO v5.6"
    title.Font = ed.Font(ed.SystemFont.Bold, 13)
    layout.AddRow(title)
    layout.AddRow(ef.Label(Text=""))

    sec_uso = ef.Label()
    sec_uso.Text = "UTILIZZO"
    sec_uso.Font = ed.Font(ed.SystemFont.Bold, 11)
    layout.AddRow(sec_uso)

    uso = ef.Label()
    uso.Text = ("1. Selezionare curve e/o punti da esportare.\n"
                "2. Lo script propaga le espressioni parametriche\n"
                "   dai punti del layer 'PKG_Punti_Parametrici' alle curve.\n"
                "3. Viene generato un TXT tab-separated con una riga "
                "per oggetto/segmento\n   e la colonna UserText "
                "popolata con le espressioni parametriche.")
    layout.AddRow(uso)
    layout.AddRow(ef.Label(Text=""))

    sec_par = ef.Label()
    sec_par.Text = "PROPAGAZIONE PARAMETRICA"
    sec_par.Font = ed.Font(ed.SystemFont.Bold, 11)
    layout.AddRow(sec_par)

    par = ef.Label()
    par.Text = ("Per ogni curva, lo script cerca punti parametrici che "
                "coincidano\n(snap <= 0.001 mm) con i suoi estremi. Se "
                "entrambi gli estremi\nhanno un match, scrive nello user "
                "text della curva:\n"
                "  Comando        es. _Line, _Arc, _Circle, _InterpCrv\n"
                "  Tipo_Originale Line / Arc / Circle / Nurbs\n"
                "  P1_param       espressione del punto iniziale\n"
                "  P2_param       espressione del punto finale\n"
                "  P1_id, P2_id   pair_id dei punti sorgente\n"
                "  Raggio, Centro_param, AngStart, AngEnd (per archi/cerchi)\n"
                "  Status         associato | parziale")
    layout.AddRow(par)
    layout.AddRow(ef.Label(Text=""))

    sec_col = ef.Label()
    sec_col.Text = "CLASSIFICAZIONE (curve)"
    sec_col.Font = ed.Font(ed.SystemFont.Bold, 11)
    layout.AddRow(sec_col)

    col = ef.Label()
    col.Text = ("Layer 'Taglio'       -> Tipo T  (nero,  0,0,0)\n"
                "Layer 'Cordone'      -> Tipo C  (rosso, 255,0,0)\n"
                "Layer 'MezzoTaglio'  -> Tipo M  (verde, 0,255,0)\n"
                "Layer 'Foratore'     -> Tipo F  (blu,   0,0,255)\n"
                "Oggetti Point        -> Tipo P  (qualsiasi layer)")
    layout.AddRow(col)
    layout.AddRow(ef.Label(Text=""))

    sec_mir = ef.Label()
    sec_mir.Text = "SPECCHIATURA (v5.6)"
    sec_mir.Font = ed.Font(ed.SystemFont.Bold, 11)
    layout.AddRow(sec_mir)

    mir = ef.Label()
    mir.Text = ("Gli oggetti con UserString 'Blocco'=N formano un blocco\n"
                "(N e' anche l'ordine di esecuzione, dal piu' interno al\n"
                "piu' esterno). Dentro il blocco, la linea CYAN e' l'asse:\n"
                "  - CONTINUA    -> simmetria: riflette e MANTIENE l'origine\n"
                "  - TRATTEGGIATA-> patella:  riflette e CANCELLA l'origine\n"
                "L'export marca l'asse con Ruolo=AsseSpecchio_Continuo o\n"
                "AsseSpecchio_Tratteggiato e riassume i blocchi in testa al\n"
                "TXT. I blocchi si eseguono in ordine: ognuno opera su tutto\n"
                "cio' che esiste fino a quel punto. Un blocco con DUE tipi di\n"
                "asse (continuo+tratteggiato) e' un errore: export annullato.")
    layout.AddRow(mir)
    layout.AddRow(ef.Label(Text=""))

    sec_fmt = ef.Label()
    sec_fmt.Text = "FORMATO OUTPUT"
    sec_fmt.Font = ed.Font(ed.SystemFont.Bold, 11)
    layout.AddRow(sec_fmt)

    fmt_label = ef.Label()
    fmt_label.Text = ("Header:\n"
                "  # file.3dm | bbox: WxH | obj: N | segm: M | unita: ...\n"
                "  # Colonne: ID Tipo Geom Nome Layer X1 Y1 X2 Y2 R CX CY "
                "AngS AngE Len ...\n\n"
                "UserText: pairs concatenati con ';', formato chiave=valore.\n"
                "Valori vuoti = '-'. Decimali con punto.\n"
                "Angoli archi: convenzione con segno (CW = negativo) coerente\n"
                "tra UserText e colonne.")
    layout.AddRow(fmt_label)
    layout.AddRow(ef.Label(Text=""))

    btn_ok = ef.Button()
    btn_ok.Text = "OK"
    btn_ok.Click += lambda s, e: dlg.Close()
    layout.AddRow(None, btn_ok)

    dlg.Content = layout
    dlg.ShowModal(Rhino.UI.RhinoEtoApp.MainWindow)


def show_report_and_ask_export(n_aggiornate, n_saltate, reasons_dict,
                                n_punti_validi, n_curve_sel, n_punti_sel):
    """Mostra il report della propagazione e chiede se esportare su file.
    Ritorna (export, include_prompt):
      export        = True se l'utente vuole esportare
      include_prompt = True se vuole il prompt LLM in testa al TXT."""
    import Eto.Forms as ef
    import Eto.Drawing as ed

    result = {"export": False, "include_prompt": True}

    dlg = ef.Dialog()
    dlg.Title = "Esporta Geometrie Parametrico v5.6 - Report"
    dlg.Padding = ed.Padding(16)
    dlg.MinimumSize = ed.Size(480, 320)
    dlg.Resizable = False

    layout = ef.DynamicLayout()
    layout.Spacing = ed.Size(8, 8)
    layout.DefaultSpacing = ed.Size(4, 4)

    title = ef.Label()
    title.Text = "Propagazione parametrica completata"
    title.Font = ed.Font(ed.SystemFont.Bold, 12)
    layout.AddRow(title)
    layout.AddRow(ef.Label(Text=""))

    report_lines = []
    report_lines.append("Selezione: %d curve, %d punti" % (n_curve_sel, n_punti_sel))
    report_lines.append("Punti parametrici sorgente: %d (layer '%s')" % (
        n_punti_validi, LAYER_PUNTI))
    report_lines.append("")
    report_lines.append("Curve aggiornate:   %d" % n_aggiornate)
    report_lines.append("Curve saltate:      %d" % n_saltate)

    if reasons_dict:
        report_lines.append("")
        report_lines.append("Dettaglio:")
        for k, v in sorted(reasons_dict.items(), key=lambda kv: -kv[1]):
            report_lines.append("   - %s: %d" % (k, v))

    report = ef.Label()
    report.Text = "\n".join(report_lines)
    layout.AddRow(report)
    layout.AddRow(ef.Label(Text=""))

    question = ef.Label()
    question.Text = "Vuoi esportare i dati su file TXT?"
    question.Font = ed.Font(ed.SystemFont.Bold, 11)
    layout.AddRow(question)

    chk_prompt = ef.CheckBox()
    chk_prompt.Text = "Aggiungi prompt LLM in testa al file"
    chk_prompt.Checked = True
    layout.AddRow(chk_prompt)
    layout.AddRow(ef.Label(Text=""))

    btn_export = ef.Button()
    btn_export.Text = "Si, esporta su file"
    def on_export(s, e):
        result["export"] = True
        result["include_prompt"] = bool(chk_prompt.Checked)
        dlg.Close()
    btn_export.Click += on_export

    btn_close = ef.Button()
    btn_close.Text = "No, chiudi"
    def on_close(s, e):
        result["export"] = False
        dlg.Close()
    btn_close.Click += on_close

    layout.AddRow(btn_export, btn_close)

    dlg.Content = layout
    dlg.ShowModal(Rhino.UI.RhinoEtoApp.MainWindow)

    return result["export"], result["include_prompt"]


def show_variables_dialog(found_vars, inferred_defaults=None):
    """Mostra un dialogo Eto dove l'utente conferma/modifica i valori
    di default e i range (min, max) delle variabili parametriche.

    found_vars         : lista ordinata di nomi variabile estratti dalle formule.
    inferred_defaults  : {var: valore} dedotti dal disegno (pre-compilano il
                         campo Default). None o {} = nessun pre-fill.
    Ritorna una lista di dict [{"name","default","min","max","desc"}, ...]
    oppure None se l'utente preme 'Salta' (nessuna sezione variabili nel TXT).
    Lista vuota se non ci sono variabili (non viene mostrato il dialogo)."""
    import Eto.Forms as ef
    import Eto.Drawing as ed

    if not found_vars:
        return []

    if inferred_defaults is None:
        inferred_defaults = {}

    result = {"ok": False, "data": []}

    dlg = ef.Dialog()
    dlg.Title = "Esporta Geometrie Parametrico v5.6 - Variabili"
    dlg.Padding = ed.Padding(10)
    dlg.Resizable = False

    layout = ef.DynamicLayout()
    layout.Spacing = ed.Size(4, 2)
    layout.DefaultSpacing = ed.Size(4, 2)

    title = ef.Label()
    title.Text = "Variabili parametriche rilevate nelle formule"
    title.Font = ed.Font(ed.SystemFont.Bold, 11)
    layout.AddRow(title)

    note = ef.Label()
    note.Text = ("Conferma o modifica i valori di default e il range\n"
                 "ammissibile. Saranno scritti in testa al TXT esportato\n"
                 "e usati dall'LLM per validare l'input dello script.\n"
                 "Min e Max accettano anche formule (es. P-3, L/2+S).\n"
                 "Lettere ammesse: L P A S C T E (forzate maiuscole).")
    layout.AddRow(note)

    # Intestazione colonne
    hdr_var = ef.Label(Text="Var")
    hdr_var.Font = ed.Font(ed.SystemFont.Bold, 9)
    hdr_var.Width = 24
    hdr_def = ef.Label(Text="Default")
    hdr_def.Font = ed.Font(ed.SystemFont.Bold, 9)
    hdr_min = ef.Label(Text="Min")
    hdr_min.Font = ed.Font(ed.SystemFont.Bold, 9)
    hdr_max = ef.Label(Text="Max")
    hdr_max.Font = ed.Font(ed.SystemFont.Bold, 9)
    hdr_desc = ef.Label(Text="Descrizione")
    hdr_desc.Font = ed.Font(ed.SystemFont.Bold, 9)
    layout.AddRow(hdr_var, hdr_def, hdr_min, hdr_max, hdr_desc)

    # Righe editabili, una per variabile
    def _hint_str(val):
        """0.0 -> '' (campo vuoto): l'utente compila solo quelli che
        servono per il modello corrente."""
        if val is None or val == 0.0:
            return ""
        return str(val)

    rows_ui = []
    for vname in found_vars:
        hint = PACKAGING_VAR_HINTS.get(vname, {})

        # Il default viene dal DISEGNO (inferred_defaults) se disponibile,
        # altrimenti dal hint (che e' 0 = vuoto).
        inferred_val = inferred_defaults.get(vname)

        lbl = ef.Label(Text=vname)
        lbl.Font = ed.Font(ed.SystemFont.Bold, 10)
        lbl.Width = 24

        tb_def = ef.TextBox()
        if inferred_val is not None and inferred_val != 0.0:
            tb_def.Text = str(inferred_val)
        else:
            tb_def.Text = _hint_str(hint.get("default"))
        tb_def.Width = 64

        tb_min = ef.TextBox()
        tb_min.Text = _hint_str(hint.get("min"))
        tb_min.Width = 64

        tb_max = ef.TextBox()
        tb_max.Text = _hint_str(hint.get("max"))
        tb_max.Width = 64

        tb_desc = ef.TextBox()
        tb_desc.Text = hint.get("desc", "")
        tb_desc.Width = 170

        layout.AddRow(lbl, tb_def, tb_min, tb_max, tb_desc)
        rows_ui.append((vname, tb_def, tb_min, tb_max, tb_desc))

    btn_ok = ef.Button(Text="Conferma e esporta")
    def on_ok(s, e):
        def _parse_float(txt):
            try:
                return float(txt.strip().replace(",", "."))
            except Exception:
                return None

        def _parse_range(txt):
            """Parsa un campo Min/Max: accetta un numero oppure una
            espressione parametrica (es. 'P-3', 'L/2+S').
            Lettere forzate a maiuscolo; ammesse solo L P A S C T E.
            Valida anche la sintassi dell'espressione con eval.
            Ritorna (valore, errore):
              valore = float | str | None
              errore = str | None"""
            txt = txt.strip()
            if not txt:
                return None, None
            # Prova come float
            try:
                return float(txt.replace(",", ".")), None
            except ValueError:
                pass
            # E' un'espressione: forza maiuscolo
            expr = txt.upper()
            # Valida: solo lettere ammesse
            bad = set()
            for ch in expr:
                if ch.isalpha() and ch not in ALLOWED_RANGE_VARS:
                    bad.add(ch)
            if bad:
                return None, ("lettera '%s' non ammessa (solo %s)" %
                              ("".join(sorted(bad)),
                               " ".join(sorted(ALLOWED_RANGE_VARS))))
            # Valida sintassi: eval con tutte le variabili a 1
            try:
                ns = {}
                for v in ALLOWED_RANGE_VARS:
                    ns[v] = 1.0
                float(eval(expr, {"__builtins__": {}}, ns))
            except Exception:
                return None, ("espressione '%s' non valida" % expr)
            return expr, None

        data = []
        errors = []
        for (vname, tb_def, tb_min, tb_max, tb_desc) in rows_ui:
            min_val, min_err = _parse_range(tb_min.Text)
            max_val, max_err = _parse_range(tb_max.Text)
            if min_err:
                errors.append("Min di %s: %s" % (vname, min_err))
            if max_err:
                errors.append("Max di %s: %s" % (vname, max_err))
            data.append({
                "name":    vname,
                "default": _parse_float(tb_def.Text),
                "min":     min_val,
                "max":     max_val,
                "desc":    tb_desc.Text.strip(),
            })

        if errors:
            ef.MessageBox.Show(
                "\n".join(errors),
                "Variabili - errore di validazione")
            return   # resta aperto, l'utente corregge

        result["data"] = data
        result["ok"] = True
        dlg.Close()
    btn_ok.Click += on_ok

    btn_skip = ef.Button(Text="Salta (nessuna sezione variabili)")
    def on_skip(s, e):
        result["ok"] = False
        dlg.Close()
    btn_skip.Click += on_skip

    layout.AddRow(None, btn_ok, btn_skip)

    dlg.Content = layout
    dlg.ShowModal(Rhino.UI.RhinoEtoApp.MainWindow)

    if result["ok"]:
        return result["data"]
    return None


# ============================================================
#  PROPAGAZIONE PARAMETRICA - HELPERS
# ============================================================

def make_pair_id_from_xy(x, y):
    """Identificatore geometrico del punto. A risoluzione FINE: 0.001 mm, la
    stessa del match (ROUND_DIGITS). A millimetro intero due vertici distinti
    entro 0.5 mm avrebbero lo stesso id, e in cartotecnica bevel e spessore
    creano coordinate sub-millimetriche: la risoluzione fine evita il collasso.
    Formato leggibile, con segno e decimali: PKG_X+0100.000_Y-0030.500.
    PKG_Annotator non scrive la UserString 'pair_id' in alcuna versione,
    quindi questa e' SEMPRE la via con cui l'id viene costruito."""
    def tok(v):
        r = round(v, ROUND_DIGITS)
        s = "+" if r >= 0 else "-"
        return "%s%0*.*f" % (s, 8, ROUND_DIGITS, abs(r))
    return "PKG_X%s_Y%s" % (tok(x), tok(y))


def _parse_user_text_dict(rh_object):
    """Restituisce un dict dallo user text di un RhinoObject."""
    result = {}
    if rh_object is None:
        return result
    try:
        keys = rh_object.Attributes.GetUserStrings()
        if keys is None:
            return result
        for k in keys.AllKeys:
            result[k] = rh_object.Attributes.GetUserString(k)
    except Exception:
        pass
    return result


def _write_user_text(rh_object, data_dict):
    """Scrive un dict come user text sull'oggetto.
    USA Duplicate() perche' altrimenti ModifyAttributes e' un no-op silenzioso.
    FIX v5.1: prima rimuove le chiavi parametriche precedenti (PARAM_KEYS),
    cosi' non restano residui di una passata anteriore."""
    if rh_object is None or not data_dict:
        return False
    new_attrs = rh_object.Attributes.Duplicate()
    # Pulizia chiavi parametriche stale
    for k in PARAM_KEYS:
        try:
            new_attrs.DeleteUserString(k)
        except Exception:
            pass
    for k, v in data_dict.items():
        new_attrs.SetUserString(k, "%s" % v)
    return sc.doc.Objects.ModifyAttributes(rh_object, new_attrs, True)


def _clean_stale_param_keys(rh_object):
    """FIX v5.2: rimuove le PARAM_KEYS da una curva che NON supera la
    propagazione ma le possiede da una passata precedente.

    Casi reali: curva spostata o modificata dopo una propagazione riuscita;
    duplicato creato da SpecchiaCurve (PKG_Annotator <= v4.3) che ereditava
    lo UserText parametrico dell'originale. Senza pulizia, l'export
    emetterebbe per quella curva formule e Status=associato riferiti a una
    geometria che non esiste piu' (Centro_geom e Punto_medio sono per giunta
    coordinate assolute pre-modifica).

    La presenza della chiave 'Comando' fa da sentinella: e' scritta solo
    dalla propagazione. Ritorna True se l'oggetto e' stato modificato."""
    if rh_object is None:
        return False
    try:
        has_param = rh_object.Attributes.GetUserString("Comando")
    except Exception:
        has_param = None
    if not has_param:
        return False
    new_attrs = rh_object.Attributes.Duplicate()
    for k in PARAM_KEYS:
        try:
            new_attrs.DeleteUserString(k)
        except Exception:
            pass
    return sc.doc.Objects.ModifyAttributes(rh_object, new_attrs, True)


def _collect_param_points():
    """Costruisce { (x_round, y_round) : {param_x, param_y, pair_id} }
    leggendo i punti del layer LAYER_PUNTI con X_status=ok e Y_status=ok."""
    points_map = {}
    skipped_orphan = 0

    layer = sc.doc.Layers.FindName(LAYER_PUNTI)
    if layer is None:
        return points_map, skipped_orphan, False

    layer_index = layer.Index

    settings = rd.ObjectEnumeratorSettings()
    settings.ObjectTypeFilter = rd.ObjectType.Point
    settings.LayerIndexFilter = layer_index

    for obj in sc.doc.Objects.GetObjectList(settings):
        pt_geom = obj.Geometry
        if not isinstance(pt_geom, rg.Point):
            continue

        ut = _parse_user_text_dict(obj)
        x_status = ut.get("X_status", "")
        y_status = ut.get("Y_status", "")

        if x_status != STATUS_OK or y_status != STATUS_OK:
            skipped_orphan += 1
            continue

        loc = pt_geom.Location
        key = (round(loc.X, ROUND_DIGITS), round(loc.Y, ROUND_DIGITS))

        # pair_id: PKG_Annotator non scrive questa UserString in nessuna
        # versione, quindi l'id viene SEMPRE ricostruito dalle coordinate
        # (a 0.001 mm). Il ramo 'da UserString' resta pronto se in futuro
        # l'annotator inizia a scriverla (deve usare lo stesso schema).
        pid = ut.get("pair_id", "")
        if not pid:
            pid = make_pair_id_from_xy(loc.X, loc.Y)

        points_map[key] = {
            "param_x": ut.get("X_param", "?"),
            "param_y": ut.get("Y_param", "?"),
            "pair_id": pid,
        }

    return points_map, skipped_orphan, True


def _extract_variables_from_formulas(points_map):
    """Scansiona X_param e Y_param di tutti i punti parametrici e
    restituisce la lista ORDINATA di variabili packaging trovate.
    L'ordine segue PACKAGING_VARS_ORDER; eventuali variabili extra
    (non in lista) vengono aggiunte in coda, ordinate alfabeticamente."""
    found = set()
    for _key, entry in points_map.items():
        for field in ("param_x", "param_y"):
            formula = entry.get(field, "")
            for m in _VAR_RE.finditer(formula):
                found.add(m.group(1))
    # Ordina: prima le note, poi le extra
    ordered = [v for v in PACKAGING_VARS_ORDER if v in found]
    extra = sorted(found - set(PACKAGING_VARS_ORDER))
    ordered.extend(extra)
    return ordered


def _try_solve_linear(formula, var, target):
    """Risolve formula(var) = target per 'var', assumendo linearita'.
    Metodo a due punti: valuta f(var=0) e f(var=1) per ricavare
    intercetta e pendenza; poi verifica il risultato ricalcolando.
    Ritorna il valore di 'var' arrotondato, o None se non riesce
    (formula non lineare, errore di sintassi, divisione per zero)."""
    try:
        ns0 = {var: 0.0}
        ns1 = {var: 1.0}
        f0 = float(eval(formula, {"__builtins__": {}}, ns0))
        f1 = float(eval(formula, {"__builtins__": {}}, ns1))
        slope = f1 - f0
        if abs(slope) < 1e-12:
            return None
        result = (target - f0) / slope
        # Verifica: ricalcola con il risultato e controlla lo scarto
        ns_v = {var: result}
        check = float(eval(formula, {"__builtins__": {}}, ns_v))
        if abs(check - target) > 0.01:
            return None   # formula non lineare in var
        return round(result, ROUND_DIGITS)
    except Exception:
        return None


def _solve_variables_from_points(points_map):
    """Ricava i valori delle variabili parametriche dai punti,
    confrontando le coordinate reali con le espressioni parametriche.

    Ogni punto ha (real_x, real_y) e (X_param, Y_param): per esempio
    se real_x = 100 e X_param = 'L/2', allora L = 200.

    Strategia a due passate (iterativa):
      1. Risolve le formule a UNA sola incognita (es. L/2 = 100 -> L = 200)
      2. Sostituisce i valori noti nelle formule rimanenti e risolve quelle
         ridotte a una incognita, ripetendo finche' non si risolvono piu'
         variabili.

    Ritorna { "L": 200.0, "P": 150.0, "S": 0.5, ... }."""

    # Raccogli tutte le coppie (formula, valore_reale)
    equations = []
    for key, entry in points_map.items():
        real_x, real_y = key
        for field, real_val in (("param_x", real_x), ("param_y", real_y)):
            formula = entry.get(field, "").strip()
            if not formula or formula == "?":
                continue
            # Solo formule che contengono almeno una variabile
            if _VAR_RE.search(formula):
                equations.append((formula, real_val))

    solved = {}

    # Passata 1: formule a singola variabile
    for formula, value in equations:
        vars_in = set(_VAR_RE.findall(formula))
        if len(vars_in) != 1:
            continue
        var = list(vars_in)[0]
        if var in solved:
            continue
        val = _try_solve_linear(formula, var, value)
        if val is not None:
            solved[var] = val

    # Passate successive: sostituisci i noti e risolvi le rimanenti
    max_iter = 5
    changed = True
    while changed and max_iter > 0:
        changed = False
        max_iter -= 1
        for formula, value in equations:
            vars_in = set(_VAR_RE.findall(formula))
            unknown = vars_in - set(solved.keys())
            if len(unknown) != 1:
                continue
            var = list(unknown)[0]
            if var in solved:
                continue
            # Sostituisci i valori noti nella formula
            subst = formula
            for sv, sval in solved.items():
                subst = re.sub(
                    r'(?<![A-Za-z_])' + sv + r'(?![A-Za-z_])',
                    "%.6f" % sval, subst)
            val = _try_solve_linear(subst, var, value)
            if val is not None:
                solved[var] = val
                changed = True

    return solved


def _lookup_param(points_map, x, y):
    """Cerca un punto nel dizionario con snap esatto a ROUND_DIGITS cifre."""
    key = (round(x, ROUND_DIGITS), round(y, ROUND_DIGITS))
    return points_map.get(key, None)


def _fmt_param_expr(entry):
    """Formatta '(X_param, Y_param)' da un'entry del dizionario."""
    if entry is None:
        return "non_associato"
    return "(%s, %s)" % (entry["param_x"], entry["param_y"])


def _signed_angles_deg(arc):
    """FIX v5.1: angoli inizio/fine in gradi con la convenzione di segno
    usata anche dall'export: arco CW (Plane.Normal.Z<0) -> angoli negativi.
    Ritorna (start_deg, end_deg)."""
    start_deg = math.degrees(arc.StartAngle)
    end_deg   = math.degrees(arc.EndAngle)
    if arc.Plane.Normal.Z < 0:
        start_deg = -start_deg
        end_deg   = -end_deg
    return start_deg, end_deg


# ============================================================
#  PROPAGAZIONE: GENERATORI USER TEXT PER TIPO
# ============================================================

def _ut_for_line(p1_entry, p2_entry, line):
    return {
        "Comando":         "_Line",
        "Tipo_Originale":  "Line",
        "P1_param":        _fmt_param_expr(p1_entry),
        "P2_param":        _fmt_param_expr(p2_entry),
        "P1_id":           p1_entry["pair_id"],
        "P2_id":           p2_entry["pair_id"],
        "Lunghezza":       "%.4f" % line.Length,
        "Status":          "associato",
    }


def _ut_for_arc(p1_entry, p2_entry, arc, centro_entry):
    start_deg, end_deg = _signed_angles_deg(arc)  # FIX v5.1: segno coerente
    data = {
        "Comando":         "_Arc",
        "Tipo_Originale":  "Arc",
        "P1_param":        _fmt_param_expr(p1_entry),
        "P2_param":        _fmt_param_expr(p2_entry),
        "P1_id":           p1_entry["pair_id"],
        "P2_id":           p2_entry["pair_id"],
        "Centro_param":    _fmt_param_expr(centro_entry),
        "Raggio":          "%.4f" % arc.Radius,
        "AngStart_deg":    "%.4f" % start_deg,
        "AngEnd_deg":      "%.4f" % end_deg,
        "Lunghezza":       "%.4f" % arc.Length,
        "Verso":           "CW" if arc.Plane.Normal.Z < 0 else "CCW",
        "Status":          "associato" if centro_entry is not None else "parziale",
    }
    if centro_entry is not None:
        data["Centro_id"] = centro_entry["pair_id"]
    # ROBUSTEZZA (toolkit condiviso): salva SEMPRE il centro geometrico
    # assoluto, anche quando non e' un punto annotato. Dati due estremi +
    # raggio esistono fino a 4 archi possibili (centro su un lato o l'altro
    # della corda, arco minore o maggiore): il solo Verso non basta a
    # disambiguare. Il centro esplicito + raggio + estremi rende la
    # ricostruzione univoca in ogni caso, indipendentemente dal tipo di
    # scatola. Coordinate assolute in mm (non parametriche).
    data["Centro_geom"] = "%.6f,%.6f" % (arc.Center.X, arc.Center.Y)
    # Punto a META' arco: consente la ricostruzione canonica a TRE PUNTI
    # (start, mid, end) con rg.Arc(p_start, p_mid, p_end), che e' univoca
    # e immune alle ambiguita' di piano/segno/verso. E' la via piu' solida
    # per archi generici (non solo semicerchi).
    mid_pt = arc.PointAt((arc.StartAngle + arc.EndAngle) * 0.5)
    data["Punto_medio"] = "%.6f,%.6f" % (mid_pt.X, mid_pt.Y)
    return data


def _ut_for_circle(circle, centro_entry):
    return {
        "Comando":         "_Circle",
        "Tipo_Originale":  "Circle",
        "Centro_param":    _fmt_param_expr(centro_entry),
        "Centro_id":       centro_entry["pair_id"],
        "Raggio":          "%.4f" % circle.Radius,
        "Circonferenza":   "%.4f" % (2.0 * math.pi * circle.Radius),
        "Status":          "associato",
    }


TOL_DEGEN = 1e-6   # soglia per estremi allineati su un asse (dx o dy nulli)


def _conic_proportion(nurbs):
    """Per una Bezier quadratica (grado 2, 3 punti di controllo) calcola la
    FIRMA DI FORMA del raccordo: la terna (u, v, w).

      u, v = posizione del punto di controllo intermedio come frazione del
             rettangolo definito dai due estremi: u sull'asse X, v sull'asse Y.
             Sono ADIMENSIONALI: la stessa curva si riadatta a qualsiasi
             rettangolo definito dai due estremi parametrici.
      w    = peso del punto di controllo intermedio. Se w=1 la curva e' una
             parabola; se w!=1 e' una conica (arco di ellisse/iperbole).
             Senza w il raccordo non e' ricostruibile fedelmente.

    Caso degenere: raccordo tra estremi allineati su un asse (parallele).
    Se dx~0 oppure dy~0, la frazione su quell'asse non e' definita: viene
    marcata 'degenere' e si salva l'offset assoluto del CP come fallback,
    cosi' la ricostruzione resta possibile senza divisione per zero.

    Ritorna un dict di stringhe gia' pronte per lo UserText, o None se la
    curva non e' una quadratica a 3 CP (in tal caso il raccordo resta
    gestito come prima, con i soli estremi parametrici)."""
    if nurbs.Degree != 2 or nurbs.Points.Count != 3:
        return None

    p1 = nurbs.Points[0].Location
    cp = nurbs.Points[1].Location
    p2 = nurbs.Points[2].Location

    # peso del CP intermedio (Weight e' 1.0 per le curve non razionali)
    try:
        w = nurbs.Points[1].Weight
    except Exception:
        w = 1.0

    dx = p2.X - p1.X
    dy = p2.Y - p1.Y

    data = {"CtrlPeso_w": "%.6f" % w}

    if abs(dx) > TOL_DEGEN:
        data["CtrlProp_u"] = "%.6f" % ((cp.X - p1.X) / dx)
    else:
        data["CtrlProp_u"] = "degenere"
        data["CtrlOff_x"]  = "%.6f" % (cp.X - p1.X)

    if abs(dy) > TOL_DEGEN:
        data["CtrlProp_v"] = "%.6f" % ((cp.Y - p1.Y) / dy)
    else:
        data["CtrlProp_v"] = "degenere"
        data["CtrlOff_y"]  = "%.6f" % (cp.Y - p1.Y)

    return data


def _nurbs_full_cp(nurbs):
    """ROBUSTEZZA (toolkit condiviso): serializza i punti di controllo
    completi di una NURBS, con coordinate, peso e vettore dei nodi.
    Serve per le curve che NON sono quadratiche a 3 CP (grado 3+, spline a
    piu' campate): per queste la firma (u,v,w) non basta, ma salvando tutti
    i CP + pesi + nodi la forma resta ricostruibile al 100% (in forma
    geometrica esatta, non parametrica). Coordinate assolute in mm.

    Formato CtrlPoints: 'x,y,w;x,y,w;...'
    Formato Nodi: 't0;t1;...' (knot vector)."""
    cps = []
    for i in range(nurbs.Points.Count):
        cp = nurbs.Points[i]
        loc = cp.Location
        try:
            w = cp.Weight
        except Exception:
            w = 1.0
        cps.append("%.6f,%.6f,%.6f" % (loc.X, loc.Y, w))
    knots = []
    try:
        for i in range(nurbs.Knots.Count):
            knots.append("%.6f" % nurbs.Knots[i])
    except Exception:
        pass
    # Separatore '|' tra punti/nodi: sopravvive alla sanitizzazione di
    # get_user_text (che converte ';' in ',' per non rompere il formato TXT).
    # Usare ';' qui corromperebbe i dati. Dentro ogni punto, ',' separa
    # x,y,w (la sanitize non tocca le virgole interne ai valori).
    return {
        "CtrlPoints": "|".join(cps),
        "Nodi":       "|".join(knots),
    }


def _ut_for_nurbs(p1_entry, p2_entry, nurbs):
    data = {
        "Comando":         "_InterpCrv",
        "Tipo_Originale":  "Nurbs",
        "P1_param":        _fmt_param_expr(p1_entry),
        "P2_param":        _fmt_param_expr(p2_entry),
        "P1_id":           p1_entry["pair_id"],
        "P2_id":           p2_entry["pair_id"],
        "Grado":           "%d" % nurbs.Degree,
        "NumPunti":        "%d" % nurbs.Points.Count,
        "Lunghezza":       "%.4f" % nurbs.GetLength(),
        "Status":          "associato",
    }

    # Per le quadratiche a 3 CP il raccordo e' INTERAMENTE parametrico:
    # estremi + firma di forma (u, v, w), e si riadatta quando cambiano i
    # parametri. Per gli altri gradi salviamo i CP completi: la forma e'
    # ricostruibile esattamente, anche se fissa (non riscalabile).
    prop = _conic_proportion(nurbs)
    if prop is not None:
        data.update(prop)
        data["Nota"] = "Raccordo conico: estremi + proporzione (u,v) e peso w del controllo"
    else:
        data.update(_nurbs_full_cp(nurbs))
        data["Nota"] = "Curva libera: CP completi (x,y,w) + nodi per ricostruzione esatta"

    return data


# ============================================================
#  PROPAGAZIONE: PROCESSING SINGOLA CURVA
# ============================================================

def _process_curve_for_param(obj, points_map):
    """Analizza un RhinoObject curva; se entrambi gli estremi matchano
    ritorna (dict_da_scrivere, esito). Altrimenti (None, motivo)."""
    curve = obj.Geometry
    if not isinstance(curve, rg.Curve):
        return None, "non_curve"

    is_circle, circle = curve.TryGetCircle(Rhino.RhinoMath.ZeroTolerance)
    if is_circle:
        c_entry = _lookup_param(points_map, circle.Center.X, circle.Center.Y)
        if c_entry is None:
            return None, "circle_centro_orfano"
        return _ut_for_circle(circle, c_entry), "ok"

    is_arc, arc = curve.TryGetArc(Rhino.RhinoMath.ZeroTolerance)
    if is_arc:
        p1_entry = _lookup_param(points_map, arc.StartPoint.X, arc.StartPoint.Y)
        p2_entry = _lookup_param(points_map, arc.EndPoint.X, arc.EndPoint.Y)
        if p1_entry is None or p2_entry is None:
            return None, "arc_estremo_orfano"
        c_entry = _lookup_param(points_map, arc.Center.X, arc.Center.Y)
        return _ut_for_arc(p1_entry, p2_entry, arc, c_entry), "ok"

    if curve.IsLinear(Rhino.RhinoMath.ZeroTolerance):
        p_start = curve.PointAtStart
        p_end   = curve.PointAtEnd
        line    = rg.Line(p_start, p_end)
        p1_entry = _lookup_param(points_map, p_start.X, p_start.Y)
        p2_entry = _lookup_param(points_map, p_end.X, p_end.Y)
        if p1_entry is None or p2_entry is None:
            return None, "line_estremo_orfano"
        return _ut_for_line(p1_entry, p2_entry, line), "ok"

    is_nurbs_like = (
        isinstance(curve, rg.NurbsCurve) or
        isinstance(curve, rg.PolylineCurve) or
        curve.Degree > 1
    )
    if is_nurbs_like:
        nurbs = curve.ToNurbsCurve()
        if nurbs is None:
            return None, "nurbs_conversion_failed"
        p_start = nurbs.PointAtStart
        p_end   = nurbs.PointAtEnd
        p1_entry = _lookup_param(points_map, p_start.X, p_start.Y)
        p2_entry = _lookup_param(points_map, p_end.X, p_end.Y)
        if p1_entry is None or p2_entry is None:
            return None, "nurbs_estremo_orfano"
        return _ut_for_nurbs(p1_entry, p2_entry, nurbs), "ok"

    return None, "tipo_non_gestito"


def propaga_parametrico(curve_objs):
    """Esegue la propagazione sui curve_objs forniti.
    Ritorna (n_aggiornate, n_saltate, reasons_dict, n_punti_validi)."""
    print("-" * 60)
    print("PROPAGAZIONE PARAMETRICA")
    print("Tolleranza snap: %.4f mm | Layer punti: %s" % (
        TOL_SNAP, LAYER_PUNTI))

    points_map, skipped_orphan, layer_ok = _collect_param_points()
    if not layer_ok:
        print("  [ERRORE] Layer '%s' non trovato." % LAYER_PUNTI)
        return 0, 0, {}, 0

    print("  Punti parametrici validi: %d" % len(points_map))
    if skipped_orphan > 0:
        print("  Punti con status non-ok ignorati: %d" % skipped_orphan)

    if len(points_map) == 0:
        print("  [AVVISO] Nessun punto parametrico valido.")
        return 0, 0, {}, 0

    aggiornate = 0
    saltate    = 0
    reasons    = {}

    for obj in curve_objs:
        ut_data, esito = _process_curve_for_param(obj, points_map)
        if ut_data is None:
            saltate += 1
            reasons[esito] = reasons.get(esito, 0) + 1
            # FIX v5.2: la curva saltata puo' portare UserText parametrico
            # di una passata precedente (curva modificata, o duplicato di
            # SpecchiaCurve che lo ha ereditato): va ripulito, altrimenti
            # l'export lo emette come se fosse ancora valido.
            if _clean_stale_param_keys(obj):
                reasons["param_stale_ripuliti"] = \
                    reasons.get("param_stale_ripuliti", 0) + 1
            continue
        ok = _write_user_text(obj, ut_data)
        if ok:
            aggiornate += 1
        else:
            saltate += 1
            reasons["write_failed"] = reasons.get("write_failed", 0) + 1

    sc.doc.Views.Redraw()

    print("  Curve aggiornate: %d" % aggiornate)
    print("  Curve saltate:    %d" % saltate)
    if reasons:
        for k, v in sorted(reasons.items(), key=lambda kv: -kv[1]):
            print("     - %-30s %d" % (k, v))

    return aggiornate, saltate, reasons, len(points_map)


# ============================================================
#  EXPORT - HELPERS (dal V.4)
# ============================================================

def fmt(val, decimals=2):
    """Formatta un numero con N decimali (default 2)."""
    if val is None:
        return "-"
    return str(round(val, decimals))


def classify_curve(obj):
    """Determina il tipo T/C/M/F dal layer name e colore effettivo."""
    layer = sc.doc.Layers[obj.Attributes.LayerIndex]
    lname = layer.Name.lower().strip()

    if "mezzotaglio" in lname or "mezzo_taglio" in lname or "mezzo taglio" in lname:
        return "M"
    if "foratore" in lname or "foratura" in lname:
        return "F"
    if "cordone" in lname or "cordonatura" in lname or "piega" in lname:
        return "C"
    if "taglio" in lname or "cut" in lname or "fustella" in lname:
        return "T"

    attr = obj.Attributes
    if attr.ColorSource == Rhino.DocObjects.ObjectColorSource.ColorFromLayer:
        color = layer.Color
    else:
        color = attr.ObjectColor

    r, g, b = int(color.R), int(color.G), int(color.B)

    if r > 200 and g < 60 and b < 60:
        return "C"
    if r < 60 and g > 200 and b < 60:
        return "M"
    if r < 60 and g < 60 and b > 200:
        return "F"
    return "T"


def get_layer_name(obj):
    return sc.doc.Layers[obj.Attributes.LayerIndex].Name


def get_object_name(obj):
    name = obj.Attributes.Name
    if name is None or name == "":
        return "-"
    return name


def get_user_text(obj):
    """Estrae tutti gli User Text dell'oggetto come 'k1=v1;k2=v2'."""
    nvc = obj.Attributes.GetUserStrings()
    if nvc is None or nvc.Count == 0:
        return "-"
    pairs = []
    for i in range(nvc.Count):
        k = nvc.GetKey(i)
        v = nvc.Get(k)
        k_safe = k.replace("\t", " ").replace(";", ",").replace("=", ":")
        v_safe = v.replace("\t", " ").replace(";", ",").replace("=", ":")
        pairs.append("%s=%s" % (k_safe, v_safe))
    return ";".join(pairs)


# ============================================================
#  EXPORT - GEOMETRIA
# ============================================================

def explode_curve(curve):
    """Scompone una PolyCurve in segmenti elementari."""
    if isinstance(curve, rg.PolyCurve):
        segments = []
        for i in range(curve.SegmentCount):
            seg = curve.SegmentCurve(i)
            segments.extend(explode_curve(seg))
        return segments
    if isinstance(curve, rg.PolylineCurve):
        pl = curve.ToPolyline()
        segments = []
        for i in range(pl.Count - 1):
            lc = rg.LineCurve(pl[i], pl[i + 1])
            segments.append(lc)
        return segments
    return [curve]


def extract_arc_data(curve):
    """Estrae i dati di un arco con segno corretto (CW = negativo)."""
    success, arc = curve.TryGetArc()
    if not success:
        return None
    start_deg = math.degrees(arc.StartAngle)
    end_deg = math.degrees(arc.EndAngle)
    if arc.Plane.Normal.Z < 0:
        start_deg = -start_deg
        end_deg = -end_deg
    return {
        "R": arc.Radius,
        "CX": arc.Plane.Origin.X,
        "CY": arc.Plane.Origin.Y,
        "AngS": start_deg,
        "AngE": end_deg,
    }


def detect_geometry(curve):
    """Rileva tipo geometrico e ritorna (geom_tag, extra_dict)."""
    if isinstance(curve, rg.LineCurve) or curve.IsLinear():
        return "Line", {}

    arc_data = extract_arc_data(curve)
    if arc_data is not None:
        return "Arc", arc_data

    success_pl, polyline = curve.TryGetPolyline()
    if success_pl:
        pts_str = ";".join(
            "%s,%s" % (fmt(polyline[i].X), fmt(polyline[i].Y))
            for i in range(polyline.Count)
        )
        return "Poly", {"Pts": pts_str}

    nurbs = curve.ToNurbsCurve()
    if nurbs is not None:
        deg = nurbs.Degree
        is_rational = nurbs.IsRational
        cp_parts = []
        for i in range(nurbs.Points.Count):
            cp = nurbs.Points[i]
            pt = cp.Location
            if is_rational:
                w = cp.Weight
                cp_parts.append("%s,%s,%s" % (
                    fmt(pt.X), fmt(pt.Y), fmt(w, 3)))
            else:
                cp_parts.append("%s,%s" % (fmt(pt.X), fmt(pt.Y)))
        cp_str = ";".join(cp_parts)
        extra = {"Deg": str(deg), "CP": cp_str}

        if deg > 2 or nurbs.Points.Count > 4:
            n_samples = 8
            samples = []
            t0 = nurbs.Domain.T0
            t1 = nurbs.Domain.T1
            for i in range(n_samples + 1):
                t = t0 + (t1 - t0) * i / float(n_samples)
                p = nurbs.PointAt(t)
                samples.append("%s,%s" % (fmt(p.X), fmt(p.Y)))
            extra["Sampled"] = ";".join(samples)

        return "Nurbs", extra

    return "Nurbs", {}


# ============================================================
#  EXPORT - COSTRUZIONE RIGHE
# ============================================================

COLUMNS = ["ID", "Tipo", "Geom", "Nome", "Layer",
           "X1", "Y1", "X2", "Y2",
           "R", "CX", "CY", "AngS", "AngE",
           "Len", "Deg", "Pts", "CP", "Sampled",
           "Blocco", "Ruolo", "UserText"]


def row_for_point(idx, obj, usertext_override=None, block="-", role="-"):
    pt = obj.Geometry.Location
    ut = usertext_override if usertext_override is not None else get_user_text(obj)
    row = {
        "ID": str(idx),
        "Tipo": "P",
        "Geom": "Point",
        "Nome": get_object_name(obj),
        "Layer": get_layer_name(obj),
        "X1": fmt(pt.X),
        "Y1": fmt(pt.Y),
        "X2": fmt(pt.Z),
        "Blocco": block,
        "Ruolo": role,
        "UserText": ut,
    }
    return row


def row_for_segment(idx, obj, segment, tipo, usertext_override=None, block="-", role="-"):
    p0 = segment.PointAtStart
    p1 = segment.PointAtEnd
    geom_tag, extra = detect_geometry(segment)
    ut = usertext_override if usertext_override is not None else get_user_text(obj)

    row = {
        "ID": str(idx),
        "Tipo": tipo,
        "Geom": geom_tag,
        "Nome": get_object_name(obj),
        "Layer": get_layer_name(obj),
        "X1": fmt(p0.X),
        "Y1": fmt(p0.Y),
        "X2": fmt(p1.X),
        "Y2": fmt(p1.Y),
        "Len": fmt(segment.GetLength()),
        "Blocco": block,
        "Ruolo": role,
        "UserText": ut,
    }

    if "R" in extra:        row["R"]       = fmt(extra["R"])
    if "CX" in extra:       row["CX"]      = fmt(extra["CX"])
    if "CY" in extra:       row["CY"]      = fmt(extra["CY"])
    if "AngS" in extra:     row["AngS"]    = fmt(extra["AngS"])
    if "AngE" in extra:     row["AngE"]    = fmt(extra["AngE"])
    if "Deg" in extra:      row["Deg"]     = extra["Deg"]
    if "Pts" in extra:      row["Pts"]     = extra["Pts"]
    if "CP" in extra:       row["CP"]      = extra["CP"]
    if "Sampled" in extra:  row["Sampled"] = extra["Sampled"]

    return row


def format_row(row):
    cells = []
    for col in COLUMNS:
        cells.append(row.get(col, "-"))
    return "\t".join(cells)


# ============================================================
#  EXPORT - SCRITTURA FILE
# ============================================================

def _refetch(obj):
    """FIX v5.1: ri-legge l'oggetto dal documento via Id, cosi' gli
    Attributes (e lo UserText appena scritto in propagazione) sono freschi.
    Se il refetch fallisce, ritorna l'oggetto originale come fallback."""
    try:
        fresh = sc.doc.Objects.FindId(obj.Id)
        if fresh is not None:
            return fresh
    except Exception:
        pass
    return obj


# ============================================================
#  SPECCHIATURA: rilevamento blocchi e assi cyan  [v5.3]
# ============================================================

def _effective_color(obj):
    """Colore effettivo dell'oggetto (per-oggetto se impostato, senno' del
    layer). Stessa logica di classify_curve."""
    attr = obj.Attributes
    if attr.ColorSource == rd.ObjectColorSource.ColorFromLayer:
        return sc.doc.Layers[attr.LayerIndex].Color
    return attr.ObjectColor


def _show_blocking_error(messages):
    """Mostra un message box con gli errori bloccanti della specchiatura.
    Guardato da try: se la UI non e' disponibile, resta il print su console."""
    try:
        body = ("Export annullato.\n\nConflitto sugli assi di "
                "specchiatura:\n\n- " + "\n- ".join(messages) +
                "\n\nUn blocco ammette UN solo asse: linea continua "
                "(simmetria) OPPURE tratteggiata (patella).")
        Rhino.UI.Dialogs.ShowMessage(
            body, "Esporta Geometrie Parametrico v5.6 - Errore")
    except Exception:
        pass


def _is_cyan(color):
    """True se il colore e' cyan. Test assoluto (entro CYAN_CH_TOL da
    0,255,255) con fallback RELAZIONALE: rosso basso, verde e blu alti e
    simili tra loro. Cosi' riconosce anche tonalita' di cyan non perfette."""
    r, g, b = int(color.R), int(color.G), int(color.B)
    cr, cg, cb = COLOR_CYAN_RGB
    if (abs(r - cr) <= CYAN_CH_TOL and
            abs(g - cg) <= CYAN_CH_TOL and
            abs(b - cb) <= CYAN_CH_TOL):
        return True
    if r < 110 and g > 140 and b > 140 and abs(g - b) <= 90:
        return True
    return False


def _linear_tol():
    """Tolleranza per il test di linearita': tolleranza del documento, con
    un minimo prudente. Piu' permissiva di ZeroTolerance (che scartava
    segmenti tratteggiati/polilinee non perfettamente rettilinei)."""
    try:
        return max(sc.doc.ModelAbsoluteTolerance, 0.001)
    except Exception:
        return 0.001


def _is_linear_curve(g):
    """True se la geometria e' una curva lineare (entro _linear_tol)."""
    if not isinstance(g, rg.Curve):
        return False
    try:
        if g.IsLinear(_linear_tol()):
            return True
    except Exception:
        pass
    try:
        return g.IsLinear()
    except Exception:
        return False


def _block_number(obj):
    """Numero di blocco dell'oggetto (UserString MIRROR_BLOCK_KEY) o ''.
    Fallback usato solo quando nella selezione non ci sono gruppi Rhino."""
    try:
        v = obj.Attributes.GetUserString(MIRROR_BLOCK_KEY)
    except Exception:
        v = None
    return (v or "").strip()


def _object_groups(obj):
    """Lista degli indici dei gruppi Rhino a cui l'oggetto appartiene (puo'
    appartenere a piu' gruppi: e' cosi' che si modellano le matrioske)."""
    try:
        arr = obj.Attributes.GetGroupList()
    except Exception:
        arr = None
    if not arr:
        return []
    out = []
    for x in arr:
        try:
            out.append(int(x))
        except Exception:
            pass
    return out


def _selection_has_groups(objs):
    """True se almeno un oggetto della selezione appartiene a un gruppo Rhino."""
    for obj in objs:
        if _object_groups(obj):
            return True
    return False


def _effective_linetype_index(obj):
    """Indice del linetype EFFETTIVO dell'oggetto: per-oggetto se la sorgente
    e' 'da oggetto', altrimenti quello del layer. Speculare a _effective_color.
    Ritorna un intero (puo' essere -1 = default/continuo)."""
    attr = obj.Attributes
    try:
        src = attr.LinetypeSource
    except Exception:
        return attr.LinetypeIndex
    if src == rd.ObjectLinetypeSource.LinetypeFromLayer:
        try:
            return sc.doc.Layers[attr.LayerIndex].LinetypeIndex
        except Exception:
            return -1
    # LinetypeFromObject e LinetypeFromParent: usa l'indice dell'oggetto
    return attr.LinetypeIndex


def _is_continuous_linetype(idx):
    """True se il linetype di indice 'idx' e' CONTINUO. Il giudizio si basa
    sulla STRUTTURA del pattern, non sul nome (robusto a lingua/template):
      - idx < 0                         -> default = continuo
      - idx == ContinuousLinetypeIndex  -> continuo del documento
      - linetype senza segmenti / pattern nullo -> continuo
    Qualsiasi pattern con segmenti (dash, dash-dot, ...) e' NON continuo, e
    in questo script viene trattato come TRATTEGGIATO (patella)."""
    if idx < 0:
        return True
    try:
        if idx == sc.doc.Linetypes.ContinuousLinetypeIndex:
            return True
    except Exception:
        pass
    try:
        lt = sc.doc.Linetypes[idx]
    except Exception:
        lt = None
    if lt is None:
        return True
    try:
        if lt.SegmentCount == 0:
            return True
    except Exception:
        pass
    try:
        if lt.PatternLength <= 0.0:
            return True
    except Exception:
        pass
    return False


def _cyan_axis_role(obj):
    """Se l'oggetto e' una LINEA cyan (asse di specchiatura), ritorna il ruolo
    in base al tipo di linea: AXIS_ROLE_CONTINUOUS (simmetria, origine resta)
    oppure AXIS_ROLE_DASHED (patella, origine cancellata). Ritorna None se
    l'oggetto NON e' una linea cyan."""
    g = obj.Geometry
    if not _is_linear_curve(g):
        return None
    if not _is_cyan(_effective_color(obj)):
        return None
    idx = _effective_linetype_index(obj)
    if _is_continuous_linetype(idx):
        return AXIS_ROLE_CONTINUOUS
    return AXIS_ROLE_DASHED


def _linetype_debug(obj):
    """Ritorna (nome, segmenti, lunghezza_pattern, continuo?) del linetype
    effettivo: usato dalla diagnostica per spiegare le classificazioni."""
    idx = _effective_linetype_index(obj)
    name, seg, plen = "?", "?", "?"
    try:
        if idx < 0:
            name = "(default/continuo)"
        else:
            lt = sc.doc.Linetypes[idx]
            name = lt.Name
            try:
                seg = str(lt.SegmentCount)
            except Exception:
                pass
            try:
                plen = "%.3f" % lt.PatternLength
            except Exception:
                pass
    except Exception:
        pass
    return name, seg, plen, _is_continuous_linetype(idx)


def _resolve_mirror_steps(objs):
    """Determina i PASSI di specchiatura. Meccanismo primario: i GRUPPI Rhino
    (_Group). Ogni gruppo che contiene una linea cyan definisce un passo; la
    linea cyan ne e' l'asse e ne fissa il tipo (continua=simmetria, origine
    mantenuta; tratteggiata=patella, origine cancellata). Un oggetto puo'
    stare in piu' gruppi: e' cosi' che si annidano le matrioske.

    Ordine di esecuzione: dal passo piu' INTERNO (meno membri) al piu'
    ESTERNO (piu' membri); a parita', le patelle prima della simmetria.
    Per le matrioske i membri del passo interno sono un sottoinsieme di
    quelli del passo esterno, quindi il passo esterno li rispecchia di nuovo.

    Fallback retrocompatibile: se nella selezione NON ci sono gruppi Rhino,
    si usa la vecchia UserString 'Blocco' (numero = passo).

    Ritorna (step_list_of, steps, errors, warns):
      step_list_of : { obj.Id(str) : "1,2" | "1" | "-" }
                     per le curve membre: lista (CSV) dei passi a cui
                     partecipano; per le linee-asse: il passo che definiscono.
      steps        : [ {"order":k, "axis":obj, "role":str,
                        "member_ids":set(str), "n_membri":int} ]  ordinati
      errors       : [str] bloccanti     warns: [str] avvisi
    """
    if _selection_has_groups(objs):
        return _resolve_steps_by_groups(objs)
    return _resolve_steps_by_userstring(objs)


def _resolve_steps_by_groups(objs):
    errors = []
    warns = []

    # 1) Individua gli assi (linee cyan) e il loro tipo.
    axis_ids = set()
    axes = []  # (obj, role, [gruppi])
    for obj in objs:
        role = _cyan_axis_role(obj)
        if role is not None:
            axis_ids.add(str(obj.Id))
            axes.append((obj, role, _object_groups(obj)))

    # 2) Membri (NON-asse) per ciascun gruppo.
    group_member_ids = {}
    for obj in objs:
        oid = str(obj.Id)
        if oid in axis_ids:
            continue
        for g in _object_groups(obj):
            group_member_ids.setdefault(g, set()).add(oid)

    # 3) Ogni asse definisce un passo: gruppo definitorio = il piu' piccolo
    #    (meno membri) che lo contiene = il livello piu' interno dell'asse.
    steps_raw = []  # (axis_obj, role, gidx, member_id_set)
    for (axobj, role, groups) in axes:
        if not groups:
            warns.append("Asse cyan %s non appartiene ad alcun gruppo Rhino: "
                         "impossibile sapere cosa riflettere. Raggruppalo "
                         "(_Group) con le sue curve." % str(axobj.Id)[:8])
            continue
        gsel, gsize = None, None
        for g in groups:
            sz = len(group_member_ids.get(g, set()))
            if gsize is None or sz < gsize:
                gsize, gsel = sz, g
        steps_raw.append((axobj, role, gsel, group_member_ids.get(gsel, set())))

    # 4) Errore: due assi di tipo diverso che definiscono lo STESSO gruppo.
    by_group = {}
    for (axobj, role, gsel, mids) in steps_raw:
        by_group.setdefault(gsel, []).append(role)
    for g, roles in by_group.items():
        if len(set(roles)) > 1:
            errors.append("Gruppo Rhino %d: contiene assi di tipo diverso "
                          "(%s) come definitori dello stesso passo. Un passo "
                          "ammette UN solo asse." % (g, ", ".join(sorted(set(roles)))))

    # 5) Ordina: interno (pochi membri) -> esterno; patella prima di simmetria.
    def _role_rank(r):
        return 0 if r == AXIS_ROLE_DASHED else 1
    steps_sorted = sorted(steps_raw, key=lambda s: (len(s[3]), _role_rank(s[1])))

    steps = []
    for i, (axobj, role, gsel, mids) in enumerate(steps_sorted, start=1):
        steps.append({"order": i, "axis": axobj, "role": role,
                      "member_ids": set(mids), "n_membri": len(mids)})

    # 6) Avviso se i passi non sono annidati a catena (matrioska attesa).
    for i in range(1, len(steps)):
        if not steps[i - 1]["member_ids"].issubset(steps[i]["member_ids"]):
            warns.append("Passi %d e %d non risultano annidati (matrioska): "
                         "verifica che il gruppo esterno includa le curve di "
                         "quello interno." % (steps[i - 1]["order"],
                                              steps[i]["order"]))

    # 7) step_list per oggetto.
    step_list_of = {}
    axis_step = {}
    for s in steps:
        axis_step[str(s["axis"].Id)] = s["order"]
    for obj in objs:
        oid = str(obj.Id)
        if oid in axis_ids:
            k = axis_step.get(oid)
            step_list_of[oid] = str(k) if k else "-"
        else:
            ks = [str(s["order"]) for s in steps if oid in s["member_ids"]]
            step_list_of[oid] = ",".join(ks) if ks else "-"

    return step_list_of, steps, errors, warns


def _resolve_steps_by_userstring(objs):
    """Fallback v5.4: passi dalla UserString 'Blocco' (un solo livello per
    oggetto, niente annidamento esplicito)."""
    errors = []
    warns = []
    by_num = {}  # numero -> {"axes":[(obj,role)], "member_ids":set}
    for obj in objs:
        n = _block_number(obj)
        if not n:
            continue
        d = by_num.setdefault(n, {"axes": [], "member_ids": set()})
        role = _cyan_axis_role(obj)
        if role is not None:
            d["axes"].append((obj, role))
        else:
            d["member_ids"].add(str(obj.Id))

    nums_sorted = sorted(by_num.keys(), key=lambda s: (len(s), s))
    steps = []
    order = 0
    for n in nums_sorted:
        d = by_num[n]
        roles = set(r for (_o, r) in d["axes"])
        if len(roles) > 1:
            errors.append("Blocco %s: assi di tipo diverso (%s). Un blocco "
                          "ammette UN solo asse." % (n, ", ".join(sorted(roles))))
            continue
        if not d["axes"]:
            warns.append("Blocco %s: nessuna linea cyan; ignorato." % n)
            continue
        if len(d["axes"]) > 1:
            warns.append("Blocco %s: piu' assi dello stesso tipo; uso il "
                         "primo." % n)
        ax_obj, ax_role = d["axes"][0]
        order += 1
        steps.append({"order": order, "axis": ax_obj, "role": ax_role,
                      "member_ids": set(d["member_ids"]),
                      "n_membri": len(d["member_ids"]), "_blocco": n})

    step_list_of = {}
    axis_step = {}
    for s in steps:
        axis_step[str(s["axis"].Id)] = s["order"]
    for obj in objs:
        oid = str(obj.Id)
        if oid in axis_step:
            step_list_of[oid] = str(axis_step[oid])
        else:
            ks = [str(s["order"]) for s in steps if oid in s["member_ids"]]
            step_list_of[oid] = ",".join(ks) if ks else "-"
    return step_list_of, steps, errors, warns


def _mirror_summary_lines(steps):
    """Righe di commento '# ...' che riassumono i PASSI di specchiatura per
    l'LLM e per PKG_Esegue: ordine, tipo d'asse, forma parametrica, n. membri.
    L'ordine e' di esecuzione (dal piu' interno al piu' esterno)."""
    out = []
    if not steps:
        return out
    out.append("# PASSI DI SPECCHIATURA (ordine = esecuzione, dal piu' interno "
               "al piu' esterno):")
    out.append("#   continuo=SIMMETRIA (mantiene l'origine) | "
               "tratteggiato=PATELLA (cancella l'origine)")
    out.append("#   matrioska: ogni passo riflette ANCHE i risultati dei passi "
               "interni precedenti (la colonna Blocco elenca i passi di ogni "
               "curva).")
    for s in steps:
        ax = s["axis"]
        if s["role"] == AXIS_ROLE_DASHED:
            tipo_txt = "TRATTEGGIATO (patella: cancella origine)"
        else:
            tipo_txt = "CONTINUO (simmetria: mantiene origine)"
        g = _refetch(ax).Geometry
        p0 = g.PointAtStart
        p1 = g.PointAtEnd
        ut = _parse_user_text_dict(_refetch(ax))
        p1p = ut.get("P1_param", "")
        p2p = ut.get("P2_param", "")
        par = ""
        if p1p or p2p:
            par = "  asse_param: %s -> %s" % (p1p or "?", p2p or "?")
        out.append("#   Passo %d: asse %s (%.3f,%.3f)->(%.3f,%.3f)%s  "
                   "membri: %d" % (s["order"], tipo_txt, p0.X, p0.Y,
                                   p1.X, p1.Y, par, s["n_membri"]))
    return out


def _variables_summary_lines(var_data):
    """Righe commentate '# ...' che dichiarano le variabili parametriche
    con default e range ammissibili. Vanno in testa al TXT, prima dei
    dati e dopo gli header. Se var_data e' None o vuota, niente righe."""
    if not var_data:
        return []
    out = []
    out.append("# VARIABILI PARAMETRICHE (valori di default e range "
               "ammissibili per il modello)")
    out.append("#   Var  Default     Min         Max         Descrizione")
    def _f(x):
        if x is None:
            return "-"
        if isinstance(x, float) or isinstance(x, int):
            if x == 0.0:
                return "-"
            return "%.2f" % x
        # Espressione parametrica (stringa, es. 'P-3')
        return str(x)
    for v in var_data:
        out.append("#   %-3s  %-10s  %-10s  %-10s  %s" % (
            v["name"], _f(v["default"]), _f(v["min"]),
            _f(v["max"]), v.get("desc", "")))
    return out


def _llm_prompt_header():
    """Testo del prompt da anteporre al TXT quando l'utente lo richiede.
    Rende il file autoportante: chi lo riceve (un LLM) ha davanti sia le
    istruzioni sia i dati per generare lo script parametrico. Unico punto da
    modificare se in futuro lo si vorra' caricare da un .md esterno."""
    return (
"""=== ISTRUZIONI PER LA GENERAZIONE DELLO SCRIPT PARAMETRICO ===

Scrivi professionalmente uno script per Rhino 7 e 8 (IronPython 2.7,
RhinoCommon, prima riga "#! python 2") che generi il packaging
descritto piu' sotto in modo PARAMETRICO, mantenendo l'unita di
misura in mm.

Specifiche di stile e convenzioni del toolkit (apri se hai accesso web):
- https://raw.githubusercontent.com/DDR68/Rhino_Packaging_Toolkit/refs/heads/main/docs/llm-knowledge/prompts/ironpython-examples.md
- https://raw.githubusercontent.com/DDR68/Rhino_Packaging_Toolkit/refs/heads/main/docs/llm-knowledge/prompts/rhino-ironpython.md
Se NON puoi accedere ai link, segui comunque queste regole minime:
solo RhinoCommon e scriptcontext (no rhinoscriptsyntax), niente
f-string, stringhe in formato %, header UTF-8, print a singolo
argomento, input/selezione via Rhino.Input.

COME LEGGERE I DATI CHE SEGUONO
- Ogni riga e' un oggetto geometrico, colonne separate da TAB.
- Le variabili packaging (es. L, P, A, S, C, T, E) hanno valori
  definiti nel disegno; le formule nel blocco UserText le combinano.
- Il blocco UserText (ultima colonna) contiene le coppie chiave=valore
  che definiscono il RAPPORTO PARAMETRICO di ogni geometria:
    Linea   -> P1_param, P2_param  (estremi come formule)
    Cerchio -> Centro_param, Raggio
    Arco    -> P1_param, P2_param, Punto_medio (tre punti), Raggio
    Raccordo conico -> P1_param, P2_param, CtrlProp_u, CtrlProp_v,
                       CtrlPeso_w
    Curva libera    -> CtrlPoints (x,y,w | ...), Nodi, Grado
- Le coordinate X1,Y1,X2,Y2 sono i valori NUMERICI attuali (solo per
  riferimento e verifica); la forma parametrica sta nelle formule del
  blocco UserText. Costruisci SEMPRE dalle formule, non dai numeri.
- Le coordinate parametriche dei punti possono incorporare il RAGGIO di
  raccordo tra due linee: un punto la cui formula contiene un termine di
  raggio e' il punto di TANGENZA dove un raccordo ad arco incontra una
  linea. Due tangenze adiacenti delimitano un arco di raccordo (di norma
  un quarto di cerchio): ricostruiscilo come arco esatto, non come
  spezzata.

COME RICONOSCERE GLI ASSI DI SPECCHIO (linee cyan)
- Gli assi di specchiatura NON sono geometria da fustellare. Una linea
  e' un ASSE se soddisfa anche solo uno di questi criteri:
    (a) colonna Ruolo = AsseSpecchio_Continuo o AsseSpecchio_Tratteggiato
        (o il generico AsseSpecchio);  OPPURE
    (b) Layer NON strutturale, cioe' diverso da Taglio, Cordone,
        MezzoTaglio, Foratore (tipicamente Layer 'Disegno'): nel
        disegno corrisponde a una LINEA CYAN.
  Vale ANCHE se le colonne Ruolo e Blocco sono '-'. Una linea su Layer
  'Disegno' (es. bordo superiore) e' un ASSE, NON un taglio.
- DUE TIPI DI ASSE, distinti dal tipo di linea cyan:
    * CONTINUA  -> Ruolo = AsseSpecchio_Continuo  = asse di SIMMETRIA:
      rifletti le geometrie e MANTIENI sia origine sia copia (scatola
      intera).
    * TRATTEGGIATA -> Ruolo = AsseSpecchio_Tratteggiato = asse di PATELLA:
      rifletti le geometrie e CANCELLA gli originali (vive solo la copia
      ribaltata). E' lo sviluppo di un'aletta che si ripiega.
- La colonna Blocco e' la LISTA dei PASSI (es. '1,2') a cui ogni curva
  partecipa; per le linee-asse e' il passo che definiscono. I passi sono
  annidati come matrioske e numerati dal piu' INTERNO (1) al piu' ESTERNO.
  Esegui i passi UNO ALLA VOLTA in ordine crescente: al passo k rifletti
  TUTTE le curve la cui lista di passi contiene k (escluse le linee-asse),
  rispetto all'asse del passo k. Una curva interna compare in piu' passi,
  quindi viene rispecchiata di nuovo dal passo esterno: e' cosi' che la
  simmetria finale ingloba i risultati delle patelle. Se Blocco vale '-'
  per tutto, considera un unico asse per l'intera figura.

SPECCHIATURA E PULIZIA (ULTIME operazioni dello script)
- Il tracciato esportato e' di norma una META' (o una porzione) della
  fustella: gli assi indicano dove riflettere per ottenere l'INTERO.
- Ogni asse e' di SERVIZIO: si ricostruisce solo per riflettere e si
  CANCELLA alla fine. Nella fustella prodotta non deve restare.
- Esegui queste come ULTIME operazioni, dopo aver costruito tutte le
  geometrie origine, SEGUENDO L'ORDINE DEI PASSI (1, 2, 3, ...):
    1. Ricostruisci l'asse del passo corrente in modo PARAMETRICO dai
       suoi P1_param/P2_param (se assenti, usa gli estremi numerici).
       Ricavalo dalla FORMULA, non da una linea disegnata a mano, e NON
       cercarlo nel documento Rhino.
    2. Rifletti rispetto alla RETTA dell'asse tutte le curve la cui lista
       di passi (colonna Blocco) contiene il passo corrente (escluse le
       linee-asse), poi:
         - se l'asse e' TRATTEGGIATO (patella): CANCELLA gli originali
           riflessi, tieni solo le copie (le copie ereditano la lista di
           passi, quindi restano disponibili per i passi successivi);
         - se l'asse e' CONTINUO (simmetria): MANTIENI sia origine sia
           copia (scatola intera).
    3. Passa al passo successivo (numero maggiore) e ripeti: cosi' il
       passo esterno ingloba e rispecchia i risultati di quelli interni.
    4. Come ULTIMISSIMA operazione, CANCELLA ogni linea d'asse: nel
       risultato finale non deve restarne alcuna.
- Poiche' l'asse nasce dalle stesse formule del bordo, giace ESATTAMENTE
  sull'edge condiviso: dopo una SIMMETRIA le due meta' devono COMBACIARE,
  senza distacco ne sovrapposizione. Se risultano STACCATE, l'asse e'
  posizionato male: ricavalo dalla FORMULA.

COSA DEVI PRODURRE
Uno script che:
- legga i VALORI DI DEFAULT e i RANGE ammissibili di ogni variabile
  dalla sezione '# VARIABILI PARAMETRICHE' dei dati qui sotto. Se la
  sezione e' assente, definisca almeno L, P, A, S con default sensati;
- definisca in testa le variabili packaging come valori di DEFAULT e le
  CHIEDA all'avvio con Rhino.Input.RhinoGet.GetNumber (Invio = valore di
  default). Se il valore inserito e' fuori dal range Min-Max dichiarato,
  lo script deve AVVISARE ('Valore fuori range: min-max consigliato') e
  RICHIEDERE l'input, accettando comunque se l'utente insiste.
  ATTENZIONE: Min e Max possono essere numeri OPPURE espressioni
  parametriche (es. 'P-3', 'L/2'). Se sono espressioni, valutale con
  i valori correnti delle variabili gia' inserite prima di confrontare;
- costruisca tutte le geometrie dalle loro formule;
- come ULTIME operazioni: ricostruisca l'asse parametrico, applichi le
  specchiature (scatola intera, meta' unite sull'asse) e infine CANCELLI
  l'asse;
- disegni nei layer corretti: Taglio (nero), Cordone (rosso),
  MezzoTaglio, Foratore. Nel risultato finale NON resta alcun asse.

NOTE DI RICOSTRUZIONE (fedelta')
- Curve libere/Bezier che approssimano un raccordo a 90 gradi vanno
  ricostruite come ARCHI di cerchio esatti (quarto di cerchio): piu'
  pulite per la fustella e comunque parametriche.
- Piccoli scostamenti numerici dell'export (ordine del mezzo mm) vanno
  arrotondati al valore che CHIUDE la geometria sul bordo o sul raccordo
  adiacente.

AUTO-VERIFICA (obbligatoria)
Al termine, controlla lo script confrontando la geometria prodotta con
i dati qui sotto: per ogni punto verifica che la formula valutata coi
valori delle variabili ridia le coordinate numeriche indicate; per
archi e raccordi verifica estremi, raggio e lato; verifica inoltre che
dopo la specchiatura le due meta' COMBACINO sull'asse e che nessuna
linea d'asse sia rimasta nel risultato. Segnala e CORREGGI ogni
inesattezza prima di restituire la versione finale.

=== GEOMETRIE E RAPPORTI PARAMETRICI DEL PACKAGING ===
""")

def export_objects(curve_objs, point_objs, include_prompt=False, var_data=None):
    """Genera il contenuto TXT e lo salva."""
    lines = []
    rows = []
    n_exploded = 0
    n_total = 0
    all_bbox = rg.BoundingBox.Empty
    idx = 1

    # Specchiatura: passi + assi cyan (v5.5: gruppi Rhino, continua/tratteggiata)
    step_list_of, steps, mirror_errors, mirror_warns = \
        _resolve_mirror_steps(list(point_objs) + list(curve_objs))

    # Errore bloccante: un gruppo con assi di tipo misto (continuo +
    # tratteggiato) ha semantica ambigua. Niente export.
    if mirror_errors:
        print("")
        print("[ERRORE] Export annullato per conflitto sugli assi di "
              "specchiatura:")
        for e in mirror_errors:
            print("   - %s" % e)
        print("Correggi i gruppi (un solo tipo di linea cyan per passo) "
              "e riprova.")
        _show_blocking_error(mirror_errors)
        return

    for w in mirror_warns:
        print("[AVVISO] %s" % w)

    using_groups = _selection_has_groups(list(point_objs) + list(curve_objs))
    print("[INFO] Membership specchiatura: %s" % (
        "GRUPPI Rhino" if using_groups else "UserString 'Blocco' (fallback)"))
    if steps:
        print("[INFO] %d passo/i di specchiatura rilevati:" % len(steps))
        for s in steps:
            tt = ("tratteggiato/patella" if s["role"] == AXIS_ROLE_DASHED
                  else "continuo/simmetria")
            print("   Passo %d: asse %s, membri=%d" % (
                s["order"], tt, s["n_membri"]))

    # DIAGNOSTICA SPECCHIATURA: per ogni curva cyan o lineare, mostra cosa
    # "vede" lo script. Serve a capire i mancati riconoscimenti.
    print("[DIAG specchiatura] curve cyan/lineari tra le selezionate:")
    n_diag = 0
    n_axis_no_group = 0
    for obj in curve_objs:
        ro = _refetch(obj)
        g = ro.Geometry
        is_lin = _is_linear_curve(g)
        col = _effective_color(ro)
        is_cy = _is_cyan(col)
        if not (is_lin or is_cy):
            continue
        n_diag += 1
        name, seg, plen, cont = _linetype_debug(ro)
        role = _cyan_axis_role(ro)
        grps = _object_groups(ro)
        steplist = step_list_of.get(str(ro.Id), "-")
        if role is not None and not grps:
            n_axis_no_group += 1
        print("   id=%s lin=%s RGB=(%d,%d,%d) cyan=%s ltype=%s seg=%s "
              "plen=%s continuo=%s gruppi=%s passi=%s -> ruolo=%s" % (
                  str(ro.Id)[:8], is_lin, int(col.R), int(col.G), int(col.B),
                  is_cy, name, seg, plen, cont,
                  (",".join(str(x) for x in grps) if grps else "-"),
                  steplist, role or "-"))
    if n_diag == 0:
        print("   (nessuna curva cyan o lineare rilevata)")
    if n_axis_no_group > 0:
        print("[AVVISO] %d linee asse cyan riconosciute SENZA gruppo Rhino: "
              "vengono marcate col ruolo nel TXT ma NON entrano nell'ordine "
              "di specchiatura. Raggruppale (_Group) con le loro curve."
              % n_axis_no_group)

    # Punti
    for obj in point_objs:
        obj = _refetch(obj)  # FIX v5.1
        pt = obj.Geometry.Location
        bb = rg.BoundingBox(pt, pt)
        all_bbox.Union(bb)
        _oid = str(obj.Id)
        rows.append(row_for_point(
            idx, obj,
            block=step_list_of.get(_oid, "-"),
            role=_cyan_axis_role(obj) or "-"))
        idx += 1
        n_total += 1

    # Curve
    for obj in curve_objs:
        obj = _refetch(obj)  # FIX v5.1: attributi/usertext freschi
        curve = obj.Geometry
        tipo = classify_curve(obj)
        ut = get_user_text(obj)  # letto UNA volta dall'oggetto fresco
        _oid = str(obj.Id)
        # v5.5: Blocco = lista dei passi (CSV) cui la curva partecipa
        # (matrioska: una curva interna compare in piu' passi).
        _blk = step_list_of.get(_oid, "-")
        # Il ruolo deriva dal colore+linetype, indipendente dal gruppo.
        _role = _cyan_axis_role(obj) or "-"
        bb = curve.GetBoundingBox(True)
        if bb.IsValid:
            all_bbox.Union(bb)
        segments = explode_curve(curve)
        if len(segments) > 1 and (isinstance(curve, rg.PolyCurve)
                                  or isinstance(curve, rg.PolylineCurve)):
            n_exploded += 1
        for seg in segments:
            rows.append(row_for_segment(idx, obj, seg, tipo,
                                        usertext_override=ut,
                                        block=_blk, role=_role))
            idx += 1
            n_total += 1

    # Header
    doc_path = sc.doc.Path if sc.doc.Path else "(non salvato)"
    doc_name = os.path.basename(doc_path) if sc.doc.Path else "(non salvato)"
    unit = str(sc.doc.ModelUnitSystem)

    if all_bbox.IsValid:
        w = all_bbox.Max.X - all_bbox.Min.X
        h = all_bbox.Max.Y - all_bbox.Min.Y
        bbox_str = "%sx%s" % (fmt(w), fmt(h))
    else:
        bbox_str = "n/d"

    n_curves = len(curve_objs)
    n_points = len(point_objs)

    lines.append("# %s | bbox: %s | curve: %d | punti: %d | segm: %d | "
                 "exploded: %d | unita: %s" % (
        doc_name, bbox_str, n_curves, n_points, n_total, n_exploded, unit))
    lines.append("# Tipo: T=Taglio C=Cordone M=MezzoTaglio F=Foratore P=Point")
    lines.append("# Angoli archi: convenzione con segno (CW = negativo)")
    for _vl in _variables_summary_lines(var_data):
        lines.append(_vl)
    lines.append("# Blocco: lista dei passi di specchiatura (CSV) cui la curva "
                 "partecipa; per le linee-asse e' il passo che definiscono.")
    lines.append("# Colonne: " + "  ".join(COLUMNS))
    for _ml in _mirror_summary_lines(steps):
        lines.append(_ml)

    for r in rows:
        lines.append(format_row(r))

    # Salvataggio
    fd = Rhino.UI.SaveFileDialog()
    fd.Filter = "Text file (*.txt)|*.txt"
    fd.DefaultExt = "txt"
    if sc.doc.Path:
        base = os.path.splitext(os.path.basename(sc.doc.Path))[0]
        fd.FileName = base + "_parametric_export.txt"
    else:
        fd.FileName = "geometrie_parametric_export.txt"

    if not fd.ShowSaveDialog():
        print("Esportazione annullata.")
        return

    filepath = fd.FileName
    content = "\n".join(lines)

    # Prompt LLM in testa, se richiesto dall'utente. Va PRIMA delle righe
    # commentate '#' e dei dati, cosi' l'LLM legge prima le istruzioni.
    if include_prompt:
        content = _llm_prompt_header() + "\n" + content

    with open(filepath, "w") as f:
        f.write(content)

    print("")
    print("Esportazione completata: %s" % filepath)
    print("Curve: %d  |  Punti: %d  |  Segmenti totali: %d" % (
        n_curves, n_points, n_total))
    if n_exploded > 0:
        print("PolyCurve esplose: %d" % n_exploded)
    if all_bbox.IsValid:
        print("Ingombro: %s mm" % bbox_str)


# ============================================================
#  MAIN
# ============================================================

def main():
    print("=" * 60)
    print("ESPORTA GEOMETRIE PARAMETRICO v5.6")
    print("=" * 60)

    selected = list(sc.doc.Objects.GetSelectedObjects(False, False))
    curve_objs = []
    point_objs = []
    for obj in selected:
        ot = obj.ObjectType
        if ot == Rhino.DocObjects.ObjectType.Curve:
            curve_objs.append(obj)
        elif ot == Rhino.DocObjects.ObjectType.Point:
            point_objs.append(obj)

    if not curve_objs and not point_objs:
        print("Nessun oggetto selezionato - apertura guida.")
        show_help()
        return

    print("Oggetti selezionati: %d curve, %d punti" % (
        len(curve_objs), len(point_objs)))

    n_aggiornate = 0
    n_saltate    = 0
    reasons      = {}
    n_punti_validi = 0

    if curve_objs:
        n_aggiornate, n_saltate, reasons, n_punti_validi = propaga_parametrico(
            curve_objs)

    if curve_objs:
        do_export, include_prompt = show_report_and_ask_export(
            n_aggiornate, n_saltate, reasons,
            n_punti_validi, len(curve_objs), len(point_objs))
    else:
        # senza curve, esporto i soli punti; il prompt LLM ha senso comunque
        do_export, include_prompt = True, True

    if do_export:
        # v5.6: estrazione variabili parametriche dalle formule dei punti
        var_data = None
        points_map, _sk, _lok = _collect_param_points()
        if points_map:
            found_vars = _extract_variables_from_formulas(points_map)
            if found_vars:
                # Deduce i default risolvendo le equazioni formula=coordinata
                solved = _solve_variables_from_points(points_map)
                print("Variabili parametriche rilevate: %s" % (
                    ", ".join(found_vars)))
                if solved:
                    print("Default dedotti dal disegno: %s" % (
                        ", ".join("%s=%.4g" % (k, v)
                                  for k, v in sorted(solved.items()))))
                var_data = show_variables_dialog(found_vars,
                                                inferred_defaults=solved)
                if var_data is not None:
                    print("Variabili confermate: %d" % len(var_data))
                else:
                    print("Sezione variabili saltata dall'utente.")
        print("-" * 60)
        export_objects(curve_objs, point_objs,
                       include_prompt=include_prompt, var_data=var_data)
    else:
        print("-" * 60)
        print("Propagazione completata. Nessun export su file.")


if __name__ == "__main__":
    main()
