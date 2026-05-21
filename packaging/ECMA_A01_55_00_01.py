#! python 2
# -*- coding: utf-8 -*-

# ECMA A01.55.00.01 - Generatore parametrico fustella
# Toolkit: Rhino_Packaging_Toolkit (DDR68)
# Unita di lavoro interna: millimetri (convertite all'unita del documento)
#
# Parametri:
#   L = Larghezza pannello       (default 70 mm)
#   P = Profondita pannello      (default 50 mm)
#   A = Altezza corpo            (default 100 mm)
#   S = Compensazione spessore   (default 0.5 mm)
#   C = Lembo di incollaggio     (default 18 mm)
#   E = Smusso di fustellazione  (default 2 mm)
#   T = Sporgenza aletta sup.    (default 9 mm)

import Rhino
import scriptcontext as sc
import System
from Rhino.Geometry import Point3d


# Segmenti definiti in forma parametrica simbolica.
# Formato: (tipo, x1_expr, y1_expr, x2_expr, y2_expr)
#   tipo: "T" = Taglio (nero), "C" = Cordone (rosso)
SEGMENTI = [
    ("T", "C+(L-S)+P+L+E", "A+E", "C+(L-S)+P+L", "A"),  # 37
    ("T", "C+(L-S)+P+L", "A", "C+(L-S)+P+L-E", "A+E"),  # 38
    ("T", "C+(L-S)+P+L-E+P", "A+E", "C+(L-S)+P+L-E+P", "A+(L/3)+T"),  # 39
    ("T", "C+(L-S)+P+L-E+P", "A+(L/3)+T", "C+(L-S)+P+L+(P/2)-E", "A+(L/3)+T"),  # 40
    ("T", "C+(L-S)+P+L+(P/2)-E", "A+(L/3)+T", "C+(L-S)+P+L+(P/2)", "A+(L/3)"),  # 41
    ("T", "C+(L-S)+P+L+(P/2)", "A+(L/3)", "C+(L-S)+P+L+E", "A+E"),  # 42
    ("T", "C+(L-S)+(P/2)+E", "A+(L/3)+T", "C+(L-S)+(P/2)", "A+(L/3)"),  # 43
    ("T", "C+(L-S)+E", "A+(L/3)+T", "C+(L-S)+(P/2)+E", "A+(L/3)+T"),  # 44
    ("T", "C+(L-S)+E", "A+E", "C+(L-S)+E", "A+(L/3)+T"),  # 45
    ("T", "C+(L-S)+(P/2)", "A+(L/3)", "C+(L-S)+P-E", "A+E"),  # 46
    ("C", "C+(L-S)+P", "A", "C+(L-S)", "A"),  # 47
    ("T", "C+(L-S)-(L/3)-E", "A+(P/2)+T", "C+(L/3)-S+E", "A+(P/2)+T"),  # 48
    ("T", "C+(L-S)-(L/3)-E", "A+(P/2)+T", "C+(L-S)-(L/3)", "A+(P/2)"),  # 49
    ("T", "C+(L/3)-S+E", "A+(P/2)+T", "C+(L/3)-S", "A+(P/2)"),  # 50
    ("T", "C+(L-S)-E", "A+E", "C+(L-S)-(L/3)", "A+(P/2)"),  # 51
    ("T", "C+(L/3)-S", "A+(P/2)", "C+(E-S)", "A+E"),  # 52
    ("T", "C+(L-S)+P+L-E", "A+(P/2)+T", "C+(L-S)+P+L-(L/3)+E", "A+(P/2)+T"),  # 53
    ("T", "C+(L-S)+P+L-(L/3)+E", "A+(P/2)+T", "C+(L-S)+P+L-(L/3)", "A+(P/2)"),  # 54
    ("T", "C+(L-S)+P+L-(L/3)", "A+(P/2)", "C+(L-S)+P+(L/3)", "A+(P/2)"),  # 55
    ("T", "C+(L-S)+P+(L/3)", "A+(P/2)", "C+(L-S)+P+(L/3)-E", "A+(P/2)+T"),  # 56
    ("T", "C+(L-S)+P+(L/3)-E", "A+(P/2)+T", "C+(L-S)+P+E", "A+(P/2)+T"),  # 57
    ("T", "C+(L-S)+P", "0", "C+(L-S)", "0"),  # 58
    ("T", "0", "3", "0", "A-3"),  # 59
    ("T", "C", "0", "0", "3"),  # 60
    ("T", "C+(L-S)+P+L-E", "A+E", "C+(L-S)+P+L-E", "A+(P/2)+T"),  # 61
    ("T", "C+(L-S)+P+E", "A+(P/2)+T", "C+(L-S)+P+E", "A+E"),  # 62
    ("T", "C+(L-S)+P+E", "A+E", "C+(L-S)+P", "A"),  # 63
    ("T", "C+(L-S)", "A", "C+(L-S)+E", "A+E"),  # 64
    ("T", "C+(L-S)+P-E", "A+E", "C+(L-S)+P", "A"),  # 65
    ("T", "C+(L-S)+P+L+P-S", "A", "C+(L-S)+P+L-E+P", "A+E"),  # 66
    ("T", "C+(L-S)", "A", "C+(L-S)-E", "A+E"),  # 67
    ("T", "C+(E-S)", "A+E", "C", "A"),  # 68
    ("T", "C", "A", "0", "A-3"),  # 69
    ("T", "C+(L-S)", "0", "C", "0"),  # 70
    ("C", "C+(L-S)", "A", "C", "A"),  # 71
    ("C", "C", "A", "C", "0"),  # 72
    ("T", "C+(L-S)+P+L+P-S", "A", "C+(L-S)+P+L+P-S", "0"),  # 73
    ("T", "C+(L-S)+P+L+P-S", "0", "C+(L-S)+P+L", "0"),  # 74
    ("C", "C+(L-S)+P+L+P-S", "A", "C+(L-S)+P+L", "A"),  # 75
    ("C", "C+(L-S)+P+L", "A", "C+(L-S)+P+L", "0"),  # 76
    ("T", "C+(L-S)+P+L", "0", "C+(L-S)+P", "0"),  # 77
    ("C", "C+(L-S)+P+L", "A", "C+(L-S)+P", "A"),  # 78
    ("C", "C+(L-S)+P", "A", "C+(L-S)+P", "0"),  # 79
    ("C", "C+(L-S)", "A", "C+(L-S)", "0"),  # 80
]


def get_or_create_layer(nome, r, g, b):
    idx = sc.doc.Layers.FindByFullPath(nome, -1)
    if idx >= 0:
        return idx
    layer = Rhino.DocObjects.Layer()
    layer.Name = nome
    layer.Color = System.Drawing.Color.FromArgb(r, g, b)
    return sc.doc.Layers.Add(layer)


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


def valuta(expr, ctx):
    # Valuta un'espressione aritmetica nelle variabili C, L, P, A, S, E, T.
    # Le espressioni sono interne e contengono solo numeri e operatori.
    return eval(expr, {"__builtins__": {}}, ctx)


def main():
    scala = Rhino.RhinoMath.UnitScale(
        Rhino.UnitSystem.Millimeters, sc.doc.ModelUnitSystem)

    L = chiedi_numero("Larghezza L (mm)", 70.0, 1.0)
    if L is None:
        print "Annullato"
        return
    P = chiedi_numero("Profondita P (mm)", 50.0, 1.0)
    if P is None:
        print "Annullato"
        return
    A = chiedi_numero("Altezza A (mm)", 100.0, 1.0)
    if A is None:
        print "Annullato"
        return
    S = chiedi_numero("Compensazione spessore S (mm)", 0.5, 0.0)
    if S is None:
        print "Annullato"
        return
    C = chiedi_numero("Lembo incollaggio C (mm)", 18.0, 1.0)
    if C is None:
        print "Annullato"
        return
    E = chiedi_numero("Smusso fustellazione E (mm)", 2.0, 0.0)
    if E is None:
        print "Annullato"
        return
    T = chiedi_numero("Sporgenza aletta T (mm)", 9.0, 0.0)
    if T is None:
        print "Annullato"
        return

    ctx = {
        "L": L * scala,
        "P": P * scala,
        "A": A * scala,
        "S": S * scala,
        "C": C * scala,
        "E": E * scala,
        "T": T * scala,
    }

    sc.doc.Strings.SetString("L", str(ctx["L"]))
    sc.doc.Strings.SetString("P", str(ctx["P"]))
    sc.doc.Strings.SetString("A", str(ctx["A"]))
    sc.doc.Strings.SetString("S", str(ctx["S"]))

    idx_taglio = get_or_create_layer("Taglio", 0, 0, 0)
    idx_cordone = get_or_create_layer("Cordone", 255, 0, 0)

    attr_t = Rhino.DocObjects.ObjectAttributes()
    attr_t.LayerIndex = idx_taglio
    attr_t.ColorSource = Rhino.DocObjects.ObjectColorSource.ColorFromLayer

    attr_c = Rhino.DocObjects.ObjectAttributes()
    attr_c.LayerIndex = idx_cordone
    attr_c.ColorSource = Rhino.DocObjects.ObjectColorSource.ColorFromLayer

    n_t = 0
    n_c = 0
    for seg in SEGMENTI:
        tipo = seg[0]
        x1 = valuta(seg[1], ctx)
        y1 = valuta(seg[2], ctx)
        x2 = valuta(seg[3], ctx)
        y2 = valuta(seg[4], ctx)
        p1 = Point3d(x1, y1, 0.0)
        p2 = Point3d(x2, y2, 0.0)
        if p1.DistanceTo(p2) < 1e-6:
            continue
        if tipo == "C":
            gid = sc.doc.Objects.AddLine(p1, p2, attr_c)
            n_c += 1
        else:
            gid = sc.doc.Objects.AddLine(p1, p2, attr_t)
            n_t += 1
        rh = sc.doc.Objects.FindId(gid)
        if rh:
            rh.Attributes.SetUserString(
                "Tipo", "Piega" if tipo == "C" else "Taglio")
            rh.Attributes.SetUserString("Parametrico",
                "({0}, {1}) -> ({2}, {3})".format(seg[1], seg[2], seg[3], seg[4]))
            sc.doc.Objects.ModifyAttributes(rh, rh.Attributes, True)

    sc.doc.Views.Redraw()
    print "ECMA A01.55.00.01 creata: {0} tagli, {1} cordoni".format(n_t, n_c)


if __name__ == "__main__":
    main()
