#! python 2
# -*- coding: utf-8 -*-
"""
ECMA A01.55.00.01 - Fascetta tubolare con chiusura a incastro sul top
Generatore parametrico fustella per Rhinoceros 7 / 8
IronPython 2.7 / RhinoCommon

Topologia:
  - 4 pannelli + patella di incollatura laterale (sx)
  - Fondo APERTO (taglio dritto, nessuna aletta inferiore)
  - 4 alette superiori SPECIALIZZATE che si chiudono in sequenza:

    1) P3 si piega per prima (coperchio fondo)
       Pannello L dx, forma a "ponte" con 2 ali alte ai bordi
       Tacca centrale incassata T = slot finale per linguetta di P1
       Le ali alte verticali (su x3 e x4) ricevono linguette P2/P4

    2) P2 e P4 si piegano poi (linguette laterali)
       Pannelli P, forma asimmetrica
       P2: verticale alta sx + diagonale 45 dx (scarico)
       P4: diagonale 45 sx (scarico) + verticale alta dx sul bordo
       I lati verticali si appoggiano alle ali di P3

    3) P1 si piega per ultima (chiusura definitiva)
       Pannello L sx, forma M simmetrica con linguetta centrale rialzata
       La linguetta centrale (larga L-P) si infila nella tacca di P3
       Le 2 diagonali 45 esterne sono scarichi per non urtare P2/P4

Regola di chiusura (vincolante):
  L >= P + 2*T
  Garantisce che la linguetta di P1 raggiunga la tacca di P3
  senza interferenze laterali con P2 e P4.

Riferimento dimensionale (default):
  L=70, P=50, A=100, S=0.5, C=18, E=2, T=9 -> bbox 257 x 134 mm
"""

import Rhino
import scriptcontext as sc
import System

# =============================================================
# PARAMETRI INTERNI
# =============================================================
inc      = 18.0   # Larghezza patella di incollatura (C)
chamf    = 2.0    # Smusso angolare alette (E)
tacca    = 9.0    # Profondita tacca incastro / sporgenza linguetta (T)
sm_inc   = 3.0    # Smusso patella incollatura (verticale)

# =============================================================
# FUNZIONI HELPER
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

def polilinea(punti, layer):
    """Disegna segmenti consecutivi collegando i punti dati."""
    for i in range(len(punti) - 1):
        linea(punti[i], punti[i+1], layer)

# =============================================================
# MAIN
# =============================================================
def main():
    # --- Input ---
    L = chiedi("Larghezza esterna L (pannello lungo)", 70.0, 10.0)
    if L is None:
        return
    P = chiedi("Profondita esterna P (pannello corto)", 50.0, 10.0)
    if P is None:
        return
    A = chiedi("Altezza esterna A", 100.0, 10.0)
    if A is None:
        return
    S = chiedi("Spessore materiale S", 0.5, 0.3, 1.5)
    if S is None:
        return

    # --- Validazione geometrica ---
    if L < P + 2 * tacca:
        print("Errore: regola di chiusura non rispettata.")
        print("  L=%.1f deve essere >= P + 2*T = %.1f + 2*%.1f = %.1f" % (
            L, P, tacca, P + 2 * tacca))
        print("  Differenza: %.1f mm. Aumentare L o ridurre T." % (
            P + 2 * tacca - L))
        return
    if P < 2 * (chamf + tacca):
        print("Errore: P (%.1f) troppo piccolo per ospitare tacche+smussi (min %.1f)."
              % (P, 2 * (chamf + tacca)))
        return
    if A <= 2 * sm_inc:
        print("Errore: A (%.1f) deve essere > 2*sm_inc (%.1f)." % (A, 2 * sm_inc))
        return
    if chamf >= P / 2.0:
        print("Errore: smusso E (%.1f) deve essere < P/2 (%.1f)." % (chamf, P / 2.0))
        return

    # ==========================================================
    # COORDINATE DERIVATE
    # ==========================================================
    # Bighe X: inc | P1=L-S | P2=P | P3=L | P4=P-S
    x0 = 0.0
    x1 = inc
    x2 = x1 + L - S
    x3 = x2 + P
    x4 = x3 + L
    x5 = x4 + P - S

    # Quote Y
    y_bot     = 0.0
    y_top     = A
    y_inc_bot = y_bot + sm_inc
    y_inc_top = y_top - sm_inc
    y_E       = y_top + chamf            # fine smusso angolare
    y_t       = y_top + (P / 2.0)        # quota scalino tacca
    y_h       = y_top + (P / 2.0) + tacca  # base alta alette

    # Proiezione orizzontale diagonali 45
    diag = (P / 2.0) - chamf

    # ==========================================================
    # SETUP LAYER
    # ==========================================================
    LT = ensure_layer("Taglio",   0,   0,   0)
    LC = ensure_layer("Cordone", 255,   0,   0)

    # ==========================================================
    # 1. CORDONATURE VERTICALI (bighe pannelli)
    # ==========================================================
    linea((x1, y_bot),     (x1, y_top),     LC)  # incollatura (cordone completo)
    linea((x2, y_bot),     (x2, y_top),     LC)
    linea((x3, y_bot),     (x3, y_top),     LC)
    linea((x4, y_bot),     (x4, y_top),     LC)

    # ==========================================================
    # 2. CORDONATURE ORIZZONTALI - TOP (piega alette)
    # ==========================================================
    linea((x1, y_top), (x2, y_top), LC)  # P1
    linea((x2, y_top), (x3, y_top), LC)  # P2
    linea((x3, y_top), (x4, y_top), LC)  # P3
    linea((x4, y_top), (x5, y_top), LC)  # P4

    # ==========================================================
    # 3. TAGLI - FONDO APERTO (segmentato per pannello)
    # ==========================================================
    # Il fondo e' suddiviso in 4 segmenti sulle bighe verticali per
    # preservare la corrispondenza pannello-segmento (utile per
    # esplosione e annotazione).
    linea((x1, y_bot), (x2, y_bot), LT)
    linea((x2, y_bot), (x3, y_bot), LT)
    linea((x3, y_bot), (x4, y_bot), LT)
    linea((x4, y_bot), (x5, y_bot), LT)

    # ==========================================================
    # 4. TAGLI - BORDO DESTRO FUSTELLA (solo corpo, fino a y_top)
    # ==========================================================
    # La parte alta del bordo (da y_top a y_h) e' tracciata dall'aletta P4
    # come segmento finale (x5, y_top) -> (x5 - chamf + S, y_E).
    linea((x5, y_bot), (x5, y_top), LT)

    # ==========================================================
    # 5. TAGLI - PATELLA INCOLLATURA (trapezio sx)
    # ==========================================================
    # Trapezio con base maggiore a destra (su cordone x1, da y_bot a y_top)
    # e base minore a sinistra (da y_inc_bot a y_inc_top, su x0).
    # I lati corti sono 2 diagonali di pendenza sm_inc che raccordano
    # x0 a x1 sul fondo (y_bot=0) e in cima (y_top=A).
    linea((x0, y_inc_bot), (x1, y_bot), LT)   # diagonale inferiore
    linea((x0, y_inc_bot), (x0, y_inc_top), LT)  # lato sx verticale
    linea((x0, y_inc_top), (x1, y_top), LT)   # diagonale superiore

    # ==========================================================
    # 6. TAGLI - ALETTA P1 (L sx, chiude ULTIMA, M simmetrica)
    # ==========================================================
    # 8 vertici: 18,100 -> 19.5,102 -> 42.5,125 -> 42.5,134 -> 62.5,134
    #            -> 62.5,125 -> 85.5,102 -> 87.5,100
    # Compensazione: lato sx ha raccordo E spostato di -S verso il cordone
    # incollatura, perche' la patella x1 cede S di sormonto.
    p1 = [
        (x1,                       y_top),  # 18.0  ,100
        (x1 + chamf - S,           y_E),    # 19.5  ,102
        (x1 + chamf - S + diag,    y_t),    # 42.5  ,125
        (x1 + chamf - S + diag,    y_h),    # 42.5  ,134
        (x2 - chamf - diag,        y_h),    # 62.5  ,134
        (x2 - chamf - diag,        y_t),    # 62.5  ,125
        (x2 - chamf,               y_E),    # 85.5  ,102
        (x2,                       y_top),  # 87.5  ,100
    ]
    polilinea(p1, LT)

    # ==========================================================
    # 7. TAGLI - ALETTA P2 (P, linguetta asimm. SX verticale)
    # ==========================================================
    # 7 vertici: 87.5,100 -> 89.5,102 -> 89.5,134 -> 114.5,134
    #            -> 112.5,125 -> 135.5,102 -> 137.5,100
    p2 = [
        (x2,                       y_top),  # 87.5  ,100
        (x2 + chamf,               y_E),    # 89.5  ,102
        (x2 + chamf,               y_h),    # 89.5  ,134  - verticale alta sx
        (x2 + chamf + (P / 2.0),   y_h),    # 114.5 ,134  - base alta dx
        (x3 - chamf - diag,        y_t),    # 112.5 ,125  - gomito interno (diag corta E,T)
        (x3 - chamf,               y_E),    # 135.5 ,102  - diagonale 45 scarico
        (x3,                       y_top),  # 137.5 ,100
    ]
    polilinea(p2, LT)

    # ==========================================================
    # 8. TAGLI - ALETTA P3 (L dx, coperchio, chiude PER PRIMA)
    # ==========================================================
    # 10 vertici: 137.5,100 -> 139.5,102 -> 139.5,134 -> 160.5,134
    #             -> 162.5,125 -> 182.5,125 -> 184.5,134 -> 205.5,134
    #             -> 205.5,102 -> 207.5,100
    p3 = [
        (x3,                          y_top),  # 137.5 ,100
        (x3 + chamf,                  y_E),    # 139.5 ,102
        (x3 + chamf,                  y_h),    # 139.5 ,134 - cima ala sx
        (x3 + chamf + diag - chamf,   y_h),    # 160.5 ,134 - fine spallina sx
        (x3 + chamf + diag,           y_t),    # 162.5 ,125 - gomito interno sx (diag E,T)
        (x4 - chamf - diag,           y_t),    # 182.5 ,125 - gomito interno dx
        (x4 - chamf - diag + chamf,   y_h),    # 184.5 ,134 - inizio spallina dx (diag E,T)
        (x4 - chamf,                  y_h),    # 205.5 ,134 - cima ala dx
        (x4 - chamf,                  y_E),    # 205.5 ,102 - base ala dx verticale
        (x4,                          y_top),  # 207.5 ,100
    ]
    polilinea(p3, LT)

    # ==========================================================
    # 9. TAGLI - ALETTA P4 (P-S, linguetta asimm. DX verticale)
    # ==========================================================
    # 7 vertici: 207.5,100 -> 209.5,102 -> 232.5,125 -> 230.5,134
    #            -> 255.5,134 -> 255.5,102 -> 257.0,100
    # Speculare di P2: DX verticale sul bordo fustella (no smusso a dx perche'
    # il bordo destro coincide con la verticale alta della linguetta).
    p4 = [
        (x4,                       y_top),  # 207.5 ,100
        (x4 + chamf,               y_E),    # 209.5 ,102
        (x4 + chamf + diag,        y_t),    # 232.5 ,125 - diagonale 45 scarico
        (x4 + chamf + diag - chamf,y_h),    # 230.5 ,134 - gomito interno (diag E,T)
        (x5 - chamf + S,           y_h),    # 255.5 ,134 - base alta
        (x5 - chamf + S,           y_E),    # 255.5 ,102 - verticale alta dx
        (x5,                       y_top),  # 257.0 ,100 - bordo fustella
    ]
    polilinea(p4, LT)

    # ==========================================================
    # 10. METADATI DOCUMENTO
    # ==========================================================
    sc.doc.Strings.SetString("Tipo", "ECMA_A01.55.00.01")
    sc.doc.Strings.SetString("L", "%.2f" % L)
    sc.doc.Strings.SetString("P", "%.2f" % P)
    sc.doc.Strings.SetString("A", "%.2f" % A)
    sc.doc.Strings.SetString("S", "%.2f" % S)

    # ==========================================================
    # FINE
    # ==========================================================
    sc.doc.Views.Redraw()
    print("ECMA A01.55.00.01 generato")
    print("  Esterne: L=%.2f P=%.2f A=%.2f" % (L, P, A))
    print("  Spessore: S=%.2f  Colla: inc=%.1f" % (S, inc))
    print("  Smussi: E=%.1f  Tacca: T=%.1f" % (chamf, tacca))
    print("  Pannelli: inc=%.1f P1=%.1f P2=%.1f P3=%.1f P4=%.1f" % (
        inc, L - S, P, L, P - S))
    print("  Regola chiusura: L (%.1f) >= P + 2T (%.1f)  margine %.1f mm" % (
        L, P + 2 * tacca, L - P - 2 * tacca))
    print("  Sequenza chiusura: P3 (coperchio) -> P2,P4 (linguette) -> P1 (top)")
    print("  Bbox: %.1f x %.1f mm" % (x5, y_h))

main()
