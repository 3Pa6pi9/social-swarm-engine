import asyncio
import json
import random
import os
import urllib.request
import gradio as gr
from playwright.async_api import async_playwright
from playwright_stealth import Stealth

VAULT_FILE = "swarm_vault.json"

# ==========================================
# VAULT & STATE MANAGEMENT (CRUD)
# ==========================================
def load_vault():
    if os.path.exists(VAULT_FILE):
        try:
            with open(VAULT_FILE, "r") as f:
                vault = json.load(f)
                if "Squads" not in vault: vault["Squads"] = ["Alpha", "Bravo", "Charlie"]
                if "Targets" not in vault: vault["Targets"] = []
                for p in ["Facebook", "X (Twitter)"]:
                    for a in vault.get(p, []):
                        if "status" not in a: a["status"] = "ACTIVE"
                        if "proxy" not in a: a["proxy"] = ""
                return vault
        except: pass
    return {"Facebook": [], "X (Twitter)": [], "Squads": ["Alpha", "Bravo", "Charlie"], "Targets": []}

def save_vault(vault):
    with open(VAULT_FILE, "w") as f:
        json.dump(vault, f, indent=4)

def update_agent_cookie(platform, agent_name, new_cookies_list):
    vault = load_vault()
    agent = next((b for b in vault[platform] if b["name"] == agent_name), None)
    if agent:
        agent["cookie"] = json.dumps(new_cookies_list)
        save_vault(vault)

def register_agent(platform, name, cookie_str, proxy_mode, proxy_custom):
    if not name or not cookie_str: return "Error: Name and Cookie required.", gr.update(), gr.update(), gr.update()
    try: json.loads(cookie_str)
    except Exception as e: return f"Error: Invalid Cookie JSON.", gr.update(), gr.update(), gr.update()
        
    vault = load_vault()
    if any(b["name"] == name for b in vault[platform]):
        return f"Error: Agent [{name}] already exists. Use Update.", gr.update(), gr.update(), gr.update()
        
    if proxy_mode == "Auto-Free Scraper": final_proxy = "AUTO_FREE"
    elif proxy_mode == "Custom Proxy": final_proxy = proxy_custom.strip()
    else: final_proxy = ""

    vault[platform].append({
        "name": name, 
        "squad": "Unassigned", 
        "cookie": cookie_str, 
        "proxy": final_proxy,
        "status": "ACTIVE"
    })
    save_vault(vault)
    choices = [b["name"] for b in vault[platform]]
    return f"Success: Registered agent [{name}].", gr.update(choices=choices), gr.update(choices=choices), gr.update(choices=choices)

def update_agent(platform, old_name, new_name, new_cookie_str, proxy_mode, proxy_custom):
    if not old_name: return "Error: Select an agent to update.", gr.update(), gr.update(), gr.update()
    vault = load_vault()
    agent = next((b for b in vault[platform] if b["name"] == old_name), None)
    if not agent: return "Error: Agent not found.", gr.update(), gr.update(), gr.update()

    final_name = new_name.strip() if new_name.strip() else old_name
    if final_name != old_name and any(b["name"] == final_name for b in vault[platform]):
        return f"Error: Name '{final_name}' is already taken.", gr.update(), gr.update(), gr.update()

    if new_cookie_str.strip():
        try: json.loads(new_cookie_str)
        except Exception as e: return f"Error: Invalid Cookie JSON.", gr.update(), gr.update(), gr.update()
        agent["cookie"] = new_cookie_str
        agent["status"] = "ACTIVE"

    if proxy_mode == "Auto-Free Scraper": agent["proxy"] = "AUTO_FREE"
    elif proxy_mode == "Custom Proxy": agent["proxy"] = proxy_custom.strip()
    elif proxy_mode == "Raw IP": agent["proxy"] = ""

    agent["name"] = final_name
    save_vault(vault)
    choices = [b["name"] for b in vault[platform]]
    return f"Success: Agent updated to [{final_name}].", gr.update(choices=choices), gr.update(choices=choices), gr.update(choices=choices)

def delete_agent(platform, name):
    if not name: return "Error: Select an agent to delete.", gr.update(), gr.update(), gr.update()
    vault = load_vault()
    vault[platform] = [b for b in vault[platform] if b["name"] != name]
    save_vault(vault)
    choices = [b["name"] for b in vault[platform]]
    return f"Success: Agent [{name}] purged.", gr.update(choices=choices), gr.update(choices=choices), gr.update(choices=choices)

def create_squad(new_squad_name):
    if not new_squad_name: return "Error: Squad name required.", gr.update(), gr.update(), gr.update()
    vault = load_vault()
    if new_squad_name in vault["Squads"]: return "Squad already exists.", gr.update(), gr.update(), gr.update()
    vault["Squads"].append(new_squad_name)
    save_vault(vault)
    choices = vault["Squads"]
    return f"Success: Squad '{new_squad_name}' created.", gr.update(choices=choices), gr.update(choices=["ALL SQUADS"] + choices), gr.update(choices=choices)

def delete_squad(squad_name):
    if not squad_name: return "Error: Select a squad to delete.", gr.update(), gr.update(), gr.update()
    vault = load_vault()
    if squad_name in vault["Squads"]:
        vault["Squads"].remove(squad_name)
        for p in ["Facebook", "X (Twitter)"]:
            for bot in vault[p]:
                if bot.get("squad") == squad_name: bot["squad"] = "Unassigned"
        save_vault(vault)
    choices = vault["Squads"]
    return f"Success: Squad '{squad_name}' dismantled.", gr.update(choices=choices), gr.update(choices=["ALL SQUADS"] + choices), gr.update(choices=choices)

def assign_multiple_to_squad(platform, selected_agents, squad_name):
    if not selected_agents or not squad_name: return "Error: Select agent(s) and a squad.", get_squad_roster()
    vault = load_vault()
    count = 0
    for agent_name in selected_agents:
        agent = next((b for b in vault[platform] if b["name"] == agent_name), None)
        if agent:
            agent["squad"] = squad_name
            count += 1
    save_vault(vault)
    return f"Success: Moved {count} agents to Squad {squad_name}.", get_squad_roster()

def save_target(target_name, target_url):
    if not target_name or not target_url: return "Error: Name and URL required.", gr.update(), gr.update()
    vault = load_vault()
    vault["Targets"].append({"name": target_name, "url": target_url})
    save_vault(vault)
    choices = [f"{t['name']} ({t['url']})" for t in vault["Targets"]]
    return f"Success: Target '{target_name}' injected.", gr.update(choices=choices), gr.update(choices=choices)

def delete_target(target_entry):
    if not target_entry: return "Error: Select a target.", gr.update(), gr.update()
    vault = load_vault()
    url_part = target_entry.split("(")[-1].replace(")", "").strip()
    vault["Targets"] = [t for t in vault["Targets"] if t["url"] != url_part]
    save_vault(vault)
    choices = [f"{t['name']} ({t['url']})" for t in vault["Targets"]]
    return f"Success: Target removed.", gr.update(choices=choices), gr.update(choices=choices)

def get_squad_roster():
    vault = load_vault()
    lines = []
    for squad in vault["Squads"] + ["Unassigned"]:
        squad_agents = []
        for plat in ["Facebook", "X (Twitter)"]:
            for bot in vault[plat]:
                if bot.get("squad", "Unassigned") == squad:
                    status_flag = "🟢 ACTIVE" if bot.get("status", "ACTIVE") == "ACTIVE" else "🔴 BURNED"
                    proxy_val = bot.get("proxy", "")
                    if proxy_val == "AUTO_FREE": proxy_flag = "🌐 Scavenger Proxy"
                    elif proxy_val: proxy_flag = "🛡️ Custom Proxy"
                    else: proxy_flag = "⚠️ Raw IP"
                    squad_agents.append(f"{bot['name']} ({plat}) - {status_flag} - {proxy_flag}")
        if squad_agents:
            lines.append(f"=== {squad.upper()} SQUAD ===")
            for a in squad_agents: lines.append(f" • {a}")
            lines.append("")
    return "\n".join(lines) if lines else "Vault is completely empty."

def get_agent_dropdowns(platform):
    vault = load_vault()
    choices = [b["name"] for b in vault[platform]]
    return gr.update(choices=choices), gr.update(choices=choices), gr.update(choices=choices)

def toggle_deploy_mode(mode, platform):
    vault = load_vault()
    if mode == "Individual Agent": return gr.update(visible=False), gr.update(visible=True, choices=[b["name"] for b in vault[platform]])
    else: return gr.update(visible=True), gr.update(visible=False)

def flag_agent_burned(platform, agent_name):
    vault = load_vault()
    agent = next((b for b in vault[platform] if b["name"] == agent_name), None)
    if agent:
        agent["status"] = "BURNED"
        save_vault(vault)

# ==========================================
# DIY AUTO-FREE PROXY SCAVENGER
# ==========================================
def fetch_auto_free_proxies():
    try:
        url = "https://raw.githubusercontent.com/TheSpeedX/PROXY-List/master/http.txt"
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req, timeout=5) as response:
            data = response.read().decode('utf-8').splitlines()
            return [f"http://{p.strip()}" for p in data if ":" in p]
    except Exception: return []

def get_random_proxy(proxy_str):
    if not proxy_str: return None
    if proxy_str.strip().upper() == "AUTO_FREE":
        proxies = fetch_auto_free_proxies()
        return random.choice(proxies) if proxies else None
    proxies = [p.strip() for p in proxy_str.replace(',', '\n').split('\n') if p.strip()]
    return random.choice(proxies) if proxies else None

# ==========================================
# 3 BOT ARCHETYPES (SAFETY, SCOUTING, ENGAGING)
# ==========================================
class SafetyBot:
    """The Architect: Calculates environmental masks, hardware profiles, and geolocations."""
    @staticmethod
    def generate_mask(device_mode, proxy_str):
        is_mobile = device_mode == "Mobile (iPhone 13)"
        selected_proxy = get_random_proxy(proxy_str)
        
        context_kwargs = {
            "locale": "en-US", 
            "timezone_id": "Africa/Addis_Ababa", 
            "record_video_dir": "videos/"
        }
        
        if is_mobile:
            context_kwargs.update({
                "viewport": {"width": 390, "height": 844},
                "user_agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 16_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.0 Mobile/15E148 Safari/604.1",
                "is_mobile": True,
                "has_touch": True
            })
        else:
            context_kwargs.update({
                "viewport": {"width": 1920, "height": 1080}, 
                "user_agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            })
            
        if selected_proxy: 
            context_kwargs["proxy"] = {"server": selected_proxy}
            
        return context_kwargs, selected_proxy

class ScoutingBot:
    """The Recon Unit: Navigates unauthenticated public profile URLs to harvest metrics and map structure."""
    @staticmethod
    async def scout_target(target_url):
        status_log = [f"[ScoutingBot] Initiating unauthenticated recon on: {target_url}"]
        async with Stealth().use_async(async_playwright()) as p:
            browser = await p.chromium.launch(headless=True, args=["--disable-blink-features=AutomationControlled", "--no-sandbox"])
            context = await browser.new_context(viewport={"width": 1280, "height": 800})
            page = await context.new_page()
            try:
                await page.goto(target_url, wait_until="domcontentloaded", timeout=90000)
                await asyncio.sleep(5)
                title = await page.title()
                snippet = await page.inner_text("body")
                clean_snippet = " ".join(snippet.split())[:400]
                status_log.append(f"[ScoutingBot] Target Title: {title}")
                status_log.append(f"[ScoutingBot] Page Content Preview: {clean_snippet}...")
                status_log.append("[ScoutingBot] Recon complete. Target verified safe for engagement.")
            except Exception as e:
                status_log.append(f"[ScoutingBot] Recon error or obstruction: {str(e)}")
            finally:
                await context.close()
                await browser.close()
        return "\n".join(status_log)

class EngagingBot:
    """The Operator: Executes authenticated, humanized actions with full hardware masking."""
    @staticmethod
    async def run_fb_bot(target_url, action, comment_text, device_mode, cookie_json_str, proxy_pool_str, bot_name):
        os.makedirs("videos", exist_ok=True)
        status_log = [f"[EngagingBot: {bot_name}] FB Hunter-Seeker Booting..."]
        
        context_kwargs, selected_proxy = SafetyBot.generate_mask(device_mode, proxy_pool_str)
        if selected_proxy: 
            status_log.append(f"[{bot_name}] Tunneling via Proxy: {selected_proxy.split('@')[-1] if '@' in selected_proxy else selected_proxy}")
        
        video_path = None
        
        async with Stealth().use_async(async_playwright()) as p:
            browser = await p.chromium.launch(headless=True, args=["--disable-blink-features=AutomationControlled", "--no-sandbox"])
            context = await browser.new_context(**context_kwargs)
            
            try:
                raw_cookies = json.loads(cookie_json_str)
                await context.add_cookies([{"name": c["name"], "value": c["value"], "domain": c.get("domain", ".facebook.com"), "path": c.get("path", "/")} for c in raw_cookies])
            except Exception as e:
                await browser.close()
                return f"[Error: {bot_name}] Cookie Fault: {str(e)}", "BURNED", None

            page = await context.new_page()
            
            try:
                status_log.append(f"[{bot_name}] Warming session on Home Feed...")
                await page.goto("https://www.facebook.com", wait_until="domcontentloaded", timeout=90000)
                await asyncio.sleep(random.uniform(4, 7))
                await page.mouse.wheel(0, random.randint(300, 800))
                await asyncio.sleep(random.uniform(3, 5))

                if await page.locator('input[name="email"], input[name="pass"], [data-sigil="login_password_step"]').count() > 0:
                    status_log.append(f"[Error: {bot_name}] Session Hijack Defense Triggered. Kicked to Login.")
                    raise Exception("Session Invalidated")

                # Force clean mobile view
                if "facebook.com" in target_url:
                    target_url = target_url.replace("www.facebook.com", "m.facebook.com").replace("web.facebook.com", "m.facebook.com")

                status_log.append(f"[{bot_name}] Navigating to mobile target URL...")
                await page.goto(target_url, wait_until="domcontentloaded", timeout=90000)
                await asyncio.sleep(random.uniform(4, 6))

                # Robust Mobile Like Selector with Explicit Wait
                if action in ["Like", "Both"]:
                    status_log.append(f"[{bot_name}] Waiting for mobile Like button to render...")
                    try:
                        like_selector = '[data-sigil="like_link"], [aria-label*="Like"], button:has-text("Like"), a:has-text("Like")'
                        await page.wait_for_selector(like_selector, timeout=10000)
                        like_btn = page.locator(like_selector).first
                        await like_btn.click(force=True)
                        status_log.append(f"[{bot_name}] Target Liked successfully!")
                        await asyncio.sleep(2)
                    except Exception as like_err:
                        status_log.append(f"[{bot_name}] Like action skipped: {str(like_err)}")

                # Comment action
                if action in ["Comment", "Both"] and comment_text:
                    status_log.append(f"[{bot_name}] Looking for comment trigger...")
                    comment_trigger = page.locator('text="Write a comment", [aria-label="Comment"], [data-sigil*="comment"]').first
                    if await comment_trigger.is_visible():
                        await comment_trigger.click(force=True)
                        await asyncio.sleep(2)
                    
                    input_box = page.locator('textarea[name="comment_text"], input[name="comment_text"], div[contenteditable="true"]').first
                    if await input_box.isVisible():
                        await input_box.click(force=True)
                        await asyncio.sleep(1)
                        await page.keyboard.type(comment_text, delay=random.randint(65, 120))
                        await asyncio.sleep(2)

                        submit_btn = page.locator('button[type="submit"], input[type="submit"], [data-sigil*="touchable"]').last
                        if await submit_btn.isVisible():
                            await submit_btn.click(force=True)
                            status_log.append(f"[{bot_name}] Comment payload successfully delivered!")
                        else:
                            await page.keyboard.press("Enter")
                            status_log.append(f"[{bot_name}] Comment payload delivered via keyboard override.")
                        await asyncio.sleep(3)
                    else:
                        status_log.append(f"[{bot_name}] Warning: Comment box failed to mount.")
                        
                final_cookies = await context.cookies()
                update_agent_cookie("Facebook", bot_name, final_cookies)
                status_log.append(f"[{bot_name}] Rotated session tokens synced to Vault.")
                final_status = "SUCCESS"
                
            except Exception as e:
                error_msg = str(e)
                if "Timeout" in error_msg or "Target closed" in error_msg or "net::ERR" in error_msg:
                    status_log.append(f"[{bot_name}] Mission Aborted (Timeout). Cookie is SAFE.")
                    final_status = "ACTIVE"
                else:
                    status_log.append(f"[{bot_name}] Mission Aborted: {error_msg}")
                    final_status = "BURNED"
            finally:
                if page.video: video_path = await page.video.path()
                await context.close()
                await browser.close()
                
        return "\n".join(status_log), final_status, video_path

    @staticmethod
    async def run_x_bot(target_url, action, comment_text, device_mode, cookie_json_str, proxy_pool_str, bot_name):
        os.makedirs("videos", exist_ok=True)
        status_log = [f"[EngagingBot: {bot_name}] X Hunter-Seeker Booting..."]
        
        context_kwargs, selected_proxy = SafetyBot.generate_mask(device_mode, proxy_pool_str)
        if selected_proxy: 
            status_log.append(f"[{bot_name}] Tunneling via Proxy: {selected_proxy.split('@')[-1] if '@' in selected_proxy else selected_proxy}")
        
        video_path = None
        
        async with Stealth().use_async(async_playwright()) as p:
            browser = await p.chromium.launch(headless=True, args=["--disable-blink-features=AutomationControlled", "--no-sandbox"])
            context = await browser.new_context(**context_kwargs)
            
            try:
                raw_cookies = json.loads(cookie_json_str)
                await context.add_cookies([{"name": c["name"], "value": c["value"], "domain": c.get("domain", ".twitter.com"), "path": c.get("path", "/")} for c in raw_cookies])
            except Exception as e:
                await browser.close()
                return f"[Error: {bot_name}] Cookie Fault: {str(e)}", "BURNED", None

            page = await context.new_page()
            
            try:
                status_log.append(f"[{bot_name}] Warming session on Home Feed...")
                await page.goto("https://x.com/home", wait_until="domcontentloaded", timeout=90000)
                status_log.append(f"[{bot_name}] Proxy handshake successful. Stabilizing session...")
                await asyncio.sleep(random.uniform(4, 7))
                await page.mouse.wheel(0, random.randint(300, 800))
                await asyncio.sleep(random.uniform(3, 5))
                
                if await page.locator('[data-testid="loginButton"]').count() > 0:
                    status_log.append(f"[Error: {bot_name}] Session Invalidated by X. Kicked to Login.")
                    raise Exception("Session Invalidated")

                status_log.append(f"[{bot_name}] Navigating to target URL...")
                await page.goto(target_url, wait_until="domcontentloaded", timeout=90000)
                await asyncio.sleep(random.uniform(4, 6))
                    
                for close_sel in ['[data-testid="app-bar-close"]', '[data-testid="close"]', '[aria-label="Close"]']:
                    els = page.locator(close_sel)
                    if await els.count() > 0 and await els.first.is_visible():
                        await els.first.click(force=True)
                        await asyncio.sleep(1)

                if action in ["Like", "Both"]:
                    like_btn = page.locator('[data-testid="like"]')
                    if await like_btn.count() > 0 and await like_btn.first.is_visible():
                        await like_btn.first.scroll_into_view_if_needed()
                        await asyncio.sleep(1)
                        await like_btn.first.click(force=True)
                        status_log.append(f"[{bot_name}] Target Liked.")
                        await asyncio.sleep(2)

                if action in ["Comment", "Both"] and comment_text:
                    reply_btn = page.locator('[data-testid="reply"]')
                    if await reply_btn.count() > 0 and await reply_btn.first.is_visible():
                        await reply_btn.first.click(force=True)
                        await asyncio.sleep(2)
                        
                        editor = page.locator('.public-DraftEditor-content, [data-testid="tweetTextarea_0"]')
                        if await editor.count() > 0 and await editor.first.is_visible():
                            await editor.first.click(force=True)
                            await asyncio.sleep(1)
                            await page.keyboard.type(comment_text, delay=random.randint(65, 120))
                            await asyncio.sleep(2)
                            
                            post_btn = page.locator('[data-testid="tweetButton"], [data-testid="tweetButtonInline"]')
                            if await post_btn.count() > 0 and await post_btn.first.is_visible():
                                await post_btn.first.click(force=True)
                                status_log.append(f"[{bot_name}] Payload delivered via UI.")
                            else:
                                await page.keyboard.press("Control+Enter")
                                status_log.append(f"[{bot_name}] Payload delivered via KB Override.")
                            await asyncio.sleep(3)
                            
                final_cookies = await context.cookies()
                update_agent_cookie("X (Twitter)", bot_name, final_cookies)
                status_log.append(f"[{bot_name}] Rotated session tokens synced to Vault.")
                final_status = "SUCCESS"
                
            except Exception as e:
                error_msg = str(e)
                if "Timeout" in error_msg or "Target closed" in error_msg or "net::ERR" in error_msg:
                    status_log.append(f"[{bot_name}] Mission Aborted (Timeout). Cookie is SAFE.")
                    final_status = "ACTIVE"
                else:
                    status_log.append(f"[{bot_name}] Mission Aborted: {error_msg}")
                    final_status = "BURNED"
            finally:
                if page.video: video_path = await page.video.path()
                await context.close()
                await browser.close()
                
        return "\n".join(status_log), final_status, video_path

# ==========================================
# SWARM LAUNCHER & SCOUT WRAPPER
# ==========================================
async def launch_swarm(platform, deploy_mode, squad_target, ind_agent, url_dropdown, url_manual, action, text, device_mode):
    target_url = url_manual.strip() if url_manual.strip() else url_dropdown
    if target_url and "(" in target_url and target_url.endswith(")"): target_url = target_url.split("(")[-1].replace(")", "").strip()
    if not target_url: return "[Error] Target URL required.", None
    
    vault = load_vault()
    agents = vault.get(platform, [])
    
    if deploy_mode == "Individual Agent": agents = [a for a in agents if a["name"] == ind_agent]
    else:
        if squad_target != "ALL SQUADS": agents = [a for a in agents if a.get("squad", "Unassigned") == squad_target]
        
    active_agents = [a for a in agents if a.get("status", "ACTIVE") == "ACTIVE"]
    
    if not active_agents:
        return f"[System] No ACTIVE agents found for deployment. Check Vault for BURNED status.", None
        
    master_telemetry = [f"=== INITIATING SWARM: {len(active_agents)} ACTIVE AGENTS ===", f"Target: {target_url}\n"]
    diagnostic_video = None
    
    for agent in active_agents:
        master_telemetry.append(f"---> Activating EngagingBot: {agent['name']}")
        
        if platform == "Facebook":
            log, status, vid_path = await EngagingBot.run_fb_bot(target_url, action, text, device_mode, agent['cookie'], agent.get('proxy', ''), agent['name'])
        else:
            log, status, vid_path = await EngagingBot.run_x_bot(target_url, action, text, device_mode, agent['cookie'], agent.get('proxy', ''), agent['name'])
            
        master_telemetry.append(log)
        if vid_path: diagnostic_video = vid_path
        
        if status == "BURNED":
            master_telemetry.append(f"[SafetyBot Overseer] ⚠️ CASUALTY DETECTED: {agent['name']} flagged as BURNED.")
            flag_agent_burned(platform, agent['name'])
            master_telemetry.append("[SafetyBot Overseer] Extracting crash video telemetry...\n")
            break
        elif status == "ACTIVE":
            master_telemetry.append(f"[SafetyBot Overseer] 🛡️ Agent aborted due to network/timeout. Cookie preserved.")
        else:
            master_telemetry.append(f"<--- EngagingBot {agent['name']} offline.\n")
            
    master_telemetry.append("=== SWARM OPERATION COMPLETE ===")
    return "\n".join(master_telemetry), diagnostic_video

def deploy_wrapper(p, m, s, i, ud, um, a, t, d):
    return asyncio.run(launch_swarm(p, m, s, i, ud, um, a, t, d))

def scout_wrapper(url_dropdown, url_manual):
    target_url = url_manual.strip() if url_manual.strip() else url_dropdown
    if target_url and "(" in target_url and target_url.endswith(")"): target_url = target_url.split("(")[-1].replace(")", "").strip()
    if not target_url: return "[Error] Target URL required for Scout reconnaissance."
    return asyncio.run(ScoutingBot.scout_target(target_url))

# ==========================================
# UI INITIALIZATION
# ==========================================
initial_vault = load_vault()
initial_squads = initial_vault["Squads"]
initial_fb_agents = [b["name"] for b in initial_vault["Facebook"]]
initial_targets = [f"{t['name']} ({t['url']})" for t in initial_vault.get("Targets", [])]

custom_css = "body { font-family: 'Inter', sans-serif; } .gradio-container { border-radius: 12px; box-shadow: 0 8px 30px rgba(0,0,0,0.12); }"

with gr.Blocks(css=custom_css, theme=gr.themes.Glass()) as app:
    gr.HTML("<h1 style='text-align: center;'>🌐 Executive Swarm Command Center</h1>")
    
    with gr.Tabs():
        with gr.Tab("🛡️ Agent Armory"):
            with gr.Row():
                with gr.Column():
                    gr.Markdown("### 1. Create New Agent")
                    reg_platform = gr.Radio(["Facebook", "X (Twitter)"], label="Platform", value="Facebook")
                    reg_name = gr.Textbox(label="New Agent Alias")
                    reg_cookie = gr.Textbox(label="Raw Cookie JSON", lines=3)
                    
                    reg_proxy_mode = gr.Radio(["Raw IP", "Auto-Free Scraper", "Custom Proxy"], label="Proxy Mode", value="Raw IP")
                    reg_proxy_custom = gr.Textbox(label="Custom Proxy (if selected)", placeholder="http://user:pass@ip:port")
                    
                    reg_btn = gr.Button("Create Agent", variant="primary")
                    reg_out = gr.Textbox(show_label=False)
                with gr.Column():
                    gr.Markdown("### 2. Update / Renew Agent")
                    upd_agent_dropdown = gr.Dropdown(choices=initial_fb_agents, label="Select Agent")
                    upd_name = gr.Textbox(label="New Name (Optional)")
                    upd_cookie = gr.Textbox(label="New Cookie JSON (Optional)", lines=3)
                    
                    upd_proxy_mode = gr.Radio(["Keep Existing", "Raw IP", "Auto-Free Scraper", "Custom Proxy"], label="New Proxy Mode", value="Keep Existing")
                    upd_proxy_custom = gr.Textbox(label="New Custom Proxy (if selected)")
                    
                    upd_btn = gr.Button("Update Agent", variant="secondary")
                    upd_out = gr.Textbox(show_label=False)
                with gr.Column():
                    gr.Markdown("### 3. Delete Agent")
                    del_agent_dropdown = gr.Dropdown(choices=initial_fb_agents, label="Select Agent to Purge")
                    del_agent_btn = gr.Button("Permanently Delete Agent", variant="stop")
                    del_agent_out = gr.Textbox(show_label=False)
        
        with gr.Tab("👥 Squad Formation"):
            with gr.Row():
                with gr.Column():
                    gr.Markdown("### Squad Management")
                    with gr.Row():
                        new_squad_input = gr.Textbox(label="Create Squad", placeholder="Name...")
                        create_squad_btn = gr.Button("Create")
                    with gr.Row():
                        del_squad_dropdown = gr.Dropdown(choices=initial_squads, label="Delete Squad")
                        del_squad_btn = gr.Button("Delete", variant="stop")
                    squad_crud_out = gr.Textbox(show_label=False)
                    
                    gr.Markdown("### Assign Agents")
                    assign_platform = gr.Radio(["Facebook", "X (Twitter)"], label="Select Platform", value="Facebook")
                    assign_squad = gr.Dropdown(choices=initial_squads, label="Target Squad")
                    assign_agents = gr.CheckboxGroup(choices=initial_fb_agents, label="Select Agents")
                    assign_btn = gr.Button("Assign Selected", variant="primary")
                    assign_out = gr.Textbox(show_label=False)
                    
                with gr.Column():
                    refresh_roster_btn = gr.Button("Refresh Squad Rosters")
                    roster_display = gr.Textbox(label="Active Deployment Roster", lines=20, value=get_squad_roster())

        with gr.Tab("🎯 Target Arrays"):
            with gr.Row():
                with gr.Column():
                    gr.Markdown("### Add Target")
                    target_name = gr.Textbox(label="Target Alias")
                    target_url = gr.Textbox(label="Target URL")
                    save_target_btn = gr.Button("Inject into Monitoring Array", variant="primary")
                    
                    gr.Markdown("### Remove Target")
                    del_target_dropdown = gr.Dropdown(choices=initial_targets, label="Select Target to Remove")
                    del_target_btn = gr.Button("Delete Target", variant="stop")
                    target_status = gr.Textbox(show_label=False)
                with gr.Column():
                    target_display = gr.Dropdown(choices=initial_targets, label="Active Targets", interactive=False)

        with gr.Tab("🔍 Scouting Recon"):
            with gr.Row():
                with gr.Column():
                    gr.Markdown("### 🔭 Dispatch ScoutingBot")
                    scout_saved_target = gr.Dropdown(choices=initial_targets, label="Select Monitored Target")
                    scout_manual_target = gr.Textbox(label="OR Manual URL Override", placeholder="https://...")
                    scout_btn = gr.Button("Run Unauthenticated Recon 🕵️‍♂️", variant="primary")
                with gr.Column():
                    scout_console = gr.Textbox(label="Scouting Intelligence Output", lines=15)

        with gr.Tab("🚀 Launch Command"):
            with gr.Row():
                with gr.Column(scale=1):
                    deploy_platform = gr.Radio(["Facebook", "X (Twitter)"], label="Network", value="Facebook")
                    with gr.Accordion("Targeting", open=True):
                        saved_target = gr.Dropdown(choices=initial_targets, label="Select Monitored Target")
                        manual_target = gr.Textbox(label="OR Manual URL Override", placeholder="https://...")
                    
                    deploy_mode = gr.Radio(["By Squad", "Individual Agent"], label="Scale", value="By Squad")
                    deploy_squad = gr.Dropdown(choices=["ALL SQUADS"] + initial_squads, label="Select Squad", value="ALL SQUADS", visible=True)
                    deploy_agent = gr.Dropdown(choices=initial_fb_agents, label="Select Agent", visible=False)
                    
                    device_emulation = gr.Radio(["Mobile (iPhone 13)", "Desktop PC"], label="Evasion Mode", value="Desktop PC")
                    action_type = gr.Radio(["Like", "Comment", "Both"], label="Action", value="Both")
                    comment_input = gr.Textbox(label="Text Payload", lines=3)
                    
                    deploy_btn = gr.Button("Execute EngagingBot Swarm 🚀", variant="primary", size="lg")
                with gr.Column(scale=1):
                    console_out = gr.Textbox(label="Terminal Telemetry", lines=15)
                    video_player = gr.Video(label="Agent Viewport (Crash Diagnostics)")

    # --- UI WIRING ---
    reg_btn.click(fn=register_agent, inputs=[reg_platform, reg_name, reg_cookie, reg_proxy_mode, reg_proxy_custom], outputs=[reg_out, upd_agent_dropdown, del_agent_dropdown, assign_agents])
    upd_btn.click(fn=update_agent, inputs=[reg_platform, upd_agent_dropdown, upd_name, upd_cookie, upd_proxy_mode, upd_proxy_custom], outputs=[upd_out, upd_agent_dropdown, del_agent_dropdown, assign_agents])
    del_agent_btn.click(fn=delete_agent, inputs=[reg_platform, del_agent_dropdown], outputs=[del_agent_out, upd_agent_dropdown, del_agent_dropdown, assign_agents])
    create_squad_btn.click(fn=create_squad, inputs=new_squad_input, outputs=[squad_crud_out, assign_squad, deploy_squad, del_squad_dropdown])
    del_squad_btn.click(fn=delete_squad, inputs=del_squad_dropdown, outputs=[squad_crud_out, assign_squad, deploy_squad, del_squad_dropdown])
    save_target_btn.click(fn=save_target, inputs=[target_name, target_url], outputs=[target_status, saved_target, target_display, del_target_dropdown])
    del_target_btn.click(fn=delete_target, inputs=del_target_dropdown, outputs=[target_status, saved_target, target_display, del_target_dropdown])
    reg_platform.change(fn=get_agent_dropdowns, inputs=reg_platform, outputs=[upd_agent_dropdown, del_agent_dropdown, assign_agents])
    assign_platform.change(fn=get_agent_dropdowns, inputs=assign_platform, outputs=[upd_agent_dropdown, del_agent_dropdown, assign_agents])
    assign_btn.click(fn=assign_multiple_to_squad, inputs=[assign_platform, assign_agents, assign_squad], outputs=[assign_out, roster_display])
    refresh_roster_btn.click(fn=get_squad_roster, outputs=roster_display)
    deploy_mode.change(fn=toggle_deploy_mode, inputs=[deploy_mode, deploy_platform], outputs=[deploy_squad, deploy_agent])
    deploy_platform.change(fn=toggle_deploy_mode, inputs=[deploy_mode, deploy_platform], outputs=[deploy_squad, deploy_agent])
    deploy_btn.click(fn=deploy_wrapper, inputs=[deploy_platform, deploy_mode, deploy_squad, deploy_agent, saved_target, manual_target, action_type, comment_input, device_emulation], outputs=[console_out, video_player])
    scout_btn.click(fn=scout_wrapper, inputs=[scout_saved_target, scout_manual_target], outputs=[scout_console])

if __name__ == "__main__":
    app.launch(server_name="0.0.0.0", server_port=7860, share=True)
    