import os
import asyncio
import requests
from flask import Flask, request, jsonify
from playwright.async_api import async_playwright
# Use this more robust import style
from playwright_stealth import stealth_async 

app = Flask(__name__)

SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_SERVICE_ROLE_KEY")

async def scrape_site(url, business_id, job_id, product_limit):
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
        )
        page = await context.new_page()
        
        # Apply stealth
        try:
            await stealth_async(page)
        except Exception as e:
            print(f"Stealth warning: {e}") # Don't crash if stealth fails, just log it

        try:
            await page.goto(url, wait_until="networkidle", timeout=60000)
            
            # Smart scroll: scroll down a bit to trigger lazy loading
            for _ in range(3 if product_limit <= 20 else 10):
                await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                await asyncio.sleep(1.5)

            html_content = await page.content()
            page_title = await page.title()

            # Save to Raw Table
            requests.post(
                f"{SUPABASE_URL}/rest/v1/onboarding_raw_data",
                headers={
                    "apikey": SUPABASE_KEY,
                    "Authorization": f"Bearer {SUPABASE_KEY}",
                    "Content-Type": "application/json"
                },
                json={
                    "business_id": business_id,
                    "job_id": job_id,
                    "source_title": page_title,
                    "raw_html": html_content[:200000], # Playwright grabs a lot, we keep the core
                    "product_limit": product_limit
                }
            )

            # Update Job Status
            requests.patch(
                f"{SUPABASE_URL}/rest/v1/onboarding_jobs?id=eq.{job_id}",
                headers={"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}"},
                json={"status": "raw_data_captured"}
            )

        except Exception as e:
            requests.patch(
                f"{SUPABASE_URL}/rest/v1/onboarding_jobs?id=eq.{job_id}",
                headers={"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}"},
                json={"status": "failed", "error_message": str(e)}
            )
        finally:
            await browser.close()

@app.route('/scrape', methods=['POST'])
def handle_scrape():
    data = request.json
    # Launch background task
    asyncio.run(scrape_site(
        data.get('url'), 
        data.get('business_id'), 
        data.get('job_id'),
        data.get('product_limit', 20)
    ))
    return jsonify({"status": "Scrape initiated"}), 202

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.environ.get("PORT", 8080)))
