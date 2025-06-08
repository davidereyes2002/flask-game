import psycopg2
import psycopg2.extras
import os
from flask import g

DATABASE_URL = os.getenv("DATABASE_URL")

def get_db():
    if 'db' not in g:
        connection_url = DATABASE_URL
        conn = psycopg2.connect(connection_url)
        conn.autocommit = True
        # This cursor will return rows as dictionaries
        g.db = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    return g.db

def close_db(e=None):
    db = g.pop('db', None)
    if db is not None:
        db.close()
