import csv
import datetime
import pytz
import requests
import urllib
import uuid

from flask import redirect, render_template, request, session
from functools import wraps


def apology(message, code=400):
    """Render message as an apology to user."""

    def escape(s):
        """
        Escape special characters.

        https://github.com/jacebrowning/memegen#special-characters
        """
        for old, new in [
            ("-", "--"),
            (" ", "-"),
            ("_", "__"),
            ("?", "~q"),
            ("%", "~p"),
            ("#", "~h"),
            ("/", "~s"),
            ('"', "''"),
        ]:
            s = s.replace(old, new)
        return s

    return render_template("apology.html", top=code, bottom=escape(message)), code


def login_required(f):
    """
    Decorate routes to require login.

    https://flask.palletsprojects.com/en/latest/patterns/viewdecorators/
    """

    @wraps(f)
    def decorated_function(*args, **kwargs):
        if session.get("user_id") is None:
            return redirect("/welcome")
        return f(*args, **kwargs)

    return decorated_function


def is_password_complex(password):
    """Check if password meets complexity requirements"""
    if len(password) < 8:
        return False

    has_upper = False
    has_digit = False
    has_symbol = False
    symbols = "@$!%*?&"

    for char in password:
        if char.isupper():
            has_upper = True
        elif char.isdigit():
            has_digit = True
        elif char in symbols:
            has_symbol = True

        # Exit early if all criteria are met
        if has_upper and has_digit and has_symbol:
            return True

    return False


def split_sentences(text):
    sentences = []
    current_sentence = ""
    for char in text:
        if char.isdigit() and not current_sentence.endswith("."):
            if current_sentence.strip():
                sentences.append(current_sentence.strip())
            current_sentence = ""
        else:
            current_sentence += char
    if current_sentence.strip():
        sentences.append(current_sentence.strip())
    return sentences
