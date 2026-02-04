"""
Neo4j Database Handler for Pentagon Chatbot

Graph Schema (3 Core Nodes):
  - Human: The human user (long-term identity)
  - Bot: The AI assistant (Synapse)
  - Conversation: One chat conversation instance (Episode - memory container)

Relationships:
  (Human)-[:BUILT]->(Bot)           # User is the bot creator
  (Human)-[:INTERACTS]->(Bot)       # User is interacting with bot
  (Human)-[:OWNS_CONVERSATION]->(Conversation)  # This chat belongs to this user
  (Conversation)-[:HOSTED_BY]->(Bot)    # This chat session is with this bot

Conversation stores indexed properties (short-term memory):
  - message1, message2, ...: Individual messages
  - intent1, intent2, ...: Intent per message
  - sentiment1, sentiment2, ...: Sentiment per message
  - entity1, entity2, ...: Extracted entities per message
  - timestamp1, timestamp2, ...: Time of each message
  - msg_count: Total message count
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
    """Migrate old User/Person/Agent/Session nodes to Human/Bot/Conversation nodes"""
    d = get_driver()
    if not d:
        return False
    
    try:
        with d.session() as session:
            # Migrate Person nodes to Human nodes
            old_persons = session.run("""
                MATCH (p:Person)
                WHERE NOT p:Human
                RETURN count(p) as count
            """).single()
            
            if old_persons and old_persons['count'] > 0:
                print(f"Migrating {old_persons['count']} Person nodes to Human nodes...")
                session.run("""
                    MATCH (p:Person)
                    SET p:Human
                    SET p.is_creator = CASE WHEN p.username = 'admin' THEN true ELSE false END
                """)
            
            # Migrate User nodes to Human nodes
            old_users = session.run("""
                MATCH (u:User)
                WHERE NOT u:Human
                RETURN count(u) as count
            """).single()
            
            if old_users and old_users['count'] > 0:
                print(f"Migrating {old_users['count']} User nodes to Human nodes...")
                session.run("""
                    MATCH (u:User)
                    SET u:Human
                    SET u.is_creator = CASE WHEN u.username = 'admin' THEN true ELSE false END
                """)
            
            # Migrate Agent nodes to Bot nodes
            old_agents = session.run("""
                MATCH (a:Agent)
                WHERE NOT a:Bot
                RETURN count(a) as count
            """).single()
            
            if old_agents and old_agents['count'] > 0:
                print(f"Migrating {old_agents['count']} Agent nodes to Bot nodes...")
                session.run("""
                    MATCH (a:Agent)
                    SET a:Bot
                """)
            
            # Migrate Session nodes to Conversation nodes
            old_sessions = session.run("""
                MATCH (s:Session)
                WHERE NOT s:Conversation
                RETURN count(s) as count
            """).single()
            
            if old_sessions and old_sessions['count'] > 0:
                print(f"Migrating {old_sessions['count']} Session nodes to Conversation nodes...")
                session.run("""
                    MATCH (s:Session)
                    SET s:Conversation
                """)
            
            # Create INTERACTS relationships for all humans to Bot
            session.run("""
                MATCH (h:Human), (b:Bot {name: 'Synapse'})
                WHERE NOT (h)-[:INTERACTS]->(b)
                CREATE (h)-[:INTERACTS]->(b)
            """)
            
            # Create BUILT relationship for admin
            session.run("""
                MATCH (h:Human {username: 'admin'}), (b:Bot {name: 'Synapse'})
                WHERE NOT (h)-[:BUILT]->(b)
                CREATE (h)-[:BUILT]->(b)
            """)
            
            # Migrate old conversations to have HOSTED_BY relationship
            session.run("""
                MATCH (c:Conversation), (b:Bot {name: 'Synapse'})
                WHERE NOT (c)-[:HOSTED_BY]->(b)
                CREATE (c)-[:HOSTED_BY]->(b)
            """)
            
            # Migrate OWNS_CONVERSATION relationships
            session.run("""
                MATCH (h:Human)-[r:HAS_SESSION]->(c:Conversation)
                WHERE NOT (h)-[:OWNS_CONVERSATION]->(c)
                CREATE (h)-[:OWNS_CONVERSATION]->(c)
            """)
            
            print("Migration completed!")
            
            # Clean up old base nodes if exists
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
    """Initialize base graph structure with Human and Bot nodes"""
    d = get_driver()
    if not d:
        return False
    
    try:
        with d.session() as session:
            # Create Bot node (Synapse) first
            session.run("""
                MERGE (b:Bot {name: 'Synapse'})
                ON CREATE SET 
                    b.creator = 'Group A1',
                    b.members = ['Hussain Haider (S2024376005)', 'Nevera (S2024376014)', 'Aeliya (F2023376042)'],
                    b.city = 'Lahore',
                    b.company = 'Microsoft',
                    b.created_at = datetime()
            """)
            print("Bot node initialized (Synapse)")
            
            # Run migration for old schema
            migrate_old_schema()
            
            # Check if admin exists (as Human, Person or User)
            admin_exists = session.run("""
                MATCH (h)
                WHERE (h:Human OR h:Person OR h:User) AND h.username = 'admin'
                RETURN h
            """).single()
            
            if not admin_exists:
                admin_id = str(uuid.uuid4())
                session.run("""
                    MATCH (b:Bot {name: 'Synapse'})
                    CREATE (h:Human {
                        id: $id,
                        username: 'admin',
                        name: 'Administrator',
                        email: 'admin@synapse.ai',
                        password_hash: $password_hash,
                        is_creator: true,
                        created_at: datetime()
                    })
                    CREATE (h)-[:BUILT]->(b)
                    CREATE (h)-[:INTERACTS]->(b)
                """, id=admin_id, password_hash=hash_password('12345678'))
                print("Admin Human created (username: admin, password: 12345678)")
            
            print("Graph structure initialized successfully!")
            return True
    except Exception as e:
        print(f"Error initializing graph structure: {e}")
        return False


# ============== PERSON MANAGEMENT ==============

def create_user(username, name, email, password):
    """Create a new Human node with INTERACTS relationship to Bot"""
    d = get_driver()
    if not d:
        return False, "Database connection error", None
    
    try:
        with d.session() as session:
            # Check if username exists (support Human, Person and User labels)
            existing = session.run("""
                MATCH (h)
                WHERE (h:Human OR h:Person OR h:User) AND h.username = $username
                RETURN h
            """, username=username).single()
            
            if existing:
                return False, "Username already exists", None
            
            # Check if email exists (support Human, Person and User labels)
            email_exists = session.run("""
                MATCH (h)
                WHERE (h:Human OR h:Person OR h:User) AND h.email = $email
                RETURN h
            """, email=email).single()
            
            if email_exists:
                return False, "Email already registered", None
            
            # Create Human with INTERACTS relationship to Bot
            human_id = str(uuid.uuid4())
            session.run("""
                MATCH (b:Bot {name: 'Synapse'})
                CREATE (h:Human {
                    id: $id,
                    username: $username,
                    name: $name,
                    email: $email,
                    password_hash: $password_hash,
                    is_creator: false,
                    created_at: datetime()
                })
                CREATE (h)-[:INTERACTS]->(b)
            """, id=human_id, username=username, name=name, email=email, 
                password_hash=hash_password(password))
            
            return True, "User created successfully", {
                'id': human_id,
                'username': username,
                'name': name,
                'email': email
            }
    except Exception as e:
        return False, f"Error creating user: {e}", None


def authenticate_user(username, password):
    """Authenticate Human/Person/User by username and password (supports all labels)"""
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
                MATCH (h)
                WHERE (h:Human OR h:Person OR h:User) AND h.username = $username
                RETURN h.username as username, h.password_hash as stored_hash
            """, username=username).single()
            
            if user_check:
                print(f"[AUTH DEBUG] Found user: {user_check['username']}")
                print(f"[AUTH DEBUG] Stored hash: {user_check['stored_hash'][:20] if user_check['stored_hash'] else 'None'}...")
                print(f"[AUTH DEBUG] Hash match: {user_check['stored_hash'] == password_hash}")
            else:
                print(f"[AUTH DEBUG] User '{username}' not found in database!")
            
            # Support Human, Person and User labels for backward compatibility
            result = session.run("""
                MATCH (h)
                WHERE (h:Human OR h:Person OR h:User) 
                  AND h.username = $username 
                  AND h.password_hash = $password_hash
                RETURN h.id as id, h.username as username, h.name as name, h.email as email
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


def get_user_by_id(user_id):
    """Get Human/Person/User information by ID (supports all labels)"""
    d = get_driver()
    if not d:
        return None
    
    try:
        with d.session() as session:
            result = session.run("""
                MATCH (h)
                WHERE (h:Human OR h:Person OR h:User) AND h.id = $user_id
                RETURN h.id as id, h.username as username, h.name as name, h.email as email
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
    Find Human/Person/User by user ID or email (supports all labels).
    If not found, returns None (use create_user to create new Human)
    """
    d = get_driver()
    if not d:
        return None
    
    try:
        with d.session() as session:
            if user_id:
                result = session.run("""
                    MATCH (h)
                    WHERE (h:Human OR h:Person OR h:User) AND h.id = $user_id
                    RETURN h.id as id, h.username as username, h.name as name, h.email as email
                """, user_id=user_id).single()
            elif email:
                result = session.run("""
                    MATCH (h)
                    WHERE (h:Human OR h:Person OR h:User) AND h.email = $email
                    RETURN h.id as id, h.username as username, h.name as name, h.email as email
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


# ============== CONVERSATION MANAGEMENT ==============

def get_or_create_session(user_id, session_id=None):
    """
    Get existing conversation or create new one for user.
    Creates relationships:
      (Human)-[:OWNS_CONVERSATION]->(Conversation)
      (Conversation)-[:HOSTED_BY]->(Bot)
    """
    d = get_driver()
    if not d:
        return str(uuid.uuid4())
    
    try:
        with d.session() as session:
            # If session_id provided, verify it exists (support Human, Person and User)
            if session_id:
                existing = session.run("""
                    MATCH (h)-[:OWNS_CONVERSATION|HAS_SESSION]->(c)
                    WHERE (h:Human OR h:Person OR h:User) AND h.id = $user_id
                      AND (c:Conversation OR c:Session) AND c.id = $session_id
                    RETURN c.id as id
                """, user_id=user_id, session_id=session_id).single()
                
                if existing:
                    return session_id
            
            # Create new Conversation with indexed properties
            new_session_id = str(uuid.uuid4())
            session.run("""
                MATCH (h)
                WHERE (h:Human OR h:Person OR h:User) AND h.id = $user_id
                MATCH (b:Bot {name: 'Synapse'})
                CREATE (c:Conversation {
                    id: $session_id,
                    started_at: datetime(),
                    msg_count: 0
                })
                CREATE (h)-[:OWNS_CONVERSATION]->(c)
                CREATE (c)-[:HOSTED_BY]->(b)
            """, user_id=user_id, session_id=new_session_id)
            
            return new_session_id
    except Exception as e:
        print(f"Error creating conversation: {e}")
        return str(uuid.uuid4())


def get_user_sessions(user_id):
    """Get all conversations for a Human/Person/User (supports all labels)"""
    d = get_driver()
    if not d:
        return []
    
    try:
        with d.session() as session:
            results = session.run("""
                MATCH (h)-[:OWNS_CONVERSATION|HAS_SESSION]->(c)
                WHERE (h:Human OR h:Person OR h:User) AND h.id = $user_id
                  AND (c:Conversation OR c:Session)
                RETURN c.id as session_id, c.started_at as started_at, 
                       COALESCE(c.msg_count, 0) as message_count
                ORDER BY c.started_at DESC
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


# ============== CHAT STORAGE (Indexed Conversation Memory) ==============

def store_chat(user_id, session_id, user_input, agent_output, timestamp, nlp_data, prev_chat_id=None):
    """
    Store chat in Conversation node using indexed properties:
      - message1, message2, ...: Individual messages (alternating user/bot)
      - intent1, intent2, ...: Intent per user message
      - sentiment1, sentiment2, ...: Sentiment per user message  
      - entity1, entity2, ...: Extracted entities per user message
      - timestamp1, timestamp2, ...: Time of each exchange
      - msg_count: Total message count
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
                sentiment = nlp_data['sentiment'].get('scores', {}).get('compound', 0.0)
                sentiment_label = nlp_data['sentiment'].get('sentiment', 'neutral')
            
            # Extract intent
            intent = 'general'
            if nlp_data and 'intent' in nlp_data:
                intent = nlp_data['intent'][0] if isinstance(nlp_data['intent'], list) and len(nlp_data['intent']) > 0 else str(nlp_data['intent'])
            
            # Extract entities
            entities = []
            if nlp_data and 'entities' in nlp_data:
                entities = nlp_data['entities']
            entities_json = json.dumps(entities) if entities else '[]'
            
            # Get current message count and increment
            count_result = session.run("""
                MATCH (c)
                WHERE (c:Conversation OR c:Session) AND c.id = $session_id
                RETURN COALESCE(c.msg_count, 0) as count
            """, session_id=session_id).single()
            
            current_count = count_result['count'] if count_result else 0
            new_count = current_count + 1
            
            # Store using indexed properties: message1, intent1, sentiment1, etc.
            session.run(f"""
                MATCH (c)
                WHERE (c:Conversation OR c:Session) AND c.id = $session_id
                SET c.message{new_count}_user = $user_input,
                    c.message{new_count}_bot = $agent_output,
                    c.intent{new_count} = $intent,
                    c.sentiment{new_count} = $sentiment,
                    c.sentiment{new_count}_label = $sentiment_label,
                    c.entity{new_count} = $entities,
                    c.timestamp{new_count} = $timestamp,
                    c.msg_count = $new_count,
                    c.last_updated = datetime()
            """, session_id=session_id, 
                user_input=user_input, agent_output=agent_output,
                intent=intent, sentiment=sentiment, sentiment_label=sentiment_label,
                entities=entities_json, timestamp=timestamp, new_count=new_count)
            
            return f"{session_id}_msg{new_count}"
    except Exception as e:
        print(f"Error storing chat: {e}")
        return str(uuid.uuid4())


def get_chat_history(user_id):
    """Get all chats for a Human/Person/User across all conversations (supports all labels and formats)"""
    d = get_driver()
    if not d:
        return []
    
    try:
        with d.session() as session:
            results = session.run("""
                MATCH (h)-[:OWNS_CONVERSATION|HAS_SESSION]->(c)
                WHERE (h:Human OR h:Person OR h:User) AND h.id = $user_id
                  AND (c:Conversation OR c:Session)
                RETURN c as conv_node, c.id as session_id, c.msg_count as msg_count,
                       c.started_at as started_at
                ORDER BY c.started_at ASC
            """, user_id=user_id)
            
            all_chats = []
            for record in results:
                session_id = record['session_id']
                conv = dict(record['conv_node'])
                msg_count = record['msg_count'] or conv.get('chat_count', 0) or 0
                
                # Read indexed properties: message1_user, message1_bot, intent1, etc.
                for i in range(1, int(msg_count) + 1):
                    user_msg = conv.get(f'message{i}_user') or conv.get(f'input{i}', '')
                    bot_msg = conv.get(f'message{i}_bot') or conv.get(f'output{i}', '')
                    intent = conv.get(f'intent{i}', 'general')
                    sentiment = conv.get(f'sentiment{i}', 0)
                    sentiment_label = conv.get(f'sentiment{i}_label', 'neutral')
                    timestamp = conv.get(f'timestamp{i}')
                    
                    if user_msg or bot_msg:
                        all_chats.append({
                            'session_id': session_id,
                            'chat_number': i,
                            'input': user_msg,
                            'output': bot_msg,
                            'intent': intent,
                            'sentiment': sentiment,
                            'sentiment_label': sentiment_label,
                            'timestamp': timestamp
                        })
            
            return all_chats
    except Exception as e:
        print(f"Error getting chat history: {e}")
        return []


def get_chat_history_by_session(user_id, session_id):
    """Get chats for a specific conversation (supports all labels and formats)"""
    d = get_driver()
    if not d:
        return []
    
    try:
        with d.session() as session:
            result = session.run("""
                MATCH (h)-[:OWNS_CONVERSATION|HAS_SESSION]->(c)
                WHERE (h:Human OR h:Person OR h:User) AND h.id = $user_id
                  AND (c:Conversation OR c:Session) AND c.id = $session_id
                RETURN c as conv_node, c.msg_count as msg_count
            """, user_id=user_id, session_id=session_id).single()
            
            if not result:
                return []
            
            conv = dict(result['conv_node'])
            msg_count = result['msg_count'] or conv.get('chat_count', 0) or 0
            chats = []
            
            # Read indexed properties
            for i in range(1, int(msg_count) + 1):
                user_msg = conv.get(f'message{i}_user') or conv.get(f'input{i}', '')
                bot_msg = conv.get(f'message{i}_bot') or conv.get(f'output{i}', '')
                intent = conv.get(f'intent{i}', 'general')
                sentiment = conv.get(f'sentiment{i}', 0)
                sentiment_label = conv.get(f'sentiment{i}_label', 'neutral')
                entities_json = conv.get(f'entity{i}', '[]')
                timestamp = conv.get(f'timestamp{i}')
                
                try:
                    entities = json.loads(entities_json) if entities_json else []
                except:
                    entities = []
                
                if user_msg or bot_msg:
                    chats.append({
                        'session_id': session_id,
                        'chat_number': i,
                        'input': user_msg,
                        'output': bot_msg,
                        'intent': intent,
                        'sentiment': sentiment,
                        'sentiment_label': sentiment_label,
                        'entities': entities,
                        'timestamp': timestamp
                    })
            
            return chats
    except Exception as e:
        print(f"Error getting session chat history: {e}")
        return []


# ============== CONVERSATION MEMORY QUERIES ==============

def get_session_memory(session_id):
    """
    Get the full memory container for a conversation using indexed properties.
    Returns dict with all messageN_user, messageN_bot, intentN, etc.
    """
    d = get_driver()
    if not d:
        return None
    
    try:
        with d.session() as session:
            result = session.run("""
                MATCH (c)
                WHERE (c:Conversation OR c:Session) AND c.id = $session_id
                RETURN c as conv_node, c.msg_count as msg_count
            """, session_id=session_id).single()
            
            if result:
                conv = dict(result['conv_node'])
                msg_count = result['msg_count'] or 0
                
                messages = []
                sentiments = []
                intents = []
                entities = []
                timestamps = []
                
                for i in range(1, int(msg_count) + 1):
                    messages.append({
                        'user': conv.get(f'message{i}_user', ''),
                        'bot': conv.get(f'message{i}_bot', '')
                    })
                    sentiments.append(conv.get(f'sentiment{i}', 0))
                    intents.append(conv.get(f'intent{i}', 'general'))
                    entities.append(conv.get(f'entity{i}', '[]'))
                    timestamps.append(conv.get(f'timestamp{i}'))
                
                return {
                    'messages': messages,
                    'sentiments': sentiments,
                    'intents': intents,
                    'entities': entities,
                    'timestamps': timestamps,
                    'msg_count': msg_count
                }
    except Exception as e:
        print(f"Error getting session memory: {e}")
    return None


def query_session_memory(session_id, query_type):
    """
    Query conversation memory for specific information.
    
    Query types:
      - 'user_name': Find PERSON entity in entities
      - 'last_message': Last user/bot message pair
      - 'first_message': First user/bot message pair
      - 'last_sentiment': Last sentiment value
      - 'last_intent': Last detected intent
      - 'last_entity': Last entity list
      - 'average_sentiment': Average of all sentiments
      - 'all_entities': All entities mentioned
      - 'mood_summary': Overall mood based on average sentiment
    """
    memory = get_session_memory(session_id)
    if not memory:
        return None
    
    messages = memory['messages']
    sentiments = memory['sentiments']
    intents = memory['intents']
    entities = memory['entities']
    
    try:
        if query_type == 'user_name':
            # Search for PERSON entity in entities
            for entity_json in reversed(entities):
                try:
                    entity_list = json.loads(entity_json) if isinstance(entity_json, str) else entity_json
                    for ent in entity_list:
                        if isinstance(ent, dict) and ent.get('type') == 'PERSON':
                            return ent.get('name')
                except:
                    pass
            return None
        
        elif query_type == 'last_message':
            if messages:
                return messages[-1]
            return None
        
        elif query_type == 'first_message':
            if messages:
                return messages[0]
            return None
        
        elif query_type == 'last_user_message':
            if messages:
                return messages[-1].get('user', '')
            return None
        
        elif query_type == 'last_bot_message':
            if messages:
                return messages[-1].get('bot', '')
            return None
        
        elif query_type == 'last_sentiment':
            if sentiments:
                return sentiments[-1]
            return None
        
        elif query_type == 'last_intent':
            if intents:
                return intents[-1]
            return None
        
        elif query_type == 'last_entity':
            for entity_json in reversed(entities):
                try:
                    entity_list = json.loads(entity_json) if isinstance(entity_json, str) else entity_json
                    if entity_list:
                        return entity_list[-1]
                except:
                    pass
            return None
        
        elif query_type == 'average_sentiment':
            if sentiments:
                numeric_sentiments = [s for s in sentiments if isinstance(s, (int, float))]
                if numeric_sentiments:
                    return sum(numeric_sentiments) / len(numeric_sentiments)
            return 0.0
        
        elif query_type == 'all_entities':
            all_ents = []
            for entity_json in entities:
                try:
                    entity_list = json.loads(entity_json) if isinstance(entity_json, str) else entity_json
                    all_ents.extend(entity_list)
                except:
                    pass
            return all_ents
        
        elif query_type == 'mood_summary':
            if sentiments:
                numeric_sentiments = [s for s in sentiments if isinstance(s, (int, float))]
                if numeric_sentiments:
                    avg = sum(numeric_sentiments) / len(numeric_sentiments)
                    if avg > 0.3:
                        return 'positive'
                    elif avg < -0.3:
                        return 'negative'
            return 'neutral'
        
    except Exception as e:
        print(f"Error querying session memory: {e}")
    
    return None


def get_person_from_session(session_id):
    """Get the Human/Person/User who owns this conversation (supports all labels)"""
    d = get_driver()
    if not d:
        return None
    
    try:
        with d.session() as session:
            result = session.run("""
                MATCH (h)-[:OWNS_CONVERSATION|HAS_SESSION]->(c)
                WHERE (h:Human OR h:Person OR h:User)
                  AND (c:Conversation OR c:Session) AND c.id = $session_id
                RETURN h.id as id, h.username as username, h.name as name, h.email as email
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
    chat_id = f"{session_id}_msg_preview"
    
    # Get intent
    intent = 'general'
    if nlp_data and 'intent' in nlp_data:
        intent = nlp_data['intent'][0] if isinstance(nlp_data['intent'], list) and len(nlp_data['intent']) > 0 else str(nlp_data['intent'])
    
    queries = [
        f"// Store chat in Conversation using indexed properties (message1, intent1, etc.)",
        f"MATCH (c:Conversation {{id: '{session_id}'}})",
        f"SET c.messageN_user = '{user_input[:50]}...',",
        f"    c.messageN_bot = '{agent_output[:50]}...',",
        f"    c.intentN = '{intent}',",
        f"    c.sentimentN = sentiment_value,",
        f"    c.entityN = entities_json,",
        f"    c.timestampN = '{timestamp}'",
        f"    c.msg_count = N"
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
            # Count nodes (support both old and new labels)
            human_count = session.run("MATCH (h) WHERE h:Human OR h:Person OR h:User RETURN count(h) as count").single()['count']
            conv_count = session.run("MATCH (c) WHERE c:Conversation OR c:Session RETURN count(c) as count").single()['count']
            bot_count = session.run("MATCH (b) WHERE b:Bot OR b:Agent RETURN count(b) as count").single()['count']
            
            # Count total messages by summing msg_count
            msg_result = session.run("""
                MATCH (c)
                WHERE c:Conversation OR c:Session
                RETURN sum(COALESCE(c.msg_count, 0)) as total
            """).single()
            total_messages = msg_result['total'] if msg_result['total'] else 0
            
            # Count relationships
            rel_result = session.run("""
                MATCH ()-[r]->()
                RETURN count(r) as count
            """).single()
            relationship_count = rel_result['count'] if rel_result else 0
            
            return {
                'humans': human_count,
                'conversations': conv_count,
                'bots': bot_count,
                'total_messages': total_messages,
                'relationships': relationship_count,
                'connected': True
            }
    except Exception as e:
        return {'error': str(e)}


def get_agent_info():
    """Get Bot (Synapse) information"""
    d = get_driver()
    if not d:
        return None
    
    try:
        with d.session() as session:
            result = session.run("""
                MATCH (b)
                WHERE (b:Bot OR b:Agent) AND b.name = 'Synapse'
                RETURN b.name as name, b.creator as creator, b.members as members,
                       b.city as city, b.company as company
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
        print(f"Error getting bot info: {e}")
    return None


def get_graph_schema():
    """Return the graph schema description (3 Core Nodes with new names)"""
    return {
        'nodes': [
            {
                'label': 'Human',
                'description': 'The human user (long-term identity)',
                'properties': ['id', 'username', 'name', 'email', 'password_hash', 'is_creator', 'created_at']
            },
            {
                'label': 'Bot',
                'description': 'The AI assistant (Synapse)',
                'properties': ['name', 'creator', 'members', 'city', 'company', 'created_at']
            },
            {
                'label': 'Conversation',
                'description': 'One chat conversation instance (Episode - memory container)',
                'properties': ['id', 'started_at', 'last_updated', 'msg_count', 'messageN_user', 'messageN_bot', 'intentN', 'sentimentN', 'entityN', 'timestampN']
            }
        ],
        'relationships': [
            {'type': 'BUILT', 'from': 'Human', 'to': 'Bot', 'description': 'User is the bot creator'},
            {'type': 'INTERACTS', 'from': 'Human', 'to': 'Bot', 'description': 'User is interacting with bot'},
            {'type': 'OWNS_CONVERSATION', 'from': 'Human', 'to': 'Conversation', 'description': 'This chat belongs to this user'},
            {'type': 'HOSTED_BY', 'from': 'Conversation', 'to': 'Bot', 'description': 'This conversation is with this bot'}
        ],
        'conversation_memory': {
            'messageN_user': 'User message N (message1_user, message2_user, ...)',
            'messageN_bot': 'Bot response N (message1_bot, message2_bot, ...)',
            'intentN': 'Detected intent for message N (intent1, intent2, ...)',
            'sentimentN': 'Sentiment score for message N (sentiment1, sentiment2, ...)',
            'entityN': 'Extracted entities for message N (entity1, entity2, ...)',
            'timestampN': 'Timestamp for message N (timestamp1, timestamp2, ...)',
            'msg_count': 'Total number of message exchanges'
        },
        'memory_queries': {
            'user_name': 'Find PERSON entity in entityN properties',
            'last_message': 'Get messageN where N = msg_count',
            'last_sentiment': 'Get sentimentN where N = msg_count',
            'last_intent': 'Get intentN where N = msg_count',
            'last_entity': 'Get entityN where N = msg_count',
            'first_message': 'Get message1_user and message1_bot',
            'average_sentiment': 'Average of all sentimentN values',
            'mood_summary': 'Overall mood based on average sentiment'
        }
    }


# Initialize on module load
get_driver()
init_graph_structure()
