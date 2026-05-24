# Prompt per la generazione dello script parametrico

Questo prompt viene anteposto (opzionalmente) ai file TXT esportati da
`Esporta_Geometrie_Parametrico_V.5.py`. Rende il file **autoportante**: chi lo
riceve — tipicamente un LLM — ha davanti sia le istruzioni sia i dati
geometrici per generare lo script IronPython parametrico.

Lo script lo include in testa al TXT quando l'utente spunta la relativa
casella nel dialogo di export. Il testo è anche mantenuto come costante nella
funzione `_llm_prompt_header` dello script; questo file Markdown ne è la
versione di riferimento, modificabile senza toccare il codice.

---

## Testo del prompt

```text
=== ISTRUZIONI PER LA GENERAZIONE DELLO SCRIPT PARAMETRICO ===

Scrivi professionalmente uno script per Rhino 7 e 8 (IronPython 2.7,
RhinoCommon, prima riga "#! python 2") che generi il packaging descritto
piu' sotto in modo PARAMETRICO, mantenendo l'unita di misura in mm.

Specifiche di stile e convenzioni del toolkit (apri se hai accesso web):
- https://raw.githubusercontent.com/DDR68/Rhino_Packaging_Toolkit/refs/heads/main/docs/llm-knowledge/prompts/ironpython-examples.md
- https://raw.githubusercontent.com/DDR68/Rhino_Packaging_Toolkit/refs/heads/main/docs/llm-knowledge/prompts/rhino-ironpython.md
Se NON puoi accedere ai link, segui comunque queste regole minime:
solo RhinoCommon e scriptcontext (no rhinoscriptsyntax), niente f-string,
stringhe in formato %, header UTF-8, selezione via Rhino.Input.Custom.

COME LEGGERE I DATI CHE SEGUONO
- Ogni riga e' un oggetto geometrico, colonne separate da TAB.
- Le variabili packaging (es. L, P, A, S, C, T, E) hanno valori definiti
  nel disegno; le formule nel blocco UserText le combinano.
- Il blocco UserText (ultima colonna) contiene le coppie chiave=valore
  che definiscono il RAPPORTO PARAMETRICO di ogni geometria:
    Linea   -> P1_param, P2_param  (estremi come formule)
    Cerchio -> Centro_param, Raggio
    Arco    -> P1_param, P2_param, Punto_medio (tre punti), Raggio
    Raccordo conico -> P1_param, P2_param, CtrlProp_u, CtrlProp_v, CtrlPeso_w
    Curva libera    -> CtrlPoints (x,y,w | ...), Nodi, Grado
- Le coordinate X1,Y1,X2,Y2 sono i valori NUMERICI attuali (per riferimento);
  la forma parametrica sta nelle formule del blocco UserText.

COSA DEVI PRODURRE
Uno script che definisca le variabili in testa (cosi' che modificandole il
disegno si riscali), costruisca tutte le geometrie dalle loro formule, e le
disegni nei layer corretti (Taglio, Cordone, MezzoTaglio, Foratore).

AUTO-VERIFICA (obbligatoria)
Al termine, controlla lo script confrontando la geometria che produce con i
dati qui sotto: per ogni punto, verifica che la formula valutata coi valori
delle variabili ridia le coordinate numeriche indicate; per archi e raccordi
verifica estremi, raggio e lato. Segnala e CORREGGI ogni inesattezza prima di
restituire la versione finale.

=== GEOMETRIE E RAPPORTI PARAMETRICI DEL PACKAGING ===
```

---

## Legenda delle chiavi UserText

Riferimento rapido alle chiavi che definiscono ogni geometria nel TXT.

### Comuni
- `Comando` — comando Rhino di riferimento (`_Line`, `_Circle`, `_Arc`, `_InterpCrv`)
- `Tipo_Originale` — tipo geometrico (`Line`, `Circle`, `Arc`, `Nurbs`)
- `Status` — `associato` (tutto parametrico) o `parziale` (qualche estremo non parametrico)
- `P1_id`, `P2_id` — `pair_id` dei punti parametrici agli estremi

### Linea
- `P1_param`, `P2_param` — estremi come formule `(expr_x, expr_y)`
- `Lunghezza` — lunghezza in mm (riferimento)

### Cerchio
- `Centro_param` — centro come formula
- `Raggio`, `Circonferenza` — in mm

### Arco
- `P1_param`, `P2_param` — estremi parametrici
- `Punto_medio` — punto a metà arco, coordinate assolute `x,y` (ricostruzione canonica a tre punti)
- `Centro_geom` — centro assoluto `x,y` (fallback)
- `Raggio`, `Verso` (CW/CCW), `AngStart_deg`, `AngEnd_deg` — angoli con segno (CW negativo)

### Raccordo conico (NURBS grado 2, 3 CP)
- `P1_param`, `P2_param` — estremi parametrici
- `CtrlProp_u`, `CtrlProp_v` — posizione del punto di controllo come frazione del rettangolo dei due estremi (adimensionale, si riscala)
- `CtrlPeso_w` — peso del punto di controllo (w=1 parabola, w≠1 conica)
- `CtrlOff_x`, `CtrlOff_y` — offset assoluto del controllo, presenti solo nei casi degeneri (estremi allineati su un asse, `CtrlProp_*` = `degenere`)

### Curva libera (NURBS altro grado)
- `CtrlPoints` — punti di controllo `x,y,w` separati da `|`
- `Nodi` — vettore dei nodi, valori separati da `|`
- `Grado`, `NumPunti`

---

## Convenzioni geometriche

- Ricostruzione **pienamente parametrica** (si riscala cambiando L, P, A, S):
  linee, cerchi, raccordi conici quadratici.
- Ricostruzione **esatta ma fissa** (alle coordinate assolute salvate):
  archi con centro non annotato, NURBS di grado superiore al secondo.
- Angoli archi: convenzione con segno, CW negativo.
- Separatore `|` per liste interne (CtrlPoints, Nodi): scelto perché
  sopravvive alla sanitizzazione del formato TXT (che converte `;` in `,`).
