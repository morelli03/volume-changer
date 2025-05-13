# Automatic Volume Manager

Un'utility Python per Windows che gestisce automaticamente il volume di un'applicazione target in base all'attività audio di un'applicazione trigger. Utilizza una TUI (Text User Interface) basata su Rich per visualizzare lo stato e i log in tempo reale.

![Screenshot dell'interfaccia TUI](images/icon.png)
![Screenshot dell'interfaccia TUI](images/screenshot.png)

## Caratteristiche Principali

*   **Monitoraggio App Trigger:** Rileva quando un'applicazione specificata (es. Discord, Teams) sta emettendo audio sopra una soglia definita.
*   **Controllo App Target:** Abbassa il volume di un'altra applicazione (es. Spotify, un gioco) quando l'app trigger è attiva.
*   **Ripristino Automatico:** Ripristina il volume originale dell'app target quando l'app trigger diventa silenziosa (dopo un periodo di debounce).
*   **Riduzione Volume Configurabile:**
    *   **Fissa:** Abbassa il volume di una percentuale fissa.
    *   **Dinamica:** Abbassa il volume in base a regole definite (es. più alto è il volume originale, maggiore è la riduzione).
*   **Fading del Volume:** Transizioni graduali del volume (fade-in/fade-out) per un'esperienza più fluida.
*   **TUI:** Interfaccia utente nel terminale che mostra:
    *   Impostazioni correnti.
    *   Stato delle applicazioni trigger e target (trovate, attive).
    *   Volume corrente e originale dell'app target.
    *   Log degli eventi in tempo reale.
*   **Configurazione Flessibile:** Tutte le impostazioni sono gestite tramite un file `config.ini`.
*   **Ripristino all'Uscita:** Tenta di ripristinare il volume originale dell'app target quando lo script viene chiuso (Ctrl+C).
*   **Supporto per Eseguibile:** Può essere compilato in un file `.exe` per un facile utilizzo senza installare Python.

## Come Funziona

Lo script esegue il polling delle sessioni audio attive su Windows a intervalli regolari:
1.  Identifica le sessioni audio per l'applicazione "trigger" e "target" specificate nel `config.ini`.
2.  Misura il livello di picco dell'audio dell'applicazione trigger.
3.  Se il picco supera la `TriggerVolumeThreshold`:
    *   Se l'applicazione target non è già stata "ridotta", ne memorizza il volume attuale come "originale".
    *   Calcola il nuovo volume target ridotto (fisso o dinamico).
    *   Abbassa gradualmente (fade-out) il volume dell'applicazione target al livello ridotto.
    *   Mantiene il volume ridotto finché l'applicazione trigger è attiva.
4.  Se l'applicazione trigger scende sotto la soglia:
    *   Attende per un `DebounceTimeSeconds` per evitare fluttuazioni rapide.
    *   Se l'applicazione trigger rimane silenziosa, ripristina gradualmente (fade-in) il volume dell'applicazione target al suo livello "originale".
5.  Se il volume dell'app target viene modificato manualmente mentre è in stato "ridotto", lo script lo riporterà al livello ridotto previsto.
6.  All'uscita (Ctrl+C), lo script tenta di ripristinare il volume dell'app target al suo valore originale se era stato ridotto.

## Requisiti

### Per eseguire lo script Python:
*   Windows (testato su Windows 11, python 3.10.6)
*   Python 3.7+
*   Pip (Python package installer)
*   Le librerie Python elencate in `requirements.txt`:
    *   `pycaw`: Per il controllo del volume audio per-applicazione.
    *   `psutil`: Per ottenere i nomi dei processi dagli ID.
    *   `rich`: Per la TUI avanzata.
    *   `comtypes`: Dipendenza di `pycaw`.

## Installazione e Utilizzo

### Opzione 1: Utilizzare lo script Python (Consigliato per Sviluppatori/Utenti Avanzati)

1.  **Clona il repository o scarica i file:**
    ```bash
    git clone https://github.com/morelli03/volume-changer.git
    cd volume-changer
    ```
    Oppure scarica lo ZIP ed estrailo.

3.  **Installa le dipendenze:**
    ```bash
    pip install -r requirements.txt
    ```

4.  **Configura `config.ini`:**
    *   Apri `config.ini` con un editor di testo e modifica i valori secondo le tue esigenze (vedi la sezione "Configurazione" sotto). **Assicurati che i nomi delle applicazioni (`TriggerAppName`, `TargetAppName`) corrispondano esattamente ai nomi dei processi eseguibili (es. `Discord.exe`, `Spotify.exe`).**

5.  **Esegui lo script:**
    ```bash
    python volume_manager_1.1.py
    ```

6.  **Per uscire:** Premi `Ctrl+C` nella finestra del terminale dove lo script è in esecuzione.

### Opzione 2: Utilizzare il file `.exe` precompilato

1.  **Scarica il file `volume_manager.exe`** dalla sezione [**Releases**](https://github.com/TUO_USERNAME/NOME_REPOSITORY/releases) di questo repository.
2.  **Scarica o crea il file `config.ini`**. Assicurati che sia nella stessa cartella del file `.exe`.
3.  **Modifica `config.ini`** come descritto nella sezione "Configurazione".
4.  **Esegui `volume_manager.exe`**. Si aprirà una finestra del terminale che mostrerà la TUI.
5.  **Per uscire:** Premi `Ctrl+C` nella finestra del terminale o chiudi la finestra.

    **Nota:** Alcuni software antivirus potrebbero segnalare il file `.exe` come potenziale minaccia (falso positivo) perché non è firmato digitalmente. Se compilato da una fonte fidata (come te stesso o questo repository), dovrebbe essere sicuro.

## Configurazione (`config.ini`)

Il file `config.ini` permette di personalizzare il comportamento dello script. Assicurati che i nomi delle applicazioni siano i nomi dei file eseguibili (es. `firefox.exe`, non "Firefox").

```ini
[General]
; Nome dell'eseguibile dell'applicazione che, quando attiva, farà abbassare il volume dell'app target
; Esempi: discord.exe, msteams.exe, zoom.exe
TriggerAppName = discord.exe

; Nome dell'eseguibile dell'applicazione il cui volume verrà controllato
; Esempi: spotify.exe, vlc.exe, chrome.exe (se vuoi abbassare il browser per i giochi)
TargetAppName = spotify.exe

; Intervallo in secondi tra i controlli del volume
PollingIntervalSeconds = 0.5

; Tempo in secondi che l'app trigger deve rimanere silenziosa prima di ripristinare il volume dell'app target
DebounceTimeSeconds = 2.0

[VolumeControl]
; Soglia di volume (da 0.0 a 1.0) dell'app trigger per considerarla "attiva"
; 0.1 = 10% di picco audio
TriggerVolumeThreshold = 0.05

; Se True, usa le regole dinamiche. Se False, usa FixedReductionAmountPoints.
UseDynamicReduction = True

; Valore fisso (da 0.0 a 1.0) di cui ridurre il volume dell'app target
; Es: 0.3 = riduce il volume di 30 punti percentuali (es. da 70% a 40%)
; Usato solo se UseDynamicReduction = False
FixedReductionAmountPoints = 0.30

; Volume minimo (da 0.0 a 1.0) a cui l'app target può essere ridotta
; Es: 0.05 = il volume non scenderà mai sotto il 5%
MinimumVolumeAfterReduction = 0.05

; Tolleranza per confronti tra valori di volume float (evita aggiustamenti per differenze minime)
VolumeFloatTolerance = 0.001

[DynamicReductionRules]
; Regole per la riduzione dinamica. Formato: "soglia_originale:punti_riduzione, altra_soglia:altri_punti"
; Le soglie sono volumi originali dell'app target (0.0-1.0). I punti sono quanto ridurre (0.0-1.0).
; Lo script applicherà la prima regola (dalla più alta alla più bassa) la cui soglia è soddisfatta.
; Esempio: se il volume originale è 80% (0.8), userà la regola 0.7:0.5 riducendo di 50 punti.
; Se il volume originale è 60% (0.6), userà la regola 0.5:0.35 riducendo di 35 punti.
; Se il volume originale è 20% (0.2), nessuna regola si applica e la riduzione è 0 (o la FixedReduction se Dynamic non si applica)
; Lasciare vuoto per non usare regole specifiche e fare affidamento sulla FixedReduction se UseDynamicReduction è True ma non ci sono regole applicabili.
Rules = 0.7:0.5, 0.5:0.35, 0.3:0.2

[Fading]
; Durata in secondi per l'effetto di fade-out (abbassamento volume)
FadeOutDurationSeconds = 0.3
; Numero di step per il fade-out
FadeOutSteps = 10

; Durata in secondi per l'effetto di fade-in (ripristino volume)
FadeInDurationSeconds = 0.5
; Numero di step per il fade-in
FadeInSteps = 15

; Durata in secondi per l'effetto di fade-in quando si esce dallo script (Ctrl+C)
; Se <=0, usa metà della FadeInDurationSeconds
ExitFadeDurationSeconds = 0.0 ; Usare 0.0 per il fallback automatico, oppure un valore tipo 0.1
; Numero di step per il fade-in all'uscita
; Se <=0, usa FadeInSteps
ExitFadeSteps = 0 ; Usare 0 per il fallback automatico, oppure un valore tipo 5

[TUI]
; Quante volte al secondo aggiornare l'interfaccia utente (TUI)
RefreshRate = 4
; Numero massimo di messaggi da conservare e visualizzare nel log della TUI
MaxLogMessages = 100
```

## Compilare in un `.exe` (Opzionale)

Se vuoi compilare lo script in un file `.exe` autonomo, puoi usare [PyInstaller](https://pyinstaller.org/):

1.  **Installa PyInstaller** (se non l'hai già fatto, preferibilmente nel tuo ambiente virtuale):
    ```bash
    pip install pyinstaller
    ```

2.  **Esegui PyInstaller dalla directory principale del progetto:**
    ```bash
    pyinstaller --onefile --windowed --name VolumeManager --icon=your_icon.ico volume_manager_1.1.py
    ```
    *   `--onefile`: Crea un singolo file eseguibile.
    *   `--windowed`: Su Windows, previene l'apertura di una console aggiuntiva se la tua app è GUI (per questo script che usa Rich TUI, potresti preferire omettere `--windowed` o usare `--console` che è il default, per assicurarti che la TUI sia visibile). *Per questo script specifico, è meglio NON usare `--windowed` perché la TUI è basata su console.*
    *   `--name VolumeManager`: Specifica il nome del file `.exe` risultante.
    *   `--icon=your_icon.ico`: (Opzionale) Aggiunge un'icona al tuo `.exe`.
    *   `volume_manager_1.1.py`: Il tuo script principale.

    Un comando più semplice potrebbe essere:
    ```bash
    pyinstaller --onefile --name VolumeManager volume_manager_1.1.py
    ```

3.  Il file `.exe` si troverà nella cartella `dist` creata da PyInstaller.
4.  **Ricorda:** Il file `config.ini` deve essere posizionato nella stessa directory dell'`.exe` per essere letto correttamente.

## Troubleshooting

*   **Applicazione Trigger/Target non trovata:**
    *   Assicurati che il nome dell'applicazione in `config.ini` (`TriggerAppName`, `TargetAppName`) corrisponda **esattamente** al nome del processo eseguibile (es. `spotify.exe`, non "Spotify Music"). Puoi trovare i nomi dei processi nel Task Manager (scheda Dettagli).
    *   Assicurati che le applicazioni siano in esecuzione e stiano producendo/ricevendo audio.
*   **Il volume non cambia:**
    *   Verifica `TriggerVolumeThreshold`. Se è troppo alto, l'app trigger potrebbe non essere mai considerata "attiva". Se troppo basso, potrebbe essere sempre attiva.
    *   Controlla i log nella TUI per messaggi di errore o informazioni sullo stato.
*   **Errore "File 'config.ini' non trovato":**
    *   Assicurati che `config.ini` esista e sia nella stessa directory dello script Python o del file `.exe`.
*   **Permessi:** In rari casi, potrebbero essere necessari permessi di amministratore se le applicazioni target sono eseguite come amministratore, ma generalmente non è richiesto.

## Contribuire
I contributi sono benvenuti! Sentiti libero di aprire una issue per segnalare bug o suggerire miglioramenti, o un pull request con le tue modifiche.

## Licenza
Questo progetto è rilasciato sotto la Licenza MIT. Vedi il file `LICENSE` per maggiori dettagli (o aggiungi qui il testo della licenza MIT).

---
*(Aggiungi un file LICENSE con la licenza MIT se lo desideri)*
