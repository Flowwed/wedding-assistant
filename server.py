from fastapi import FastAPI, Request
from fastapi.responses import FileResponse
from pydantic import BaseModel
from openai import OpenAI
from supabase import create_client
import json
import os
import re
from typing import Optional, Dict, List

app = FastAPI()

# ================= OPENAI =================
client = OpenAI()

# ================= SUPABASE =================
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_KEY")
supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

def save_message(token: str, page: str, sid: str, role: str, content: str):
    supabase.table("messages").insert({
        "token": token,
        "page": page,
        "sid": sid,
        "role": role,
        "content": content
    }).execute()

# ================= PROMPT =================
with open("emily_prompt.txt", "r", encoding="utf-8") as f:
    BASE_PROMPT = f.read()

# ================= MEMORY =================
MEMORY_DIR = "memories"
os.makedirs(MEMORY_DIR, exist_ok=True)

def get_token(request: Request) -> str:
    return request.query_params.get("token") or "dev"

def get_page(request: Request) -> str:
    page = request.query_params.get("page") or ""
    page = page.strip()
    return page if page else "Entry"

def get_session_id(request: Request) -> str:
    return request.query_params.get("_") or "default"

def memory_path(token: str) -> str:
    return os.path.join(MEMORY_DIR, f"{token}.json")

def load_memory(token: str) -> dict:
    if not os.path.exists(memory_path(token)):
        return {"profile": {}, "wedding": {}}
    with open(memory_path(token), "r", encoding="utf-8") as f:
        return json.load(f)

def has_any_memory(memory: dict) -> bool:
    return bool(memory.get("profile") or memory.get("wedding"))

# ================= CONVERSATIONS =================
conversations: Dict[str, List[dict]] = {}

def get_conversation(token: str, page: str, sid: str) -> List[dict]:
    key = f"{token}:{page}:{sid}"

    if key not in conversations:
        page_context = f"\n\nThe user is currently on the '{page}' page of FloWWed Studio."
        system_prompt = BASE_PROMPT + page_context
        conversations[key] = [{"role": "system", "content": system_prompt}]

    return conversations[key]

def trim_conversation(conv: List[dict], max_messages: int = 40):
    if len(conv) > max_messages:
        conv[:] = [conv[0]] + conv[-(max_messages - 1):]

# ================= GREETINGS =================
FIRST_GREETING = (
    "Hi — I’m Emily.\n"
    "I’m here to help you plan your wedding.\n"
    "And if you’d like, I can also walk you through how everything works inside FloWWed Studio.\n"
    "We can start whenever you’re ready."
)

def returning_greeting(memory: dict) -> str:
    p = memory.get("profile", {})
    greeting = "Hi"
    if "name" in p:
        greeting += f" {p['name']}"
    greeting += " — good to see you again. We can continue planning your wedding whenever you’re ready."
    return greeting

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
    page = get_page(request)
    sid = get_session_id(request)

    memory = load_memory(token)
    conv = get_conversation(token, page, sid)

    if not msg.text or not msg.text.strip():
        greeting = returning_greeting(memory) if has_any_memory(memory) else FIRST_GREETING
        conv.append({"role": "assistant", "content": greeting})
        save_message(token, page, sid, "assistant", greeting)
        trim_conversation(conv)
        return {"reply": greeting}

    text = msg.text.strip()
    conv.append({"role": "user", "content": text})
    save_message(token, page, sid, "user", text)

    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=conv
    )

    reply = response.choices[0].message.content.strip()
    conv.append({"role": "assistant", "content": reply})
    save_message(token, page, sid, "assistant", reply)
    trim_conversation(conv)

    return {"reply": reply}
