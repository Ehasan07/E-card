# E-Card Project Features Documentation

This document outlines the key features and functionalities implemented in the E-Card project.

## 1. User Authentication & Management

### 1.1 User Registration
- Allows new users to create an account with a username, password, and email.
- Collects phone number during registration.

### 1.2 User Login
- Standard login functionality for registered users.

### 1.3 Password Reset (OTP-based)
- Secure multi-step password reset process.
- Users can request a password reset by providing their email address.
- A 6-digit One-Time Password (OTP) is generated and sent to the user's registered email.
- Users must verify the OTP before being allowed to set a new password.
- (Note: SMS OTP sending is a placeholder and requires third-party integration.)

### 1.4 Admin Login & Dashboard
- Separate login for superusers to access the admin dashboard.
- Admin dashboard provides an overview of total users and total e-cards.
- Admins can view and delete any e-card.

## 2. E-Card Creation & Customization

### 2.1 Create E-Card
- Users can create personalized digital e-cards.
- Collects comprehensive personal and professional information:
    - First Name, Last Name
    - Company, Job Title
    - Email, Phone, Address
    - Birthday (optional)
    - Website URL
    - Notes/Bio
- Supports profile picture (avatar) upload.

### 2.2 Social Media Integration
- Fields for various social media URLs: Facebook, WhatsApp, YouTube, Instagram, Twitter/X, LinkedIn.
- Social media icons are displayed on the e-card, linking to the provided URLs.

### 2.3 Card Design & Styling
- Multiple pre-defined background gradient styles to choose from.
- Automatic text color adjustment: Text color (black/white) dynamically changes based on the selected background to ensure readability.
- Social media icons retain their brand colors and gain a subtle light background on dark card themes for visibility.

### 2.4 Live Preview
- Real-time, static preview of the e-card during the creation process.
- All entered information (personal details, contact info, social links, QR code) is immediately reflected in the preview.
- No animations in the live preview for a direct representation.

## 3. E-Card Viewing & Sharing

### 3.1 View E-Card
- Each created e-card has a unique, shareable URL (e.g., `/card/<unique_slug>/`).
- Displays all the user's information, avatar, and selected design.

### 3.2 QR Code Functionality
- A unique QR code is generated for each e-card.
- Scanning the QR code directs to the e-card's unique URL.
- "Download QR Code" button allows users to save the QR code image.

### 3.3 Sharing Options
- Buttons for easy sharing via WhatsApp and Facebook.
- "Copy Link" button to quickly copy the e-card's URL to the clipboard.

### 3.4 Edit E-Card
- Users can edit their existing e-cards.
- All fields are pre-populated with existing data for easy modification.

## 4. Technical Details

### 4.1 Django Framework
- Built using the Django web framework (Python).
- Utilizes Django's ORM for database interactions.

### 4.2 Frontend Technologies
- HTML for structure.
- Tailwind CSS for styling and responsive design.
- JavaScript for dynamic functionalities (live preview, QR code generation, form handling).
- Lucide Icons for vector icons.
- qrcode.js library for client-side QR code generation in live preview.

### 4.3 Database
- SQLite (db.sqlite3) for development.

### 4.4 Media Handling
- Stores user avatars and generated QR codes in the `/media` directory.

## 5. Project Structure

- `ecard_project/`: Main Django project settings and URL configurations.
- `cards/`: Django app containing models, views, forms, templates, and static files related to e-card functionality.
    - `models.py`: Defines database models for `Profile`, `Card`.
    - `views.py`: Handles application logic, rendering templates, and processing form data.
    - `forms.py`: Defines Django forms for user input.
    - `urls.py`: Defines URL patterns for the `cards` app.
    - `templates/cards/`: HTML templates for various pages.
    - `migrations/`: Database migration files.
- `media/`: Directory for user-uploaded content (avatars, QR codes).
- `venv/`: Python virtual environment.
- `manage.py`: Django's command-line utility.
- `requirements.txt`: Lists Python dependencies.
