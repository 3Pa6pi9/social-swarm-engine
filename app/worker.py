import asyncio
import json
import random
import urllib.request
from datetime import datetime
from playwright.async_api import async_playwright
from app.database import SessionLocal, AgentAccount, CampaignLog
from app.llm import generate_comment

def unroll_shortlink(url: str) -> str:
    """Resolves fb.watch / t.co shortlinks to their canonical URL without redirect loops."""
    try:
        req = urllib.request.Request(
            url,
            headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Accept-Language": "en-US,en;q=0.9",
            }
        )
        with urllib.request.urlopen(req, timeout=10) as response:
            return response.geturl()
    except Exception:
        return url

def normalize_cookies(raw_cookies: list) -> list:
    """Cleans Cookie-Editor JSON exports so Playwright accepts them without errors."""
    cleaned = []
    for c in raw_cookies:
        cookie = {
            "name": c.get("name"),
            "value": c.get("value"),
            "domain": c.get("domain", ""),
            "path": c.get("path", "/"),
        }
        if "secure" in c:
            cookie["secure"] = bool(c["secure"])
        if "httpOnly" in c:
            cookie["httpOnly"] = bool(c["httpOnly"])
        # Normalize sameSite for Playwright ('Strict', 'Lax', or 'None')
        same_site = str(c.get("sameSite", "")).lower()
        if same_site in ["no_restriction", "none"]:
            cookie["sameSite"] = "None"
            cookie["secure"] = True
        elif same_site == "lax":
            cookie["sameSite"] = "Lax"
        elif same_site == "strict":
            cookie["sameSite"] = "Strict"
        cleaned.append(cookie)
    return cleaned

async def process_single_agent(agent_id: int, target_url: str, tone: str, dry_run: bool = False):
    db = SessionLocal()
    agent = db.query(AgentAccount).filter(AgentAccount.id == agent_id).first()
    if not agent:
        db.close()
        return

    screenshot_file = f"app/screenshots/{agent.username}_{int(datetime.utcnow().timestamp())}.png"

    async with async_playwright() as p:
        launch_kwargs = {
            "headless": True,
            "args": [
                "--no-sandbox",
                "--disable-setuid-sandbox",
                "--disable-blink-features=AutomationControlled"
            ]
        }
        if agent.proxy_url:
            launch_kwargs["proxy"] = {"server": agent.proxy_url}

        browser = await p.chromium.launch(**launch_kwargs)
        context = await browser.new_context(
            viewport={"width": 1280, "height": 800},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36",
            locale="en-US",
            extra_http_headers={
                "Accept-Language": "en-US,en;q=0.9",
                "Upgrade-Insecure-Requests": "1"
            }
        )

        # Hide webdriver property
        await context.add_init_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")

        # Inject saved cookies if available
        has_cookies = False
        if agent.cookies_json and agent.cookies_json.strip():
            try:
                cookies_data = json.loads(agent.cookies_json)
                raw_list = cookies_data.get("cookies", []) if isinstance(cookies_data, dict) else cookies_data
                if isinstance(raw_list, list) and len(raw_list) > 0:
                    await context.add_cookies(normalize_cookies(raw_list))
                    has_cookies = True
            except Exception as e:
                print(f"[!] Cookie load error for {agent.username}: {e}")

        page = await context.new_page()

        try:
            resolved_url = unroll_shortlink(target_url) if "fb.watch" in target_url or "t.co" in target_url else target_url
            print(f"[{agent.username}] Navigating to {resolved_url}...")

            post_text = f"Social post at {target_url}"
            nav_note = ""

            try:
                await page.goto(resolved_url, wait_until="domcontentloaded", timeout=25000)
                await asyncio.sleep(random.uniform(3.0, 5.0))
                page_title = await page.title()
                if page_title:
                    post_text = page_title
            except Exception as nav_err:
                # If unauthenticated datacenter IP hits a redirect loop, handle gracefully in dry-run
                print(f"[*] Notice: Navigation redirect/login wall hit ({str(nav_err)[:50]}). Proceeding with fallback context.")
                nav_note = " (Login cookies needed to bypass FB redirect wall)"

            # Scrape post text if DOM loaded
            if agent.platform == "x":
                locator = page.locator('[data-testid="tweetText"]').first
                if await locator.count() > 0:
                    post_text = await locator.inner_text()
            elif agent.platform == "facebook":
                locator = page.locator('div[dir="auto"]').first
                if await locator.count() > 0:
                    scraped = await locator.inner_text()
                    if scraped and len(scraped) > 5:
                        post_text = scraped

            comment_text = await generate_comment(post_text, agent.persona, tone)
            print(f"[{agent.username}] AI Comment Ready: {comment_text}")

            action_status = f"simulated_dry_run{nav_note}"
            if not dry_run and has_cookies:
                if agent.platform == "x":
                    like_btn = page.locator('[data-testid="like"]').first
                    if await like_btn.count() > 0:
                        await like_btn.click()
                        await asyncio.sleep(random.uniform(1.5, 3.0))
                    rt_btn = page.locator('[data-testid="retweet"]').first
                    if await rt_btn.count() > 0:
                        await rt_btn.click()
                        await asyncio.sleep(1.0)
                        confirm_rt = page.locator('[data-testid="retweetConfirm"]').first
                        if await confirm_rt.count() > 0:
                            await confirm_rt.click()
                    reply_box = page.locator('[data-testid="tweetTextarea_0"]').first
                    if await reply_box.count() > 0:
                        await reply_box.click()
                        await page.keyboard.type(comment_text, delay=random.randint(50, 110))
                        await asyncio.sleep(1.5)
                        await page.locator('[data-testid="tweetButtonInline"]').first.click()
                        await asyncio.sleep(3.0)
                elif agent.platform == "facebook":
                    like_btn = page.locator('[aria-label="Like"]').first
                    if await like_btn.count() > 0:
                        await like_btn.click()
                        await asyncio.sleep(random.uniform(1.5, 3.0))
                    comment_box = page.locator('[aria-label="Write a comment..."], [aria-label="Write a public comment..."]').first
                    if await comment_box.count() > 0:
                        await comment_box.click()
                        await page.keyboard.type(comment_text, delay=random.randint(50, 110))
                        await page.keyboard.press("Enter")
                        await asyncio.sleep(3.0)

                action_status = "completed_live"

            try:
                await page.screenshot(path=screenshot_file)
                print(f"[{agent.username}] Saved screenshot -> {screenshot_file}")
            except Exception:
                screenshot_file = None

            log_entry = CampaignLog(
                target_url=target_url,
                agent_username=agent.username,
                platform=agent.platform,
                generated_comment=comment_text,
                action_status=action_status,
                screenshot_path=screenshot_file
            )
            db.add(log_entry)
            db.commit()

        except Exception as e:
            print(f"[!] Worker exception for {agent.username}: {e}")
            db.add(CampaignLog(
                target_url=target_url,
                agent_username=agent.username,
                platform=agent.platform,
                generated_comment="",
                action_status=f"error: {str(e)[:80]}",
                screenshot_path=None
            ))
            db.commit()
        finally:
            await browser.close()
            db.close()

async def dispatch_swarm(target_url: str, platform: str, max_agents: int, tone: str, dry_run: bool):
    db = SessionLocal()
    agents = db.query(AgentAccount).filter(AgentAccount.platform == platform).limit(max_agents).all()
    agent_ids = [a.id for a in agents]
    db.close()

    for idx, aid in enumerate(agent_ids):
        await process_single_agent(aid, target_url, tone, dry_run)
        if idx < len(agent_ids) - 1:
            jitter = random.uniform(5.0, 12.0)
            print(f"[*] Jitter pause: {jitter:.1f}s before next agent...")
            await asyncio.sleep(jitter)