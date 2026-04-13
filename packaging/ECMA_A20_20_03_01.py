# -*- coding: utf-8 -*-
"""
ECMA A20.20.03.01 - Reverse Tuck End
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
chamf = 3.0           # Smusso angolare dust flap e incollatura
taper = 2.0           # Rastrematura bordo esterno dust flap
orecchio = 1.0        # Sporgenza orecchio oltre piega tuck
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

    # A = dimensione esterna (tra bighe compensate y_top_t e y_bot_t)
    # body_h = altezza tra bighe P2/P4 = A - 2S
    body_h = A - 2 * S

    # --- Pannelli asse X ---
    x0 = 0.0
    x1 = inc                           # Biga Incoll.|P1
    x2 = x1 + L - S                    # Biga P1|P2     (P1 = L-S)
    x3 = x2 + P - 2 * S                # Biga P2|P3     (P2 = P-2S)
    x4 = x3 + L                        # Biga P3|P4     (P3 = L)
    x5 = x4 + P - S                    # Bordo destro   (P4 = P-S)

    # --- Corpo asse Y ---
    y_bot = 0.0
    y_top = body_h
    y_bot_t = y_bot - S
    y_top_t = y_top + S

    # --- Profondita dust flap ---
    # (P + ganc - S) / 2, mai > L/2
    dust_d = min((P + ganc - S) / 2.0, L / 2.0)

    # --- Tuck inferiore (da P3) ---
    tuck_b_fold = y_bot_t - P + orecchio
    tuck_b_ear  = y_bot_t - P
    tuck_b_tip  = tuck_b_fold - ganc

    # --- Tuck superiore (da P1) ---
    tuck_t_fold = y_top_t + P - orecchio
    tuck_t_ear  = y_top_t + P
    tuck_t_tip  = tuck_t_fold + ganc

    # --- Centro P3 ---
    cx = (x3 + x4) / 2.0

    # --- Incollatura Y ---
    y_inc_top = y_top - S
    y_inc_bot = y_bot

    # ==========================================================
    # SETUP LAYER
    # ==========================================================
    T = ensure_layer("Taglio", 0, 0, 0)
    C = ensure_layer("Cordone", 255, 0, 0)

    # ==========================================================
    # 1. CORDONATURE VERTICALI
    # ==========================================================
    linea((x1, y_bot), (x1, y_inc_top), C)
    linea((x2, y_bot), (x2, y_top), C)
    linea((x3, y_bot), (x3, y_top), C)
    linea((x4, y_bot), (x4, y_top), C)

    # ==========================================================
    # 2. CORDONATURE ORIZZONTALI - FONDO
    # ==========================================================
    linea((x2 + S, y_bot), (x3, y_bot), C)
    linea((x3, y_bot_t), (cx, y_bot_t), C)
    linea((cx, y_bot_t), (x4, y_bot_t), C)
    linea((x4, y_bot), (x5, y_bot), C)

    # ==========================================================
    # 3. CORDONATURE ORIZZONTALI - TOP
    # ==========================================================
    linea((x1, y_top_t), (x2, y_top_t), C)
    linea((x2, y_top), (x3 - S, y_top), C)
    linea((x4 + S, y_top), (x5, y_top), C)

    # ==========================================================
    # 4. CORDONATURE TUCK FOLD
    # ==========================================================
    linea((x3 + fessura_l, tuck_b_fold), (cx, tuck_b_fold), C)
    linea((cx, tuck_b_fold), (x4 - fessura_l, tuck_b_fold), C)

    tuck_t_slot_l = x1 + fessura_l
    tuck_t_slot_r = x2 - fessura_l
    linea((tuck_t_slot_l, tuck_t_fold), (tuck_t_slot_r, tuck_t_fold), C)

    # ==========================================================
    # 5. TAGLI - BORDI CORPO
    # ==========================================================
    linea((x1, y_bot), (x2, y_bot), T)
    linea((x3, y_top), (x4, y_top), T)
    linea((x5, y_bot), (x5, y_top), T)

    # ==========================================================
    # 6. TAGLI - SCARICHI (S = spessore)
    # ==========================================================
    # Fondo
    linea((x2, y_bot), (x2 + S, y_bot), T)
    linea((x3, y_bot), (x3, y_bot_t), T)
    linea((x4, y_bot_t), (x4, y_bot), T)
    # Top
    linea((x2, y_top), (x2, y_top_t), T)
    linea((x3 - S, y_top), (x3, y_top), T)
    linea((x4, y_top), (x4 + S, y_top), T)

    # ==========================================================
    # 7. TAGLI - INCOLLATURA
    # ==========================================================
    linea((x1, y_inc_bot), (x0, y_inc_bot + chamf), T)
    linea((x0, y_inc_bot + chamf), (x0, y_inc_top - chamf), T)
    linea((x0, y_inc_top - chamf), (x1, y_inc_top), T)

    # ==========================================================
    # 8. TAGLI - DUST FLAP FONDO P2
    # ==========================================================
    df_b2_ox = x2 + S
    linea((df_b2_ox, y_bot), (df_b2_ox, y_bot - chamf - taper), T)
    linea((df_b2_ox, y_bot - chamf - taper),
          (df_b2_ox + chamf, y_bot - 2 * chamf - taper), T)
    linea((df_b2_ox + chamf, y_bot - 2 * chamf - taper),
          (df_b2_ox + chamf + taper, y_bot - dust_d), T)

    linea((x3, y_bot), (x3 - chamf, y_bot - chamf), T)
    linea((x3 - chamf, y_bot - chamf), (x3 - chamf, y_bot - dust_d), T)

    linea((df_b2_ox + chamf + taper, y_bot - dust_d),
          (x3 - chamf, y_bot - dust_d), T)

    # ==========================================================
    # 9. TAGLI - DUST FLAP FONDO P4
    # ==========================================================
    linea((x4, y_bot), (x4 + chamf, y_bot - chamf), T)
    linea((x4 + chamf, y_bot - chamf), (x4 + chamf, y_bot - dust_d), T)

    linea((x5, y_bot), (x5, y_bot - chamf - taper), T)
    linea((x5, y_bot - chamf - taper),
          (x5 - chamf, y_bot - 2 * chamf - taper), T)
    linea((x5 - chamf, y_bot - 2 * chamf - taper),
          (x5 - chamf - taper, y_bot - dust_d), T)

    linea((x4 + chamf, y_bot - dust_d),
          (x5 - chamf - taper, y_bot - dust_d), T)

    # ==========================================================
    # 10. TAGLI - DUST FLAP TOP P2
    # ==========================================================
    linea((x2, y_top), (x2 + chamf, y_top + chamf), T)
    linea((x2 + chamf, y_top + chamf), (x2 + chamf, y_top + dust_d), T)

    df_t2_ix = x3 - S
    linea((df_t2_ix, y_top), (df_t2_ix, y_top + chamf + taper), T)
    linea((df_t2_ix, y_top + chamf + taper),
          (df_t2_ix - chamf, y_top + 2 * chamf + taper), T)
    linea((df_t2_ix - chamf, y_top + 2 * chamf + taper),
          (df_t2_ix - chamf - taper, y_top + dust_d), T)

    linea((x2 + chamf, y_top + dust_d),
          (df_t2_ix - chamf - taper, y_top + dust_d), T)

    # ==========================================================
    # 11. TAGLI - DUST FLAP TOP P4
    # ==========================================================
    df_t4_ix = x4 + S
    linea((df_t4_ix, y_top), (df_t4_ix, y_top + chamf + taper), T)
    linea((df_t4_ix, y_top + chamf + taper),
          (df_t4_ix + chamf, y_top + 2 * chamf + taper), T)
    linea((df_t4_ix + chamf, y_top + 2 * chamf + taper),
          (df_t4_ix + chamf + taper, y_top + dust_d), T)

    linea((x5, y_top), (x5 - chamf, y_top + chamf), T)
    linea((x5 - chamf, y_top + chamf), (x5 - chamf, y_top + dust_d), T)

    linea((df_t4_ix + chamf + taper, y_top + dust_d),
          (x5 - chamf, y_top + dust_d), T)

    # ==========================================================
    # 12. TAGLI - TUCK FONDO (da P3)
    # ==========================================================
    linea((x3, y_bot_t), (x3, tuck_b_ear), T)
    linea((x4, y_bot_t), (x4, tuck_b_ear), T)

    linea((x3, tuck_b_ear), (x3 + fessura_l, tuck_b_ear), T)
    linea((x3 + fessura_l, tuck_b_ear),
          (x3 + fessura_l, tuck_b_ear + fessura_p), T)

    linea((x4, tuck_b_ear), (x4 - fessura_l, tuck_b_ear), T)
    linea((x4 - fessura_l, tuck_b_ear),
          (x4 - fessura_l, tuck_b_ear + fessura_p), T)

    tip_b_l = x3 + fessura_l + orecchio
    tip_b_r = x4 - fessura_l - orecchio
    linea((tip_b_l, tuck_b_tip), (tip_b_r, tuck_b_tip), T)

    ctrl_b_y = tuck_b_ear + (tuck_b_tip - tuck_b_ear) * nurbs_k
    nurbs2((x3, tuck_b_ear), (x3, ctrl_b_y), (tip_b_l, tuck_b_tip), T)
    nurbs2((x4, tuck_b_ear), (x4, ctrl_b_y), (tip_b_r, tuck_b_tip), T)

    # ==========================================================
    # 13. TAGLI - TUCK TOP (da P1)
    # ==========================================================
    linea((x1, y_inc_top), (x1, y_top_t), T)
    linea((x2, y_top_t), (x2, tuck_t_ear), T)
    linea((x1, y_top_t), (x1, tuck_t_ear), T)

    linea((x1, tuck_t_ear), (x1 + fessura_l, tuck_t_ear), T)
    linea((x1 + fessura_l, tuck_t_ear),
          (x1 + fessura_l, tuck_t_ear - fessura_p), T)

    linea((x2, tuck_t_ear), (x2 - fessura_l, tuck_t_ear), T)
    linea((x2 - fessura_l, tuck_t_ear),
          (x2 - fessura_l, tuck_t_ear - fessura_p), T)

    tip_t_l = x1 + fessura_l + orecchio
    tip_t_r = x2 - fessura_l - orecchio
    linea((tip_t_l, tuck_t_tip), (tip_t_r, tuck_t_tip), T)

    ctrl_t_y = tuck_t_ear + (tuck_t_tip - tuck_t_ear) * nurbs_k
    nurbs2((x1, tuck_t_ear), (x1, ctrl_t_y), (tip_t_l, tuck_t_tip), T)
    nurbs2((x2, tuck_t_ear), (x2, ctrl_t_y), (tip_t_r, tuck_t_tip), T)

    # ==========================================================
    # 14. METADATI DOCUMENTO
    # ==========================================================
    sc.doc.Strings.SetString("Tipo", "ECMA_A20.20.03.01")
    sc.doc.Strings.SetString("L", "%.2f" % L)
    sc.doc.Strings.SetString("P", "%.2f" % P)
    sc.doc.Strings.SetString("A", "%.2f" % A)
    sc.doc.Strings.SetString("S", "%.2f" % S)

    # ==========================================================
    # FINE
    # ==========================================================
    sc.doc.Views.Redraw()

    print("ECMA A20.20.03.01 generato")
    print("  Esterne: L=%.2f  P=%.2f  A=%.2f" % (L, P, A))
    print("  Spessore: S=%.2f" % S)
    print("  Interne: L=%.2f  P=%.2f  A=%.2f" % (L - 3 * S, P - 2 * S, A - 4 * S))
    print("  Corpo tra bighe P2/P4: %.2f mm" % body_h)
    print("  Alette: %.2f mm (max %.1f)" % (dust_d, L / 2.0))
    print("  Tuck: P+ganc-S = %.1f mm" % (P + ganc - S))
    print("  Pannelli: inc=%.1f P1=%.1f P2=%.1f P3=%.1f P4=%.1f" % (
        inc, L - S, P - 2 * S, L, P - S))
    print("  Bbox: %.1f x %.1f mm" % (x5, tuck_t_tip - tuck_b_tip))

main()
