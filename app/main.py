import os
from fastapi import FastAPI, BackgroundTasks, Depends
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from typing import Optional
from sqlalchemy.orm import Session
from app.database import init_db, SessionLocal, AgentAccount, CampaignLog
from app.worker import dispatch_swarm

# Ensure the screenshots folder exists before mounting
os.makedirs("app/screenshots", exist_ok=True)

app = FastAPI(title="Multi-Agent Engagement Engine Prototype")

# Mount the screenshots folder so the browser can load the images
app.mount("/screenshots", StaticFiles(directory="app/screenshots"), name="screenshots")

@app.on_event("startup")
def on_startup():
    init_db()
    db = SessionLocal()
    if db.query(AgentAccount).count() == 0:
        seed_agents = [
            AgentAccount(username="x_agent_alpha", platform="x", persona="Sharp tech minimalist, writes 1-line punchy observations.", status="mock_ready"),
            AgentAccount(username="fb_agent_gamma", platform="facebook", persona="Warm community supporter, enthusiastic and conversational.", status="mock_ready"),
        ]
        db.add_all(seed_agents)
        db.commit()
    db.close()

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

class AccountCreate(BaseModel):
    username: str
    platform: str
    persona: str
    proxy_url: Optional[str] = None
    cookies_json: Optional[str] = None

class DispatchPayload(BaseModel):
    target_url: str
    platform: str = "x"
    max_agents: int = 2
    tone: str = "Supportive, sharp, and organic"
    dry_run: bool = True

@app.post("/api/accounts")
def add_or_update_account(payload: AccountCreate, db: Session = Depends(get_db)):
    existing = db.query(AgentAccount).filter(AgentAccount.username == payload.username).first()
    status_val = "live_ready" if payload.cookies_json else "mock_ready"
    if existing:
        existing.platform, existing.persona, existing.cookies_json, existing.status = payload.platform, payload.persona, payload.cookies_json, status_val
    else:
        db.add(AgentAccount(**payload.dict(), status=status_val))
    db.commit()
    return {"message": "Account saved"}

@app.post("/api/dispatch")
async def trigger_campaign(payload: DispatchPayload, bg: BackgroundTasks):
    bg.add_task(dispatch_swarm, payload.target_url, payload.platform, payload.max_agents, payload.tone, payload.dry_run)
    return {"status": "dispatched"}

@app.get("/api/logs")
def get_logs(db: Session = Depends(get_db)):
    return db.query(CampaignLog).order_by(CampaignLog.id.desc()).limit(25).all()

@app.get("/", response_class=HTMLResponse)
def dashboard_ui():
    return """
    <!DOCTYPE html>
    <html>
    <head>
        <title>Swarm Command Center</title>
        <script src="https://cdn.tailwindcss.com"></script>
    </head>
    <body class="bg-zinc-950 text-zinc-100 min-h-screen p-8 font-sans">
        <div class="max-w-5xl mx-auto space-y-8">
            <h1 class="text-2xl font-bold border-b border-zinc-800 pb-4">Multi-Agent Social Fleet</h1>
            <div class="grid grid-cols-1 md:grid-cols-2 gap-6">
                <!-- Dispatch Panel -->
                <div class="bg-zinc-900 border border-zinc-800 rounded-xl p-6 space-y-4">
                    <h2 class="text-lg font-semibold">1. Dispatch Swarm</h2>
                    <input id="url" type="text" placeholder="Paste Post URL..." class="w-full bg-zinc-950 border border-zinc-800 rounded-lg p-2.5 text-sm">
                    <div class="grid grid-cols-2 gap-3">
                        <select id="platform" class="bg-zinc-950 border border-zinc-800 rounded-lg p-2.5 text-sm"><option value="x">X (Twitter)</option><option value="facebook">Facebook</option></select>
                        <input id="count" type="number" value="1" class="bg-zinc-950 border border-zinc-800 rounded-lg p-2.5 text-sm" placeholder="Agents">
                    </div>
                    <label class="flex items-center space-x-2 text-xs text-zinc-400">
                        <input id="dry_run" type="checkbox" checked class="rounded bg-zinc-950"><span>Dry-Run Mode</span>
                    </label>
                    <button onclick="dispatch()" class="w-full bg-indigo-600 hover:bg-indigo-500 py-2.5 rounded-lg text-sm transition">Deploy Agents</button>
                </div>
                <!-- Account Panel -->
                <div class="bg-zinc-900 border border-zinc-800 rounded-xl p-6 space-y-3">
                    <h2 class="text-lg font-semibold">2. Load Real Cookies</h2>
                    <div class="grid grid-cols-2 gap-3">
                        <input id="acc_user" type="text" placeholder="Username" class="bg-zinc-950 border border-zinc-800 rounded-lg p-2 text-sm">
                        <select id="acc_plat" class="bg-zinc-950 border border-zinc-800 rounded-lg p-2 text-sm"><option value="x">X (Twitter)</option><option value="facebook">Facebook</option></select>
                    </div>
                    <input id="acc_persona" type="text" placeholder="Persona description" class="w-full bg-zinc-950 border border-zinc-800 rounded-lg p-2 text-sm">
                    <textarea id="acc_cookies" rows="2" placeholder="Paste exported JSON cookies here" class="w-full bg-zinc-950 border border-zinc-800 rounded-lg p-2 text-xs font-mono"></textarea>
                    <button onclick="addAccount()" class="w-full bg-zinc-800 hover:bg-zinc-700 py-2 rounded-lg text-sm transition">Save to Vault</button>
                </div>
            </div>
            <!-- Live Feed -->
            <div class="bg-zinc-900 border border-zinc-800 rounded-xl p-6 space-y-4">
                <h2 class="text-lg font-semibold">Live Activity Logs</h2>
                <div id="logs" class="space-y-2 text-sm font-mono text-zinc-300">Loading...</div>
            </div>
        </div>
        <script>
            async function dispatch() {
                const payload = { target_url: document.getElementById('url').value, platform: document.getElementById('platform').value, max_agents: parseInt(document.getElementById('count').value), tone: "organic", dry_run: document.getElementById('dry_run').checked };
                await fetch('/api/dispatch', {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(payload)});
                setTimeout(loadData, 4000);
            }
            async function addAccount() {
                const payload = { username: document.getElementById('acc_user').value, platform: document.getElementById('acc_plat').value, persona: document.getElementById('acc_persona').value, cookies_json: document.getElementById('acc_cookies').value };
                await fetch('/api/accounts', {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(payload)});
                loadData();
            }
            async function loadData() {
                const res = await fetch('/api/logs');
                const logs = await res.json();
                document.getElementById('logs').innerHTML = logs.map(l => {
                    // Fix path string to serve from /screenshots route
                    let imgHtml = '';
                    if (l.screenshot_path) {
                        const publicPath = l.screenshot_path.replace('app/screenshots/', '/screenshots/');
                        imgHtml = `<a href="${publicPath}" target="_blank" class="text-indigo-400 hover:underline inline-block mt-2 font-bold">📸 View Real Screenshot</a>`;
                    }
                    return `<div class="p-3 bg-zinc-950 border border-zinc-800 rounded-lg">
                        <div class="flex justify-between text-xs text-zinc-400 mb-1">
                            <span>[${l.platform.toUpperCase()}] <b>${l.agent_username}</b></span>
                            <span class="${l.action_status.includes('error') ? 'text-red-400' : 'text-emerald-400'}">${l.action_status}</span>
                        </div>
                        <div class="text-zinc-100">"${l.generated_comment}"</div>
                        ${imgHtml}
                    </div>`;
                }).join('');
            }
            loadData(); setInterval(loadData, 5000);
        </script>
    </body>
    </html>
    """