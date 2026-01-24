import os
import time

# Fix for Python 3.8+ compatibility (time.clock was removed)
if not hasattr(time, 'clock'):
    time.clock = time.perf_counter

import aiml
from autocorrect import Speller

spell = Speller(lang='en')

BRAIN_FILE="./data/aiml_brain.dump"

k = aiml.Kernel()

if os.path.exists(BRAIN_FILE):
    print("Loading from brain file: " + BRAIN_FILE)
    k.loadBrain(BRAIN_FILE)
else:
    print("Parsing aiml files from data folder...")
    # Change to data directory and load all AIML files
    original_dir = os.getcwd()
    os.chdir(os.path.join(original_dir, "data"))
    k.learn("std-startup.xml") if os.path.exists("std-startup.xml") else None
    # Load all .aiml files
    for f in os.listdir("."):
        if f.endswith(".aiml"):
            try:
                k.learn(f)
            except Exception as e:
                print(f"Warning: Could not load {f}: {e}")
    os.chdir(original_dir)
    print("Saving brain file: " + BRAIN_FILE)
    k.saveBrain(BRAIN_FILE)


while True:
    query = input("User > ")
    query = [spell(w) for w in (query.split())]
    question = " ".join(query)
    response = k.respond(question)
    if response:
        print("bot > ", response)
    else:
        print("bot > :) ", )

