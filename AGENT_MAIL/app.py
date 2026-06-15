from flask import Flask, render_template, request, redirect, url_for
import threading
import os
from dotenv import load_dotenv
from groq_fixed import run_watch, SimpleLogger

# Charger .env pour valeurs par défaut
load_dotenv()

app = Flask(__name__)

# Logger partagé entre l'app et la tâche en background (persistant)
app_logger = SimpleLogger(file_path='veilles.log')
bg_thread = None
bg_stop_event = None
STOP_FLAG = os.path.join(os.getcwd(), 'stop_veille.flag')


@app.route('/', methods=['GET', 'POST'])
def index():
    if request.method == 'POST':
        sender = request.form.get('sender')
        password = request.form.get('password')
        recipients = request.form.get('recipients')
        groq_key = request.form.get('groq_key')
        newsapi_key = request.form.get('newsapi_key')
        interval = request.form.get('interval') or '0'

        # Convertir les valeurs en float (sécurité)
        try:
            interval_val = float(interval)
        except Exception:
            interval_val = 0

        global bg_thread, bg_stop_event

        def single_run():
            run_watch(sender, password, recipients, groq_api_key=groq_key, newsapi_key=newsapi_key, logger=app_logger)

        def repeating_run(stop_event):
            # remove any existing stop flag when starting
            try:
                if os.path.exists(STOP_FLAG):
                    os.remove(STOP_FLAG)
            except Exception:
                pass

            while not stop_event.is_set() and not os.path.exists(STOP_FLAG):
                run_watch(sender, password, recipients, groq_api_key=groq_key, newsapi_key=newsapi_key, logger=app_logger)
                # attendre l'intervalle ou sortir si on demande l'arrêt
                stop_event.wait(interval_val)

        # Créer/.mettre à jour .env si besoin
        def write_env_if_missing(sender, password, groq_key, newsapi_key):
            env_path = os.path.join(os.getcwd(), '.env')
            # Si .env existe déjà, ne rien faire (ne pas écraser)
            if os.path.exists(env_path):
                app_logger.info('.env existe déjà — pas d\'écriture')
                return

            try:
                with open(env_path, 'w', encoding='utf-8') as f:
                    if sender:
                        f.write(f"EMAIL_EXPEDITEUR={sender}\n")
                    if password:
                        f.write(f"EMAIL_MOT_DE_PASSE={password}\n")
                    if groq_key:
                        f.write(f"GROQ_API_KEY={groq_key}\n")
                    if newsapi_key:
                        f.write(f"NEWSAPI_KEY={newsapi_key}\n")
                app_logger.info(f".env créé : {env_path}")
            except Exception as e:
                app_logger.error(f"Impossible d'écrire .env: {e}")

        write_env_if_missing(sender, password, groq_key, newsapi_key)

        # Lancer selon interval
        if interval_val and interval_val > 0:
            # Si une tâche est déjà en cours, on refuse de lancer une seconde
            if bg_thread and bg_thread.is_alive():
                app_logger.info("Une tâche est déjà en cours. Arrêtez-la d'abord (/stop).")
            else:
                # clear stop flag when starting
                try:
                    if os.path.exists(STOP_FLAG):
                        os.remove(STOP_FLAG)
                except Exception:
                    pass
                bg_stop_event = threading.Event()
                bg_thread = threading.Thread(target=repeating_run, args=(bg_stop_event,), daemon=True)
                bg_thread.start()
                app_logger.info(f"Tâche répétée lancée en background — intervalle {interval_val}s — envoi vers: {recipients}")
        else:
            threading.Thread(target=single_run, daemon=True).start()
            app_logger.info(f"Tâche unique lancée en background — envoi vers: {recipients}")

        return redirect(url_for('logs'))
    else:
        # Pré-remplir uniquement l'expéditeur et les clés depuis .env
        sender_default = os.getenv('EMAIL_EXPEDITEUR', '')
        password_default = os.getenv('EMAIL_MOT_DE_PASSE', '')
        groq_key_default = os.getenv('GROQ_API_KEY', '')
        newsapi_key_default = os.getenv('NEWSAPI_KEY', '')

        return render_template('index.html', sender=sender_default, password=password_default, groq_key=groq_key_default, newsapi_key=newsapi_key_default)


@app.route('/logs')
def logs():
    # Utiliser le logger partagé
    lines = app_logger.get_lines()
    return render_template('logs.html', lines=lines)


@app.route('/stop')
def stop():
    global bg_thread, bg_stop_event
    # create stop flag (works across gunicorn workers) and set event if present
    try:
        with open(STOP_FLAG, 'w') as f:
            f.write('stop')
    except Exception as e:
        app_logger.error(f"Impossible de créer stop flag: {e}")

    if bg_stop_event:
        bg_stop_event.set()
        app_logger.info("Signal d'arrêt envoyé à la tâche background.")
    else:
        app_logger.info("Aucun thread local, stop flag créé pour arrêter la tâche en cours.")
    return redirect(url_for('logs'))


if __name__ == '__main__':
    app.run(port=5000, debug=True)
