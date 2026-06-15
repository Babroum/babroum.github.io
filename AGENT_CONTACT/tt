import os
import json
import requests
from dotenv import load_dotenv
from langchain_groq import ChatGroq
from langchain_core.messages import HumanMessage, SystemMessage, ToolMessage
from langchain_core.tools import tool
from tavily import TavilyClient

load_dotenv()

GROQ_API_KEY = os.environ.get("GROQ_API_KEY")
TAVILY_API_KEY = os.environ.get("TAVILY_API_KEY")
# Initialisation du client Tavily
tavily_client = TavilyClient(api_key=TAVILY_API_KEY)

@tool
def web_search(query: str) -> str:
    """Recherche des informations sur le web à propos d'une université ou d'un contact."""
    try:
        response = tavily_client.search(q=query, max_results=3)
        results = [f"Source: {r['url']}\nContenu: {r['content']}" for r in response.get('results', [])]
        return "\n\n".join(results)
    except Exception as e:
        return f"Erreur de recherche : {str(e)}"


# Liaison de l'outil de recherche Web avec le modèle Groq
tools = [web_search]
llm = ChatGroq(
    model="llama-3.3-70b-versatile", 
    temperature=0,
    groq_api_key=GROQ_API_KEY, # Correction : Virgule ajoutée ici
    
).bind_tools(tools)



system_prompt = """Tu es un agent expert en recherche et prospection universitaire internationale.
Ta mission est d'identifier des universités pertinentes dans trois régions : le Canada, l'Europe de l'Est et le Vietnam. Détermine le nombre idéal de résultats par région (entre 3 et 8) selon la pertinence des données.

Pour chaque établissement, tu dois collecter :
- Le nom de l'université.
- Le pays ou la région.
- Le site web officiel ou le lien de contact.
- Le nom et le prénom du dirigeant (chancelier, recteur ou président).
- Le numéro de téléphone officiel.
-le mail

Contrainte de format STRICTE :
Renvoie UNIQUEMENT un tableau JSON valide (une liste d'objets), sans aucune introduction, explication ou conclusion. Utilise scrupuleusement la structure et les clés suivantes :

[
  {
    "universite": "Nom de l'établissement",
    "region": "Canada, Europe de l'Est ou Vietnam",
    "nom": "Nom de famille du dirigeant",
    "prenom": "Prénom du dirigeant",
    "tel": "Numéro de téléphone (ou null si inconnu)",
    "contact": "URL du site web ou mail de contact",
    "mail": "mail du nom de la personne"
  }
]

Si une information est manquante (comme le téléphone ou les composants du nom), utilise la valeur `null` (sans guillemets) ou une chaîne vide `""`."""

messages = [
    SystemMessage(content=system_prompt),
    HumanMessage(content="Effectue des recherches approfondies sur le web pour identifier les universités dans ces 3 régions et génère le tableau JSON final selon les instructions.")
]


print("🕵️‍♂️ L'agent IA commence ses recherches sur le Web...")

# 3. Boucle d'exécution de l'agent (Recherche Web + Génération)
while True:
    ai_msg = llm.invoke(messages)
    messages.append(ai_msg)
    
    if ai_msg.tool_calls:
        for tool_call in ai_msg.tool_calls:
            if tool_call["name"] == "web_search": # Correction : Appel du bon outil web_search
                print(f"🔍 Recherche en cours sur le web pour : {tool_call['args'].get('query')}...")
                query_result = web_search.invoke(tool_call["args"])
                messages.append(ToolMessage(content=query_result, tool_call_id=tool_call["id"]))
        continue
    else:
        break

raw_output = ai_msg.content

# 4. Extraction du JSON et Sauvegarde en CSV
try:
    if "```json" in raw_output:
        raw_output = raw_output.split("```json")[1].split("```")[0].strip()
    elif "```" in raw_output:
        raw_output = raw_output.split("```")[1].strip()
        
    data_json = json.loads(raw_output)
    
    print("\n✅ Extraction réussie ! Voici le JSON obtenu :")
    print(json.dumps(data_json, indent=4, ensure_ascii=False))
    
    import pandas as pd
    rows = data_json if isinstance(data_json, list) else data_json.get("partenaires", data_json)
    
    df = pd.DataFrame(rows)
    df.to_csv("prospection_universites_web.csv", index=False, encoding="utf-8-sig")
    print("\n📊 Données enregistrées avec succès dans 'prospection_universites_web.csv' !")

except Exception as e:
    print(f"\n❌ Erreur lors du parsing du JSON : {e}")
    print("Voici la réponse brute de l'agent :")
    print(raw_output)