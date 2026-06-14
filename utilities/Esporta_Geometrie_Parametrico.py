#! python 2
# -*- coding: utf-8 -*-
"""
Script: Esporta_Geometrie_Parametrico.py
Versione: 5.3
Compatibilita: Rhino 7 / Rhino 8 - IronPython 2.7 - RhinoCommon (no rhinoscriptsyntax)

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
MIRROR_AXIS_ROLE = "AsseSpecchio"

# La linea di specchiatura e' riconosciuta dal COLORE cyan (0,255,255), per
# oggetto o per layer. Tolleranza per-canale ampia ma sicura (il blu 0,0,255
# resta escluso: ha G lontano da 255).
COLOR_CYAN_RGB = (0, 255, 255)
CYAN_CH_TOL    = 40


# ============================================================
#  HELP DIALOG (Eto.Forms)
# ============================================================

def show_help():
    """Mostra finestra di aiuto con convenzioni colore e formato export."""
    import Eto.Forms as ef
    import Eto.Drawing as ed

    dlg = ef.Dialog()
    dlg.Title = "Esporta Geometrie Parametrico v5.3 - Guida"
    dlg.Padding = ed.Padding(16)
    dlg.MinimumSize = ed.Size(680, 560)
    dlg.Resizable = True

    layout = ef.DynamicLayout()
    layout.Spacing = ed.Size(8, 8)
    layout.DefaultSpacing = ed.Size(4, 4)

    title = ef.Label()
    title.Text = "ESPORTA GEOMETRIE PARAMETRICO v5.3"
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
    sec_mir.Text = "SPECCHIATURA (v5.3)"
    sec_mir.Font = ed.Font(ed.SystemFont.Bold, 11)
    layout.AddRow(sec_mir)

    mir = ef.Label()
    mir.Text = ("Gli oggetti con UserString 'Blocco'=N formano un blocco\n"
                "(N e' anche l'ordine di esecuzione). Dentro il blocco, la\n"
                "linea CYAN e' l'asse di specchiatura. L'export raggruppa per\n"
                "blocco, marca l'asse con Ruolo=AsseSpecchio e ne riassume gli\n"
                "estremi (anche parametrici) in testa al TXT. Lo script\n"
                "parametrico generato riflette ogni blocco sul suo asse, in\n"
                "ordine, poi cancella l'asse (di servizio); per la scatola\n"
                "intera origine e copia restano entrambe.")
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
    dlg.Title = "Esporta Geometrie Parametrico v5.3 - Report"
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


def _is_cyan(color):
    cr, cg, cb = COLOR_CYAN_RGB
    return (abs(int(color.R) - cr) <= CYAN_CH_TOL and
            abs(int(color.G) - cg) <= CYAN_CH_TOL and
            abs(int(color.B) - cb) <= CYAN_CH_TOL)


def _block_number(obj):
    """Numero di blocco dell'oggetto (UserString MIRROR_BLOCK_KEY) o ''."""
    try:
        v = obj.Attributes.GetUserString(MIRROR_BLOCK_KEY)
    except Exception:
        v = None
    return (v or "").strip()


def _is_cyan_axis_line(obj):
    """True se l'oggetto e' una linea (curva lineare) di colore cyan: l'asse
    di specchiatura del suo blocco."""
    g = obj.Geometry
    if not isinstance(g, rg.Curve):
        return False
    if not g.IsLinear(Rhino.RhinoMath.ZeroTolerance):
        return False
    return _is_cyan(_effective_color(obj))


def _resolve_mirror_blocks(objs):
    """Raggruppa gli oggetti per numero di blocco e, in ogni blocco, individua
    la linea cyan come asse. Ritorna (block_of, axis_ids, blocks):
      block_of : { obj.Id(str) : numero }
      axis_ids : set( obj.Id(str) ) delle linee-asse scelte
      blocks   : { numero : {"members":[obj], "axis":obj|None} }
    """
    blocks = {}
    block_of = {}
    for obj in objs:
        n = _block_number(obj)
        if not n:
            continue
        block_of[str(obj.Id)] = n
        b = blocks.get(n)
        if b is None:
            b = {"members": [], "axis": None}
            blocks[n] = b
        b["members"].append(obj)
        if b["axis"] is None and _is_cyan_axis_line(obj):
            b["axis"] = obj
    axis_ids = set(str(b["axis"].Id) for b in blocks.values()
                   if b["axis"] is not None)
    return block_of, axis_ids, blocks


def _mirror_summary_lines(blocks):
    """Righe di commento '# ...' che riassumono i blocchi di specchiatura per
    l'LLM: asse (coordinate + forma parametrica se nota) e n. membri."""
    out = []
    if not blocks:
        return out
    out.append("# BLOCCHI DI SPECCHIATURA (numero = ordine di esecuzione):")
    for n in sorted(blocks.keys(), key=lambda s: (len(s), s)):
        b = blocks[n]
        ax = b["axis"]
        nm = len(b["members"])
        if ax is None:
            out.append("#   Blocco %s: [nessuna linea cyan nel blocco] - "
                       "membri: %d" % (n, nm))
            continue
        g = _refetch(ax).Geometry
        p0 = g.PointAtStart
        p1 = g.PointAtEnd
        ut = _parse_user_text_dict(_refetch(ax))
        p1p = ut.get("P1_param", "")
        p2p = ut.get("P2_param", "")
        par = ""
        if p1p or p2p:
            par = "  asse_param: %s -> %s" % (p1p or "?", p2p or "?")
        out.append("#   Blocco %s: asse (%.3f,%.3f)->(%.3f,%.3f)%s  membri: %d"
                   % (n, p0.X, p0.Y, p1.X, p1.Y, par, nm))
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
    (a) colonna Ruolo = AsseSpecchio;  OPPURE
    (b) Layer NON strutturale, cioe' diverso da Taglio, Cordone,
        MezzoTaglio, Foratore (tipicamente Layer 'Disegno'): nel
        disegno corrisponde a una LINEA CYAN.
  Vale ANCHE se le colonne Ruolo e Blocco sono '-'. In questi dati la
  linea su Layer 'Disegno' (bordo orizzontale superiore) e' l'ASSE,
  NON un taglio: non confonderla con la geometria.
- La colonna Blocco, quando valorizzata, raggruppa le geometrie che
  condividono lo stesso asse; se vale '-', considera un unico asse per
  l'intera figura.

SPECCHIATURA E PULIZIA (ULTIME operazioni dello script)
- Il tracciato esportato e' di norma una META' (o una porzione) della
  fustella: l'asse indica dove riflettere per ottenere l'INTERO.
- L'asse e' di SERVIZIO: si ricostruisce solo per riflettere e si
  CANCELLA alla fine. Nella fustella prodotta non deve restare.
- Esegui queste come ULTIME operazioni, dopo aver costruito tutte le
  geometrie origine:
    1. Ricostruisci OGNI asse in modo PARAMETRICO dai suoi P1_param/
       P2_param (se assenti, usa gli estremi numerici). Ricavalo dalla
       FORMULA, non da una linea disegnata a mano, e NON cercarlo nel
       documento Rhino.
    2. Rifletti le geometrie origine rispetto alla RETTA dell'asse e
       MANTIENI sia origine sia copia (scatola intera). Con piu'
       blocchi, applica gli assi in ordine crescente di Blocco.
    3. CANCELLA l'asse (o gli assi): e' l'ultimissima operazione. Nel
       risultato finale non deve restare alcuna linea d'asse.
- Poiche' l'asse nasce dalle stesse formule del bordo, giace ESATTAMENTE
  sull'edge condiviso: le due meta' devono COMBACIARE, senza distacco ne
  sovrapposizione. Se risultano STACCATE, l'asse e' posizionato male:
  ricavalo dalla FORMULA.
- (Le PATELLE, dove l'origine sparisce e resta solo la copia, non sono
  gestite in questa versione: tratta tutto come scatola intera.)

COSA DEVI PRODURRE
Uno script che:
- definisca in testa le variabili packaging (almeno L, P, A, S; aggiungi
  C, T, E se compaiono nelle formule) come valori di DEFAULT e le CHIEDA
  all'avvio con Rhino.Input.RhinoGet.GetNumber (Invio = valore di
  default), cosi' che modificandole la fustella si riscali;
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

def export_objects(curve_objs, point_objs, include_prompt=False):
    """Genera il contenuto TXT e lo salva."""
    lines = []
    rows = []
    n_exploded = 0
    n_total = 0
    all_bbox = rg.BoundingBox.Empty
    idx = 1

    # Specchiatura: blocchi + assi cyan (v5.3)
    block_of, axis_ids, blocks = _resolve_mirror_blocks(
        list(point_objs) + list(curve_objs))

    # Punti
    for obj in point_objs:
        obj = _refetch(obj)  # FIX v5.1
        pt = obj.Geometry.Location
        bb = rg.BoundingBox(pt, pt)
        all_bbox.Union(bb)
        _oid = str(obj.Id)
        rows.append(row_for_point(
            idx, obj,
            block=block_of.get(_oid, "-"),
            role=(MIRROR_AXIS_ROLE if _oid in axis_ids else "-")))
        idx += 1
        n_total += 1

    # Curve
    for obj in curve_objs:
        obj = _refetch(obj)  # FIX v5.1: attributi/usertext freschi
        curve = obj.Geometry
        tipo = classify_curve(obj)
        ut = get_user_text(obj)  # letto UNA volta dall'oggetto fresco
        _oid = str(obj.Id)
        _blk = block_of.get(_oid, "-")
        _role = MIRROR_AXIS_ROLE if _oid in axis_ids else "-"
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
    lines.append("# Colonne: " + "  ".join(COLUMNS))
    for _ml in _mirror_summary_lines(blocks):
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
    print("ESPORTA GEOMETRIE PARAMETRICO v5.3")
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
        print("-" * 60)
        export_objects(curve_objs, point_objs, include_prompt=include_prompt)
    else:
        print("-" * 60)
        print("Propagazione completata. Nessun export su file.")


if __name__ == "__main__":
    main()
