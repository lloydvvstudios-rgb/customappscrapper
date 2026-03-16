import os
import asyncio
import requests
from flask import Flask, request, jsonify
from playwright.async_api import async_playwright
from playwright_stealth import stealth_async

app = Flask(__name__)

SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_SERVICE_ROLE_KEY")

async def scrape_site(url, business_id, job_id, product_limit):
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36"
        )
        page = await context.new_page()
        await stealth_async(page)

        try:
            await page.goto(url, wait_until="networkidle", timeout=60000)

            # Scroll based on limit. Free users (20 items) only need 1 or 2 scrolls.
            scroll_attempts = 2 if product_limit <= 20 else 10
            for _ in range(scroll_attempts):
                await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                await asyncio.sleep(1.5)

            content = await page.content()
            title = await page.title()

            save_to_supabase(business_id, job_id, title, content, product_limit)

        except Exception as e:
            update_job_status(job_id, "failed", str(e))
        
        finally:
            await browser.close()

def save_to_supabase(biz_id, job_id, title, html, limit):
    endpoint = f"{SUPABASE_URL}/rest/v1/onboarding_raw_data"
    headers = {
        "apikey": SUPABASE_KEY,
        "Authorization": f"Bearer {SUPABASE_KEY}",
        "Content-Type": "application/json"
    }
    payload = {
        "business_id": biz_id,
        "job_id": job_id,
        "source_title": title,
        "raw_html": html[:80000], # Keep HTML size manageable
        # We save the limit here so the AI Extractor knows exactly when to stop
        "processed": False 
    }
    requests.post(endpoint, json=payload)
    update_job_status(job_id, "completed")

def update_job_status(job_id, status, error=None):
    endpoint = f"{SUPABASE_URL}/rest/v1/onboarding_jobs?id=eq.{job_id}"
    headers = {
        "apikey": SUPABASE_KEY,
        "Authorization": f"Bearer {SUPABASE_KEY}",
        "Content-Type": "application/json"
    }
    requests.patch(endpoint, json={"status": status, "error_message": error})

@app.route('/scrape', methods=['POST'])
def handle_scrape():
    data = request.json
    url = data.get('url')
    biz_id = data.get('business_id')
    job_id = data.get('job_id')
    product_limit = data.get('product_limit', 20)

    # Run Playwright asynchronously without blocking the Flask response
    asyncio.run(scrape_site(url, biz_id, job_id, product_limit))
    
    return jsonify({"status": "Scraping started", "job_id": job_id})

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.environ.get("PORT", 8080)))
