# Utilities — Strumenti di Lavoro

Script di utilità per il lavoro parametrico.

## Script disponibili

| Script | Funzione |
|--------|----------|
| `PKG_Annotator.py` | Inserimento punti per regole parametriche (il tracciato deve trovarsi in X0,Y0). |
| `PKG_Quota_Assistita.py` | Inserimento assistito delle quote con regole parametriche, lavora come assistente di PKG_Annotator.py, aggiungendo quote parametriche.|
| `Esporta_Geometrie_Parametrico.py` |Esporta la selezione aplicando le regole parametriche. Legge le curve e i punti descrittivi creando un file TXT che puo essere usato con PKG_Esegue_Parametrico.py per la creazione del tracciato con le misure personalizate. Se si crea il TXT con la spunta su Aggiungi prompt in LLM in testa al file, puo essere caricato in una chat AI per generare script in IronPython, testato con Opus 4.6 e succesivi.|
| `PKG_Esegue_Parametrico.py` |Legge il TXT generato da Esporta_Geometrie_Parametrico.py (senza prompt per LLM) e produce il tracciato parametrico. Utile per non passare dal LLM e accedere al proprio archivio personalizato di packaging in TXT. |
