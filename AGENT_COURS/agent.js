// =========================================================================
// SCRIPT DE SYNCHRONISATION ET CONTRÔLE DE L'AGENT DE VEILLE (PORT 8080)
// =========================================================================

document.addEventListener('DOMContentLoaded', () => {
    // Récupération des composants HTML via leurs ID uniques
    const selectIntervalle = document.getElementById('scheduleSelect');
    const boutonEnregistrer = document.getElementById('saveScheduleBtn');
    const boutonNouvelleAnalyse = document.getElementById('newAnalysisBtn');
    const statusText = document.getElementById('statusText');

    const API_BASE_URL = 'http://localhost:8080/api';

    // Sécurité : On s'assure que les éléments existent dans le HTML actuel
    if (!selectIntervalle || !boutonNouvelleAnalyse) {
        console.error("❌ Erreur : Les éléments 'scheduleSelect' ou 'newAnalysisBtn' sont introuvables dans le HTML.");
        return;
    }

    /**
     * 1. GESTION DYNAMIQUE DU BRIDAGE DU BOUTON "NOUVELLE ANALYSE"
     */
    function synchroniserEtatBoutonAnalyse() {
        if (selectIntervalle.value === 'manual') {
            // Mode Manuel : On libère le bouton
            boutonNouvelleAnalyse.disabled = false;
            if (statusText) {
                statusText.innerText = "Mode Manuel Activé";
                statusText.parentElement.style.borderColor = "rgba(214, 158, 46, 0.4)";
                statusText.parentElement.style.color = "#D69E2E";
            }
        } else {
            // Mode Auto : Bouton bridé
            boutonNouvelleAnalyse.disabled = true;
            if (statusText) {
                statusText.innerText = "Agent Actif (Auto)";
                statusText.parentElement.style.borderColor = "rgba(135, 206, 235, 0.3)";
                statusText.parentElement.style.color = "#87CEEB";
            }
        }
    }

    // Écouter les modifications sur la liste déroulante pour ajuster le bridage en direct
    selectIntervalle.addEventListener('change', synchroniserEtatBoutonAnalyse);
    
    // Premier contrôle au chargement initial de la page pour appliquer l'état par défaut
    synchroniserEtatBoutonAnalyse();


    /**
     * 2. ENREGISTRER LA FRÉQUENCE DE VEILLE AUTOMATIQUE
     */
    if (boutonEnregistrer) {
        boutonEnregistrer.addEventListener('click', async () => {
            const optionChoisie = selectIntervalle.value;
            
            boutonEnregistrer.disabled = true;
            boutonEnregistrer.innerText = "🔄 Synchronisation...";

            try {
                const reponse = await fetch(`${API_BASE_URL}/schedule`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ interval: optionChoisie })
                });

                if (reponse.ok) {
                    alert(`✅ Mode mis à jour sur le serveur : ${optionChoisie}.`);
                } else {
                    const errData = await reponse.json();
                    alert(`❌ Erreur : ${errData.message}`);
                }
            } catch (error) {
                console.error("Erreur d'envoi du schedule :", error);
                alert("❌ Erreur : Le serveur Flask (Port 8080) est déconnecté.");
            } finally {
                boutonEnregistrer.disabled = false;
                boutonEnregistrer.innerText = "Enregistrer la fréquence";
            }
        });
    }


    /**
     * 3. EXÉCUTER UNE ANALYSE MANUELLE IMMÉDIATE
     */
    boutonNouvelleAnalyse.addEventListener('click', async () => {
        if (boutonNouvelleAnalyse.disabled) return;

        // Mutation visuelle d'attente pendant le traitement de l'IA
        const libelleDorigine = boutonNouvelleAnalyse.innerHTML;
        boutonNouvelleAnalyse.disabled = true;
        boutonNouvelleAnalyse.innerHTML = "🔄 Audit IA & Drive en cours...";

        try {
            const reponse = await fetch(`${API_BASE_URL}/analyze`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' }
            });

            if (reponse.ok) {
                alert("✅ Succès ! L'analyse manuelle est terminée et tes fichiers ont été mis à jour sur Google Drive.");
            } else {
                const errData = await reponse.json();
                alert(`❌ Échec de la session : ${errData.message}`);
            }
        } catch (error) {
            console.error("Erreur de traitement manuel :", error);
            alert("❌ Erreur de liaison réseau : Le serveur Flask est injoignable.");
        } finally {
            boutonNouvelleAnalyse.innerHTML = libelleDorigine;
            synchroniserEtatBoutonAnalyse();
        }
    });
});