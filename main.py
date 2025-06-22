from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from github import Github
from github.GithubException import GithubException, UnknownObjectException
import requests, time, os

# Load environment variables from .env when running locally
from dotenv import load_dotenv
load_dotenv()

app = FastAPI()

# Read GitHub token from environment variable
GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN")
if not GITHUB_TOKEN:
    raise RuntimeError("Missing GITHUB_TOKEN environment variable. Please add it to your .env or Render environment.")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["POST", "OPTIONS"],
    allow_headers=["*"],
)

class DeployRequest(BaseModel):
    repoName: str  # repository name to create/update
    html: str      # HTML content to push

@app.post("/deploy")
async def deploy(req: DeployRequest):
    html = req.html
    if not html.strip():
        raise HTTPException(status_code=400, detail="Empty HTML content provided")

    # Initialize GitHub client with token from environment
    g = Github(GITHUB_TOKEN)
    try:
        user = g.get_user()
    except Exception:
        raise HTTPException(status_code=401, detail="Invalid GitHub token")

    username = user.login
    repo_name = req.repoName

    # Get or create the repository
    try:
        repo = user.get_repo(repo_name)
    except GithubException as e:
        if e.status == 404:
            repo = user.create_repo(name=repo_name, auto_init=True)
        else:
            raise HTTPException(status_code=400, detail=f"Repo access error: {e}")

    time.sleep(2)  # brief pause before file operations

    # Push or update index.html
    try:
        existing = repo.get_contents("index.html", ref="main")
        repo.update_file(
            path="index.html",
            message="Update index.html",
            content=html,
            sha=existing.sha,
            branch="main"
        )
    except UnknownObjectException:
        repo.create_file(
            path="index.html",
            message="Add index.html",
            content=html,
            branch="main"
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to push index.html: {e}")

    # Enable GitHub Pages
    pages_api = f"https://api.github.com/repos/{username}/{repo_name}/pages"
    headers = {
        "Authorization": f"Bearer {GITHUB_TOKEN}",
        "Accept": "application/vnd.github+json"
    }
    payload = {"source": {"branch": "main", "path": "/"}}
    resp = requests.post(pages_api, headers=headers, json=payload)
    if resp.status_code not in (201, 204):
        raise HTTPException(
            status_code=500,
            detail=f"Enabling Pages failed ({resp.status_code}): {resp.text}"
        )

    # Fetch GitHub Pages URL
    info = requests.get(pages_api, headers=headers)
    if info.status_code != 200:
        raise HTTPException(
            status_code=500,
            detail=f"Fetching Pages info failed ({info.status_code}): {info.text}"
        )
    html_url = info.json().get("html_url")
    if not html_url:
        raise HTTPException(status_code=500, detail="No html_url in Pages response")

    return {"url": html_url}

if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run("main:app", host="0.0.0.0", port=port, reload=True)
