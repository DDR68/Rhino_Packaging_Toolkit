# -*- coding: utf-8 -*-
"""
ECMA A20.20.01.01 - Straight Tuck End
Generatore parametrico fustella per Rhinoceros 7
IronPython 2.7 / RhinoCommon
"""
import Rhino
import scriptcontext as sc
import System

# =============================================================
# PARAMETRI INTERNI (modificabili all'interno dello script)
# =============================================================
inc = 18.0            # Larghezza linguetta incollatura
ganc = 18.0           # Lunghezza patella gancio (inserimento tuck)
chamf = 3.0           # Smusso angolare tab e incollatura
taper = 2.0           # Rastrematura bordo interno tab
fessura_l = 7.0       # Larghezza fessura slit-lock
fessura_p = 2.5       # Profondita fessura slit-lock
nurbs_k = 0.635       # Fattore posizione punto controllo Nurbs tuck

# =============================================================
# FUNZIONI
# =============================================================
def chiedi(prompt, default, lo=None, hi=None):
    gn = Rhino.Input.Custom.GetNumber()
    gn.SetCommandPrompt(prompt)
    gn.SetDefaultNumber(default)
    gn.AcceptNothing(True)
    if lo is not None:
        gn.SetLowerLimit(lo, False)
    if hi is not None:
        gn.SetUpperLimit(hi, False)
    r = gn.Get()
    if r == Rhino.Input.GetResult.Cancel:
        return None
    if r == Rhino.Input.GetResult.Nothing:
        return default
    return gn.Number()

def ensure_layer(name, r, g, b):
    idx = sc.doc.Layers.FindByFullPath(name, -1)
    if idx < 0:
        layer = Rhino.DocObjects.Layer()
        layer.Name = name
        layer.Color = System.Drawing.Color.FromArgb(r, g, b)
        idx = sc.doc.Layers.Add(layer)
    return idx

def pt(x, y):
    return Rhino.Geometry.Point3d(x, y, 0)

def linea(a, b, layer):
    crv = Rhino.Geometry.LineCurve(pt(a[0], a[1]), pt(b[0], b[1]))
    attr = Rhino.DocObjects.ObjectAttributes()
    attr.LayerIndex = layer
    sc.doc.Objects.AddCurve(crv, attr)

def nurbs2(p0, ctrl, p2, layer):
    pts = System.Collections.Generic.List[Rhino.Geometry.Point3d]()
    pts.Add(pt(p0[0], p0[1]))
    pts.Add(pt(ctrl[0], ctrl[1]))
    pts.Add(pt(p2[0], p2[1]))
    crv = Rhino.Geometry.NurbsCurve.Create(False, 2, pts)
    if crv:
        attr = Rhino.DocObjects.ObjectAttributes()
        attr.LayerIndex = layer
        sc.doc.Objects.AddCurve(crv, attr)

# =============================================================
# MAIN
# =============================================================
def main():

    # --- Input parametri da linea di comando ---
    L = chiedi("Larghezza esterna L", 50.0, 10.0)
    if L is None:
        return
    P = chiedi("Profondita esterna P", 25.0, 10.0)
    if P is None:
        return
    A = chiedi("Altezza esterna A", 80.0, 10.0)
    if A is None:
        return
    S = chiedi("Spessore materiale S", 0.5, 0.3, 1.5)
    if S is None:
        return

    # --- Validazione ---
    if P < inc + 3:
        print("Errore: P (%.1f) < incollatura + 3mm (%.1f). Sormonto piega." % (P, inc + 3))
        return
    if A <= 2 * S:
        print("Errore: A deve essere > 2*S (%.1f)." % (2 * S))
        return

    # ==========================================================
    # COORDINATE DERIVATE
    # ==========================================================

    # body_h = altezza corpo tra bighe principali = A - 2S
    body_h = A - 2 * S

    # Orecchio slit-lock = 2*S
    orecchio = 2 * S

    # --- Pannelli asse X ---
    # Straight tuck: entrambi i tuck dal pannello P1
    # inc | P1(L-S) | P2(P-S) | [S] | P3(L) | P4(P-S)
    x0 = 0.0
    x1 = inc                           # Biga Incoll.|P1
    x2 = x1 + L - S                    # Biga P1|P2     (P1 = L-S)
    x3 = x2 + P - S                    # Biga P2 dx     (P2 = P-S)
    x3b = x3 + S                       # Biga P3 sx     (scarico S)
    x4 = x3b + L                       # Biga P3|P4     (P3 = L)
    x5 = x4 + P - S                    # Bordo destro   (P4 = P-S)

    # --- Corpo asse Y ---
    y_bot = 0.0
    y_top = body_h
    y_bot_t = y_bot - S                # Biga P1 fondo (compensata)
    y_top_t = y_top + S                # Biga P1 top   (compensata)

    # --- Incollatura Y (accorciata S su entrambi i lati) ---
    y_inc_bot = y_bot + S
    y_inc_top = y_top - S

    # --- Profondita dust flap: (P + ganc - S) / 2, mai > L/2 ---
    dust_d = min((P + ganc - S) / 2.0, L / 2.0)
    tab_b_y = y_bot - dust_d            # Base tab fondo
    tab_t_y = y_top + dust_d            # Base tab top

    # --- Tuck fondo (da P1, sotto y_bot_t) ---
    tuck_b_ear  = y_bot_t - P
    tuck_b_fold = tuck_b_ear + orecchio
    tuck_b_tip  = tuck_b_fold - ganc

    # --- Tuck top (da P1, sopra y_top_t) ---
    tuck_t_ear  = y_top_t + P
    tuck_t_fold = tuck_t_ear - orecchio
    tuck_t_tip  = tuck_t_fold + ganc

    # --- Bordi tuck P1 ---
    tuck_xl = x1 - S                   # Bordo sinistro tuck
    tuck_xr = x2                       # Bordo destro tuck

    # --- Inizio cordone P1 (intersezione diagonale con y_bot_t/y_top_t) ---
    crd_off = S * 2 * S / (2 * S + taper)
    crd_x = x1 - crd_off

    # ==========================================================
    # SETUP LAYER
    # ==========================================================
    T = ensure_layer("Taglio", 0, 0, 0)
    C = ensure_layer("Cordone", 255, 0, 0)

    # ==========================================================
    # 1. CORDONATURE VERTICALI
    # ==========================================================
    # Incollatura (x1): accorciata S su entrambi i lati
    linea((x1, y_inc_bot), (x1, y_inc_top), C)

    # P2 U-fold (3 segmenti: fondo, sinistra, top)
    linea((x3, y_bot), (x2, y_bot), C)
    linea((x2, y_bot), (x2, y_top), C)
    linea((x2, y_top), (x3, y_top), C)

    # P2|P3 scarico (x3b)
    linea((x3b, y_bot), (x3b, y_top), C)

    # P3|P4 (x4)
    linea((x4, y_bot), (x4, y_top), C)

    # ==========================================================
    # 2. CORDONATURE ORIZZONTALI - FONDO
    # ==========================================================
    # P4 fondo
    linea((x5, y_bot), (x4 + S, y_bot), C)

    # P1 fondo (compensata)
    linea((crd_x, y_bot_t), (x2, y_bot_t), C)

    # Tuck fold fondo
    linea((tuck_xl + fessura_l, tuck_b_fold),
          (tuck_xr - fessura_l, tuck_b_fold), C)

    # ==========================================================
    # 3. CORDONATURE ORIZZONTALI - TOP
    # ==========================================================
    # P4 top
    linea((x5, y_top), (x4 + S, y_top), C)

    # P1 top (compensata)
    linea((crd_x, y_top_t), (x2, y_top_t), C)

    # Tuck fold top
    linea((tuck_xl + fessura_l, tuck_t_fold),
          (tuck_xr - fessura_l, tuck_t_fold), C)

    # ==========================================================
    # 4. TAGLI - BORDI CORPO
    # ==========================================================
    # P3 fondo
    linea((x3b, y_bot), (x4, y_bot), T)
    # P3 top
    linea((x3b, y_top), (x4, y_top), T)
    # Bordo destro (x5)
    linea((x5, y_bot), (x5, y_top), T)

    # ==========================================================
    # 5. TAGLI - SCARICHI FONDO
    # ==========================================================
    # P2|P3 scarico fondo
    linea((x3, y_bot), (x3b, y_bot), T)
    # P3|P4 scarico fondo
    linea((x4, y_bot), (x4 + S, y_bot), T)
    # P1|P2 gradino verticale fondo
    linea((x2, y_bot_t), (x2, y_bot), T)

    # ==========================================================
    # 6. TAGLI - SCARICHI TOP
    # ==========================================================
    linea((x3, y_top), (x3b, y_top), T)
    linea((x4, y_top), (x4 + S, y_top), T)
    linea((x2, y_top), (x2, y_top_t), T)

    # ==========================================================
    # 7. TAGLI - INCOLLATURA
    # ==========================================================
    linea((x1, y_inc_bot), (x0, y_inc_bot + chamf), T)
    linea((x0, y_inc_bot + chamf), (x0, y_inc_top - chamf), T)
    linea((x0, y_inc_top - chamf), (x1, y_inc_top), T)

    # ==========================================================
    # 8. TAGLI - CONNESSIONE INCOLLATURA-TUCK
    # ==========================================================
    # Fondo: diagonale incollatura -> bordo sx tuck
    linea((x1, y_inc_bot), (tuck_xl, y_bot_t - taper), T)
    # Top: diagonale incollatura -> bordo sx tuck
    linea((x1, y_inc_top), (tuck_xl, y_top_t + taper), T)

    # ==========================================================
    # 9. TAGLI - TAB P2 FONDO
    # ==========================================================
    # Esterno (sx, a x2): smusso 45 + verticale
    linea((x2, y_bot), (x2 + chamf, y_bot - chamf), T)
    linea((x2 + chamf, y_bot - chamf), (x2 + chamf, tab_b_y), T)

    # Interno (dx, a x3): verticale + smusso + rastrematura
    linea((x3, y_bot), (x3, y_bot - chamf - taper), T)
    linea((x3, y_bot - chamf - taper),
          (x3 - chamf, y_bot - 2 * chamf - taper), T)
    linea((x3 - chamf, y_bot - 2 * chamf - taper),
          (x3 - chamf - taper, tab_b_y), T)

    # Base tab
    linea((x2 + chamf, tab_b_y), (x3 - chamf - taper, tab_b_y), T)

    # ==========================================================
    # 10. TAGLI - TAB P4 FONDO
    # ==========================================================
    # Interno (sx, a x4+S): verticale + smusso + rastrematura
    linea((x4 + S, y_bot), (x4 + S, y_bot - chamf - taper), T)
    linea((x4 + S, y_bot - chamf - taper),
          (x4 + S + chamf, y_bot - 2 * chamf - taper), T)
    linea((x4 + S + chamf, y_bot - 2 * chamf - taper),
          (x4 + S + chamf + taper, tab_b_y), T)

    # Esterno (dx, a x5): smusso compensato + verticale
    linea((x5, y_bot), (x5 - chamf + S, y_bot - chamf), T)
    linea((x5 - chamf + S, y_bot - chamf), (x5 - chamf + S, tab_b_y), T)

    # Base tab
    linea((x4 + S + chamf + taper, tab_b_y),
          (x5 - chamf + S, tab_b_y), T)

    # ==========================================================
    # 11. TAGLI - TAB P2 TOP
    # ==========================================================
    linea((x2, y_top), (x2 + chamf, y_top + chamf), T)
    linea((x2 + chamf, y_top + chamf), (x2 + chamf, tab_t_y), T)

    linea((x3, y_top), (x3, y_top + chamf + taper), T)
    linea((x3, y_top + chamf + taper),
          (x3 - chamf, y_top + 2 * chamf + taper), T)
    linea((x3 - chamf, y_top + 2 * chamf + taper),
          (x3 - chamf - taper, tab_t_y), T)

    linea((x2 + chamf, tab_t_y), (x3 - chamf - taper, tab_t_y), T)

    # ==========================================================
    # 12. TAGLI - TAB P4 TOP
    # ==========================================================
    linea((x4 + S, y_top), (x4 + S, y_top + chamf + taper), T)
    linea((x4 + S, y_top + chamf + taper),
          (x4 + S + chamf, y_top + 2 * chamf + taper), T)
    linea((x4 + S + chamf, y_top + 2 * chamf + taper),
          (x4 + S + chamf + taper, tab_t_y), T)

    linea((x5, y_top), (x5 - chamf + S, y_top + chamf), T)
    linea((x5 - chamf + S, y_top + chamf),
          (x5 - chamf + S, tab_t_y), T)

    linea((x4 + S + chamf + taper, tab_t_y),
          (x5 - chamf + S, tab_t_y), T)

    # ==========================================================
    # 13. TAGLI - TUCK FONDO (da P1)
    # ==========================================================
    # Bordo sinistro tuck (dalla diagonale all'ear)
    linea((tuck_xl, y_bot_t - taper), (tuck_xl, tuck_b_ear), T)
    # Bordo destro tuck (dalla biga P1 all'ear)
    linea((tuck_xr, y_bot_t), (tuck_xr, tuck_b_ear), T)

    # Fessura sinistra
    linea((tuck_xl, tuck_b_ear),
          (tuck_xl + fessura_l, tuck_b_ear), T)
    linea((tuck_xl + fessura_l, tuck_b_ear),
          (tuck_xl + fessura_l, tuck_b_ear + fessura_p), T)

    # Fessura destra
    linea((tuck_xr, tuck_b_ear),
          (tuck_xr - fessura_l, tuck_b_ear), T)
    linea((tuck_xr - fessura_l, tuck_b_ear),
          (tuck_xr - fessura_l, tuck_b_ear + fessura_p), T)

    # Punta tuck (nurbs + linea)
    tip_b_l = tuck_xl + fessura_l + orecchio
    tip_b_r = tuck_xr - fessura_l - orecchio
    linea((tip_b_l, tuck_b_tip), (tip_b_r, tuck_b_tip), T)

    ctrl_b_y = tuck_b_ear + (tuck_b_tip - tuck_b_ear) * nurbs_k
    nurbs2((tuck_xl, tuck_b_ear), (tuck_xl, ctrl_b_y),
           (tip_b_l, tuck_b_tip), T)
    nurbs2((tuck_xr, tuck_b_ear), (tuck_xr, ctrl_b_y),
           (tip_b_r, tuck_b_tip), T)

    # ==========================================================
    # 14. TAGLI - TUCK TOP (da P1)
    # ==========================================================
    # Bordo sinistro tuck
    linea((tuck_xl, y_top_t + taper), (tuck_xl, tuck_t_ear), T)
    # Bordo destro tuck
    linea((tuck_xr, y_top_t), (tuck_xr, tuck_t_ear), T)

    # Fessura sinistra
    linea((tuck_xl, tuck_t_ear),
          (tuck_xl + fessura_l, tuck_t_ear), T)
    linea((tuck_xl + fessura_l, tuck_t_ear),
          (tuck_xl + fessura_l, tuck_t_ear - fessura_p), T)

    # Fessura destra
    linea((tuck_xr, tuck_t_ear),
          (tuck_xr - fessura_l, tuck_t_ear), T)
    linea((tuck_xr - fessura_l, tuck_t_ear),
          (tuck_xr - fessura_l, tuck_t_ear - fessura_p), T)

    # Punta tuck (nurbs + linea)
    tip_t_l = tuck_xl + fessura_l + orecchio
    tip_t_r = tuck_xr - fessura_l - orecchio
    linea((tip_t_l, tuck_t_tip), (tip_t_r, tuck_t_tip), T)

    ctrl_t_y = tuck_t_ear + (tuck_t_tip - tuck_t_ear) * nurbs_k
    nurbs2((tuck_xl, tuck_t_ear), (tuck_xl, ctrl_t_y),
           (tip_t_l, tuck_t_tip), T)
    nurbs2((tuck_xr, tuck_t_ear), (tuck_xr, ctrl_t_y),
           (tip_t_r, tuck_t_tip), T)

    # ==========================================================
    # 15. METADATI DOCUMENTO
    # ==========================================================
    sc.doc.Strings.SetString("Tipo", "ECMA_A20.20.01.01")
    sc.doc.Strings.SetString("L", "%.2f" % L)
    sc.doc.Strings.SetString("P", "%.2f" % P)
    sc.doc.Strings.SetString("A", "%.2f" % A)
    sc.doc.Strings.SetString("S", "%.2f" % S)

    # ==========================================================
    # FINE
    # ==========================================================
    sc.doc.Views.Redraw()

    print("ECMA A20.20.01.01 generato")
    print("  Esterne: L=%.2f  P=%.2f  A=%.2f" % (L, P, A))
    print("  Spessore: S=%.2f" % S)
    print("  Corpo tra bighe: %.2f mm" % body_h)
    print("  Pannelli: inc=%.1f P1=%.1f P2=%.1f [S] P3=%.1f P4=%.1f" % (
        inc, L - S, P - S, L, P - S))
    print("  Tuck: ganc=%.1f  orecchio=%.1f" % (ganc, orecchio))
    print("  Alette dust: %.2f mm (max %.1f)" % (dust_d, L / 2.0))
    print("  Bbox: %.1f x %.1f mm" % (x5, tuck_t_tip - tuck_b_tip))

main()
