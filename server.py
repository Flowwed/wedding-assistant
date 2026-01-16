from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from openai import OpenAI
from supabase import create_client
import json
import os
from typing import Optional, Dict, List

# ================= SUPABASE =================
SUPABASE_URL = os.environ["SUPABASE_URL"]
SUPABASE_KEY = os.environ["SUPABASE_SERVICE_KEY"]
supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

app = FastAPI()

# ================= CORS =================
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ================= OPENAI =================
client = OpenAI()

# ================= PROMPT =================
with open("emily_prompt.txt", "r", encoding="utf-8") as f:
    BASE_PROMPT = f.read()

# ================= MEMORY =================
def get_token(request: Request) -> str:
    return request.query_params.get("token") or "dev"

def get_page(request: Request) -> str:
    page = request.query_params.get("page") or ""
    return page.strip() or "Entry"

def get_session_id(request: Request) -> str:
    return request.query_params.get("_") or "default"

def load_memory(token: str) -> dict:
    res = supabase.table("emily_memories").select("data").eq("token", token).single().execute()
    if not res.data:
        return {"profile": {}, "wedding": {}}
    return res.data["data"]

def save_memory(token: str, memory: dict):
    supabase.table("emily_memories").upsert({
        "token": token,
        "data": memory
    }).execute()

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
def root():
    return {"status": "ok"}

@app.post("/chat")
def chat(msg: Message, request: Request):
    try:
        token = get_token(request)
        page = get_page(request)
        sid = get_session_id(request)

        # 1. Load memory from Supabase (or empty)
        memory = load_memory(token)

        # 2. Ensure row exists even if empty
        save_memory(token, memory)

        conv = get_conversation(token, page, sid)

        if not msg.text or not msg.text.strip():
            greeting = returning_greeting(memory) if has_any_memory(memory) else FIRST_GREETING
            conv.append({"role": "assistant", "content": greeting})
            trim_conversation(conv)
            return {"reply": greeting}

        text = msg.text.strip()
        conv.append({"role": "user", "content": text})

        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=conv
        )

        reply = response.choices[0].message.content.strip()
        conv.append({"role": "assistant", "content": reply})
        trim_conversation(conv)

        return {"reply": reply}

    except Exception as e:
        print("CHAT ERROR:", e)
        return JSONResponse(
            status_code=500,
            content={"reply": "Backend error"}
        )
