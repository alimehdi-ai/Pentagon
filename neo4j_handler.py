"""
Neo4j Database Handler for Pentagon Chatbot

Graph Schema (3 Core Nodes):
  - Person: The human user (long-term identity)
  - Agent: The bot (Pentagon)
  - Session: One chat conversation instance (Episode - memory container)

Relationships:
  (Person)-[:CREATED]->(Agent)    # User is the bot creator
  (Person)-[:USES]->(Agent)       # User is interacting with bot
  (Person)-[:HAS_SESSION]->(Session)  # This chat belongs to this user
  (Session)-[:WITH_AGENT]->(Agent)    # This chat session is with this bot

Session stores arrays (short-term memory):
  - messages[]: All conversation messages [{role, content}]
  - sentiments[]: Sentiment score per message
  - entities[]: Extracted entities (name, place, topic, etc)
  - timestamps[]: Time of each message
"""

from neo4j import GraphDatabase
import hashlib
import uuid
from datetime import datetime, timezone
import json

# Neo4j Connection Configuration
NEO4J_URI = "bolt://127.0.0.1:7687"
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

def migrate_old_schema():
    """Migrate old User nodes to Person nodes if they exist"""
    d = get_driver()
    if not d:
        return False
    
    try:
        with d.session() as session:
            # Check if old User nodes exist
            old_users = session.run("""
                MATCH (u:User)
                WHERE NOT u:Person
                RETURN count(u) as count
            """).single()
            
            if old_users and old_users['count'] > 0:
                print(f"Migrating {old_users['count']} old User nodes to Person nodes...")
                
                # Add Person label to all User nodes
                session.run("""
                    MATCH (u:User)
                    SET u:Person
                    SET u.is_creator = CASE WHEN u.username = 'admin' THEN true ELSE false END
                """)
                
                # Migrate old HAS_SESSION relationships (User->Session to Person->Session)
                # They already work since Person now has User label too
                
                # Create USES relationships for all users to Agent
                session.run("""
                    MATCH (p:Person), (a:Agent {name: 'Pentagon'})
                    WHERE NOT (p)-[:USES]->(a)
                    CREATE (p)-[:USES]->(a)
                """)
                
                # Create CREATED relationship for admin
                session.run("""
                    MATCH (p:Person {username: 'admin'}), (a:Agent {name: 'Pentagon'})
                    WHERE NOT (p)-[:CREATED]->(a)
                    CREATE (p)-[:CREATED]->(a)
                """)
                
                # Migrate old sessions to have WITH_AGENT relationship
                session.run("""
                    MATCH (s:Session), (a:Agent {name: 'Pentagon'})
                    WHERE NOT (s)-[:WITH_AGENT]->(a)
                    CREATE (s)-[:WITH_AGENT]->(a)
                """)
                
                # Migrate old sessions: convert inputN/outputN to arrays if needed
                session.run("""
                    MATCH (s:Session)
                    WHERE s.messages IS NULL
                    SET s.messages = [], s.sentiments = [], s.entities = [], s.timestamps = []
                """)
                
                print("Migration completed!")
            
            # Clean up old base Person node if exists
            session.run("""
                MATCH (p:Person {type: 'base'})
                WHERE NOT (p)<-[:IS_A]-()
                DELETE p
            """)
            
            return True
    except Exception as e:
        print(f"Migration error (non-fatal): {e}")
        return False


def init_graph_structure():
    """Initialize base graph structure with Person and Agent nodes"""
    d = get_driver()
    if not d:
        return False
    
    try:
        with d.session() as session:
            # Create Agent node (Pentagon bot) first
            session.run("""
                MERGE (a:Agent {name: 'Pentagon'})
                ON CREATE SET 
                    a.creator = 'Pentagon Team',
                    a.members = ['Ali Mehdi', 'Zaryab', 'Muqeet', 'Naila', 'Shaman'],
                    a.city = 'Lahore',
                    a.company = 'Microsoft',
                    a.created_at = datetime()
            """)
            print("Agent node initialized (Pentagon)")
            
            # Run migration for old schema
            migrate_old_schema()
            
            # Check if admin exists (as Person or User)
            admin_exists = session.run("""
                MATCH (p)
                WHERE (p:Person OR p:User) AND p.username = 'admin'
                RETURN p
            """).single()
            
            if not admin_exists:
                admin_id = str(uuid.uuid4())
                session.run("""
                    MATCH (a:Agent {name: 'Pentagon'})
                    CREATE (p:Person {
                        id: $id,
                        username: 'admin',
                        name: 'Administrator',
                        email: 'admin@pentagon.ai',
                        password_hash: $password_hash,
                        is_creator: true,
                        created_at: datetime()
                    })
                    CREATE (p)-[:CREATED]->(a)
                    CREATE (p)-[:USES]->(a)
                """, id=admin_id, password_hash=hash_password('12345678'))
                print("Admin Person created (username: admin, password: 12345678)")
            
            print("Graph structure initialized successfully!")
            return True
    except Exception as e:
        print(f"Error initializing graph structure: {e}")
        return False


# ============== PERSON MANAGEMENT ==============

def create_user(username, name, email, password):
    """Create a new Person node with USES relationship to Agent"""
    d = get_driver()
    if not d:
        return False, "Database connection error", None
    
    try:
        with d.session() as session:
            # Check if username exists (support both Person and User labels)
            existing = session.run("""
                MATCH (p)
                WHERE (p:Person OR p:User) AND p.username = $username
                RETURN p
            """, username=username).single()
            
            if existing:
                return False, "Username already exists", None
            
            # Check if email exists (support both Person and User labels)
            email_exists = session.run("""
                MATCH (p)
                WHERE (p:Person OR p:User) AND p.email = $email
                RETURN p
            """, email=email).single()
            
            if email_exists:
                return False, "Email already registered", None
            
            # Create Person with USES relationship to Agent
            person_id = str(uuid.uuid4())
            session.run("""
                MATCH (a:Agent {name: 'Pentagon'})
                CREATE (p:Person {
                    id: $id,
                    username: $username,
                    name: $name,
                    email: $email,
                    password_hash: $password_hash,
                    is_creator: false,
                    created_at: datetime()
                })
                CREATE (p)-[:USES]->(a)
            """, id=person_id, username=username, name=name, email=email, 
                password_hash=hash_password(password))
            
            return True, "User created successfully", {
                'id': person_id,
                'username': username,
                'name': name,
                'email': email
            }
    except Exception as e:
        return False, f"Error creating user: {e}", None


def authenticate_user(username, password):
    """Authenticate Person/User by username and password (supports both labels)"""
    d = get_driver()
    if not d:
        return False, "Database connection error", None
    
    try:
        with d.session() as session:
            # Debug: print what we're searching for
            print(f"[AUTH DEBUG] Attempting login for username: '{username}'")
            password_hash = hash_password(password)
            print(f"[AUTH DEBUG] Password hash: {password_hash[:20]}...")
            
            # First check if user exists at all
            user_check = session.run("""
                MATCH (p)
                WHERE (p:Person OR p:User) AND p.username = $username
                RETURN p.username as username, p.password_hash as stored_hash
            """, username=username).single()
            
            if user_check:
                print(f"[AUTH DEBUG] Found user: {user_check['username']}")
                print(f"[AUTH DEBUG] Stored hash: {user_check['stored_hash'][:20] if user_check['stored_hash'] else 'None'}...")
                print(f"[AUTH DEBUG] Hash match: {user_check['stored_hash'] == password_hash}")
            else:
                print(f"[AUTH DEBUG] User '{username}' not found in database!")
            
            # Support both Person and User labels for backward compatibility
            result = session.run("""
                MATCH (p)
                WHERE (p:Person OR p:User) 
                  AND p.username = $username 
                  AND p.password_hash = $password_hash
                RETURN p.id as id, p.username as username, p.name as name, p.email as email
            """, username=username, password_hash=password_hash).single()
            
            if result:
                print(f"[AUTH DEBUG] Login successful for: {result['username']}")
                return True, "Login successful", {
                    'id': result['id'],
                    'username': result['username'],
                    'name': result['name'],
                    'email': result['email']
                }
            print(f"[AUTH DEBUG] Login failed - password mismatch")
            return False, "Invalid username or password", None
    except Exception as e:
        print(f"[AUTH DEBUG] Exception: {e}")
        return False, f"Authentication error: {e}", None


def save_face_encoding(user_id, face_encoding_str):
    """Save face encoding for a user"""
    d = get_driver()
    if not d:
        return False, "Database connection error"
    
    try:
        with d.session() as session:
            result = session.run("""
                MATCH (p)
                WHERE (p:Person OR p:User) AND p.id = $user_id
                SET p.face_encoding = $face_encoding
                RETURN p.id as id
            """, user_id=user_id, face_encoding=face_encoding_str).single()
            
            if result:
                return True, "Face encoding saved successfully"
            return False, "User not found"
    except Exception as e:
        return False, f"Error saving face encoding: {e}"


def get_all_face_encodings():
    """Get all users with face encodings for face recognition"""
    d = get_driver()
    if not d:
        return []
    
    try:
        with d.session() as session:
            results = session.run("""
                MATCH (p)
                WHERE (p:Person OR p:User) AND p.face_encoding IS NOT NULL
                RETURN p.id as id, p.username as username, p.name as name, 
                       p.email as email, p.face_encoding as face_encoding
            """)
            
            users = []
            for record in results:
                users.append({
                    'id': record['id'],
                    'username': record['username'],
                    'name': record['name'],
                    'email': record['email'],
                    'face_encoding': record['face_encoding']
                })
            return users
    except Exception as e:
        print(f"Error getting face encodings: {e}")
        return []


def authenticate_by_face(user_id):
    """Authenticate and return user data by ID (for face login)"""
    d = get_driver()
    if not d:
        return False, "Database connection error", None
    
    try:
        with d.session() as session:
            result = session.run("""
                MATCH (p)
                WHERE (p:Person OR p:User) AND p.id = $user_id
                RETURN p.id as id, p.username as username, p.name as name, p.email as email
            """, user_id=user_id).single()
            
            if result:
                return True, "Face login successful", {
                    'id': result['id'],
                    'username': result['username'],
                    'name': result['name'],
                    'email': result['email']
                }
            return False, "User not found", None
    except Exception as e:
        return False, f"Authentication error: {e}", None


def get_user_by_id(user_id):
    """Get Person/User information by ID (supports both labels)"""
    d = get_driver()
    if not d:
        return None
    
    try:
        with d.session() as session:
            result = session.run("""
                MATCH (p)
                WHERE (p:Person OR p:User) AND p.id = $user_id
                RETURN p.id as id, p.username as username, p.name as name, p.email as email
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


def find_or_create_person(user_id=None, email=None):
    """
    Find Person/User by user ID or email (supports both labels).
    If not found, returns None (use create_user to create new Person)
    """
    d = get_driver()
    if not d:
        return None
    
    try:
        with d.session() as session:
            if user_id:
                result = session.run("""
                    MATCH (p)
                    WHERE (p:Person OR p:User) AND p.id = $user_id
                    RETURN p.id as id, p.username as username, p.name as name, p.email as email
                """, user_id=user_id).single()
            elif email:
                result = session.run("""
                    MATCH (p)
                    WHERE (p:Person OR p:User) AND p.email = $email
                    RETURN p.id as id, p.username as username, p.name as name, p.email as email
                """, email=email).single()
            else:
                return None
            
            if result:
                return {
                    'id': result['id'],
                    'username': result['username'],
                    'name': result['name'],
                    'email': result['email']
                }
    except Exception as e:
        print(f"Error finding person: {e}")
    return None


# ============== SESSION MANAGEMENT ==============

def get_or_create_session(user_id, session_id=None):
    """
    Get existing session or create new one for user.
    Creates relationships:
      (Person)-[:HAS_SESSION]->(Session)
      (Session)-[:WITH_AGENT]->(Agent)
    """
    d = get_driver()
    if not d:
        return str(uuid.uuid4())
    
    try:
        with d.session() as session:
            # If session_id provided, verify it exists (support both Person and User)
            if session_id:
                existing = session.run("""
                    MATCH (p)-[:HAS_SESSION]->(s:Session {id: $session_id})
                    WHERE (p:Person OR p:User) AND p.id = $user_id
                    RETURN s.id as id
                """, user_id=user_id, session_id=session_id).single()
                
                if existing:
                    return session_id
            
            # Create new session with array properties and relationships
            new_session_id = str(uuid.uuid4())
            session.run("""
                MATCH (p)
                WHERE (p:Person OR p:User) AND p.id = $user_id
                MATCH (a:Agent {name: 'Pentagon'})
                CREATE (s:Session {
                    id: $session_id,
                    started_at: datetime(),
                    messages: [],
                    sentiments: [],
                    entities: [],
                    timestamps: []
                })
                CREATE (p)-[:HAS_SESSION]->(s)
                CREATE (s)-[:WITH_AGENT]->(a)
            """, user_id=user_id, session_id=new_session_id)
            
            return new_session_id
    except Exception as e:
        print(f"Error creating session: {e}")
        return str(uuid.uuid4())


def get_user_sessions(user_id):
    """Get all sessions for a Person/User (supports both labels)"""
    d = get_driver()
    if not d:
        return []
    
    try:
        with d.session() as session:
            results = session.run("""
                MATCH (p)-[:HAS_SESSION]->(s:Session)
                WHERE (p:Person OR p:User) AND p.id = $user_id
                RETURN s.id as session_id, s.started_at as started_at, 
                       CASE WHEN s.messages IS NOT NULL THEN size(s.messages) ELSE s.chat_count END as message_count
                ORDER BY s.started_at DESC
            """, user_id=user_id)
            
            sessions = []
            for record in results:
                sessions.append({
                    'session_id': record['session_id'],
                    'started_at': str(record['started_at']) if record['started_at'] else None,
                    'chat_count': record['message_count'] or 0
                })
            return sessions
    except Exception as e:
        print(f"Error getting sessions: {e}")
        return []


# ============== CHAT STORAGE (Array-based Session Memory) ==============

def store_chat(user_id, session_id, user_input, agent_output, timestamp, nlp_data, prev_chat_id=None):
    """
    Store chat in Session node by appending to arrays:
      - messages[]: {role: 'user'/'agent', content: '...'}
      - sentiments[]: sentiment score per message
      - entities[]: extracted entities
      - timestamps[]: time of each message
    """
    d = get_driver()
    if not d:
        return str(uuid.uuid4())
    
    try:
        with d.session() as session:
            # Extract sentiment
            sentiment = 0.0
            sentiment_label = "neutral"
            if nlp_data and 'sentiment' in nlp_data and nlp_data['sentiment']:
                sentiment = nlp_data['sentiment'].get('compound', 0.0)
                sentiment_label = nlp_data['sentiment'].get('sentiment', 'neutral')
            
            # Extract entities
            entities = []
            if nlp_data and 'entities' in nlp_data:
                entities = nlp_data['entities']  # List of entity dicts
            
            # Create message objects
            user_message = json.dumps({'role': 'user', 'content': user_input})
            agent_message = json.dumps({'role': 'agent', 'content': agent_output})
            
            # Create entity JSON
            entities_json = json.dumps(entities) if entities else '[]'
            
            # Append to Session arrays
            session.run("""
                MATCH (s:Session {id: $session_id})
                SET s.messages = s.messages + [$user_msg, $agent_msg],
                    s.sentiments = s.sentiments + [$sentiment],
                    s.entities = s.entities + [$entities],
                    s.timestamps = s.timestamps + [$timestamp],
                    s.last_updated = datetime()
            """, session_id=session_id, 
                user_msg=user_message, agent_msg=agent_message,
                sentiment=sentiment, entities=entities_json, timestamp=timestamp)
            
            # Return a chat ID
            result = session.run("""
                MATCH (s:Session {id: $session_id})
                RETURN size(s.timestamps) as count
            """, session_id=session_id).single()
            
            count = result['count'] if result else 1
            return f"{session_id}_chat{count}"
    except Exception as e:
        print(f"Error storing chat: {e}")
        return str(uuid.uuid4())


def get_chat_history(user_id):
    """Get all chats for a Person/User across all sessions (supports both labels and old schema)"""
    d = get_driver()
    if not d:
        return []
    
    try:
        with d.session() as session:
            results = session.run("""
                MATCH (p)-[:HAS_SESSION]->(s:Session)
                WHERE (p:Person OR p:User) AND p.id = $user_id
                RETURN s as session_node, s.id as session_id, s.messages as messages, 
                       s.sentiments as sentiments, s.entities as entities,
                       s.timestamps as timestamps, s.started_at as started_at,
                       s.chat_count as chat_count
                ORDER BY s.started_at ASC
            """, user_id=user_id)
            
            all_chats = []
            for record in results:
                session_id = record['session_id']
                messages = record['messages']
                
                # Check if using new array format or old inputN/outputN format
                if messages is not None and len(messages) > 0:
                    # New format: arrays
                    sentiments = record['sentiments'] or []
                    timestamps = record['timestamps'] or []
                    
                    chat_num = 0
                    for i in range(0, len(messages), 2):
                        chat_num += 1
                        try:
                            user_msg = json.loads(messages[i]) if i < len(messages) else {}
                            agent_msg = json.loads(messages[i+1]) if i+1 < len(messages) else {}
                        except:
                            user_msg = {'content': messages[i] if i < len(messages) else ''}
                            agent_msg = {'content': messages[i+1] if i+1 < len(messages) else ''}
                        sentiment_idx = chat_num - 1
                        
                        all_chats.append({
                            'session_id': session_id,
                            'chat_number': chat_num,
                            'input': user_msg.get('content', ''),
                            'output': agent_msg.get('content', ''),
                            'sentiment': sentiments[sentiment_idx] if sentiment_idx < len(sentiments) else 0,
                            'timestamp': timestamps[sentiment_idx] if sentiment_idx < len(timestamps) else None
                        })
                else:
                    # Old format: inputN/outputN properties
                    sess = dict(record['session_node'])
                    chat_count = record['chat_count'] or 0
                    
                    for i in range(1, int(chat_count) + 1):
                        input_val = sess.get(f'input{i}')
                        output_val = sess.get(f'output{i}')
                        sentiment_val = sess.get(f'sentiment{i}', 'neutral')
                        timestamp_val = sess.get(f'timestamp{i}')
                        
                        if input_val and output_val:
                            all_chats.append({
                                'session_id': session_id,
                                'chat_number': i,
                                'input': input_val,
                                'output': output_val,
                                'sentiment': sentiment_val,
                                'timestamp': timestamp_val
                            })
            
            return all_chats
    except Exception as e:
        print(f"Error getting chat history: {e}")
        return []


def get_chat_history_by_session(user_id, session_id):
    """Get chats for a specific session (supports both labels and old schema)"""
    d = get_driver()
    if not d:
        return []
    
    try:
        with d.session() as session:
            result = session.run("""
                MATCH (p)-[:HAS_SESSION]->(s:Session {id: $session_id})
                WHERE (p:Person OR p:User) AND p.id = $user_id
                RETURN s as session_node, s.messages as messages, s.sentiments as sentiments,
                       s.entities as entities, s.timestamps as timestamps, s.chat_count as chat_count
            """, user_id=user_id, session_id=session_id).single()
            
            if not result:
                return []
            
            messages = result['messages']
            chats = []
            
            # Check if using new array format or old inputN/outputN format
            if messages is not None and len(messages) > 0:
                # New format
                sentiments = result['sentiments'] or []
                entities = result['entities'] or []
                timestamps = result['timestamps'] or []
                
                chat_num = 0
                for i in range(0, len(messages), 2):
                    chat_num += 1
                    try:
                        user_msg = json.loads(messages[i]) if i < len(messages) else {}
                        agent_msg = json.loads(messages[i+1]) if i+1 < len(messages) else {}
                    except:
                        user_msg = {'content': messages[i] if i < len(messages) else ''}
                        agent_msg = {'content': messages[i+1] if i+1 < len(messages) else ''}
                    sentiment_idx = chat_num - 1
                    
                    try:
                        ent_list = json.loads(entities[sentiment_idx]) if sentiment_idx < len(entities) else []
                    except:
                        ent_list = []
                    
                    chats.append({
                        'session_id': session_id,
                        'chat_number': chat_num,
                        'input': user_msg.get('content', ''),
                        'output': agent_msg.get('content', ''),
                        'sentiment': sentiments[sentiment_idx] if sentiment_idx < len(sentiments) else 0,
                        'entities': ent_list,
                        'timestamp': timestamps[sentiment_idx] if sentiment_idx < len(timestamps) else None
                    })
            else:
                # Old format: inputN/outputN properties
                sess = dict(result['session_node'])
                chat_count = result['chat_count'] or 0
                
                for i in range(1, int(chat_count) + 1):
                    input_val = sess.get(f'input{i}')
                    output_val = sess.get(f'output{i}')
                    sentiment_val = sess.get(f'sentiment{i}', 'neutral')
                    timestamp_val = sess.get(f'timestamp{i}')
                    
                    if input_val and output_val:
                        chats.append({
                            'session_id': session_id,
                            'chat_number': i,
                            'input': input_val,
                            'output': output_val,
                            'sentiment': sentiment_val,
                            'entities': [],
                            'timestamp': timestamp_val
                        })
            
            return chats
    except Exception as e:
        print(f"Error getting session chat history: {e}")
        return []


# ============== SESSION MEMORY QUERIES ==============

def get_session_memory(session_id):
    """
    Get the full memory container for a session.
    Returns: messages[], sentiments[], entities[], timestamps[]
    """
    d = get_driver()
    if not d:
        return None
    
    try:
        with d.session() as session:
            result = session.run("""
                MATCH (s:Session {id: $session_id})
                RETURN s.messages as messages, s.sentiments as sentiments,
                       s.entities as entities, s.timestamps as timestamps
            """, session_id=session_id).single()
            
            if result:
                return {
                    'messages': result['messages'] or [],
                    'sentiments': result['sentiments'] or [],
                    'entities': result['entities'] or [],
                    'timestamps': result['timestamps'] or []
                }
    except Exception as e:
        print(f"Error getting session memory: {e}")
    return None


def query_session_memory(session_id, query_type):
    """
    Query session memory for specific information.
    
    Query types:
      - 'user_name': Find PERSON entity in entities[]
      - 'last_message': Last item in messages[]
      - 'first_message': First item in messages[]
      - 'last_sentiment': Last item in sentiments[]
      - 'last_entity': Last item in entities[]
      - 'average_sentiment': Average of sentiments[]
      - 'all_entities': All entities mentioned
    """
    memory = get_session_memory(session_id)
    if not memory:
        return None
    
    messages = memory['messages']
    sentiments = memory['sentiments']
    entities = memory['entities']
    
    try:
        if query_type == 'user_name':
            # Search for PERSON entity in entities
            for entity_json in reversed(entities):
                entity_list = json.loads(entity_json) if isinstance(entity_json, str) else entity_json
                for ent in entity_list:
                    if isinstance(ent, dict) and ent.get('label') == 'PERSON':
                        return ent.get('text')
            return None
        
        elif query_type == 'last_message':
            if messages:
                last_msg = json.loads(messages[-1]) if isinstance(messages[-1], str) else messages[-1]
                return last_msg.get('content')
            return None
        
        elif query_type == 'first_message':
            if messages:
                first_msg = json.loads(messages[0]) if isinstance(messages[0], str) else messages[0]
                return first_msg.get('content')
            return None
        
        elif query_type == 'last_user_message':
            # Find last user message
            for msg_json in reversed(messages):
                msg = json.loads(msg_json) if isinstance(msg_json, str) else msg_json
                if msg.get('role') == 'user':
                    return msg.get('content')
            return None
        
        elif query_type == 'last_sentiment':
            if sentiments:
                return sentiments[-1]
            return None
        
        elif query_type == 'last_entity':
            for entity_json in reversed(entities):
                entity_list = json.loads(entity_json) if isinstance(entity_json, str) else entity_json
                if entity_list:
                    return entity_list[-1]
            return None
        
        elif query_type == 'average_sentiment':
            if sentiments:
                return sum(sentiments) / len(sentiments)
            return 0.0
        
        elif query_type == 'all_entities':
            all_ents = []
            for entity_json in entities:
                entity_list = json.loads(entity_json) if isinstance(entity_json, str) else entity_json
                all_ents.extend(entity_list)
            return all_ents
        
        elif query_type == 'mood_summary':
            if sentiments:
                avg = sum(sentiments) / len(sentiments)
                if avg > 0.3:
                    return 'positive'
                elif avg < -0.3:
                    return 'negative'
                else:
                    return 'neutral'
            return 'neutral'
        
    except Exception as e:
        print(f"Error querying session memory: {e}")
    
    return None


def get_person_from_session(session_id):
    """Get the Person/User who owns this session (supports both labels)"""
    d = get_driver()
    if not d:
        return None
    
    try:
        with d.session() as session:
            result = session.run("""
                MATCH (p)-[:HAS_SESSION]->(s:Session {id: $session_id})
                WHERE p:Person OR p:User
                RETURN p.id as id, p.username as username, p.name as name, p.email as email
            """, session_id=session_id).single()
            
            if result:
                return {
                    'id': result['id'],
                    'username': result['username'],
                    'name': result['name'],
                    'email': result['email']
                }
    except Exception as e:
        print(f"Error getting person from session: {e}")
    return None


# ============== CONTEXT & KNOWLEDGE ==============

def get_user_context(user_id, limit=5):
    """Get recent conversation context for a Person"""
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
        f"// Store chat in session arrays (messages, sentiments, entities, timestamps)",
        f"MATCH (s:Session {{id: '{session_id}'}})",
        f"SET s.messages = s.messages + [user_msg, agent_msg],",
        f"    s.sentiments = s.sentiments + [sentiment],",
        f"    s.entities = s.entities + [entities],",
        f"    s.timestamps = s.timestamps + [timestamp]"
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
            person_count = session.run("MATCH (p:Person) RETURN count(p) as count").single()['count']
            session_count = session.run("MATCH (s:Session) RETURN count(s) as count").single()['count']
            agent_count = session.run("MATCH (a:Agent) RETURN count(a) as count").single()['count']
            
            # Count total messages
            msg_result = session.run("""
                MATCH (s:Session)
                RETURN sum(size(s.messages)) as total
            """).single()
            total_messages = msg_result['total'] if msg_result['total'] else 0
            
            # Count relationships
            rel_result = session.run("""
                MATCH ()-[r]->()
                RETURN count(r) as count
            """).single()
            relationship_count = rel_result['count'] if rel_result else 0
            
            return {
                'persons': person_count,
                'sessions': session_count,
                'agents': agent_count,
                'total_messages': total_messages,
                'relationships': relationship_count,
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
    """Return the graph schema description (3 Core Nodes)"""
    return {
        'nodes': [
            {
                'label': 'Person',
                'description': 'The human user (long-term identity)',
                'properties': ['id', 'username', 'name', 'email', 'password_hash', 'is_creator', 'created_at']
            },
            {
                'label': 'Agent',
                'description': 'The bot (Pentagon)',
                'properties': ['name', 'creator', 'members', 'city', 'company', 'created_at']
            },
            {
                'label': 'Session',
                'description': 'One chat conversation instance (Episode - memory container)',
                'properties': ['id', 'started_at', 'last_updated', 'messages[]', 'sentiments[]', 'entities[]', 'timestamps[]']
            }
        ],
        'relationships': [
            {'type': 'CREATED', 'from': 'Person', 'to': 'Agent', 'description': 'User is the bot creator'},
            {'type': 'USES', 'from': 'Person', 'to': 'Agent', 'description': 'User is interacting with bot'},
            {'type': 'HAS_SESSION', 'from': 'Person', 'to': 'Session', 'description': 'This chat belongs to this user'},
            {'type': 'WITH_AGENT', 'from': 'Session', 'to': 'Agent', 'description': 'This chat session is with this bot'}
        ],
        'session_memory': {
            'messages': 'All conversation messages [{role, content}]',
            'sentiments': 'Sentiment score per message',
            'entities': 'Extracted entities (name, place, topic, etc)',
            'timestamps': 'Time of each message'
        },
        'memory_queries': {
            'user_name': 'Find PERSON entity inside entities[]',
            'last_message': 'Last item in messages[]',
            'last_sentiment': 'Last item in sentiments[]',
            'last_entity': 'Last item in entities[]',
            'first_message': 'First item in messages[]',
            'average_sentiment': 'Average of sentiments[]',
            'mood_summary': 'Overall mood based on average sentiment'
        }
    }


# Initialize on module load
get_driver()
init_graph_structure()
