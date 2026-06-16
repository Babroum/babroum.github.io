// ==========================================
// 0. CONFIGURATION & UTILITAIRES
// ==========================================

// --- COULEUR DYNAMIQUE ---
const themeColor = '#87CEEB';
// Convertisseur Hex vers RGB pour les transparences
function hexToRgb(hex) {
    const r = parseInt(hex.slice(1, 3), 16);
    const g = parseInt(hex.slice(3, 5), 16);
    const b = parseInt(hex.slice(5, 7), 16);
    return `${r}, ${g}, ${b}`;
}
const themeRgb = hexToRgb(themeColor);
const API_BASE_URL = window.location.origin && window.location.origin !== 'null'
    ? window.location.origin
    : 'http://localhost:8000';

function escapeHtml(text) {
    if (!text) return '';
    return text.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;").replace(/'/g, "&#039;");
}

function sanitizeInput(input) {
    if (typeof input !== 'string') return '';
    return input.trim().slice(0, 2000);
}

if (typeof marked !== 'undefined') {
    marked.setOptions({ headerIds: false, mangle: false });
}

// Relancer l'audio global
if (window.parent && window.parent.resumeGlobalAudio) {
    window.parent.resumeGlobalAudio();
}

// ==========================================
// 1. GESTION DES DONNÉES (CHATS)
// ==========================================
const welcomeMessages = ["Ravi de vous revoir", "Bonjour, prêt à explorer ?", "Bienvenue."];
let conversationHistory = [];
let currentChatId = null;
let chats = [];

try {
    const stored = localStorage.getItem('my_ai_chats');
    chats = stored ? JSON.parse(stored) : [];
    if (!Array.isArray(chats)) chats = [];
} catch (e) { chats = []; }

const chatInput = document.getElementById('chatInput');
const sendBtn = document.getElementById('sendBtn');
const messagesContainer = document.getElementById('messagesContainer');
const chatArea = document.getElementById('chatArea');
const welcomeMessage = document.getElementById('welcomeMessage');
let downloadUniversitiesBtn = document.getElementById('downloadUniversitiesBtn');
let downloadEmailsBtn = document.getElementById('downloadEmailsBtn');

function ensureDownloadsUI() {
    if (downloadUniversitiesBtn && downloadEmailsBtn) return;

    const sidebarMenu = document.querySelector('.sidebar-menu');
    if (!sidebarMenu) return;

    const section = document.createElement('div');
    section.className = 'menu-section';
    section.innerHTML = `
        <div class="menu-section-title">Fichiers</div>
        <div class="downloads-panel">
            <button class="download-btn" id="downloadUniversitiesBtn" type="button">Télécharger \`universities.csv\`</button>
            <button class="download-btn" id="downloadEmailsBtn" type="button">Télécharger \`emails.csv\`</button>
        </div>
    `;
    sidebarMenu.prepend(section);

    downloadUniversitiesBtn = document.getElementById('downloadUniversitiesBtn');
    downloadEmailsBtn = document.getElementById('downloadEmailsBtn');
}

ensureDownloadsUI();

const downloadableFiles = {
    universities: downloadUniversitiesBtn,
    emails: downloadEmailsBtn
};

if (welcomeMessage) {
    document.getElementById('welcomeText').textContent = welcomeMessages[Math.floor(Math.random() * welcomeMessages.length)];
}

function saveChatsToStorage() {
    try { localStorage.setItem('my_ai_chats', JSON.stringify(chats)); } catch (e) {}
}

function setDownloadButtonsState(files = {}) {
    Object.entries(downloadableFiles).forEach(([key, button]) => {
        if (!button) return;
        const fileInfo = files[key];
        const isAvailable = Boolean(fileInfo && fileInfo.exists);
        button.disabled = !isAvailable;
        button.dataset.downloadUrl = isAvailable ? `${API_BASE_URL}${fileInfo.download_url}` : '';
        button.title = isAvailable ? `Télécharger ${fileInfo.filename}` : `Aucun fichier ${key}.csv disponible`;
    });
}

async function refreshAvailableFiles() {
    try {
        const response = await fetch(`${API_BASE_URL}/api/files`);
        if (!response.ok) throw new Error(`HTTP ${response.status}`);
        const files = await response.json();
        setDownloadButtonsState(files);
    } catch (error) {
        setDownloadButtonsState({});
    }
}

function downloadCsv(fileKey) {
    const button = downloadableFiles[fileKey];
    const downloadUrl = button?.dataset.downloadUrl;
    if (!downloadUrl) {
        alert("Le fichier n'est pas encore disponible.");
        return;
    }
    const link = document.createElement('a');
    link.href = downloadUrl;
    link.download = '';
    document.body.appendChild(link);
    link.click();
    link.remove();
}

// ==========================================
// 2. GESTION SIDEBAR
// ==========================================
function renderSidebar() {
    const chatHistory = document.getElementById('chatHistory');
    chatHistory.innerHTML = '';

    if (chats.length === 0) {
        chatHistory.innerHTML = '<div class="empty-state">Aucune archive</div>';
        return;
    }

    chats.slice().reverse().forEach(chat => {
        const item = document.createElement('div');
        item.className = 'history-item';
        item.style.display = 'flex';
        item.style.justifyContent = 'space-between';
        item.style.alignItems = 'center';
        item.style.gap = '10px';

        // GESTION DYNAMIQUE DE LA COULEUR ACTIVE
        if (chat.id === currentChatId) {
            item.style.background = `rgba(${themeRgb}, 0.2)`; 
            item.style.borderLeft = `3px solid ${themeColor}`;
        }

        let title = chat.title;
        if (!title) {
            const firstMsg = chat.messages.find(m => m.role === 'user');
            title = firstMsg ? (firstMsg.content.substring(0, 20) + "...") : "Nouvelle conversation";
        }

        const spanTitle = document.createElement('span');
        spanTitle.textContent = title;
        spanTitle.style.flexGrow = '1';
        spanTitle.style.whiteSpace = 'nowrap';
        spanTitle.style.overflow = 'hidden';
        spanTitle.style.textOverflow = 'ellipsis';
        spanTitle.style.pointerEvents = 'none';

        const spanDelete = document.createElement('span');
        spanDelete.innerHTML = "&times;";
        spanDelete.className = "delete-chat";
        spanDelete.dataset.chatId = chat.id;
        spanDelete.title = "Supprimer";
        spanDelete.style.cursor = 'pointer';
        spanDelete.style.fontWeight = 'bold';
        spanDelete.style.padding = '0 5px';
        spanDelete.style.opacity = '0.7';

        item.appendChild(spanTitle);
        item.appendChild(spanDelete);
        item.dataset.chatId = chat.id;
        chatHistory.appendChild(item);
    });
}

function deleteChat(id) {
    if (confirm("Supprimer cette conversation ?")) {
        chats = chats.filter(c => c.id !== id);
        saveChatsToStorage();
        if (currentChatId === id) newChat(); else renderSidebar();
    }
}

// ==========================================
// 3. LOGIQUE AVATAR
// ==========================================

// Fonction pour figer l'avatar précédent en image (Optimisation perf)
function freezeLastAvatar() {
    const activeCanvas = document.querySelector('.ai-live-canvas');
    if (activeCanvas) {
        const parent = activeCanvas.parentElement;
        const img = document.createElement('img');
        img.src = activeCanvas.toDataURL();
        img.style.cssText = `width:100%; height:100%; border-radius:50%; box-shadow:0 0 10px rgba(${themeRgb}, 0.5);`;
        activeCanvas.remove();
        parent.appendChild(img);
    }
}

function createMessage(role, content, isTyping = false) {
    const div = document.createElement('div');
    div.className = `message ${role}`;
    const avatar = document.createElement('div');
    avatar.className = 'message-avatar';
    
    if (role === 'user') {
        avatar.textContent = '👤';
    } else {
        // --- RESTAURATION DU CANVAS POUR L'IA ---
        const canvas = document.createElement('canvas');
        canvas.className = 'ai-live-canvas';
        canvas.width = 64; canvas.height = 64;
        canvas.style.cssText = 'width:100%; height:100%;';
        avatar.appendChild(canvas);
    }

    const msgContent = document.createElement('div');
    msgContent.className = 'message-content';
    const header = document.createElement('div');
    header.className = 'message-header';
    
    const authorSpan = document.createElement('span');
    authorSpan.className = 'message-author';
    authorSpan.textContent = role === 'user' ? 'Vous' : 'My IA';
    const timeSpan = document.createElement('span');
    timeSpan.className = 'message-time';
    timeSpan.textContent = new Date().toLocaleTimeString().slice(0, 5);
    
    header.appendChild(authorSpan); header.appendChild(document.createTextNode(' ')); header.appendChild(timeSpan);
    
    const text = document.createElement('div');
    text.className = 'message-text';
    
    if (isTyping) {
        text.innerHTML = '<div class="typing-indicator"><div class="typing-dot"></div><div class="typing-dot"></div><div class="typing-dot"></div></div>';
    } else {
        if (role === 'ai') {
            const rawHtml = marked.parse(content);
            const cleanHtml = rawHtml.replace(/<script\b[^>]*>([\s\S]*?)<\/script>/gim, "").replace(/<iframe\b[^>]*>([\s\S]*?)<\/iframe>/gim, "").replace(/on\w+="[^"]*"/g, "");
            text.innerHTML = cleanHtml;
            if (window.hljs) text.querySelectorAll('pre code').forEach((block) => hljs.highlightElement(block));
        } else {
            text.textContent = content;
        }
    }
    msgContent.appendChild(header); msgContent.appendChild(text); div.appendChild(avatar); div.appendChild(msgContent);
    return div;
}

function addMessageToUI(role, content, isTyping = false) {
    // Si c'est l'IA qui parle, on fige le précédent avatar avant d'en créer un nouveau
    if (role === 'ai') freezeLastAvatar();
    
    const el = createMessage(role, content, isTyping);
    messagesContainer.appendChild(el);
    chatArea.scrollTop = chatArea.scrollHeight;
    return el;
}

// ==========================================
// 4. ENVOI & CHARGEMENT
// ==========================================
async function sendMessage() {
    const txt = sanitizeInput(chatInput.value);
    if (!txt) return;

    if (!currentChatId) {
        currentChatId = Date.now();
        chats.push({ id: currentChatId, messages: [] });
        renderSidebar();
    }
    
    welcomeMessage.classList.add('hidden');
    addMessageToUI('user', txt);
    conversationHistory.push({ role: 'user', content: txt });
    updateChatData(currentChatId);
    
    chatInput.value = '';
    sendBtn.disabled = true;
    const typing = addMessageToUI('ai', '', true);

    try {
        const recentContext = conversationHistory.slice(-15);
        const res = await fetch(`${API_BASE_URL}/api/chat`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ messages: recentContext })
        });

        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        const data = await res.json();
        
        typing.remove();
        const aiText = data.content?.[0]?.text || data.reply || "Erreur format";
        addMessageToUI('ai', aiText);
        conversationHistory.push({ role: 'assistant', content: aiText });
        updateChatData(currentChatId);

        if (conversationHistory.length === 2) generateSmartTitle(currentChatId, conversationHistory[0].content);
        setDownloadButtonsState(data.files || {});
    } catch (e) {
        typing.remove();
        addMessageToUI('ai', "Erreur connexion serveur.");
    }
    sendBtn.disabled = false;
}

async function generateSmartTitle(id, firstMsg) {
    try {
        const res = await fetch(`${API_BASE_URL}/api/title`, {
            method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({ message: firstMsg })
        });
        if (res.ok) {
            const data = await res.json();
            const chat = chats.find(c => c.id === id);
            if(chat) { chat.title = sanitizeInput(data.title); saveChatsToStorage(); renderSidebar(); }
        }
    } catch(e) {}
}

function updateChatData(id) {
    const idx = chats.findIndex(c => c.id === id);
    if(idx > -1) { chats[idx].messages = [...conversationHistory]; saveChatsToStorage(); }
}

function loadChat(id) {
    if (currentChatId === id) return;
    const chat = chats.find(c => c.id === id);
    if (!chat) return;
    currentChatId = id; conversationHistory = [...chat.messages];
    messagesContainer.innerHTML = ''; welcomeMessage.classList.add('hidden');
    conversationHistory.forEach(m => addMessageToUI(m.role === 'assistant'?'ai':'user', m.content));
    renderSidebar();
}

function newChat() {
    conversationHistory = []; currentChatId = null; messagesContainer.innerHTML = ''; welcomeMessage.classList.remove('hidden'); renderSidebar();
}

sendBtn.onclick = sendMessage;
chatInput.onkeypress = (e) => { if(e.key==='Enter' && !e.shiftKey) { e.preventDefault(); sendMessage(); } };
document.querySelector('.new-chat-btn').onclick = newChat;
if (downloadUniversitiesBtn) downloadUniversitiesBtn.onclick = () => downloadCsv('universities');
if (downloadEmailsBtn) downloadEmailsBtn.onclick = () => downloadCsv('emails');

// ==========================================
// 5. ANIMATIONS (COULEUR DYNAMIQUE)
// ==========================================
const bgCanvas = document.getElementById('sphereCanvas');
if (bgCanvas) {
    const bgCtx = bgCanvas.getContext('2d');
    bgCanvas.width = window.innerWidth; bgCanvas.height = window.innerHeight;
    const particles = [];
    const colors = [themeColor, '#FFFFFF'];
    for(let i=0; i<800; i++) {
        particles.push({ x: Math.random()*bgCanvas.width, y: Math.random()*bgCanvas.height, size: Math.random()*2, speed: Math.random()*0.5, color: colors[Math.floor(Math.random()*2)] });
    }
    function animateBg() {
        bgCtx.fillStyle = 'rgba(10, 14, 26, 0.2)'; bgCtx.fillRect(0,0,bgCanvas.width, bgCanvas.height);
        particles.forEach(p => { p.y -= p.speed; if(p.y < 0) p.y = bgCanvas.height; bgCtx.fillStyle = p.color; bgCtx.beginPath(); bgCtx.arc(p.x, p.y, p.size, 0, Math.PI*2); bgCtx.fill(); });
        requestAnimationFrame(animateBg);
    }
    animateBg();
}

// LOGO & AVATAR IA
const logoCanvas = document.getElementById('logoCanvas');
if (logoCanvas) {
    const logoCtx = logoCanvas.getContext('2d');
    logoCanvas.width = 64; logoCanvas.height = 64;
    const logoParticles = [];
    for(let i=0; i<80; i++) {
        const theta = Math.random() * Math.PI * 2; const phi = Math.acos(2 * Math.random() - 1); const r = 14;
        logoParticles.push({ x: r * Math.sin(phi) * Math.cos(theta), y: r * Math.sin(phi) * Math.sin(theta), z: r * Math.cos(phi), color: themeColor, size: 1.2 });
    }
    let angleY = 0; let angleX = 0;
    
    function animateLogo() {
        logoCtx.fillStyle = 'rgba(10, 14, 26, 0.3)'; logoCtx.fillRect(0, 0, 64, 64);
        angleY += 0.03; angleX += 0.01;
        logoParticles.forEach(p => {
            let x = p.x; let y = p.y; let z = p.z;
            let tx = x * Math.cos(angleY) - z * Math.sin(angleY); let tz = x * Math.sin(angleY) + z * Math.cos(angleY); x = tx; z = tz;
            let ty = y * Math.cos(angleX) - z * Math.sin(angleX); tz = y * Math.sin(angleX) + z * Math.cos(angleX); y = ty; z = tz;
            const scale = 100 / (100 + z);
            logoCtx.fillStyle = p.color; logoCtx.beginPath(); logoCtx.arc(x*scale+32, y*scale+32, p.size*scale, 0, Math.PI*2); logoCtx.fill();
        });

        // --- RESTAURATION : Copie du logo vers l'avatar dans le chat ---
        const activeLiveCanvas = document.querySelector('.ai-live-canvas');
        if (activeLiveCanvas) {
            const destCtx = activeLiveCanvas.getContext('2d');
            destCtx.clearRect(0, 0, 64, 64);
            destCtx.drawImage(logoCanvas, 0, 0);
        }

        requestAnimationFrame(animateLogo);
    }
    animateLogo();
}

// Gestion Clics
const chatHistory = document.getElementById('chatHistory');
if (chatHistory) {
    chatHistory.addEventListener('click', (e) => {
        if (e.target.classList.contains('delete-chat')) {
            e.stopPropagation(); const id = parseInt(e.target.dataset.chatId); deleteChat(id); return;
        }
        const item = e.target.closest('.history-item');
        if (item) loadChat(parseInt(item.dataset.chatId));
    });
}
renderSidebar();
refreshAvailableFiles();
