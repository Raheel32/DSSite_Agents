# AI Agents Service (FastAPI + LangGraph)

Site-agnostic agents. Any website (WordPress, HTML, React) calls these over HTTP.

## Run locally
```bash
python -m venv venv && source venv/bin/activate   # Windows: venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env                              # Windows: copy .env.example .env
uvicorn app.main:app --reload
```
Open http://127.0.0.1:8000/docs to test every endpoint in the browser.

## Test
`python test_fraud.py`

## Agent 4 example call (from any site)
```js
fetch("https://YOUR-SERVICE/fraud/check", {
  method: "POST",
  headers: {"Content-Type": "application/json"},
  body: JSON.stringify({
    order_ref: "ORD-1001", customer_email: "ali@example.com", amount: 4500,
    payment_method: "cod", ip_address: "103.255.4.10", checkout_seconds: 90
  })
}).then(r => r.json()).then(console.log);
```


## Agent 1 - Refund & Escalation
* `POST /refund/request`  - website sends order_ref, email, message (+ order facts)
* `POST /approve-refund`  - admin approves / rejects a paused request
* `GET  /refund/requests` - admin list (`?status=pending_approval`)
* `GET  /admin`           - admin dashboard (enter your ADMIN_API_KEY)
Test: `python test_refund.py`   |   Policy numbers: top of `app/agents/refund_agent.py`
WordPress form: `wordpress/refund_form_snippet.php`

## Agent 2 - Product Discovery
* `POST /recommendations`            - search text (+ optional purchase history) -> best products
* `POST /catalog/products`           - website pushes new/updated products (up to 200 per call)
* `DELETE /catalog/products/{id}`    - website removes a product
* `GET /catalog/stats`               - admin: how many products the agent knows
Test: `python test_discovery.py`
WordPress: `wordpress/catalog_sync_snippet.php` (auto-sync) and `wordpress/ai_search_snippet.php` (search box)

## Admin inside WordPress
`wordpress/admin_dashboard_snippet.php` adds WooCommerce > "AI Agents" (approve/reject refunds, fraud flags).
Set `DISABLE_ADMIN_PAGE=1` on Render to turn off the separate /admin page.

## Smart search inside the existing WordPress search
`wordpress/ai_search_integration_snippet.php` makes the normal product search use Agent 2 (falls back to
normal WordPress search if the agent is slow or finds nothing).

Paste your secret keys ONLY in `wordpress/ds_agents_config_snippet.php` (priority 1); every other snippet reads them from there.

## Agent 5 - Product Onboarding & SEO
* `POST /onboarding/product` - photo (base64) + name (+ your category names) -> description, SEO title/meta, tags, category
Loop: extract_details (Gemini Vision) -> generate_description -> validation_node -> retry with feedback (max 3)
Test: `python test_onboarding.py`   |   Rules: top of `app/agents/onboarding_agent.py`
WordPress: `wordpress/onboarding_page_snippet.php` adds WooCommerce > "AI Product Onboarding" (creates a Draft product)

## Agent 3 - Competitor Pricing Auditor
* `POST /pricing/audit`              - (admin key) audit one product: searches Pakistani stores via Tavily
* `GET  /pricing/audits`             - (admin key) recent audits
* `POST /pricing/audits/{id}/status` - (admin key) mark a suggestion applied / dismissed
Loop: plan_query -> search_web (Tavily) -> extract_prices (Gemini or regex) -> reviewer_node -> search again or recommend
Test: `python test_pricing.py`   |   Settings: top of `app/agents/pricing_agent.py`
WordPress: `wordpress/price_audit_page_snippet.php` adds WooCommerce > "AI Price Audit"
