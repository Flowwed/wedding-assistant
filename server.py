from fastapi import FastAPI, Request
from fastapi.responses import FileResponse
from pydantic import BaseModel
from openai import OpenAI
import json
import os
import re
from typing import Optional, Dict, List, Tuple

app = FastAPI()

# ================= OPENAI =================
client = OpenAI()

# ================= PROMPT =================
with open("emily_prompt.txt", "r", encoding="utf-8") as f:
    SYSTEM_PROMPT = f.read()

# ================= MEMORY =================
MEMORY_DIR = "memories"
os.makedirs(MEMORY_DIR, exist_ok=True)

def get_token(request: Request) -> str:
    return request.query_params.get("token") or "dev"

def memory_path(token: str) -> str:
    return os.path.join(MEMORY_DIR, f"{token}.json")

def load_memory(token: str) -> dict:
    if not os.path.exists(memory_path(token)):
        return {"profile": {}, "wedding": {}}
    with open(memory_path(token), "r", encoding="utf-8") as f:
        return json.load(f)

def save_memory(token: str, memory: dict) -> None:
    with open(memory_path(token), "w", encoding="utf-8") as f:
        json.dump(memory, f, indent=2)

def has_any_memory(memory: dict) -> bool:
    return bool(memory.get("profile") or memory.get("wedding"))

# ================= CONVERSATIONS =================
conversations: Dict[str, List[dict]] = {}

def get_conversation(token: str) -> List[dict]:
    if token not in conversations:
        conversations[token] = [{"role": "system", "content": SYSTEM_PROMPT}]
    return conversations[token]

def trim_conversation(conv: List[dict], max_messages: int = 40):
    if len(conv) > max_messages:
        conv[:] = [conv[0]] + conv[-(max_messages - 1):]

# ================= GREETINGS =================
FIRST_GREETING = (
    "Hi — I’m Emily.\n"
    "I’m here to help you plan your wedding.\n"
    "We can start whenever you’re ready."
)

def returning_greeting(memory: dict) -> str:
    p = memory.get("profile", {})

    greeting = "Hi"
    if "name" in p:
        greeting += f" {p['name']}"

    greeting += " — good to see you again. We can continue planning your wedding whenever you’re ready."
    return greeting

# ================= EXTRACTORS =================
MONTHS = [
    "January","February","March","April","May","June",
    "July","August","September","October","November","December"
]

CHANGE_WORDS = r"\b(change|changed|move|moved|instead|now|actually|we decided)\b"

def extract_name(text: str, memory: dict) -> Optional[str]:
    if "name" in memory.get("profile", {}):
        return None

    m = re.search(r"\b(my name is|i am|i'm|this is)\s+([A-Z][a-z]+)\b", text, re.I)
    return m.group(2).capitalize() if m else None

def extract_month(text: str) -> Optional[str]:
    for m in MONTHS:
        if re.search(rf"\b{m}\b", text, re.I):
            return m
    return None

def extract_year(text: str) -> Optional[str]:
    m = re.search(r"\b(20\d{2})\b", text)
    return m.group(1) if m else None

def extract_guests(text: str) -> Optional[int]:
    if not re.search(r"\b(guests|guest|people)\b", text, re.I):
        return None
    m = re.search(r"\b(\d{2,4})\b", text)
    return int(m.group(1)) if m else None

def extract_location(text: str, memory: dict) -> Tuple[Optional[str], Optional[str]]:
    """
    SAFE location extractor:
    - ONLY 'in City, Country'
    - ONLY overwrite if user clearly changes location
    """

    if not re.search(r"\bwedding|ceremony|venue|married|marry\b", text, re.I):
        return None, None

    wants_change = bool(re.search(CHANGE_WORDS, text, re.I))
    already_set = bool(memory.get("wedding", {}).get("city") or memory.get("wedding", {}).get("country"))

    if already_set and not wants_change:
        return None, None

    m = re.search(
        r"\bin\s+([A-Z][a-zA-Z]*(?:\s+[A-Z][a-zA-Z]*)*)\s*,\s*([A-Z][a-zA-Z]*(?:\s+[A-Z][a-zA-Z]*)*)\b",
        text
    )
    if m:
        return m.group(1).strip(), m.group(2).strip()

    m = re.search(r"\bin\s+([A-Z][a-zA-Z]*(?:\s+[A-Z][a-zA-Z]*)*)\b", text)
    if m:
        return None, m.group(1).strip()

    return None, None

# ================= MODEL =================
class Message(BaseModel):
    text: Optional[str] = None

# ================= ROUTES =================
@app.get("/")
def home():
    return FileResponse("index.html")

@app.post("/chat")
def chat(msg: Message, request: Request):
    token = get_token(request)
    memory = load_memory(token)
    conv = get_conversation(token)

    # INIT
    if not msg.text or not msg.text.strip():
        greeting = returning_greeting(memory) if has_any_memory(memory) else FIRST_GREETING
        conv.append({"role": "assistant", "content": greeting})
        trim_conversation(conv)
        return {"reply": greeting}

    text = msg.text.strip()
    conv.append({"role": "user", "content": text})

    changed = False

    # Name
    name = extract_name(text, memory)
    if name:
        memory.setdefault("profile", {})["name"] = name
        changed = True

    # Location
    city, country = extract_location(text, memory)
    if city:
        memory.setdefault("wedding", {})["city"] = city
        changed = True
    if country:
        memory.setdefault("wedding", {})["country"] = country
        changed = True

    # Date & guests
    month = extract_month(text)
    if month:
        memory.setdefault("wedding", {})["month"] = month
        changed = True

    year = extract_year(text)
    if year:
        memory.setdefault("wedding", {})["year"] = year
        changed = True

    guests = extract_guests(text)
    if guests is not None:
        memory.setdefault("wedding", {})["guests"] = guests
        changed = True

    if changed:
        save_memory(token, memory)

    # Facts for model (SAFE ONLY)
    facts = []
    p = memory.get("profile", {})
    w = memory.get("wedding", {})

    if "name" in p:
        facts.append(f"Name: {p['name']}")
    if "month" in w and "year" in w:
        facts.append(f"Date: {w['month']} {w['year']}")
    if "guests" in w:
        facts.append(f"Guests: {w['guests']}")

    if facts:
        conv.append({
            "role": "system",
            "content": "Known facts:\n" + "\n".join(facts)
        })

    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=conv
    )

    reply = response.choices[0].message.content.strip()
    conv.append({"role": "assistant", "content": reply})
    trim_conversation(conv)

    return {"reply": reply}
