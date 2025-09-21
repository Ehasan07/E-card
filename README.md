# V-Card Studio

A cinematic, glassmorphism-powered Django platform for crafting, animating, and sharing premium digital v-cards. V-Card Studio blends immersive UI design with a secure, direct password reset workflow, QR-enabled sharing, and export-ready admin tooling.

## Table of Contents
- [Highlights](#highlights)
- [Quick Start](#quick-start)
- [Live Experience](#live-experience)
- [User Journey](#user-journey)
- [Admin Toolkit](#admin-toolkit)
- [Architecture](#architecture)
- [Testing](#testing)
- [Deployment Notes](#deployment-notes)
- [Contributing](#contributing)
- [License](#license)

## Highlights
- **Immersive Landing Page** – Animated hero, hue-shifting gradients, and motion-rich section reveals animate the first impression.
- **Two-Panel Builder** – Form inputs on the left, scroll-synced live preview on the right, complete with animated cards and responsive info chips.
- **Deep Gradient Library** – Hand-picked presets from *Celestial Noir* to *Crimson Nebula* plus custom color pickers ensure every card feels brand-new.
- **Direct Password Reset** – A streamlined, secure password reset flow that works with either email or phone number, getting users back into their accounts faster.
- **QR-First Sharing** – Instant QR generation, downloadable assets, and compact quick actions for copying, calling, messaging, and saving contacts.
- **Export-Ready Admin Console** – Glassy dashboard with CSV/Excel downloaders, moderation queue, and global card/actions view.

## Quick Start
### Prerequisites
- Python 3.8+
- pip
- PostgreSQL 12+ (or SQLite for local development)

### Installation
```bash
# Clone and enter the project
git clone https://github.com/Ehasan07/E-card.git
cd E-card

# Create virtual environment
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Configure env vars (.env example provided)
cp .env.example .env
# Set DATABASE_URL, SECRET_KEY, EMAIL credentials etc.

# Apply migrations
python manage.py migrate

# Collect static assets (optional for dev, required for prod)
python manage.py collectstatic --noinput

# Start development server
python manage.py runserver
```

## Live Experience
- `http://localhost:8000/` – Landing page with hero animation, feature grid, workflow highlights, and CTA.
- `/documentation/` – Animated docs portal rendering the README, feature tiles, gradient toggles, and setup snippets.
- `/login/`, `/register/` – Split layouts that echo the brand experience while onboarding users.
- `/documentation/` – Autoplay animations describing builder controls and gradient presets.

## User Journey
1. **Register** with username, email, password, and phone number.
2. **Design the card** through guided sections (personal details, socials, styling).
3. **Preview in real time** while picking gradients, uploading avatars/logos, and adjusting contact chips.
4. **Publish & share** via unique slug, QR download, quick actions (call, copy, save contact) and browser share sheet.

## Admin Toolkit
- `/my-admin/login/` – Secure admin entrance.
- `/my-admin/dashboard/` – Animated stats (total users/cards/moderation queue) and robust tables with quick actions.
- **Exports** – CSV bundle and Excel workbook with dynamic columns reflecting each card’s JSON data.

## Architecture
```
E-card/
├── cards/
│   ├── migrations/
│   ├── templates/cards/
│   │   ├── index.html           # Landing experience
│   │   ├── documentation.html   # Animated docs portal
│   │   ├── create_card.html     # Builder with preview scroll sync
│   │   └── ...
│   ├── views.py                 # Password reset logic, builder, dashboards
│   ├── models.py                # Profile & Card models
│   ├── forms.py                 # CardForm, ForgotPasswordForm, SetPasswordForm
│   └── tests.py                 # Unit tests for cards
├── ecard_project/               # Settings, URLs, ASGI/WSGI
├── media/                       # Avatars, logos, QR codes
├── staticfiles/                 # Collected static (ignored by git)
├── README.md / FEATURES.md
└── manage.py
```

### Key Components
- **Profile Model** – stores user phone number and related profile information.
- **Card Model** – JSON field for dynamic card data, auto slug, avatar/logo storage, text contrast logic, QR image generation.
- **Password Reset Flow** – `forgot_password` view validates user via email or phone, then `reset_password` view provides a secure form to set a new password.

## Testing
Run the full suite locally before shipping changes:
```bash
python manage.py test cards.tests cards.test_dashboards
```
- `DashboardTests` covers user/admin dashboard access, counts, and redirects.

## Deployment Notes
- Production usage targets PostgreSQL via `DATABASE_URL`.
- Gunicorn + systemd unit files (`gunicorn.service`, `gunicorn.socket`) orchestrate the app server.
- Nginx acts as a reverse proxy; sample config in `nginx.conf` includes SSL guidance.
- `deploy.sh` documents automated provisioning steps for Ubuntu (packages, environment, services).
- Static assets served via `/staticfiles/` collected with `collectstatic`.

## Contributing
Pull requests are welcome—please open an issue to discuss major changes. To keep the experience cohesive:
- Match the existing glassmorphism + gradient aesthetic.
- Run the test suite and lint before submitting.
- Include UI screenshots or Loom for significant frontend tweaks.

## License
MIT License. See [LICENSE](LICENSE) for details.
