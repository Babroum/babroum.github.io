import express from 'express';
import cors from 'cors';
import nodemailer from 'nodemailer';
import fs from 'fs';
import path from 'path';
import { fileURLToPath } from 'url';
import cron from 'node-cron';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

const app = express();
const PORT = process.env.PORT || 3000;

// Middleware
app.use(cors());
app.use(express.json());
app.use(express.static(__dirname));

// Données persistantes
const CONFIG_FILE = 'mail_config.json';
let mailConfig = null;
let cronJob = null;

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

// Fonction pour envoyer un email
async function sendVeilleEmail(config) {
    if (!config || !config.senderEmail || !config.recipients.length) {
        throw new Error('Configuration incomplète');
    }

    const transporter = nodemailer.createTransport({
        service: 'gmail',
        auth: {
            user: config.senderEmail,
            pass: config.appPassword
        }
    });

    const html = `
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="UTF-8">
            <style>
                body { font-family: Arial, sans-serif; background: #1a1a1a; color: #e0e0e0; }
                .container { max-width: 600px; margin: 0 auto; padding: 20px; background: rgba(42,42,42,0.5); border-radius: 8px; }
                h1 { color: #87CEEB; margin-bottom: 20px; }
                .article { background: rgba(58,58,58,0.3); padding: 16px; margin: 16px 0; border-left: 3px solid #87CEEB; border-radius: 4px; }
                .article h2 { font-size: 16px; color: #87CEEB; margin: 0 0 8px 0; }
                .article p { margin: 0; font-size: 14px; color: #d0d0d0; }
                .footer { margin-top: 30px; padding-top: 16px; border-top: 1px solid rgba(58,58,58,0.3); font-size: 12px; color: #8a8a8a; }
            </style>
        </head>
        <body>
            <div class="container">
                <h1>📰 Veille Économie & Gestion</h1>
                <p>Bonjour,</p>
                <p>Voici votre veille automatique du jour. Les articles les plus pertinents sur l'économie et la gestion sont ci-dessous.</p>
                
                <div class="article">
                    <h2>Article 1 : Exemple</h2>
                    <p>Contenu de l'article placeholder.</p>
                </div>

                <div class="article">
                    <h2>Article 2 : Exemple</h2>
                    <p>Contenu de l'article placeholder.</p>
                </div>

                <div class="footer">
                    <p>Cet email a été envoyé automatiquement par votre Agent Mail. <a href="https://your-render-url.onrender.com" style="color: #87CEEB;">Configurer</a></p>
                </div>
            </div>
        </body>
        </html>
    `;

    const mailOptions = {
        from: config.senderEmail,
        to: config.recipients.join(','),
        subject: '📰 Veille Économie & Gestion',
        html: html
    };

    await transporter.sendMail(mailOptions);
}

// Routes API

// 1. Sauvegarder la configuration
app.post('/api/config', (req, res) => {
    try {
        const config = req.body;

        // Validation basique
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

// 2. Test de connexion email
app.post('/api/test-email', async (req, res) => {
    try {
        const { senderEmail, appPassword } = req.body;

        if (!senderEmail || !appPassword) {
            return res.status(400).json({ message: 'Email et mot de passe requis' });
        }

        const transporter = nodemailer.createTransport({
            service: 'gmail',
            auth: {
                user: senderEmail,
                pass: appPassword
            }
        });

        await transporter.verify();
        res.json({ message: 'Connexion SMTP vérifiée avec succès ✓' });
    } catch (e) {
        console.error('Test email error:', e);
        res.status(401).json({ message: 'Erreur authentification Gmail : ' + (e.message || 'Vérifiez vos identifiants') });
    }
});

// 3. Envoyer maintenant
app.post('/api/send-now', async (req, res) => {
    try {
        const config = req.body;

        if (!config.senderEmail || !config.recipients.length) {
            return res.status(400).json({ message: 'Configuration incomplète' });
        }

        await sendVeilleEmail(config);
        res.json({ message: `Email envoyé à ${config.recipients.length} destinataire(s) ✓` });
    } catch (e) {
        console.error('Send email error:', e);
        res.status(500).json({ message: 'Erreur envoi email: ' + e.message });
    }
});

// 4. Récupérer la configuration
app.get('/api/config', (req, res) => {
    if (mailConfig) {
        res.json(mailConfig);
    } else {
        res.json(null);
    }
});

// Setup du scheduler
function setupScheduler(config) {
    // Arrêter l'ancien job
    if (cronJob) {
        cronJob.stop();
    }

    if (!config.enableSchedule || !config.sendTime) {
        console.log('Scheduler désactivé');
        return;
    }

    const [hours, minutes] = config.sendTime.split(':');

    // Cron format: minute hour * * *
    const cronExpression = `${minutes} ${hours} * * *`;

    cronJob = cron.schedule(cronExpression, async () => {
        console.log(`[${new Date().toISOString()}] Envoi automatique déclenché`);
        try {
            await sendVeilleEmail(config);
            console.log('[OK] Email envoyé avec succès');
        } catch (e) {
            console.error('[ERROR] Erreur envoi automatique:', e.message);
        }
    });

    console.log(`✓ Scheduler activé: ${cronExpression} (${config.sendTime})`);
}

// Servir les fichiers statiques
app.get('/', (req, res) => {
    res.sendFile(path.join(__dirname, 'mail-agent.html'));
});

// Démarrage du serveur
loadConfig();
if (mailConfig && mailConfig.enableSchedule) {
    setupScheduler(mailConfig);
}

app.listen(PORT, () => {
    console.log(`🚀 Agent Mail démarré sur le port ${PORT}`);
    console.log(`📍 Accédez à http://localhost:${PORT}`);
});

// Gestion arrêt gracieux
process.on('SIGTERM', () => {
    console.log('Arrêt gracieux...');
    if (cronJob) cronJob.stop();
    process.exit(0);
});
