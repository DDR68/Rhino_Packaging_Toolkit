#! python 2
# -*- coding: utf-8 -*-
"""
Script per Rhino 7 (IronPython 2.7.12)
Organizza oggetti selezionati (curve e annotazioni) per colore,
spostandoli sui livelli corrispondenti e correggendo i colori.

v2 — Correzioni applicate secondo Guida_IronPython_Rhino7_Def:
  - FindByFullPath: secondo parametro corretto a -1 (era True = bug critico)
  - Blocco Undo unico per tutta l'operazione batch
  - sc.escape_test() nel loop per permettere ESC su selezioni grandi
  - Rimossi except nudi; errori loggati esplicitamente
  - Layer creati con colore di riferimento assegnato
  - create_layer_if_not_exists restituisce l'indice (non il nome)
"""

import rhinoscriptsyntax as rs
import scriptcontext as sc
import System.Drawing as Drawing
import Rhino


def rgb_to_color(r, g, b):
    """Converte valori RGB in oggetto System.Drawing.Color."""
    return Drawing.Color.FromArgb(r, g, b)


def colors_match(color1, color2, tolerance=5):
    """Confronta due colori con una tolleranza."""
    if color1 is None or color2 is None:
        return False
    return (abs(color1.R - color2.R) <= tolerance and
            abs(color1.G - color2.G) <= tolerance and
            abs(color1.B - color2.B) <= tolerance)


def create_layer_if_not_exists(layer_name, layer_color=None):
    """
    Crea il livello se non esiste e gli assegna il colore di riferimento.
    Restituisce l'indice del layer (>= 0) oppure -1 in caso di errore.
    """
    layer_table = sc.doc.Layers
    layer_index = layer_table.FindByFullPath(layer_name, -1)

    if layer_index < 0:
        new_layer = Rhino.DocObjects.Layer()
        new_layer.Name = layer_name
        if layer_color is not None:
            new_layer.Color = layer_color
        layer_index = layer_table.Add(new_layer)
        if layer_index >= 0:
            print("Livello creato: {} (indice: {})".format(layer_name, layer_index))
        else:
            print("ERRORE: Impossibile creare il livello {}".format(layer_name))
            return -1
    else:
        # Se esiste gia', aggiorna il colore se specificato
        if layer_color is not None:
            layer_obj = layer_table[layer_index]
            if layer_obj.Color.ToArgb() != layer_color.ToArgb():
                layer_obj.Color = layer_color
                layer_obj.CommitChanges()
        print("Livello esistente: {} (indice: {})".format(layer_name, layer_index))

    return layer_index


def get_object_display_color(rhino_obj):
    """
    Restituisce il colore visualizzato dell'oggetto tramite DrawColor.
    Accetta un RhinoObject (non un GUID) per evitare lookup ripetuti.
    """
    if rhino_obj is None:
        return None
    return rhino_obj.Attributes.DrawColor(sc.doc)


def set_object_color(rhino_obj, color):
    """
    Imposta il colore esplicito dell'oggetto (ColorFromObject).
    Accetta un RhinoObject gia' recuperato.
    Restituisce True se riuscito, False altrimenti.
    """
    if rhino_obj is None:
        return False

    rhino_obj.Attributes.ObjectColor = Drawing.Color.FromArgb(color.R, color.G, color.B)
    rhino_obj.Attributes.ColorSource = Rhino.DocObjects.ObjectColorSource.ColorFromObject
    return rhino_obj.CommitChanges()


def select_objects():
    """Seleziona curve e annotazioni con RhinoCommon GetObject."""
    obj_filter = (Rhino.DocObjects.ObjectType.Curve |
                  Rhino.DocObjects.ObjectType.Annotation)

    go = Rhino.Input.Custom.GetObject()
    go.SetCommandPrompt("Seleziona curve, testi e quote da organizzare")
    go.GeometryFilter = obj_filter
    go.GroupSelect = True
    go.SubObjectSelect = False
    go.EnableClearObjectsOnEntry(False)
    go.EnableUnselectObjectsOnExit(False)
    go.DeselectAllBeforePostSelect = False
    go.EnablePreSelect(True, True)

    result = go.GetMultiple(1, 0)

    if result == Rhino.Input.GetResult.Object:
        return [go.Object(i).ObjectId for i in range(go.ObjectCount)]

    return None


def organize_objects_by_color():
    """Funzione principale: organizza gli oggetti selezionati per colore."""

    # --- DEFINIZIONE MAPPING COLORE → LAYER ---

    color_layer_mapping = {
        "Taglio":    rgb_to_color(0, 0, 0),        # Nero
        "Cordone":   rgb_to_color(255, 0, 0),       # Rosso
        "Disegno":   rgb_to_color(0, 255, 0),       # Verde
        "Crocini":   rgb_to_color(0, 0, 255),       # Blu
        "Quote":     rgb_to_color(105, 105, 105),    # Grigio
        "Tracciato": rgb_to_color(255, 0, 255),      # Magenta
    }

    # --- CREAZIONE / VERIFICA LIVELLI ---

    print("=== Creazione/Verifica Livelli ===")
    layer_indices = {}
    for layer_name, layer_color in color_layer_mapping.items():
        idx = create_layer_if_not_exists(layer_name, layer_color)
        if idx < 0:
            print("ERRORE CRITICO: impossibile preparare il layer '{}'. Esco.".format(
                layer_name))
            return
        layer_indices[layer_name] = idx

    # --- INPUT / SELEZIONE ---

    print("\n=== Selezione Oggetti ===")
    object_ids = select_objects()

    if not object_ids:
        print("Nessun oggetto selezionato. Operazione annullata.")
        return

    print("Oggetti selezionati: {}".format(len(object_ids)))

    # --- ELABORAZIONE ---

    moved_objects = {}
    corrected_colors = {}
    for layer_name in color_layer_mapping:
        moved_objects[layer_name] = 0
        corrected_colors[layer_name] = 0
    unmatched_count = 0
    unmatched_colors = []

    rs.EnableRedraw(False)

    try:
        undo_record = sc.doc.BeginUndoRecord(
            "Organizza {} oggetti per colore".format(len(object_ids)))

        print("\n=== Elaborazione Oggetti ===")

        for obj_id in object_ids:
            # Permetti interruzione con ESC
            if sc.escape_test(False):
                print("Operazione interrotta dall'utente (ESC).")
                break

            # Recupera l'oggetto una sola volta (guida: non trattare GUID come oggetto)
            rhino_obj = sc.doc.Objects.Find(obj_id)
            if rhino_obj is None:
                unmatched_count += 1
                continue

            obj_color = get_object_display_color(rhino_obj)
            if obj_color is None:
                unmatched_count += 1
                continue

            # Cerca corrispondenza colore → layer
            matched = False
            for layer_name, target_color in color_layer_mapping.items():
                if colors_match(obj_color, target_color):
                    matched = True
                    new_layer_index = layer_indices[layer_name]
                    old_layer_index = rhino_obj.Attributes.LayerIndex

                    # Sposta sul layer se necessario
                    if old_layer_index != new_layer_index:
                        rhino_obj.Attributes.LayerIndex = new_layer_index
                        rhino_obj.CommitChanges()
                        moved_objects[layer_name] += 1

                    # Correggi colore se non esattamente quello di riferimento
                    # oppure se la sorgente non e' ColorFromObject (es. ByLayer)
                    color_source = rhino_obj.Attributes.ColorSource
                    is_by_object = (color_source ==
                        Rhino.DocObjects.ObjectColorSource.ColorFromObject)
                    is_exact_rgb = (obj_color.R == target_color.R and
                                    obj_color.G == target_color.G and
                                    obj_color.B == target_color.B)

                    if not is_exact_rgb or not is_by_object:
                        if set_object_color(rhino_obj, target_color):
                            corrected_colors[layer_name] += 1
                            if not is_by_object:
                                print("  Colore dichiarato esplicito: "
                                      "RGB({},{},{}) [era ByLayer]".format(
                                    target_color.R, target_color.G, target_color.B))
                            else:
                                print("  Colore corretto: "
                                      "RGB({},{},{}) -> RGB({},{},{})".format(
                                    obj_color.R, obj_color.G, obj_color.B,
                                    target_color.R, target_color.G, target_color.B))

                    break

            if not matched:
                unmatched_count += 1
                color_str = "R={}, G={}, B={}".format(
                    obj_color.R, obj_color.G, obj_color.B)
                if color_str not in unmatched_colors:
                    unmatched_colors.append(color_str)

        # Chiudi il blocco Undo
        if undo_record > 0:
            sc.doc.EndUndoRecord(undo_record)

    finally:
        rs.EnableRedraw(True)

    # --- REPORT ---

    print("\n=== Risultati ===")
    total_moved = 0
    total_corrected = 0

    for layer_name in color_layer_mapping:
        m = moved_objects[layer_name]
        c = corrected_colors[layer_name]
        if m > 0 or c > 0:
            msg = "Livello '{}'".format(layer_name)
            if m > 0:
                msg += ": {} oggetti spostati".format(m)
            if c > 0:
                msg += ", {} colori corretti".format(c)
            print(msg)
            total_moved += m
            total_corrected += c

    if unmatched_count > 0:
        print("\nOggetti non corrispondenti: {}".format(unmatched_count))
        print("Colori trovati ma non riconosciuti:")
        for color in unmatched_colors:
            print("  - {}".format(color))

    print("\nTotale oggetti spostati: {}".format(total_moved))
    print("Totale colori corretti: {}".format(total_corrected))
    print("Operazione completata con successo!")

    # --- REDRAW ---

    sc.doc.Views.Redraw()


# Esegui lo script
if __name__ == "__main__":
    organize_objects_by_color()
