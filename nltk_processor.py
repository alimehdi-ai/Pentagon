"""
NLTK Processing Module for PEMABOT
Handles all NLP operations: tokenization, POS tagging, NER, sentiment analysis
Supports multi-sentence processing by tokenizing into child sentences
"""

import nltk
from nltk.tokenize import word_tokenize, sent_tokenize
from nltk.tag import pos_tag
from nltk.chunk import ne_chunk
from nltk.corpus import wordnet
from nltk.sentiment import SentimentIntensityAnalyzer

# Download required NLTK data
NLTK_PACKAGES = [
    'punkt', 'averaged_perceptron_tagger', 'maxent_ne_chunker',
    'words', 'wordnet', 'vader_lexicon', 'punkt_tab',
    'averaged_perceptron_tagger_eng', 'maxent_ne_chunker_tab'
]

def initialize_nltk():
    """Download all required NLTK packages"""
    for package in NLTK_PACKAGES:
        try:
            nltk.download(package, quiet=True)
        except:
            pass
    print("NLTK packages initialized")

# Initialize NLTK on module load
initialize_nltk()

# Initialize sentiment analyzer
sia = SentimentIntensityAnalyzer()

# Intent patterns for detection
INTENT_PATTERNS = {
    'greeting': ['hello', 'hi', 'hey', 'good morning', 'good evening', 'good afternoon', 'howdy', 'greetings'],
    'farewell': ['bye', 'goodbye', 'see you', 'take care', 'later', 'farewell'],
    'question': ['what', 'why', 'how', 'when', 'where', 'who', 'which', 'whose', 'whom'],
    'request': ['please', 'can you', 'could you', 'would you', 'help me', 'i need', 'i want'],
    'gratitude': ['thank', 'thanks', 'appreciate', 'grateful'],
    'apology': ['sorry', 'apologize', 'my bad', 'forgive'],
    'affirmation': ['yes', 'yeah', 'yep', 'sure', 'ok', 'okay', 'alright', 'correct', 'right'],
    'negation': ['no', 'nope', 'not', 'never', 'none', 'neither'],
    'opinion': ['think', 'believe', 'feel', 'opinion', 'view'],
    'information': ['tell me', 'explain', 'describe', 'define', 'meaning of', 'what is']
}


def analyze_sentiment(text):
    """Analyze sentiment using VADER"""
    scores = sia.polarity_scores(text)
    compound = scores['compound']
    if compound >= 0.05:
        sentiment = 'Positive'
        emoji = '😊'
    elif compound <= -0.05:
        sentiment = 'Negative'
        emoji = '😔'
    else:
        sentiment = 'Neutral'
        emoji = '😐'
    return {
        'sentiment': sentiment,
        'emoji': emoji,
        'scores': {
            'positive': round(scores['pos'] * 100, 1),
            'negative': round(scores['neg'] * 100, 1),
            'neutral': round(scores['neu'] * 100, 1),
            'compound': round(compound, 3)
        }
    }


def detect_intent(text):
    """Detect intent from text using pattern matching and NLP"""
    text_lower = text.lower()
    detected_intents = []
    
    for intent, patterns in INTENT_PATTERNS.items():
        for pattern in patterns:
            if pattern in text_lower:
                detected_intents.append(intent)
                break
    
    # Use sentiment for additional context
    sentiment = analyze_sentiment(text)
    if sentiment['sentiment'] == 'Positive':
        if 'affirmation' not in detected_intents:
            detected_intents.append('positive_sentiment')
    elif sentiment['sentiment'] == 'Negative':
        detected_intents.append('negative_sentiment')
    
    # Default intent if none detected
    if not detected_intents:
        detected_intents.append('general')
    
    return detected_intents


def extract_entities(text):
    """Extract entities from text using NLP"""
    entities = []
    try:
        tokens = word_tokenize(text)
        pos_tags_list = pos_tag(tokens)
        tree = ne_chunk(pos_tags_list)
        
        for subtree in tree:
            if hasattr(subtree, 'label'):
                entity_name = " ".join([word for word, tag in subtree.leaves()])
                entity_type = subtree.label()
                entities.append({
                    'name': entity_name,
                    'type': entity_type
                })
        
        # Also extract nouns as potential entities
        for word, tag in pos_tags_list:
            if tag in ['NNP', 'NNPS']:  # Proper nouns
                if not any(e['name'] == word for e in entities):
                    entities.append({
                        'name': word,
                        'type': 'NOUN'
                    })
    except Exception as e:
        print(f"Entity extraction error: {e}")
    
    return entities


def get_wordnet_pos(treebank_tag):
    """Convert treebank POS tag to WordNet POS tag"""
    if treebank_tag.startswith('J'):
        return wordnet.ADJ
    elif treebank_tag.startswith('V'):
        return wordnet.VERB
    elif treebank_tag.startswith('N'):
        return wordnet.NOUN
    elif treebank_tag.startswith('R'):
        return wordnet.ADV
    else:
        return None


def extract_nouns_with_definitions(pos_tags):
    """Extract nouns and get their WordNet definitions"""
    nouns_with_defs = []
    for word, tag in pos_tags:
        if tag.startswith('NN'):  # NN, NNS, NNP, NNPS
            synsets = wordnet.synsets(word, pos=wordnet.NOUN)
            if synsets:
                definition = synsets[0].definition()
                nouns_with_defs.append({
                    'word': word,
                    'definition': definition
                })
    return nouns_with_defs


def extract_named_entities(pos_tags):
    """Extract named entities using NLTK's ne_chunk"""
    entities = []
    try:
        tree = ne_chunk(pos_tags)
        for subtree in tree:
            if hasattr(subtree, 'label'):
                entity_name = " ".join([word for word, tag in subtree.leaves()])
                entity_type = subtree.label()
                entities.append({
                    'name': entity_name,
                    'type': entity_type
                })
    except:
        pass
    return entities


def process_nlp(text):
    """Process text with all NLP features"""
    result = {
        'tokens': [],
        'pos_tags': [],
        'nouns': [],
        'entities': [],
        'sentiment': {}
    }
    
    try:
        # Tokenization
        tokens = word_tokenize(text)
        result['tokens'] = tokens
        
        # POS Tagging
        pos_tags = pos_tag(tokens)
        result['pos_tags'] = [{'word': word, 'tag': tag} for word, tag in pos_tags]
        
        # Extract nouns with definitions
        result['nouns'] = extract_nouns_with_definitions(pos_tags)
        
        # Named Entity Recognition
        result['entities'] = extract_named_entities(pos_tags)
        
        # Sentiment Analysis
        result['sentiment'] = analyze_sentiment(text)
        
    except Exception as e:
        print(f"NLP processing error: {e}")
    
    return result


def tokenize_sentences(text):
    """
    Tokenize text into individual sentences for multi-sentence handling.
    Returns a list of sentence strings.
    """
    try:
        sentences = sent_tokenize(text)
        # Filter out empty sentences and strip whitespace
        sentences = [s.strip() for s in sentences if s.strip()]
        return sentences if sentences else [text]
    except Exception as e:
        print(f"Sentence tokenization error: {e}")
        return [text]


def is_multi_sentence(text):
    """
    Check if text contains multiple sentences.
    Returns True if there are 2 or more sentences.
    """
    sentences = tokenize_sentences(text)
    return len(sentences) > 1


def process_multi_sentence(text):
    """
    Process text that may contain multiple sentences.
    Returns a list of processed sentence data.
    """
    sentences = tokenize_sentences(text)
    
    results = []
    for i, sentence in enumerate(sentences):
        sentence_data = {
            'sentence_num': i + 1,
            'text': sentence,
            'nlp': process_nlp(sentence),
            'intent': detect_intent(sentence)
        }
        results.append(sentence_data)
    
    return results


def combine_nlp_results(sentence_results):
    """
    Combine NLP results from multiple sentences into a single result.
    Used for the overall analysis display.
    """
    combined = {
        'tokens': [],
        'pos_tags': [],
        'nouns': [],
        'entities': [],
        'sentiment': {'sentiment': 'Neutral', 'emoji': '😐', 'scores': {'positive': 0, 'negative': 0, 'neutral': 100, 'compound': 0}},
        'sentences': [],
        'is_multi_sentence': len(sentence_results) > 1
    }
    
    total_compound = 0
    total_pos = 0
    total_neg = 0
    total_neu = 0
    
    for result in sentence_results:
        nlp = result['nlp']
        combined['tokens'].extend(nlp.get('tokens', []))
        combined['pos_tags'].extend(nlp.get('pos_tags', []))
        combined['nouns'].extend(nlp.get('nouns', []))
        combined['entities'].extend(nlp.get('entities', []))
        
        # Accumulate sentiment scores
        if nlp.get('sentiment'):
            scores = nlp['sentiment'].get('scores', {})
            total_compound += scores.get('compound', 0)
            total_pos += scores.get('positive', 0)
            total_neg += scores.get('negative', 0)
            total_neu += scores.get('neutral', 0)
        
        combined['sentences'].append({
            'num': result['sentence_num'],
            'text': result['text'],
            'intent': result['intent'],
            'sentiment': nlp.get('sentiment', {}).get('sentiment', 'Neutral')
        })
    
    # Average sentiment scores
    n = len(sentence_results)
    if n > 0:
        avg_compound = total_compound / n
        combined['sentiment']['scores'] = {
            'positive': round(total_pos / n, 1),
            'negative': round(total_neg / n, 1),
            'neutral': round(total_neu / n, 1),
            'compound': round(avg_compound, 3)
        }
        
        # Determine overall sentiment
        if avg_compound >= 0.05:
            combined['sentiment']['sentiment'] = 'Positive'
            combined['sentiment']['emoji'] = '😊'
        elif avg_compound <= -0.05:
            combined['sentiment']['sentiment'] = 'Negative'
            combined['sentiment']['emoji'] = '😔'
        else:
            combined['sentiment']['sentiment'] = 'Neutral'
            combined['sentiment']['emoji'] = '😐'
    
    # Remove duplicate entities
    seen_entities = set()
    unique_entities = []
    for ent in combined['entities']:
        key = (ent.get('name', ''), ent.get('type', ''))
        if key not in seen_entities:
            seen_entities.add(key)
            unique_entities.append(ent)
    combined['entities'] = unique_entities
    
    # Remove duplicate nouns
    seen_nouns = set()
    unique_nouns = []
    for noun in combined['nouns']:
        if noun.get('word') not in seen_nouns:
            seen_nouns.add(noun.get('word'))
            unique_nouns.append(noun)
    combined['nouns'] = unique_nouns
    
    return combined
