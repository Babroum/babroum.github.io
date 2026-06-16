// ==========================================
// 0. CONFIGURATION & UTILITAIRES
// ==========================================
const themeColor = '#87CEEB';
function hexToRgb(hex) {
    const r = parseInt(hex.slice(1, 3), 16);
    const g = parseInt(hex.slice(3, 5), 16);
    const b = parseInt(hex.slice(5, 7), 16);
    return `${r}, ${g}, ${b}`;
}
const themeRgb = hexToRgb(themeColor);
const API_URL = window.location.origin;

// ==========================================
// 1. GESTION DES DONNÉES
// ==========================================
let config = {
    senderEmail: '',
    appPassword: '',
    recipients: [],
    intervalDays: 1,
    sendTime: '08:00',
    enableSchedule: true,
    groqApiKey: '',
    newsApiKey: ''
};

function loadLocalConfig() {
    const stored = localStorage.getItem('mail_agent_config');
    if (stored) {
        try { config = { ...config, ...JSON.parse(stored) }; } catch (e) { }
    }
}

function saveLocalConfig() {
    localStorage.setItem('mail_agent_config', JSON.stringify(config));
}

loadLocalConfig();

// ==========================================
// 2. ÉLÉMENTS DOM
// ==========================================
const senderEmailInput       = document.getElementById('senderEmail');
const appPasswordInput       = document.getElementById('appPassword');
const groqApiKeyInput        = document.getElementById('groqApiKey');
const newsApiKeyInput        = document.getElementById('newsApiKey');
const intervalDaysInput      = document.getElementById('intervalDays');
const intervalSlider         = document.getElementById('intervalSlider');
const intervalDisplay        = document.getElementById('intervalDisplay');
const sendTimeInput          = document.getElementById('sendTime');
const enableScheduleCheckbox = document.getElementById('enableSchedule');
const newRecipientInput      = document.getElementById('newRecipient');
const addRecipientBtn        = document.getElementById('addRecipientBtn');
const recipientsList         = document.getElementById('recipientsList');
const configForm             = document.getElementById('configForm');
const testEmailBtn           = document.getElementById('testEmailBtn');
const sendNowBtn             = document.getElementById('sendNowBtn');
const resetBtn               = document.getElementById('resetBtn');
const togglePasswordBtn      = document.getElementById('togglePassword');
const notificationArea       = document.getElementById('notificationArea');
const testModal              = document.getElementById('testModal');
const closeTestModal         = document.getElementById('closeTestModal');
const testModalBody          = document.getElementById('testModalBody');
const logPanel               = document.getElementById('logPanel');
const logContent             = document.getElementById('logContent');
const clearLogsBtn           = document.getElementById('clearLogsBtn');

// ==========================================
// 3. NOTIFICATIONS
// ==========================================
function showNotification(message, type = 'success') {
    const n = document.createElement('div');
    n.className = `notification ${type}`;
    n.textContent = message;
    notificationArea.appendChild(n);
    setTimeout(() => {
        n.style.animation = 'slideOut 0.3s ease-out';
        setTimeout(() => n.remove(), 300);
    }, 5000);
}

// ==========================================
// 4. GESTION DESTINATAIRES
// ==========================================
function renderRecipients() {
    recipientsList.innerHTML = '';
    if (config.recipients.length === 0) {
        recipientsList.innerHTML = '<div class="empty-state">Aucun destinataire</div>';
        document.getElementById('recipientCount').textContent = '0';
        return;
    }
    config.recipients.forEach((email, index) => {
        const item = document.createElement('div');
        item.className = 'recipient-item';
        item.innerHTML = `<span>✉️ ${email}</span>
            <button type="button" class="remove-recipient-btn" data-index="${index}">×</button>`;
        item.querySelector('button').onclick = (e) => {
            e.preventDefault();
            config.recipients.splice(index, 1);
            saveLocalConfig();
            renderRecipients();
        };
        recipientsList.appendChild(item);
    });
    document.getElementById('recipientCount').textContent = config.recipients.length;
}

addRecipientBtn.onclick = (e) => {
    e.preventDefault();
    const email = newRecipientInput.value.trim();
    if (!email) { showNotification('Entrez une adresse email', 'error'); return; }
    if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email)) { showNotification('Adresse email invalide', 'error'); return; }
    if (config.recipients.includes(email)) { showNotification('Cet email est déjà ajouté', 'error'); return; }
    config.recipients.push(email);
    saveLocalConfig();
    newRecipientInput.value = '';
    renderRecipients();
    showNotification(`${email} ajouté ✓`, 'success');
};

// ==========================================
// 5. GESTION INTERVALLE
// ==========================================
intervalDaysInput.onchange = () => {
    intervalSlider.value = intervalDaysInput.value;
    intervalDisplay.textContent = intervalDaysInput.value;
    config.intervalDays = parseInt(intervalDaysInput.value);
    saveLocalConfig();
};
intervalSlider.oninput = () => {
    intervalDaysInput.value = intervalSlider.value;
    intervalDisplay.textContent = intervalSlider.value;
    config.intervalDays = parseInt(intervalSlider.value);
    saveLocalConfig();
};

// ==========================================
// 6. TOGGLE PASSWORD
// ==========================================
togglePasswordBtn.onclick = (e) => {
    e.preventDefault();
    const type = appPasswordInput.type === 'password' ? 'text' : 'password';
    appPasswordInput.type = type;
    togglePasswordBtn.textContent = type === 'password' ? '👁️' : '🙈';
};

// ==========================================
// 7. FORM SUBMIT — SAUVEGARDER
// ==========================================
configForm.onsubmit = async (e) => {
    e.preventDefault();
    config.senderEmail    = senderEmailInput.value.trim();
    config.appPassword    = appPasswordInput.value.trim();
    config.groqApiKey     = groqApiKeyInput ? groqApiKeyInput.value.trim() : '';
    config.newsApiKey     = newsApiKeyInput ? newsApiKeyInput.value.trim() : '';
    config.sendTime       = sendTimeInput.value;
    config.enableSchedule = enableScheduleCheckbox.checked;

    if (!config.senderEmail || !config.appPassword) { showNotification('Email et mot de passe requis', 'error'); return; }
    if (!config.recipients.length) { showNotification('Ajoutez au moins un destinataire', 'error'); return; }

    saveLocalConfig();

    try {
        const res = await fetch(`${API_URL}/api/config`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(config)
        });
        if (res.ok) { showNotification('Configuration sauvegardée ✓', 'success'); updateStatus(); }
        else { const d = await res.json(); showNotification(`Erreur : ${d.message}`, 'error'); }
    } catch (e) {
        showNotification('Erreur connexion serveur', 'error');
    }
};

// ==========================================
// 8. TEST EMAIL
// ==========================================
testEmailBtn.onclick = async (e) => {
    e.preventDefault();
    if (!senderEmailInput.value || !appPasswordInput.value) {
        showNotification('Remplissez email et mot de passe', 'error'); return;
    }
    testModal.classList.add('active');
    testModalBody.innerHTML = '<p>Test en cours... <span class="loader"></span></p>';
    try {
        const res = await fetch(`${API_URL}/api/test-email`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ senderEmail: senderEmailInput.value, appPassword: appPasswordInput.value })
        });
        const data = await res.json();
        if (res.ok) {
            testModalBody.innerHTML = `<p style="color:var(--success);">✓ Connexion réussie!</p><p style="font-size:12px;color:#a0a0a0;margin-top:10px;">${data.message}</p>`;
            showNotification('Test réussi ✓', 'success');
        } else {
            testModalBody.innerHTML = `<p style="color:var(--error);">✗ ${data.message}</p>`;
            showNotification('Test échoué', 'error');
        }
    } catch (e) {
        testModalBody.innerHTML = `<p style="color:var(--error);">✗ Erreur réseau : ${e.message}</p>`;
        showNotification('Erreur réseau', 'error');
    }
};

closeTestModal.onclick = () => testModal.classList.remove('active');
testModal.onclick = (e) => { if (e.target === testModal) testModal.classList.remove('active'); };

// ==========================================
// 9. ENVOYER MAINTENANT
// ==========================================
sendNowBtn.onclick = async (e) => {
    e.preventDefault();

    // Lire les valeurs courantes du formulaire
    const currentConfig = {
        ...config,
        senderEmail: senderEmailInput.value.trim() || config.senderEmail,
        appPassword: appPasswordInput.value.trim() || config.appPassword,
        groqApiKey:  groqApiKeyInput ? groqApiKeyInput.value.trim() : config.groqApiKey,
        newsApiKey:  newsApiKeyInput ? newsApiKeyInput.value.trim() : config.newsApiKey,
    };

    if (!currentConfig.senderEmail || !currentConfig.appPassword) {
        showNotification('Email expéditeur et mot de passe requis', 'error'); return;
    }
    if (!currentConfig.recipients.length) {
        showNotification('Aucun destinataire configuré', 'error'); return;
    }

    sendNowBtn.disabled = true;
    sendNowBtn.querySelector('.text').textContent = 'En cours…';
    showNotification('⏳ Veille lancée — logs en direct ci-dessous', 'success');
    openLogPanel();

    try {
        const res = await fetch(`${API_URL}/api/send-now`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(currentConfig)
        });
        const data = await res.json();
        if (res.ok) {
            addHistoryItem('Envoi lancé', 'success');
        } else {
            showNotification(`✗ ${data.message}`, 'error');
            addHistoryItem('Erreur envoi', 'error');
        }
    } catch (err) {
        showNotification('✗ Erreur réseau', 'error');
        addHistoryItem('Erreur réseau', 'error');
    }

    // Le bouton se réactive quand l'agent finit (polling status)
};

// ==========================================
// 10. RÉINITIALISER
// ==========================================
resetBtn.onclick = (e) => {
    e.preventDefault();
    if (confirm('Réinitialiser toute la configuration ?')) {
        localStorage.removeItem('mail_agent_config');
        config = { senderEmail: '', appPassword: '', recipients: [], intervalDays: 1, sendTime: '08:00', enableSchedule: true, groqApiKey: '', newsApiKey: '' };
        senderEmailInput.value = '';
        appPasswordInput.value = '';
        if (groqApiKeyInput) groqApiKeyInput.value = '';
        if (newsApiKeyInput) newsApiKeyInput.value = '';
        intervalDaysInput.value = 1;
        sendTimeInput.value = '08:00';
        enableScheduleCheckbox.checked = true;
        renderRecipients();
        showNotification('Configuration réinitialisée', 'success');
    }
};

// ==========================================
// 11. PANNEAU DE LOGS SSE
// ==========================================
let sseSource = null;

function openLogPanel() {
    if (logPanel) logPanel.style.display = 'block';
    if (sseSource) return; // déjà connecté

    sseSource = new EventSource(`${API_URL}/api/logs/stream`);
    sseSource.onmessage = (e) => {
        const entry = JSON.parse(e.data);
        appendLog(entry);
    };
    sseSource.onerror = () => {
        appendLog({ ts: new Date().toISOString(), level: 'error', msg: '⚠️ Connexion SSE perdue, tentative de reconnexion…' });
    };
}

function appendLog(entry) {
    if (!logContent) return;
    const line = document.createElement('div');
    line.className = `log-line log-${entry.level}`;
    const time = entry.ts ? entry.ts.slice(11, 19) : '';
    line.textContent = `[${time}] ${entry.msg}`;
    logContent.appendChild(line);
    logContent.scrollTop = logContent.scrollHeight;

    // Mettre à jour l'historique sidebar si succès/erreur terminal
    if (entry.msg.includes('✅') || entry.msg.includes('succès')) {
        addHistoryItem(entry.msg, 'success');
        sendNowBtn.disabled = false;
        sendNowBtn.querySelector('.text').textContent = 'Envoyer maintenant';
    }
    if (entry.msg.includes('❌') && entry.msg.includes('Erreur')) {
        addHistoryItem(entry.msg.slice(0, 60), 'error');
        sendNowBtn.disabled = false;
        sendNowBtn.querySelector('.text').textContent = 'Envoyer maintenant';
    }
}

if (clearLogsBtn) {
    clearLogsBtn.onclick = () => { if (logContent) logContent.innerHTML = ''; };
}

// ==========================================
// 12. POLLING STATUT
// ==========================================
function pollStatus() {
    fetch(`${API_URL}/api/status`)
        .then(r => r.json())
        .then(state => {
            const configStatus = document.getElementById('configStatus');
            if (state.running) {
                sendNowBtn.disabled = true;
                sendNowBtn.querySelector('.text').textContent = 'En cours…';
                if (configStatus) { configStatus.textContent = '⏳ Envoi en cours…'; configStatus.style.color = 'var(--warning)'; }
            } else {
                sendNowBtn.disabled = false;
                sendNowBtn.querySelector('.text').textContent = 'Envoyer maintenant';
                if (state.lastRunStatus === 'success' && configStatus) {
                    configStatus.textContent = '✓ Dernier envoi OK';
                    configStatus.style.color = 'var(--success)';
                } else if (state.lastRunStatus === 'error' && configStatus) {
                    configStatus.textContent = '✗ Dernier envoi échoué';
                    configStatus.style.color = 'var(--error)';
                }
            }
        })
        .catch(() => { /* ignore network blips */ });
}
setInterval(pollStatus, 3000);

// ==========================================
// 13. UPDATE STATUS SIDEBAR
// ==========================================
function updateStatus() {
    const statusBadge = document.getElementById('statusBadge');
    const nextSchedule = document.getElementById('nextSchedule');

    if (config.senderEmail && config.recipients.length && config.enableSchedule) {
        if (statusBadge) { statusBadge.innerHTML = '<span class="status-dot"></span><span>✓ Actif</span>'; statusBadge.style.color = 'var(--success)'; }
        const [h, m] = config.sendTime.split(':');
        if (nextSchedule) nextSchedule.textContent = `${h}:${m} (quotidien)`;
    } else {
        if (statusBadge) { statusBadge.innerHTML = '<span class="status-dot"></span><span>✗ Inactif</span>'; statusBadge.style.color = '#a0a0a0'; }
        if (nextSchedule) nextSchedule.textContent = '--:-- (--)';
    }
}

function addHistoryItem(message, status) {
    const historyList = document.getElementById('historyList');
    if (!historyList) return;
    if (historyList.querySelector('.empty-state')) historyList.innerHTML = '';
    const item = document.createElement('div');
    item.className = `history-item ${status}`;
    const time = new Date().toLocaleTimeString().slice(0, 5);
    item.textContent = `${time} - ${message.slice(0, 50)}`;
    historyList.insertBefore(item, historyList.firstChild);
    while (historyList.children.length > 10) historyList.lastChild.remove();
}

// ==========================================
// 14. INITIALISATION AU CHARGEMENT
// ==========================================
window.onload = async () => {
    // 1. Pré-remplir depuis localStorage
    senderEmailInput.value       = config.senderEmail  || '';
    appPasswordInput.value       = config.appPassword  || '';
    if (groqApiKeyInput) groqApiKeyInput.value = config.groqApiKey || '';
    if (newsApiKeyInput) newsApiKeyInput.value = config.newsApiKey  || '';
    intervalDaysInput.value      = config.intervalDays || 1;
    intervalSlider.value         = config.intervalDays || 1;
    intervalDisplay.textContent  = config.intervalDays || 1;
    sendTimeInput.value          = config.sendTime     || '08:00';
    enableScheduleCheckbox.checked = config.enableSchedule !== false;
    renderRecipients();
    updateStatus();

    // 2. Compléter avec les variables d'environnement Render (si champs vides)
    try {
        const res = await fetch(`${API_URL}/api/env-defaults`);
        if (res.ok) {
            const defaults = await res.json();
            if (!senderEmailInput.value && defaults.senderEmail)
                senderEmailInput.value = defaults.senderEmail;
            if (!appPasswordInput.value && defaults.appPasswordSet)
                appPasswordInput.placeholder = '(défini côté serveur)';
            if (groqApiKeyInput && !groqApiKeyInput.value && defaults.groqApiKey)
                groqApiKeyInput.value = defaults.groqApiKey;
            if (newsApiKeyInput && !newsApiKeyInput.value && defaults.newsApiKey)
                newsApiKeyInput.value = defaults.newsApiKey;
        }
    } catch (e) { /* pas bloquant */ }

    // 3. Ouvrir les logs SSE d'emblée (pour voir le statut en direct)
    openLogPanel();
};

// ==========================================
// 15. ANIMATIONS FOND
// ==========================================
const bgCanvas = document.getElementById('sphereCanvas');
if (bgCanvas) {
    const bgCtx = bgCanvas.getContext('2d');
    bgCanvas.width  = window.innerWidth;
    bgCanvas.height = window.innerHeight;
    const particles = [];
    const colors = [themeColor, '#FFFFFF'];
    for (let i = 0; i < 800; i++) {
        particles.push({
            x: Math.random() * bgCanvas.width,
            y: Math.random() * bgCanvas.height,
            size: Math.random() * 2,
            speed: Math.random() * 0.5,
            color: colors[Math.floor(Math.random() * 2)]
        });
    }
    function animateBg() {
        bgCtx.fillStyle = 'rgba(10,14,26,0.2)';
        bgCtx.fillRect(0, 0, bgCanvas.width, bgCanvas.height);
        particles.forEach(p => {
            p.y -= p.speed;
            if (p.y < 0) p.y = bgCanvas.height;
            bgCtx.fillStyle = p.color;
            bgCtx.beginPath();
            bgCtx.arc(p.x, p.y, p.size, 0, Math.PI * 2);
            bgCtx.fill();
        });
        requestAnimationFrame(animateBg);
    }
    animateBg();
    window.onresize = () => {
        bgCanvas.width  = window.innerWidth;
        bgCanvas.height = window.innerHeight;
    };
}

// LOGO ANIMÉ
const logoCanvas = document.getElementById('logoCanvas');
if (logoCanvas) {
    const logoCtx = logoCanvas.getContext('2d');
    logoCanvas.width = 64; logoCanvas.height = 64;
    const logoParticles = [];
    for (let i = 0; i < 80; i++) {
        const theta = Math.random() * Math.PI * 2;
        const phi   = Math.acos(2 * Math.random() - 1);
        const r = 14;
        logoParticles.push({ x: r * Math.sin(phi) * Math.cos(theta), y: r * Math.sin(phi) * Math.sin(theta), z: r * Math.cos(phi), color: themeColor, size: 1.2 });
    }
    let angleY = 0, angleX = 0;
    function animateLogo() {
        logoCtx.fillStyle = 'rgba(10,14,26,0.3)';
        logoCtx.fillRect(0, 0, 64, 64);
        angleY += 0.03; angleX += 0.01;
        logoParticles.forEach(p => {
            let x = p.x, y = p.y, z = p.z;
            let tx = x * Math.cos(angleY) - z * Math.sin(angleY);
            let tz = x * Math.sin(angleY) + z * Math.cos(angleY);
            x = tx; z = tz;
            let ty = y * Math.cos(angleX) - z * Math.sin(angleX);
            tz = y * Math.sin(angleX) + z * Math.cos(angleX);
            y = ty; z = tz;
            const scale = 100 / (100 + z);
            logoCtx.fillStyle = p.color;
            logoCtx.beginPath();
            logoCtx.arc(x * scale + 32, y * scale + 32, p.size * scale, 0, Math.PI * 2);
            logoCtx.fill();
        });
        requestAnimationFrame(animateLogo);
    }
    animateLogo();
}
