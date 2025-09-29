# MY-Card Studio – Feature Guide

This document captures the major product areas, UX decisions, and technical behaviours that define MY-Card Studio.

---
## 1. Marketing & Acquisition
- **Landing page**
  - Animated hero with gradient cycling and a card preview device.
  - Feature grid, timeline/"how it works" section, testimonials, and pricing-style CTA rows.
  - Responsive navigation with glassmorphism, sticky header, and mobile drawer.
- **Documentation portal**
  - `/documentation/` renders markdown with animated tiles, gradient toggles, and quick links.
  - Great entry point for onboarding, design guidelines, and developer references.

---
## 2. Builder Experience
- **Two-panel layout** – Form inputs on the left, live preview on the right. Scrolling the form animates the preview into view.
- **Sectioned workflow**
  1. Personal details (names, job, company, contact info)
  2. Social & messaging links (Messenger, Discord, Parrale, etc.)
  3. Styling (avatar, logo, gradients, notes)
- **Validation & guidance**
  - Case-insensitive username/email uniqueness checks.
  - Phone validation prevents duplicates, normalises digits, and highlights when a number is reused.
  - Business spotlight field enforces contextual copy depending on the chosen highlight (phone, email, website).
- **Visual polish**
  - 16 gradient presets with custom colour picker fallback.
  - Smart text-contrast detection flips colours for readability.
  - Avatar/logo preview with fallback initials badge.
  - Social preview chips inherit brand colours for instant feedback.

---
## 3. Public Card View
- **Layout**
  - Hero banner with avatar/logo, contact chips, quick actions (call, SMS, copy, save contact).
  - Sections for primary contact details, role/company, business spotlight, notes, and social dock.
- **Quick actions**
  - Copy-to-clipboard buttons for email/website.
  - Call/SMS tel links with graceful fallback messaging.
  - QR download button (auto-named `my-card-qrcode.png`).
- **Admin awareness**
  - Superusers see a “Back to dashboard” banner when viewing cards.
  - Offline cards redirect visitors to contextual inactive pages (owner vs public view).

---
## 4. Account & Security
- **Registration** – Captures username, email, password, and phone number. Phone storage is normalised and deduplicated across users.
- **Login** – Standard Django session authentication with brand-aligned UI.
- **Password reset** – Lightweight three-step flow: identify via email/phone → set new password → confirmation. No OTP/email loop required.
- **Profiles** – Each user receives a `Profile` record (phone, card limit, OTP metadata for future features).

---
## 5. Admin & Operations
- **Dashboard**
  - Stat cards for total users, cards, and pending upgrade requests.
  - Detailed tables with card status, quick view/edit links, and reactivation buttons.
  - Card limit management per user with inline forms.
- **Moderation**
  - Approve/reject upgrade requests, optionally reactivating cards in the same flow.
  - Toggle card `is_active` state with context-sensitive messaging.
- **Exports**
  - CSV bundle (`users.csv`, `cards.csv`) zipped for quick download.
  - Excel workbook (Users, Cards) with dynamic headers derived from JSONFields.

---
## 6. Supporting Services
- **QR generation** – Every card generates a QR image pointing to the public URL with `?qr=1` query for analytics.
- **Media handling** – Avatars, logos, and QR codes stored under `/media`; fallback logic keeps the UI consistent when uploads are missing.
- **Styling system** – Tailwind-inspired utility classes with custom CSS modules for gradients, glass panels, and animations. Lucide icons everywhere for consistency.

---
## 7. Testing
- `cards.tests.CardViewTests` – Card slug routing, owner/visitor context, business highlight rendering.
- `cards.tests.BusinessCardCreationTests` – Business builder happy path and validation errors.
- `cards.tests.RegistrationFormTests` – Username/email/phone uniqueness guards.
- `cards.test_dashboards.DashboardTests` (noted in README) – Admin dashboard access and stats.

Run the curated suites with:
```bash
python manage.py test cards.tests.CardViewTests cards.tests.BusinessCardCreationTests cards.tests.RegistrationFormTests
```

---
## 8. Deployment Considerations
- Environment variables loaded via `python-decouple` (`.env`).
- Production stack: Gunicorn (systemd units provided) behind Nginx (see `nginx.conf`).
- PostgreSQL recommended; SQLite acceptable for prototypes or local dev.
- Static assets served from `/staticfiles` after running `collectstatic`.
- `deploy.sh` enumerates package installs, permissions, and service restarts.

---
## 9. Future Enhancements
- Analytics dashboard (unique views, conversions, spotlight engagement).
- Team workspaces and role-based access control.
- Template marketplace for community gradients/layout variations.
- Webhook integrations for CRM/contact sync.

---
*This guide mirrors the current implementation of MY-Card Studio and should be updated whenever new features ship or workflows change.*
