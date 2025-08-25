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
*   **Live Preview:** A real-time preview of the e-card is displayed during the creation process, updating as you type.

### E-Card Sharing and Viewing
*   **Unique Shareable URL:** Each e-card has a unique URL that can be shared with others.
*   **QR Code Generation:** A QR code is automatically generated for each e-card, which links to the e-card's URL. The QR code can be downloaded for use on physical materials.
*   **Social Media Integration:** Display icons and links to various social media profiles, including Facebook, WhatsApp, YouTube, Instagram, Twitter, and LinkedIn.

### Dashboards
*   **User Dashboard:** A personalized dashboard for logged-in users to view, manage, and delete their created e-cards.
*   **Admin Dashboard:** A separate, secure dashboard for administrators to get an overview of the platform, including total users and total e-cards. Admins can also view and delete any e-card on the platform.

## Getting Started

Follow these instructions to get a copy of the project up and running on your local machine.

### Prerequisites

*   Python 3.8+
*   pip (Python package installer)

### Installation

1.  **Clone the repository:**
    ```bash
    git clone https://github.com/your-username/E-card.git
    cd E-card
    ```

2.  **Create and activate a virtual environment:**
    ```bash
    python -m venv venv
    source venv/bin/activate  # On Windows, use `venv\Scripts\activate`
    ```

3.  **Install the dependencies:**
    ```bash
    pip install -r requirements.txt
    ```

4.  **Apply database migrations:**
    ```bash
    python manage.py makemigrations
    python manage.py migrate
    ```

5.  **Create a superuser to access the admin dashboard:**
    ```bash
    python manage.py createsuperuser
    ```

6.  **Run the development server:**
    ```bash
    python manage.py runserver
    ```

The application will be available at `http://127.0.0.1:8000/`.

## Usage

### User Flow

1.  **Register/Login:** Create a new account or log in to an existing one.
2.  **Create E-Card:** From the dashboard, click on "Create E-Card" and fill in your details.
3.  **Customize:** Choose a background style and upload a profile picture.
4.  **Save and View:** Save your e-card to generate a unique URL and QR code.
5.  **Share:** Share your e-card using the provided URL or by downloading the QR code.

### Admin Flow

1.  **Login:** Log in to the admin dashboard using your superuser credentials.
2.  **View Statistics:** See the total number of users and e-cards on the platform.
3.  **Manage E-Cards:** View a list of all e-cards and delete any that are inappropriate or no longer needed.

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
├── media/
│   ├── avatars/
│   └── qrcodes/
├── staticfiles/
├── venv/
├── db.sqlite3
├── manage.py
└── requirements.txt
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
*   **`media/`**: The directory where user-uploaded files (avatars and QR codes) are stored.
*   **`manage.py`**: A command-line utility for interacting with the Django project.
*   **`requirements.txt`**: A list of the Python packages required for the project.

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

This project is licensed under the MIT License - see the [LICENSE.md](LICENSE.md) file for details.Updated E-card project description
