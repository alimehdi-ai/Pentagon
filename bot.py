"""
PEMABOT - Main Bot Application
Flask-based chatbot using AIML, NLTK, and Neo4j
"""

from flask import Flask, render_template, request, jsonify, redirect, url_for
import os
import time
from datetime import datetime, timezone

# Fix for Python 3.8+ compatibility (time.clock was removed)
if not hasattr(time, 'clock'):
    time.clock = time.perf_counter

import aiml
from autocorrect import Speller
from context_store import ChatContextStore

# Import custom modules
from nltk_processor import (
    detect_intent, process_nlp, analyze_sentiment
)
from neo4j_handler import (
    store_chat, get_user_context, search_knowledge,
    generate_cypher_queries, is_connected,
    create_user, authenticate_user, get_user_by_id,
    get_or_create_session, get_user_sessions, get_chat_history,
    get_chat_history_by_session, get_graph_stats, get_agent_info,
    get_graph_schema, query_session_memory, get_session_memory,
    get_person_from_session, find_or_create_person
)

# Initialize spell checker
spell = Speller(lang='en')

# Initialize Flask app
app = Flask(__name__)

# AIML Configuration
BRAIN_FILE = "./data/aiml_brain.dump"
k = aiml.Kernel()

# Chat context storage (per session)
context_store = ChatContextStore(os.path.join("data", "chat_context.jsonl"))


def load_aiml_brain():
    """Load AIML brain from file or parse AIML files"""
    if os.path.exists(BRAIN_FILE):
        print("Loading from brain file: " + BRAIN_FILE)
        k.loadBrain(BRAIN_FILE)
    else:
        print("Parsing AIML files from data folder...")
        original_dir = os.getcwd()
        
        # Load all AIML files from data folder
        data_path = os.path.join(original_dir, "data")
        os.chdir(data_path)
        
        # Load startup.xml first if exists
        if os.path.exists("startup.xml"):
            print("  Loading startup.xml...")
            k.learn("startup.xml")
        
        # Load ALL .aiml files from data folder
        aiml_files = sorted([f for f in os.listdir(".") if f.endswith(".aiml")])
        print(f"  Found {len(aiml_files)} AIML files in data folder")
        for f in aiml_files:
            try:
                k.learn(f)
                print(f"  Loaded: {f}")
            except Exception as e:
                print(f"  Warning: Could not load {f}: {e}")
        os.chdir(original_dir)
        
        # Load custom AIML files from made-by-us folder
        made_by_us_path = os.path.join(original_dir, "made-by-us")
        if os.path.exists(made_by_us_path):
            print("Loading custom AIML files from made-by-us folder...")
            os.chdir(made_by_us_path)
            custom_files = sorted([f for f in os.listdir(".") if f.endswith(".aiml")])
            print(f"  Found {len(custom_files)} AIML files in made-by-us folder")
            for f in custom_files:
                try:
                    k.learn(f)
                    print(f"  Loaded: {f}")
                except Exception as e:
                    print(f"  Warning: Could not load {f}: {e}")
            os.chdir(original_dir)
        
        print(f"Total categories loaded: {k.numCategories()}")
        print("Saving brain file: " + BRAIN_FILE)
        k.saveBrain(BRAIN_FILE)


def set_bot_properties():
    """Set bot identity properties"""
    k.setBotPredicate("name", "Synapse")
    k.setBotPredicate("master", "Mehmood Hussain")
    k.setBotPredicate("botmaster", "teacher")
    k.setBotPredicate("birthday", "January 2026")
    k.setBotPredicate("location", "Pakistan")
    k.setBotPredicate("gender", "robot")
    k.setBotPredicate("species", "chatbot")
    print("Bot identity set: Synapse")


# Load AIML brain and set properties
load_aiml_brain()
set_bot_properties()

# Store for tracking conversation state per user
user_sessions = {}


@app.route("/")
def home():
    """Render home page"""
    return render_template("home.html")


@app.route("/login")
def login_page():
    """Render login page"""
    return render_template("login.html")


@app.route("/api/auth/signup", methods=['POST'])
def signup():
    """Handle user registration"""
    data = request.get_json()
    if not data:
        return jsonify({'success': False, 'message': 'No data provided'}), 400
    
    name = data.get('name', '').strip()
    username = data.get('username', '').strip().lower()
    email = data.get('email', '').strip().lower()
    password = data.get('password', '')
    
    # Validation
    if not all([name, username, email, password]):
        return jsonify({'success': False, 'message': 'All fields are required'}), 400
    
    if len(username) < 3:
        return jsonify({'success': False, 'message': 'Username must be at least 3 characters'}), 400
    
    if len(password) < 6:
        return jsonify({'success': False, 'message': 'Password must be at least 6 characters'}), 400
    
    if '@' not in email:
        return jsonify({'success': False, 'message': 'Invalid email address'}), 400
    
    # Create user
    success, message, user_data = create_user(username, name, email, password)
    
    if success:
        return jsonify({'success': True, 'message': message, 'user': user_data})
    else:
        return jsonify({'success': False, 'message': message}), 400


@app.route("/api/auth/login", methods=['POST'])
def login():
    """Handle user login"""
    data = request.get_json()
    print(f"[LOGIN DEBUG] Received data: {data}")
    if not data:
        return jsonify({'success': False, 'message': 'No data provided'}), 400
    
    username = data.get('username', '').strip().lower()
    password = data.get('password', '')
    print(f"[LOGIN DEBUG] Username: '{username}', Password length: {len(password)}")
    
    if not username or not password:
        return jsonify({'success': False, 'message': 'Username and password are required'}), 400
    
    # Authenticate user
    success, message, user_data = authenticate_user(username, password)
    
    if success:
        return jsonify({'success': True, 'message': message, 'user': user_data})
    else:
        return jsonify({'success': False, 'message': message}), 401


@app.route("/api/auth/user/<user_id>")
def get_user(user_id):
    """Get user info by ID"""
    user = get_user_by_id(user_id)
    if user:
        return jsonify({'success': True, 'user': user})
    return jsonify({'success': False, 'message': 'User not found'}), 404


def get_user_personal_response(query, user_id):
    """Check if query is asking about logged-in user's personal info and return appropriate response"""
    query_lower = query.lower().strip()
    
    # Get user data from database
    user_data = get_user_by_id(user_id)
    if not user_data:
        return None
    
    # Patterns for name questions
    name_patterns = ['what is my name', 'what\'s my name', 'whats my name', 'my name', 'who am i', 
                     'do you know my name', 'tell me my name', 'say my name', 'know my name']
    
    # Patterns for email questions
    email_patterns = ['what is my email', 'what\'s my email', 'whats my email', 'my email',
                      'do you know my email', 'tell me my email', 'my email address']
    
    # Patterns for username questions
    username_patterns = ['what is my username', 'what\'s my username', 'whats my username', 
                         'my username', 'do you know my username', 'tell me my username']
    
    # Patterns for general "about me" questions
    about_me_patterns = ['tell me about myself', 'what do you know about me', 'who am i to you',
                         'do you know me', 'what do you know about myself']
    
    # Check patterns and return appropriate response
    if any(pattern in query_lower for pattern in name_patterns):
        return f"Your name is {user_data['name']}! 😊"
    
    if any(pattern in query_lower for pattern in email_patterns):
        return f"Your email address is {user_data['email']} 📧"
    
    if any(pattern in query_lower for pattern in username_patterns):
        return f"Your username is {user_data['username']} 👤"
    
    if any(pattern in query_lower for pattern in about_me_patterns):
        return f"Of course I know you! You are {user_data['name']}, your username is {user_data['username']}, and your email is {user_data['email']}. How can I help you today? 😊"
    
    return None


def get_contextual_response(query, user_id, session_id):
    """Answer queries that require previous chat context in the same session."""
    query_lower = query.lower().strip()
    history = context_store.get_history(user_id, session_id, limit=10)

    last_user = context_store.get_last_user_message(user_id, session_id)
    last_bot = context_store.get_last_bot_message(user_id, session_id)

    # Check for "what did I say" type questions
    if any(p in query_lower for p in [
        "what did i say", "what i said", "my last message",
        "repeat what i said", "last message"
    ]):
        if last_user:
            return f"You said: {last_user}"

    if any(p in query_lower for p in [
        "what did you say", "what you said", "repeat that",
        "say that again", "your last reply", "your last response"
    ]):
        if last_bot:
            return f"I said: {last_bot}"

    if any(p in query_lower for p in [
        "summarize", "summary", "recap", "conversation so far",
        "what have we talked about"
    ]):
        context_text = context_store.get_context_text(user_id, session_id, limit=5)
        if context_text:
            return f"Here is a quick recap:\n{context_text}"

    # Try to answer from stored facts and conversation history
    fact_response = context_store.answer_from_context(user_id, session_id, query)
    if fact_response:
        return fact_response

    return None


def get_fact_acknowledgment(query, user_id, session_id):
    """Generate acknowledgment when user shares personal information."""
    import re
    query_lower = query.lower().strip()
    
    # Check if this message shares new information
    acknowledgments = {
        r"my (?:name is|name's) (\w+)": "Nice to meet you, {0}! I'll remember that. 😊",
        r"my (?:fav(?:ou?rite)?|favorite) (?:color|colour) is (\w+)": "Got it! {0} is a great color! 🎨 I'll remember that.",
        r"my (?:fav(?:ou?rite)?|favorite) food is (.+?)(?:\.|$)": "Yum! {0} sounds delicious! 🍽️ I'll remember that.",
        r"my (?:fav(?:ou?rite)?|favorite) movie is (.+?)(?:\.|$)": "Nice choice! I'll remember that {0} is your favorite movie! 🎬",
        r"my (?:fav(?:ou?rite)?|favorite) song is (.+?)(?:\.|$)": "Great taste in music! I'll remember {0}! 🎵",
        r"my (?:fav(?:ou?rite)?|favorite) book is (.+?)(?:\.|$)": "A book lover! I'll remember {0}! 📚",
        r"my (?:fav(?:ou?rite)?|favorite) game is (.+?)(?:\.|$)": "Cool! I'll remember that {0} is your favorite game! 🎮",
        r"my (?:fav(?:ou?rite)?|favorite) sport is (.+?)(?:\.|$)": "Nice! I'll remember that you love {0}! ⚽",
        r"my (?:fav(?:ou?rite)?|favorite) animal is (.+?)(?:\.|$)": "Awesome! I'll remember that you love {0}! 🦁",
        r"i am (\d+) years old": "Got it! You're {0} years old. I'll remember that! 🎂",
        r"i'm (\d+) years old": "Got it! You're {0} years old. I'll remember that! 🎂",
        r"i live in (.+?)(?:\.|$)": "Cool! {0} sounds nice! I'll remember you live there. 🏠",
        r"i am from (.+?)(?:\.|$)": "Nice! {0} is a great place! I'll remember that. 🌍",
        r"i'm from (.+?)(?:\.|$)": "Nice! {0} is a great place! I'll remember that. 🌍",
        r"i (?:like|love|enjoy) (\w+)": "Nice! I'll remember that you like {0}! ❤️",
        r"i have a (.+?) named (\w+)": "Aww! {1} the {0} sounds adorable! I'll remember that! 🐾",
        r"my pet(?:'s)? name is (\w+)": "Cute name! I'll remember that your pet is called {0}! 🐾",
        r"my birthday is (.+?)(?:\.|$)": "I'll remember your birthday is {0}! 🎉",
    }
    
    for pattern, response_template in acknowledgments.items():
        match = re.search(pattern, query_lower, re.IGNORECASE)
        if match:
            groups = match.groups()
            return response_template.format(*[g.strip() for g in groups])
    
    return None


@app.route("/get")
def get_bot_response():
    """Main endpoint to get bot response (returns full metadata)"""
    query = request.args.get('msg')
    user_id = request.args.get('user_id', 'default_user')
    session_id = request.args.get('session_id')  # Get session_id from query params
    original_query = query
    timestamp = datetime.now(timezone.utc).isoformat()
    
    # Initialize user session tracking if not exists
    if user_id not in user_sessions:
        user_sessions[user_id] = {}
    
    # Get or create session in Neo4j
    session_id = get_or_create_session(user_id, session_id)
    
    # Initialize session tracking for chat chain
    if session_id not in user_sessions[user_id]:
        user_sessions[user_id][session_id] = {'prev_chat_id': None}
    
    session_tracking = user_sessions[user_id][session_id]
    
    # Process NLP on original query (includes intent, entities, sentiment, WordNet nouns)
    nlp_data = process_nlp(original_query)
    nlp_data['intent'] = detect_intent(original_query)
    
    # Extract facts from current message BEFORE trying to respond
    # This allows "my favorite color is blue" to be stored before any response logic
    context_store._extract_facts(user_id, session_id, original_query)
    
    # Get user context for better responses
    context = get_user_context(user_id)
    
    # First check if user is asking about their personal info
    personal_response = get_user_personal_response(original_query, user_id)
    contextual_response = get_contextual_response(original_query, user_id, session_id)
    fact_acknowledgment = get_fact_acknowledgment(original_query, user_id, session_id)
    
    if personal_response:
        response = personal_response
        response_source = 'user_profile'
    elif contextual_response:
        response = contextual_response
        response_source = 'session_context'
    elif fact_acknowledgment:
        # User shared personal info, acknowledge it
        response = fact_acknowledgment
        response_source = 'fact_acknowledgment'
    else:
        # Try to find answer from Neo4j knowledge
        neo4j_response = search_knowledge(original_query, nlp_data['intent'], nlp_data['entities'])
        
        # Spell correction for AIML
        corrected_words = [spell(w) for w in original_query.split()]
        question = " ".join(corrected_words)
        
        # Determine bot response
        if neo4j_response:
            response = neo4j_response
            response_source = 'neo4j'
        else:
            # Fallback to AIML
            response = k.respond(question, session_id)
            response_source = 'aiml'
            if not response:
                response = ":)"
    
    # Enhance response with WordNet definition if applicable
    enhanced_response = response
    if response_source == 'aiml' and nlp_data['nouns'] and len(nlp_data['nouns']) > 0:
        if any(word in original_query.lower() for word in ['what is', 'define', 'meaning', 'explain']):
            noun_def = nlp_data['nouns'][0]
            if noun_def['definition'] and response == ":)":
                enhanced_response = f"'{noun_def['word']}' means: {noun_def['definition']}"

    # Generate Cypher queries for visualization
    cypher_queries, chat_id = generate_cypher_queries(
        user_id, session_id, original_query, enhanced_response, timestamp, nlp_data,
        session_tracking['prev_chat_id']
    )
    
    # Store Chat in Neo4j (links Session -> Chat -> Agent)
    chat_id = store_chat(
        user_id, session_id, original_query, enhanced_response, timestamp, nlp_data,
        session_tracking['prev_chat_id']
    )

    # Store Chat in local context store
    context_store.add_message(user_id, session_id, original_query, enhanced_response, timestamp)
    
    # Update session tracking with new chat ID
    session_tracking['prev_chat_id'] = chat_id
    
    # Return structured JSON output
    return jsonify({
        'cypher_queries': cypher_queries,
        'bot_reply': enhanced_response,
        'session_id': session_id,
        'metadata': {
            'user_id': user_id,
            'intent': nlp_data['intent'],
            'sentiment': nlp_data['sentiment'],
            'nouns': nlp_data['nouns'],
            'response_source': response_source,
            'neo4j_connected': is_connected(),
            'chat': {
                'id': chat_id,
                'input': original_query,
                'output': enhanced_response,
                'timestamp': timestamp
            }
        },
        'nlp': nlp_data
    })


@app.route("/api/chat", methods=['POST'])
def api_chat():
    """API endpoint that returns only structured JSON output (cypher_queries + bot_reply)"""
    data = request.get_json()
    if not data or 'msg' not in data:
        return jsonify({'error': 'Missing msg field'}), 400
    
    query = data.get('msg')
    user_id = data.get('user_id', 'default_user')
    original_query = query
    timestamp = datetime.now(timezone.utc).isoformat()
    session_id = data.get('session_id')
    
    # Initialize user session tracking if not exists
    if user_id not in user_sessions:
        user_sessions[user_id] = {}
    
    # Get or create session in Neo4j
    session_id = get_or_create_session(user_id, session_id)
    
    # Initialize session tracking for chat chain
    if session_id not in user_sessions[user_id]:
        user_sessions[user_id][session_id] = {'prev_chat_id': None}
    
    session_tracking = user_sessions[user_id][session_id]
    
    # Process NLP on original query
    nlp_data = process_nlp(original_query)
    nlp_data['intent'] = detect_intent(original_query)
    
    # Extract facts from current message BEFORE trying to respond
    context_store._extract_facts(user_id, session_id, original_query)
    
    # Try to find answer from Neo4j knowledge first
    neo4j_response = search_knowledge(original_query, nlp_data['intent'], nlp_data['entities'])
    contextual_response = get_contextual_response(original_query, user_id, session_id)
    fact_acknowledgment = get_fact_acknowledgment(original_query, user_id, session_id)
    
    # Spell correction for AIML
    corrected_words = [spell(w) for w in original_query.split()]
    question = " ".join(corrected_words)
    
    # Determine bot response
    if contextual_response:
        response = contextual_response
    elif fact_acknowledgment:
        # User shared personal info, acknowledge it
        response = fact_acknowledgment
    elif neo4j_response:
        response = neo4j_response
    else:
        response = k.respond(question, session_id)
        if not response:
            if nlp_data['nouns'] and len(nlp_data['nouns']) > 0:
                if any(word in original_query.lower() for word in ['what is', 'define', 'meaning', 'explain']):
                    noun_def = nlp_data['nouns'][0]
                    if noun_def['definition']:
                        response = f"'{noun_def['word']}' means: {noun_def['definition']}"
            if not response:
                response = ":)"
    
    # Generate Cypher queries for visualization
    cypher_queries, chat_id = generate_cypher_queries(
        user_id, session_id, original_query, response, timestamp, nlp_data,
        session_tracking['prev_chat_id']
    )
    
    # Store Chat in Neo4j
    chat_id = store_chat(
        user_id, session_id, original_query, response, timestamp, nlp_data,
        session_tracking['prev_chat_id']
    )

    # Store Chat in local context store
    context_store.add_message(user_id, session_id, original_query, response, timestamp)
    
    # Update session tracking
    session_tracking['prev_chat_id'] = chat_id
    
    # Return structured JSON output only
    return jsonify({
        'cypher_queries': cypher_queries,
        'bot_reply': response,
        'session_id': session_id
    })


@app.route("/api/context/<user_id>")
def get_context(user_id):
    """Get conversation context for a user"""
    context = get_user_context(user_id, limit=10)
    return jsonify({'user_id': user_id, 'context': context})


@app.route("/api/chat_history/<user_id>")
def api_get_chat_history(user_id):
    """Get full chat history for a user (across all sessions)"""
    history = get_chat_history(user_id)
    return jsonify({'user_id': user_id, 'history': history})


@app.route("/api/chat_history/<user_id>/<session_id>")
def api_get_session_chat_history(user_id, session_id):
    """Get chat history for a specific session"""
    history = get_chat_history_by_session(user_id, session_id)
    return jsonify({'user_id': user_id, 'session_id': session_id, 'history': history})


@app.route("/api/sessions/<user_id>")
def api_get_user_sessions(user_id):
    """Get all sessions for a user"""
    sessions = get_user_sessions(user_id)
    return jsonify({'user_id': user_id, 'sessions': sessions})


@app.route("/api/session/new/<user_id>", methods=['POST'])
def api_create_new_session(user_id):
    """Create a new chat session for a user"""
    session_id = get_or_create_session(user_id, None)  # Force new session
    return jsonify({'success': True, 'session_id': session_id})


@app.route("/api/graph/stats")
def api_get_graph_stats():
    """Get graph database statistics"""
    stats = get_graph_stats()
    return jsonify(stats)


@app.route("/api/graph/schema")
def api_get_graph_schema():
    """Get graph schema description"""
    schema = get_graph_schema()
    return jsonify(schema)


@app.route("/api/agent")
def api_get_agent():
    """Get agent (Pentagon) information"""
    agent = get_agent_info()
    return jsonify({'agent': agent})


@app.route("/api/status")
def get_status():
    """Get bot status including Neo4j connection status"""
    return jsonify({
        'status': 'running',
        'bot_name': 'Pentagon',
        'neo4j_connected': is_connected(),
        'aiml_categories': k.numCategories()
    })


if __name__ == "__main__":
    app.run(host='0.0.0.0', port=5000, debug=True)
