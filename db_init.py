# db_init.py
import sqlite3
import time

DB = "portfolio.db"

def init():
    conn = sqlite3.connect(DB)
    c = conn.cursor()

    # folders: id, name, created_at
    c.execute('''
        CREATE TABLE IF NOT EXISTS folders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            created_at INTEGER NOT NULL
        )
    ''')

    # files: id, folder_id (nullable), name, filename (on disk), file_type, created_at
    c.execute('''
        CREATE TABLE IF NOT EXISTS files (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            folder_id INTEGER,
            name TEXT NOT NULL,
            filename TEXT NOT NULL,
            file_type TEXT NOT NULL,
            created_at INTEGER NOT NULL,
            FOREIGN KEY(folder_id) REFERENCES folders(id) ON DELETE CASCADE
        )
    ''')

    # ✅ profile: id, name, title, bio, profile_picture, email, github, linkedin
    c.execute('''
        CREATE TABLE IF NOT EXISTS profile (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            title TEXT,
            bio TEXT,
            profile_picture TEXT,
            email TEXT,
            github TEXT,
            linkedin TEXT
        )
    ''')

    conn.commit()

    # ✅ Insert default row if empty (so the app always finds one)
    c.execute('SELECT COUNT(*) FROM profile')
    if c.fetchone()[0] == 0:
        c.execute('''
            INSERT INTO profile (name, title, bio, profile_picture, email, github, linkedin)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        ''', (
            'Dimlas DSA',
            'Computer Engineering Student',
            'Passionate about embedded systems, AI, and full-stack development.',
            'Profile.png',
            'earljhonddimla@iskolarngbayan.edu.ph',
            'Earl-cmyk',
            'https://linkedin.com/in/earldimla'
        ))
        conn.commit()
        print("✅ Default profile created.")

    conn.close()
    print("Initialized DB:", DB)

if __name__ == "__main__":
    init()
