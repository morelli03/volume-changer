import time
import os
import configparser
from ctypes import cast, POINTER
from comtypes import CLSCTX_ALL, COMError
from pycaw.pycaw import AudioUtilities, IAudioEndpointVolume, ISimpleAudioVolume, IAudioMeterInformation
import psutil
import math
from collections import deque

from rich.console import Console
from rich.layout import Layout
from rich.live import Live
from rich.panel import Panel
from rich.table import Table
from rich.text import Text
from rich.align import Align
# import rich.box # Only if you use specific box styles like rich.box.ROUNDED


# --- GLOBAL CONFIGURATION OBJECT ---
CONFIG = {}
LOG_MESSAGES = deque(maxlen=100) # Default, will be updated from config

# --- CONFIGURATION LOADING ---
def load_config():
    global CONFIG, LOG_MESSAGES
    parser = configparser.ConfigParser(inline_comment_prefixes=';') # Allow ; for comments
    
    if not os.path.exists("config.ini"):
        print("ERRORE: File 'config.ini' non trovato. Assicurati che sia nella stessa directory dello script.")
        print("Puoi copiare il contenuto d'esempio fornito e salvarlo come 'config.ini'.")
        exit(1)
        
    try:
        parser.read("config.ini")

        CONFIG['TriggerAppName'] = parser.get('General', 'TriggerAppName')
        CONFIG['TargetAppName'] = parser.get('General', 'TargetAppName')
        CONFIG['PollingIntervalSeconds'] = parser.getfloat('General', 'PollingIntervalSeconds')
        CONFIG['DebounceTimeSeconds'] = parser.getfloat('General', 'DebounceTimeSeconds')

        CONFIG['TriggerVolumeThreshold'] = parser.getfloat('VolumeControl', 'TriggerVolumeThreshold')
        CONFIG['UseDynamicReduction'] = parser.getboolean('VolumeControl', 'UseDynamicReduction')
        CONFIG['FixedReductionAmountPoints'] = parser.getfloat('VolumeControl', 'FixedReductionAmountPoints')
        CONFIG['MinimumVolumeAfterReduction'] = parser.getfloat('VolumeControl', 'MinimumVolumeAfterReduction')
        CONFIG['VolumeFloatTolerance'] = parser.getfloat('VolumeControl', 'VolumeFloatTolerance')

        rules_str = parser.get('DynamicReductionRules', 'Rules')
        parsed_rules = []
        if rules_str:
            for rule_pair in rules_str.split(','):
                parts = rule_pair.strip().split(':')
                if len(parts) == 2:
                    try:
                        threshold = float(parts[0].strip())
                        reduction = float(parts[1].strip())
                        parsed_rules.append((threshold, reduction))
                    except ValueError:
                        raise ValueError(f"Formato regola non valido in DynamicReductionRules: '{rule_pair.strip()}'")
        CONFIG['DynamicReductionRulesList'] = sorted(parsed_rules, key=lambda x: x[0], reverse=True)


        CONFIG['FadeOutDurationSeconds'] = parser.getfloat('Fading', 'FadeOutDurationSeconds')
        CONFIG['FadeOutSteps'] = parser.getint('Fading', 'FadeOutSteps')
        CONFIG['FadeInDurationSeconds'] = parser.getfloat('Fading', 'FadeInDurationSeconds')
        CONFIG['FadeInSteps'] = parser.getint('Fading', 'FadeInSteps')
        
        exit_fade_duration = parser.getfloat('Fading', 'ExitFadeDurationSeconds', fallback=0.0)
        exit_fade_steps = parser.getint('Fading', 'ExitFadeSteps', fallback=0)

        if exit_fade_duration <= 0:
            CONFIG['ExitFadeDurationSeconds'] = max(0.1, CONFIG['FadeInDurationSeconds'] / 2)
        else:
            CONFIG['ExitFadeDurationSeconds'] = exit_fade_duration

        if exit_fade_steps <= 0:
            CONFIG['ExitFadeSteps'] = CONFIG['FadeInSteps']
        else:
            CONFIG['ExitFadeSteps'] = exit_fade_steps

        CONFIG['TuiRefreshRate'] = parser.getint('TUI', 'RefreshRate', fallback=4)
        CONFIG['TuiMaxLogMessages'] = parser.getint('TUI', 'MaxLogMessages', fallback=100)
        LOG_MESSAGES = deque(maxlen=CONFIG['TuiMaxLogMessages'])

    except (configparser.NoSectionError, configparser.NoOptionError, ValueError) as e:
        print(f"ERRORE nel file 'config.ini': {e}")
        exit(1)
    except Exception as e:
        print(f"ERRORE IMPREVISTO durante il caricamento di 'config.ini': {e}")
        exit(1)

def add_log_message(message, level="INFO"):
    timestamp = time.strftime('%H:%M:%S')
    color_map = {
        "INFO": "cyan",
        "WARN": "yellow",
        "ERROR": "red",
        "SUCCESS": "green",
        "ACTION": "magenta"
    }
    color = color_map.get(level, "white")
    LOG_MESSAGES.append(Text.assemble((f"[{timestamp}] ", "dim white"), (f"[{level}] ", color), str(message)))


def calculate_dynamic_reduction_amount(original_volume_level):
    for threshold, reduction_amount in CONFIG['DynamicReductionRulesList']:
        if original_volume_level >= threshold:
            return reduction_amount
    return 0.0


def get_process_name_from_pid(pid):
    if pid == 0: return "System"
    try:
        process = psutil.Process(pid)
        return process.name()
    except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
        return f"PID_{pid}_?"

def find_app_sessions(app_name_target, all_sessions_list):
    found_sessions = []
    for session in all_sessions_list:
        process_name = get_process_name_from_pid(session.ProcessId)
        if process_name and app_name_target.lower() in process_name.lower():
            found_sessions.append(session)
    return found_sessions

def set_volume_gradually(session_control, target_volume, current_volume, duration_seconds, steps):
    if abs(current_volume - target_volume) < CONFIG['VolumeFloatTolerance'] or steps <= 0 or duration_seconds <= 0:
        try:
            session_control.SetMasterVolume(target_volume, None)
        except Exception as e:
            add_log_message(f"Errore impostazione diretta volume (fallback): {e}", "ERROR")
        return

    volume_diff = target_volume - current_volume
    volume_step_size = volume_diff / steps
    delay_step = duration_seconds / steps

    for i in range(steps):
        next_volume = current_volume + volume_step_size * (i + 1)
        next_volume = max(0.0, min(1.0, next_volume))
        try:
            session_control.SetMasterVolume(next_volume, None)
        except Exception as e:
            add_log_message(f"Errore impostazione graduale volume (step {i+1}): {e}", "ERROR")
            try:
                session_control.SetMasterVolume(target_volume, None)
            except Exception as e_final:
                 add_log_message(f"Errore impostazione finale volume (fallback): {e_final}", "ERROR")
            return
        time.sleep(delay_step)
    
    try:
        final_check_vol = session_control.GetMasterVolume()
        if abs(final_check_vol - target_volume) > CONFIG['VolumeFloatTolerance']:
            session_control.SetMasterVolume(target_volume, None)
    except Exception as e:
        add_log_message(f"Errore impostazione finale precisa volume: {e}", "ERROR")


console = Console()

class AppStatus:
    trigger_app_name = ""
    target_app_name = ""
    trigger_found = False
    target_found = False
    trigger_active = False
    target_current_volume_percent = "N/A"
    target_original_volume_percent = "N/A" # Usato per visualizzare il valore originale
    target_reduced_state = False
    
    # Variabili per il ripristino all'uscita
    original_target_volume_value = None # Valore float del volume originale
    is_target_volume_currently_reduced_by_script = False # Flag specifico


# Parte grafica configurazioni TUI
status = AppStatus()

def make_layout() -> Layout:
    layout = Layout(name="root")
    layout.split_column(
        Layout(name="header", size=3),
        Layout(name="main"),
        Layout(name="footer", size=1)
    )
    layout["main"].split_row(
        Layout(name="left_panel", ratio=1), 
        Layout(name="right_panel", ratio=2),
    )
    layout["left_panel"].split_column(
        Layout(name="config_display", ratio=1),
        Layout(name="status_display", ratio=1)
    )
    layout["right_panel"].name = "log_display"
    return layout

def generate_config_panel() -> Panel:
    config_table = Table(show_header=False, box=None, expand=True, padding=0)
    config_table.add_column("Setting", style="dim cyan", min_width=15, ratio=9, no_wrap=True, overflow="ellipsis")
    config_table.add_column("Value", ratio=7, overflow="fold", no_wrap=False)

    config_table.add_row("Trigger App:", Text(CONFIG['TriggerAppName'], overflow="fold"))
    config_table.add_row("Target App:", Text(CONFIG['TargetAppName'], overflow="fold"))
    config_table.add_row("Trigger Soglia Vol.:", f"{CONFIG['TriggerVolumeThreshold']*100:.0f}%")
    config_table.add_row("Polling Interval:", f"{CONFIG['PollingIntervalSeconds']}s")
    config_table.add_row("Debounce Time:", f"{CONFIG['DebounceTimeSeconds']}s")
    reduction_dynamic_text = Text("Sì", style="green") if CONFIG['UseDynamicReduction'] else Text("No", style="red")
    config_table.add_row("Riduzione Dinamica:", reduction_dynamic_text)
    if not CONFIG['UseDynamicReduction']:
        config_table.add_row("Riduzione Fissa:", f"{CONFIG['FixedReductionAmountPoints']*100:.0f} punti %")
    config_table.add_row("Volume Min. Ridotto:", f"{CONFIG['MinimumVolumeAfterReduction']*100:.0f}%")
    fade_out_val = f"{CONFIG['FadeOutDurationSeconds']}s ({CONFIG['FadeOutSteps']} steps)"
    config_table.add_row("Fade Out:", Text(fade_out_val, overflow="fold"))
    fade_in_val = f"{CONFIG['FadeInDurationSeconds']}s ({CONFIG['FadeInSteps']} steps)"
    config_table.add_row("Fade In:", Text(fade_in_val, overflow="fold"))
    fade_uscita_val = f"{CONFIG['ExitFadeDurationSeconds']:.2f}s ({CONFIG['ExitFadeSteps']} steps)"
    config_table.add_row("Fade Uscita:", Text(fade_uscita_val, overflow="fold"))
    return Panel(config_table, title="[b]Impostazioni[/b]", border_style="blue", padding=(0, 1))

def generate_status_panel() -> Panel:
    status_text = Text()
    status_text.append("App Trigger: ", style="bold")
    status_text.append(f"{status.trigger_app_name} ", style="cyan")
    status_text.append("Trovata" if status.trigger_found else "Non Trovata", style="green" if status.trigger_found else "red")
    status_text.append("\n  └ Attiva: ", style="bold")
    status_text.append("Sì" if status.trigger_active else "No", style="magenta" if status.trigger_active else "dim")
    status_text.append("\n\nApp Target: ", style="bold")
    status_text.append(f"{status.target_app_name} ", style="cyan")
    status_text.append("Trovata" if status.target_found else "Non Trovata", style="green" if status.target_found else "red")
    status_text.append(f"\n  └ Volume Attuale: {status.target_current_volume_percent}")
    status_text.append(f"\n  └ Volume Originale: {status.target_original_volume_percent}") # Usa la stringa formattata
    status_text.append("\n  └ Stato Riduzione: ", style="bold")
    status_text.append("ATTIVA" if status.is_target_volume_currently_reduced_by_script else "NON ATTIVA", style="yellow" if status.is_target_volume_currently_reduced_by_script else "dim")
    return Panel(status_text, title="[b]Stato Attuale[/b]", border_style="green", padding=(1,1))

def generate_log_panel() -> Panel:
    log_content = Text("\n").join(list(LOG_MESSAGES))
    return Panel(log_content, title="[b]Log Eventi[/b]", border_style="yellow", padding=(1,1))

def generate_ui_components() -> Layout:
    layout = make_layout()
    header_title = Text.assemble(("Volume Changer", "bold bright_magenta"), (" v1.1"))
    layout["header"].update(Align.center(header_title))
    layout["config_display"].update(generate_config_panel())
    layout["status_display"].update(generate_status_panel())
    layout["log_display"].update(generate_log_panel())
    layout["footer"].update(Align.center(Text("Premi Ctrl+C per uscire", style="dim white")))
    return layout


def main_loop_tui(live: Live):
    global status

    status.trigger_app_name = CONFIG['TriggerAppName']
    status.target_app_name = CONFIG['TargetAppName']
    add_log_message(f"Controllo volume avviato. Trigger: {CONFIG['TriggerAppName']}, Target: {CONFIG['TargetAppName']}", "SUCCESS")

    # Queste variabili ora sono in status per il ripristino all'uscita
    # status.original_target_volume_value = None
    # status.is_target_volume_currently_reduced_by_script = False
    
    trigger_app_quiet_since = None 
    trigger_app_previously_found = True 
    target_app_previously_found = True
    current_reduced_volume_level = None # Livello a cui il volume è stato effettivamente ridotto

    while True:
        live.update(generate_ui_components())
        time.sleep(CONFIG['PollingIntervalSeconds'])

        all_sessions = AudioUtilities.GetAllSessions()
        trigger_sessions_list = find_app_sessions(CONFIG['TriggerAppName'], all_sessions)
        target_sessions_list = find_app_sessions(CONFIG['TargetAppName'], all_sessions)
        target_session = target_sessions_list[0] if target_sessions_list else None

        status.trigger_found = bool(trigger_sessions_list)
        status.target_found = bool(target_session)
        
        if not status.trigger_found and trigger_app_previously_found:
            add_log_message(f"App trigger '{CONFIG['TriggerAppName']}' non trovata.", "WARN")
        elif status.trigger_found and not trigger_app_previously_found:
             add_log_message(f"App trigger '{CONFIG['TriggerAppName']}' trovata nuovamente.", "INFO")
        trigger_app_previously_found = status.trigger_found

        if not status.target_found and target_app_previously_found and (status.trigger_found or status.is_target_volume_currently_reduced_by_script):
            add_log_message(f"App target '{CONFIG['TargetAppName']}' non trovata.", "WARN")
            if status.is_target_volume_currently_reduced_by_script: # Se scompare mentre era ridotto
                status.original_target_volume_value = None
                status.is_target_volume_currently_reduced_by_script = False
                trigger_app_quiet_since = None
                current_reduced_volume_level = None
                status.target_original_volume_percent = "N/A"
        elif status.target_found and not target_app_previously_found:
            add_log_message(f"App target '{CONFIG['TargetAppName']}' trovata nuovamente.", "INFO")
        target_app_previously_found = status.target_found
        
        if target_session:
            try:
                vol_ctrl_for_display = target_session._ctl.QueryInterface(ISimpleAudioVolume)
                current_vol_display = vol_ctrl_for_display.GetMasterVolume()
                status.target_current_volume_percent = f"{current_vol_display*100:.0f}%"
            except: status.target_current_volume_percent = "Errore"
        else: status.target_current_volume_percent = "N/A"

        # Aggiorna la stringa per la visualizzazione del volume originale
        status.target_original_volume_percent = f"{status.original_target_volume_value*100:.0f}%" if status.original_target_volume_value is not None else "N/A"


        status.trigger_active = False
        if trigger_sessions_list:
            for trigger_session_candidate in trigger_sessions_list:
                try:
                    meter = trigger_session_candidate._ctl.QueryInterface(IAudioMeterInformation)
                    if meter.GetPeakValue() > CONFIG['TriggerVolumeThreshold']:
                        status.trigger_active = True
                        break 
                except (COMError, AttributeError, Exception): pass 

        if status.trigger_active:
            trigger_app_quiet_since = None 
            if target_session:
                volume_control_target = target_session._ctl.QueryInterface(ISimpleAudioVolume)
                actual_current_target_vol = volume_control_target.GetMasterVolume()

                if not status.is_target_volume_currently_reduced_by_script: 
                    if status.original_target_volume_value is None: 
                        status.original_target_volume_value = actual_current_target_vol
                        status.target_original_volume_percent = f"{status.original_target_volume_value*100:.0f}%" # Aggiorna display subito
                    
                    reduction_points = calculate_dynamic_reduction_amount(status.original_target_volume_value) if CONFIG['UseDynamicReduction'] else CONFIG['FixedReductionAmountPoints']
                    volume_to_set_when_triggered = max(status.original_target_volume_value - reduction_points, CONFIG['MinimumVolumeAfterReduction'])
                    volume_to_set_when_triggered = min(volume_to_set_when_triggered, status.original_target_volume_value)

                    if abs(actual_current_target_vol - volume_to_set_when_triggered) > CONFIG['VolumeFloatTolerance']:
                        msg = (f"{CONFIG['TriggerAppName']} attiva! Abbasso {CONFIG['TargetAppName']} da "
                               f"{actual_current_target_vol*100:.0f}% a {volume_to_set_when_triggered*100:.0f}%. "
                               f"(Originale: {status.original_target_volume_value*100:.0f}%)")
                        add_log_message(msg, "ACTION")
                        set_volume_gradually(volume_control_target, volume_to_set_when_triggered, actual_current_target_vol, 
                                             CONFIG['FadeOutDurationSeconds'], CONFIG['FadeOutSteps'])
                    current_reduced_volume_level = volume_to_set_when_triggered
                    status.is_target_volume_currently_reduced_by_script = True

                elif current_reduced_volume_level is not None and \
                     abs(actual_current_target_vol - current_reduced_volume_level) > CONFIG['VolumeFloatTolerance']:
                    msg = (f"{CONFIG['TargetAppName']} volume ({actual_current_target_vol*100:.0f}%) variato esternamente. "
                           f"Ri-abbasso a {current_reduced_volume_level*100:.0f}%.")
                    add_log_message(msg, "ACTION")
                    set_volume_gradually(volume_control_target, current_reduced_volume_level, actual_current_target_vol, 
                                         CONFIG['FadeOutDurationSeconds'], CONFIG['FadeOutSteps'])
        else: # Trigger non attivo
            if status.is_target_volume_currently_reduced_by_script: 
                if trigger_app_quiet_since is None:
                    trigger_app_quiet_since = time.time() 

                if trigger_app_quiet_since and (time.time() - trigger_app_quiet_since >= CONFIG['DebounceTimeSeconds']):
                    if target_session and status.original_target_volume_value is not None:
                        volume_control_target = target_session._ctl.QueryInterface(ISimpleAudioVolume)
                        actual_current_target_vol = volume_control_target.GetMasterVolume()
                        
                        if abs(actual_current_target_vol - status.original_target_volume_value) > CONFIG['VolumeFloatTolerance']:
                            msg = (f"{CONFIG['TriggerAppName']} silenzioso. Ripristino {CONFIG['TargetAppName']} da "
                                   f"{actual_current_target_vol*100:.0f}% a {status.original_target_volume_value*100:.0f}%.")
                            add_log_message(msg, "ACTION")
                            set_volume_gradually(volume_control_target, status.original_target_volume_value, actual_current_target_vol, 
                                                 CONFIG['FadeInDurationSeconds'], CONFIG['FadeInSteps'])
                        
                        status.original_target_volume_value = None 
                        status.is_target_volume_currently_reduced_by_script = False
                        trigger_app_quiet_since = None
                        current_reduced_volume_level = None
                        status.target_original_volume_percent = "N/A"
                    elif not target_session and status.original_target_volume_value is not None: # App target chiusa
                        add_log_message(f"{CONFIG['TriggerAppName']} silenzioso. App target '{CONFIG['TargetAppName']}' non trovata, resetto stato.", "WARN")
                        status.original_target_volume_value = None
                        status.is_target_volume_currently_reduced_by_script = False
                        trigger_app_quiet_since = None
                        current_reduced_volume_level = None
                        status.target_original_volume_percent = "N/A"
                    elif status.original_target_volume_value is None and status.is_target_volume_currently_reduced_by_script: # Stato anomalo
                         add_log_message(f"{CONFIG['TriggerAppName']} silenzioso. Stato inconsistente. Reset stato.", "WARN")
                         status.is_target_volume_currently_reduced_by_script = False
                         trigger_app_quiet_since = None
                         current_reduced_volume_level = None
                         status.target_original_volume_percent = "N/A" # Resetta anche display
        
        live.update(generate_ui_components())


if __name__ == "__main__":
    load_config() 
    
    status.trigger_app_name = CONFIG['TriggerAppName']
    status.target_app_name = CONFIG['TargetAppName']

    with Live(generate_ui_components(), refresh_per_second=CONFIG['TuiRefreshRate'], screen=True, transient=False) as live:
        try:
            main_loop_tui(live)
        except KeyboardInterrupt:
            add_log_message("Uscita dal programma richiesta dall'utente.", "WARN")
            live.update(generate_ui_components()) # Aggiorna TUI un'ultima volta
            
            if status.is_target_volume_currently_reduced_by_script and status.original_target_volume_value is not None:
                add_log_message(f"Tentativo di ripristino volume di {CONFIG['TargetAppName']} a {status.original_target_volume_value*100:.0f}%...", "ACTION")
                all_sessions_on_exit = AudioUtilities.GetAllSessions()
                target_sessions_list_on_exit = find_app_sessions(CONFIG['TargetAppName'], all_sessions_on_exit)
                target_session_on_exit = target_sessions_list_on_exit[0] if target_sessions_list_on_exit else None

                if target_session_on_exit:
                    try:
                        volume_control_target = target_session_on_exit._ctl.QueryInterface(ISimpleAudioVolume)
                        # Ripristino istantaneo
                        volume_control_target.SetMasterVolume(status.original_target_volume_value, None)
                        add_log_message(f"Volume di {CONFIG['TargetAppName']} ripristinato istantaneamente a {status.original_target_volume_value*100:.0f}%.", "SUCCESS")
                    except Exception as e_exit:
                        add_log_message(f"Errore nel ripristinare istantaneamente il volume di {CONFIG['TargetAppName']} all'uscita: {e_exit}", "ERROR")
                else:
                    add_log_message(f"Impossibile trovare {CONFIG['TargetAppName']} per ripristinare il volume all'uscita.", "WARN")
            else:
                add_log_message(f"Nessun ripristino del volume necessario per {CONFIG['TargetAppName']} all'uscita.", "INFO")
            
            # Pausa per permettere di leggere il messaggio di log del ripristino prima che la TUI scompaia
            time.sleep(0.5) 

        except Exception as e:
            console.print_exception(show_locals=True)
            add_log_message(f"ERRORE GLOBALE IMPREVISTO: {e}", "ERROR")
            live.update(generate_ui_components()) 
            time.sleep(5)
        finally:
            add_log_message("Script terminato.", "INFO")
            # console.clear() # Opzionale: pulisce lo schermo dopo la chiusura di Live
    
    # Stampa log finale sulla console normale
    print("\n--- Log ------------------------------")
    for msg_text in LOG_MESSAGES:
        console.print(msg_text)
    print("--------------------------------------")