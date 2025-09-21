# V-Card Studio Feature Guide

A snapshot of the capabilities that make V-Card Studio an immersive, secure, and shareable digital identity platform.

## Core Experiences
### Immersive Landing
- Animated hero with hue-rotating gradients and interactive preview device.
- Feature grid, workflow timeline, testimonial slider, and CTA deck inspired by high-end SaaS marketing pages.
- Responsive navbar with mobile drawer, scroll-triggered reveals, and premium glassmorphism.

### Builder & Preview
- Two-panel layout with form inputs versus live animated preview.
- Scroll-sync preview: as you scroll the builder, the preview glides in tandem on desktop.
- Form sections: personal info, socials, styling, with icons and micro copy for clarity.
- Background palette: 16 gradient presets spanning light, vibrant, and deep/dark themes plus custom color picker.
- Smart contrast detection toggles text color for optimum readability.
- Avatar and logo upload with instant preview + fallback badges.

### Public V-Card View
- Responsive layout with brand badge, contact chips, quick action buttons, and social icon grid.
- Email/website copy buttons, phone call/SMS actions, and save-to-contacts (vCard) trigger.
- QR download and share prompts with consistent glass styling.
- Admin preview banner with “Back to dashboard” link when accessed by superusers.

## Security & Account Management
### Direct Password Reset Flow
1. User provides their email or phone number on the "Forgot Password" page.
2. If the account exists, the user is immediately redirected to the "Set New Password" page.
3. The user sets and confirms their new password.
4. Upon success, the password is changed, and the user is prompted to log in.
- This flow is direct and does not require any email or OTP verification.

### Authentication/Authorization
- Standard register/login flow with phone number capture.
- Admin login gated to superusers with custom login view and brand-consistent UI.
- Admin-only routes decorated with `user_passes_test` for security.

## Data Visibility & Export
- Admin dashboard: glass panels display total users, cards, moderation queue counts.
- Toggle stat cards reveal user and card tables; links to view/edit/delete.
- CSV export: zipped bundle with `users.csv` + `cards.csv`, capturing dynamic card JSON fields.
- Excel export: multi-sheet workbook (Users, Cards) using `openpyxl`.

## Documentation Portal
- `/documentation/` renders an animated documentation page with cards, gradient toggles, and README markdown.
- Sections: interface overview, security layers, designer tips, quick reference snippets.

## Styling & Frontend
- Tailwind foundation with custom CSS for gradients, blur, pulse, and scroll animations.
- Lucide icon set throughout dashboards, forms, and marketing assets.
- Hue-rotate animation on hero preview; nav fixed with blur/shadow, mobile drawer transitions.

## Testing
- `cards.test_dashboards.DashboardTests`: covers dashboard access states, redirect logic, and counts.
- Run with `python manage.py test cards.tests cards.test_dashboards`.

## Deployment Touchpoints
- PostgreSQL-backed settings via `python-decouple` / `dj-database-url`.
- Gunicorn + systemd units (`gunicorn.service`, `gunicorn.socket`).
- Nginx reverse proxy (`nginx.conf`) with SSL recommendations.
- `deploy.sh` bootstrap script for Ubuntu environment setup.

## Roadmap Ideas (Optional Enhancements)
- Card analytics dashboard (views by day, device share).
- Team workspaces for collaborative card creation.
- Template marketplace with community gradients and layouts.
- Webhooks / Zapier integration for automatic contact sync.

---
This feature guide represents the current UX + engineering state of V-Card Studio—from landing page wow-factor to direct account recovery and admin exports.
