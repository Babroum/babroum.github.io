# 🚀 Déploiement Agent Mail sur Render.com

Guide complet pour déployer ton interface Agent Mail sur Render.com gratuitement.

---

## 📋 Prérequis

- Compte GitHub (gratuit)
- Compte Render.com (gratuit)
- Les fichiers du projet :
  - `server.js`
  - `package.json`
  - `mail-agent.html`
  - `mail-agent.css`
  - `mail-agent.js`

---

## 1️⃣ Préparer le dépôt GitHub

### A. Créer un dépôt

1. Ouvre https://github.com/new
2. Nom : `agent-mail` (ou ce que tu veux)
3. Cochle "Public"
4. Crée le dépôt

### B. Uploader les fichiers

Depuis GitHub :
```
1. Cliquez "Add file" → "Upload files"
2. Sélectionnez les 5 fichiers
3. Commit avec le message "Initial commit"
```

Ou en ligne de commande :
```bash
git clone https://github.com/VOTRE_USER/agent-mail.git
cd agent-mail
# Copier les fichiers dans ce dossier
git add .
git commit -m "Initial commit"
git push origin main
```

---

## 2️⃣ Déployer sur Render.com

### A. Créer un compte Render

1. Va sur https://render.com
2. Sign up avec GitHub (plus simple)
3. Autorise l'accès à tes repos

### B. Créer un service Web

1. Dashboard → "Create" → "Web Service"
2. Sélectionne `agent-mail` repository
3. Clique "Connect"

### C. Configuration du service

| Champ | Valeur |
|-------|--------|
| Name | `agent-mail` |
| Environment | `Node` |
| Build Command | `npm install` |
| Start Command | `npm start` |
| Instance Type | `Free` (ou Starter si besoin) |

4. Clique "Deploy Web Service"

⏳ **Attends 2-5 minutes le build**

### D. C'est prêt !

Tu verras : `https://agent-mail-xxxx.onrender.com` ✓

**Important** : La première requête peut être lente (démarrage du serveur gratuit), c'est normal.

---

## 3️⃣ Utiliser l'interface

### Accès

```
https://agent-mail-xxxx.onrender.com
```

Remplace `agent-mail-xxxx` par ton URL réelle

### Configuration

1. **Email expéditeur** :
   - Rentre ton adresse Gmail
   - Mot de passe d'application (16 chars)

2. **Destinataires** :
   - Ajoute les emails qui reçoivent la veille

3. **Horaire** :
   - Choisis l'heure d'envoi automatique
   - L'intervalle en jours (1 = chaque jour)

4. **Sauvegarde** :
   - Clique "Sauvegarder"
   - Teste la connexion avec le bouton "Test"

---

## 4️⃣ Dépannage

### ❌ "Error: 502 Bad Gateway"

**Cause** : Le serveur s'est écrasé ou le build a échoué

**Solution** :
1. Regarde les logs (Dashboard → Logs)
2. Vérifie que `package.json` existe
3. Reconstruis : "Rebuild latest" dans Render

### ❌ "Cannot find module 'express'"

**Cause** : npm install n'a pas runné

**Solution** :
1. Render → "Rebuild latest"
2. Attends le build complet

### ❌ "Email test fails"

**Cause** : Mot de passe invalide

**Solution** :
1. Génère un **mot de passe d'application** : https://myaccount.google.com/apppasswords
2. Sélectionne "Mail" + "Windows"
3. Copie exactement le mot de passe (16 chars)
4. Paste dans l'interface

### ❌ "Scheduler ne fonctionne pas"

**Cause** : Render.com libre = peut s'endormir après 15min d'inactivité

**Solution** :
- Upgrade vers "Starter" (environ $7/mois) ou
- Envoie un email manuellement avec "Envoyer maintenant"

---

## 5️⃣ Améliorations (optionnel)

### Ajouter une base de données

Si tu veux sauvegarder l'historique d'envois, ajoute PostgreSQL gratuit :

1. Render → Create → PostgreSQL
2. Copie les credentials
3. Mise à jour `server.js` avec `pg` package

### Custom domain

1. Render Dashboard → Settings
2. "Custom Domain"
3. Ajoute `agent.tondomaine.com`

### Variables d'environnement

Pour sécuriser les secrets (optionnel) :

1. Render → Web Service → Environment
2. `DATABASE_URL`, `SECRET_KEY`, etc.
3. Utilise `process.env.DATABASE_URL` dans le code

---

## 6️⃣ Monitorage

### Vérifier que ça tourne

```bash
curl https://agent-mail-xxxx.onrender.com
```

Doit retourner le HTML

### Logs en temps réel

Dashboard → "Logs" (onglet en haut à droite)

---

## 📊 Structure finale

```
agent-mail/
├── server.js              ← Backend Node.js
├── package.json           ← Dépendances
├── mail-agent.html        ← Interface
├── mail-agent.css         ← Styles
├── mail-agent.js          ← Frontend logic
└── mail_config.json       ← Config générée auto
```

---

## 🔒 Sécurité

⚠️ **Attention** : Sur Render gratuit, les fichiers disques (`mail_config.json`) sont effacés à chaque redémarrage.

**Solution** :
- Utilise localStorage (sauvegarde local navigateur) ✓ (déjà fait)
- Ou upgrade vers une instance persistante

---

## 💡 Tips

**Reload auto après changement** :
```
Render → Auto-Deploy → "On"
```

Quand tu push sur GitHub, le code se redéploie automatiquement.

**Garder le serveur actif** :
Upgrade vers "Starter" ($7/mois) ou utilise un service comme https://www.freshping.io pour des pings réguliers.

---

## 📞 Support

- Erreurs Render → https://status.render.com
- Docs Node → https://nodejs.org/docs
- Docs Render → https://render.com/docs

---

🎉 Bravo ! Ton Agent Mail est déployé ! 🎉

Envoie des veilles automatiques depuis le cloud ☁️
