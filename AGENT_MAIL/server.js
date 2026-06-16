import express from 'express';
import cors from 'cors';
import nodemailer from 'nodemailer';
import fs from 'fs';
import path from 'path';
import { fileURLToPath } from 'url';
import cron from 'node-cron';
import { spawn } from 'child_process';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

const app = express();
const PORT = process.env.PORT || 3000;

// Middleware
app.use(cors());
app.use(express.json());
app.use(express.static(__dirname));

// ==========================================
// DONNÉES PERSISTANTES
// ==========================================
const CONFIG_FILE = path.join(__dirname, 'mail_config.json');
let mailConfig = null;
let cronJob = null;

// État interne de l'agent (pour la UI)
let agentState = {
    running: false,
    lastRunAt: null,
    lastRunStatus: null, // 'success' | 'error'
    lastRunMessage: '',
    logs: []
};

function pushLog(msg, level = 'info') {
    const entry = { ts: new Date().toISOString(), level, msg };
    agentState.logs.push(entry);
    if (agentState.logs.length > 200) agentState.logs.shift();
    console.log(`[${level.toUpperCase()}] ${msg}`);
    // Notifier les clients SSE
    sseClients.forEach(res => {
        res.write(`data: ${JSON.stringify(entry)}\n\n`);
    });
}

function loadConfig() {
    try {
        if (fs.existsSync(CONFIG_FILE)) {
            mailConfig = JSON.parse(fs.readFileSync(CONFIG_FILE, 'utf-8'));
        }
    } catch (e) {
        console.error('Erreur lecture config:', e);
    }
}

function saveConfig(config) {
    try {
        fs.writeFileSync(CONFIG_FILE, JSON.stringify(config, null, 2));
        mailConfig = config;
    } catch (e) {
        console.error('Erreur sauvegarde config:', e);
    }
}

// ==========================================
// SSE — LOGS EN TEMPS RÉEL
// ==========================================
const sseClients = new Set();

app.get('/api/logs/stream', (req, res) => {
    res.setHeader('Content-Type', 'text/event-stream');
    res.setHeader('Cache-Control', 'no-cache');
    res.setHeader('Connection', 'keep-alive');
    res.flushHeaders();

    // Envoyer l'historique récent
    agentState.logs.slice(-50).forEach(entry => {
        res.write(`data: ${JSON.stringify(entry)}\n\n`);
    });

    sseClients.add(res);
    req.on('close', () => sseClients.delete(res));
});

// ==========================================
// LANCEMENT DU SCRIPT PYTHON
// ==========================================
function runPythonAgent(config) {
    return new Promise((resolve, reject) => {
        if (agentState.running) {
            reject(new Error('Un envoi est déjà en cours, veuillez patienter.'));
            return;
        }

        agentState.running = true;
        pushLog('🚀 Démarrage de la veille…');

        const env = {
            ...process.env,
            EMAIL_EXPEDITEUR: config.senderEmail,
            EMAIL_MOT_DE_PASSE: config.appPassword,
            DESTINATAIRES: config.recipients.join(','),
            GROQ_API_KEY: config.groqApiKey || process.env.GROQ_API_KEY || '',
            NEWSAPI_KEY: config.newsApiKey || process.env.NEWSAPI_KEY || '',
        };

        const scriptPath = path.join(__dirname, 'groq_fixed.py');
        const py = spawn('python3', [scriptPath], { env });

        let stderr = '';

        py.stdout.on('data', data => {
            data.toString().split('\n').filter(Boolean).forEach(line => pushLog(line, 'info'));
        });

        py.stderr.on('data', data => {
            const text = data.toString();
            stderr += text;
            text.split('\n').filter(Boolean).forEach(line => pushLog(line, 'error'));
        });

        py.on('error', err => {
            agentState.running = false;
            agentState.lastRunStatus = 'error';
            agentState.lastRunMessage = `Impossible de lancer python3 : ${err.message}`;
            agentState.lastRunAt = new Date().toISOString();
            pushLog(`❌ ${agentState.lastRunMessage}`, 'error');
            reject(new Error(agentState.lastRunMessage));
        });

        py.on('close', code => {
            agentState.running = false;
            agentState.lastRunAt = new Date().toISOString();

            if (code === 0) {
                agentState.lastRunStatus = 'success';
                agentState.lastRunMessage = 'Veille envoyée avec succès ✓';
                pushLog(`✅ ${agentState.lastRunMessage}`, 'info');
                resolve(agentState.lastRunMessage);
            } else {
                agentState.lastRunStatus = 'error';
                agentState.lastRunMessage = `Le script s'est terminé avec le code ${code}`;
                pushLog(`❌ ${agentState.lastRunMessage}`, 'error');
                reject(new Error(agentState.lastRunMessage));
            }
        });
    });
}

// ==========================================
// ROUTES API
// ==========================================

// 0. Valeurs par défaut depuis les variables d'environnement Render
app.get('/api/env-defaults', (req, res) => {
    res.json({
        senderEmail:  process.env.EMAIL_EXPEDITEUR  || '',
        // On ne renvoie jamais le mot de passe en clair dans la réponse,
        // mais on indique s'il est défini côté serveur pour pré-remplir le placeholder
        appPasswordSet: !!(process.env.EMAIL_MOT_DE_PASSE),
        groqApiKey:   process.env.GROQ_API_KEY   || '',
        newsApiKey:   process.env.NEWSAPI_KEY     || '',
    });
});

// 1. Sauvegarder la configuration
app.post('/api/config', (req, res) => {
    try {
        const config = req.body;
        if (!config.senderEmail || !config.appPassword || !Array.isArray(config.recipients) || config.recipients.length === 0) {
            return res.status(400).json({ message: 'Configuration incomplète' });
        }
        saveConfig(config);
        setupScheduler(config);
        res.json({ message: 'Configuration sauvegardée', success: true });
    } catch (e) {
        res.status(500).json({ message: e.message });
    }
});

// 2. Test de connexion email (nodemailer SMTP verify)
app.post('/api/test-email', async (req, res) => {
    try {
        const { senderEmail, appPassword } = req.body;
        if (!senderEmail || !appPassword) {
            return res.status(400).json({ message: 'Email et mot de passe requis' });
        }
        const transporter = nodemailer.createTransport({
            service: 'gmail',
            auth: { user: senderEmail, pass: appPassword }
        });
        await transporter.verify();
        res.json({ message: 'Connexion SMTP vérifiée avec succès ✓' });
    } catch (e) {
        res.status(401).json({ message: 'Erreur authentification Gmail : ' + (e.message || 'Vérifiez vos identifiants') });
    }
});

// 3. Lancer la veille maintenant (Python → Groq → email)
app.post('/api/send-now', async (req, res) => {
    try {
        const config = req.body;
        if (!config.senderEmail || !config.appPassword || !config.recipients?.length) {
            return res.status(400).json({ message: 'Configuration incomplète' });
        }
        // Répondre immédiatement, le travail tourne en arrière-plan
        res.json({ message: 'Veille lancée — suivez les logs en temps réel ⏳', async: true });
        runPythonAgent(config).catch(err => {
            pushLog(`❌ Erreur background: ${err.message}`, 'error');
        });
    } catch (e) {
        res.status(500).json({ message: e.message });
    }
});

// 4. Statut de l'agent
app.get('/api/status', (req, res) => {
    res.json(agentState);
});

// 5. Historique des logs (snapshot)
app.get('/api/logs', (req, res) => {
    res.json(agentState.logs.slice(-100));
});

// 6. Récupérer la configuration sauvegardée
app.get('/api/config', (req, res) => {
    res.json(mailConfig || null);
});

// ==========================================
// SCHEDULER CRON
// ==========================================
function setupScheduler(config) {
    if (cronJob) { cronJob.stop(); cronJob = null; }

    if (!config.enableSchedule || !config.sendTime) {
        pushLog('ℹ️  Scheduler désactivé');
        return;
    }

    const [hours, minutes] = config.sendTime.split(':');
    const cronExpr = `${minutes} ${hours} * * *`;

    cronJob = cron.schedule(cronExpr, () => {
        pushLog(`⏰ Envoi automatique déclenché (${config.sendTime})`);
        runPythonAgent(config).catch(e => pushLog(`❌ Envoi auto échoué : ${e.message}`, 'error'));
    });

    pushLog(`✅ Scheduler activé : ${cronExpr} (${config.sendTime})`);
}

// ==========================================
// SERVEUR STATIQUE
// ==========================================
app.get('/', (req, res) => {
    res.sendFile(path.join(__dirname, 'mail-agent.html'));
});

// ==========================================
// DÉMARRAGE
// ==========================================
loadConfig();
if (mailConfig?.enableSchedule) setupScheduler(mailConfig);

app.listen(PORT, () => {
    console.log(`🚀 Agent Mail démarré sur le port ${PORT}`);
});

// Arrêt gracieux
process.on('SIGTERM', () => {
    if (cronJob) cronJob.stop();
    process.exit(0);
});

// Empêcher le crash total sur exception non gérée
process.on('uncaughtException', err => {
    pushLog(`💥 Exception non gérée: ${err.message}`, 'error');
    // on ne quitte PAS — le serveur reste en ligne
});

process.on('unhandledRejection', reason => {
    pushLog(`💥 Promise rejetée: ${reason}`, 'error');
});
