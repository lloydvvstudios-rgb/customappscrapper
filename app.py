import os
import asyncio
import requests
from flask import Flask, request, jsonify
from playwright.async_api import async_playwright

# Ensure Playwright looks in the right place before anything else happens
os.environ['PLAYWRIGHT_BROWSERS_PATH'] = os.path.join(os.getcwd(), '.cache')

app = Flask(__name__)

SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_SERVICE_ROLE_KEY")

async def scrape_site(url, business_id, job_id, product_limit):
    async with async_playwright() as p:
        # Launch browser
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
        )
        page = await context.new_page()
        
        # Apply stealth using the safe method
        try:
            await playwright_stealth.stealth_async(page)
        except Exception as e:
            print(f"Stealth Init Warning: {e}")

        try:
            # 1. Navigate to URL
            response = await page.goto(url, wait_until="networkidle", timeout=60000)
            
            # 2. Validation: Check for errors or empty pages
            if response.status >= 400:
                raise Exception(f"Site returned error code: {response.status}")
            
            content = await page.content()
            if "captcha" in content.lower() or "blocked" in content.lower():
                raise Exception("Blocked by bot detection (Captcha/Cloudflare)")
            
            if len(content) < 1500:
                raise Exception("Page content too thin - likely an error or redirect")

            # 3. Handle lazy loading
            scroll_count = 3 if product_limit <= 20 else 10
            for _ in range(scroll_count):
                await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                await asyncio.sleep(1.5)

            final_html = await page.content()
            page_title = await page.title()

            # 4. Save to Supabase
            save_res = requests.post(
                f"{SUPABASE_URL}/rest/v1/onboarding_raw_data",
                headers={
                    "apikey": SUPABASE_KEY,
                    "Authorization": f"Bearer {SUPABASE_KEY}",
                    "Content-Type": "application/json",
                    "Prefer": "return=minimal"
                },
                json={
                    "business_id": business_id,
                    "job_id": job_id,
                    "source_title": page_title,
                    "raw_html": final_html[:250000], # Cap size to avoid DB payload limits
                    "product_limit": product_limit
                }
            )
            save_res.raise_for_status()

            # 5. Update Job Status
            requests.patch(
                f"{SUPABASE_URL}/rest/v1/onboarding_jobs?id=eq.{job_id}",
                headers={"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}"},
                json={"status": "raw_data_captured"}
            )

        except Exception as e:
            print(f"Scrape Error: {str(e)}")
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
    # Fire and forget background task
    asyncio.run(scrape_site(
        data.get('url'), 
        data.get('business_id'), 
        data.get('job_id'),
        data.get('product_limit', 20)
    ))
    return jsonify({"status": "initiated"}), 202

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 8080))
    app.run(host='0.0.0.0', port=port)
