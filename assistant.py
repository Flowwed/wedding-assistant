
from openai import OpenAI
import json
import os
import re

# 1. ВСТАВЬ СЮДА СВОЙ API-КЛЮЧ
client = OpenAI()
MEMORY_FILE = "memory.json"

KNOWN_COUNTRIES = {
    "italy", "france", "spain", "germany", "portugal",
    "greece", "usa", "canada", "uk", "england", "australia"
}

SYSTEM_PROMPT = """
You are Emily, a professional wedding planner with 10+ years of experience.

You must NEVER invent facts.
If something is not explicitly stored in memory, say so calmly and professionally.

You speak like a calm, confident human.
You have subtle, warm humor.
Not a therapist. Not a robot. Not a salesperson.

CORE RULE
- You can only reference wedding facts that exist in memory.
- Never guess or assume missing details.

ROLE
- You are primarily a wedding planner.
- You can talk about any topic naturally.
- Wedding planning context is preserved silently.

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

conversation = [{"role": "system", "content": SYSTEM_PROMPT}]

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

    # name
    match = re.search(r"my name is ([a-zA-Z]+)", lower)
    if match:
        memory["profile"]["name"] = match.group(1).capitalize()

    # country (STRICT)
    if lower in KNOWN_COUNTRIES:
        memory["wedding"]["country"] = lower.capitalize()

# ================= MODE =================
def detect_mode(text):
    keywords = ["wedding", "marriage", "ceremony", "venue", "guests", "date", "country"]
    return "wedding" if any(k in text.lower() for k in keywords) else "chat"

# ================= MAIN LOOP =================
while True:
    user_input = input("You: ")

    if user_input.lower() in ("exit", "quit"):
        print("\nEmily: We can continue anytime.\n")
        break

    conversation.append({"role": "user", "content": user_input})

    extract_entities(user_input)
    memory["mode"] = detect_mode(user_input)

    # ===== HARD MEMORY TRUTH =====
    if "remember the country" in user_input.lower():
        country = memory["wedding"].get("country")
        if country:
            reply = f"Yes — you mentioned {country}."
        else:
            reply = "I don’t have a country noted yet. When you decide, I’ll keep it on file."
        print(f"\nEmily: {reply}\n")
        conversation.append({"role": "assistant", "content": reply})
    else:
        prompt = f"""
Conversation so far is above.

Current mode: {memory["mode"]}

Rules:
- Never invent facts.
- If mode is wedding, continue logically.
- If mode is chat, follow naturally.
"""

        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=conversation + [{"role": "user", "content": prompt}]
        )

        reply = response.choices[0].message.content.strip()
        print(f"\nEmily: {reply}\n")
        conversation.append({"role": "assistant", "content": reply})

    # ================= SAVE MEMORY =================
    with open(MEMORY_FILE, "w", encoding="utf-8") as f:
        json.dump(memory, f, indent=2)


