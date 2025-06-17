import sqlite3

def init_db():
    conn = sqlite3.connect('users.db')
    cursor = conn.cursor()
    # Ensure users table exists or update schema
    cursor.execute(''' SELECT count(name) FROM sqlite_master WHERE type='table' AND name='users' ''')
    if cursor.fetchone()[0] == 0:
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS users (
                email TEXT PRIMARY KEY,
                name TEXT,
                password TEXT,
                nativeLanguage TEXT,
                targetLanguage TEXT,
                last_partner TEXT,
                average_rating REAL DEFAULT 0.0,
                bio TEXT DEFAULT ''
            )
        ''')
    else:
        # Check if bio column exists and add it if not
        cursor.execute('PRAGMA table_info(users)')
        columns = [info[1] for info in cursor.fetchall()]
        if 'bio' not in columns:
            cursor.execute('ALTER TABLE users ADD COLUMN bio TEXT DEFAULT ""')
            conn.commit()

    # Ensure messages table exists
    cursor.execute(''' SELECT count(name) FROM sqlite_master WHERE type='table' AND name='messages' ''')
    if cursor.fetchone()[0] == 0:
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_email TEXT,
                partner_email TEXT,
                message TEXT,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                read_status INTEGER DEFAULT 0,
                FOREIGN KEY (user_email) REFERENCES users(email),
                FOREIGN KEY (partner_email) REFERENCES users(email)
            )
        ''')
    # Ensure partnership_requests table exists
    cursor.execute(''' SELECT count(name) FROM sqlite_master WHERE type='table' AND name='partnership_requests' ''')
    if cursor.fetchone()[0] == 0:
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS partnership_requests (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                sender_email TEXT,
                receiver_email TEXT,
                status TEXT DEFAULT 'pending',
                FOREIGN KEY (sender_email) REFERENCES users(email),
                FOREIGN KEY (receiver_email) REFERENCES users(email)
            )
        ''')
    # Ensure notifications table exists
    cursor.execute(''' SELECT count(name) FROM sqlite_master WHERE type='table' AND name='notifications' ''')
    if cursor.fetchone()[0] == 0:
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS notifications (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_email TEXT,
                type TEXT,
                related_email TEXT,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                read_status INTEGER DEFAULT 0,
                FOREIGN KEY (user_email) REFERENCES users(email)
            )
        ''')
    # Ensure feedback table exists
    cursor.execute(''' SELECT count(name) FROM sqlite_master WHERE type='table' AND name='feedback' ''')
    if cursor.fetchone()[0] == 0:
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS feedback (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_email TEXT,
                partner_email TEXT,
                rating INTEGER CHECK (rating >= 1 AND rating <= 5),
                comment TEXT,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_email) REFERENCES users(email),
                FOREIGN KEY (partner_email) REFERENCES users(email)
            )
        ''')
    # Ensure sessions table exists
    cursor.execute(''' SELECT count(name) FROM sqlite_master WHERE type='table' AND name='sessions' ''')
    if cursor.fetchone()[0] == 0:
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS sessions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                initiator_email TEXT,
                partner_email TEXT,
                scheduled_time DATETIME,
                status TEXT DEFAULT 'pending',
                FOREIGN KEY (initiator_email) REFERENCES users(email),
                FOREIGN KEY (partner_email) REFERENCES users(email)
            )
        ''')
    # Ensure progress table exists
    cursor.execute(''' SELECT count(name) FROM sqlite_master WHERE type='table' AND name='progress' ''')
    if cursor.fetchone()[0] == 0:
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS progress (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_email TEXT,
                activity_type TEXT,
                activity_details TEXT,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                duration_minutes INTEGER DEFAULT 0,
                FOREIGN KEY (user_email) REFERENCES users(email)
            )
        ''')
    conn.commit()
    conn.close()