# MY-Card Studio

MY-Card Studio is a Django-powered platform for designing and publishing cinematic digital cards. The experience pairs a marketing-grade landing page with a two-panel builder, real-time previewing, and a QR-first sharing flow. Users can craft **personal** or **business** cards, while admins manage the workspace, moderate cards, and export data for reporting.

---
## Table of Contents
1. [Feature Highlights](#feature-highlights)
2. [Quick Start](#quick-start)
3. [Application Walkthrough](#application-walkthrough)
4. [Business vs Personal Cards](#business-vs-personal-cards)
5. [Admin Capabilities](#admin-capabilities)
6. [Architecture](#architecture)
7. [Technology Stack](#technology-stack)
8. [Testing](#testing)
9. [Deployment Notes](#deployment-notes)
10. [Troubleshooting](#troubleshooting)
11. [Contributing](#contributing)
12. [License](#license)

---
## Feature Highlights
- **Immersive landing page** – Animated hero, glassmorphism surfaces, and scroll-triggered reveals showcase the product before signup.
- **Dual card builders** – Choose between personal and business card flows, each with contextual copy and restrictions.
- **Live preview** – The builder scrolls in sync with a live card preview, complete with gradient backgrounds, avatar/logo fallbacks, and responsive contact chips.
- **Social deep links** – Support for Messenger, Discord, Parrale, and a wide range of social platforms with branded styling across preview and public views.
- **Direct password recovery** – Skip email loops: users reset credentials with a minimalist three-step flow.
- **QR-first sharing** – Published cards generate downloadable QR codes and quick actions for calls, SMS, saving contacts, or copying the public URL.
- **Admin dashboard** – View usage stats, moderate cards, reactivate accounts, and export CSV/Excel bundles of user and card data.

---
## Quick Start
### Prerequisites
- Python 3.10+
- pip
- SQLite (bundled) or PostgreSQL 12+ for production

### Installation
```bash
# Clone and enter the repo
git clone https://github.com/Ehasan07/E-card.git
cd E-card

# Set up a virtual environment
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate

# Install requirements
pip install -r requirements.txt

# Configure environment
cp .env.example .env
# Update SECRET_KEY, DATABASE_URL, email credentials, etc.

# Apply migrations and create a superuser
python manage.py migrate
python manage.py createsuperuser

# Collect static assets (optional for dev, required for prod)
python manage.py collectstatic --noinput

# Run the dev server
python manage.py runserver
```

---
## Application Walkthrough
| Area | URL | Description |
|------|-----|-------------|
| Landing | `/` | Cinematic marketing page with feature grid, FAQ, statistics, and CTA deck. |
| Documentation | `/documentation/` | Animated knowledge base rendering the README with callouts and gradient toggles. |
| Auth | `/register/`, `/login/` | Branded forms that capture username, email, password, and phone. |
| Builder | `/create/`, `/create/business/` | Two-panel editor with contextual helper text, gradient presets, and live preview. |
| Public cards | `/card/<slug>/` | Responsive card layout with quick actions, unique slug, and QR download. |
| Admin | `/my-admin/dashboard/` | Glass dashboard summarising users, cards, and pending requests. |

---
## Business vs Personal Cards
| Aspect | Personal Card | Business Card |
|--------|---------------|---------------|
| URL | `/create/` | `/create/business/` |
| Spotlight | *None* – standard fields only | Optional **Business Spotlight** field with phone, email, or website highlight. |
| CTA Copy | “Craft your interactive identity” | “Launch your business presence” |
| Forms | Same core form, but business cards display additional guidance around the spotlight field. |

Both card types share:
- Avatar/logo uploads with instant preview.
- Gradient palette with 16 presets + custom colour picker.
- Social link fields for platforms including Messenger, Discord, Parrale, and more.
- Real-time validation for usernames, emails, and duplicate phone numbers.

---
## Admin Capabilities
- **Dashboard** – Stats for total users/cards, pending upgrade requests, and quick links back to cards.
- **User management** – Adjust card limits, deactivate/reactivate cards, delete users.
- **Exports** – Download CSV bundle (users + cards) or Excel workbook with dynamic card JSON columns.
- **Moderation** – Toggle card visibility and respond to upgrade requests directly from the dashboard.

Admin routes are protected by `user_passes_test` with redirects to `/my-admin/login/` for unauthorised access.

---
## Architecture
```
E-card/
├── cards/
│   ├── templates/cards/      # Landing, dashboard, builder, auth, documentation, public card views
│   ├── forms.py              # CardForm, BusinessCardForm, User/Profile forms
│   ├── views.py              # Builder flow, dashboards, exports, password reset
│   ├── models.py             # Profile, Card, subscription-related models
│   ├── tests.py              # Unit tests for card flows and auth
│   └── migrations/
├── ecard_project/            # Django settings, URL routing, ASGI/WSGI
├── static/ / staticfiles/    # Static assets (collected)
├── media/                    # Uploaded avatars, logos, QR codes
├── scripts/                  # Helper scripts for deployment
├── README.md / FEATURES.md   # Documentation
└── manage.py
```

---
## Technology Stack
- **Backend** – Django 5 (auth, ORM, admin tooling)
- **Frontend** – Tailwind-inspired utility classes with custom CSS animations, Lucide icons
- **Database** – SQLite by default; PostgreSQL recommended for production
- **Tasking** – JSONField-powered card data, Pillow for images, `qrcode` for QR generation
- **Tooling** – `dj-database-url`, `python-decouple`, Gunicorn systemd units, Nginx reverse proxy

---
## Testing
Run the suite locally before shipping changes:
```bash
python manage.py test cards.tests.CardViewTests cards.tests.BusinessCardCreationTests cards.tests.RegistrationFormTests
```
Additional dashboard tests live in `cards.test_dashboards`.

---
## Deployment Notes
- Configure `DATABASE_URL`, `SECRET_KEY`, and email/SMS providers in `.env`.
- For production, point Nginx at `gunicorn.socket` (see `nginx.conf`).
- Run `python manage.py collectstatic --noinput` before enabling the site.
- `deploy.sh` documents Ubuntu provisioning (packages, systemd units, static directory permissions).
- Optional: set up HTTPS via Let’s Encrypt; the provided Nginx sample includes SSL hints.

---
## Troubleshooting
| Issue | Fix |
|-------|-----|
| QR images not generating | Ensure Pillow and qrcode are installed; verify `media/qrcodes/` has write permissions. |
| Duplicate username/phone errors | Validation is case-insensitive; choose unique values or update existing accounts. |
| Static assets missing in production | Confirm `collectstatic` ran and Nginx is serving `/staticfiles`. |
| Admin export failing | Check file write permissions and that `openpyxl` is installed. |

---
## Contributing
We welcome pull requests! Please:
1. Open an issue for large enhancements so we can align on the approach.
2. Match the established glassmorphism aesthetic (gradients, blur, iconography).
3. Include screenshots/Loom for major UI tweaks.
4. Run the test suite and lint before submitting.

---
## License
Released under the MIT License. See [LICENSE](LICENSE) for details.
