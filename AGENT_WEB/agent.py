import os
import json
import time
import unicodedata
from pathlib import Path
from threading import Lock
from typing import Optional
import re

from dotenv import load_dotenv
from strands import Agent, tool
from strands.models.gemini import GeminiModel
from linkup import LinkupClient
import logging
try:
    from .system_prompt import SYSTEM_PROMPT
except ImportError:
    from system_prompt import SYSTEM_PROMPT
import requests
from strands.agent.conversation_manager import SlidingWindowConversationManager
import csv
from pydantic import BaseModel, Field

PACKAGE_DIR = Path(__file__).resolve().parent
PROJECT_DIR = PACKAGE_DIR.parent

load_dotenv(PROJECT_DIR / ".env")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s"
)

logger = logging.getLogger(__name__)
agent_lock = Lock()
file_lock = Lock()
CACHE_PATH = PROJECT_DIR / "contacts_cache.json"
EMAILS_PATH = PROJECT_DIR / "emails.csv"
EMAILS_FIELDS = ["Pays", "Domaine", "Université", "Prénom", "Nom", "Email", "Source"]
UNIVERSITIES_PATH = PROJECT_DIR / "universities.csv"
UNIVERSITIES_FIELDS = ["Pays", "Domaine", "Université", "Sites web", "Domaine web"]

COUNTRY_ALIASES = {
    "hongrie": "Hungary",
    "canada": "Canada",
    "vietnam": "Vietnam",
    "pologne": "Poland",
    "roumanie": "Romania",
    "bulgarie": "Bulgaria",
    "slovaquie": "Slovakia",
    "republique tcheque": "Czech Republic",
    "republique tchque": "Czech Republic",
    "republique tchèque": "Czech Republic",
    "tchequie": "Czech Republic",
    "tcheque": "Czech Republic",
    "ukraine": "Ukraine",
    "serbie": "Serbia",
    "croatie": "Croatia",
    "lettonie": "Latvia",
    "lituanie": "Lithuania",
    "estonie": "Estonia",
    "royaume uni": "United Kingdom",
    "angleterre": "United Kingdom",
    "etats unis": "United States",
    "etatsunis": "United States",
    "usa": "United States",
}


def _strip_accents(value: str) -> str:
    return "".join(
        c for c in unicodedata.normalize("NFKD", value) if not unicodedata.combining(c)
    )


def normalize_country(country: str) -> str:
    raw = (country or "").strip()
    if not raw:
        return ""
    key = _strip_accents(raw).lower()
    key = " ".join(key.replace("-", " ").replace("_", " ").split())
    return COUNTRY_ALIASES.get(key, raw)

class InternationalContact(BaseModel):
    first_name: str = Field(default="")
    last_name: str = Field(default="")
    email: str = Field(default="")

class InternationalContactList(BaseModel):
    contacts: list[InternationalContact] = Field(default_factory=list)

class UniversityRow(BaseModel):
    name: str = Field(default="")
    website: str = Field(default="")
    domain: str = Field(default="")

class UniversityMatches(BaseModel):
    universities: list[UniversityRow] = Field(default_factory=list)

def _normalize_key(country: str, topic: str, university_name: str) -> str:
    return "|".join(
        [
            (country or "").strip().lower(),
            (topic or "").strip().lower(),
            (university_name or "").strip().lower(),
        ]
    )

def _normalize_email_key(country: str, topic: str, university_name: str, email: str) -> str:
    return "|".join(
        [
            (country or "").strip().lower(),
            (topic or "").strip().lower(),
            (university_name or "").strip().lower(),
            (email or "").strip().lower(),
        ]
    )


def _load_cache() -> dict:
    if not CACHE_PATH.exists():
        return {"version": 1, "items": {}}
    try:
        data = json.loads(CACHE_PATH.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            return {"version": 1, "items": {}}
        if "items" not in data or not isinstance(data["items"], dict):
            data["items"] = {}
        data.setdefault("version", 1)
        return data
    except Exception:
        return {"version": 1, "items": {}}


def _save_cache(data: dict) -> None:
    try:
        CACHE_PATH.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception:
        return


def _read_existing_emails() -> list[dict[str, str]]:
    if not EMAILS_PATH.exists():
        return []
    try:
        with open(EMAILS_PATH, "r", encoding="utf-8-sig", newline="") as csv_file:
            reader = csv.DictReader(csv_file, delimiter=";")
            rows = []
            for row in reader:
                if not isinstance(row, dict):
                    continue
                normalized = {k: (row.get(k) or "").strip() for k in EMAILS_FIELDS}
                rows.append(normalized)
            return rows
    except Exception:
        return []


def _write_emails(rows: list[dict[str, str]]) -> None:
    with open(EMAILS_PATH, "w", newline="", encoding="utf-8-sig") as csv_file:
        writer = csv.DictWriter(csv_file, fieldnames=EMAILS_FIELDS, delimiter=";")
        writer.writeheader()
        writer.writerows(rows)


def _upsert_emails(existing: list[dict[str, str]], new_rows: list[dict[str, str]]) -> list[dict[str, str]]:
    by_key: dict[str, dict[str, str]] = {}
    fallback_by_university: dict[str, list[str]] = {}
    for row in existing:
        email = row.get("Email", "")
        k = _normalize_email_key(row.get("Pays", ""), row.get("Domaine", ""), row.get("Université", ""), email)
        if k.strip("|"):
            by_key[k] = row
            if not row.get("Pays") and not row.get("Domaine") and row.get("Université"):
                uni_key = (row["Université"] or "").strip().lower()
                fallback_by_university.setdefault(uni_key, []).append(k)
    for row in new_rows:
        email = row.get("Email", "")
        k = _normalize_email_key(row.get("Pays", ""), row.get("Domaine", ""), row.get("Université", ""), email)
        if not k.strip("|"):
            continue
        current = by_key.get(k)
        if not current and row.get("Université"):
            uni_key = (row["Université"] or "").strip().lower()
            fallback_keys = fallback_by_university.get(uni_key) or []
            for fk in fallback_keys:
                candidate = by_key.get(fk)
                if candidate and candidate.get("Email") == row.get("Email"):
                    current = candidate
                    by_key.pop(fk, None)
                    break
        if not current:
            by_key[k] = row
            continue
        merged = {field: (row.get(field) or current.get(field) or "") for field in EMAILS_FIELDS}
        if current.get("Email") and not row.get("Email"):
            merged["Email"] = current["Email"]
        by_key[k] = merged
    return list(by_key.values())

def _parse_university_filter(universities) -> list[str]:
    if universities is None:
        return []

    values: list[str] = []
    if isinstance(universities, str):
        values = [universities]
    elif isinstance(universities, list):
        for item in universities:
            if isinstance(item, str):
                values.append(item)
            elif isinstance(item, dict):
                for key in ("name", "Nom", "Université", "university"):
                    v = item.get(key)
                    if isinstance(v, str) and v.strip():
                        values.append(v)
                        break
            else:
                values.append(str(item))
    else:
        values = [str(universities)]

    parts: list[str] = []
    for value in values:
        raw = (value or "").strip()
        if not raw:
            continue
        parts.extend([p.strip() for p in raw.split(",") if p.strip()])

    seen = set()
    result = []
    for p in parts:
        k = p.lower()
        if k not in seen:
            seen.add(k)
            result.append(p)
    return result

def _matches_any(university_name: str, filters: list[str]) -> bool:
    if not filters:
        return True
    name_l = (university_name or "").strip().lower()
    for f in filters:
        f_l = f.strip().lower()
        if f_l and (f_l in name_l or name_l in f_l):
            return True
    return False


def _is_valid_email(value: str) -> bool:
    v = (value or "").strip()
    if not v or "@" not in v:
        return False
    return bool(re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", v))


def _contact_score(email: str, first_name: str = "", last_name: str = "") -> int:
    e = (email or "").strip().lower()
    local = e.split("@", 1)[0] if "@" in e else e
    score = 0

    if first_name.strip() or last_name.strip():
        score += 15

    ri_keywords = [
        "international",
        "relations",
        "global",
        "mobility",
        "erasmus",
        "exchange",
        "partnership",
        "cooperation",
        "outgoing",
        "incoming",
    ]
    for kw in ri_keywords:
        if kw in local:
            score += 25

    generic_bad = [
        "admissions",
        "admission",
        "apply",
        "enquiries",
        "enquiry",
        "info",
        "contact",
        "hello",
        "support",
        "registrar",
        "students",
        "student",
        "general",
        "office",
    ]
    for kw in generic_bad:
        if kw in local:
            score -= 15

    if "@" in e and e.endswith((".edu", ".ac.uk")):
        score += 5

    return score

def _extract_first_url(value) -> str:
    url_regex = re.compile(r"https?://[^\s)>\"]+")

    def from_str(s: str) -> str:
        m = url_regex.search(s)
        return m.group(0) if m else ""

    if value is None:
        return ""
    if isinstance(value, str):
        return from_str(value)

    queue = [value]
    visited_ids = set()
    steps = 0
    while queue and steps < 200:
        current = queue.pop(0)
        steps += 1
        obj_id = id(current)
        if obj_id in visited_ids:
            continue
        visited_ids.add(obj_id)

        if isinstance(current, str):
            url = from_str(current)
            if url:
                return url
            continue

        if isinstance(current, dict):
            for key in ("url", "uri", "link", "source", "sources"):
                v = current.get(key)
                if isinstance(v, str):
                    url = from_str(v)
                    if url:
                        return url
            for v in current.values():
                if isinstance(v, (dict, list, str)):
                    queue.append(v)
            continue

        if isinstance(current, list):
            for v in current:
                if isinstance(v, (dict, list, str)):
                    queue.append(v)
            continue

    return ""

def _extract_emails(value) -> list[str]:
    email_regex = re.compile(r"[a-zA-Z0-9_.+\-]+@[a-zA-Z0-9\-]+\.[a-zA-Z0-9.\-]+")

    def from_str(s: str) -> list[str]:
        found = []
        for m in email_regex.finditer(s):
            raw = m.group(0).strip()
            raw = raw.strip("`'\"()[]{}<>.,;:")
            if raw and raw not in found:
                found.append(raw)
        return found

    if value is None:
        return []
    if isinstance(value, str):
        return from_str(value)

    queue = [value]
    visited_ids = set()
    steps = 0
    found: list[str] = []
    seen = set()

    while queue and steps < 400:
        current = queue.pop(0)
        steps += 1
        obj_id = id(current)
        if obj_id in visited_ids:
            continue
        visited_ids.add(obj_id)

        if isinstance(current, str):
            for e in from_str(current):
                e_l = e.lower()
                if e_l not in seen:
                    seen.add(e_l)
                    found.append(e)
            continue

        if isinstance(current, dict):
            for v in current.values():
                if isinstance(v, (dict, list, str)):
                    queue.append(v)
            continue

        if isinstance(current, list):
            for v in current:
                if isinstance(v, (dict, list, str)):
                    queue.append(v)
            continue

    return found


def _fetch_university_rows(country: str, topic: str = "") -> list[dict[str, str]]:
    country_en = normalize_country(country)
    if not topic:
        response = requests.get(f"http://universities.hipolabs.com/search?country={country_en}")
        response.raise_for_status()
        data = response.json()
        rows = [
            {
                "Nom": u["name"],
                "Sites web": ", ".join(u["web_pages"]),
                "Domaine": (u.get("domains") or [""])[0],
            }
            for u in data
        ]
        if rows:
            return rows

        client = LinkupClient(api_key=os.environ.get("LINKUP_API_KEY"))
        extractor = Agent(model=model)
        result = client.search(
            depth="standard",
            query=f"universities in {country_en} official website",
            output_type="searchResults",
        )
        parsed = extractor(
            f"Extrait des universités en {country_en}. Retourne le nom officiel, le site web officiel et le domaine si possible. Résultats: {result}",
            structured_output_model=UniversityMatches,
        ).structured_output
        return [
            {"Nom": u.name, "Sites web": u.website, "Domaine": u.domain}
            for u in parsed.universities
            if u.name and u.website
        ]

    client = LinkupClient(api_key=os.environ.get("LINKUP_API_KEY"))
    extractor = Agent(model=model)
    result = client.search(depth="standard", query=f"universities in {country_en} for {topic} with official website", output_type="searchResults")
    parsed = extractor(
        f"Extrait uniquement des universités pertinentes pour {topic} en {country_en}. Retourne le nom officiel, le site web officiel et le domaine si possible. Résultats: {result}",
        structured_output_model=UniversityMatches
    ).structured_output
    return [{"Nom": u.name, "Sites web": u.website, "Domaine": u.domain} for u in parsed.universities if u.name and u.website]

gemini_key = os.environ.get("GOOGLE_API_KEY")

model = GeminiModel(
    client_args={
        "api_key": gemini_key,
    },
    
    model_id="gemini-3.1-flash-lite",
    params={
        
        "temperature": 0.7,
        "max_output_tokens": 2048,
        "top_p": 0.9,
        "top_k": 40
    }
)

@tool
def find_universities(country : str, topic : str = "") -> str :
    try :
        country_en = normalize_country(country)
        rows = _fetch_university_rows(country_en, topic)
        csv_rows = [
            {
                "Pays": (country_en or "").strip(),
                "Domaine": ((topic or "").strip() or "général"),
                "Université": (row.get("Nom") or "").strip(),
                "Sites web": (row.get("Sites web") or "").strip(),
                "Domaine web": (row.get("Domaine") or "").strip(),
            }
            for row in rows
        ]
        with open(UNIVERSITIES_PATH, "w", newline="", encoding="utf-8-sig") as csv_file:
            writer = csv.DictWriter(csv_file, fieldnames=UNIVERSITIES_FIELDS, delimiter=";")
            writer.writeheader()
            writer.writerows(csv_rows)
        scope = f" pour le domaine {topic}" if topic else ""
        return f"universities.csv mis à jour avec {len(csv_rows)} université(s) trouvée(s) au {country_en}{scope}."
    except Exception as error :
        return f"Erreur: {error}"

@tool
def web_search(query: str ) -> str :
    logger.info("using web_search tool...")
    """Run a web search and return a concise textual answer.

    Args:
        query: The text query to search for.

    Returns:
        str: A concise answer generated from the search results.
    """
    api_key=os.environ.get("LINKUP_API_KEY")
    client = LinkupClient(api_key=api_key)
    response = client.search(
        depth="deep",
        query=query,
        output_type="searchResults",
       
    )
    
    logger.info("finishing web_search tool...")
    return response



@tool
def find_email(domain : str,first_name : str, last_name) -> str : 
    hunter_key=os.environ.get("HUNTER_API_KEY")
    url = f"https://api.hunter.io/v2/email-finder?domain={domain}&first_name={first_name}&last_name={last_name}&api_key={hunter_key}"
    try : 
        response = requests.get(url)
        response.raise_for_status()
        data = response.json().get("data", {})

        row = {
            "Pays": "",
            "Domaine": (domain or "").strip(),
            "Université": "",
            "Prénom": (data.get("first_name") or "").strip(),
            "Nom": (data.get("last_name") or "").strip(),
            "Email": (data.get("email") or "").strip(),
            "Source": "https://hunter.io/",
        }

        with file_lock:
            existing = _read_existing_emails()
            merged = _upsert_emails(existing, [row])
            _write_emails(merged)

        return f'Prénom: {row["Prénom"]} | Nom: {row["Nom"]} | Email: {row["Email"]}'
    except requests.exceptions.RequestException as error: 
        return f"Erreur: {error}"


@tool
def find_international_contacts(country : str, topic : str = "", universities : str = "", max_universities : int = 5, max_contacts : int = 5, force_refresh : bool = False) -> str :
    try :
        country_en = normalize_country(country)
        client = LinkupClient(api_key=os.environ.get("LINKUP_API_KEY"))
        extractor = Agent(model=model)
        university_filters = _parse_university_filter(universities)
        university_rows = _fetch_university_rows(country_en, topic)
        unique_universities = []
        seen = set()
        for university in university_rows:
            key = (university.get("Nom", "").strip().lower(), university.get("Domaine", "").strip().lower())
            if key not in seen:
                seen.add(key)
                unique_universities.append(university)
        university_rows = unique_universities

        with file_lock:
            existing_rows = _read_existing_emails()
            existing_keys = set()
            for row in existing_rows:
                uni = row.get("Université", "")
                if uni:
                    existing_keys.add(_normalize_key(country_en, topic, uni))
                existing_keys.add(_normalize_key(row.get("Pays", ""), row.get("Domaine", ""), uni))
            cache = _load_cache()

        ttl_days = 14
        now = int(time.time())
        candidates = []
        for university in university_rows:
            university_name = (university.get("Nom") or "").strip()
            if not university_name:
                continue
            if not _matches_any(university_name, university_filters):
                continue
            k = _normalize_key(country_en, topic, university_name)
            cached = cache.get("items", {}).get(k)
            if not force_refresh and isinstance(cached, dict):
                status = cached.get("status")
                last_attempt = int(cached.get("last_attempt", 0) or 0)
                if status == "found_ri":
                    continue
                if status == "found_generic" and last_attempt and (now - last_attempt) < ttl_days * 86400:
                    continue
                if status == "not_found" and last_attempt and (now - last_attempt) < ttl_days * 86400:
                    continue
            if not force_refresh and k in existing_keys:
                continue
            candidates.append(university)

        if max_universities <= 0:
            universities_to_process = candidates
        else:
            universities_to_process = candidates[:max_universities]

        rows: list[dict[str, str]] = []
        per_university_limit = 1 if max_contacts != 0 else 3

        for university in universities_to_process :
            if max_contacts > 0 and len(rows) >= max_contacts:
                break
            try :
                university_name = university["Nom"]
                domain = university.get("Domaine", "")
                query = (
                    f'site:{domain} "{university_name}" '
                    f'("international relations" OR "international office" OR erasmus) '
                    f'(email OR contact)'
                ) if domain else (
                    f'"{university_name}" {country_en} {topic} '
                    f'("international relations" OR "international office" OR erasmus) '
                    f'(email OR contact)'
                )
                depth = "deep" if university_filters or max_universities <= 2 else "standard"
                search_result = client.search(depth=depth, query=query, output_type="searchResults")
                source_url = _extract_first_url(search_result) or (f"https://{domain}/" if domain else "")
                parsed = extractor(
                    "Extrait jusqu'à 3 contacts/emails de relations internationales depuis ces résultats. "
                    "Inclure les emails nominatif (prenom.nom@) OU les emails de service (international@, erasmus@, mobility@...). "
                    "Priorité absolue aux emails liés aux relations internationales (international, mobility, erasmus, global). "
                    "Évite admissions/info/contact sauf si aucun email RI n'existe. "
                    "Si tu ne trouves rien, retourne une liste vide.\n"
                    f"Université: {university_name}\n"
                    f"Résultats: {search_result}",
                    structured_output_model=InternationalContactList,
                ).structured_output

                candidates_rows: list[tuple[int, dict[str, str]]] = []
                for contact in (parsed.contacts or [])[:6]:
                    email = (contact.email or "").strip()
                    first_name = (contact.first_name or "").strip()
                    last_name = (contact.last_name or "").strip()
                    if not _is_valid_email(email):
                        continue
                    score = _contact_score(email=email, first_name=first_name, last_name=last_name)
                    candidates_rows.append(
                        (
                            score,
                            {
                                "Pays": (country_en or "").strip(),
                                "Domaine": (topic or "").strip(),
                                "Université": (university_name or "").strip(),
                                "Prénom": first_name,
                                "Nom": last_name,
                                "Email": email,
                                "Source": source_url,
                            },
                        )
                    )

                if not candidates_rows:
                    for email in _extract_emails(search_result)[:12]:
                        email = (email or "").strip()
                        if not _is_valid_email(email):
                            continue
                        score = _contact_score(email=email, first_name="", last_name="")
                        candidates_rows.append(
                            (
                                score,
                                {
                                    "Pays": (country_en or "").strip(),
                                    "Domaine": (topic or "").strip(),
                                    "Université": (university_name or "").strip(),
                                    "Prénom": "",
                                    "Nom": "",
                                    "Email": email,
                                    "Source": source_url,
                                },
                            )
                        )

                candidates_rows.sort(key=lambda x: x[0], reverse=True)
                added = 0
                best_score: Optional[int] = None
                for score, row in candidates_rows:
                    if max_contacts > 0 and len(rows) >= max_contacts:
                        break
                    rows.append(row)
                    added += 1
                    if best_score is None:
                        best_score = score
                    if added >= per_university_limit:
                        break

                if added > 0:
                    k = _normalize_key(country_en, topic, university_name)
                    status = "found_ri" if (best_score is not None and best_score >= 10) else "found_generic"
                    cache.setdefault("items", {})[k] = {
                        "status": status,
                        "last_attempt": now,
                        "best_score": best_score,
                    }
                else:
                    k = _normalize_key(country_en, topic, university_name)
                    cache.setdefault("items", {})[k] = {
                        "status": "not_found",
                        "last_attempt": now,
                    }
            except Exception as error :
                logger.warning(f"Impossible de traiter {university.get('Nom', 'université inconnue')} : {error}")

        with file_lock:
            existing_rows = _read_existing_emails()
            merged = _upsert_emails(existing_rows, rows)
            _write_emails(merged)
            _save_cache(cache)

        scope = f" pour le domaine {topic}" if topic else ""
        skipped = max(0, len(university_rows) - len(candidates))
        return (
            f"emails.csv mis à jour avec {len(rows)} nouveau(x) contact(s) trouvé(s) "
            f"sur {len(universities_to_process)} université(s) analysée(s) au {country_en}{scope}. "
            f"{skipped} université(s) ignorée(s) (déjà traitées ou en cache)."
        )
    except Exception as error :
        return f"Erreur: {error}"

@tool
def email_verifier(email : str) -> str :
    hunter_key=os.environ.get("HUNTER_API_KEY")
    url = f"https://api.hunter.io/v2/email-verifier?email={email}&api_key={hunter_key}"
    try :
        response = requests.get(url)
        response.raise_for_status()
        return response.text
    except requests.exceptions.RequestException as error :
        return f"Erreur: {error}"


def build_agent(window_size: int = 10) -> Agent:
    conversation_manager = SlidingWindowConversationManager(window_size=window_size)
    return Agent(
        model=model,
        conversation_manager=conversation_manager,
        tools=[find_universities, web_search, find_email, find_international_contacts, email_verifier],
        system_prompt=SYSTEM_PROMPT,
    )


def _build_prompt_from_messages(messages: list[dict[str, str]]) -> str:
    normalized_messages = []
    for message in messages[-15:]:
        role = message.get("role", "user")
        content = message.get("content", "").strip()
        if content:
            normalized_messages.append({"role": role, "content": content})

    if not normalized_messages:
        return "Bonjour."

    if len(normalized_messages) == 1 and normalized_messages[0]["role"] == "user":
        return normalized_messages[0]["content"]

    history_lines = []
    for message in normalized_messages:
        role_label = "Utilisateur" if message["role"] == "user" else "Assistant"
        history_lines.append(f"{role_label}: {message['content']}")

    return (
        "Voici l'historique recent de la conversation.\n"
        "Reponds uniquement au dernier message utilisateur en tenant compte du contexte.\n\n"
        + "\n".join(history_lines)
    )


def run_agent(messages: list[dict[str, str]] | str) -> str:
    prompt = messages if isinstance(messages, str) else _build_prompt_from_messages(messages)
    with agent_lock:
        result = build_agent()(prompt)
    reply = str(result).strip()
    return reply or "Je n'ai pas pu generer de reponse."


def run_cli() -> None:
    cli_agent = build_agent()
    while True:
        prompt = input("\nParlez a l'agent : ")
        if prompt.lower() == "q":
            print("Goodbye !")
            break
        result = cli_agent(prompt)
        print(str(result).strip())


if __name__ == "__main__":
    run_cli()
