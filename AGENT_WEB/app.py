import re
from pathlib import Path
from typing import Literal

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

try:
    from .agent import run_agent
except ImportError:
    from agent import run_agent

PACKAGE_DIR = Path(__file__).resolve().parent
PROJECT_DIR = PACKAGE_DIR.parent
UI_DIR = PACKAGE_DIR / "UI"
CSV_FILES = {
    "universities": PROJECT_DIR / "universities.csv",
    "emails": PROJECT_DIR / "emails.csv",
}


class NoCacheStaticFiles(StaticFiles):
    async def get_response(self, path: str, scope):
        response = await super().get_response(path, scope)
        response.headers["Cache-Control"] = "no-store"
        return response

app = FastAPI(title="SAE S2.06 Agent API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class ChatMessage(BaseModel):
    role: Literal["user", "assistant"]
    content: str = Field(min_length=1, max_length=4000)


class ChatRequest(BaseModel):
    messages: list[ChatMessage] = Field(min_length=1, max_length=20)


class TitleRequest(BaseModel):
    message: str = Field(min_length=1, max_length=4000)


def generate_title(message: str) -> str:
    words = re.findall(r"[A-Za-zÀ-ÿ0-9']+", message.strip())
    if not words:
        return "Nouveau chat"
    title = " ".join(words[:6])
    if len(words) > 6:
        title += "..."
    return title[:60]


def get_csv_info() -> dict[str, dict[str, str | bool]]:
    info = {}
    for key, path in CSV_FILES.items():
        info[key] = {
            "exists": path.exists(),
            "filename": path.name,
            "download_url": f"/api/files/{key}",
        }
    return info


@app.get("/health")
def healthcheck() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/api/chat")
def chat(request: ChatRequest, http_request: Request) -> dict:
    try:
        reply = run_agent([message.model_dump() for message in request.messages])
    except Exception as error:
        raise HTTPException(status_code=500, detail=str(error)) from error

    files_info = get_csv_info()
    base_url = str(http_request.base_url).rstrip("/")
    download_lines = []
    if files_info["universities"]["exists"]:
        download_lines.append(f"- [Télécharger universities.csv]({base_url}{files_info['universities']['download_url']})")
    if files_info["emails"]["exists"]:
        download_lines.append(f"- [Télécharger emails.csv]({base_url}{files_info['emails']['download_url']})")
    if download_lines:
        reply = reply.rstrip() + "\n\nFichiers CSV :\n" + "\n".join(download_lines)

    return {
        "content": [
            {"text": reply}
        ],
        "files": files_info,
    }


@app.post("/api/title")
def title(request: TitleRequest) -> dict[str, str]:
    return {"title": generate_title(request.message)}


@app.get("/api/files")
def files() -> dict[str, dict[str, str | bool]]:
    return get_csv_info()


@app.get("/api/files/{file_key}")
def download_file(file_key: str) -> FileResponse:
    file_path = CSV_FILES.get(file_key)
    if not file_path:
        raise HTTPException(status_code=404, detail="Fichier inconnu.")
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="Fichier non disponible.")
    return FileResponse(file_path, filename=file_path.name, media_type="text/csv")


@app.get("/")
def index() -> FileResponse:
    return FileResponse(UI_DIR / "Vchat.html", headers={"Cache-Control": "no-store"})

@app.get("/Vchat.html")
def vchat() -> FileResponse:
    return FileResponse(UI_DIR / "Vchat.html", headers={"Cache-Control": "no-store"})


app.mount("/", NoCacheStaticFiles(directory=UI_DIR), name="ui")
