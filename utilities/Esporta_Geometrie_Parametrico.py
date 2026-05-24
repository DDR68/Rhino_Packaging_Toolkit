#! python 2
# -*- coding: utf-8 -*-
"""
Script: Esporta_Geometrie_Parametrico_V.5.py
Versione: 5.1
Compatibilita: Rhino 7 / Rhino 8 - IronPython 2.7 - RhinoCommon (no rhinoscriptsyntax)

UNIFICA:
  - Aggiorna_UserText_Parametrico (propagazione punti parametrici -> curve)
  - Esporta_Geometrie_Semplice V.4 (export TXT tab-separated)

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
#  HELP DIALOG (Eto.Forms)
# ============================================================

def show_help():
    """Mostra finestra di aiuto con convenzioni colore e formato export."""
    import Eto.Forms as ef
    import Eto.Drawing as ed

    dlg = ef.Dialog()
    dlg.Title = "Esporta Geometrie Parametrico v5.1 - Guida"
    dlg.Padding = ed.Padding(16)
    dlg.MinimumSize = ed.Size(680, 560)
    dlg.Resizable = True

    layout = ef.DynamicLayout()
    layout.Spacing = ed.Size(8, 8)
    layout.DefaultSpacing = ed.Size(4, 4)

    title = ef.Label()
    title.Text = "ESPORTA GEOMETRIE PARAMETRICO v5.1"
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
    Ritorna True se l'utente vuole esportare, False altrimenti."""
    import Eto.Forms as ef
    import Eto.Drawing as ed

    result = {"export": False}

    dlg = ef.Dialog()
    dlg.Title = "Esporta Geometrie Parametrico v5.1 - Report"
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
    layout.AddRow(ef.Label(Text=""))

    btn_export = ef.Button()
    btn_export.Text = "Si, esporta su file"
    def on_export(s, e):
        result["export"] = True
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

    return result["export"]


# ============================================================
#  PROPAGAZIONE PARAMETRICA - HELPERS
# ============================================================

def make_pair_id_from_xy(x, y):
    """FIX v5.1: ricostruisce il pair_id con lo STESSO schema di
    PKG_Annotator.make_point_key, per i punti annotati prima della v4.1
    (che non scrivevano la chiave 'pair_id')."""
    ix = int(round(x))
    iy = int(round(y))
    sx = "+" if ix >= 0 else "-"
    sy = "+" if iy >= 0 else "-"
    return "PKG_X%s%04d_Y%s%04d" % (sx, abs(ix), sy, abs(iy))


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

        # FIX v5.1: pair_id da UserString; se assente (annotator < v4.1)
        # lo ricostruisco dalle coordinate con lo schema dell'annotator.
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
           "Len", "Deg", "Pts", "CP", "Sampled", "UserText"]


def row_for_point(idx, obj, usertext_override=None):
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
        "UserText": ut,
    }
    return row


def row_for_segment(idx, obj, segment, tipo, usertext_override=None):
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


def export_objects(curve_objs, point_objs):
    """Genera il contenuto TXT e lo salva."""
    lines = []
    rows = []
    n_exploded = 0
    n_total = 0
    all_bbox = rg.BoundingBox.Empty
    idx = 1

    # Punti
    for obj in point_objs:
        obj = _refetch(obj)  # FIX v5.1
        pt = obj.Geometry.Location
        bb = rg.BoundingBox(pt, pt)
        all_bbox.Union(bb)
        rows.append(row_for_point(idx, obj))
        idx += 1
        n_total += 1

    # Curve
    for obj in curve_objs:
        obj = _refetch(obj)  # FIX v5.1: attributi/usertext freschi
        curve = obj.Geometry
        tipo = classify_curve(obj)
        ut = get_user_text(obj)  # letto UNA volta dall'oggetto fresco
        bb = curve.GetBoundingBox(True)
        if bb.IsValid:
            all_bbox.Union(bb)
        segments = explode_curve(curve)
        if len(segments) > 1 and (isinstance(curve, rg.PolyCurve)
                                  or isinstance(curve, rg.PolylineCurve)):
            n_exploded += 1
        for seg in segments:
            rows.append(row_for_segment(idx, obj, seg, tipo, usertext_override=ut))
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
    print("ESPORTA GEOMETRIE PARAMETRICO v5.1")
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
        do_export = show_report_and_ask_export(
            n_aggiornate, n_saltate, reasons,
            n_punti_validi, len(curve_objs), len(point_objs))
    else:
        do_export = True

    if do_export:
        print("-" * 60)
        export_objects(curve_objs, point_objs)
    else:
        print("-" * 60)
        print("Propagazione completata. Nessun export su file.")


if __name__ == "__main__":
    main()
