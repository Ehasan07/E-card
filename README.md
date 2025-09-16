# E-Card Creator

A comprehensive web application built with Django that allows users to create, customize, and share personalized digital e-cards. This project provides a full suite of features for user management, e-card creation, and administration.

## Table of Contents

- [Features](#features)
- [Getting Started](#getting-started)
  - [Prerequisites](#prerequisites)
  - [Installation](#installation)
- [Usage](#usage)
  - [User Flow](#user-flow)
  - [Admin Flow](#admin-flow)
- [Project Structure](#project-structure)
- [Database Models](#database-models)
- [URL Endpoints](#url-endpoints)
- [Built With](#built-with)
- [Contributing](#contributing)
- [License](#license)

## Features

### User Management
*   **User Registration:** New users can sign up with a username, email, and password.
*   **User Login:** Registered users can log in to access their dashboard.
*   **OTP-Based Password Reset:** A secure password reset process where users receive a One-Time Password (OTP) to their registered email to verify their identity before setting a new password.

### E-Card Creation and Customization
*   **Comprehensive E-Card Details:** Users can create e-cards with a wide range of information, including:
    *   First and Last Name
    *   Company and Job Title
    *   Contact Information (Email, Phone, Address)
    *   Personal Details (Birthday, Website)
    *   A short bio or notes section.
*   **Profile Picture:** Users can upload an avatar to personalize their e-card.
*   **Styling Options:** Choose from a variety of background styles to customize the look and feel of the e-card.
*   **Immersive Builder:** A two-panel builder shows a live, animated preview while you customize content, colors, avatar, and gradients.
*   **Smart Styling:** Automatic text-contrast detection keeps content readable no matter which gradient or custom color you choose.
*   **Drag-and-Drop Ready UI:** Inputs are grouped into guided sections with icons, micro-animations, and instant feedback so you always know what changed.

### E-Card Sharing and Viewing
*   **Unique Shareable URL:** Each e-card has a unique URL that can be shared with others.
*   **QR Code Generation:** A QR code is automatically generated for each e-card, which links to the e-card's URL. The QR code can be downloaded for use on physical materials.
*   **Social Media Integration:** Display icons and links to various social media profiles, including Facebook, WhatsApp, YouTube, Instagram, Twitter, and LinkedIn.
*   **Quick Actions:** Copy email/phone, launch mailto calls, save contacts as vCards, and share via the browser’s native share sheet in a single tap.
*   **Insight Banners:** Helpful tips and reminders surface next to the QR panel so you remember to embed or monitor your card after sharing.

### Dashboards
*   **User Dashboard:** A personalized dashboard for logged-in users to view, manage, and delete their created e-cards, with animated stat cards and stylish back-to-home navigation.
*   **Admin Dashboard:** A secure console showing total users, cards, and moderation queue with glassmorphism styling, quick actions, and logout/back-home shortcuts.

### Hero & Onboarding Experience
*   **Showcase Landing Page:** Animated gradients, feature highlights, a hero tutorial modal, and AI-inspired UI mockups make the home page feel premium.
*   **Guided Registration & Login:** Split layouts with elevator pitches, feature callouts, and icon-labeled inputs deliver a welcoming experience for both users and admins.

## Getting Started

Follow these instructions to get a copy of the project up and running on your local machine.

### Prerequisites

*   Python 3.8+
*   pip (Python package installer)
*   PostgreSQL 12+ (local instance or connection credentials)

### Installation

1.  **Clone the repository:**
    ```bash
    git clone https://github.com/Ehasan07/E-card.git
    cd E-card
    ```

2.  **Create and activate a virtual environment:**
    ```bash
    python -m venv venv
    source venv/bin/activate  # On Windows, use `venv\Scripts\activate`
    ```
    *(Note: The `venv/` directory is ignored by Git and will not be present in the cloned repository. You need to create it locally.)*

3.  **Install the dependencies:**
    ```bash
    pip install -r requirements.txt
    ```

4.  **Create a PostgreSQL database and user:**
    If you have `psql` access, run the helper script (defaults shown below substitute environment variables `DB_USER`, `DB_PASS`, `DB_NAME` if set):
    ```bash
    # Optional: export PGUSER if your local superuser is different (e.g. postgres)
    chmod +x scripts/setup_postgres.sh  # make executable (first run only)
    ./scripts/setup_postgres.sh
    ```
    Or execute the SQL manually:
    ```sql
    CREATE ROLE ec_user WITH LOGIN PASSWORD 'change_me';
    CREATE DATABASE ecard_db OWNER ec_user;
    GRANT ALL PRIVILEGES ON DATABASE ecard_db TO ec_user;
    ```

5.  **Configure environment variables:**
    Copy `.env.example` to `.env` (or export variables in your shell) and adjust as needed:
    ```bash
    SECRET_KEY=your-production-secret
    DEBUG=True
    ALLOWED_HOSTS=127.0.0.1,localhost
    DATABASE_URL=postgres://ec_user:change_me@localhost:5432/ecard_db
    ```

6.  **Apply database migrations:**
    ```bash
    python manage.py makemigrations
    python manage.py migrate
    ```

5.  **Collect static files:**
    ```bash
    python manage.py collectstatic
    ```
    *(Note: The `staticfiles/` directory is ignored by Git. This command will collect all static files into this directory locally.)*

6.  **Create a superuser to access the admin dashboard:**
    ```bash
    python manage.py createsuperuser
    ```

7.  **Run the development server:**
    ```bash
    python manage.py runserver
    ```

The application will be available at `http://127.0.0.1:8000/`.

## Usage

### User Flow

1.  **Register/Login:** Create a new account or log in to an existing one.
2.  **Create E-Card:** From the dashboard, click on "Create E-Card" and fill in your details.
3.  **Customize:** Choose backgrounds or enter custom colors, upload a profile picture, and see changes live.
4.  **Save and View:** Save your e-card to generate a unique URL and QR code.
5.  **Share:** Share your e-card using the provided URL, native share button, or downloaded QR code; copy contact info or save it as a vCard in one click.

### Admin Flow

1.  **Admin Login:** Navigate to `/my-admin/login/` and log in using your superuser credentials.
2.  **View Statistics:** See the total number of users, cards, and queue size via animated metric cards.
3.  **Manage E-Cards:** Review all e-cards with quick actions, then jump back home or log out via the navigation buttons.

## Production Deployment

This project is configured for production deployment on a Linux server (e.g., Ubuntu on Hetzner) using a professional-grade stack.

### Technology Stack

*   **Web Server:** Nginx
*   **Application Server:** Gunicorn
*   **Database:** PostgreSQL (configured via `DATABASE_URL`)
*   **Process Management:** Systemd
*   **SSL:** Let's Encrypt

### Overview

The production environment is managed through environment variables and dedicated service files.

1.  **Configuration via `.env`:** Sensitive information and environment-specific settings (like `SECRET_KEY`, `DATABASE_URL`, and `ALLOWED_HOSTS`) are loaded from a `.env` file at the project root. This is handled by the `python-decouple` library.

2.  **Gunicorn:** The `gunicorn` application server runs the Django application. It is managed by a `systemd` service (`ecard.service`), which ensures the application starts on boot and restarts if it fails.

3.  **Nginx:** Nginx acts as a reverse proxy, forwarding requests to Gunicorn. It is also responsible for serving static and media files directly, which is more efficient. The configuration is located in `ecard.conf`.

4.  **Systemd:** The `ecard.service` and `gunicorn.socket` files manage the Gunicorn process, ensuring it is always running.

5.  **SSL/TLS:** The site is secured with a Let's Encrypt SSL certificate, which is automatically provisioned and renewed by `certbot`.

### Deployment Steps

A `deploy.sh` script is provided to automate the setup on a fresh Ubuntu server. This script will:
*   Install all necessary packages.
*   Set up the PostgreSQL database.
*   Configure and start the Nginx and Gunicorn services.
*   Set up the firewall.

For detailed instructions, refer to the `deploy.sh` script and the configuration files (`nginx.conf`, `gunicorn.service`, `gunicorn.socket`).

## Project Structure

```
E-card/
├── cards/
│   ├── migrations/
│   ├── templates/
│   │   └── cards/
│   ├── templatetags/
│   ├── __init__.py
│   ├── admin.py
│   ├── apps.py
│   ├── forms.py
│   ├── models.py
│   ├── tests.py
│   ├── urls.py
│   └── views.py
├── ecard_project/
│   ├── __init__.py
│   ├── asgi.py
│   ├── settings.py
│   ├── urls.py
│   └── wsgi.py
├── media/                  *(Ignored by Git - user-uploaded files)*
│   ├── avatars/
│   └── qrcodes/
├── staticfiles/            *(Ignored by Git - collected static assets)*
├── venv/                   *(Ignored by Git - virtual environment)*
├── db.sqlite3              *(Ignored by Git - SQLite database file)*
├── manage.py
├── requirements.txt
├── .gitignore              *(New file to specify ignored files)*
└── FEATURES.md
```

*   **`cards/`**: The core Django app that contains the main logic for the e-card functionality.
    *   **`models.py`**: Defines the database schema with the `Profile` and `Card` models.
    *   **`views.py`**: Contains the business logic for handling user requests and rendering templates.
    *   **`urls.py`**: Defines the URL patterns for the `cards` app.
    *   **`forms.py`**: Contains the forms used for user input and validation.
    *   **`templates/`**: Contains the HTML templates for the user interface.
*   **`ecard_project/`**: The main Django project directory.
    *   **`settings.py`**: Contains the project settings, such as database configuration and installed apps.
    *   **`urls.py`**: The root URL configuration for the project.
*   **`media/`**: The directory where user-uploaded content (avatars, QR codes) is stored. This directory is now ignored by Git.
*   **`staticfiles/`**: The directory where Django collects static files. This directory is now ignored by Git.
*   **`venv/`**: The Python virtual environment. This directory is now ignored by Git.
*   **`manage.py`**: Django's command-line utility.
*   **`requirements.txt`**: A list of the Python packages required for the project.
*   **`.gitignore`**: A new file that specifies which files and directories Git should ignore.

## Database Models

### `Profile`
*   `user`: A one-to-one relationship with the `User` model.
*   `phone_number`: The user's phone number.
*   `otp`: A field to store the One-Time Password for password reset.

### `Card`
*   `user`: A foreign key to the `User` model, indicating who owns the card.
*   `card_data`: A JSON field to store all the details of the e-card.
*   `avatar`: An image field for the user's profile picture.
*   `qr_code`: An image field for the generated QR code.
*   `unique_slug`: A unique slug for the card's URL.
*   `text_color`: The color of the text on the card, determined by the background style.
*   `created_at`: The date and time the card was created.

## URL Endpoints

*   `/`: The home page.
*   `/register/`: User registration page.
*   `/login/`: User login page.
*   `/logout/`: Logs the user out.
*   `/dashboard/`: The user's dashboard.
*   `/create/`: The page for creating a new e-card.
*   `/card/<slug:unique_slug>/`: The public view of an e-card.
*   `/card/<slug:unique_slug>/edit/`: The page for editing an e-card.
*   `/my-admin/login/`: The login page for the admin dashboard.
*   `/my-admin/dashboard/`: The admin dashboard.
*   `/my-admin/card/<slug:unique_slug>/delete/`: Deletes an e-card (admin only).
*   `/password_reset/request_otp/`: The page for requesting a password reset OTP.
*   `/password_reset/verify_otp/`: The page for verifying the password reset OTP.

## Built With

*   [Django](https://www.djangoproject.com/) - The web framework used
*   [Tailwind CSS](https://tailwindcss.com/) - For styling
*   [qrcode.js](https://github.com/davidshimjs/qrcodejs) - For generating QR codes
*   [Pillow](https://python-pillow.org/) - For image processing

## Contributing

Pull requests are welcome. For major changes, please open an issue first to discuss what you would like to change.

## License

This project is licensed under the MIT License - see the [LICENSE.md](LICENSE.md) file for details.
