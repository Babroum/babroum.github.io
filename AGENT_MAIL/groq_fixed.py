import feedparser
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from groq import Groq
import re
import requests
import os 
from dotenv import load_dotenv

load_dotenv()

# Charger variables d'environnement depuis .env si présent

# --- Config ---

# Sources RSS de base (fallback)
FEEDS_RSS = [
    ("EducPros",              "https://www.letudiant.fr/educpros/rss.xml"),
    ("Le Monde Éco",          "https://www.lemonde.fr/economie/rss_full.xml"),
    ("Les Échos",             "https://www.lesechos.fr/rss/rss_une.xml"),
    ("The Conversation FR",   "https://theconversation.com/fr/articles.atom"),
    ("Cadremploi Actus",      "https://www.cadremploi.fr/rss/actualites.xml"),
]

# APIs de news (gratuit jusqu'à limites)
NEWSAPI_KEY = os.environ.get("NEWSAPI_KEY") # Gratuit, limité à 100 req/jour
NEWSAPI_URL = "https://newsapi.org/v2/everything"

# Bing News API (alternative, génère RSS dynamiquement)
def get_feeds_from_newsapi(logger=None):
    """Récupère les articles via NewsAPI pour les mots-clés"""
    import requests
    feeds = []
    
    queries = [
        "économie France",
        "gestion entreprise", 
        "master MBA France",
        "éducation supérieure",
        "finance business",
        "startups entrepreneuriat",
        "transformation digitale",
        "management RH",
    ]
    
    for query in queries:
        try:
            response = requests.get(NEWSAPI_URL, params={
                "q": query,
                "language": "fr",
                "sortBy": "publishedAt",
                "apiKey": NEWSAPI_KEY,
                "pageSize": 5
            }, timeout=5)
            
            if response.status_code == 200:
                data = response.json()
                if data.get("articles"):
                    feeds.append((f"NewsAPI: {query}", data.get("articles", [])))
                    if logger:
                        logger.info(f"✅ {len(data.get('articles', []))} articles trouvés pour '{query}'")
                    else:
                        print(f"✅ {len(data.get('articles', []))} articles trouvés pour '{query}'")
        except Exception as e:
            if logger:
                logger.error(f"⚠️  Erreur NewsAPI pour '{query}': {e}")
            else:
                print(f"⚠️  Erreur NewsAPI pour '{query}': {e}")
    
    return feeds


def get_feeds_from_rss(logger=None):
    """Récupère les flux RSS"""
    articles_par_sujet = []
    for nom, url in FEEDS_RSS:
        try:
            feed = feedparser.parse(url)
            articles = []
            for entry in feed.entries:
                texte = (entry.title + entry.get("summary", "")).lower()
                if any(mot in texte for mot in MOTS_CLES):
                    articles.append({
                        "title":   entry.title,
                        "link":    entry.link,
                        "summary": entry.get("summary", "")
                    })
                if len(articles) == 5:
                    break
            if articles:
                articles_par_sujet.append((nom, articles))
                if logger:
                    logger.info(f"✅ {len(articles)} articles trouvés dans {nom}")
                else:
                    print(f"✅ {len(articles)} articles trouvés dans {nom}")
        except Exception as e:
            if logger:
                logger.error(f"⚠️  Erreur en parsant {nom}: {e}")
            else:
                print(f"⚠️  Erreur en parsant {nom}: {e}")
    return articles_par_sujet

EMAIL_EXPEDITEUR = os.environ.get("EMAIL_EXPEDITEUR")  # Récupéré depuis .env
EMAIL_MOT_DE_PASSE = os.environ.get("EMAIL_MOT_DE_PASSE")  # Récupéré depuis .env
DESTINATAIRES = [
    "kriegelgael@gmail.com"
]

MOTS_CLES = [
    "master", "licence", "bachelor", "mba", "doctorat", "formation",
    "diplôme", "certification", "accréditation", "cursus",
    "université", "iae", "école de commerce", "grande école",
    "enseignement supérieur", "campus", "faculté",
    "économie", "gestion", "management", "finance", "comptabilité",
    "marketing", "ressources humaines", "stratégie", "entrepreneuriat",
    "fiscalité", "audit", "contrôle de gestion",
    "intelligence artificielle", "transition écologique", "numérique",
    "insertion professionnelle", "classement", "parcoursup",
    "réforme", "accréditation aacsb", "accréditation equis",
    "étudiant", "professeur", "chercheur", "recrutement", "entreprise",
]

GROQ_API_KEY = os.environ.get("GROQ_API_KEY")

# Override depuis .env si disponible


class SimpleLogger:
    """Logger en mémoire et optionnellement persistant dans un fichier.

    Usage: `SimpleLogger(file_path='veilles.log')` pour activer la persistance.
    """
    def __init__(self, file_path=None):
        self.lines = []
        self.file_path = file_path

    def _write_file(self, line):
        if not self.file_path:
            return
        try:
            with open(self.file_path, 'a', encoding='utf-8') as f:
                f.write(line + '\n')
        except Exception:
            # ne pas planter l'application si l'écriture échoue
            pass

    def info(self, msg):
        text = str(msg)
        print(text)
        self.lines.append(text)
        from datetime import datetime
        ts = datetime.utcnow().isoformat()
        self._write_file(f"[INFO] {ts} {text}")

    def error(self, msg):
        text = str(msg)
        print(text)
        self.lines.append(text)
        from datetime import datetime
        ts = datetime.utcnow().isoformat()
        self._write_file(f"[ERROR] {ts} {text}")

    def get_lines(self, max_lines=200):
        # Si on a un fichier, retourner les dernières lignes du fichier
        if self.file_path:
            try:
                with open(self.file_path, 'r', encoding='utf-8') as f:
                    all_lines = [l.rstrip('\n') for l in f.readlines()]
                    return all_lines[-max_lines:]
            except Exception:
                pass
        return self.lines[-max_lines:]

# --- Récupération et filtrage ---
def fetch_articles(logger=None):
    if NEWSAPI_KEY:  # Vérifier que la clé n'est pas vide
        # Lancer NewsAPI    

        """Combine NewsAPI + RSS"""
        if logger:
            logger.info("🔍 Récupération des articles...")
        else:
            print("\n🔍 Récupération des articles...\n")
        articles_par_sujet = []
        
        # 1. Essayer NewsAPI en premier (+ rapide, + moderne)
        if logger:
            logger.info("📡 NewsAPI en cours...")
        else:
            print("📡 NewsAPI en cours...", flush=True)
        newsapi_feeds = get_feeds_from_newsapi(logger=logger)
        
        for nom, articles_list in newsapi_feeds:
            filtered = []
            for article in articles_list:
                texte = (article.get("title", "") + article.get("description", "")).lower()
                if any(mot in texte for mot in MOTS_CLES):
                    filtered.append({
                        "title":   article.get("title", ""),
                        "link":    article.get("url", ""),
                        "summary": article.get("description", "")
                    })
            if filtered:
                articles_par_sujet.append((nom, filtered[:4]))
        
        # 2. Complémenter avec RSS (pour la diversité)
        """
        if logger:
            logger.info("📰 RSS en cours...")
        else:
            print("📰 RSS en cours...", flush=True)
        rss_feeds = get_feeds_from_rss(logger=logger)
        articles_par_sujet.extend(rss_feeds)
        """
        if logger:
            logger.info(f"\n✅ Total: {sum(len(a) for _, a in articles_par_sujet)} articles collectés\n")
        else:
            print(f"\n✅ Total: {sum(len(a) for _, a in articles_par_sujet)} articles collectés\n")
        return articles_par_sujet
    else:
        logger.info("⚠️  NewsAPI key vide, passage au RSS")
        return 

def summarize_with_groq(articles_par_sujet, logger=None):
    client = Groq(api_key=GROQ_API_KEY)

    # Aplatir tous les articles
    tous_les_articles = []
    for nom, articles in articles_par_sujet:
        for article in articles:
            tous_les_articles.append({**article, "source": nom})

    if not tous_les_articles:
        if logger:
            logger.info("❌ Aucun article trouvé")
        else:
            print("❌ Aucun article trouvé")
        return []

    if logger:
        logger.info(f"📚 {len(tous_les_articles)} articles à traiter...")
    else:
        print(f"📚 {len(tous_les_articles)} articles à traiter...")

    content = "\n\n".join([
        f"[{i+1}] ({a['source']}) {a['title']}\n{a['summary'][:200]}"
        for i, a in enumerate(tous_les_articles)
    ])

    try:
        response = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            temperature=0,
            max_tokens=100,
            messages=[
                {
                    "role": "system",
                    "content": "Tu réponds UNIQUEMENT avec une liste de numéros d'articles séparés par des virgules. Ex: 1,3,5,7"
                },
                {
                    "role": "user",
                    "content": f"""Sélectionne les 4 articles les plus importants pour un étudiant en économie-gestion.

Retourne JUSTE les numéros séparés par des virgules, rien d'autre.

Articles:
{content}"""
                }
            ]
        )

        raw = response.choices[0].message.content.strip()
        if logger:
            logger.info(f"🔍 Réponse brute de Groq: '{raw}'")
        else:
            print(f"🔍 Réponse brute de Groq: '{raw}'")

        # Parser robuste: cherche tous les nombres
        numeros = []
        matches = re.findall(r'\d+', raw)
        for match in matches:
            idx = int(match) - 1
            if 0 <= idx < len(tous_les_articles):
                numeros.append(idx)

        if logger:
            logger.info(f"✅ Articles sélectionnés: {[i+1 for i in numeros[:4]]}")
        else:
            print(f"✅ Articles sélectionnés: {[i+1 for i in numeros[:4]]}")
        return [tous_les_articles[i] for i in numeros[:4]]

    except Exception as e:
        if logger:
            logger.error(f"❌ Erreur Groq: {e}")
        else:
            print(f"❌ Erreur Groq: {e}")
        return []


def generate_resume(article, logger=None):
    """Génère 2-3 phrases de résumé via Groq (sans préambule)"""
    client = Groq(api_key=GROQ_API_KEY)
    
    try:
        if logger:
            logger.info(f"✍️  Génération résumé pour: {article.get('title')[:80]}")
        response = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            temperature=0.2,
            max_tokens=200,  # Augmenté pour éviter les coupures
            messages=[
                {
                    "role": "system",
                    "content": "IMPORTANT: Réponds UNIQUEMENT avec 2-3 phrases de résumé. ZÉRO préambule, ZÉRO introduction, ZÉRO explication. Juste le texte brut."
                },
                {
                    "role": "user",
                    "content": f"""Titre: {article['title']}

Contenu:
{article['summary'][:600]}

Résume en 2-3 phrases simples et directes."""
                }
            ]
        )
        
        raw = response.choices[0].message.content.strip()
        
        # Nettoyer les réponses parasites communes
        phrases_a_enlever = [
            r"^Voici.*?:\s*",
            r"^Résumé.*?:\s*",
            r"^En résumé.*?:\s*",
            r"^Article.*?:\s*",
            r"^Ce.*?parle de.*?:\s*",
            r"^\*\*[^*]+\*\*\s*",  # Texte en bold markdown
        ]
        
        for pattern in phrases_a_enlever:
            raw = re.sub(pattern, "", raw, flags=re.IGNORECASE)
        
        # Enlever les tirets ou points d'énumération au début
        raw = re.sub(r"^[-•*]\s*", "", raw)
        
        return raw.strip()
    
    except Exception as e:
        if logger:
            logger.error(f"⚠️  Erreur résumé: {e}")
        else:
            print(f"⚠️  Erreur résumé: {e}")
        # Fallback : premiers 150 caractères du contenu original
        return (article['summary'][:150] + "...").replace("<br>", " ").replace("<p>", "").replace("</p>", "")


def send_email(resultats, sender=None, password=None, recipients=None, logger=None):
    """Envoie l'email en itérant sur chaque destinataire avec un délai optionnel.

    - `recipients` attend une liste d'adresses.
    - `delay_between` en secondes entre chaque envoi individuel.
    - `logger` doit implémenter `info()` et `error()`.
    """
    if logger is None:
        logger = SimpleLogger()

    if not resultats:
        logger.info("⚠️  Pas d'articles à envoyer")
        return

    if sender is None or password is None or recipients is None:
        logger.error("❌ Paramètres d'email manquants")
        return

    # Construire le HTML commun
    if logger:
        logger.info(f"🧩 Construction du HTML pour {len(resultats)} articles")
    html = "<html><body><h2>📰 Articles essentiels du jour</h2><hr>"
    for i, article in enumerate(resultats, 1):
        resume = generate_resume(article, logger=logger)
        html += f"""
        <p>
            <strong>[{i}] {article['title']}</strong><br>
            <small style=\"color: #666;\">Source: {article['source']}</small><br>
            <p style=\"margin: 10px 0; line-height: 1.5;\">{resume}</p>
            <a href=\"{article['link']}\" style=\"color: #0066cc; text-decoration: none;\">→ Lire l'article complet</a>
        </p>
        <hr>
        """
    html += "</body></html>"

    # Envoi individualisé
    if logger:
        logger.info(f"🔐 Expéditeur: {sender[:3]}*** (mot de passe {'ok' if password else 'vide'}) | Destinataires: {recipients}")
    for idx, dest in enumerate(recipients, 1):
        msg = MIMEMultipart("alternative")
        msg["Subject"] = "📰 Veille académique - Économie & Gestion"
        msg["From"] = sender
        msg["To"] = dest
        msg.attach(MIMEText(html, "html"))

        try:
            if logger:
                logger.info(f"🔌 Tentative connexion SMTP pour {dest} ({idx}/{len(recipients)})")
            with smtplib.SMTP_SSL("smtp.gmail.com", 465, timeout=20) as server:
                server.login(sender, password)
                if logger:
                    logger.info("🔑 Authentification SMTP réussie")
                server.sendmail(sender, [dest], msg.as_string())
                logger.info(f"✉️  Email envoyé à {dest} ({idx}/{len(recipients)})")
        except Exception as e:
            logger.error(f"❌ Erreur email pour {dest}: {e}")


# --- Main ---
def run_watch(sender, password, recipients_csv, groq_api_key=None, newsapi_key=None, keywords=None, logger=None):
    """Point d'entrée utilisable depuis une interface.

    - `recipients_csv`: chaîne avec adresses séparées par des virgules.
    - `delay_between`: secondes entre chaque envoi individuel.
    - `logger`: objet optionnel pour collecter logs.
    """
    if logger is None:
        logger = SimpleLogger()

    # Mettre à jour les variables globales utilisées par les fonctions existantes
    global EMAIL_EXPEDITEUR, EMAIL_MOT_DE_PASSE, DESTINATAIRES, GROQ_API_KEY, NEWSAPI_KEY, MOTS_CLES
    EMAIL_EXPEDITEUR = sender or EMAIL_EXPEDITEUR
    EMAIL_MOT_DE_PASSE = password or EMAIL_MOT_DE_PASSE
    DESTINATAIRES = [e.strip() for e in recipients_csv.split(",") if e.strip()]
    if groq_api_key:
        GROQ_API_KEY = groq_api_key
    if newsapi_key:
        NEWSAPI_KEY = newsapi_key
    if keywords:
        MOTS_CLES = keywords

    logger.info("🚀 Démarrage de la veille (depuis interface)")
    try:
        articles_par_sujet = fetch_articles(logger=logger)
    except Exception as e:
        logger.error(f"❌ Erreur récupération articles: {e}")
        return

    if not articles_par_sujet:
        logger.error("❌ Aucun flux accessible")
        return

    try:
        resultats = summarize_with_groq(articles_par_sujet, logger=logger)
    except Exception as e:
        logger.error(f"❌ Erreur pendant le résumé Groq: {e}")
        return

    if resultats:
        try:
            send_email(resultats, sender=EMAIL_EXPEDITEUR, password=EMAIL_MOT_DE_PASSE, recipients=DESTINATAIRES, logger=logger)
        except Exception as e:
            logger.error(f"❌ Erreur lors de l'envoi des emails: {e}")
    else:
        logger.info("⚠️  Groq n'a rien sélectionné")


if __name__ == "__main__":
    # Comportement historique quand on lance le script directement
    logger = SimpleLogger()
    run_watch(EMAIL_EXPEDITEUR, EMAIL_MOT_DE_PASSE, ",".join(DESTINATAIRES), groq_api_key=GROQ_API_KEY, newsapi_key=NEWSAPI_KEY, logger=logger)
