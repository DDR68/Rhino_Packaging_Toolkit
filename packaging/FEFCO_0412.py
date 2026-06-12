#! python 2
# -*- coding: utf-8 -*-
# =====================================================================
# FEFCO 0412 - script parametrico
# Generato da export Esporta_Geometrie_Parametrico (Crocera_parametric_export.txt)
# Rhino 7/8 - IronPython 2.7 - RhinoCommon - unita: millimetri
# All'avvio chiede le DIMENSIONI ESTERNE L, P, A, S; al termine mostra
# le DIMENSIONI INTERNE: L-S*4, P-S*2, A-S*3.
# =====================================================================

import Rhino
import scriptcontext as sc
import System
from Rhino.Geometry import Point3d, Arc

# Valori di default (dimensioni esterne del disegno originale, mm)
DEF_L = 80.0
DEF_P = 120.0
DEF_A = 30.0
DEF_S = 2.0
T = 30.0    # Patella / lembo testa-piede (fisso, modificare qui se serve)

def chiedi_numero(prompt, default, minimo):
    gn = Rhino.Input.Custom.GetNumber()
    gn.SetCommandPrompt(prompt)
    gn.SetDefaultNumber(default)
    gn.SetLowerLimit(minimo, False)
    gn.AcceptNothing(True)
    gn.Get()
    if gn.CommandResult() != Rhino.Commands.Result.Success:
        return None
    return gn.Number()

def costruisci_segmenti(L, P, A, S, T):
    # -----------------------------------------------------------------
    # STAZIONI PARAMETRICHE (dalle formule del blocco UserText)
    # -----------------------------------------------------------------
    W1   = L / 2.0 + S * 2 + 1            # mezzo pannello laterale      (45)
    WA   = A + S * 3                      # larghezza ala                (36)
    XA   = W1 + WA                        # bordo interno ala sinistra   (81)
    WC   = L + S * 4 + 2                  # banda centrale               (90)
    XB   = XA + WC                        # bordo interno ala destra    (171)
    XTOT = XA + WC + XA                   # ingombro totale X           (252)
    HS   = P / 2.0 + S + 1                # mezza apertura su P          (63)

    HTOT = T + (A + S * 2) + (P + S * 2 + 2) + (A + S * 2) + T   # ingombro Y (254)
    Y64  = HTOT - T - (A + S * 2) - (P + S * 2 + 2)              # quota base finestra (64)

    # stazioni X (il suffisso numerico e il valore coi parametri di default)
    x000 = 0.0
    x020 = XA - HS + S
    x045 = W1
    x081 = XA
    x083 = XA + S
    x126 = XA + WC / 2.0                  # mezzeria banda centrale
    x169 = XB - S
    x171 = XB
    x207 = XTOT - W1
    x232 = XB + HS - S
    x252 = XTOT

    # stazioni Y
    y000 = 0.0
    y030 = T
    y032 = T + S
    y062 = T + S + A
    y064 = Y64
    y066 = Y64 + S
    y127 = HTOT / 2.0                     # mezzeria
    y188 = HTOT - T - (A + S * 2) - S     # = y190 - S (vedi nota in coda)
    y190 = HTOT - T - (A + S * 2)
    y192 = HTOT - T - (A + S * 2) + S
    y222 = HTOT - T - S
    y224 = HTOT - T
    y254 = HTOT

    # -----------------------------------------------------------------
    # SEGMENTI: (layer, tipo, ...) - "L" linea: x1,y1,x2,y2
    #                                "A" arco 3 punti: x1,y1, xm,ym, x2,y2
    # layer: "T" = Taglio, "C" = Cordone
    # id = riga dell'export di riferimento
    # -----------------------------------------------------------------
    segmenti = [
    ("T", "L", x169, y032, x232, y032),  # id 40
    ("T", "L", x232, y062, x232, y032),  # id 41
    ("T", "L", x171, y062, x232, y062),  # id 42
    ("T", "L", x169, y222, x232, y222),  # id 43
    ("T", "L", x232, y192, x232, y222),  # id 44
    ("T", "L", x171, y192, x232, y192),  # id 45
    ("T", "L", x083, y032, x020, y032),  # id 46
    ("T", "L", x020, y062, x020, y032),  # id 47
    ("T", "L", x081, y062, x020, y062),  # id 48
    ("T", "L", x083, y222, x020, y222),  # id 49
    ("T", "L", x020, y192, x020, y222),  # id 50
    ("T", "L", x081, y192, x020, y192),  # id 51
    ("T", "L", x169, y032, x169, y000),  # id 52
    ("T", "L", x126, y000, x169, y000),  # id 53
    ("C", "L", x126, y030, x169, y030),  # id 54
    ("T", "A", x171, y066, x169, y064, x171, y062),  # id 55 (arco r=S)
    ("C", "L", x207, y066, x207, y127),  # id 56
    ("C", "L", x171, y066, x171, y127),  # id 57
    ("C", "L", x169, y064, x169, y032),  # id 58
    ("T", "L", x171, y066, x252, y066),  # id 59
    ("T", "L", x252, y066, x252, y127),  # id 60
    ("C", "L", x126, y064, x169, y064),  # id 61
    ("T", "L", x169, y222, x169, y254),  # id 62
    ("T", "L", x126, y254, x169, y254),  # id 63
    ("C", "L", x126, y224, x169, y224),  # id 64
    ("T", "A", x171, y188, x169, y190, x171, y192),  # id 65 (arco r=S)
    ("C", "L", x207, y188, x207, y127),  # id 66
    ("C", "L", x171, y188, x171, y127),  # id 67
    ("C", "L", x169, y190, x169, y222),  # id 68
    ("T", "L", x171, y188, x252, y188),  # id 69
    ("T", "L", x252, y188, x252, y127),  # id 70
    ("C", "L", x126, y190, x169, y190),  # id 71
    ("T", "L", x083, y032, x083, y000),  # id 72
    ("T", "L", x126, y000, x083, y000),  # id 73
    ("C", "L", x126, y030, x083, y030),  # id 74
    ("T", "A", x081, y066, x083, y064, x081, y062),  # id 75 (arco r=S)
    ("C", "L", x045, y066, x045, y127),  # id 76
    ("C", "L", x081, y066, x081, y127),  # id 77
    ("C", "L", x083, y064, x083, y032),  # id 78
    ("T", "L", x081, y066, x000, y066),  # id 79
    ("T", "L", x000, y066, x000, y127),  # id 80
    ("C", "L", x126, y064, x083, y064),  # id 81
    ("T", "L", x083, y222, x083, y254),  # id 82
    ("T", "L", x126, y254, x083, y254),  # id 83
    ("C", "L", x126, y224, x083, y224),  # id 84
    ("T", "A", x081, y188, x083, y190, x081, y192),  # id 85 (arco r=S)
    ("C", "L", x045, y188, x045, y127),  # id 86
    ("C", "L", x081, y188, x081, y127),  # id 87
    ("C", "L", x083, y190, x083, y222),  # id 88
    ("T", "L", x081, y188, x000, y188),  # id 89
    ("T", "L", x000, y188, x000, y127),  # id 90
    ("C", "L", x126, y190, x083, y190),  # id 91
    ]
    return segmenti

# NOTA AUTO-VERIFICA: nell'export la quota y=188 compare con due formule
# diverse: Y64+S+(P+S) e HTOT-T-(A+2S)-S, coincidenti solo per S=2.
# Si adotta la seconda (y188 = y190 - S), coerente con la simmetria del
# disegno e con y066 = y064 + S: gli archi di raccordo restano semicerchi
# di raggio S e le linee orizzontali per qualsiasi spessore.

# === FINE DATI PARAMETRICI ===

def get_or_create_layer(nome, r, g, b):
    idx = sc.doc.Layers.FindByFullPath(nome, -1)
    if idx >= 0:
        return idx
    layer = Rhino.DocObjects.Layer()
    layer.Name = nome
    layer.Color = System.Drawing.Color.FromArgb(r, g, b)
    return sc.doc.Layers.Add(layer)

def main():
    # -------------------- INPUT DIMENSIONI ESTERNE --------------------
    L = chiedi_numero("DIMENSIONI ESTERNE - Larghezza L (mm)", DEF_L, 1.0)
    if L is None:
        print "Annullato"
        return
    P = chiedi_numero("DIMENSIONI ESTERNE - Profondita P (mm)", DEF_P, 1.0)
    if P is None:
        print "Annullato"
        return
    A = chiedi_numero("DIMENSIONI ESTERNE - Altezza A (mm)", DEF_A, 1.0)
    if A is None:
        print "Annullato"
        return
    S = chiedi_numero("Spessore materiale S (mm)", DEF_S, 0.1)
    if S is None:
        print "Annullato"
        return

    segmenti = costruisci_segmenti(L, P, A, S, T)

    layer_idx = {
        "T": get_or_create_layer("Taglio", 0, 0, 0),
        "C": get_or_create_layer("Cordone", 255, 0, 0),
        "M": get_or_create_layer("MezzoTaglio", 0, 128, 0),
        "F": get_or_create_layer("Foratore", 255, 0, 255),
    }

    n_ok = 0
    n_err = 0
    bbox = Rhino.Geometry.BoundingBox.Empty

    for seg in segmenti:
        tipo = seg[0]
        kind = seg[1]

        attr = Rhino.DocObjects.ObjectAttributes()
        attr.LayerIndex = layer_idx[tipo]
        attr.ColorSource = Rhino.DocObjects.ObjectColorSource.ColorFromLayer

        try:
            if kind == "L":
                p1 = Point3d(seg[2], seg[3], 0.0)
                p2 = Point3d(seg[4], seg[5], 0.0)
                if p1.DistanceTo(p2) < sc.doc.ModelAbsoluteTolerance:
                    n_err += 1
                    print "Segmento degenere saltato: %s" % str(seg)
                    continue
                guid = sc.doc.Objects.AddLine(p1, p2, attr)
                bbox.Union(p1)
                bbox.Union(p2)
            else:
                p1 = Point3d(seg[2], seg[3], 0.0)
                pm = Point3d(seg[4], seg[5], 0.0)
                p2 = Point3d(seg[6], seg[7], 0.0)
                arco = Arc(p1, pm, p2)
                if not arco.IsValid:
                    n_err += 1
                    print "Arco non valido saltato: %s" % str(seg)
                    continue
                guid = sc.doc.Objects.AddArc(arco, attr)
                bb = arco.ToNurbsCurve().GetBoundingBox(True)
                bbox.Union(bb)

            if guid != System.Guid.Empty:
                n_ok += 1
            else:
                n_err += 1
        except Exception, ex:
            n_err += 1
            print "Errore su segmento %s: %s" % (str(seg), str(ex))

    # metadati documento (dimensioni esterne usate)
    sc.doc.Strings.SetString("L", str(L))
    sc.doc.Strings.SetString("P", str(P))
    sc.doc.Strings.SetString("A", str(A))
    sc.doc.Strings.SetString("S", str(S))
    sc.doc.Strings.SetString("T", str(T))
    sc.doc.Strings.SetString("Modello", "FEFCO 0412")

    sc.doc.Views.Redraw()

    if bbox.IsValid:
        dx = bbox.Max.X - bbox.Min.X
        dy = bbox.Max.Y - bbox.Min.Y
        print "FEFCO 0412 creato: %d segmenti (%d errori) - ingombro %.1f x %.1f mm" % (n_ok, n_err, dx, dy)
    else:
        print "FEFCO 0412: %d segmenti, %d errori" % (n_ok, n_err)

    # ----------------- FINESTRA DIMENSIONI INTERNE --------------------
    Li = L - S * 4
    Pi = P - S * 2
    Ai = A - S * 3
    msg = ("DIMENSIONI INTERNE\n\n"
           "L = L - S*4 = %.1f mm\n"
           "P = P - S*2 = %.1f mm\n"
           "A = A - S*3 = %.1f mm\n\n"
           "(esterne: L=%.1f  P=%.1f  A=%.1f  S=%.1f)") % (Li, Pi, Ai, L, P, A, S)
    Rhino.UI.Dialogs.ShowMessage(msg, "FEFCO 0412 - Dimensioni interne")

if __name__ == "__main__":
    main()
