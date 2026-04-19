# Cartotecnica Strutturale

Grammatica strutturale della cartotecnica: elementi, funzioni e relazioni topologiche.

## Elementi fondamentali

### Pannello
Superficie piana che forma una faccia della scatola.
Delimitato da linee di taglio (bordi liberi) e cordonature (pieghe).
Dimensioni definite dai parametri L (Larghezza), P (Profondita), A (Altezza).

### Cordonatura (Cordone)
Linea di piega impressa nel cartone. Permette la piegatura controllata.
- Colore convenzionale: ROSSO (255,0,0)
- Rappresentata come linea retta nel tracciato piano

### Taglio
Linea di separazione del materiale.
- Colore convenzionale: NERO (0,0,0)
- Puo essere retto, curvo, o composto (raccordi nurbs/archi)

### Mezzo Taglio
Incisione parziale dello spessore, non attraversa il cartone.
- Colore convenzionale: VERDE (0,255,0)
- Usato per finestre, linguette a strappo

### Foratore
Linea di perforazione (tratteggiata nella fustella).
- Colore convenzionale: BLU (0,0,255)
- Usato per linee di strappo, aperture facilitata

## Elementi funzionali

### Patella (Aletta di chiusura)
Estensione di un pannello che si piega per chiudere o rinforzare la scatola.
Classificata per funzione:

| Tipo | Descrizione | Esempio |
|------|-------------|---------|
| Tuck (linguetta) | Si inserisce dentro la scatola | Chiusura superiore/inferiore astuccio |
| Aletta incollatura | Si incolla al pannello adiacente | Giunzione laterale |
| Aletta chiusura | Si piega verso l'interno | Chiusura parziale lati |
| Patella strutturale | Connette piu facce | Giunzioni poliedri |

### Bima (Tacca di registro)
Intaglio a forma di linguetta sul bordo di una patella.
Serve per guidare, bloccare o trattenere la patella nella posizione corretta.

**Il numero di bime indica la complessita topologica del nodo:**

| Bime | Funzione | Contesto |
|------|----------|----------|
| 0 | Patella libera, nessun vincolo | Alette incollatura semplici |
| 1 | Inserimento guidato | Tuck base, inserimento in fessura |
| 2 | Aggancio tra due elementi | Alette chiusura astuccio standard |
| 3 | Giunzione multi-faccia | Vertici poliedri (3 facce convergenti) |
| 4 | Giunzione complessa | Nodi ad alta connettivita |

### Raccordo
Curva di transizione tra taglio e cordonatura.
- Arco R=1.0-1.5mm: transizione standard
- Nurbs grado 2: raccordo parabolico (non razionale)
- Nurbs razionale (w=cos30=0.866): arco conico 60 gradi (tuck arrotondati)

### Compensazione spessore (S)
Offset applicato ai pannelli per compensare lo spessore del cartone
quando la scatola e piegata. Tipicamente:
- Pannello 1 (fronte): L - S
- Pannello 2 (lato): P (invariato)
- Pannello 3 (retro): L (invariato)
- Pannello 4 (lato): P - S

## Relazione topologia - geometria

La complessita geometrica di una scatola e determinata dalla sua topologia:

### Prisma rettangolare (astuccio)
- Facce: 4 pannelli + 2 chiusure
- Angoli: tutti 90 gradi
- Vertici: 8, ciascuno condiviso da 3 facce
- Bime: 0-2 per patella
- Esempio: ECMA A20.20.01.01

### Prisma esagonale
- Facce: 6 pannelli + 2 chiusure
- Angoli: 120 gradi
- Vertici: 12, ciascuno condiviso da 3 facce
- Bime: 2 per patella
- Compensazione angolare necessaria

### Dodecaedro
- Facce: 12 pentagoni
- Angolo diedrale: 116.57 gradi
- Vertici: 20, ciascuno condiviso da 3 facce
- Bime: 3-4 per patella (giunzione non ortogonale)
- Richiede snap-fit o incastro meccanico

### Regola generale
```
n_bime = f(n_facce_convergenti, angolo_diedrale, tipo_giunzione)
```
- Angolo 90 gradi: 1-2 bime sufficienti
- Angolo != 90 gradi: bime aggiuntive per compensare torsione
- Piu facce convergenti: piu bime per distribuire il vincolo

## Parametri standard

| Parametro | Simbolo | Descrizione |
|-----------|---------|-------------|
| Larghezza | L | Dimensione frontale |
| Profondita | P | Dimensione laterale |
| Altezza | A | Dimensione verticale |
| Spessore | S | Spessore cartone (tipico: 0.3-0.8mm) |
| Incollatura | G | Larghezza aletta incollatura (tipico: 18mm) |
| Distanza bima | D | Gap bima-taglio (tipico: 1mm) |

## Formati foglio standard (cm)

35x25, 35x50, 50x70, 100x70, 101x71, 102x72, 1200x800, 1400x1000, 1600x1200
