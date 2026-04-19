# Pipeline Export / Ricostruzione Geometrie

Documentazione del flusso di lavoro per esportare geometrie da Rhino
e ricostruirle come script parametrici.

## Panoramica

```
Tracciato Rhino (.3dm)
    |
    v
Esporta_Geometrie_Semplice_V.3.py  -->  geometrie_export_v3.txt
    |
    v
Analisi LLM (Claude / altro)
    |
    v
Script parametrico IronPython  -->  Tracciato generato (.3dm)
    |
    v
Confronto visivo + correzioni
```

## Script di esportazione (V.3)

### File: Esporta_Geometrie_Semplice_V.3.py

Esporta tutte le curve selezionate in formato TXT tab-separated.

### Funzionalita
- **Esplosione PolyCurve**: curve composite scomposte in segmenti elementari
- **Rilevamento tipo**: isinstance() + TryGet per classificazione affidabile
- **Archi con piano corretto**: Normal.Z < 0 = angoli negati (sweep CW)
- **NURBS razionali**: pesi CP inclusi nel formato x,y,w
- **Punti campionati**: per curve complesse (grado > 2 o molti CP)

### Formato output

```
# file.3dm | bbox: WxH | obj: N | segm: M | exploded: E | unita: Millimeters
# Tipo: T=Taglio  C=Cordone  M=MezzoTaglio  F=Foratore
# ID  Tipo  Geom  X1  Y1  X2  Y2  R  CX  CY  AngS  AngE  Len  [extra]
```

| Colonna | Descrizione |
|---------|-------------|
| ID | Indice sequenziale del segmento |
| Tipo | T/C/M/F (da layer e colore) |
| Geom | Line / Arc / Nurbs / Poly |
| X1,Y1 | Punto di inizio |
| X2,Y2 | Punto di fine |
| R | Raggio (solo archi) |
| CX,CY | Centro arco |
| AngS,AngE | Angoli inizio/fine in gradi (negativi = CW) |
| Len | Lunghezza curva |

### Colonne extra per NURBS
| Colonna | Descrizione |
|---------|-------------|
| Deg | Grado della curva |
| Pts | Numero control points |
| CP | Control points: x,y oppure x,y,w per razionali |
| Sampled | Punti campionati (solo se grado > 2 o CP > 4) |

## Classificazione tipo curva

Priorita di classificazione:
1. Nome layer (taglio, cordone, mezzotaglio, foratore)
2. Colore effettivo (nero=T, rosso=C, verde=M, blu=F)

## Bug noti e soluzioni (storico)

### V.1 - Problemi risolti in V.2
- PolyCurve non esplose (curva composita letta come singola NURBS)
- Pesi NURBS ignorati (curve razionali trattate come non-razionali)
- Centro arco non esportato

### V.2 - Problemi risolti in V.3
- **Angoli arco con piano invertito**: arc.StartAngle/EndAngle sono sempre
  positivi nel piano locale. Se arc.Plane.Normal.Z < 0, gli angoli vanno
  negati per riflettere il sweep CW nel piano globale XY.
  Sintomo: archi semicircolari specchiati nella ricostruzione.

## Ricostruzione parametrica

### Processo di analisi del TXT esportato

1. **Identificare i pannelli** dalle cordonature verticali (tipo C, Geom Line, stessa Y)
2. **Calcolare L, P, A, S** dalle distanze tra cordonature
3. **Classificare le patelle** per posizione e numero di bime
4. **Identificare i raccordi** (archi, nurbs) e le loro funzioni
5. **Mappare ogni curva** a una formula parametrica

### Costruzione NURBS razionali in IronPython 2.7

```python
from Rhino.Geometry import NurbsCurve, Point4d

# MAI usare ControlPoint() - non supportato in SetPoint
crv = NurbsCurve(3, True, 3, 3)  # dim=3, rational=True, order=3, n_pts=3
crv.Knots[0] = 0.0
crv.Knots[1] = 1.0
# Coordinate omogenee: Point4d(x*w, y*w, z*w, w)
crv.Points.SetPoint(0, Point4d(x0, y0, 0, 1.0))
crv.Points.SetPoint(1, Point4d(xm*w, ym*w, 0, w))  # w = cos(30) = 0.866
crv.Points.SetPoint(2, Point4d(x1, y1, 0, 1.0))
```

### Costruzione archi

```python
from Rhino.Geometry import Arc, Circle, Plane, Interval
import math

# Semicerchio verso l'alto (CCW)
add_arc(cx, cy, r, 0, 180)

# Semicerchio verso il basso (CW)
add_arc(cx, cy, r, -180, 0)

# Quarto di cerchio (primo quadrante)
add_arc(cx, cy, r, 0, 90)
```

## Checklist verifica

Dopo la generazione di uno script parametrico:

- [ ] Contare le curve: devono corrispondere all'export
- [ ] Verificare raccordi (zoom sui punti di giunzione)
- [ ] Controllare direzione archi (non specchiati)
- [ ] Testare con dimensioni diverse (almeno L, P, A variati del 50%)
- [ ] Esportare il risultato con V.3 e confrontare i due TXT
- [ ] Verificare che le cordonature non si sovrappongano ai tagli
