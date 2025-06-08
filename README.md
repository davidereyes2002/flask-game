# GIF Reactions Game Web App

This is a Flask-based web application that allows users to register, log in, and join or host multiplayer game sessions. The app features real-time updates, session management, and integration with OpenAI for in-game functionality.

---

## Features

- User authentication system (register, login, logout)
- Host and join game sessions
- Real-time session updates (player count, session status)
- Dynamic session polling using JavaScript
- Game start flow with session and round tracking
- Secure password handling and validations
- PostgreSQL integration for persistent storage
- `.env` management with Python `dotenv`
- Integrated with OpenAI API for advanced game logic

---

## Tech Stack

- **Backend:** Python, Flask
- **Frontend:** HTML, CSS, JavaScript (vanilla)
- **Database:** PostgreSQL
- **APIs:** OpenAI (via `openai` library), GIPHY
- **Other:** Jinja2, Flask-Session, Werkzeug, python-dotenv

---

## Project Structure

- project/
- ├── static/ # CSS, JS, images
- ├── templates/ # HTML templates (Jinja)
- ├── app.py # Main Flask app
- ├── db.py # DB connection and teardown
- ├── helpers.py # Custom helper functions
- ├── requirements.txt
- ├── README.md


---

## Setup Instructions

### 1. Clone the Repository

1. git clone https://github.com/yourusername/your-repo-name.git
2. cd your-repo-name
3. python3 -m venv venv
4. venv\Scripts\activate
5. pip install -r requirements.txt
6. Create a .env file and add the following lines:
    - OPENAI_API_KEY=your-openai-key
    - GIPHY_API_KEY=your-giphy-key
    - DATABASE_URL=your-database=url

7. Initialize your database. Set up your PostgreSQL database manually or via a script (not provided here). Ensure the required tables (users, sessions, session_users, rounds, game_started, etc.) are created.
8. Run the app with: python app.py

