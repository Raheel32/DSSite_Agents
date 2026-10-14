![DSSite Agents: AI-Powered Agents for WordPress and WooCommerce](assets/dssite-agents-thumbnail.png)


# AI Agents for E-Commerce (FastAPI + LangGraph)

Five LangGraph agents that plug into **any** online shop over HTTPS, demonstrated on a live
WordPress / WooCommerce grocery store (Discount Shop). Built as the Saylani Agentic AI mid-capstone.

| | |
|---|---|
| **Live shop (WordPress + WooCommerce)** | https://testv3.websitedemolynk.com/discountv2/ |
| **Agent service (FastAPI on Render)** | https://ai-agents-service-tdhq.onrender.com (`/docs` lists every endpoint) |
| **Repository** | https://github.com/Raheel32/DSSite_Agents |
| **Business requirements** | [`docs/BRD_Capstone_Project.pdf`](docs/BRD_Capstone_Project.pdf) |
| **UAT checklist (103 tests)** | [`docs/UAT_Checklist.xlsx`](docs/UAT_Checklist.xlsx) |

> The agent service runs on Render's free tier, which sleeps when idle. The first request after a
> quiet period can take up to a minute.

## What it does

The API is intended to let a website call agent workflows over HTTP
instead of embedding the agent logic directly into the website. The
repository includes five agent workflows:

1.  **Refund and escalation**: classifies a customer's message,
    evaluates order facts against configurable rules, and routes some
    requests to an administrator for review.
2.  **Product discovery and recommendations**: parses a shopper's query,
    searches the catalog maintained by the service, and ranks matching
    products.
3.  **Competitor pricing audit**: uses Tavily web search and price
    extraction/review logic to produce pricing-audit results.
4.  **Order fraud screening**: calculates a risk score from supplied
    order signals and returns a verdict. The current implementation
    contains example IP blocklist entries and configurable rule
    thresholds; this is a screening aid, not proof that an order is
    fraudulent.
5.  **Product onboarding and SEO**: accepts product details including an
    image payload, generates product copy and SEO fields, validates the
    draft, and supports a WordPress/WooCommerce integration intended to
    create a draft product.

The repository also contains WordPress PHP snippets for catalog
synchronization, AI product search, refund requests, administration,
price audits, and product onboarding.

## Architecture

```mermaid
flowchart LR
    S["WordPress / WooCommerce<br/>(any site works)"] -- "HTTPS + API keys" --> API["FastAPI service<br/>(Render)"]
    API --> G["5 LangGraph agents"]
    G --> DB[("PostgreSQL")]
    G --> LLM["Google Gemini<br/>(text + vision)"]
    G --> T["Tavily<br/>(web search)"]
    S -. "snippets: order hook, search hook,<br/>admin pages" .- S
```
``` text
WordPress / WooCommerce / another website
                  |
                  | HTTP requests
                  v
          FastAPI application
                  |
        +---------+----------+
        |         |          |
    LangGraph  SQLAlchemy  External APIs
    workflows  database    Gemini / Tavily
        |
        v
   JSON API responses
```

The application entry point is `app.main:app`. On startup, the current
entry point creates database tables and calls a seed routine. The
application exposes a health endpoint at `/health` and FastAPI's
interactive API documentation at `/docs`.

The agents never touch the shop's database. The shop sends the facts an agent needs (order, search
text, photo, price) and receives a decision. WordPress code lives in small
[Code Snippets](wordpress/) files, so the same service can serve a different shop with a different adapter.

## The five agents

| # | Agent | What it does | LangGraph ideas shown |
|---|---|---|---|
| 1 | **Smart Refund & Escalation** | Reads a refund/cancel request, applies the refund policy, auto-decides simple cases and pauses large or unclear ones for an admin | Sequential steps, conditional edges, **human-in-the-loop** (`interrupt_before`), checkpointer |
| 2 | **Product Discovery** | Turns "winter jacket and shoes under 5000" into ranked products from the synced catalog; plugged into the shop's own search bar | **Parallel branches** (`Send`), **custom reducer** that merges branch results |
| 3 | **Competitor Pricing Auditor** | Searches Pakistani stores for the same product and pack, reviews the evidence, suggests lower / raise / keep | **Iterative loop** with a `reviewer_node`, tool use (Tavily) |
| 4 | **Order Fraud Detection** | Scores every new order (IP, payment, speed, repeats) and marks it Safe or Flagged | **Sequential pipeline**, accumulating state reducer |
| 5 | **Product Onboarding & SEO** | Vendor gives a photo and a name; the agent writes description, SEO title/meta, tags, category | Gemini **Vision**, **iterative refinement** with a `validation_node` |

## Agents and API endpoints

The endpoint names below are based on the current application README and
router registration. Check `/docs` on your running instance for the
exact request schemas and response models.

  ------------------------------------------------------------------------------------
  Agent / capability      Endpoint(s)                          Purpose
  ----------------------- ------------------------------------ -----------------------
  Fraud screening         `POST /fraud/check`                  Evaluate order signals
                                                               and return a risk
                                                               assessment

  Refund request          `POST /refund/request`               Submit a refund or
                                                               cancellation request
                                                               for policy evaluation

  Refund administration   `POST /approve-refund`,              Review pending requests
                          `GET /refund/requests`               and record an
                                                               administrative decision

  Refund dashboard        `GET /admin`                         Separate admin
                                                               dashboard documented by
                                                               the project

  Product recommendations `POST /recommendations`              Search the service's
                                                               product catalog using
                                                               shopper intent

  Catalog management      `POST /catalog/products`,            Add/update or remove
                          `DELETE /catalog/products/{id}`      catalog items

  Catalog statistics      `GET /catalog/stats`                 Return catalog
                                                               statistics

  Product onboarding      `POST /onboarding/product`           Generate and validate
                                                               product information and
                                                               SEO content

  Competitor pricing      `POST /pricing/audit`,               Run a pricing audit and
                          `GET /pricing/audits`                retrieve previous
                                                               audits

  Pricing audit status    `POST /pricing/audits/{id}/status`   Mark an audit
                                                               suggestion as applied
                                                               or dismissed

  Service health          `GET /health`                        Basic health response

  Root information        `GET /`                              Return service
                                                               information and
                                                               documented endpoint
                                                               names
  ------------------------------------------------------------------------------------

Administrative endpoints and website-facing endpoints may use different
keys. Configure and verify authentication in the actual route
implementation before exposing the service publicly.

Design rules used across the agents:

* **The LLM understands, Python decides.** Gemini classifies text or reads photos; money decisions, validation and
  ranking are plain Python rules, so a customer cannot talk the AI into a refund.
* **Never invent facts.** Competitor prices must literally appear in the page text; generated product text may not
  claim "organic", "halal" etc. unless the name or the pack shows it.
* **Fail safe.** If Gemini, Tavily or the service is slow or down, the shop keeps working (normal search, orders
  never blocked, template text flagged "needs review").
* **A person stays in charge.** Refund approvals, price changes and publishing are always explicit clicks.

## Repository layout

```
app/
  main.py                 FastAPI app, CORS, routers
  database.py  models.py  schemas.py  security.py  seed.py
  agents/                 fraud_agent  refund_agent  discovery_agent  onboarding_agent  pricing_agent
  routers/                fraud  refund  recommendations  catalog  onboarding  pricing  admin
  static/admin.html       optional standalone admin page
wordpress/                Code Snippets for the shop (see install order below)
docs/                     BRD and UAT checklist
test_*.py                 one self-test per agent
render.yaml               Render blueprint (web service + PostgreSQL)
```

## Technology stack

Dependencies declared in `requirements.txt` include:

-   Python
-   FastAPI and Uvicorn
-   LangGraph and LangChain Core
-   `langchain-google-genai` for Gemini integration
-   SQLAlchemy
-   SQLite for the default local database configuration, or PostgreSQL
    when configured
-   `python-dotenv` for environment variables
-   HTTPX
-   Tavily Python client for web search

The dependency file currently contains repeated entries and uses version
lower bounds rather than a fully locked dependency set. For reproducible
deployments, consider cleaning up and locking dependencies after
compatibility testing.

## Requirements

-   Python 3.11 is the version specified by the repository's Render
    blueprint. A compatible Python version should also be used locally.
-   Git, if cloning the repository.
-   A Google AI API key for Gemini-backed functionality.
-   A Tavily API key for the competitor-pricing web-search workflow.
-   Suitable database configuration.
-   WordPress/WooCommerce only if you plan to use the provided PHP
    integrations.

Some agent code has fallback behavior when Gemini is unavailable, but
external-service-dependent functionality may be limited without the
relevant keys.

## Run locally

Commands below are examples for a fresh checkout. Run them from the
repository root.

### 1. Clone the repository

``` bash
git clone https://github.com/Raheel32/DSSite_Agents.git
cd DSSite_Agents
```

### 2. Create and activate a virtual environment

**Windows PowerShell**

``` powershell
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
```

If PowerShell blocks activation, you can run the environment's Python
and pip executables directly, or follow your organization's PowerShell
execution-policy guidance.

**macOS / Linux**

``` bash
python3.11 -m venv .venv
source .venv/bin/activate
```

### 3. Install dependencies

``` bash
python -m pip install --upgrade pip
pip install -r requirements.txt
```

### 4. Configure environment variables

Copy the example file:

**Windows PowerShell**

``` powershell
Copy-Item .env.example .env
```

**macOS / Linux**

``` bash
cp .env.example .env
```

Edit `.env` and set appropriate values:

``` dotenv
# The checked-in example defaults to a local SQLite database.
DATABASE_URL=sqlite:///./agents.db

# Needed for Gemini-backed agent behavior.
GOOGLE_API_KEY=replace_with_your_google_ai_api_key
# Optional: set a supported Gemini model name.
# GEMINI_MODEL=gemini-flash-latest

# Needed for competitor pricing research.
TAVILY_API_KEY=replace_with_your_tavily_api_key

# Replace both placeholders with long, random secrets.
ADMIN_API_KEY=replace_with_a_long_random_admin_secret
SITE_API_KEY=replace_with_a_long_random_site_secret
```

Do not commit `.env` or real API keys to Git. Keep development and
production secrets separate. If using PostgreSQL, replace the SQLite URL
with a connection string compatible with the installed database driver
and your database provider.

### 5. Start the API

``` bash
uvicorn app.main:app --reload
```

Then open:

-   API documentation: http://127.0.0.1:8000/docs
-   Root endpoint: http://127.0.0.1:8000/
-   Health endpoint: http://127.0.0.1:8000/health

The `--reload` option is intended for local development, not production
deployment.

## Example request: fraud screening

The following example mirrors the request shape documented in the
repository README. Use a test order and your own local API URL:

``` javascript
fetch("http://127.0.0.1:8000/fraud/check", {
  method: "POST",
  headers: {
    "Content-Type": "application/json"
  },
  body: JSON.stringify({
    order_ref: "ORD-1001",
    customer_email: "ali@example.com",
    amount: 4500,
    payment_method: "cod",
    ip_address: "103.255.4.10",
    checkout_seconds: 90
  })
})
  .then(async (response) => {
    if (!response.ok) {
      throw new Error(`Request failed: ${response.status}`);
    }
    return response.json();
  })
  .then(console.log)
  .catch(console.error);
```

Use `/docs` to inspect required fields and the actual response schema
for every endpoint. The sample values are illustrative, not a real
order.

## Run the test scripts

The repository includes separate test scripts for the agent workflows:

``` bash
python test_fraud.py
python test_refund.py
python test_discovery.py
python test_pricing.py
python test_onboarding.py
```

Run them from the repository root with the project's virtual environment
activated. Some tests may require environment variables, a configured
database, or external API access. The presence of these scripts does not
mean they have passed in your environment; record actual results when
validating a change.

### Environment variables

| Variable | Purpose |
|---|---|
| `DATABASE_URL` | PostgreSQL URL (Render fills it in); SQLite when empty |
| `GOOGLE_API_KEY` | Gemini (intent, query understanding, vision, text) |
| `TAVILY_API_KEY` | Web search for the pricing agent |
| `SITE_API_KEY` | Key the **shop** sends with its requests |
| `ADMIN_API_KEY` | Key for admin endpoints (approvals, lists, audits) |
| `GEMINI_MODEL` | Optional model override (default `gemini-flash-latest`) |
| `DISABLE_ADMIN_PAGE` | Set to `1` to hide the standalone `/admin` page |

If `SITE_API_KEY` / `ADMIN_API_KEY` are empty the protection is off (local development only).

## WordPress / WooCommerce integration

The `wordpress/` directory contains PHP snippets documented for the
following integrations:

  -------------------------------------------------------------------------
  Integration file                      Documented purpose
  ------------------------------------- -----------------------------------
  `ds_agents_config_snippet.php`        Shared configuration for the
                                        integration snippets

  `refund_form_snippet.php`             Customer refund/cancellation
                                        request form

  `catalog_sync_snippet.php`            Synchronize catalog products with
                                        the agent service

  `ai_search_snippet.php`               AI product-search interface

  `ai_search_integration_snippet.php`   Connect the existing WordPress
                                        product search to the discovery
                                        agent, with a documented fallback

  `admin_dashboard_snippet.php`         WooCommerce admin interface for
                                        refund decisions and fraud flags

  `onboarding_page_snippet.php`         WooCommerce product onboarding
                                        interface intended to create draft
                                        products

  `price_audit_page_snippet.php`        WooCommerce interface for
                                        competitor pricing audits
  -------------------------------------------------------------------------

Review each PHP snippet before installing it. Confirm the endpoint URL,
request headers, key handling, WordPress hooks, permissions, and
compatibility with your WordPress/WooCommerce versions. Use a staging
site first, and do not paste secrets into public posts, screenshots, or
source control.

The separate `/admin` page can be disabled in the Render configuration
using `DISABLE_ADMIN_PAGE=1`, according to the project's existing
documentation. Verify the implementation and access controls before
relying on this setting.

## Deploy on Render

A `render.yaml` blueprint is included. It declares:

-   A Python web service named `ai-agents-service`
-   A PostgreSQL database named `agents-db`
-   A build command that installs `requirements.txt`
-   A Uvicorn start command bound to `0.0.0.0` and Render's `$PORT`
-   `/health` as the health-check path
-   Environment variables for the database URL, Google API key, Tavily
    API key, admin key, and site key

Typical workflow:

1.  Push the repository to GitHub.
2.  In Render, create a new Blueprint deployment from the repository.
3.  Review the proposed services, database, plan limits, and costs
    before confirming.
4.  Enter secret environment-variable values in Render's dashboard.
5.  Wait for deployment and check the service logs and health endpoint.
6.  Test the API endpoints and integrations in a staging environment
    before connecting a live store.

The blueprint uses free plans in its current configuration. Free-tier
availability, sleep behavior, database limits, and pricing can change,
so verify current Render terms before relying on it. A successful
deployment alone does not establish that all agents or integrations work
correctly.

## Project layout

Key paths documented or referenced by the repository include:

``` text
DSSite_Agents/
├── app/
│   ├── main.py
│   ├── agents/
│   │   ├── refund_agent.py
│   │   ├── discovery_agent.py
│   │   ├── fraud_agent.py
│   │   ├── pricing_agent.py
│   │   └── onboarding_agent.py
│   ├── routers/
│   ├── database.py
│   └── seed.py
├── wordpress/
├── .env.example
├── requirements.txt
├── render.yaml
├── test_refund.py
├── test_discovery.py
├── test_fraud.py
├── test_pricing.py
└── test_onboarding.py
```

This is a high-level guide to the key paths referenced by the project,
not a guarantee that every folder contains only the files shown above.


## API overview

| Endpoint | Auth | Agent |
|---|---|---|
| `POST /fraud/check` | site key | 4 |
| `GET /fraud/flagged`, `GET /fraud/history` | admin key | 4 |
| `POST /refund/request`, `GET /refund/{id}/status` | site key | 1 |
| `GET /refund/requests`, `POST /approve-refund` | admin key | 1 |
| `POST /recommendations` | site key | 2 |
| `POST /catalog/products`, `DELETE /catalog/products/{id}` | site key | 2 |
| `GET /catalog/stats` | admin key | 2 |
| `POST /onboarding/product` | site key | 5 |
| `POST /pricing/audit`, `GET /pricing/audits`, `POST /pricing/audits/{id}/status` | admin key | 3 |
| `GET /health` | none | - |

## Security and production-readiness checklist

Before using this project with real customer or order data:

-   [ ] Restrict CORS origins in `app/main.py` to the domains that
    actually need access. The current code allows all origins.
-   [ ] Verify authentication and authorization on every administrative
    and website-facing route.
-   [ ] Use strong, unique secrets for `ADMIN_API_KEY` and
    `SITE_API_KEY`; never use the example placeholders in production.
-   [ ] Ensure secrets are stored in environment variables or an
    appropriate secret manager and are never committed.
-   [ ] Validate request payloads, amounts, identifiers, image sizes,
    and external-service responses.
-   [ ] Review refund policy rules against your real business policy.
    Test boundary cases and human-review paths.
-   [ ] Treat fraud scores as signals for review, not as definitive
    proof of wrongdoing.
-   [ ] Replace demo fraud indicators and example blocklist entries with
    a documented, maintained approach suitable for your use case.
-   [ ] Confirm database persistence and recovery behavior across
    application restarts, especially for workflows waiting for human
    approval.
-   [ ] Add automated tests for invalid inputs, authentication failures,
    database failures, timeouts, retries, and external API errors.
-   [ ] Configure logging, monitoring, backups, rate limiting, and
    appropriate retention/deletion of customer data.
-   [ ] Test WordPress integrations on staging and verify user
    capabilities and nonces for admin actions.
-   [ ] Review privacy, data-protection, and applicable legal
    requirements before processing customer information.

This checklist is not a security certification. The code, configuration,
and deployment environment need a full review before production use.

## Known implementation considerations

These are important limitations visible in the current repository:

-   CORS is configured to allow every origin in `app/main.py`; the
    source itself says to tighten this before going live.
-   The fraud agent includes sample blocked IP addresses and rule-based
    thresholds. These are demonstration rules, not a complete
    fraud-prevention system.
-   The local `.env.example` defaults to SQLite, while the Render
    blueprint provisions PostgreSQL. Validate both configurations
    independently.
-   The app startup creates database tables and runs a seed routine.
    Confirm that the seed behavior is appropriate for the database and
    environment you deploy.
-   The dependency list contains duplicate entries and does not lock
    exact versions.
-   External Gemini and Tavily calls can fail because of missing keys,
    network errors, quotas, or model availability. Test fallback
    behavior and error handling.
-   Human-review workflows and in-memory LangGraph checkpointing need
    careful persistence testing across restarts and multiple service
    instances.

## BRD requirements and where they are met

| BRD item | Status | Where |
|---|---|---|
| Base e-commerce platform | Adapted: an existing WooCommerce store is used (agreed with the instructor, who asked for site-independent agents) | Live shop |
| Cash on Delivery and bank transfer only | WooCommerce payment settings | UAT PAY-01 to PAY-06 |
| Admin dashboard | WooCommerce admin plus WooCommerce > AI Agents | `admin_dashboard_snippet.php` |
| UAT before AI | 103-test checklist | `docs/UAT_Checklist.xlsx` |
| Agent 1 (conditional + human-in-the-loop) | Done | `app/agents/refund_agent.py` |
| Agent 2 (parallel + reducers) | Done | `app/agents/discovery_agent.py` |
| Agent 3 (iterative, tool routing) | Done | `app/agents/pricing_agent.py` |
| Agent 4 (sequential) | Done | `app/agents/fraud_agent.py` |
| Agent 5 (iterative, Gemini vision) | Done | `app/agents/onboarding_agent.py` |
| FastAPI, SQLAlchemy, PostgreSQL, LangGraph, LangChain, Gemini, Tavily | Used | `requirements.txt` |
| Render deployment | Done | `render.yaml` |

## Known limitations

* Free-tier hosting sleeps when idle; a keep-alive ping or a paid instance removes the delay.
* Web prices can be outdated or from marketplaces with several sellers; the pricing agent shows its sources for a human to judge.
* Approving a refund records the decision; a person still does the actual WooCommerce refund.
* Gemini and Tavily free quotas limit how many audits and onboardings can run per day.

## Contributing

Contributions and issue reports are welcome.

1.  Fork the repository and create a focused branch.
2.  Describe the issue or proposed change.
3.  Add or update tests for the behavior being changed.
4.  Run the relevant test scripts and report any required environment
    variables or external services.
5.  Open a pull request with a clear summary and testing notes.

Please do not include API keys, credentials, real customer records, or
production order data in issues, commits, or test fixtures.

## License

This project is licensed under the MIT License. See the [LICENSE](LICENSE) file for details.

## Disclaimer

This project provides agent workflows and integrations for
experimentation and development. Generated product copy,
recommendations, pricing research, refund routing, and fraud assessments
should be reviewed and validated for the intended business context. Do
not treat outputs as guaranteed accurate or use the service with live
transactions until appropriate testing, security review, and operational
controls are in place.

