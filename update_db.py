import sqlite3

# Connect to the database
conn = sqlite3.connect('users.db')
cursor = conn.cursor()

# Start transaction
cursor.execute('BEGIN TRANSACTION;')

# Create temporary table with new schema
cursor.execute('''
    CREATE TABLE users_temp (
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
cursor.execute('''
    INSERT INTO users_temp (email, name, password, nativeLanguage, targetLanguage, last_partner, average_rating)
    SELECT email, name, password, nativeLanguage, targetLanguage, last_partner, average_rating FROM users
''')
cursor.execute('DROP TABLE users')
cursor.execute('ALTER TABLE users_temp RENAME TO users')
cursor.execute('COMMIT')

# Close the connection
conn.close()
print("Database schema updated successfully!")