"""
Neo4j Database Handler for Pentagon Chatbot
Stores all chats inside Session nodes as properties: input1, output1, input2, output2, etc.
Graph Schema:
  Person ←[:IS_A]- User -[:HAS_SESSION]→ Session (contains inputN, outputN, intentN, sentimentN properties)
  Agent (Pentagon - static info node)
"""

from neo4j import GraphDatabase
import hashlib
import uuid
from datetime import datetime, timezone
import json

# Neo4j Connection Configuration
NEO4J_URI = "neo4j://127.0.0.1:7687"
NEO4J_USER = "neo4j"
NEO4J_PASSWORD = "Pakistan@2"

# Global driver instance
driver = None


def get_driver():
    """Get or create Neo4j driver instance"""
    global driver
    if driver is None:
        try:
            driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))
            driver.verify_connectivity()
            print("Neo4j connection established successfully!")
        except Exception as e:
            print(f"Failed to connect to Neo4j: {e}")
            return None
    return driver


def is_connected():
    """Check if Neo4j is connected"""
    try:
        d = get_driver()
        if d:
            d.verify_connectivity()
            return True
    except:
        pass
    return False


def hash_password(password):
    """Hash password using SHA-256"""
    return hashlib.sha256(password.encode()).hexdigest()


# ============== GRAPH INITIALIZATION ==============

def init_graph_structure():
    """Initialize base graph structure with Person and Agent nodes"""
    d = get_driver()
    if not d:
        return False
    
    try:
        with d.session() as session:
            # Clean up old sessions without chat_count (migration)
            session.run("""
                MATCH (s:Session)
                WHERE s.chat_count IS NULL
                SET s.chat_count = 0
            """)
            
            # Create base Person node (parent for all users)
            session.run("""
                MERGE (p:Person {type: 'base'})
                ON CREATE SET p.created_at = datetime()
            """)
            print("Base Person node initialized")
            
            # Create Agent node (Pentagon bot)
            session.run("""
                MERGE (a:Agent {name: 'Pentagon'})
                ON CREATE SET 
                    a.creator = 'Group A1',
                    a.members = ['Abdul Muqeet (S2024376069)', 'Zaryab Hassan (S2024376094)', 'Ali Mehdi (S2024376092)'],
                    a.city = 'lahore',
                    a.company = 'Devsinc',
                    a.created_at = datetime()
            """)
            print("Agent node initialized (Pentagon)")
            
            # Create admin user if not exists
            admin_exists = session.run("""
                MATCH (u:User {username: 'admin'})
                RETURN u
            """).single()
            
            if not admin_exists:
                admin_id = str(uuid.uuid4())
                session.run("""
                    MATCH (p:Person {type: 'base'})
                    CREATE (u:User {
                        id: $id,
                        username: 'admin',
                        name: 'Administrator',
                        email: 'admin@pentagon.ai',
                        password_hash: $password_hash,
                        created_at: datetime()
                    })
                    CREATE (u)-[:IS_A]->(p)
                """, id=admin_id, password_hash=hash_password('12345678'))
                print("Admin user created successfully (username: admin, password: 12345678)")
            
            print("Graph structure initialized successfully!")
            return True
    except Exception as e:
        print(f"Error initializing graph structure: {e}")
        return False


# ============== USER MANAGEMENT ==============

def create_user(username, name, email, password):
    """Create a new user linked to Person node"""
    d = get_driver()
    if not d:
        return False, "Database connection error", None
    
    try:
        with d.session() as session:
            # Check if username exists
            existing = session.run("""
                MATCH (u:User {username: $username})
                RETURN u
            """, username=username).single()
            
            if existing:
                return False, "Username already exists", None
            
            # Check if email exists
            email_exists = session.run("""
                MATCH (u:User {email: $email})
                RETURN u
            """, email=email).single()
            
            if email_exists:
                return False, "Email already registered", None
            
            # Create user linked to Person
            user_id = str(uuid.uuid4())
            session.run("""
                MATCH (p:Person {type: 'base'})
                CREATE (u:User {
                    id: $id,
                    username: $username,
                    name: $name,
                    email: $email,
                    password_hash: $password_hash,
                    created_at: datetime()
                })
                CREATE (u)-[:IS_A]->(p)
            """, id=user_id, username=username, name=name, email=email, 
                password_hash=hash_password(password))
            
            return True, "User created successfully", {
                'id': user_id,
                'username': username,
                'name': name,
                'email': email
            }
    except Exception as e:
        return False, f"Error creating user: {e}", None


def authenticate_user(username, password):
    """Authenticate user by username and password"""
    d = get_driver()
    if not d:
        return False, "Database connection error", None
    
    try:
        with d.session() as session:
            result = session.run("""
                MATCH (u:User {username: $username, password_hash: $password_hash})
                RETURN u.id as id, u.username as username, u.name as name, u.email as email
            """, username=username, password_hash=hash_password(password)).single()
            
            if result:
                return True, "Login successful", {
                    'id': result['id'],
                    'username': result['username'],
                    'name': result['name'],
                    'email': result['email']
                }
            return False, "Invalid username or password", None
    except Exception as e:
        return False, f"Authentication error: {e}", None


def get_user_by_id(user_id):
    """Get user information by ID"""
    d = get_driver()
    if not d:
        return None
    
    try:
        with d.session() as session:
            result = session.run("""
                MATCH (u:User {id: $user_id})
                RETURN u.id as id, u.username as username, u.name as name, u.email as email
            """, user_id=user_id).single()
            
            if result:
                return {
                    'id': result['id'],
                    'username': result['username'],
                    'name': result['name'],
                    'email': result['email']
                }
    except Exception as e:
        print(f"Error getting user: {e}")
    return None


# ============== SESSION MANAGEMENT ==============

def get_or_create_session(user_id, session_id=None):
    """Get existing session or create new one for user"""
    d = get_driver()
    if not d:
        return str(uuid.uuid4())
    
    try:
        with d.session() as session:
            # If session_id provided, verify it exists
            if session_id:
                existing = session.run("""
                    MATCH (u:User {id: $user_id})-[:HAS_SESSION]->(s:Session {id: $session_id})
                    RETURN s.id as id
                """, user_id=user_id, session_id=session_id).single()
                
                if existing:
                    return session_id
            
            # Create new session
            new_session_id = str(uuid.uuid4())
            session.run("""
                MATCH (u:User {id: $user_id})
                CREATE (s:Session {
                    id: $session_id,
                    started_at: datetime(),
                    chat_count: 0
                })
                CREATE (u)-[:HAS_SESSION]->(s)
            """, user_id=user_id, session_id=new_session_id)
            
            return new_session_id
    except Exception as e:
        print(f"Error creating session: {e}")
        return str(uuid.uuid4())


def get_user_sessions(user_id):
    """Get all sessions for a user"""
    d = get_driver()
    if not d:
        return []
    
    try:
        with d.session() as session:
            results = session.run("""
                MATCH (u:User {id: $user_id})-[:HAS_SESSION]->(s:Session)
                RETURN s.id as session_id, s.started_at as started_at, s.chat_count as chat_count
                ORDER BY s.started_at DESC
            """, user_id=user_id)
            
            sessions = []
            for record in results:
                sessions.append({
                    'session_id': record['session_id'],
                    'started_at': str(record['started_at']) if record['started_at'] else None,
                    'chat_count': record['chat_count'] or 0
                })
            return sessions
    except Exception as e:
        print(f"Error getting sessions: {e}")
        return []


# ============== CHAT STORAGE (inputN: outputN format) ==============

def store_chat(user_id, session_id, user_input, agent_output, timestamp, nlp_data, prev_chat_id=None):
    """
    Store chat in Session node as properties: input1, output1, intent1, sentiment1, timestamp1, etc.
    """
    d = get_driver()
    if not d:
        return str(uuid.uuid4())
    
    try:
        with d.session() as session:
            # Get current chat count from session
            result = session.run("""
                MATCH (s:Session {id: $session_id})
                RETURN s.chat_count as count
            """, session_id=session_id).single()
            
            current_count = 0
            if result and result['count']:
                current_count = result['count']
            
            # Increment chat count
            new_count = current_count + 1
            
            # Property names for this chat
            input_key = f"input{new_count}"
            output_key = f"output{new_count}"
            intent_key = f"intent{new_count}"
            sentiment_key = f"sentiment{new_count}"
            timestamp_key = f"timestamp{new_count}"
            
            # Extract sentiment label
            sentiment = "neutral"
            if nlp_data and 'sentiment' in nlp_data and nlp_data['sentiment']:
                sentiment = nlp_data['sentiment'].get('sentiment', 'neutral')
            
            # Extract intent
            intent = nlp_data.get('intent', 'general') if nlp_data else 'general'
            
            # Use dynamic property setting with backticks for property names
            session.run(f"""
                MATCH (s:Session {{id: $session_id}})
                SET s.chat_count = $new_count,
                    s.`{input_key}` = $user_input,
                    s.`{output_key}` = $agent_output,
                    s.`{intent_key}` = $intent,
                    s.`{sentiment_key}` = $sentiment,
                    s.`{timestamp_key}` = $timestamp,
                    s.last_updated = datetime()
            """, session_id=session_id, new_count=new_count, 
                user_input=user_input, agent_output=agent_output,
                intent=intent, sentiment=sentiment, timestamp=timestamp)
            
            # Return a chat ID (based on session and count)
            return f"{session_id}_chat{new_count}"
    except Exception as e:
        print(f"Error storing chat: {e}")
        return str(uuid.uuid4())


def get_chat_history(user_id):
    """Get all chats for a user across all sessions (reads inputN, outputN properties)"""
    d = get_driver()
    if not d:
        return []
    
    try:
        with d.session() as session:
            # Get all sessions with their properties
            results = session.run("""
                MATCH (u:User {id: $user_id})-[:HAS_SESSION]->(s:Session)
                RETURN s as session_node
                ORDER BY s.started_at ASC
            """, user_id=user_id)
            
            all_chats = []
            for record in results:
                sess = dict(record['session_node'])  # Convert Node to dict
                session_id = sess.get('id')
                chat_count = sess.get('chat_count', 0) or 0
                
                # Extract all inputN/outputN pairs
                for i in range(1, int(chat_count) + 1):
                    input_val = sess.get(f'input{i}')
                    output_val = sess.get(f'output{i}')
                    intent_val = sess.get(f'intent{i}', 'general')
                    sentiment_val = sess.get(f'sentiment{i}', 'neutral')
                    timestamp_val = sess.get(f'timestamp{i}')
                    
                    if input_val and output_val:
                        all_chats.append({
                            'session_id': session_id,
                            'chat_number': i,
                            'input': input_val,
                            'output': output_val,
                            'intent': intent_val,
                            'sentiment': sentiment_val,
                            'timestamp': timestamp_val
                        })
            
            return all_chats
    except Exception as e:
        print(f"Error getting chat history: {e}")
        return []


def get_chat_history_by_session(user_id, session_id):
    """Get chats for a specific session"""
    d = get_driver()
    if not d:
        return []
    
    try:
        with d.session() as session:
            result = session.run("""
                MATCH (u:User {id: $user_id})-[:HAS_SESSION]->(s:Session {id: $session_id})
                RETURN s as session_node
            """, user_id=user_id, session_id=session_id).single()
            
            if not result:
                return []
            
            sess = dict(result['session_node'])  # Convert Node to dict
            chat_count = sess.get('chat_count', 0) or 0
            chats = []
            
            for i in range(1, int(chat_count) + 1):
                input_val = sess.get(f'input{i}')
                output_val = sess.get(f'output{i}')
                intent_val = sess.get(f'intent{i}', 'general')
                sentiment_val = sess.get(f'sentiment{i}', 'neutral')
                timestamp_val = sess.get(f'timestamp{i}')
                
                if input_val and output_val:
                    chats.append({
                        'session_id': session_id,
                        'chat_number': i,
                        'input': input_val,
                        'output': output_val,
                        'intent': intent_val,
                        'sentiment': sentiment_val,
                        'timestamp': timestamp_val
                    })
            
            return chats
    except Exception as e:
        print(f"Error getting session chat history: {e}")
        return []


# ============== CONTEXT & KNOWLEDGE ==============

def get_user_context(user_id, limit=5):
    """Get recent conversation context for a user"""
    history = get_chat_history(user_id)
    # Return last N chats as context
    return history[-limit:] if history else []


def search_knowledge(query, intent, entities):
    """Search knowledge graph for answers (placeholder for future expansion)"""
    # This can be expanded to query a knowledge base
    return None


def generate_cypher_queries(user_id, session_id, user_input, agent_output, timestamp, nlp_data, prev_chat_id=None):
    """Generate Cypher queries for visualization/logging purposes"""
    chat_id = f"{session_id}_chat_preview"
    
    queries = [
        f"// Store chat in session as input/output properties",
        f"MATCH (s:Session {{id: '{session_id}'}})",
        f"SET s.inputN = '{user_input}', s.outputN = '{agent_output}'"
    ]
    
    return queries, chat_id


# ============== GRAPH STATS & INFO ==============

def get_graph_stats():
    """Get statistics about the graph database"""
    d = get_driver()
    if not d:
        return {'error': 'Not connected'}
    
    try:
        with d.session() as session:
            # Count nodes
            user_count = session.run("MATCH (u:User) RETURN count(u) as count").single()['count']
            session_count = session.run("MATCH (s:Session) RETURN count(s) as count").single()['count']
            
            # Count total chats (sum of all chat_counts)
            chat_result = session.run("""
                MATCH (s:Session)
                WHERE s.chat_count IS NOT NULL
                RETURN sum(s.chat_count) as total
            """).single()
            total_chats = chat_result['total'] if chat_result['total'] else 0
            
            return {
                'users': user_count,
                'sessions': session_count,
                'total_chats': total_chats,
                'connected': True
            }
    except Exception as e:
        return {'error': str(e)}


def get_agent_info():
    """Get Agent (Pentagon) information"""
    d = get_driver()
    if not d:
        return None
    
    try:
        with d.session() as session:
            result = session.run("""
                MATCH (a:Agent {name: 'Pentagon'})
                RETURN a.name as name, a.creator as creator, a.members as members,
                       a.city as city, a.company as company
            """).single()
            
            if result:
                return {
                    'name': result['name'],
                    'creator': result['creator'],
                    'members': result['members'],
                    'city': result['city'],
                    'company': result['company']
                }
    except Exception as e:
        print(f"Error getting agent info: {e}")
    return None


def get_graph_schema():
    """Return the graph schema description"""
    return {
        'nodes': [
            {
                'label': 'Person',
                'description': 'Base node representing a person entity',
                'properties': ['type', 'created_at']
            },
            {
                'label': 'User',
                'description': 'User account linked to Person via IS_A relationship',
                'properties': ['id', 'username', 'name', 'email', 'password_hash', 'created_at']
            },
            {
                'label': 'Session',
                'description': 'Chat session containing all messages as properties (input1, output1, input2, output2, etc.)',
                'properties': ['id', 'started_at', 'chat_count', 'inputN', 'outputN', 'intentN', 'sentimentN', 'timestampN']
            },
            {
                'label': 'Agent',
                'description': 'The Pentagon chatbot agent',
                'properties': ['name', 'creator', 'members', 'city', 'company', 'created_at']
            }
        ],
        'relationships': [
            {'type': 'IS_A', 'from': 'User', 'to': 'Person', 'description': 'User is a type of Person'},
            {'type': 'HAS_SESSION', 'from': 'User', 'to': 'Session', 'description': 'User has chat sessions'}
        ],
        'chat_storage': 'Chats stored inside Session as: input1, output1, intent1, sentiment1, timestamp1, input2, output2, etc.'
    }


# Initialize on module load
get_driver()
init_graph_structure()
