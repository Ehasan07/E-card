<div align="center">

# MY-Card

### Digital business card platform for the tap-and-share era

**Live app →** [mycard.dupno.com](https://mycard.dupno.com) &nbsp;•&nbsp; **Demo card →** [/card/shiplu07/](https://mycard.dupno.com/card/shiplu07/) &nbsp;•&nbsp; **Docs →** [/documentation/](https://mycard.dupno.com/documentation/)

[![Django](https://img.shields.io/badge/Django-5.2-092E20?logo=django&logoColor=white)](https://www.djangoproject.com/)
[![Python](https://img.shields.io/badge/Python-3.12-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![PostgreSQL](https://img.shields.io/badge/PostgreSQL-16-4169E1?logo=postgresql&logoColor=white)](https://www.postgresql.org/)
[![bKash](https://img.shields.io/badge/bKash-Recurring%20Payment-E2136E)](https://www.bkash.com/)
[![Deploy](https://img.shields.io/badge/Deploy-Hetzner%20VPS-D50C2D)](https://www.hetzner.com/)
[![License](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Status](https://img.shields.io/badge/Status-Production-brightgreen)](https://mycard.dupno.com)

<br>

*Replace paper cards with a live, trackable link. QR-first sharing. Real-time preview. bKash-native billing.*

</div>

---

## Table of Contents

1. [What it does](#what-it-does)
2. [Screens & flows](#screens--flows)
3. [Features](#features)
4. [Tech stack](#tech-stack)
5. [Architecture](#architecture)
6. [Quick start (local)](#quick-start-local)
7. [Deployment](#deployment)
8. [bKash integration](#bkash-integration)
9. [Roadmap](#roadmap)
10. [Repository layout](#repository-layout)
11. [Contributing](#contributing)
12. [License](#license)

---

## What it does

**One card. Every channel.** MY-Card gives every user a shareable page at
`mycard.dupno.com/card/<username>` with:

- Live avatar, job title, company, phone, email
- Tap-to-save vCard (Apple Contacts / Google Contacts)
- Wallet pass (Apple + Google Pay)
- QR code that always points to the same URL
- 30+ social & messaging links
- Analytics: views, click-throughs per platform, contact saves, lead form submissions

Everything is **updateable in place** — hand out one card, keep changing the details behind it for years.

### Two product tracks

| | Personal card | Business card |
|---|---|---|
| **Who** | Freelancers, creators, individuals | Companies, teams, brand identities |
| **Fields** | First name, role, socials, personal bio | Company name, logo, team members, business highlight |
| **Theme** | Colour-forward, portrait-first | Logo-forward, brand-consistent |
| **Preview** | Portrait phone frame | Landscape business card frame |

---

## Screens & flows

Full end-to-end flows, all live:

| Flow | URL | Description |
|---|---|---|
| Landing | [`/`](https://mycard.dupno.com/) | Animated hero, live demo preview, pricing, feature grid, testimonials |
| Onboarding modal | (from landing) | Personal / Business chooser popup — one-tap into the builder |
| Card builder | `/start/<type>/` | Journey stepper + live preview panel (blinq.me-style) with inline signup for new visitors |
| Public card | `/card/<slug>/` | Owner sees back-to-dashboard bar; public visitors see the card + QR + wallet buttons |
| Dashboard | `/dashboard/` | Sidebar layout with your cards, leads, notifications, billing, analytics |
| Analytics | `/card/<slug>/analytics/` | Sparkline, click-through breakdown by social platform + contact channel |
| Billing | `/billing/` | Every payment, printable QuickBooks-style receipt |
| Admin | `/my-admin/dashboard/` | User + card + payment + card-lifecycle admin surface |
| bKash checkout | `/pay/bkash/initiate/` | Real bKash Recurring Payment Platform integration (mock mode until sandbox creds land) |

---

## Features

<table>
<tr>
<td width="33%" valign="top">

### Public card

- 30+ social / contact CTAs
- QR + shareable link
- Apple & Google Wallet passes
- vCard download
- Owner-only sticky nav bar
- Physical-card print layout
- SEO + OpenGraph meta

</td>
<td width="33%" valign="top">

### Builder

- Journey stepper (5 steps)
- Live preview updates on every keystroke
- Curated theme picker
- Custom public URL (Pro, one-time change)
- Avatar + logo upload
- Anonymous → auto-register on save

</td>
<td width="33%" valign="top">

### Business layer

- bKash Recurring Payment integration
- 12-month free trial → yearly renewal
- Card-lifecycle system with 30/7/1-day warnings
- 7-day grace period after expiry
- Admin dashboard + statements
- Printable payment receipts
- Leads inbox + lead-capture forms

</td>
</tr>
</table>

### Notable UX polish

- **Toast system** — top-center, no-reload, hover-to-pause, JSON-driven `window.mcToast()` API
- **Theme-aware everywhere** — every surface uses design tokens (`--mc-bg-*`, `--mc-text-*`, `--mc-accent-*`) so dark ↔ light switch is instant
- **AJAX inbox** — mark-as-read updates in place, keeps scroll position
- **Multilingual** — English + Bengali (বাংলা) with runtime switcher
- **Print CSS** — receipts and admin statements produce clean paper output with repeating table headers

---

## Tech stack

| Layer | Choice | Why |
|---|---|---|
| Backend | **Django 5.2** + Python 3.12 | Fast to iterate, mature ORM, admin scaffolding |
| Database | **PostgreSQL 16** | JSONB for `card_data`, strong indexing |
| Frontend | Server-rendered Django templates + vanilla JS | Zero build step, works everywhere |
| Icons | [Lucide](https://lucide.dev/) | Consistent stroke, tree-shakeable |
| Payments | **bKash Recurring Payment Platform (RPP) v2.1.2** + Stripe stubs | Bangladesh-first market |
| Web server | Nginx + Gunicorn (systemd) | Battle-tested, HTTP/2 |
| SSL | Let's Encrypt (auto-renew) | Free, TLS 1.2+ |
| Hosting | Hetzner Cloud VPS | Cheap and fast |
| Emails | SMTP (SendGrid/Google) | Password reset + welcome |
| Media | Pillow + local FS | Simple for the current scale |
| QR / vCard | `qrcode`, `vobject` | Standards-compliant output |

---

## Architecture

```
                                   ┌─────────────────────────────┐
   Browser  ─── HTTPS ── Nginx ────►│  Gunicorn (systemd)         │
   (mobile / desktop / QR scan)     │  ├─ MY-Card Django app      │
                                    │  │  ├─ cards/               │  ← models, views, forms
                                    │  │  ├─ gateways/bkash.py    │  ← RPP client + HMAC verify
                                    │  │  └─ templates/           │
                                    │  └─ Static + media          │
                                    └────────────┬────────────────┘
                                                 │
                                    ┌────────────▼────────────────┐
                                    │  PostgreSQL 16              │
                                    │  ├─ Card (JSONB card_data)  │
                                    │  ├─ Payment (bKash fields)  │
                                    │  ├─ CardLifecycleLog        │
                                    │  └─ UserNotification        │
                                    └────────────┬────────────────┘
                                                 │
                    ┌────────────────────────────┼────────────────────────────┐
                    │                            │                            │
              ┌─────▼─────┐              ┌──────▼───────┐             ┌──────▼─────┐
              │ bKash RPP │              │ SMTP relay   │             │ Cron       │
              │ webhook + │              │ (welcome +   │             │ daily      │
              │ redirect  │              │  password    │             │ lifecycle  │
              │ endpoints │              │  reset)      │             │ tick 2:15  │
              └───────────┘              └──────────────┘             └────────────┘
```

Detailed technical write-ups:
- **[FEATURES.md](FEATURES.md)** — every product area, decision log, feature detail
- **[PITCH.md](PITCH.md)** — customer-facing product pitch, why anyone should pay

---

## Quick start (local)

**Prerequisites**

- Python 3.12+
- PostgreSQL 14+ (or use bundled SQLite for dev)
- Git

```bash
# 1. Clone
git clone https://github.com/Ehasan07/E-card.git
cd E-card

# 2. Virtual env
python -m venv venv
source venv/bin/activate            # Windows: venv\Scripts\activate

# 3. Dependencies
pip install -r requirements.txt

# 4. Environment
cp .env.example .env                # then edit SECRET_KEY, DATABASE_URL, BKASH_*, etc.

# 5. Database + admin user
python manage.py migrate
python manage.py createsuperuser

# 6. Static assets (optional for dev, required for prod)
python manage.py collectstatic --noinput

# 7. Run
python manage.py runserver
```

Now open `http://localhost:8000/` — you should see the landing page.

To test the bKash flow locally set `BKASH_MODE=mock` in `.env`; the mock checkout page accepts these sandbox test wallets:

```
01770618575  PIN 12121     01929918378  PIN 12121
01770618576  PIN 21212     01877722345  PIN 13131
01619777282  PIN 21212     01619777283  PIN 13131
```

OTP is `123456` for every wallet.

---

## Deployment

Currently deployed on Hetzner Cloud VPS:

- **Nginx** — reverse proxy, HTTP/2, HSTS
- **Gunicorn** — 4 workers, systemd unit (`gunicorn-my-card.service`)
- **PostgreSQL 16** — local socket
- **Let's Encrypt** — auto-renew via certbot
- **Cron** — `python manage.py card_lifecycle_tick` daily at 02:15

Deploy = `git pull` on the server + `systemctl restart gunicorn-my-card mycard`. Zero-downtime because gunicorn drains old workers on `-HUP`.

---

## bKash integration

Full end-to-end **bKash Recurring Payment Platform (RPP) v2.1.2** implementation.

- `cards/gateways/bkash.py` — `BkashClient` with `create_subscription`, `query`, `cancel`, `refund` + module-level `verify_signature()` (HMAC-SHA256, base64url — matches guide page 19)
- `cards/views.py` — `bkash_initiate`, `bkash_return`, `bkash_webhook`, `bkash_mock_checkout`, `_grant_subscription`
- `cards/templates/cards/bkash_*.html` — mock checkout (real-bKash lookalike), return landing, journey mockup for S-2 milestone

**Milestone status:**

| Step | Task | Status |
|---|---|---|
| S-1 | API docs + Swagger + sandbox URL received | ✅ |
| S-2 | Share Redirect / Webhook / Display Name / Journey URL | ✅ ready to send |
| S-2 | Receive sandbox credentials from bKash | ⏳ waiting |
| S-3 | Sandbox test + API responses shared with bKash | code complete, needs creds |
| S-4 → S-7 | Production onboarding + UAT + go-live | not started |

**Mock mode** (`BKASH_MODE=mock`) lets us demo the full flow without live credentials — the mock checkout page uses the six sandbox wallets from bKash's onboarding email + OTP `123456`.

---

## Roadmap

**Shipping now (v1)**
- [x] Personal + business card builder with live preview
- [x] QR + wallet pass + vCard
- [x] Analytics with per-CTA click ranking
- [x] bKash Recurring Payment integration (mock + sandbox-ready)
- [x] User + admin billing dashboards with printable receipts
- [x] Card lifecycle (trial → paid → expiring → expired → deactivated) + 30/7/1 day warnings + inbox notifications
- [x] Multi-language (English + Bengali)
- [x] Owner-only sticky nav on public card
- [x] Merged register-and-create onboarding

**Next up (v1.1)**
- [ ] Real bKash sandbox test (S-3 milestone)
- [ ] Production bKash go-live (S-4 → S-7)
- [ ] Team/multi-user accounts (business plan)
- [ ] Bulk CSV import for enterprise onboarding
- [ ] Custom domain support (Pro)

**Later**
- [ ] NFC tap support (physical card)
- [ ] Mobile app (React Native)
- [ ] Analytics: geographic heatmap
- [ ] Webhook API for CRM sync

---

## Repository layout

```
E-card/
├── cards/                          ← main Django app
│   ├── gateways/bkash.py           ← BkashClient + HMAC verify
│   ├── migrations/                 ← 25+ migrations, lifecycle-safe
│   ├── models.py                   ← Card, Profile, Payment, UserNotification, ...
│   ├── views.py                    ← 3000+ lines of view functions
│   ├── urls.py
│   ├── forms.py
│   ├── context_processors.py       ← sidebar + plan-flag context
│   ├── management/commands/
│   │   └── card_lifecycle_tick.py  ← daily cron: warnings, expiry, deactivation
│   ├── templates/cards/            ← 50+ templates (landing, builder, public card, admin)
│   └── static/cards/               ← CSS design tokens, JS (tilt, sidebar, forms)
├── ecard_project/                  ← Django project settings + wsgi
├── requirements.txt
├── manage.py
├── README.md                       ← this file
├── FEATURES.md                     ← every feature area, deeper detail
└── PITCH.md                        ← customer pitch, why upgrade
```

---

## Contributing

This is a commercial product, so external PRs need alignment first — open an issue describing the change and expected behaviour before writing code.

For internal contributors:

1. Branch from `main` (`git checkout -b fix/short-title`)
2. Match existing patterns — check surrounding code before introducing a new library
3. Run `python manage.py check` before pushing
4. Test locally with `BKASH_MODE=mock` for any payment-touching change
5. PR into `main`; deploys go out via `git pull` on the server

---

## License

MIT — see [LICENSE](LICENSE).

---

<div align="center">

Built by [Ehasan](https://github.com/Ehasan07) at **Dupno**

</div>
