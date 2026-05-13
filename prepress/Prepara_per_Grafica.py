#! python 2
# -*- coding: utf-8 -*-
import Rhino
import scriptcontext as sc
import System


def get_effective_color(rh_obj):
    """Restituisce il colore effettivo dell'oggetto (da oggetto o da layer)."""
    attr = rh_obj.Attributes
    if attr.ColorSource == Rhino.DocObjects.ObjectColorSource.ColorFromObject:
        return attr.ObjectColor
    layer = sc.doc.Layers[attr.LayerIndex]
    return layer.Color


def color_match(c, r, g, b, tolerance=13):
    """Verifica se il colore c rientra nella soglia +/-5% (13/255) da (r,g,b)."""
    return (abs(int(c.R) - r) <= tolerance
            and abs(int(c.G) - g) <= tolerance
            and abs(int(c.B) - b) <= tolerance)


def get_layer_name(rh_obj):
    """Restituisce il nome semplice del layer dell'oggetto."""
    idx = rh_obj.Attributes.LayerIndex
    if idx < 0 or idx >= sc.doc.Layers.Count:
        return ""
    return sc.doc.Layers[idx].Name


def ensure_layer(name, color=None):
    """Crea il layer se non esiste, restituisce l'indice."""
    idx = sc.doc.Layers.FindByFullPath(name, -1)
    if idx >= 0:
        return idx
    layer = Rhino.DocObjects.Layer()
    layer.Name = name
    if color is not None:
        layer.Color = color
    idx = sc.doc.Layers.Add(layer)
    if idx < 0:
        for i in range(sc.doc.Layers.Count):
            if sc.doc.Layers[i].Name == name:
                return i
    return idx


def find_linetype_index(names_to_try):
    """Cerca un tipo linea per nome (prova piu' varianti). Restituisce indice o -1."""
    for name in names_to_try:
        lt = sc.doc.Linetypes.FindName(name)
        if lt is not None:
            return lt.Index
    return -1


def ensure_hidden_linetype():
    """Cerca il tipo linea Hidden/Nascosto; se assente lo crea."""
    idx = find_linetype_index(["Hidden", "Nascosto", "hidden", "HIDDEN"])
    if idx >= 0:
        return idx
    lt = Rhino.DocObjects.Linetype()
    lt.Name = "Hidden"
    lt.AppendSegment(2.5, True)
    lt.AppendSegment(1.25, False)
    idx = sc.doc.Linetypes.Add(lt)
    return idx


def apply_attributes(rh_obj, layer_idx, obj_color, plot_weight, linetype_idx):
    """Applica attributi grafici all'oggetto."""
    attr = rh_obj.Attributes.Duplicate()

    attr.LayerIndex = layer_idx

    attr.ColorSource = Rhino.DocObjects.ObjectColorSource.ColorFromObject
    attr.ObjectColor = obj_color

    attr.PlotWeightSource = Rhino.DocObjects.ObjectPlotWeightSource.PlotWeightFromObject
    attr.PlotWeight = plot_weight

    attr.LinetypeSource = Rhino.DocObjects.ObjectLinetypeSource.LinetypeFromObject
    if linetype_idx >= 0:
        attr.LinetypeIndex = linetype_idx

    sc.doc.Objects.ModifyAttributes(rh_obj.Id, attr, True)


def main():
    # ------------------------------------------------------------------
    # 1. Verifica selezione attiva; se assente chiedi di selezionare
    # ------------------------------------------------------------------
    sel = list(sc.doc.Objects.GetSelectedObjects(False, False))

    valid_types = (
        Rhino.DocObjects.ObjectType.Curve
        | Rhino.DocObjects.ObjectType.Annotation
    )

    if sel:
        sel = [o for o in sel
               if o is not None
               and (int(o.ObjectType) & int(valid_types)) != 0]

    if not sel:
        go = Rhino.Input.Custom.GetObject()
        go.SetCommandPrompt("Seleziona curve e quote da preparare per grafica")
        go.GeometryFilter = valid_types
        go.SubObjectSelect = False
        go.GroupSelect = True
        go.GetMultiple(1, 0)
        if go.CommandResult() != Rhino.Commands.Result.Success:
            print("Comando annullato.")
            return
        sel = [go.Object(i).Object() for i in range(go.ObjectCount)]

    if not sel:
        print("Nessun oggetto valido selezionato.")
        return

    print("Oggetti selezionati: %d" % len(sel))

    # ------------------------------------------------------------------
    # 2-5. Prepara layer di destinazione
    # ------------------------------------------------------------------
    tracciato_idx = ensure_layer(
        "Tracciato",
        System.Drawing.Color.FromArgb(255, 0, 255)
    )
    crocini_idx = ensure_layer(
        "Crocini",
        System.Drawing.Color.FromArgb(0, 0, 255)
    )
    quote_idx = ensure_layer(
        "Quote",
        System.Drawing.Color.FromArgb(105, 105, 105)
    )

    if tracciato_idx < 0 or crocini_idx < 0 or quote_idx < 0:
        print("Errore nella creazione dei layer di destinazione.")
        return

    # ------------------------------------------------------------------
    # Prepara tipi linea
    # ------------------------------------------------------------------
    cont_idx = find_linetype_index(["Continuous", "Continuo", "continuous"])
    hidden_idx = ensure_hidden_linetype()

    # ------------------------------------------------------------------
    # Colori di destinazione
    # ------------------------------------------------------------------
    magenta = System.Drawing.Color.FromArgb(255, 0, 255)
    nero = System.Drawing.Color.FromArgb(0, 0, 0)
    cyano = System.Drawing.Color.FromArgb(0, 255, 255)

    # ------------------------------------------------------------------
    # Contatori
    # ------------------------------------------------------------------
    cnt = {"Taglio": 0, "Cordone": 0, "Crocini": 0, "Quote": 0, "skip": 0}

    # ------------------------------------------------------------------
    # Ciclo sugli oggetti selezionati
    # ------------------------------------------------------------------
    for obj in sel:
        if obj is None:
            continue

        color = get_effective_color(obj)
        lname = get_layer_name(obj)
        matched = False

        # Caso 2 -- Nero su Taglio -> Magenta, 0.3 mm, Continuo, Tracciato
        if lname == "Taglio" and color_match(color, 0, 0, 0):
            apply_attributes(obj, tracciato_idx, magenta, 0.3, cont_idx)
            cnt["Taglio"] += 1
            matched = True

        # Caso 3 -- Rosso su Cordone -> Magenta, 0.13 mm, Nascosto, Tracciato
        elif lname == "Cordone" and color_match(color, 255, 0, 0):
            apply_attributes(obj, tracciato_idx, magenta, 0.13, hidden_idx)
            cnt["Cordone"] += 1
            matched = True

        # Caso 4 -- Blu su Crocini -> Nero, 0.25 mm, Continuo, Crocini
        elif lname == "Crocini" and color_match(color, 0, 0, 255):
            apply_attributes(obj, crocini_idx, nero, 0.25, cont_idx)
            cnt["Crocini"] += 1
            matched = True

        # Caso 5 -- Grigio su Quote -> Cyano, 0.25 mm, Continuo, Quote
        elif lname == "Quote" and color_match(color, 105, 105, 105):
            apply_attributes(obj, quote_idx, cyano, 0.25, cont_idx)
            cnt["Quote"] += 1
            matched = True

        if not matched:
            cnt["skip"] += 1

    # ------------------------------------------------------------------
    # Riepilogo e ridisegno
    # ------------------------------------------------------------------
    sc.doc.Views.Redraw()

    print("--- Prepara per Grafica: completato ---")
    print("  Taglio  -> Tracciato (Magenta, 0.30mm, Continuo) : %d" % cnt["Taglio"])
    print("  Cordone -> Tracciato (Magenta, 0.13mm, Nascosto) : %d" % cnt["Cordone"])
    print("  Crocini -> Crocini   (Nero,    0.25mm, Continuo) : %d" % cnt["Crocini"])
    print("  Quote   -> Quote     (Cyano,   0.25mm, Continuo) : %d" % cnt["Quote"])
    if cnt["skip"] > 0:
        print("  Non classificati (colore/layer non corrispondente): %d" % cnt["skip"])
    total = cnt["Taglio"] + cnt["Cordone"] + cnt["Crocini"] + cnt["Quote"]
    print("  Totale oggetti modificati: %d / %d" % (total, len(sel)))


if __name__ == "__main__":
    main()
