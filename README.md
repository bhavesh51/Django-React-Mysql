# PayGate POC — Django · React · MySQL

A full-stack **Payment Gateway Proof of Concept** that mirrors real-world payment gateway behaviour (card tokenisation, Luhn validation, charge, refund, void, status polling) without connecting to any live network.

---

## Table of Contents

1. [Architecture Overview](#architecture-overview)
2. [Prerequisites](#prerequisites)
3. [Project Structure](#project-structure)
4. [Backend Setup (Django)](#backend-setup-django)
5. [Frontend Setup (React)](#frontend-setup-react)
6. [Running the Application](#running-the-application)
7. [API Reference](#api-reference)
8. [POC Test Cards](#poc-test-cards)
9. [Running Tests](#running-tests)
10. [Environment Variables](#environment-variables)
11. [OpenShift Deployment](#openshift-deployment)

---

## Architecture Overview

```
Browser (React :3000)
        │  fetch()
        ▼
Django REST API (:8000)
        │
        ├── POST /api/payments/charge/      ← process payment
        ├── POST /api/payments/:id/refund/  ← full or partial refund
        ├── POST /api/payments/:id/void/    ← void a transaction
        ├── GET  /api/payments/:id/status/  ← lightweight status poll
        ├── GET/POST /api/cards/            ← card tokenisation
        └── GET /api/transactions/          ← transaction history
        │
        ▼
    MySQL Database
    ┌──────────┐     ┌──────────────┐
    │  cards   │────▶│ transactions │
    └──────────┘     └──────────────┘
```

---

## Prerequisites

| Tool | Minimum version | Install |
|------|----------------|---------|
| Python | 3.8+ | https://python.org |
| pip | 21+ | bundled with Python |
| MySQL | 5.7+ | https://mysql.com |
| Node.js | 14+ | https://nodejs.org |
| npm | 6+ | bundled with Node.js |

---

## Project Structure

```
Django-React-Mysql/
├── README.md
├── backend/
│   ├── manage.py
│   ├── requirements.txt          ← Python dependencies
│   ├── backend/
│   │   ├── settings.py           ← Django settings (env-aware)
│   │   └── urls.py
│   └── restapi/
│       ├── models.py             ← Cards + Transaction models
│       ├── serializers.py        ← Validation + serialisation
│       ├── views.py              ← All API endpoints
│       ├── urls.py               ← URL routing
│       ├── admin.py              ← Django admin registration
│       ├── tests.py              ← 40+ test cases
│       └── migrations/
│           ├── 0001_initial.py
│           ├── 0002_auto_…
│           └── 0003_payment_gateway_schema.py
└── frontend/
    ├── package.json
    └── src/
        ├── App.js                ← Full SPA payment UI
        ├── App.css               ← All styles
        └── App.test.js           ← React component tests
```

---

## Backend Setup (Django)

### Step 1 — Create the MySQL database

Log in to MySQL and run:

```sql
CREATE DATABASE payment_gateway CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
-- Create a dedicated user (recommended):
CREATE USER 'pguser'@'localhost' IDENTIFIED BY 'yourpassword';
GRANT ALL PRIVILEGES ON payment_gateway.* TO 'pguser'@'localhost';
FLUSH PRIVILEGES;
```

### Step 2 — Create and activate a Python virtual environment

```bash
cd backend
python3 -m venv venv

# macOS / Linux
source venv/bin/activate

# Windows
venv\Scripts\activate
```

### Step 3 — Install Python dependencies

```bash
pip install -r requirements.txt
```

The requirements file installs:
- `Django 3.2`
- `djangorestframework`
- `django-cors-headers` (allows the React dev server on :3000)
- `mysqlclient` (MySQL driver)

> **Note (macOS):** If `mysqlclient` fails to install, run:
> ```bash
> brew install mysql-client pkg-config
> export PKG_CONFIG_PATH="$(brew --prefix mysql-client)/lib/pkgconfig"
> pip install mysqlclient
> ```

### Step 4 — Configure database credentials

Export the following environment variables before running Django (or add them to a `.env` file / shell profile):

```bash
export DB_NAME=payment_gateway
export DB_USER=pguser
export DB_PASSWORD=yourpassword
export DB_HOST=127.0.0.1
export DB_PORT=3306
```

Alternatively, edit [`backend/backend/settings.py`](backend/backend/settings.py) `DATABASES` block directly (not recommended for shared repos).

### Step 5 — Apply database migrations

```bash
python manage.py migrate
```

This creates the `cards` and `transactions` tables in your MySQL database.

### Step 6 — (Optional) Create a Django admin superuser

```bash
python manage.py createsuperuser
```

Access the admin panel at http://localhost:8000/admin/ once the server is running.

---

## Frontend Setup (React)

```bash
cd frontend
npm install
```

This installs all React dependencies listed in `package.json`.

The `"proxy": "http://localhost:8000"` field in `package.json` forwards API calls made from `localhost:3000` to the Django backend automatically during development.

---

## Running the Application

You need **two terminal windows** running simultaneously.

### Terminal 1 — Start the Django backend

```bash
cd backend
source venv/bin/activate        # or: venv\Scripts\activate on Windows
python manage.py runserver
```

Django will start at **http://localhost:8000**

### Terminal 2 — Start the React frontend

```bash
cd frontend
npm start
```

React will start at **http://localhost:3000** and open your browser automatically.

---

## API Reference

All endpoints return JSON. Request bodies must be `Content-Type: application/json`.

### Card Tokenisation

| Method | URL | Description |
|--------|-----|-------------|
| `GET` | `/api/cards/` | List all tokenised cards (masked) |
| `POST` | `/api/cards/` | Tokenise a new card |
| `GET` | `/api/cards/<uuid>/` | Get a single card |
| `DELETE` | `/api/cards/<uuid>/` | Delete a card (blocked if transactions exist) |

**POST `/api/cards/` — request body:**
```json
{
  "cardholder_name": "Jane Doe",
  "number": "4111111111111111",
  "expiration_month": 12,
  "expiration_year": 2030,
  "cvv": "123"
}
```

---

### Payment Processing

#### Charge a card — `POST /api/payments/charge/`

```json
{
  "cardholder_name": "Jane Doe",
  "card_number": "4111111111111111",
  "expiration_month": 12,
  "expiration_year": 2030,
  "cvv": "123",
  "amount": "99.99",
  "currency": "USD",
  "description": "Order #1234",
  "merchant_reference": "ORD-1234"
}
```

**Responses:** `201 Created` (approved) · `402 Payment Required` (declined) · `400 Bad Request` (validation error)

---

#### Refund — `POST /api/payments/<id>/refund/`

```json
{
  "amount": "50.00",
  "reason": "Customer return"
}
```

Omit `amount` for a full refund. **Response:** `201 Created`

---

#### Void — `POST /api/payments/<id>/void/`

Empty body `{}`. Voids an approved or pending charge. **Response:** `200 OK`

---

#### Payment Status — `GET /api/payments/<id>/status/`

Returns the lightweight status of any transaction.

---

### Transaction History

| Method | URL | Query params |
|--------|-----|--------------|
| `GET` | `/api/transactions/` | `status`, `transaction_type`, `card_id` |
| `GET` | `/api/transactions/<uuid>/` | — |

---

## POC Test Cards

These test card numbers control the simulated authorisation outcome:

| Card Number | Brand | Result |
|-------------|-------|--------|
| `4111 1111 1111 1111` | Visa | ✓ Approved |
| `5500 0055 5555 5559` | Mastercard | ✓ Approved |
| `3782 8224 6310 005` | Amex | ✓ Approved |
| `4111 1111 1111 0000` | Visa | ✗ Declined — Insufficient funds |
| `4111 1111 1111 9999` | Visa | ✗ Declined — Card declined by issuer |
| Any valid card + amount > `9000` | Any | ✗ Declined — Transaction limit exceeded |

Any card number that fails the **Luhn algorithm** is rejected with HTTP 400.

---

## Running Tests

### Backend tests (Django)

```bash
cd backend
source venv/bin/activate
python manage.py test restapi
```

**Test coverage includes:**
- Model layer: card masking, brand detection, CVV clearing
- Serializer layer: Luhn validation, expiry checks, field constraints
- API layer: approved charge, declined charge, full refund, partial refund, void, double-void guard, refund-on-declined guard, 404 handling, filter parameters

Expected output:
```
Ran 40 tests in X.XXXs
OK
```

### Frontend tests (React)

```bash
cd frontend
npm test -- --watchAll=false
```

**Test coverage includes:**
- App rendering — header, sections, stats bar
- Payment form — card number formatting, test card table display
- Form submission — approved charge success alert
- Transaction table — row rendering, status badges, action buttons
- ActionModal — open/close, refund, void tab switch

---

## Environment Variables

All backend configuration can be overridden via environment variables:

| Variable | Default | Description |
|----------|---------|-------------|
| `DJANGO_SECRET_KEY` | dev key | Django secret key |
| `DJANGO_DEBUG` | `True` | Debug mode (`True`/`False`) |
| `DJANGO_ALLOWED_HOSTS` | `localhost,127.0.0.1` | Comma-separated allowed hosts |
| `DB_NAME` | `payment_gateway` | MySQL database name |
| `DB_USER` | `root` | MySQL username |
| `DB_PASSWORD` | _(empty)_ | MySQL password |
| `DB_HOST` | `127.0.0.1` | MySQL host |
| `DB_PORT` | `3306` | MySQL port |
| `TEST_DB_NAME` | `test_payment_gateway` | Test database name |

---

## Notes

- **No raw PAN is persisted** — the `Cards.save()` method masks the card number to `**** **** **** XXXX` and clears the CVV before writing to the database.
- The simulated authoriser in `views._simulate_authorization()` is a pure function — no external network calls are made.
- CORS is pre-configured to allow `http://localhost:3000` for local development.
- This project is a **POC only** and is not suitable for production use without a full PCI-DSS compliance review.

---

## OpenShift Deployment

### Architecture on OpenShift

```
Internet
    │  HTTPS
    ▼
OpenShift Router (HAProxy)
    ├──► Route: paygate-frontend  → Service: paygate-frontend:8080
    │         nginx container (React SPA)
    │         proxies /api/* → paygate-backend:8000
    │
    └──► Route: paygate-backend   → Service: paygate-backend:8000
              Django + Gunicorn
              ↓
         Service: paygate-mysql:3306
              ↓
         PersistentVolumeClaim (5 Gi)
```

All three tiers run in the `paygate` namespace. NetworkPolicy objects enforce
that only the frontend → backend → MySQL traffic chain is allowed.

---

### Files created by this repo

```
├── deploy.sh                         ← end-to-end bash deployment script
├── backend/
│   ├── Dockerfile                    ← multi-stage: builder + runtime
│   └── docker-entrypoint.sh          ← waits for MySQL, runs migrate, starts gunicorn
├── frontend/
│   ├── Dockerfile                    ← multi-stage: node builder + nginx runtime
│   └── nginx.conf                    ← reverse-proxy /api/* to backend, SPA fallback
└── openshift/
    ├── 00-namespace.yaml             ← Project / Namespace
    ├── 01-secret.yaml                ← Placeholder Secret (replaced by deploy.sh)
    ├── 02-configmap.yaml             ← Non-sensitive config
    ├── 03-mysql.yaml                 ← PVC + Deployment + Service for MySQL 8.0
    ├── 04-backend.yaml               ← ImageStream + BuildConfig + Deployment + Service + Route
    ├── 05-frontend.yaml              ← ImageStream + BuildConfig + Deployment + Service + Route
    ├── 06-hpa.yaml                   ← HorizontalPodAutoscaler (2-6 backend, 2-4 frontend)
    └── 07-networkpolicy.yaml         ← Zero-trust NetworkPolicy rules
```

---

### Prerequisites

| Tool | Install |
|------|---------|
| `oc` CLI (OpenShift 4.x) | https://mirror.openshift.com/pub/openshift-v4/clients/ocp/ |
| Active OpenShift login | `oc login <cluster-url>` |
| Permission to create projects and builds | cluster-admin or self-provisioner |

---

### One-command deployment (end-to-end)

```bash
# 1. Log in to your cluster
oc login https://api.<your-cluster>.example.com:6443

# 2. Run the deploy script (generates a random Django secret key automatically)
./deploy.sh \
  --namespace paygate \
  --db-password      "S3cur3DBP@ss!" \
  --db-root-password "R00tS3cur3P@ss!" \
  --django-secret    "$(openssl rand -base64 48)"
```

The script will:

| Step | What happens |
|------|-------------|
| 1 | Create (or reuse) the `paygate` OpenShift project |
| 2 | Apply namespace labels |
| 3 | Create the `paygate-secret` with real encoded values |
| 4 | Apply ConfigMap |
| 5 | Deploy MySQL (PVC + Deployment + Service) and wait for it to be ready |
| 6 | Upload `backend/` and trigger a Docker BuildConfig → ImageStream |
| 7 | Upload `frontend/` and trigger a Docker BuildConfig → ImageStream |
| 8 | Wait for both `paygate-backend` and `paygate-frontend` Deployments to roll out |
| 9 | Apply HPA and NetworkPolicy |
| 10 | Discover the public Route hostnames, patch CORS into the ConfigMap, restart backend |

At the end the script prints a summary like:

```
══════════════════════════════════════════
  Deployment Complete
══════════════════════════════════════════

  Services deployed in namespace: paygate

  MySQL:               paygate-mysql.paygate.svc.cluster.local:3306
  Backend:             https://paygate-backend-paygate.apps.cluster.example.com
  Frontend:            https://paygate-frontend-paygate.apps.cluster.example.com
```

---

### Manual / step-by-step deployment

If you prefer to apply each manifest individually:

```bash
# 1. Log in and create the project
oc login https://api.<cluster>:6443
oc new-project paygate

# 2. Create the Secret with your real passwords
oc create secret generic paygate-secret \
  --from-literal=db-name="payment_gateway" \
  --from-literal=db-user="pguser" \
  --from-literal=db-password="<DB_PASSWORD>" \
  --from-literal=db-root-password="<ROOT_PASSWORD>" \
  --from-literal=django-secret-key="$(openssl rand -base64 48)" \
  -n paygate

# 3. Apply all manifests in order
oc apply -f openshift/00-namespace.yaml
oc apply -f openshift/02-configmap.yaml
oc apply -f openshift/03-mysql.yaml
oc apply -f openshift/04-backend.yaml
oc apply -f openshift/05-frontend.yaml
oc apply -f openshift/06-hpa.yaml
oc apply -f openshift/07-networkpolicy.yaml

# 4. Wait for MySQL to be ready before starting builds
oc rollout status deployment/paygate-mysql -n paygate

# 5. Build and push backend image
oc start-build paygate-backend --from-dir=./backend --follow -n paygate

# 6. Build and push frontend image
oc start-build paygate-frontend --from-dir=./frontend --follow -n paygate

# 7. Wait for deployments
oc rollout status deployment/paygate-backend  -n paygate
oc rollout status deployment/paygate-frontend -n paygate

# 8. Get the public routes
oc get routes -n paygate
```

---

### Updating after a code change

```bash
# Backend code changed
oc start-build paygate-backend --from-dir=./backend --follow -n paygate
oc rollout status deployment/paygate-backend -n paygate

# Frontend code changed
oc start-build paygate-frontend --from-dir=./frontend --follow -n paygate
oc rollout status deployment/paygate-frontend -n paygate
```

---

### Teardown (delete everything)

```bash
./deploy.sh --teardown
# or manually:
oc delete project paygate
```

---

### Useful diagnostic commands

```bash
# List all pods
oc get pods -n paygate

# Watch pod events during startup
oc describe pod -l app=paygate-backend -n paygate

# Stream backend application logs
oc logs -f deployment/paygate-backend -n paygate

# Stream frontend logs
oc logs -f deployment/paygate-frontend -n paygate

# Check MySQL logs
oc logs -f deployment/paygate-mysql -n paygate

# Run Django management commands in a running pod
oc exec -it deployment/paygate-backend -n paygate -- python manage.py shell

# Open a MySQL shell
oc exec -it deployment/paygate-mysql -n paygate -- \
  mysql -u pguser -p payment_gateway

# Check autoscaler status
oc get hpa -n paygate

# Check network policies
oc get networkpolicies -n paygate
```

---

### Security notes

- The `paygate-secret` Secret is created by `deploy.sh` at runtime using `--from-literal`; the placeholder values in `openshift/01-secret.yaml` are **never applied directly**.
- All routes use **HTTPS edge termination** — HTTP is redirected to HTTPS by the router.
- Raw card PANs are **never written to the database** (masked in `Cards.save()`).
- NetworkPolicy restricts lateral movement: frontend → backend → MySQL only.
- OpenShift `SecurityContextConstraints` are respected: containers run as non-root (UID 1001, group 0).

