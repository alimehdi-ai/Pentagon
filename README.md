# Pentagon - AI Chatbot

An AI-powered chatbot using AIML, NLP, and Neo4j knowledge graph.

## Team Members
- Ali Mehdi
- Zaryab
- Muqeet
- Naila
- Shaman

## Features
- Natural Language Processing (NLP) for understanding user messages
- AIML-based conversational patterns
- Neo4j graph database for knowledge storage
- Real-time sentiment analysis
- Session-based conversation history
- User authentication system

## Installation

1. Install dependencies:
```
pip install -r requirements.txt
```

2. Make sure Neo4j is running on bolt://127.0.0.1:7687

3. Run the bot:
```
python bot.py
```

4. Open your browser and navigate to http://localhost:5000

## Default Login
- Username: admin
- Password: 12345678

## Project Structure
- bot.py - Main Flask application
- neo4j_handler.py - Neo4j database operations
- nltk_processor.py - NLP processing functions
- context_store.py - Chat context storage
- data/ - AIML files and bot data
- templates/ - HTML templates
- static/ - Static files (logo, etc.)

## Technologies Used
- Python Flask
- AIML (Artificial Intelligence Markup Language)
- NLTK (Natural Language Toolkit)
- Neo4j Graph Database
- jQuery

## PF AI Course Project
