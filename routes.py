from flask import Flask, request, render_template, redirect, url_for, session, jsonify
from flask_socketio import SocketIO, emit, join_room
import sqlite3
from models import init_db
import logging

logger = logging.getLogger('chat_app')

def configure_routes(app, socketio):
    init_db()

    @app.route('/')
    def home():
        return render_template('home.html')

    @app.route('/signup', methods=['GET', 'POST'])
    def signup():
        if request.method == 'POST':
            email = request.form['email']
            name = request.form['name']
            password = request.form['password']
            native = request.form['native_language']      # updated
            target = request.form['target_language']      # updated
            with sqlite3.connect('users.db') as conn:
                try:
                    conn.execute('INSERT INTO users (email, name, password, nativeLanguage, targetLanguage, last_partner, average_rating, bio) VALUES (?, ?, ?, ?, ?, ?, ?, ?)',
                                (email, name, password, native, target, None, 0.0, ''))
                    conn.commit()
                    return render_template('signup_success.html')
                except sqlite3.IntegrityError:
                    return render_template('error.html', message='Email already exists! <a href="/signup">Try again</a>')
        return render_template('signup.html')

    @app.route('/login', methods=['GET', 'POST'])
    def login():
        if request.method == 'POST':
            email = request.form['email']
            password = request.form['password']
            with sqlite3.connect('users.db') as conn:
                cursor = conn.execute('SELECT password FROM users WHERE email = ?', (email,))
                user = cursor.fetchone()
                logger.debug(f'Login attempt for email: {email}, found user: {user}')
                if user and user[0] == password:
                    session['email'] = email
                    return redirect(url_for('dashboard', email=email))
                else:
                    return render_template('error.html', message='Wrong email or password! <a href="/login">Try again</a>')
        return render_template('login.html')

    @app.route('/search', methods=['GET', 'POST'])
    def search():
        if request.method == 'POST':
            target_language = request.form['target_language']  # updated
            email = request.form['email']
            with sqlite3.connect('users.db') as conn:
                cursor = conn.execute('SELECT email, name, nativeLanguage, targetLanguage FROM users WHERE nativeLanguage = ? AND email != ?',
                                    (target_language, email))
                matches = cursor.fetchall()
                matches_html = ''
                if matches:
                    user_native = conn.execute('SELECT nativeLanguage FROM users WHERE email = ?', (email,)).fetchone()[0]
                    for match in matches:
                        score = 1 if match[3] == user_native else 0
                        cursor.execute('SELECT status FROM partnership_requests WHERE (sender_email = ? AND receiver_email = ?) OR (sender_email = ? AND receiver_email = ?) AND status = ?',
                                      (email, match[0], match[0], email, 'accepted'))
                        is_partner = cursor.fetchone()
                        request_button = '''
                            <form method="POST" action="/send_request" style="display:inline;">
                                <input type="hidden" name="receiver_email" value="{0}">
                                <input type="hidden" name="sender_email" value="{1}">
                                <button type="submit">Send Request</button>
                            </form>
                        '''.format(match[0], email) if not is_partner else ''
                        matches_html += f'''
                            <li>
                                <span>{match[1]} ({match[0]}) - Speaks: {match[2]}, Wants: {match[3]} (Compatibility: {score}/1)</span>
                                {request_button}
                            </li>
                        '''
                else:
                    matches_html = '<li>No matches found!</li>'
                return render_template('search_results.html', matches_html=matches_html, email=email)
        return render_template('search.html', email=request.args.get('email', ''))

    @app.route('/send_request', methods=['POST'])
    def send_request():
        sender_email = request.form['sender_email']
        receiver_email = request.form['receiver_email']
        with sqlite3.connect('users.db') as conn:
            cursor = conn.execute('SELECT id FROM notifications WHERE user_email = ? AND type = ? AND related_email = ? AND read_status = 0',
                                (receiver_email, 'request', sender_email))
            if not cursor.fetchone():
                conn.execute('INSERT INTO partnership_requests (sender_email, receiver_email) VALUES (?, ?)',
                            (sender_email, receiver_email))
                conn.execute('INSERT INTO notifications (user_email, type, related_email) VALUES (?, ?, ?)',
                            (receiver_email, 'request', sender_email))
                conn.commit()
                socketio.emit('notification', {'user': receiver_email, 'type': 'request', 'related_email': sender_email}, room=receiver_email)
        return redirect(url_for('search', email=sender_email))

    @app.route('/accept_request')
    def accept_request():
        sender_email = request.args.get('sender_email')
        receiver_email = request.args.get('receiver_email')
        with sqlite3.connect('users.db') as conn:
            conn.execute('UPDATE partnership_requests SET status = ? WHERE sender_email = ? AND receiver_email = ?', ('accepted', sender_email, receiver_email))
            cursor = conn.execute('SELECT id FROM notifications WHERE user_email = ? AND type = ? AND related_email = ? AND read_status = 0',
                                (sender_email, 'match', receiver_email))
            if not cursor.fetchone():
                conn.execute('INSERT INTO notifications (user_email, type, related_email) VALUES (?, ?, ?)',
                            (sender_email, 'match', receiver_email))
                conn.commit()
                socketio.emit('notification', {'user': sender_email, 'type': 'match', 'related_email': receiver_email}, room=sender_email)
        return redirect(url_for('dashboard', email=receiver_email))

    @app.route('/dashboard')
    def dashboard():
        email = request.args.get('email', session.get('email'))
        if not email:
            return render_template('error.html', message='Please login first! <a href="/login">Login</a>')
        with sqlite3.connect('users.db') as conn:
            cursor = conn.execute('SELECT email, name, nativeLanguage, targetLanguage, last_partner, average_rating, bio FROM users WHERE email = ?', (email,))
            user = cursor.fetchone()
            if not user:
                return render_template('error.html', message='User not found! <a href="/login">Login again</a>')
            last_partner_email = user[4] if user[4] else 'No recent partner'
            last_partner_name = conn.execute('SELECT name FROM users WHERE email = ?', (user[4],)).fetchone()
            last_partner_name = last_partner_name[0] if last_partner_name else 'Unknown'

            # Fetch accepted matches and check for unread messages
            cursor = conn.execute('SELECT sender_email, receiver_email FROM partnership_requests WHERE (receiver_email = ? AND status = ?) OR (sender_email = ? AND status = ?)',
                                (email, 'accepted', email, 'accepted'))
            matches = cursor.fetchall()
            matches_html = '<li>No matches yet!</li>' if not matches else ''
            for m in matches:
                partner_email = m[0] if m[0] != email else m[1]
                partner_name = conn.execute('SELECT name FROM users WHERE email = ?', (partner_email,)).fetchone()[0]
                cursor.execute('SELECT COUNT(*) FROM messages WHERE partner_email = ? AND user_email = ? AND read_status = 0',
                              (email, partner_email))
                unread_count = cursor.fetchone()[0]
                alert = '<span class="unread-alert"> (Unread)</span>' if unread_count > 0 else ''
                # Add session scheduling link for each match
                cursor.execute('SELECT id, scheduled_time, status FROM sessions WHERE (initiator_email = ? AND partner_email = ?) OR (initiator_email = ? AND partner_email = ?) AND status = ?',
                             (email, partner_email, partner_email, email, 'pending'))
                session_info = cursor.fetchone()
                session_link = f'<a href="/schedule_session?partner_email={partner_email}&user_email={email}">Schedule Session</a>' if not session_info else f'Session at {session_info[1]} ({session_info[2]})'
                matches_html += f'<li><a href="/chat?user_email={email}&partner_email={partner_email}">{partner_name}{alert}</a> | {session_link}</li>'

            # Fetch progress summary for both user and partner
            cursor.execute('SELECT activity_type, COUNT(*), SUM(duration_minutes) FROM progress WHERE user_email = ? GROUP BY activity_type',
                          (email,))
            user_progress = cursor.fetchall()
            partner_progress_html = ''
            if last_partner_email != 'No recent partner':
                cursor.execute('SELECT activity_type, COUNT(*), SUM(duration_minutes) FROM progress WHERE user_email = ? GROUP BY activity_type',
                              (last_partner_email,))
                partner_progress = cursor.fetchall()
                partner_progress_html = '<li>Partner Progress:</li>' if partner_progress else ''
                for activity in partner_progress:
                    activity_type, count, total_duration = activity
                    partner_progress_html += f'<li>{activity_type}: {count} sessions, {total_duration or 0} minutes</li>'
            progress_html = '<li>No progress recorded yet!</li>' if not user_progress else ''
            for activity in user_progress:
                activity_type, count, total_duration = activity
                progress_html += f'<li>{activity_type}: {count} sessions, {total_duration or 0} minutes</li>'

            # Fetch notifications
            cursor = conn.execute('SELECT type, related_email, timestamp FROM notifications WHERE user_email = ? AND read_status = 0', (email,))
            notifications = cursor.fetchall()
            notifications_html = '<li>No new notifications!</li>' if not notifications else ''
            for n in notifications:
                name = conn.execute('SELECT name FROM users WHERE email = ?', (n[1],)).fetchone()[0]
                notifications_html += f'<li>{name} sent you a {"partnership request" if n[0] == "request" else "match acceptance"} at {n[2]} <a href="#" onclick="markRead(\'{n[0]}\', \'{n[1]}\')">Mark as Read</a></li>'

            cursor = conn.execute('SELECT sender_email, receiver_email FROM partnership_requests WHERE receiver_email = ? AND status = ?', (email, 'pending'))
            requests = cursor.fetchall()
            requests_html = '<li>No pending requests!</li>' if not requests else ''.join([f'<li>{conn.execute("SELECT name FROM users WHERE email = ?", (r[0],)).fetchone()[0]} (<a href="/accept_request?sender_email={r[0]}&receiver_email={email}">Accept</a>)</li>' for r in requests])

            return render_template('dashboard.html', email=user[0], name=user[1], native=user[2], target=user[3], last_partner_name=last_partner_name, matches_html=matches_html, requests_html=requests_html, notifications_html=notifications_html, user_name=user[1], average_rating=user[5], bio=user[6], progress_html=progress_html, partner_progress_html=partner_progress_html)

    @app.route('/mark_read', methods=['POST'])
    def mark_read():
        email = request.args.get('email')
        type = request.args.get('type')
        related_email = request.args.get('related_email')
        with sqlite3.connect('users.db') as conn:
            cursor = conn.execute('UPDATE notifications SET read_status = 1 WHERE user_email = ? AND type = ? AND related_email = ? AND read_status = 0', (email, type, related_email))
            if cursor.rowcount > 0:
                conn.commit()
                return jsonify({'success': True})
            return jsonify({'success': False, 'error': 'No unread notification found'})

    @app.route('/logout')
    def logout():
        email = request.args.get('email')
        session.pop('email', None)
        return redirect(url_for('home'))

    @app.route('/chat')
    def chat():
        user_email = request.args.get('user_email')
        partner_email = request.args.get('partner_email')
        with sqlite3.connect('users.db') as conn:
            cursor = conn.execute('SELECT name FROM users WHERE email = ?', (partner_email,))
            partner = cursor.fetchone()
            if not partner:
                return render_template('error.html', message='Partner not found! <a href="/dashboard?email={{ email }}">Back to Dashboard</a>', email=user_email)
            # Mark messages as read when entering chat
            conn.execute('UPDATE messages SET read_status = 1 WHERE partner_email = ? AND user_email = ? AND read_status = 0',
                        (user_email, partner_email))
            conn.commit()
            # Log chat session progress for both user and partner
            conn.execute('INSERT INTO progress (user_email, activity_type, duration_minutes) VALUES (?, ?, ?)',
                        (user_email, 'chat_session', 0))
            conn.execute('INSERT INTO progress (user_email, activity_type, duration_minutes) VALUES (?, ?, ?)',
                        (partner_email, 'chat_session', 0))
            conn.commit()
            cursor = conn.execute('SELECT user_email, message, timestamp, read_status FROM messages WHERE (user_email = ? AND partner_email = ?) OR (user_email = ? AND partner_email = ?) ORDER BY timestamp',
                                (user_email, partner_email, partner_email, user_email))
            messages = cursor.fetchall()
        return render_template('chat.html', user_email=user_email, partner_email=partner_email, partner_name=partner[0], user_name=conn.execute('SELECT name FROM users WHERE email = ?', (user_email,)).fetchone()[0], messages=messages)

    @app.route('/send_message', methods=['POST'])
    def send_message():
        user_email = request.form['user_email']
        partner_email = request.form['partner_email']
        message = request.form['message']
        with sqlite3.connect('users.db') as conn:
            conn.execute('INSERT INTO messages (user_email, partner_email, message, read_status) VALUES (?, ?, ?, 0)',
                        (user_email, partner_email, message))
            conn.commit()
            room = ':'.join(sorted([user_email, partner_email]))
            socketio.emit('message', {'user': user_email, 'message': message, 'partner': partner_email}, room=room)
        return redirect(url_for('chat', user_email=user_email, partner_email=partner_email))

    @app.route('/send_phrase', methods=['POST'])
    def send_phrase():
        user_email = request.form['user_email']
        partner_email = request.form['partner_email']
        phrase = request.form['phrase']
        with sqlite3.connect('users.db') as conn:
            conn.execute('INSERT INTO messages (user_email, partner_email, message, read_status) VALUES (?, ?, ?, 0)',
                        (user_email, partner_email, phrase))
            conn.commit()
            room = ':'.join(sorted([user_email, partner_email]))
            socketio.emit('message', {'user': user_email, 'message': phrase, 'partner': partner_email}, room=room)
        return redirect(url_for('chat', user_email=user_email, partner_email=partner_email))

    @app.route('/submit_feedback', methods=['POST'])
    def submit_feedback():
        user_email = request.form['user_email']
        partner_email = request.form['partner_email']
        rating = int(request.form['rating'])
        comment = request.form['comment']
        with sqlite3.connect('users.db') as conn:
            conn.execute('INSERT INTO feedback (user_email, partner_email, rating, comment) VALUES (?, ?, ?, ?)',
                        (user_email, partner_email, rating, comment))
            cursor = conn.execute('SELECT AVG(rating) FROM feedback WHERE partner_email = ?', (partner_email,))
            new_avg_rating = cursor.fetchone()[0] or 0.0
            conn.execute('UPDATE users SET average_rating = ? WHERE email = ?', (new_avg_rating, partner_email))
            conn.commit()
        return redirect(url_for('dashboard', email=user_email))

    @app.route('/profile')
    def profile():
        email = request.args.get('email', session.get('email'))
        if not email:
            return redirect(url_for('login'))
        with sqlite3.connect('users.db') as conn:
            cursor = conn.execute('SELECT email, name, nativeLanguage, targetLanguage, average_rating, bio FROM users WHERE email = ?', (email,))
            user = cursor.fetchone()
            if not user:
                return redirect(url_for('login'))
            return render_template('profile.html', email=user[0], name=user[1], native=user[2], target=user[3], average_rating=user[4], bio=user[5])

    @app.route('/edit_profile', methods=['GET', 'POST'])
    def edit_profile():
        email = request.args.get('email', session.get('email'))
        if not email:
            return redirect(url_for('login'))
        with sqlite3.connect('users.db') as conn:
            if request.method == 'POST':
                name = request.form['name']
                native = request.form['native_language']      # updated
                target = request.form['target_language']      # updated
                bio = request.form['bio']
                conn.execute('UPDATE users SET name = ?, nativeLanguage = ?, targetLanguage = ?, bio = ? WHERE email = ?', (name, native, target, bio, email))
                conn.commit()
                return redirect(url_for('profile', email=email))
            cursor = conn.execute('SELECT name, nativeLanguage, targetLanguage, bio FROM users WHERE email = ?', (email,))
            user = cursor.fetchone()
            return render_template('edit_profile.html', email=email, name=user[0], native=user[1], target=user[2], bio=user[3])

    @app.route('/schedule_session', methods=['GET', 'POST'])
    def schedule_session():
        user_email = request.args.get('user_email')
        partner_email = request.args.get('partner_email')
        if not user_email or not partner_email:
            return redirect(url_for('dashboard', email=user_email))
        with sqlite3.connect('users.db') as conn:
            if request.method == 'POST':
                scheduled_time = request.form['scheduled_time']
                conn.execute('INSERT INTO sessions (initiator_email, partner_email, scheduled_time) VALUES (?, ?, ?)',
                            (user_email, partner_email, scheduled_time))
                # Log session scheduling as progress for both user and partner
                conn.execute('INSERT INTO progress (user_email, activity_type, activity_details) VALUES (?, ?, ?)',
                            (user_email, 'session_scheduled', f'With {partner_email} at {scheduled_time}'))
                conn.execute('INSERT INTO progress (user_email, activity_type, activity_details) VALUES (?, ?, ?)',
                            (partner_email, 'session_scheduled', f'With {user_email} at {scheduled_time}'))
                conn.commit()
                # Notify partner
                cursor = conn.execute('SELECT id FROM notifications WHERE user_email = ? AND type = ? AND related_email = ? AND read_status = 0',
                                    (partner_email, 'session', user_email))
                if not cursor.fetchone():
                    conn.execute('INSERT INTO notifications (user_email, type, related_email) VALUES (?, ?, ?)',
                                (partner_email, 'session', user_email))
                    conn.commit()
                    socketio.emit('notification', {'user': partner_email, 'type': 'session', 'related_email': user_email}, room=partner_email)
                return redirect(url_for('dashboard', email=user_email))
            return render_template('schedule_session.html', user_email=user_email, partner_email=partner_email)

    @socketio.on('join')
    def on_join(data):
        user = data['user']
        partner = data.get('partner')
        room = ':'.join(sorted([user, partner or user]))
        join_room(room)
        logger.debug(f'User {user} joined room {room}')
        join_room(user)  # Join user-specific room for notifications
        logger.debug(f'User {user} joined personal notification room')
        # Send initial notifications
        with sqlite3.connect('users.db') as conn:
            cursor = conn.execute('SELECT type, related_email, timestamp FROM notifications WHERE user_email = ? AND read_status = 0', (user,))
            for n in cursor.fetchall():
                socketio.emit('notification', {'user': user, 'type': n[0], 'related_email': n[1]}, room=user)

    @socketio.on('message')
    def on_message(data):
        user = data['user']
        partner = data['partner']
        message = data['message']
        room = ':'.join(sorted([user, partner]))
        logger.debug(f'Message from {user} to {partner} in room {room}: {message}')
        emit('message', {'user': user, 'message': message}, room=room)

    @socketio.on('typing')
    def on_typing(data):
        user = data['user']
        partner = data['partner']
        name = data['name']
        room = ':'.join(sorted([user, partner]))
        emit('typing', {'user': user, 'name': name}, room=room, include_self=False)

    @socketio.on('stop_typing')
    def on_stop_typing(data):
        user = data['user']
        partner = data['partner']
        room = ':'.join(sorted([user, partner]))
        emit('stop_typing', {'user': user}, room=room, include_self=False)

    @socketio.on('notification')
    def on_notification(data):
        emit('notification', data, room=data['user'])
