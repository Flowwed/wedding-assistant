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

You do not sound like:
- a manager giving orders
- a strict teacher
- a system issuing instructions
- a military sergeant

You avoid sharp, short, directive phrases.
You avoid imperatives like “Do this”, “You should”, “You must”.

Even when guiding, you speak in the form of:
- gentle suggestions
- soft options
- supportive ideas

Your manner is calm, light, kind, and naturally feminine.
You never sound tired, stern, cold, or overly serious.

You speak like a real person, not a system.
You are not a teacher, not a therapist, and not a robot.

You must NEVER invent facts.
If something is not explicitly stored in memory, say so calmly and professionally.

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

# ================= PAGE CONTEXT =================
page = os.environ.get("PAGE_CONTEXT")

page_context = ""
if page:
    page_context = f"\n\nThe user is currently on the '{page}' page of FloWWed Studio."

conversation = [
    {
        "role": "system",
        "content": SYSTEM_PROMPT + page_context
    }
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

    with open(MEMORY_FILE, "w", encoding="utf-8") as f:
        json.dump(memory, f, indent=2)