import feedparser
import smtplib
import sys
import os
import re
import requests
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

# dotenv optionnel
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

# ==========================================
# IMPORTS LLM — Gemini (priorité) + Groq (fallback)
# ==========================================
GEMINI_OK = False
GROQ_OK   = False

try:
    from google import genai
    GEMINI_OK = True
except ImportError:
    pass  # géré dans run_watch

try:
    from groq import Groq
    GROQ_OK = True
except ImportError:
    pass  # géré dans run_watch

# ==========================================
# CONFIG — tout depuis les variables d'env
# ==========================================
EMAIL_EXPEDITEUR   = os.environ.get("EMAIL_EXPEDITEUR", "")
EMAIL_MOT_DE_PASSE = os.environ.get("EMAIL_MOT_DE_PASSE", "")
GEMINI_API_KEY     = os.environ.get("GEMINI_API_KEY", "")
GROQ_API_KEY       = os.environ.get("GROQ_API_KEY", "")
NEWSAPI_KEY        = os.environ.get("NEWSAPI_KEY", "")
DISABLE_EMAIL = os.environ.get("DISABLE_EMAIL", "false").lower() == "true"
NEWSAPI_URL        = "https://newsapi.org/v2/everything"

_dest_env     = os.environ.get("DESTINATAIRES", "")
DESTINATAIRES = [e.strip() for e in _dest_env.split(",") if e.strip()] or [""]

FEEDS_RSS = [
    ("EducPros",            "https://www.letudiant.fr/educpros/rss.xml"),
    ("Le Monde Éco",        "https://www.lemonde.fr/economie/rss_full.xml"),
    ("Les Échos",           "https://www.lesechos.fr/rss/rss_une.xml"),
    ("The Conversation FR", "https://theconversation.com/fr/articles.atom"),
    ("Cadremploi Actus",    "https://www.cadremploi.fr/rss/actualites.xml"),
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


# ==========================================
# LOGGER SIMPLE
# ==========================================
class SimpleLogger:
    def __init__(self, file_path=None):
        self.lines     = []
        self.file_path = file_path

    def _write_file(self, line):
        if not self.file_path:
            return
        try:
            with open(self.file_path, 'a', encoding='utf-8') as f:
                f.write(line + '\n')
        except Exception:
            pass

    def info(self, msg):
        text = str(msg)
        print(text, flush=True)
        self.lines.append(text)
        from datetime import datetime, timezone
        self._write_file(f"[INFO] {datetime.now(timezone.utc).isoformat()} {text}")

    def error(self, msg):
        text = str(msg)
        print(text, flush=True, file=sys.stderr)
        self.lines.append(text)
        from datetime import datetime, timezone
        self._write_file(f"[ERROR] {datetime.now(timezone.utc).isoformat()} {text}")

    def get_lines(self, max_lines=200):
        if self.file_path:
            try:
                with open(self.file_path, 'r', encoding='utf-8') as f:
                    return [l.rstrip('\n') for l in f.readlines()][-max_lines:]
            except Exception:
                pass
        return self.lines[-max_lines:]


# ==========================================
# COUCHE LLM UNIFIÉE : Gemini → Groq fallback
# ==========================================
class LLMClient:
    """
    Appelle Gemini en priorité.
    Si Gemini échoue (quota, erreur réseau, indisponible),
    bascule automatiquement sur Groq pour cet appel.
    """

    GEMINI_MODEL = "gemini-2.5-flash"
    GROQ_MODEL   = "llama-3.3-70b-versatile"

    def __init__(self, gemini_key, groq_key, logger):
        self.logger     = logger
        self.groq_key   = groq_key
        self._groq      = None

        # Initialiser Gemini
        self._gemini_ok = False
        if gemini_key and GEMINI_OK:
            try:
                self._gemini_client = genai.Client(api_key=gemini_key)
                self._gemini_ok    = True
                logger.info(f"✅ LLM principal : Gemini ({self.GEMINI_MODEL})")
            except Exception as e:
                logger.error(f"⚠️  Gemini init échouée : {e} — fallback Groq")
        else:
            if not gemini_key:
                logger.info("ℹ️  GEMINI_API_KEY absente — utilisation directe de Groq")
            elif not GEMINI_OK:
                logger.error("⚠️  Package 'google-generativeai' non installé — fallback Groq")

        # Initialiser Groq (toujours, pour le fallback)
        if groq_key and GROQ_OK:
            try:
                self._groq = Groq(api_key=groq_key)
                logger.info(f"✅ LLM fallback : Groq ({self.GROQ_MODEL})")
            except Exception as e:
                logger.error(f"⚠️  Groq init échouée : {e}")

        if not self._gemini_ok and not self._groq:
            logger.error("❌ Aucun LLM disponible (Gemini + Groq tous les deux KO)")
            sys.exit(1)

    def _call_gemini(self, system_prompt, user_prompt):
        """Appel Gemini avec la nouvelle API SDK google-genai"""
        full_prompt = f"{system_prompt}\n\n{user_prompt}"
        
        # Nouvelle syntaxe pour générer du contenu
        response = self._gemini_client.models.generate_content(
            model=self.GEMINI_MODEL,
            contents=full_prompt,
        )
        return response.text.strip()

    def _call_groq(self, system_prompt, user_prompt, max_tokens=200):
        """Appel Groq — lève une exception si ça rate."""
        resp = self._groq.chat.completions.create(
            model=self.GROQ_MODEL,
            temperature=0.2,
            max_tokens=max_tokens,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user",   "content": user_prompt},
            ]
        )
        return resp.choices[0].message.content.strip()

    def complete(self, system_prompt, user_prompt, max_tokens=200, label="LLM"):
        """
        Essaie Gemini, bascule sur Groq si Gemini échoue.
        Retourne le texte généré ou lève une exception si les deux ratent.
        """
        # Tentative Gemini
        if self._gemini_ok:
            try:
                result = self._call_gemini(system_prompt, user_prompt)
                return result
            except Exception as e:
                err_msg = str(e)
                # Détecter quota / rate-limit / indisponibilité
                if any(k in err_msg for k in ["429", "quota", "RESOURCE_EXHAUSTED",
                                               "503", "unavailable", "overloaded"]):
                    self.logger.error(f"⚠️  [{label}] Gemini quota/indispo : {err_msg[:120]} → fallback Groq")
                else:
                    self.logger.error(f"⚠️  [{label}] Gemini erreur : {err_msg[:120]} → fallback Groq")

        # Fallback Groq
        if self._groq:
            try:
                result = self._call_groq(system_prompt, user_prompt, max_tokens)
                return result
            except Exception as e:
                raise RuntimeError(f"Groq aussi en erreur : {e}") from e

        raise RuntimeError("Aucun LLM disponible pour répondre.")


# ==========================================
# RÉCUPÉRATION ARTICLES
# ==========================================
def get_feeds_from_newsapi(logger):
    feeds   = []
    queries = [
        "économie France", "gestion entreprise", "master MBA France",
        "éducation supérieure", "finance business", "startups entrepreneuriat",
        "transformation digitale", "management RH",
    ]
    for query in queries:
        try:
            r = requests.get(NEWSAPI_URL, params={
                "q": query, "language": "fr", "sortBy": "publishedAt",
                "apiKey": NEWSAPI_KEY, "pageSize": 5
            }, timeout=10)
            if r.status_code == 200:
                data     = r.json()
                articles = data.get("articles", [])
                if articles:
                    feeds.append((f"NewsAPI: {query}", articles))
                    logger.info(f"✅ {len(articles)} articles pour '{query}'")
            else:
                logger.error(f"⚠️  NewsAPI HTTP {r.status_code} pour '{query}': {r.text[:100]}")
        except Exception as e:
            logger.error(f"⚠️  Erreur NewsAPI pour '{query}': {e}")
    return feeds


def get_feeds_from_rss(logger):
    articles_par_sujet = []
    for nom, url in FEEDS_RSS:
        try:
            feed     = feedparser.parse(url)
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
                logger.info(f"✅ {len(articles)} articles dans {nom}")
        except Exception as e:
            logger.error(f"⚠️  Erreur RSS {nom}: {e}")
    return articles_par_sujet


def fetch_articles(logger):
    logger.info("🔍 Récupération des articles...")
    articles_par_sujet = []

    if NEWSAPI_KEY:
        logger.info("📡 NewsAPI en cours...")
        newsapi_feeds = get_feeds_from_newsapi(logger)
        for nom, articles_list in newsapi_feeds:
            filtered = []
            for a in articles_list:
                texte = (a.get("title", "") + a.get("description", "")).lower()
                if any(mot in texte for mot in MOTS_CLES):
                    filtered.append({
                        "title":   a.get("title", ""),
                        "link":    a.get("url", ""),
                        "summary": a.get("description", "")
                    })
            if filtered:
                articles_par_sujet.append((nom, filtered[:4]))
    else:
        logger.info("⚠️  Pas de clé NewsAPI — utilisation des flux RSS")

    # Fallback RSS si NewsAPI vide
    if not articles_par_sujet:
        logger.info("📰 RSS en cours...")
        rss = get_feeds_from_rss(logger)
        articles_par_sujet.extend(rss)

    total = sum(len(a) for _, a in articles_par_sujet)
    logger.info(f"✅ Total : {total} articles collectés")

    if total == 0:
        logger.error("❌ Aucun article trouvé (NewsAPI + RSS tous vides)")
        sys.exit(1)

    return articles_par_sujet


# ==========================================
# SÉLECTION + RÉSUMÉ (via LLMClient)
# ==========================================
def select_articles(articles_par_sujet, llm, logger):
    tous = []
    for nom, arts in articles_par_sujet:
        for a in arts:
            tous.append({**a, "source": nom})

    logger.info(f"📚 {len(tous)} articles à trier...")

    content = "\n\n".join([
        f"[{i+1}] ({a['source']}) {a['title']}\n{a['summary'][:200]}"
        for i, a in enumerate(tous)
    ])

    system = "Tu réponds UNIQUEMENT avec une liste de numéros d'articles séparés par des virgules. Ex: 1,3,5,7"
    user   = (
        "Sélectionne les 4 articles les plus importants pour un étudiant en économie-gestion.\n"
        "Retourne JUSTE les numéros séparés par des virgules, rien d'autre.\n\n"
        f"Articles:\n{content}"
    )

    try:
        raw = llm.complete(system, user, max_tokens=100, label="sélection")
        logger.info(f"🔍 Sélection brute : '{raw}'")

        numeros = []
        for m in re.findall(r'\d+', raw):
            idx = int(m) - 1
            if 0 <= idx < len(tous):
                numeros.append(idx)

        selected = [tous[i] for i in numeros[:4]]
        logger.info(f"✅ {len(selected)} articles sélectionnés : {[i+1 for i in numeros[:4]]}")
        return selected

    except Exception as e:
        logger.error(f"❌ Sélection LLM échouée : {e} — fallback 4 premiers")
        return tous[:4]


def generate_resume(article, llm, logger):
    system = "IMPORTANT: Réponds UNIQUEMENT avec 2-3 phrases de résumé. ZÉRO préambule. Juste le texte brut."
    user   = (
        f"Titre: {article['title']}\n\n"
        f"Contenu:\n{article['summary'][:600]}\n\n"
        "Résume en 2-3 phrases simples et directes."
    )
    try:
        logger.info(f"✍️  Résumé : {str(article.get('title',''))[:70]}")
        raw = llm.complete(system, user, max_tokens=200, label="résumé")

        for pattern in [r"^Voici.*?:\s*", r"^Résumé.*?:\s*",
                        r"^En résumé.*?:\s*", r"^\*\*[^*]+\*\*\s*"]:
            raw = re.sub(pattern, "", raw, flags=re.IGNORECASE)
        raw = re.sub(r"^[-•*]\s*", "", raw)
        return raw.strip()

    except Exception as e:
        logger.error(f"⚠️  Résumé LLM échoué : {e} — fallback texte brut")
        return (article.get('summary', '')[:150] + "...") \
               .replace("<br>", " ").replace("<p>", "").replace("</p>", "")


# ==========================================
# ENVOI EMAIL
# ==========================================
def send_email(resultats, sender, password, recipients, llm, logger):
    if resultats:
        if DISABLE_EMAIL:
            logger.info("🚫 Mode Simulation actif : Envoi d'e-mail désactivé.")
            logger.info("📝 Les articles ont été sélectionnés et résumés par l'IA avec succès !")
            logger.info("✅ Veille terminée (Simulation).")
        else:
            send_email(
                resultats,
                sender=EMAIL_EXPEDITEUR,
                password=EMAIL_MOT_DE_PASSE,
                recipients=DESTINATAIRES,
                llm=llm,
                logger=logger
            )
            logger.info("✅ Veille terminée et envoyée avec succès")
    else:
        logger.error("⚠️  Aucun article sélectionné — email non envoyé")
        sys.exit(1)

    clean_pass = password.replace(" ", "") if password else ""

    logger.info(f"🧩 Construction HTML pour {len(resultats)} articles")
    html  = "<html><body style='font-family:Arial,sans-serif;max-width:600px;margin:0 auto;'>"
    html += "<h2 style='color:#1a1a2e;'>📰 Veille Économie &amp; Gestion</h2><hr>"

    for i, article in enumerate(resultats, 1):
        resume = generate_resume(article, llm, logger)
        title  = article['title'].replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')
        html  += f"""
        <div style='margin:16px 0;padding:16px;border-left:3px solid #0066cc;background:#f9f9f9;'>
            <strong>[{i}] {title}</strong><br>
            <small style='color:#666;'>Source : {article['source']}</small><br>
            <p style='margin:10px 0;line-height:1.6;'>{resume}</p>
            <a href='{article['link']}' style='color:#0066cc;'>→ Lire l'article complet</a>
        </div>"""

    html += "<hr><p style='color:#999;font-size:12px;'>Envoyé automatiquement par Agent Mail</p></body></html>"

    logger.info(f"🔐 Expéditeur : {sender[:4]}*** | {len(recipients)} destinataire(s) : {recipients}")

    for idx, dest in enumerate(recipients, 1):
        msg            = MIMEMultipart("alternative")
        msg["Subject"] = "📰 Veille académique - Économie & Gestion"
        msg["From"]    = sender
        msg["To"]      = dest
        msg.attach(MIMEText(html, "html"))

        try:
            logger.info(f"🔌 Connexion SMTP pour {dest} ({idx}/{len(recipients)})")
            with smtplib.SMTP_SSL("smtp.gmail.com", 465, timeout=30) as server:
                server.login(sender, clean_pass)
                logger.info("🔑 Authentification SMTP réussie")
                server.sendmail(sender, [dest], msg.as_string())
                logger.info(f"✉️  Email envoyé à {dest}")
        except smtplib.SMTPAuthenticationError:
            logger.error(
                f"❌ Authentification Gmail refusée pour {sender}.\n"
                "   → Vérifiez que la validation en 2 étapes est activée\n"
                "   → Utilisez un mot de passe d'application (16 chars) et non votre mot de passe habituel"
            )
            sys.exit(1)
        except Exception as e:
            logger.error(f"❌ Erreur SMTP pour {dest}: {e}")


# ==========================================
# POINT D'ENTRÉE PRINCIPAL
# ==========================================
def run_watch(sender=None, password=None, recipients_csv=None,
              gemini_api_key=None, groq_api_key=None,
              newsapi_key=None, keywords=None, logger=None):
    if logger is None:
        logger = SimpleLogger()

    global EMAIL_EXPEDITEUR, EMAIL_MOT_DE_PASSE, DESTINATAIRES
    global GEMINI_API_KEY, GROQ_API_KEY, NEWSAPI_KEY, MOTS_CLES

    if sender:         EMAIL_EXPEDITEUR   = sender
    if password:       EMAIL_MOT_DE_PASSE = password
    if recipients_csv:
        DESTINATAIRES = [e.strip() for e in recipients_csv.split(",") if e.strip()]
    if gemini_api_key: GEMINI_API_KEY = gemini_api_key
    if groq_api_key:   GROQ_API_KEY   = groq_api_key
    if newsapi_key:    NEWSAPI_KEY     = newsapi_key
    if keywords:       MOTS_CLES       = keywords

    # Vérifications obligatoires
    if not EMAIL_EXPEDITEUR:
        logger.error("❌ EMAIL_EXPEDITEUR manquant"); sys.exit(1)
    if not EMAIL_MOT_DE_PASSE:
        logger.error("❌ EMAIL_MOT_DE_PASSE manquant"); sys.exit(1)
    if not DESTINATAIRES:
        logger.error("❌ Aucun destinataire configuré"); sys.exit(1)
    if not GEMINI_API_KEY and not GROQ_API_KEY:
        logger.error("❌ Aucune clé LLM (GEMINI_API_KEY et GROQ_API_KEY toutes les deux manquantes)"); sys.exit(1)

    logger.info("🚀 Démarrage de la veille")
    logger.info(f"📧 Expéditeur    : {EMAIL_EXPEDITEUR[:4]}***")
    logger.info(f"👥 Destinataires : {DESTINATAIRES}")
    logger.info(f"🤖 Gemini key    : {'✓' if GEMINI_API_KEY else '✗'}")
    logger.info(f"🤖 Groq key      : {'✓ (fallback)' if GROQ_API_KEY else '✗'}")
    logger.info(f"📰 NewsAPI key   : {'✓' if NEWSAPI_KEY else '✗ (RSS fallback)'}")

    # Créer le client LLM unifié
    llm = LLMClient(
        gemini_key=GEMINI_API_KEY,
        groq_key=GROQ_API_KEY,
        logger=logger
    )

    articles_par_sujet = fetch_articles(logger)
    resultats          = select_articles(articles_par_sujet, llm, logger)

    if resultats:
        send_email(
            resultats,
            sender=EMAIL_EXPEDITEUR,
            password=EMAIL_MOT_DE_PASSE,
            recipients=DESTINATAIRES,
            llm=llm,
            logger=logger
        )
        logger.info("✅ Veille terminée avec succès")
    else:
        logger.error("⚠️  Aucun article sélectionné — email non envoyé")
        sys.exit(1)


if __name__ == "__main__":
    logger = SimpleLogger()
    run_watch(logger=logger)
