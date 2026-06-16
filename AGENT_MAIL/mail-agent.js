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

// Configuration du serveur
const API_URL = window.location.origin; // Fonctionne sur Render.com

// ==========================================
// 1. GESTION DES DONNÉES
// ==========================================
let config = {
    senderEmail: '',
    appPassword: '',
    recipients: [],
    intervalDays: 1,
    sendTime: '08:00',
    enableSchedule: true
};

function loadConfig() {
    const stored = localStorage.getItem('mail_agent_config');
    if (stored) {
        try {
            config = JSON.parse(stored);
        } catch (e) { }
    }
}

function saveConfig() {
    localStorage.setItem('mail_agent_config', JSON.stringify(config));
}

loadConfig();

// ==========================================
// 2. ÉLÉMENTS DOM
// ==========================================
const senderEmailInput = document.getElementById('senderEmail');
const appPasswordInput = document.getElementById('appPassword');
const intervalDaysInput = document.getElementById('intervalDays');
const intervalSlider = document.getElementById('intervalSlider');
const intervalDisplay = document.getElementById('intervalDisplay');
const sendTimeInput = document.getElementById('sendTime');
const enableScheduleCheckbox = document.getElementById('enableSchedule');
const newRecipientInput = document.getElementById('newRecipient');
const addRecipientBtn = document.getElementById('addRecipientBtn');
const recipientsList = document.getElementById('recipientsList');
const configForm = document.getElementById('configForm');
const testEmailBtn = document.getElementById('testEmailBtn');
const sendNowBtn = document.getElementById('sendNowBtn');
const resetBtn = document.getElementById('resetBtn');
const togglePasswordBtn = document.getElementById('togglePassword');
const notificationArea = document.getElementById('notificationArea');
const testModal = document.getElementById('testModal');
const closeTestModal = document.getElementById('closeTestModal');
const testModalBody = document.getElementById('testModalBody');

// ==========================================
// 3. NOTIFICATIONS
// ==========================================
function showNotification(message, type = 'success') {
    const notification = document.createElement('div');
    notification.className = `notification ${type}`;
    notification.textContent = message;
    notificationArea.appendChild(notification);

    setTimeout(() => {
        notification.style.animation = 'slideOut 0.3s ease-out';
        setTimeout(() => notification.remove(), 300);
    }, 4000);
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
        item.innerHTML = `
            <span>✉️ ${email}</span>
            <button type="button" class="remove-recipient-btn" data-index="${index}">×</button>
        `;
        item.querySelector('button').onclick = (e) => {
            e.preventDefault();
            config.recipients.splice(index, 1);
            saveConfig();
            renderRecipients();
        };
        recipientsList.appendChild(item);
    });

    document.getElementById('recipientCount').textContent = config.recipients.length;
}

addRecipientBtn.onclick = (e) => {
    e.preventDefault();
    const email = newRecipientInput.value.trim();

    if (!email) {
        showNotification('Entrez une adresse email', 'error');
        return;
    }

    if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email)) {
        showNotification('Adresse email invalide', 'error');
        return;
    }

    if (config.recipients.includes(email)) {
        showNotification('Cet email est déjà ajouté', 'error');
        return;
    }

    config.recipients.push(email);
    saveConfig();
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
    saveConfig();
};

intervalSlider.oninput = () => {
    intervalDaysInput.value = intervalSlider.value;
    intervalDisplay.textContent = intervalSlider.value;
    config.intervalDays = parseInt(intervalSlider.value);
    saveConfig();
};

// ==========================================
// 6. GESTION PASSWORD
// ==========================================
togglePasswordBtn.onclick = (e) => {
    e.preventDefault();
    const type = appPasswordInput.type === 'password' ? 'text' : 'password';
    appPasswordInput.type = type;
    togglePasswordBtn.textContent = type === 'password' ? '👁️' : '🙈';
};

// ==========================================
// 7. FORM SUBMIT
// ==========================================
configForm.onsubmit = async (e) => {
    e.preventDefault();

    config.senderEmail = senderEmailInput.value.trim();
    config.appPassword = appPasswordInput.value.trim();
    config.sendTime = sendTimeInput.value;
    config.enableSchedule = enableScheduleCheckbox.checked;

    if (!config.senderEmail || !config.appPassword) {
        showNotification('Email et mot de passe requis', 'error');
        return;
    }

    if (!config.recipients.length) {
        showNotification('Ajoutez au moins un destinataire', 'error');
        return;
    }

    saveConfig();

    try {
        const res = await fetch(`${API_URL}/api/config`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(config)
        });

        if (res.ok) {
            showNotification('Configuration sauvegardée ✓', 'success');
            updateStatus();
        } else {
            showNotification('Erreur de sauvegarde', 'error');
        }
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
        showNotification('Remplissez email et mot de passe', 'error');
        return;
    }

    testModal.classList.add('active');
    testModalBody.innerHTML = '<p>Test en cours... <span class="loader"></span></p>';

    try {
        const res = await fetch(`${API_URL}/api/test-email`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                senderEmail: senderEmailInput.value,
                appPassword: appPasswordInput.value
            })
        });

        if (res.ok) {
            const data = await res.json();
            testModalBody.innerHTML = `<p style="color: var(--success);">✓ Connexion réussie!</p><p style="font-size: 12px; color: #a0a0a0; margin-top: 10px;">${data.message || 'Le serveur SMTP répond correctement.'}</p>`;
            showNotification('Test réussi ✓', 'success');
        } else {
            const data = await res.json();
            testModalBody.innerHTML = `<p style="color: var(--error);">✗ Erreur : ${data.message || 'Vérifiez vos identifiants'}</p>`;
            showNotification('Test échoué', 'error');
        }
    } catch (e) {
        testModalBody.innerHTML = `<p style="color: var(--error);">✗ Erreur connexion : ${e.message}</p>`;
        showNotification('Erreur réseau', 'error');
    }
};

closeTestModal.onclick = () => {
    testModal.classList.remove('active');
};

testModal.onclick = (e) => {
    if (e.target === testModal) testModal.classList.remove('active');
};

// ==========================================
// 9. ACTIONS
// ==========================================
sendNowBtn.onclick = async (e) => {
    e.preventDefault();

    if (!config.recipients.length) {
        showNotification('Aucun destinataire', 'error');
        return;
    }

    showNotification('Envoi en cours...', 'success');

    try {
        const res = await fetch(`${API_URL}/api/send-now`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(config)
        });

        if (res.ok) {
            const data = await res.json();
            showNotification(`✓ ${data.message}`, 'success');
            addHistoryItem('Email envoyé', 'success');
            updateStatus();
        } else {
            const data = await res.json();
            showNotification(`✗ ${data.message || 'Erreur d\'envoi'}`, 'error');
            addHistoryItem('Erreur envoi', 'error');
        }
    } catch (e) {
        showNotification('✗ Erreur réseau', 'error');
        addHistoryItem('Erreur réseau', 'error');
    }
};

resetBtn.onclick = (e) => {
    e.preventDefault();
    if (confirm('Réinitialiser toute la configuration ?')) {
        localStorage.removeItem('mail_agent_config');
        config = {
            senderEmail: '',
            appPassword: '',
            recipients: [],
            intervalDays: 1,
            sendTime: '08:00',
            enableSchedule: true
        };
        senderEmailInput.value = '';
        appPasswordInput.value = '';
        intervalDaysInput.value = 1;
        sendTimeInput.value = '08:00';
        enableScheduleCheckbox.checked = true;
        renderRecipients();
        showNotification('Configuration réinitialisée', 'success');
    }
};

// ==========================================
// 10. INTERFACE & ANIMATIONS
// ==========================================
function updateStatus() {
    const statusBadge = document.getElementById('statusBadge');
    const configStatus = document.getElementById('configStatus');
    const nextSchedule = document.getElementById('nextSchedule');

    if (config.senderEmail && config.recipients.length && config.enableSchedule) {
        statusBadge.innerHTML = '<span class="status-dot"></span><span>✓ Actif</span>';
        statusBadge.style.color = 'var(--success)';
        configStatus.textContent = '✓ Configuré';
        configStatus.style.color = 'var(--success)';

        const [hours, mins] = config.sendTime.split(':');
        nextSchedule.textContent = `${hours}:${mins} (demain)`;
    } else {
        statusBadge.innerHTML = '<span class="status-dot"></span><span>✗ Inactif</span>';
        statusBadge.style.color = '#a0a0a0';
        configStatus.textContent = '⚠️ Incomplet';
        configStatus.style.color = 'var(--warning)';
        nextSchedule.textContent = '--:-- (--)';
    }
}

function addHistoryItem(message, status) {
    const historyList = document.getElementById('historyList');
    if (historyList.querySelector('.empty-state')) {
        historyList.innerHTML = '';
    }

    const item = document.createElement('div');
    item.className = `history-item ${status}`;
    const time = new Date().toLocaleTimeString().slice(0, 5);
    item.textContent = `${time} - ${message}`;
    historyList.insertBefore(item, historyList.firstChild);

    // Garder max 10 items
    while (historyList.children.length > 10) {
        historyList.lastChild.remove();
    }
}

// Charger les données au démarrage
window.onload = () => {
    senderEmailInput.value = config.senderEmail || '';
    appPasswordInput.value = config.appPassword || '';
    intervalDaysInput.value = config.intervalDays || 1;
    intervalSlider.value = config.intervalDays || 1;
    intervalDisplay.textContent = config.intervalDays || 1;
    sendTimeInput.value = config.sendTime || '08:00';
    enableScheduleCheckbox.checked = config.enableSchedule !== false;
    renderRecipients();
    updateStatus();
};

// ==========================================
// 11. ANIMATIONS FOND
// ==========================================
const bgCanvas = document.getElementById('sphereCanvas');
if (bgCanvas) {
    const bgCtx = bgCanvas.getContext('2d');
    bgCanvas.width = window.innerWidth;
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
        bgCtx.fillStyle = 'rgba(10, 14, 26, 0.2)';
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
        bgCanvas.width = window.innerWidth;
        bgCanvas.height = window.innerHeight;
    };
}

// LOGO ANIMÉ
const logoCanvas = document.getElementById('logoCanvas');
if (logoCanvas) {
    const logoCtx = logoCanvas.getContext('2d');
    logoCanvas.width = 64;
    logoCanvas.height = 64;
    const logoParticles = [];

    for (let i = 0; i < 80; i++) {
        const theta = Math.random() * Math.PI * 2;
        const phi = Math.acos(2 * Math.random() - 1);
        const r = 14;
        logoParticles.push({
            x: r * Math.sin(phi) * Math.cos(theta),
            y: r * Math.sin(phi) * Math.sin(theta),
            z: r * Math.cos(phi),
            color: themeColor,
            size: 1.2
        });
    }

    let angleY = 0;
    let angleX = 0;

    function animateLogo() {
        logoCtx.fillStyle = 'rgba(10, 14, 26, 0.3)';
        logoCtx.fillRect(0, 0, 64, 64);
        angleY += 0.03;
        angleX += 0.01;

        logoParticles.forEach(p => {
            let x = p.x, y = p.y, z = p.z;
            let tx = x * Math.cos(angleY) - z * Math.sin(angleY);
            let tz = x * Math.sin(angleY) + z * Math.cos(angleY);
            x = tx;
            z = tz;
            let ty = y * Math.cos(angleX) - z * Math.sin(angleX);
            tz = y * Math.sin(angleX) + z * Math.cos(angleX);
            y = ty;
            z = tz;

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
