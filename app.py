import os
from flask import Flask, render_template, session, redirect, request, url_for, jsonify, flash
from flask_session import Session
import requests
from openai import OpenAI
from dotenv import load_dotenv

from db import get_db, close_db

from werkzeug.security import check_password_hash, generate_password_hash
from helpers import apology, login_required, is_password_complex, split_sentences

# ------------------ Flask setup ------------------
app = Flask(__name__)
app.config["SESSION_PERMANENT"] = False
app.config["SESSION_TYPE"] = "filesystem"
app.config["SECRET_KEY"] = os.urandom(24)
Session(app)

# ------------------ Environment and OpenAI client setup ------------------
load_dotenv()

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
GIPHY_API_KEY = os.getenv("GIPHY_API_KEY")

client = OpenAI(api_key=OPENAI_API_KEY)


@app.route("/welcome", methods=["GET", "POST"])
def welcome():
    return render_template('welcome.html')


@app.route("/")
@login_required
def index():
    user_id = session.get("user_id")
    db = get_db()

    # Get the username
    db.execute("SELECT username FROM users WHERE id = %s", (user_id,))
    username_row = db.fetchone()
    username = username_row["username"] if username_row else "User"

    # Get active sessions the user is part of
    db.execute("""
        SELECT * FROM sessions 
        WHERE id IN (
            SELECT session_id FROM session_users WHERE user_id = %s
        ) AND active = TRUE
    """, (user_id,))
    session_details = db.fetchall()
    print(session_details)

    if not session_details:
        # No active sessions found, pass None so template can handle it
        return render_template("homepage.html", game_session=None, username=username)

    session_detail = session_details[0]
    print(session_detail)

    # Count number of players in that session
    db.execute(
        "SELECT COUNT(user_id) AS count FROM session_users WHERE session_id = %s",
        (session_detail["id"],)
    )
    user_count_row = db.fetchone()
    user_count = user_count_row["count"] if user_count_row else 0

    # Check if current user is in the session
    db.execute(
        "SELECT 1 FROM session_users WHERE session_id = %s AND user_id = %s",
        (session_detail["id"], user_id)
    )
    user_in_row = db.fetchone()

    db.execute(
        "SELECT username FROM users WHERE id = %s", (session_detail["host_id"],)
    )
    host_username_row = db.fetchone()
    host_username = host_username_row["username"]
    print(host_username)

    # Add additional info to the session_detail dictionary
    session_detail["user_count"] = user_count
    session_detail["user_in"] = user_in_row is not None
    session_detail["host_username"] = host_username

    print(session_detail)

    return render_template("homepage.html", game_session=session_detail, username=username)


# @app.route("/")
# def index():
#     if session.get("user_id"):
#         # User is logged in, show dashboard
#         return render_template("homepage.html")
#     else:
#         # User is not logged in, show welcome page
#         return render_template("welcome.html")
    

@app.route("/register", methods=["GET", "POST"])
def register():
    """Register user"""
    if request.method == "POST":
        username = request.form.get("username")
        password = request.form.get("password")
        confirmation = request.form.get("confirmation")

        # Ensure username was submitted
        if not username:
            return apology("must provide username", 400)
        # Ensure password was submitted
        elif not password:
            return apology("must provide password", 400)
        elif not confirmation:
            return apology("must provide password again", 400)
        elif password != confirmation:
            return apology("passwords must match", 400)
        elif not is_password_complex(password):
            return apology("password must have at least one capital letter, one number, and one symbol", 400)

        db = get_db()

        # Check if username already exists
        db.execute("SELECT id FROM users WHERE username = %s", (username,))
        existing_user = db.fetchone()
        if existing_user:
            return apology("username already exists", 400)
        
        try:
            # Insert new user
            db.execute(
                "INSERT INTO users (username, hash) VALUES (%s, %s)",
                (username, generate_password_hash(password, method="pbkdf2:sha256", salt_length=16))
            )
        except Exception as e:
            print(f"Database error: {e}")
            return apology("an unexpected error occurred", 500)
        
        # Get the new user's ID
        db.execute("SELECT id FROM users WHERE username = %s", (username,))
        user = db.fetchone()
        if user is None:
            return apology("registration failed", 400)

        # Log in the new user
        session["user_id"] = user["id"]

        # Redirect user to home page
        flash("Registered successfully!")
        return redirect("/")
    else:
        return render_template("register.html")
    

@app.route("/login", methods=["GET", "POST"])
def login():
    """Log user in"""

    # Forget any user_id
    session.clear()

    # User reached route via POST (as by submitting a form via POST)
    if request.method == "POST":
        username = request.form.get("username")
        password = request.form.get("password")

        # Validate input
        if not username:
            return apology("must provide username", 403)
        if not password:
            return apology("must provide password", 403)

        db = get_db()

        # Query database for username
        db.execute("SELECT * FROM users WHERE username = %s", (username,))
        rows = db.fetchall()

        # Ensure username exists and password is correct
        if len(rows) != 1 or not check_password_hash(rows[0]["hash"], password):
            return apology("invalid username and/or password", 403)

        # Remember which user has logged in
        session["user_id"] = rows[0]["id"]

        # Redirect user to home page
        flash("Logged in!")
        return redirect("/")

    # User reached route via GET (as by clicking a link or via redirect)
    else:
        return render_template("login.html")


@app.route("/logout")
def logout():
    session.clear()  # Remove all session data
    flash("Logged out successfully!")
    return redirect("/")


@app.route("/reset", methods=["GET", "POST"])
@login_required
def reset():
    if request.method == "POST":
        old_password = request.form.get("old_password")
        new_password = request.form.get("new_password")
        confirmation = request.form.get("confirmation")
        
        if not request.form.get("old_password"):
            return apology("must provide old password", 400)
        
        if not old_password:
            return apology("must provide old password", 400)
        elif not new_password:
            return apology("must provide new password", 400)
        elif not confirmation:
            return apology("must provide new password again", 400)
        elif not is_password_complex(new_password):
            return apology("new password must have at least one capital letter, one number, and one symbol", 400)
        elif new_password != confirmation:
            return apology("new passwords must match", 400)
        elif old_password == new_password:
            return apology("old and new passwords are the same", 400)
        
        db = get_db()

        db.execute("SELECT * FROM users WHERE id = %s", (session["user_id"],))
        row = db.fetchone()

        if not row or not check_password_hash(row["hash"], old_password):
            return apology("incorrect old password", 400)

        db.execute("UPDATE users SET hash = %s WHERE id = %s",
                   (generate_password_hash(new_password, method='pbkdf2', salt_length=16), session["user_id"]))

        flash("Password changed successfully!")
        return redirect("/")

    else:
        return render_template("reset.html")


@app.route('/create-session', methods=['GET', 'POST'])
@login_required
def create_session():
    user_id = session.get('user_id')
    db = get_db()

    # Check if user is already in an active session
    db.execute("""
        SELECT 1 FROM session_users
        JOIN sessions ON session_users.session_id = sessions.id
        WHERE session_users.user_id = %s AND sessions.active = TRUE
    """, (user_id,))
    user_in_active_session = db.fetchone()

    if user_in_active_session:
        return apology("You are already in an active game session and cannot create a new one", 400)

    if request.method == "POST":
        # Get form data
        category = request.form.get('category')
        try:
            players = int(request.form.get('players'))
            time_per_question = int(request.form.get('time-per-question'))
            points_to_win = int(request.form.get('points-to-win'))
        except (TypeError, ValueError):
            return apology("Invalid input format", 400)

        # Validate input
        if not category or players < 3 or players > 8 or time_per_question < 5 or time_per_question > 60 or points_to_win < 1:
            return apology("Invalid game session parameters", 400)

        try:
            # Insert new session and get its id
            db.execute("""
                INSERT INTO sessions (category, players, time_per_question, points_to_win, host_id, active)
                VALUES (%s, %s, %s, %s, %s, TRUE)
                RETURNING id
            """, (category, players, time_per_question, points_to_win, user_id))
            session_id = db.fetchone()['id']

            # Add host as player in session_users
            db.execute("""
                INSERT INTO session_users (session_id, user_id, is_host)
                VALUES (%s, %s, TRUE)
            """, (session_id, user_id))

            # Start round 1 for the session
            db.execute("INSERT INTO rounds (session_id, round) VALUES (%s, 1)", (session_id,))

            flash(f"Session {session_id} created successfully!")
            return redirect(url_for('session_details', session_id=session_id))

        except Exception as e:
            print(f"Error creating session: {e}")
            return apology("An unexpected error occurred", 500)

    return render_template('create_session.html')


@app.route('/join-session')
@login_required
def join_session():
    db = get_db()
    user_id = session["user_id"]

    # Fetch all active sessions
    db.execute("SELECT * FROM sessions WHERE active = TRUE")
    sessions = db.fetchall()
    print("This is printing sessions")
    print(sessions)

    # Convert rows to a list of dicts so we can modify them
    updated_sessions = []
    for game_session in sessions:
        session_dict = dict(game_session)

        # Count how many users are in the session
        db.execute(
            "SELECT COUNT(user_id) AS count FROM session_users WHERE session_id = %s",
            (game_session["id"],)
        )
        user_count_row = db.fetchone()
        session_dict["user_count"] = user_count_row["count"] if user_count_row else 0

        # Check if the current user is already in this session
        db.execute(
            "SELECT 1 FROM session_users WHERE session_id = %s AND user_id = %s",
            (game_session["id"], user_id)
        )
        user_in_row = db.fetchone()
        session_dict["user_in"] = user_in_row is not None

        db.execute(
            "SELECT username FROM users WHERE id = %s", (game_session["host_id"],)
        )
        host_username_row = db.fetchone()
        host_username = host_username_row["username"]
        print(host_username)
        session_dict["host_username"] = host_username

        updated_sessions.append(session_dict)

    print("This is printing updated_sessions")
    print(updated_sessions)

    return render_template('join_session.html', sessions=updated_sessions)


@app.route('/waiting-area/<int:session_id>')
@login_required
def waiting_area(session_id):
    db = get_db()
    user_id = session["user_id"]

    # Fetch session details
    db.execute("SELECT * FROM sessions WHERE id = %s", (session_id,))
    session_details = db.fetchone()
    # print("This is from waiting area app route")
    # print(session_details)
    if not session_details:
        return apology("Session not found", 404)

    # Fetch users in the session
    db.execute("""
        SELECT users.username, session_users.is_host
        FROM session_users
        JOIN users ON session_users.user_id = users.id
        WHERE session_users.session_id = %s
    """, (session_id,))
    users_in_session = db.fetchall()

    user_count = len(users_in_session)
    host_id = session_details['host_id']

    return render_template(
        'waiting_area.html',
        game_session=session_details,
        users=users_in_session,
        user_count=user_count,
        host_id=host_id
    )


@app.route('/session/<int:session_id>', methods=['GET'])
@login_required
def session_details(session_id):
    # Fetch session details from the database
    db = get_db()
    user_id = session["user_id"]

    db.execute("SELECT * FROM sessions WHERE id = %s",(session_id,))
    session_details = db.fetchone()

    if not session_details:
        return apology("Session not found", 404)   
    
    is_host = session_details["host_id"] == user_id
     
    if not is_host:
        # Check if the user is already in *any* session (not just this one)
        db.execute(
            """
            SELECT session_users.session_id
            FROM session_users
            JOIN sessions ON session_users.session_id = sessions.id
            WHERE session_users.user_id = %s AND sessions.active = TRUE
            """,
            (user_id,)
        )
        active_session = db.fetchone()

        if active_session and active_session["session_id"] != session_id:
            return apology("You are already in another active session", 400)


        # Check if user is in this session
        db.execute(
            "SELECT 1 FROM session_users WHERE session_id = %s AND user_id = %s",
            (session_id, user_id)
        )
        user_in_session = db.fetchone()

        if not user_in_session:
            # Check the current number of players
            db.execute(
                "SELECT COUNT(*) AS count FROM session_users WHERE session_id = %s",
                (session_id,)
            )
            current_players_count = db.fetchone()["count"]

            if current_players_count >= session_details["players"]:
                return apology("Max number of players per the game session rules has been reached", 400)

            try:
                db.execute(
                    "INSERT INTO session_users (session_id, user_id) VALUES (%s, %s)",
                    (session_id, user_id)
                )
            except Exception as e:
                print(f"Exception occurred: {e}")
                return apology("An unexpected error occurred", 500)
            
        flash(f"Joined Session {session_id} successfully!")
        return redirect(url_for('waiting_area', session_id=session_id))

    # Host is viewing the session: show list of users
    db.execute("""
        SELECT users.username FROM session_users
        JOIN users ON session_users.user_id = users.id
        WHERE session_users.session_id = %s
    """, (session_id,))
    users = db.fetchall()

    print(session_details)

    return render_template("session_details.html", game_session=session_details, users=users)


@app.route('/leave-session/<int:session_id>', methods=['GET'])
@login_required
def leave_session(session_id):
    db = get_db()
    user_id = session["user_id"]

    db.execute("SELECT * FROM sessions WHERE id = %s", (session_id,))
    session_details = db.fetchone()

    if not session_details:
        return apology("Session not found", 404)

    # If the current user is the host, redirect to delete the entire session
    if session_details["host_id"] == user_id:
        return redirect(url_for('delete_session', session_id=session_id))
    
    try:
        # Remove user from the session
        db.execute("DELETE FROM session_users WHERE session_id = %s AND user_id = %s", (session_id, user_id))
    except Exception as e:
        print(f"Error removing user from session: {e}")
        return apology("Failed to leave session", 500)
    
    flash(f"Left Session {session_id} successfully!")
    return redirect('/join-session')


@app.route('/delete-session/<int:session_id>', methods=['GET'])
@login_required
def delete_session(session_id):
    db = get_db()
    user_id = session["user_id"]

    # Fetch session details
    db.execute("SELECT * FROM sessions WHERE id = %s", (session_id,))
    session_details = db.fetchone()

    if not session_details:
        return apology("Session not found", 404)

    # Ensure the user is the host
    if session_details["host_id"] != user_id:
        return apology("Only the host can delete this session", 403)

    try:
        # Count how many users are in the session
        db.execute("SELECT COUNT(*) AS count FROM session_users WHERE session_id = %s", (session_id,))
        user_count_row = db.fetchone()

        if user_count_row["count"] > 1:
            return apology("Cannot delete session with multiple users", 400)

        # Delete related data
        db.execute("DELETE FROM game_sentences WHERE session_id = %s", (session_id,))
        db.execute("DELETE FROM session_users WHERE session_id = %s", (session_id,))
        db.execute("DELETE FROM rounds WHERE session_id = %s", (session_id,))
        db.execute("DELETE FROM sessions WHERE id = %s", (session_id,))

    except Exception as e:
        print(f"Error deleting session: {e}")
        return apology("Failed to delete session", 500)

    flash(f"Deleted Session {session_id} successfully!")
    return redirect('/')


session_user_counts_waiting = {}
@app.route('/check-session-from-waiting/<int:session_id>', methods=['GET'])
@login_required
def check_session_from_waiting(session_id):
    db = get_db()
    user_id = session.get('user_id')

    # Fetch current users in the session
    db.execute("""
        SELECT users.username, session_users.is_host
        FROM session_users
        JOIN users ON session_users.user_id = users.id
        WHERE session_users.session_id = %s
    """, (session_id,))
    users_in_session = db.fetchall()

    user_count = len(users_in_session)

    # Ensure structure exists for this session
    if session_id not in session_user_counts_waiting:
        session_user_counts_waiting[session_id] = {}

    previous_count = session_user_counts_waiting[session_id].get(user_id, 0)

    # Save current count
    session_user_counts_waiting[session_id][user_id] = user_count

    if user_count != previous_count:
        return jsonify({
            'new_change': True,
            'user_count': user_count,
            'users': [{'username': user['username'], 'is_host': user['is_host']} for user in users_in_session]
        })

    return jsonify({'new_change': False})


session_user_counts_join = {}
@app.route('/check-session-from-join/<int:session_id>', methods=['GET'])
@login_required
def check_session_from_join(session_id):
    db = get_db()
    user_id = session.get('user_id')  # Get the logged-in user's ID

    # Query to get users in the session
    db.execute("""
        SELECT users.username, session_users.is_host
        FROM session_users
        JOIN users ON session_users.user_id = users.id
        WHERE session_users.session_id = %s
    """, (session_id,))
    users_in_session = db.fetchall()

    user_count = len(users_in_session)

    # Ensure the session entry exists in the dictionary
    if session_id not in session_user_counts_join:
        session_user_counts_join[session_id] = {}

    # Get the previous user count for this session and user, default to 0 if not found
    previous_count = session_user_counts_join[session_id].get(user_id, 0)

    # Update the dictionary with the current user count for this session and user
    session_user_counts_join[session_id][user_id] = user_count

    # Debugging
    print(f"Session {session_id} (User {user_id}): previous_count = {previous_count}, user_count = {user_count}")

    # Check if there is a change in the user count
    if user_count != previous_count:
        return jsonify({
            'new_change': True,
            'user_count': user_count,
            'users': [{'username': user['username'], 'is_host': user['is_host']} for user in users_in_session]
        })
    return jsonify({
            'new_change': False,
            'user_count': user_count,
            'users': [{'username': user['username'], 'is_host': user['is_host']} for user in users_in_session]
        })


# Dictionary to store the last known user count for each session
session_user_counts_homepage = {}

@app.route('/check-session-from-homepage/<int:session_id>', methods=['GET'])
@login_required
def check_session_from_homepage(session_id):
    db = get_db()
    user_id = session.get('user_id')

    db.execute("SELECT active FROM sessions WHERE id = %s", (session_id,))
    session_status = db.fetchone()

    if not session_status or not session_status["active"]:
        return jsonify({
            'new_change': False,
            'user_count': 0,
            'users': [],
            'session_active': False
        })

    db.execute("""
        SELECT users.username, session_users.is_host
        FROM session_users
        JOIN users ON session_users.user_id = users.id
        WHERE session_users.session_id = %s
    """, (session_id,))
    users_in_active_session = db.fetchall()
    user_count = len(users_in_active_session)

    if session_id not in session_user_counts_homepage:
        session_user_counts_homepage[session_id] = {}
    previous_count = session_user_counts_homepage[session_id].get(user_id, 0)
    session_user_counts_homepage[session_id][user_id] = user_count

    if user_count != previous_count:
        return jsonify({
            'new_change': True,
            'user_count': user_count,
            'users': [{'username': user['username'], 'is_host': user['is_host']} for user in users_in_active_session],
            'session_active': True
        })

    return jsonify({
        'new_change': False,
        'user_count': user_count,
        'users': [],
        'session_active': True
    })



# Dictionary to store the last known number of sessions for each user
user_session_counts = {}
@app.route('/check-number-of-sessions', methods=['GET'])
@login_required
def check_number_of_sessions():
    db = get_db()
    user_id = session.get('user_id')
    db.execute("SELECT COUNT(*) AS count FROM sessions WHERE active = TRUE")
    result = db.fetchone()
    # print(dict(result))
    current_count = result['count'] if result else 0

    # Get the previous count for this user
    previous_count = user_session_counts.get(user_id, 0)

    # Debugging
    print(f"User {user_id}: Previous session count: {previous_count}, Current session count: {current_count}")

    if current_count != previous_count:
        user_session_counts[user_id] = current_count
        return jsonify({'new_change': True, 'session_count': current_count})

    return jsonify({'new_change': False})


@app.route('/start-game/<int:session_id>', methods=['GET', 'POST'])
@login_required
def start_game(session_id):
    db = get_db()
    user_id = session["user_id"]

    if request.method == "POST":
        db.execute("DELETE FROM gif_urls WHERE session_id = %s", (session_id,))

        db.execute("SELECT * FROM sessions WHERE id = %s", (session_id,))
        session_details = db.fetchone()
        if not session_details:
            return apology("Session not found", 404)

        num_of_statements = session_details["players"] * (session_details["points_to_win"] - 1) + 1

        db.execute("SELECT COUNT(*) AS count FROM game_sentences WHERE session_id = %s", (session_id,))
        existing_statements_count = db.fetchone()["count"]

        db.execute("SELECT user_id FROM session_users WHERE session_id = %s", (session_id,))
        players = db.fetchall()

        for player in players:
            db.execute(
                "SELECT 1 FROM user_scores WHERE session_id = %s AND user_id = %s",
                (session_id, player["user_id"])
            )
            score_exists = db.fetchone()

            if not score_exists:
                db.execute(
                    "INSERT INTO user_scores (session_id, user_id, score) VALUES (%s, %s, 0)",
                    (session_id, player["user_id"])
                )

        if existing_statements_count == num_of_statements:
            try:
                db.execute("INSERT INTO game_started (session_id, started) VALUES (%s, TRUE)", (session_id,))
            except:
                db.execute("UPDATE game_started SET started = TRUE WHERE session_id = %s", (session_id,))
            db.execute("UPDATE rounds SET started = TRUE WHERE session_id = %s AND round = 1", (session_id,))
            return redirect(url_for('game_page', session_id=session_id, round=1))

        # Generate statements using OpenAI
        prompt = f"Give me {num_of_statements} statements about {session_details['category']} for a GIF reaction game where users search for a GIF that best describes it."

        try:
            completion = client.chat.completions.create(
                model="gpt-3.5-turbo",
                messages=[
                    {"role": "system", "content": "You are playing a GIF reaction game where users search for a GIF that best describes a statement."},
                    {"role": "user", "content": prompt}
                ]
            )

            response_text = completion.choices[0].message.content.strip()
            sentences = split_sentences(response_text)
            cleaned = [s.strip('. "').strip() for s in sentences if s.strip()]

            for sentence in cleaned:
                db.execute(
                    "INSERT INTO game_sentences (session_id, sentence) VALUES (%s, %s)",
                    (session_id, sentence)
                )

            try:
                db.execute("INSERT INTO game_started (session_id, started) VALUES (%s, TRUE)", (session_id,))
            except:
                db.execute("UPDATE game_started SET started = TRUE WHERE session_id = %s", (session_id,))
            db.execute("UPDATE rounds SET started = TRUE WHERE session_id = %s AND round = 1", (session_id,))

            return redirect(url_for('game_page', session_id=session_id, round=1))

        except Exception as e:
            print(f"OpenAI error: {e}")
            return apology("Error generating statements", 500)

    return redirect(url_for('session_details', session_id=session_id))


@app.route('/check-game-start/<int:session_id>', methods=['GET'])
@login_required
def check_game_start(session_id):
    db = get_db()

    db.execute("SELECT started FROM game_started WHERE session_id = %s", (session_id,))
    game_started = db.fetchone()
    # print(type(game_started))
    print(game_started)

    if game_started:
        return jsonify({'started': game_started['started']})
    return jsonify({'started': False})


# @app.route('/search-gifs', methods=['GET'])
# @login_required
# def search_gifs():
#     query = request.args.get('query')
#     response = requests.get(f'https://api.giphy.com/v1/gifs/search?api_key={GIPHY_API_KEY}&q={query}&limit=25')
#     gifs = response.json().get('data', [])
#     return {'gifs': gifs}

@app.route('/search-gifs', methods=['GET'])
@login_required
def search_gifs():
    query = request.args.get('query')
    response = requests.get(f'https://api.giphy.com/v1/gifs/search', params={
        'api_key': GIPHY_API_KEY,
        'q': query,
        'limit': 25
    })
    gifs = response.json().get('data', [])
    return jsonify({'gifs': gifs})


@app.route('/game-page/<int:session_id>/<int:round>', methods=['GET'])
@login_required
def game_page(session_id, round):
    db = get_db()
    
    db.execute("SELECT * FROM sessions WHERE id = %s", (session_id,))
    session_details = db.fetchone()
    if not session_details:
        return apology("Session not found", 404)

    db.execute("SELECT sentence FROM game_sentences WHERE session_id = %s ORDER BY id", (session_id,))
    sentences = db.fetchall()
    cleaned_sentences = [row['sentence'] for row in sentences]

    print(f"Number of sentences: {len(cleaned_sentences)}")
    print(f"Requested round: {round}")

    if round <= 0 or round > len(cleaned_sentences):
        return apology("Invalid round number", 400)

    return render_template('game_page.html',
                           session_id=session_id,
                           round=round,
                           sentence=cleaned_sentences[round - 1],
                           game_session=session_details)


@app.route('/check-user-gif/<int:session_id>/<int:round>', methods=['GET'])  # Only host can access
@login_required
def check_user_gif(session_id, round):
    db = get_db()
    user_id = session.get('user_id')

    db.execute(
        "SELECT 1 FROM gif_urls WHERE session_id = %s AND user_id = %s AND round = %s",
        (session_id, user_id, round)
    )
    user_has_gif = db.fetchone()

    return {'user_has_gif': user_has_gif is not None}


@app.route('/stop-game/<int:session_id>', methods=['GET'])  # Only host can access
@login_required
def stop_game(session_id):
    db = get_db()

    db.execute("DELETE FROM votes WHERE session_id = %s", (session_id,))
    db.execute("DELETE FROM gif_urls WHERE session_id = %s", (session_id,))
    db.execute("DELETE FROM rounds WHERE session_id = %s AND round != 1", (session_id,))
    db.execute("UPDATE user_scores SET score = 0, round_updated = 0 WHERE session_id = %s", (session_id,))
    db.execute("UPDATE game_started SET started = FALSE WHERE session_id = %s", (session_id,))

    return redirect(url_for('session_details', session_id=session_id))


@app.route('/finish-game/<int:session_id>', methods=['GET', 'POST'])
@login_required
def finish_game(session_id):
    if request.method == "POST":
        db = get_db()
        db.execute("UPDATE sessions SET active = FALSE WHERE id = %s", (session_id,))

        return redirect('/')
    else:
        # You can handle GET requests here if needed
        return redirect(url_for('session_details', session_id=session_id))


@app.route('/save-gif/<int:session_id>/<int:round>', methods=['POST'])
@login_required
def save_gif(session_id, round):
    db = get_db()
    user_id = session.get('user_id')
    selected_gif = request.form.get('selected_gif')

    # Check if the user has already submitted a GIF for this round
    db.execute(
        "SELECT 1 FROM gif_urls WHERE session_id = %s AND user_id = %s AND round = %s",
        (session_id, user_id, round)
    )
    gif_already_selected = db.fetchone()

    if gif_already_selected:
        # If a GIF is already selected, do not insert another
        return redirect(url_for('round_results', session_id=session_id, round=round))

    if selected_gif and selected_gif != '':
        # User has selected a GIF
        db.execute(
            "INSERT INTO gif_urls (session_id, user_id, gif_url, round) VALUES (%s, %s, %s, %s)",
            (session_id, user_id, selected_gif, round)
        )
    else:
        # Timer expired or no GIF selected
        db.execute(
            "INSERT INTO gif_urls (session_id, user_id, gif_url, round, is_n) VALUES (%s, %s, NULL, %s, TRUE)",
            (session_id, user_id, round)
        )

    # Redirect to round results page
    return redirect(url_for('round_results', session_id=session_id, round=round))


@app.route('/round-results/<int:session_id>/<int:round>', methods=['GET'])
@login_required
def round_results(session_id, round):
    db = get_db()
    db.execute("SELECT * FROM sessions WHERE id = %s", (session_id,))
    session_details = db.fetchone()
    if not session_details:
        return apology("Session not found", 404)

    db.execute("""
        SELECT users.username, users.id, gif_urls.gif_url, gif_urls.is_n
        FROM gif_urls
        JOIN users ON gif_urls.user_id = users.id
        WHERE gif_urls.session_id = %s AND gif_urls.round = %s
    """, (session_id, round))
    gifs = db.fetchall()

    there_is_only_one_valid_gif = {'bool': False}
    there_are_no_valid_gifs = False

    if len(gifs) == session_details["players"]:
        db.execute("""
            SELECT COUNT(*) AS count
            FROM gif_urls
            WHERE session_id = %s AND round = %s AND is_n = FALSE
        """, (session_id, round))
        count_result = db.fetchone()
        number_of_valid_gifs = count_result['count'] if count_result else 0

        if number_of_valid_gifs == 1:
            there_is_only_one_valid_gif["bool"] = True
            # Get the user_id of the valid gif
            db.execute("""
                SELECT user_id FROM gif_urls
                WHERE session_id = %s AND round = %s AND is_n = FALSE
                LIMIT 1
            """, (session_id, round))
            valid_user = db.fetchone()
            there_is_only_one_valid_gif["valid_user_id_gif"] = valid_user['user_id'] if valid_user else None
        elif number_of_valid_gifs == 0:
            there_are_no_valid_gifs = True

    return render_template(
        "round_results.html",
        game_session=session_details,
        session_id=session_id,
        round=round,
        gifs=gifs,
        there_is_only_one_valid_gif=there_is_only_one_valid_gif,
        there_are_no_valid_gifs=there_are_no_valid_gifs
    )


round_gif_counts = {}

@app.route('/check-round/<int:session_id>/<int:round>', methods=['GET'])
@login_required
def check_round(session_id, round):
    db = get_db()
    user_id = session.get('user_id')

    db.execute(
        "SELECT COUNT(*) AS count FROM gif_urls WHERE session_id = %s AND round = %s",
        (session_id, round)
    )
    gif_count_result = db.fetchone()
    gif_count = gif_count_result['count'] if gif_count_result else 0

    if session_id not in round_gif_counts:
        round_gif_counts[session_id] = {}

    previous_count = round_gif_counts[session_id].get(user_id, 0)
    round_gif_counts[session_id][user_id] = gif_count

    print(f"Session {session_id} (User {user_id}): previous_count = {previous_count}, current_count = {gif_count}")

    count_changed = (gif_count != previous_count)

    if count_changed:
        print("Change detected!")
        return jsonify({'new_change': True})

    print("No change detected.")
    return jsonify({'new_change': False})


@app.route('/input-vote/<int:session_id>/<int:round>', methods=['GET', 'POST'])
@login_required
def input_vote(session_id, round):
    db = get_db()
    if request.method == "POST":
        user_id = session.get('user_id')
        selected_username_id = request.form.get('vote_for_gif')

        # Prevent duplicate votes by checking if this user already voted for this round
        db.execute(
            "SELECT 1 FROM votes WHERE session_id = %s AND user_id = %s AND round = %s",
            (session_id, user_id, round)
        )
        existing_vote = db.fetchone()
        if existing_vote:
            # User already voted; redirect to results page without inserting again
            return redirect(url_for('winner_of_round', session_id=session_id, round=round))

        db.execute(
            "INSERT INTO votes (session_id, user_id, voted_for_user_id, round) VALUES (%s, %s, %s, %s)",
            (session_id, user_id, selected_username_id, round)
        )
        return redirect(url_for('winner_of_round', session_id=session_id, round=round))
    # Could handle GET or render voting page if needed
    return apology("Method not allowed", 405)


@app.route('/winner-of-round/<int:session_id>/<int:round>', methods=['GET'])
@login_required
def winner_of_round(session_id, round):
    db = get_db()
    db.execute("SELECT * FROM sessions WHERE id = %s", (session_id,))
    session_details = db.fetchone()
    if not session_details:
        return apology("Session not found", 404)

    db.execute("""
        SELECT votes.voted_for_user_id, users.username, users.id, COUNT(*) AS vote_count
        FROM votes
        JOIN users ON votes.voted_for_user_id = users.id
        WHERE votes.session_id = %s AND votes.round = %s
        GROUP BY votes.voted_for_user_id, users.username, users.id
        HAVING COUNT(*) = (
            SELECT MAX(cnt)
            FROM (
                SELECT COUNT(*) AS cnt
                FROM votes
                WHERE session_id = %s AND round = %s
                GROUP BY voted_for_user_id
            ) AS counts
        )
    """, (session_id, round, session_id, round))
    round_results = db.fetchall()

    db.execute("SELECT COUNT(*) AS count FROM votes WHERE session_id = %s AND round = %s", (session_id, round))
    number_of_votes_row = db.fetchone()
    number_of_votes = number_of_votes_row['count'] if number_of_votes_row else 0

    if number_of_votes == session_details['players']:
        for round_result in round_results:
            db.execute("""
                SELECT round_updated FROM user_scores
                WHERE session_id = %s AND user_id = %s AND round_updated = %s
            """, (session_id, round_result["id"], round))
            score_updated = db.fetchone()

            if not score_updated:
                db.execute("""
                    UPDATE user_scores 
                    SET score = score + 1, round_updated = %s 
                    WHERE session_id = %s AND user_id = %s
                """, (round, session_id, round_result["id"]))

    db.execute("""
        SELECT user_scores.score, user_scores.user_id, users.username 
        FROM user_scores 
        JOIN users ON user_scores.user_id = users.id 
        WHERE user_scores.session_id = %s
    """, (session_id,))
    scores = db.fetchall()

    return render_template('winner_round.html', game_session=session_details, round=round, round_results=round_results, scores=scores, number_of_votes=number_of_votes)


session_scores = {}

@app.route('/check-score-table/<int:session_id>', methods=['GET'])
@login_required
def check_score_table(session_id):
    db = get_db()
    user_id = session.get('user_id')  # Get the logged-in user's ID

    db.execute("SELECT user_id, score FROM user_scores WHERE session_id = %s", (session_id,))
    scores = db.fetchall()

    current_scores = {score['user_id']: score['score'] for score in scores}

    if session_id not in session_scores:
        session_scores[session_id] = {}

    previous_scores = session_scores[session_id].get(user_id, {})

    session_scores[session_id][user_id] = current_scores

    if current_scores != previous_scores:
        return {'new_score_change': True}
    else:
        return {'new_score_change': False}


@app.route('/start-next-round/<int:session_id>/<int:round>', methods=['GET', 'POST'])
@login_required
def start_next_round(session_id, round):
    db = get_db()
    if request.method == "POST":
        db.execute("SELECT * FROM sessions WHERE id = %s", (session_id,))
        session_details = db.fetchone()
        if not session_details:
            return apology("Session not found", 404)

        db.execute("SELECT user_id, score FROM user_scores WHERE session_id = %s", (session_id,))
        scores = db.fetchall()

        for score in scores:
            if score['score'] == session_details['points_to_win']:
                db.execute(
                    "UPDATE user_scores SET winner = TRUE WHERE session_id = %s AND user_id = %s",
                    (session_id, score['user_id'])
                )

        db.execute(
            "SELECT 1 FROM user_scores WHERE session_id = %s AND winner = TRUE",
            (session_id,)
        )
        user_has_won = db.fetchone()

        if user_has_won:
            return redirect(url_for('winner_game', session_id=session_id))

        next_round = round + 1

        db.execute(
            "SELECT 1 FROM rounds WHERE session_id = %s AND round = %s",
            (session_id, next_round)
        )
        round_exists = db.fetchone()

        if round_exists:
            db.execute(
                "UPDATE rounds SET started = TRUE WHERE session_id = %s AND round = %s",
                (session_id, next_round)
            )
        else:
            db.execute(
                "INSERT INTO rounds (session_id, round, started) VALUES (%s, %s, TRUE)",
                (session_id, next_round)
            )

        return redirect(url_for('game_page', session_id=session_id, round=next_round))

    return apology("Invalid method", 405)  # Optional safeguard


@app.route('/check-winner-game/<int:session_id>', methods=['GET'])
@login_required
def check_winner_game(session_id):
    db = get_db()
    db.execute("SELECT 1 FROM user_scores WHERE session_id = %s AND winner = TRUE", (session_id,))
    someone_won = db.fetchone()

    return {'player_has_won': bool(someone_won)}


@app.route('/check-next-round/<int:session_id>/<int:round>', methods=['GET'])
@login_required
def check_next_round(session_id, round):
    db = get_db()
    next_round = round + 1

    db.execute(
        "SELECT 1 FROM rounds WHERE session_id = %s AND round = %s AND started = TRUE",
        (session_id, next_round)
    )
    next_round_started = db.fetchone()

    return {'next_round_started': bool(next_round_started)}


@app.route('/winner-game/<int:session_id>', methods=['GET'])
@login_required
def winner_game(session_id):
    db = get_db()

    db.execute("SELECT * FROM sessions WHERE id = %s", (session_id,))
    session_details = db.fetchone()
    if not session_details:
        return apology("Session not found", 404)

    db.execute("""
        SELECT users.username, user_scores.user_id, user_scores.score
        FROM user_scores
        JOIN users ON user_scores.user_id = users.id
        WHERE user_scores.session_id = %s AND user_scores.winner = TRUE
    """, (session_id,))
    winners = db.fetchall()

    db.execute("""
        SELECT user_scores.score, user_scores.user_id, users.username
        FROM user_scores
        JOIN users ON user_scores.user_id = users.id
        WHERE user_scores.session_id = %s
    """, (session_id,))
    scores = db.fetchall()

    return render_template('winner_game.html', game_session=session_details, winners=winners, scores=scores)


@app.route('/history')
@login_required
def history():
    db = get_db()
    user_id = session.get('user_id')

    # Fetch all inactive sessions the user participated in
    db.execute("""
        SELECT * FROM sessions 
        WHERE id IN (
            SELECT session_id FROM session_users WHERE user_id = %s
        ) AND active = FALSE
        ORDER BY id DESC
    """, (user_id,))
    session_details = db.fetchall()

    if not session_details:
        return render_template('history.html', old_game_sessions=[], winners={})

    winners = {}

    for session_detail in session_details:
        session_id = session_detail["id"]

        # Get all winners for the session
        db.execute("""
            SELECT users.username
            FROM user_scores
            JOIN users ON user_scores.user_id = users.id
            WHERE user_scores.winner = TRUE AND user_scores.session_id = %s
        """, (session_id,))
        winners[session_id] = db.fetchall()  # list of dicts with 'username'

    return render_template('history.html', old_game_sessions=session_details, winners=winners)



@app.teardown_appcontext
def teardown_db(exception):
    close_db()

if __name__ == "__main__":
    app.run(host='0.0.0.0', port=5000, debug=True)
