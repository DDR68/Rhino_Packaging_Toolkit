# Libreria ECMA - Formati Parametrici Completati

Raccolta dei formati cartotecnici con formule parametriche verificate.
Ogni formato e stato sviluppato, testato e corretto su tracciati reali in Rhino 7.

## Convenzioni comuni

### Parametri di input
- **L** = Larghezza (dimensione frontale)
- **P** = Profondita (dimensione laterale)
- **A** = Altezza (dimensione verticale)
- **S** = Spessore cartone

### Pannelli (da sinistra a destra nel tracciato piano)
- P1 (fronte): larghezza = L - S
- P2 (lato): larghezza = P
- P3 (retro): larghezza = L
- P4 (lato): larghezza = P - S

### Aletta incollatura
- Posizione: bordo sinistro P1
- Larghezza: G = 18mm (costante)
- Angoli raccordo: tp = 3mm

### Layer e colori
- Taglio: layer "Taglio", nero (0,0,0)
- Cordone: layer "Cordone", rosso (255,0,0)

---

## ECMA A20.20.01.01 - Astuccio Tuck-End Standard

Astuccio con linguette di chiusura (tuck) sopra e sotto.
Tuck e alette di chiusura sugli stessi lati.

### Geometria tuck
- Profondita tuck: tuck_h = P - D (D=1mm distanza bima)
- Arrotondamento: tuck_r = G = 18mm
- Rientro punta: tip_in = 8mm
- Curva: NURBS razionale grado 2, peso CP centrale = cos(30) = 0.866
- Estensione totale: tuck_tot = tuck_h + tuck_r

### Bime tuck
- Linguetta orizzontale: bima_h = 5.5mm
- Estensione verticale: bima_v = 2.0mm (1.5mm corpo + 0.5mm raccordo)
- Raccordo: nurbs grado 2 non-razionale, 3 CP
- Posizione Y: allineate a y_tuck_base (17.5mm dal bordo pannello)

### Alette chiusura
- Altezza: h_al = P - 2*tp - S
- Rastrematura: 2 segmenti (tp x tp) + (tp x tp2v)
- Raccordo lato tuck: arco R=1.5mm semicircolare
- Raccordo lato taglio: nurbs grado 2 oppure arco R=1.0mm

### Archi di connessione
- R=1.5: semicerchio tra aletta e bordo tuck (angoli 0-180 o -180-0)
- R=1.0: quarto cerchio tra taglio e bordo esterno aletta (angoli 0-90)
- Convenzione: semicerchio verso l'alto = 0 a 180, verso il basso = -180 a 0

---

## Variante Astuccio (Tuck-End con bime distanziate)

Come ECMA A20.20.01.01 ma con bime distanziate D=1mm dai tagli.
Tuck P1 in alto, Tuck P3 in basso.

### Differenze dal formato standard
- Bime spostate di D=1mm rispetto al bordo taglio
- Aletta P4 alto: bordo esterno arretrato 2mm + 4mm angolo
- Arco incollatura: 80.5 gradi (non 90)
- Cordonature: terminano a Rs=1mm dal raccordo adiacente

### Coordinate Y (con G=18, P=30, A=97, S=0.5)
```
y_lo = G + tuck_h + S = 47.5        (piega inferiore)
y_hi = y_lo + A = 144.5             (piega superiore)
y_tuck_base_lo = y_lo - tuck_h - 2S = 17.5
y_tuck_tip_lo = 0.0
y_tuck_base_hi = y_hi + tuck_h + 2S = 174.5
y_tuck_tip_hi = 192.0
y_flap = y_hi + h_al = 168.0 (alto) / y_lo - h_al = 24.0 (basso)
```

---

## ECMA A1 - Reverse Tuck

Astuccio con tuck superiore e inferiore su lati opposti.
Tuck superiore su P3, tuck inferiore su P1 (o viceversa).

### Differenza chiave
- I tuck non sono sullo stesso pannello
- Le alette di chiusura si alternano

---

## FEFCO 0421 - Slide Insert (Cassetto)

Scatola con cassetto scorrevole interno.

### Struttura
- Involucro esterno (sleeve): 4 pannelli
- Cassetto interno (tray): fondo + 4 pareti
- Il cassetto scorre dentro l'involucro

---

## Scatola Esagonale con Manico

Prisma a base esagonale con manico fustellato.

### Geometria base
- 6 pannelli laterali con angolo 120 gradi
- Compensazione angolare per piegatura
- Manico ritagliato nel pannello superiore

---

## Dodecaedro con Snap-Fit

12 pentagoni regolari con incastro meccanico.

### Sfide specifiche
- Angolo diedrale: 116.57 gradi
- 3-4 bime per patella (giunzione non ortogonale)
- Snap-fit: linguette con sottosquadro per blocco meccanico
- Compensazione spessore su angoli non retti

---

## Note per futuri formati

Quando si aggiunge un nuovo formato:
1. Documentare tutti i parametri derivati
2. Specificare tipo di raccordi (arco/nurbs, razionale/non)
3. Indicare numero e tipo di bime per ogni patella
4. Verificare con export V.3 e confronto visivo
5. Testare con almeno 3 set di dimensioni diversi
