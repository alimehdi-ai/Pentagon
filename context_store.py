"""
Chat context storage for Pentagon.
Stores user/bot turns per session in memory and JSONL on disk.
Also extracts and stores user facts for contextual responses.
"""

from __future__ import annotations

import json
import os
import re
import threading
from typing import Dict, List, Optional, Tuple


# Patterns to extract facts from user messages
FACT_PATTERNS = [
    # "My X is Y" patterns
    (r"my (?:name is|name's) (\w+)", "name"),
    (r"i am (\w+)", "name"),  # Could be name or state
    (r"my (?:fav(?:ou?rite)?|favorite) (?:color|colour) is (\w+)", "favorite_color"),
    (r"my (?:fav(?:ou?rite)?|favorite) food is (.+?)(?:\.|$)", "favorite_food"),
    (r"my (?:fav(?:ou?rite)?|favorite) movie is (.+?)(?:\.|$)", "favorite_movie"),
    (r"my (?:fav(?:ou?rite)?|favorite) song is (.+?)(?:\.|$)", "favorite_song"),
    (r"my (?:fav(?:ou?rite)?|favorite) book is (.+?)(?:\.|$)", "favorite_book"),
    (r"my (?:fav(?:ou?rite)?|favorite) game is (.+?)(?:\.|$)", "favorite_game"),
    (r"my (?:fav(?:ou?rite)?|favorite) sport is (.+?)(?:\.|$)", "favorite_sport"),
    (r"my (?:fav(?:ou?rite)?|favorite) animal is (.+?)(?:\.|$)", "favorite_animal"),
    (r"my (?:fav(?:ou?rite)?|favorite) number is (\d+)", "favorite_number"),
    (r"my (?:fav(?:ou?rite)?|favorite) (\w+) is (.+?)(?:\.|$)", "favorite_generic"),
    (r"i (?:like|love|enjoy) (\w+)(?: a lot)?", "likes"),
    (r"i (?:hate|dislike|don't like) (\w+)", "dislikes"),
    (r"i am (\d+) years old", "age"),
    (r"i'm (\d+) years old", "age"),
    (r"my age is (\d+)", "age"),
    (r"i live in (.+?)(?:\.|$)", "location"),
    (r"i am from (.+?)(?:\.|$)", "from"),
    (r"i'm from (.+?)(?:\.|$)", "from"),
    (r"i work (?:at|for|in) (.+?)(?:\.|$)", "workplace"),
    (r"i am a (.+?)(?:\.|$)", "occupation"),
    (r"i'm a (.+?)(?:\.|$)", "occupation"),
    (r"my job is (.+?)(?:\.|$)", "job"),
    (r"my hobby is (.+?)(?:\.|$)", "hobby"),
    (r"my hobbies (?:are|include) (.+?)(?:\.|$)", "hobbies"),
    (r"i have a (.+?) named (\w+)", "pet"),
    (r"my pet(?:'s)? name is (\w+)", "pet_name"),
    (r"my (\w+)'s name is (\w+)", "named_thing"),
    (r"my birthday is (.+?)(?:\.|$)", "birthday"),
    (r"i was born (?:on|in) (.+?)(?:\.|$)", "birthday"),
]

# Patterns to detect questions about stored facts
QUESTION_PATTERNS = [
    (r"what(?:'s| is) my (?:fav(?:ou?rite)?|favorite) (color|colour)", "favorite_color"),
    (r"what(?:'s| is) my (?:fav(?:ou?rite)?|favorite) food", "favorite_food"),
    (r"what(?:'s| is) my (?:fav(?:ou?rite)?|favorite) movie", "favorite_movie"),
    (r"what(?:'s| is) my (?:fav(?:ou?rite)?|favorite) song", "favorite_song"),
    (r"what(?:'s| is) my (?:fav(?:ou?rite)?|favorite) book", "favorite_book"),
    (r"what(?:'s| is) my (?:fav(?:ou?rite)?|favorite) game", "favorite_game"),
    (r"what(?:'s| is) my (?:fav(?:ou?rite)?|favorite) sport", "favorite_sport"),
    (r"what(?:'s| is) my (?:fav(?:ou?rite)?|favorite) animal", "favorite_animal"),
    (r"what(?:'s| is) my (?:fav(?:ou?rite)?|favorite) number", "favorite_number"),
    (r"what(?:'s| is) my (?:fav(?:ou?rite)?|favorite) (\w+)", "favorite_generic"),
    (r"what do i like", "likes"),
    (r"what do i (?:hate|dislike)", "dislikes"),
    (r"how old am i", "age"),
    (r"what(?:'s| is) my age", "age"),
    (r"where do i live", "location"),
    (r"where am i from", "from"),
    (r"where do i work", "workplace"),
    (r"what(?:'s| is) my job", "job"),
    (r"what do i do", "occupation"),
    (r"what(?:'s| is) my occupation", "occupation"),
    (r"what(?:'s| is|are) my hobb(?:y|ies)", "hobby"),
    (r"do i have (?:a |any )?pet", "pet"),
    (r"what(?:'s| is) my pet(?:'s)? name", "pet_name"),
    (r"when(?:'s| is) my birthday", "birthday"),
    (r"do you remember (.+)", "memory_check"),
    (r"what did i (?:tell|say|mention) (?:you )?about (.+)", "recall_topic"),
]


class ChatContextStore:
    def __init__(self, file_path: str, max_in_memory: int = 2000) -> None:
        self.file_path = file_path
        self.max_in_memory = max_in_memory
        self._lock = threading.Lock()
        self._data: Dict[str, Dict[str, List[dict]]] = {}
        # Store extracted facts per user+session: {user_id: {session_id: {fact_type: value}}}
        self._facts: Dict[str, Dict[str, Dict[str, str]]] = {}
        self._ensure_dir()
        self._load_existing()

    def _ensure_dir(self) -> None:
        directory = os.path.dirname(self.file_path)
        if directory:
            os.makedirs(directory, exist_ok=True)

    def _load_existing(self) -> None:
        if not os.path.exists(self.file_path):
            return
        try:
            with open(self.file_path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        record = json.loads(line)
                        self._append_to_memory(record)
                        # Extract facts from historical messages
                        user_id = record.get("user_id")
                        session_id = record.get("session_id")
                        user_text = record.get("user_text")
                        if user_id and session_id and user_text:
                            self._extract_facts(user_id, session_id, user_text)
                    except json.JSONDecodeError:
                        continue
        except OSError:
            pass

    def _append_to_memory(self, record: dict) -> None:
        user_id = record.get("user_id")
        session_id = record.get("session_id")
        if not user_id or not session_id:
            return
        self._data.setdefault(user_id, {}).setdefault(session_id, []).append(record)

        # Trim oldest entries if needed
        total = sum(len(s) for u in self._data.values() for s in u.values())
        if total > self.max_in_memory:
            self._trim_oldest(total - self.max_in_memory)

    def _trim_oldest(self, count: int) -> None:
        removed = 0
        for user_id in list(self._data.keys()):
            for session_id in list(self._data[user_id].keys()):
                session_list = self._data[user_id][session_id]
                while session_list and removed < count:
                    session_list.pop(0)
                    removed += 1
                if not session_list:
                    del self._data[user_id][session_id]
            if not self._data[user_id]:
                del self._data[user_id]
            if removed >= count:
                return

    def add_message(
        self,
        user_id: str,
        session_id: str,
        user_text: str,
        bot_text: str,
        timestamp: str,
    ) -> None:
        record = {
            "user_id": user_id,
            "session_id": session_id,
            "user_text": user_text,
            "bot_text": bot_text,
            "timestamp": timestamp,
        }
        with self._lock:
            self._append_to_memory(record)
            # Extract facts from user message
            if user_text:
                self._extract_facts(user_id, session_id, user_text)
            try:
                with open(self.file_path, "a", encoding="utf-8") as f:
                    f.write(json.dumps(record, ensure_ascii=False) + "\n")
            except OSError:
                pass

    def get_history(self, user_id: str, session_id: str, limit: int = 10) -> List[dict]:
        sessions = self._data.get(user_id, {})
        history = sessions.get(session_id, [])
        return history[-limit:]

    def get_last_user_message(self, user_id: str, session_id: str) -> Optional[str]:
        history = self.get_history(user_id, session_id, limit=1)
        if not history:
            return None
        return history[-1].get("user_text")

    def get_last_bot_message(self, user_id: str, session_id: str) -> Optional[str]:
        history = self.get_history(user_id, session_id, limit=1)
        if not history:
            return None
        return history[-1].get("bot_text")

    def get_context_text(self, user_id: str, session_id: str, limit: int = 5) -> str:
        history = self.get_history(user_id, session_id, limit=limit)
        if not history:
            return ""
        lines = []
        for item in history:
            user_text = item.get("user_text", "")
            bot_text = item.get("bot_text", "")
            if user_text:
                lines.append(f"User: {user_text}")
            if bot_text:
                lines.append(f"Bot: {bot_text}")
        return "\n".join(lines)

    def _extract_facts(self, user_id: str, session_id: str, text: str) -> None:
        """Extract facts from user message and store them."""
        text_lower = text.lower().strip()
        
        for pattern, fact_type in FACT_PATTERNS:
            match = re.search(pattern, text_lower, re.IGNORECASE)
            if match:
                if fact_type == "favorite_generic":
                    # Handle "my favorite X is Y"
                    thing = match.group(1)
                    value = match.group(2).strip()
                    fact_key = f"favorite_{thing}"
                    self._store_fact(user_id, session_id, fact_key, value)
                elif fact_type == "named_thing":
                    # Handle "my X's name is Y"
                    thing = match.group(1)
                    name = match.group(2).strip()
                    fact_key = f"{thing}_name"
                    self._store_fact(user_id, session_id, fact_key, name)
                elif fact_type == "pet":
                    # Handle "I have a dog named Max"
                    pet_type = match.group(1).strip()
                    pet_name = match.group(2).strip()
                    self._store_fact(user_id, session_id, "pet", pet_type)
                    self._store_fact(user_id, session_id, "pet_name", pet_name)
                else:
                    value = match.group(1).strip()
                    self._store_fact(user_id, session_id, fact_type, value)

    def _store_fact(self, user_id: str, session_id: str, fact_type: str, value: str) -> None:
        """Store a fact for a user session."""
        if not value:
            return
        self._facts.setdefault(user_id, {}).setdefault(session_id, {})[fact_type] = value

    def get_fact(self, user_id: str, session_id: str, fact_type: str) -> Optional[str]:
        """Get a stored fact."""
        return self._facts.get(user_id, {}).get(session_id, {}).get(fact_type)

    def get_all_facts(self, user_id: str, session_id: str) -> Dict[str, str]:
        """Get all stored facts for a user session."""
        return self._facts.get(user_id, {}).get(session_id, {}).copy()

    def answer_from_context(self, user_id: str, session_id: str, query: str) -> Optional[str]:
        """Try to answer a question using stored facts and conversation history."""
        query_lower = query.lower().strip()
        facts = self.get_all_facts(user_id, session_id)
        
        # Check question patterns
        for pattern, fact_type in QUESTION_PATTERNS:
            match = re.search(pattern, query_lower, re.IGNORECASE)
            if match:
                if fact_type == "favorite_generic":
                    # "what is my favorite X"
                    thing = match.group(1)
                    fact_key = f"favorite_{thing}"
                    value = facts.get(fact_key)
                    if value:
                        return f"Your favorite {thing} is {value}! 😊"
                elif fact_type == "favorite_color":
                    value = facts.get("favorite_color") or facts.get("favorite_colour")
                    if value:
                        return f"Your favorite color is {value}! 🎨"
                elif fact_type == "memory_check":
                    # "do you remember X"
                    topic = match.group(1).strip()
                    return self._search_memory(user_id, session_id, topic, facts)
                elif fact_type == "recall_topic":
                    # "what did I tell you about X"
                    topic = match.group(1).strip()
                    return self._search_memory(user_id, session_id, topic, facts)
                else:
                    value = facts.get(fact_type)
                    if value:
                        return self._format_fact_response(fact_type, value)
        
        # Generic search in facts for keywords
        for word in query_lower.split():
            if len(word) > 3:  # Skip short words
                for fact_key, fact_value in facts.items():
                    if word in fact_key or word in fact_value.lower():
                        return self._format_fact_response(fact_key, fact_value)
        
        return None

    def _search_memory(self, user_id: str, session_id: str, topic: str, facts: Dict[str, str]) -> Optional[str]:
        """Search conversation history and facts for a topic."""
        topic_lower = topic.lower()
        
        # First check facts
        for fact_key, fact_value in facts.items():
            if topic_lower in fact_key or topic_lower in fact_value.lower():
                return f"Yes, I remember! {self._format_fact_response(fact_key, fact_value)}"
        
        # Then search conversation history
        history = self.get_history(user_id, session_id, limit=20)
        for item in reversed(history):
            user_text = item.get("user_text", "").lower()
            if topic_lower in user_text:
                return f"Yes, you mentioned: \"{item.get('user_text')}\""
        
        return f"I don't recall you telling me about {topic}. Could you remind me?"

    def _format_fact_response(self, fact_type: str, value: str) -> str:
        """Format a response based on fact type."""
        responses = {
            "name": f"Your name is {value}! 👤",
            "age": f"You are {value} years old! 🎂",
            "location": f"You live in {value}! 🏠",
            "from": f"You are from {value}! 🌍",
            "workplace": f"You work at {value}! 💼",
            "job": f"Your job is {value}! 💼",
            "occupation": f"You are a {value}! 👔",
            "hobby": f"Your hobby is {value}! 🎯",
            "hobbies": f"Your hobbies are {value}! 🎯",
            "pet": f"You have a {value}! 🐾",
            "pet_name": f"Your pet's name is {value}! 🐾",
            "birthday": f"Your birthday is {value}! 🎉",
            "likes": f"You like {value}! ❤️",
            "dislikes": f"You don't like {value}! 👎",
            "favorite_color": f"Your favorite color is {value}! 🎨",
            "favorite_food": f"Your favorite food is {value}! 🍽️",
            "favorite_movie": f"Your favorite movie is {value}! 🎬",
            "favorite_song": f"Your favorite song is {value}! 🎵",
            "favorite_book": f"Your favorite book is {value}! 📚",
            "favorite_game": f"Your favorite game is {value}! 🎮",
            "favorite_sport": f"Your favorite sport is {value}! ⚽",
            "favorite_animal": f"Your favorite animal is {value}! 🦁",
            "favorite_number": f"Your favorite number is {value}! 🔢",
        }
        
        # Handle favorite_X patterns
        if fact_type.startswith("favorite_"):
            thing = fact_type.replace("favorite_", "")
            return responses.get(fact_type, f"Your favorite {thing} is {value}! ✨")
        
        # Handle X_name patterns (like dog_name, cat_name)
        if fact_type.endswith("_name"):
            thing = fact_type.replace("_name", "")
            return f"Your {thing}'s name is {value}! 😊"
        
        return responses.get(fact_type, f"You told me that your {fact_type.replace('_', ' ')} is {value}! 😊")
