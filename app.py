from flask import Flask
from flask_socketio import SocketIO
from routes import configure_routes
import logging

# Set up logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger('chat_app')

# Initialize Flask app and SocketIO
app = Flask(__name__)
app.secret_key = 'your_secret_key_here'  # Add a secret key for session management
socketio = SocketIO(app, cors_allowed_origins="*", logger=logger, engineio_logger=True)

# Import and configure routes
configure_routes(app, socketio)

if __name__ == '__main__':
    socketio.run(app, debug=True, host='127.0.0.1', port=5004)