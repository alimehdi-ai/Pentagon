"""Quick script to check users in Neo4j database"""
from neo4j import GraphDatabase
import hashlib

NEO4J_URI = "bolt://127.0.0.1:7687"
NEO4J_USER = "neo4j"
NEO4J_PASSWORD = "Pakistan@2"

def hash_password(password):
    return hashlib.sha256(password.encode()).hexdigest()

driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))
driver.verify_connectivity()
print("✓ Connected to Neo4j!")

with driver.session() as session:
    # Check all users
    result = session.run("""
        MATCH (p)
        WHERE (p:Person OR p:User)
        RETURN p.username as username, p.email as email, 
               p.password_hash as hash, labels(p) as labels
    """)
    users = list(result)
    print(f"\n✓ Found {len(users)} users in database:")
    for u in users:
        print(f"  - Username: '{u['username']}', Email: {u['email']}, Labels: {u['labels']}")
        if u['hash']:
            print(f"    Hash (first 40): {u['hash'][:40]}...")

driver.close()
