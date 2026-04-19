# Cartotecnica LLM Knowledge Base

Knowledge base per assistenti AI (Claude, ChatGPT, Gemini, modelli locali) specializzati in cartotecnica parametrica e scripting Rhino.

## Scopo

Questo repository contiene istruzioni, convenzioni e conoscenza strutturata che qualsiasi LLM puo leggere per operare come assistente esperto in:

- **Scripting Rhino 7/8** con IronPython 2.7 e RhinoCommon
- **Progettazione cartotecnica parametrica** (fustellature, cordonature, astucci, scatole)
- **Generazione automatica** di tracciati die-cut da parametri dimensionali

## Come usare con un LLM

All'inizio di una conversazione, fornire al modello l'URL raw del file pertinente:

```
Leggi e segui le istruzioni in questo file:
https://raw.githubusercontent.com/DDR68/Rhino_Packaging_Toolkit/main/docs/llm-knowledge/prompts/rhino-ironpython.md
```

Per modelli con accesso web (Claude, ChatGPT con browsing), basta incollare l'URL.
Per modelli senza accesso web, copiare e incollare il contenuto del file nel prompt.

## Struttura

```
cartotecnica-llm/
  README.md                              # Questo file
  prompts/
    rhino-ironpython.md                  # System prompt per scripting Rhino 7/8
  knowledge/
    cartotecnica-strutturale.md          # Grammatica strutturale: patelle, bime, topologia
    ecma-library.md                      # Formati ECMA completati con formule parametriche
    pipeline-export.md                   # Pipeline esportazione/ricostruzione geometrie
  scripts/
    Esporta_Geometrie_Semplice_V.3.py   # Script export geometrie da Rhino
```

## Contesto

Questo materiale nasce dal lavoro pratico di progettazione cartotecnica con Rhinoceros 7,
sviluppato da un cartotecnico professionista con formazione in scultura (Accademia di Brera).
Le convenzioni e le regole documentate qui sono state validate su tracciati reali e
corrette iterativamente attraverso centinaia di test.

## Licenza

Il contenuto di questo repository e liberamente utilizzabile per scopi educativi e professionali.
