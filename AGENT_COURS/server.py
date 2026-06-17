import os
import io
import json
import time
import pickle
import threading
import socket  
import tempfile  # Pour la gestion des fichiers temporaires hors de VS Code
from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload, MediaFileUpload
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
import google.auth.transport.requests  
import httplib2  
import google_auth_httplib2  # Ajout de la bibliothèque de transport moderne de Google
from pypdf import PdfReader
from reportlab.lib.pagesizes import letter
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib import colors
from reportlab.graphics.shapes import Drawing, Rect, String, Line
from groq import Groq
from dotenv import load_dotenv

# Chargement automatique des variables du fichier .env
load_dotenv()

# =========================================================================
# ⚙️ CONFIGURATION RÉSEAU ET TIMEOUT POUR LE PARTAGE DE 
# XION
# =========================================================================
socket.setdefaulttimeout(60)

app = Flask(__name__)
CORS(app, resources={r"/api/*": {"origins": "*", "methods": ["GET", "POST", "OPTIONS"], "allow_headers": ["Content-Type"]}})

CHOIX_INTERVALLE = "24h"               
DUREE_VEILLE_SECONDES = 24 * 60 * 60   
VEILLE_ACTIVE = True                   

CONVERTISSEUR_TEMPS = {
    "manual": 0,
    "15m": 15 * 60,
    "1h": 60 * 60,
    "12h": 12 * 60 * 60,
    "24h": 24 * 60 * 60,
    "7d": 7 * 24 * 60 * 60
}

# =========================================================================
# 🔐 1. CHARGEMENT DES SECRETS (.ENV) ET CONFIGURATION GOOGLE / GROQ
# =========================================================================
GROQ_API_KEY = os.environ.get("GROQ_API_KEY") 
ID_DOSSIER_DRIVE = os.environ.get("ID_DOSSIER_DRIVE") 
GOOGLE_CLIENT_ID = os.environ.get("GOOGLE_CLIENT_ID")
GOOGLE_CLIENT_SECRET = os.environ.get("GOOGLE_CLIENT_SECRET")

client = Groq(api_key=GROQ_API_KEY)
SCOPES = ['https://www.googleapis.com/auth/drive']
creds = None

print("🚀 Démarrage de l'agent de veille juridique (Version Rigueur & Design)...")

# Re-constitution de la structure JSON de Google directement en mémoire
GOOGLE_CONFIG = {
    "web": {
        "client_id": GOOGLE_CLIENT_ID,
        "project_id": "agent-cours-project",
        "auth_uri": "https://accounts.google.com/o/oauth2/auth",
        "token_uri": "https://oauth2.googleapis.com/token",
        "auth_provider_x509_cert_url": "https://www.googleapis.com/oauth2/v1/certs",
        "client_secret": GOOGLE_CLIENT_SECRET,
        "redirect_uris": ["http://localhost:8080", "http://127.0.0.1:8080"]
    }
}

if os.path.exists('token.pickle'):
    with open('token.pickle', 'rb') as token:
        creds = pickle.load(token)

if not creds or not creds.valid:
    if creds and creds.expired and creds.refresh_token:
        try:
            requete_transport = google.auth.transport.requests.Request()
            creds.refresh(requete_transport)
        except Exception:
            if os.path.exists('token.pickle'):
                os.remove('token.pickle')
            flow = InstalledAppFlow.from_client_config(GOOGLE_CONFIG, SCOPES)
            creds = flow.run_local_server(port=0)
    else:
        if not GOOGLE_CLIENT_ID or not GOOGLE_CLIENT_SECRET:
            print("❌ Erreur : Les variables GOOGLE_CLIENT_ID ou GOOGLE_CLIENT_SECRET sont manquantes dans le fichier .env")
            exit(1)
        flow = InstalledAppFlow.from_client_config(GOOGLE_CONFIG, SCOPES)
        creds = flow.run_local_server(port=0)
        
    with open('token.pickle', 'wb') as token:
        pickle.dump(creds, token)

# Transport sécurisé moderne avec injection du timeout de 60s
http_custom = httplib2.Http(timeout=60)
http_autorise = google_auth_httplib2.AuthorizedHttp(creds, http=http_custom)
drive_service = build('drive', 'v3', http=http_autorise)

# =========================================================================
# 📄 2. ACTIONS MÉTIERS (SCAN, LECTURE PDF, GENERATION PDF STYLISÉ)
# =========================================================================
def scanner_dossier_drive():
    query = f"'{ID_DOSSIER_DRIVE}' in parents and mimeType='application/pdf' and trashed=false"
    try:
        resultats = drive_service.files().list(q=query, fields="files(id, name)").execute()
        return resultats.get('files', [])
    except Exception as e:
        print(f"❌ Erreur lors du scan du Drive : {e}")
        return []

def lire_contenu_pdf(file_id):
    try:
        request = drive_service.files().get_media(fileId=file_id)
        fh = io.BytesIO()
        downloader = MediaIoBaseDownload(fh, request)
        done = False
        while not done:
            _, done = downloader.next_chunk()
        fh.seek(0)
        lecteur_pdf = PdfReader(fh)
        texte_total = ""
        for page in lecteur_pdf.pages[:10]:
            texte_total += page.extract_text() or ""
        return texte_total[:8000]
    except Exception as e:
        return f"Erreur lors de la lecture du fichier : {str(e)}"

def modifier_et_remplacer_pdf(nom_fichier, nouveau_contenu_texte, id_original):
    try:
        # Génération du fichier temporaire dans le cache du système (invisible dans VS Code)
        chemin_temporaire = os.path.join(tempfile.gettempdir(), nom_fichier)
        
        doc = SimpleDocTemplate(chemin_temporaire, pagesize=letter, rightMargin=45, leftMargin=45, topMargin=45, bottomMargin=45)
        styles = getSampleStyleSheet()
        
        style_titre = ParagraphStyle(name='Titre_Pedago', parent=styles['Heading1'], fontSize=22, leading=26, textColor=colors.HexColor("#1A365D"), spaceAfter=6, alignment=1)
        style_intertitre = ParagraphStyle(name='Intertitre_Pedago', parent=styles['Heading2'], fontSize=13, leading=17, textColor=colors.HexColor("#2C5282"), spaceBefore=14, spaceAfter=8, keepWithNext=True)
        style_texte = ParagraphStyle(name='Texte_Pedago', parent=styles['Normal'], fontSize=10.5, leading=15, textColor=colors.HexColor("#2D3748"), spaceAfter=8)
        style_encadre = ParagraphStyle(name='Encadre_Pedago', parent=styles['Normal'], fontSize=10, leading=14, textColor=colors.HexColor("#2C5282"), backColor=colors.HexColor("#EBF8FF"), borderColor=colors.HexColor("#3182CE"), borderWidth=1, borderPadding=8, spaceBefore=10, spaceAfter=10)
        
        histoire = []
        nom_propre = nom_fichier.replace('.pdf', '').replace('MAJ_', '').replace('_', ' ').title()
        histoire.append(Paragraph(f"<b>FICHE DE SYNTHÈSE : {nom_propre}</b>", style_titre))
        
        ligne_titre = Drawing(520, 10)
        ligne_titre.add(Line(0, 5, 520, 5, strokeColor=colors.HexColor("#3182CE"), strokeWidth=2))
        histoire.append(ligne_titre)
        histoire.append(Spacer(1, 15))
        
        paragraphes = nouveau_contenu_texte.split('\n')
        for p in paragraphes:
            p_strip = p.strip()
            if not p_strip:
                histoire.append(Spacer(1, 6))
                continue
            
            p_clean = p_strip
            est_titre_markdown = False
            
            if p_clean.startswith("## "):
                p_clean = p_clean.replace("## ", "").strip()
                est_titre_markdown = True
            elif p_clean.startswith("# "):
                p_clean = p_clean.replace("# ", "").strip()
                est_titre_markdown = True
            elif p_clean.startswith("### "):
                p_clean = p_clean.replace("###", "").strip()
                est_titre_markdown = True

            while "**" in p_clean:  
                p_clean = p_clean.replace("**", "<b>", 1)
                p_clean = p_clean.replace("**", "</b>", 1)
                
            if p_clean.startswith("* "):
                p_clean = p_clean.replace("* ", "• ", 1)
                
            if p_clean.count("<b>") > p_clean.count("</b>"): p_clean += "</b>"
            
            if "• Schéma de la théorie de Shannon & Weaver" in p_clean:
                histoire.append(Paragraph(p_clean, style_texte))
                schema_sw = Drawing(520, 40)
                schema_sw.add(Rect(5, 5, 80, 25, fillColor=colors.HexColor("#E2E8F0"), strokeColor=colors.HexColor("#4A5568"), strokeWidth=1))
                schema_sw.add(String(45, 13, "Émetteur", textAnchor="middle", fontSize=8, fontName="Helvetica-Bold"))
                schema_sw.add(Line(85, 17, 145, 17, strokeColor=colors.HexColor("#4A5568"), strokeWidth=1.5))
                schema_sw.add(Rect(145, 5, 100, 25, fillColor=colors.HexColor("#EDF2F7"), strokeColor=colors.HexColor("#4A5568"), strokeWidth=1))
                schema_sw.add(String(195, 13, "Codage / Canal", textAnchor="middle", fontSize=8))
                schema_sw.add(Line(245, 17, 305, 17, strokeColor=colors.HexColor("#4A5568"), strokeWidth=1.5))
                schema_sw.add(Rect(305, 5, 110, 25, fillColor=colors.HexColor("#EDF2F7"), strokeColor=colors.HexColor("#4A5568"), strokeWidth=1))
                schema_sw.add(String(360, 13, "Message (Signal)", textAnchor="middle", fontSize=8))
                schema_sw.add(Line(415, 17, 440, 17, strokeColor=colors.HexColor("#4A5568"), strokeWidth=1.5))
                schema_sw.add(Rect(440, 5, 75, 25, fillColor=colors.HexColor("#E2E8F0"), strokeColor=colors.HexColor("#4A5568"), strokeWidth=1))
                schema_sw.add(String(477, 13, "Récepteur", textAnchor="middle", fontSize=8, fontName="Helvetica-Bold"))
                histoire.append(schema_sw)
                continue
            
            if est_titre_markdown or p_clean.startswith("PARTIE") or p_clean.startswith("TITRE") or p_clean.startswith("SECTION"):
                histoire.append(Paragraph(f"<b>{p_clean}</b>", style_intertitre))
            elif p_clean.upper().startswith("IMPORTANT") or p_clean.upper().startswith("DÉFINITION") or p_clean.startswith("💡"):
                histoire.append(Paragraph(p_clean, style_encadre))
            else:
                histoire.append(Paragraph(p_clean, style_texte))
        
        doc.build(histoire)
        time.sleep(1)  
        
        metadata_fichier = {'name': nom_fichier, 'parents': [ID_DOSSIER_DRIVE]}
        media = MediaFileUpload(chemin_temporaire, mimetype='application/pdf', resumable=True)
        drive_service.files().create(body=metadata_fichier, media_body=media, fields='id').execute()
        
        try: os.remove(chemin_temporaire)
        except: pass
            
        drive_service.files().update(fileId=id_original, body={'trashed': True}).execute()
        return f"Succès ! '{nom_fichier}' transformé."
    except Exception as e:
        return f"Erreur : {str(e)}"

# =========================================================================
# 🎛️ 3. BOUCLE TEMPORELLE DE VEILLE
# =========================================================================
def executer_session_de_veille():
    print("\n[ROUTINE] 🔍 Lancement de l'analyse des cours...")
    fichiers_a_traiter = scanner_dossier_drive()

    if not fichiers_a_traiter:
        print("[ROUTINE] 🎉 Parfait ! Tout est à jour dans le Drive.")
        return

    for f in fichiers_a_traiter:
        id_fichier = f.get('id')
        nom_fichier = f.get('name')
        
        texte_cours = lire_contenu_pdf(id_fichier)
        print(f"[ROUTINE] 🧠 Audit et mise à jour IA pour : '{nom_fichier}'...")
        
        # =========================================================================
        # 🧠 PROMPT UNIVERSEL ET INTELLIGENT (MODIFIÉ ICI)
        # =========================================================================
        prompt_analyse = (
            f"Tu es un professeur universitaire de haut niveau, expert multidisciplinaire. "
            f"Ta mission est de réécrire le contenu du cours suivant pour le restituer de manière exhaustive tout en appliquant une veille pour l'année 2026 s'il y a lieu :\n\n"
            f"Titre du fichier : {nom_fichier}\n"
            f"Contenu extrait : \n{texte_cours}\n\n"
            "⚠️ REGLE ABSOLUE DE RECONSTRUCTION :\n"
            "- Tu dois CONSERVER TOUTES les définitions, théories, concepts, exemples stables et informations d'origine présents dans le texte ci-dessus.\n"
            "- Si une information ou partie du texte de base est juste, factuelle et intemporelle, RÉÉCRIS-LA EXACTEMENT TEL QUEL, sans la résumer ni la supprimer.\n"
            "- N'ajoute des modifications, des compléments ou des corrections QUE sur les éléments nécessitant une mise à jour contextuelle pour 2026.\n\n"
            
            "DIRECTIVES DE VÉRIFICATION ET DE MISE À JOUR (Selon le sujet détecté) :\n\n"
            
            "1. POUR LES COURS DE DROIT :\n"
            "- Conserve l'intégralité du plan et des principes fondamentaux.\n"
            "- Modifie ou actualise UNIQUEMENT les lois, les articles de codes, la jurisprudence ou les réglementations obsolètes pour qu'ils s'alignent avec les réformes réelles applicables en 2026 (ex: RGPD européen, IA Act, régulation numérique).\n\n"
            
            "2. POUR LES COURS DE COMMUNICATION COMMERCIALE OU MARKETING :\n"
            "- Conserve l'intégralité des fondamentaux théoriques (ex: les modèles de communication comme Shannon & Weaver ou Lasswell, les objectifs cognitifs/affectifs/conctifs, et la typologie des cibles).\n"
            "- Mets à jour les applications pratiques de ces concepts pour refléter le paysage de 2026 : intègre comment l'IA générative transforme la création, la fin définitive des cookies tiers pour le ciblage, l'essor des réseaux verticaux (TikTok) pour toucher les cibles, les exigences de transparence RSE (anti-greenwashing) et le Social Commerce.\n\n"
            
            "3. POUR TOUS LES AUTRES COURS :\n"
            "- Garde tout le contenu intact, et adapte uniquement les dates ou les vieilles statistiques pour les connecter à l'actualité économique de 2026.\n\n"
            
            "CONSIGNES FORMELLES DE RENDU :\n"
            "- Restitue la totalité du document sous forme de cours réécrit structuré (Titres, sections, paragraphes).\n"
            "- Rédige dans un style purement académique, rigoureux et fluide.\n"
            "- Ne fais aucune métanarrative ni commentaire textuel (interdiction d'écrire 'Voici le texte conservé' ou 'Mise à jour effectuée'). Délivre uniquement le document finalisé."
        )
        
        try:
            chat_completion = client.chat.completions.create(
                messages=[{"role": "user", "content": prompt_analyse}],
                model="llama-3.1-8b-instant",
                temperature=0.1
            )
            texte_mis_a_jour = chat_completion.choices[0].message.content
            
            if texte_mis_a_jour and len(texte_mis_a_jour) > 100:
                resultat = modifier_et_remplacer_pdf(nom_fichier, texte_mis_a_jour, id_fichier)
                print(f"   ↳ {resultat}")
            time.sleep(2)  
        except Exception as e:
            print(f"🚨 Erreur fichier : {e}")
    print("\n🎉 Session de veille achevée.")

def boucle_temporelle_de_veille():
    global DUREE_VEILLE_SECONDES, CHOIX_INTERVALLE, VEILLE_ACTIVE
    while VEILLE_ACTIVE:
        if CHOIX_INTERVALLE == "manual":
            time.sleep(2)
            continue
        time.sleep(DUREE_VEILLE_SECONDES)
        if CHOIX_INTERVALLE != "manual":
            try: executer_session_de_veille()
            except: pass

# =========================================================================
# 🏠 ROUTE RACINE
# =========================================================================
@app.route('/', methods=['GET'])
def index():    
    return send_from_directory('.', 'agent.html')

@app.route('/<path:filename>')
def static_files(filename):
    return send_from_directory('.', filename)

# =========================================================================
# 🌐 4. ROUTES API FLASK
# =========================================================================
@app.route('/api/schedule', methods=['POST', 'OPTIONS'])
def update_schedule():
    if request.method == 'OPTIONS':
        return jsonify({"status": "ok"}), 200
    global CHOIX_INTERVALLE, DUREE_VEILLE_SECONDES
    data = request.get_json()
    laps_de_temps = data['interval']
    if laps_de_temps in CONVERTISSEUR_TEMPS:
        CHOIX_INTERVALLE = laps_de_temps
        DUREE_VEILLE_SECONDES = CONVERTISSEUR_TEMPS[laps_de_temps]
        print(f"\n[API] Nouvelle fréquence reçue : {CHOIX_INTERVALLE}")
        return jsonify({"status": "success"}), 200
    return jsonify({"status": "error"}), 400

@app.route('/api/analyze', methods=['POST', 'OPTIONS'])
def trigger_manual_analyze():
    if request.method == 'OPTIONS':
        return jsonify({"status": "ok"}), 200
    print("\n[API] ⚡ Déclenchement forcé de l'analyse IA via l'interface web.")
    try:
        executer_session_de_veille()
        return jsonify({"status": "success"}), 200
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

if __name__ == '__main__':
    thread_veille = threading.Thread(target=boucle_temporelle_de_veille)
    thread_veille.daemon = True
    thread_veille.start()
    
    port = int(os.environ.get('PORT', 8080))
    print(f"Serveur Flask disponible sur http://0.0.0.0:{port}")
    app.run(host='0.0.0.0', port=port, debug=False)
