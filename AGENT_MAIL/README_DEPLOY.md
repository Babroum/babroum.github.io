Déploiement rapide sur Render

1) Crée un compte sur https://render.com et connecte ton dépôt GitHub.
2) Dans Render : New -> Web Service -> choisis ton repo et la branche (main).
3) Défini le `Root Directory` sur `S2.06-agentMail/AGENT_MAIL` (important).
4) Build Command: `pip install -r requirements.txt`
5) Start Command: `gunicorn -w 4 app:app` (le `Procfile` fourni est utilisé automatiquement par Render)
6) Ajoute les variables d'environnement dans le dashboard Render: `EMAIL_EXPEDITEUR`, `EMAIL_MOT_DE_PASSE`, `GROQ_API_KEY`, `NEWSAPI_KEY`.

Après ça, chaque push sur la branche déclenchera un nouveau déploiement automatique.

Autres options:
- Railway: procédure similaire (connecte repo, répertoire racine, start command).
- PythonAnywhere: tu peux téléverser les fichiers et définir le WSGI app path.

Veux-tu que je crée aussi un workflow GitHub Actions qui déclenche un deploy via l'API Render (nécessite `RENDER_SERVICE_ID` + `RENDER_API_KEY` secrets) ?