#! python 2
# -*- coding: utf-8 -*-
"""
Script: PKG_Verifica_Forma.py
Versione: 1.0
Compatibilita: Rhino 7 / Rhino 8 - IronPython 2.7 - RhinoCommon

SCOPO
  Strumento di VERIFICA (validatore di forma), non di produzione.
  Legge un file TXT prodotto da Esporta_Geometrie_Parametrico_V.5 e
  ricostruisce le geometrie del tracciato in un nuovo layer, valutando le
  espressioni parametriche con i valori delle variabili presenti nei
  Document User Text (chiavi PKG_L, PKG_P, ... come le salva PKG_Annotator).

  Uso tipico: la "prova di sovrascrittura". Esporti un tracciato, lo
  ricostruisci con questo script, e verifichi a occhio che la geometria
  ricostruita coincida con l'originale (es. comando _SelDup). Se coincide,
  il TXT contiene informazione sufficiente a ridisegnare il tracciato; se
  no, c'e' un problema nell'annotazione o nell'export, da correggere prima
  che il TXT vada a valle.

  E' anche il motore per rigenerare lo stesso astuccio a misure diverse:
  basta cambiare i Document User Text PKG_* e rilanciare.

COSA VERIFICA (e cosa NO)
  Verifica la FORMA geometrica: che ogni curva sia ricostruibile dal TXT.
  NON verifica la correttezza CARTOTECNICA delle formule parametriche: se
  un punto e' annotato con una formula che per i parametri correnti da'
  per caso la coordinata giusta ma e' concettualmente errata (es. L+P
  invece di L-S), questo script disegna comunque il punto giusto, e
  l'errore emergerebbe solo cambiando i parametri. Per quel controllo
  serve un validatore di coerenza parametrica (strumento distinto).

COSA RICOSTRUISCE (e come)
  Linea    : da P1_param, P2_param (valutati coi parametri correnti).
  Cerchio  : da Centro_param + Raggio.
  Arco     : in modo CANONICO da tre punti (start, Punto_medio, end), via
             rg.Arc(p1, mid, p2). Il punto medio determina univocamente il
             lato dell'arco, senza ambiguita' di piano/segno/verso.
             Fallback per file vecchi: Centro_geom + raggio + angoli.
  Raccordo conico (NURBS grado 2, 3 CP):
             da P1_param, P2_param + terna (CtrlProp_u, CtrlProp_v,
             CtrlPeso_w). Si riadatta ai parametri correnti.
  Curva libera (NURBS altro grado):
             da CtrlPoints (x,y,w separati da '|') + Nodi. Ricostruzione
             geometrica esatta ma fissa (non riparametrizzata).

NOTE
  - Le geometrie parametriche (linea, cerchio, conica) si adattano ai
    valori PKG_* correnti: cambiando i parametri, il tracciato si riscala.
  - Le geometrie "libere" (arco con centro non annotato, NURBS grado>2)
    si ricostruiscono alle coordinate assolute salvate: identiche
    all'originale, ma non riscalabili.
"""

import Rhino
import Rhino.Geometry as rg
import scriptcontext as sc
import System
import math
import re
import os

LAYER_OUT       = "PKG_Ricostruito"
COLOR_OUT       = System.Drawing.Color.FromArgb(200, 0, 160)
VAR_NAMES       = ["L", "P", "A", "S", "C", "T", "E"]
DOC_PREFIX      = "PKG_"
ALLOWED_FUNCS   = {
    "abs":  abs, "sqrt": math.sqrt,
    "sin":  math.sin, "cos": math.cos, "tan": math.tan, "pi": math.pi,
}
_SAFE_CHARS_RE = re.compile(r"^[0-9\.\+\-\*\/\(\)\,\s a-zA-Z_]+$")


# ------------------------------------------------------------------
def load_params_from_doc():
    """Carica le variabili packaging dai Document User Text (PKG_*)."""
    result = {}
    for name in VAR_NAMES:
        val = sc.doc.Strings.GetValue(DOC_PREFIX + name)
        if val is not None and val != "":
            try:
                result[name] = float(val.replace(",", "."))
            except ValueError:
                pass
    return result


def safe_eval(expr, vars_dict):
    """Valuta un'espressione parametrica in sicurezza. Ritorna float o None."""
    if expr is None:
        return None
    expr = expr.strip()
    if not expr or expr in ("--", "non_associato"):
        return None
    if not _SAFE_CHARS_RE.match(expr):
        return None
    tokens = re.findall(r"[a-zA-Z_][a-zA-Z_0-9]*", expr)
    allowed = set(VAR_NAMES) | set(ALLOWED_FUNCS.keys())
    for tok in tokens:
        if tok not in allowed:
            return None
    try:
        code = compile(expr, "<pkg_expr>", "eval")
    except Exception:
        return None
    ns = {"__builtins__": {}}
    ns.update(ALLOWED_FUNCS)
    ns.update(vars_dict)
    try:
        val = eval(code, ns, {})
        return float(val)
    except Exception:
        return None


def eval_point(param_str, vars_dict):
    """Valuta '(expr_x, expr_y)' -> Point3d, o None se non valutabile."""
    if param_str is None:
        return None
    m = re.match(r"\(\s*(.+?),\s*(.+)\)\s*$", param_str.strip())
    if not m:
        return None
    x = safe_eval(m.group(1), vars_dict)
    y = safe_eval(m.group(2), vars_dict)
    if x is None or y is None:
        return None
    return rg.Point3d(x, y, 0.0)


# ------------------------------------------------------------------
def parse_user_text(ut_str):
    """'k1=v1;k2=v2' -> dict. (Separatore campi ';', come da export.)"""
    d = {}
    if not ut_str or ut_str == "-":
        return d
    for kv in ut_str.split(";"):
        if "=" in kv:
            k, v = kv.split("=", 1)
            d[k] = v
    return d


def parse_xy(s):
    """'x,y' -> (float,float) o None."""
    try:
        parts = s.split(",")
        return float(parts[0]), float(parts[1])
    except Exception:
        return None


# ------------------------------------------------------------------
def get_or_create_layer(name, color):
    idx = sc.doc.Layers.FindByFullPath(name, -1)
    if idx >= 0:
        return idx
    layer = Rhino.DocObjects.Layer()
    layer.Name = name
    layer.Color = color
    return sc.doc.Layers.Add(layer)


# ------------------------------------------------------------------
def build_line(ut, vars_dict):
    p1 = eval_point(ut.get("P1_param"), vars_dict)
    p2 = eval_point(ut.get("P2_param"), vars_dict)
    if p1 is None or p2 is None:
        return None, "line: estremi non valutabili"
    return rg.LineCurve(p1, p2), None


def build_circle(ut, vars_dict):
    c = eval_point(ut.get("Centro_param"), vars_dict)
    # fallback al centro geometrico se il parametrico non c'e'
    if c is None and ut.get("Centro_geom"):
        xy = parse_xy(ut["Centro_geom"])
        if xy:
            c = rg.Point3d(xy[0], xy[1], 0.0)
    if c is None:
        return None, "circle: centro non disponibile"
    try:
        r = float(ut.get("Raggio"))
    except Exception:
        return None, "circle: raggio mancante"
    return rg.ArcCurve(rg.Circle(c, r)), None


def build_arc(ut, vars_dict):
    """Arco ricostruito in modo CANONICO da tre punti (start, mid, end):
    rg.Arc(p_start, p_mid, p_end) e' univoco e immune alle ambiguita' di
    piano, segno e verso. Usa Punto_medio salvato dall'export.
    Fallback: se Punto_medio manca (file da export precedente) ma c'e'
    Centro_geom, prova la via centro+raggio+angoli (corretta per i
    semicerchi, meno robusta in generale)."""
    p1 = eval_point(ut.get("P1_param"), vars_dict)
    p2 = eval_point(ut.get("P2_param"), vars_dict)

    # --- via canonica a 3 punti ---
    if ut.get("Punto_medio"):
        mid_xy = parse_xy(ut["Punto_medio"])
        if mid_xy and p1 is not None and p2 is not None:
            p_mid = rg.Point3d(mid_xy[0], mid_xy[1], 0.0)
            try:
                arc = rg.Arc(p1, p_mid, p2)
                if arc.IsValid:
                    return rg.ArcCurve(arc), None
            except Exception as ex:
                return None, "arc: Arc(3 punti) fallita (%s)" % ex

    # --- fallback: centro geometrico + raggio + angoli ---
    if not ut.get("Centro_geom"):
        return None, "arc: ne' Punto_medio ne' Centro_geom (export vecchio?)"
    xy = parse_xy(ut["Centro_geom"])
    if not xy:
        return None, "arc: Centro_geom illeggibile"
    center = rg.Point3d(xy[0], xy[1], 0.0)
    try:
        r = float(ut.get("Raggio"))
        a0 = math.radians(float(ut.get("AngStart_deg")))
        a1 = math.radians(float(ut.get("AngEnd_deg")))
    except Exception:
        return None, "arc: raggio/angoli mancanti"
    verso = ut.get("Verso", "CCW")
    normal = rg.Vector3d(0, 0, -1) if verso == "CW" else rg.Vector3d(0, 0, 1)
    plane = rg.Plane(center, normal)
    interval = rg.Interval(abs(a0), abs(a1))
    if interval.Length <= 1e-9:
        interval = rg.Interval(0.0, 2.0 * math.pi)
    try:
        arc = rg.Arc(rg.Circle(plane, r), interval)
        return rg.ArcCurve(arc), None
    except Exception as ex:
        return None, "arc: costruzione fallita (%s)" % ex


def build_conic(ut, vars_dict):
    """Raccordo conico quadratico da estremi parametrici + (u,v,w)."""
    p1 = eval_point(ut.get("P1_param"), vars_dict)
    p2 = eval_point(ut.get("P2_param"), vars_dict)
    if p1 is None or p2 is None:
        return None, "conic: estremi non valutabili"
    dx = p2.X - p1.X
    dy = p2.Y - p1.Y
    su = ut.get("CtrlProp_u", "")
    sv = ut.get("CtrlProp_v", "")
    # u
    if su == "degenere":
        try:
            cpx = p1.X + float(ut.get("CtrlOff_x"))
        except Exception:
            return None, "conic: CtrlOff_x mancante"
    else:
        try:
            cpx = p1.X + float(su) * dx
        except Exception:
            return None, "conic: CtrlProp_u illeggibile"
    # v
    if sv == "degenere":
        try:
            cpy = p1.Y + float(ut.get("CtrlOff_y"))
        except Exception:
            return None, "conic: CtrlOff_y mancante"
    else:
        try:
            cpy = p1.Y + float(sv) * dy
        except Exception:
            return None, "conic: CtrlProp_v illeggibile"
    try:
        w = float(ut.get("CtrlPeso_w", "1.0"))
    except Exception:
        w = 1.0
    cp = rg.Point3d(cpx, cpy, 0.0)
    # NURBS razionale grado 2 a 3 CP (Bezier conica)
    nc = rg.NurbsCurve.Create(False, 2, [p1, cp, p2])
    if nc is None:
        return None, "conic: Create fallita"
    # imposto il peso del CP intermedio
    nc.Points.SetPoint(1, cp, w)
    return nc, None


def build_free(ut, vars_dict):
    """Curva libera da CtrlPoints (x,y,w | ...) + Nodi (t | ...)."""
    cps_str = ut.get("CtrlPoints")
    if not cps_str:
        return None, "free: CtrlPoints assente"
    cps = []
    weights = []
    for trip in cps_str.split("|"):
        parts = trip.split(",")
        if len(parts) < 2:
            return None, "free: CP malformato"
        x = float(parts[0]); y = float(parts[1])
        w = float(parts[2]) if len(parts) >= 3 else 1.0
        cps.append(rg.Point3d(x, y, 0.0))
        weights.append(w)
    try:
        degree = int(ut.get("Grado", "3"))
    except Exception:
        degree = 3
    nc = rg.NurbsCurve.Create(False, degree, cps)
    if nc is None:
        return None, "free: Create fallita"
    for i in range(len(cps)):
        nc.Points.SetPoint(i, cps[i], weights[i])
    # nodi (se presenti e compatibili)
    nodi_str = ut.get("Nodi")
    if nodi_str:
        try:
            knots = [float(z) for z in nodi_str.split("|")]
            if nc.Knots.Count == len(knots):
                for i in range(len(knots)):
                    nc.Knots[i] = knots[i]
        except Exception:
            pass  # se i nodi non combaciano, tengo quelli di default
    return nc, None


# ------------------------------------------------------------------
def reconstruct_row(ut, vars_dict):
    """Dispatch in base al comando/tipo. Ritorna (curve, errore)."""
    comando = ut.get("Comando", "")
    tipo    = ut.get("Tipo_Originale", "")

    if comando == "_Line":
        return build_line(ut, vars_dict)
    if comando == "_Circle":
        return build_circle(ut, vars_dict)
    if comando == "_Arc":
        return build_arc(ut, vars_dict)
    if comando == "_InterpCrv" or tipo == "Nurbs":
        # conica se ha la terna, altrimenti curva libera
        if ut.get("CtrlProp_u") is not None or ut.get("CtrlPeso_w") is not None:
            return build_conic(ut, vars_dict)
        return build_free(ut, vars_dict)
    return None, "tipo non riconosciuto: %s / %s" % (comando, tipo)


# ------------------------------------------------------------------
def read_txt(filepath):
    """Legge il TXT e ritorna la lista di UserText (uno per riga curva)."""
    rows = []
    f = open(filepath, "r")
    try:
        for line in f:
            line = line.rstrip("\r\n")
            if not line or line.startswith("#"):
                continue
            cells = line.split("\t")
            if len(cells) < 20:
                continue
            tipo = cells[1]
            if tipo == "P":
                continue  # i punti non si ricostruiscono come curve
            ut_str = cells[19]  # colonna UserText (ultima)
            rows.append(ut_str)
    finally:
        f.close()
    return rows


# ------------------------------------------------------------------
def main():
    print("=" * 60)
    print("PKG Verifica Forma v1.0")
    print("=" * 60)

    vars_dict = load_params_from_doc()
    if not vars_dict:
        print("[AVVISO] Nessun parametro PKG_* nei Document User Text.")
        print("         Le geometrie parametriche non saranno valutabili.")
        print("         (Le geometrie libere si ricostruiscono comunque.)")
    else:
        print("Parametri caricati: %s" % ", ".join(
            "%s=%g" % (k, vars_dict[k]) for k in sorted(vars_dict)))

    fd = Rhino.UI.OpenFileDialog()
    fd.Filter = "Text file (*.txt)|*.txt"
    if not fd.ShowOpenDialog():
        print("Annullato.")
        return
    filepath = fd.FileName

    rows = read_txt(filepath)
    print("Righe geometria trovate: %d" % len(rows))

    idx_layer = get_or_create_layer(LAYER_OUT, COLOR_OUT)

    attr = Rhino.DocObjects.ObjectAttributes()
    attr.LayerIndex = idx_layer
    attr.ColorSource = Rhino.DocObjects.ObjectColorSource.ColorFromLayer

    n_ok = 0
    reasons = {}
    for ut_str in rows:
        ut = parse_user_text(ut_str)
        curve, err = reconstruct_row(ut, vars_dict)
        if curve is None:
            reasons[err] = reasons.get(err, 0) + 1
            continue
        gid = sc.doc.Objects.AddCurve(curve, attr)
        if gid != System.Guid.Empty:
            n_ok += 1
        else:
            reasons["AddCurve fallita"] = reasons.get("AddCurve fallita", 0) + 1

    sc.doc.Views.Redraw()

    print("-" * 60)
    print("Ricostruite: %d curve nel layer '%s'" % (n_ok, LAYER_OUT))
    if reasons:
        print("Non ricostruite:")
        for k, v in sorted(reasons.items(), key=lambda kv: -kv[1]):
            print("   - %s: %d" % (k, v))
    print("")
    print("Per la prova di sovrascrittura: confronta visivamente il layer")
    print("'%s' con il tracciato originale (es. comando _SelDup)." % LAYER_OUT)


if __name__ == "__main__":
    main()
