from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from openai import OpenAI
from supabase import create_client
import json
import os
from typing import Optional, Dict, List

# ================= ENV =================
SUPABASE_URL = os.environ["SUPABASE_URL"]
SUPABASE_KEY = os.environ["SUPABASE_SERVICE_KEY"]

supabase = create_client(SUPABASE_URL, SUPABASE_KEY)
client = OpenAI()

# ================= APP =================
app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ================= PROMPT =================
with open("emily_prompt.txt", "r", encoding="utf-8") as f:
    BASE_PROMPT = f.read()

# ================= HELPERS =================
def get_token(request: Request) -> str:
    return request.query_params.get("token") or "dev"

def get_page(request: Request) -> str:
    return (request.query_params.get("page") or "Entry").strip()

def get_session_id(request: Request) -> str:
    return request.query_params.get("_") or "default"

def load_memory(token: str) -> dict:
    res = supabase.table("emily_memories").select("data").eq("token", token).execute()
    if res.data:
        return res.data[0]["data"]
    return {"profile": {}, "wedding": {}}

def save_memory(token: str, data: dict):
    supabase.table("emily_memories").upsert({
        "token": token,
        "data": data
    }).execute()

def has_any_memory(memory: dict) -> bool:
    return bool(memory.get("profile") or memory.get("wedding"))

def merge(a, b):
    for k, v in b.items():
        if isinstance(v, dict):
            a[k] = merge(a.get(k, {}), v)
        elif v not in (None, "", []):
            a[k] = v
    return a

# ================= CONVERSATIONS =================
conversations: Dict[str, List[dict]] = {}

def get_conversation(token: str, page: str, sid: str, memory: dict) -> List[dict]:
    key = f"{token}:{page}:{sid}"

    if key not in conversations:
        page_context = f"\n\nThe user is currently on the '{page}' page of FloWWed Studio."
        memory_context = f"\n\nKnown user memory:\n{json.dumps(memory, ensure_ascii=False, indent=2)}"
        system_prompt = BASE_PROMPT + page_context + memory_context

        conversations[key] = [
            {"role": "system", "content": system_prompt}
        ]

    return conversations[key]

def trim(conv: List[dict], max_messages: int = 40):
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
    name = p.get("name")
    if name:
        return f"Hi {name} — good to see you again. We can continue planning your wedding whenever you’re ready."
    return "Hi — good to see you again. We can continue planning your wedding whenever you’re ready."

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

        memory = load_memory(token)
        conv = get_conversation(token, page, sid, memory)

        if not msg.text or not msg.text.strip():
            greeting = returning_greeting(memory) if has_any_memory(memory) else FIRST_GREETING
            conv.append({"role": "assistant", "content": greeting})
            trim(conv)
            return {"reply": greeting}

        text = msg.text.strip()
        conv.append({"role": "user", "content": text})

        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=conv
        )

        reply = response.choices[0].message.content.strip()
        conv.append({"role": "assistant", "content": reply})
        trim(conv)

        # ===== MEMORY EXTRACTION =====
        memory_prompt = f"""
Extract any facts about the *user or their wedding*.
Never treat the assistant’s name as user data.
Do NOT extract names from labels like "Emily", "Assistant", or role names.
Only extract facts that clearly belong to the human user or their partner.

Return ONLY valid JSON in this format:

{{
  "profile": {{
    "name": null,
    "partner": null
  }},
  "wedding": {{
    "country": null,
    "city": null,
    "date": null,
    "style": null,
    "guests_count": null,
    "budget_range": null,
    "venue_shortlist": []
  }}
}}

Conversation:
User said: {text}
Assistant replied: {reply}
"""

        mem_resp = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "system", "content": memory_prompt}],
        )

        extracted = json.loads(mem_resp.choices[0].message.content)
        memory = merge(memory, extracted)
        save_memory(token, memory)

        return {"reply": reply}

    except Exception as e:
        print("CHAT ERROR:", e)
        return JSONResponse(status_code=500, content={"reply": "Backend error"})
