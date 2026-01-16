from openai import OpenAI
import json
import os
import re

client = OpenAI()
MEMORY_FILE = "memory.json"

KNOWN_COUNTRIES = {
    "italy", "france", "spain", "germany", "portugal",
    "greece", "usa", "canada", "uk", "england", "australia"
}

SYSTEM_PROMPT = """
You are Emily, a professional wedding planner with 10+ years of experience.

You always sound like a warm, confident woman.
Your tone is gentle, elegant, emotionally warm, and human.

You sound like a warm, modern woman in her early-to-mid 30s.

Your voice is light, clear, and alive.
It feels youthful, friendly, and emotionally warm —
never heavy, stern, deep, dark, or “matronly”.

You NEVER sound harsh, dry, robotic, or “masculine” in timbre.
You NEVER speak in a commanding, authoritarian, or instructional tone.

You avoid sharp, short, directive phrases.
You avoid imperatives like “Do this”, “You should”, “You must”.

You must NEVER invent facts.
If something is not explicitly stored in memory, say so calmly.

STYLE
- Max 2 sentences.
- One question at a time or none.
- No filler.
"""

# ================= LOAD MEMORY =================
if os.path.exists(MEMORY_FILE):
    with open(MEMORY_FILE, "r", encoding="utf-8") as f:
        memory = json.load(f)
else:
    memory = {}

memory.setdefault("profile", {})
memory.setdefault("wedding", {})
memory.setdefault("mode", "wedding")

conversation = [
    {"role": "system", "content": SYSTEM_PROMPT}
]

print("\n--- Emily · Wedding Assistant ---\n")

# ================= SAFE GREETING =================
name = memory["profile"].get("name")
country = memory["wedding"].get("country")

if country and country.lower() not in KNOWN_COUNTRIES:
    country = None

if name and country:
    greeting = f"Hi {name} — good to see you again. We can continue with your wedding plans in {country} whenever you’re ready."
elif name:
    greeting = f"Hi {name} — good to see you again. We can continue with your wedding plans whenever you’re ready."
else:
    greeting = "Hi — welcome back. We can continue with your wedding plans whenever you’re ready."

print(f"Emily: {greeting}")
conversation.append({"role": "assistant", "content": greeting})

# ================= ENTITY EXTRACTION =================
def extract_entities(text):
    lower = text.lower().strip()

    match = re.search(r"my name is ([a-zA-Z]+)", lower)
    if match:
        memory["profile"]["name"] = match.group(1).capitalize()

    if lower in KNOWN_COUNTRIES:
        memory["wedding"]["country"] = lower.capitalize()

# ================= MAIN LOOP =================
while True:
    user_input = input("You: ")

    if user_input.lower() in ("exit", "quit"):
        print("\nEmily: We can continue anytime.\n")
        break

    extract_entities(user_input)
    conversation.append({"role": "user", "content": user_input})

    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=conversation
    )

    reply = response.choices[0].message.content.strip()
    print(f"\nEmily: {reply}\n")
    conversation.append({"role": "assistant", "content": reply})

    with open(MEMORY_FILE, "w", encoding="utf-8") as f:
        json.dump(memory, f, indent=2)
