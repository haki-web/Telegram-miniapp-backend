from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import firebase_admin
from firebase_admin import credentials, firestore
import os

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

if not firebase_admin._apps:
    cred = credentials.Certificate({
        "type": "service_account",
        "project_id": os.getenv("FIREBASE_PROJECT_ID"),
        "private_key": os.getenv("FIREBASE_PRIVATE_KEY").replace("\\n", "\n"),
        "client_email": os.getenv("FIREBASE_CLIENT_EMAIL"),
        "token_uri": "https://oauth2.googleapis.com/token"
    })
    firebase_admin.initialize_app(cred)
    print("✅ Firebase connected!")

db = firestore.client()

@app.get("/")
async def root():
    return {"status": "ok", "message": "Firebase FastAPI Backend Running!"}

@app.post("/add_points")
async def add_points(data: dict):
    user_id = data.get("user_id")
    amount = data.get("amount", 0)
    ref = db.collection("users").document(user_id)
    doc = ref.get()

    if doc.exists:
        current_points = doc.to_dict().get("points", 0)
        ref.update({"points": current_points + amount})
    else:
        ref.set({"points": amount})

    return {"status": "ok", "points_added": amount}

@app.get("/points/{user_id}")
async def get_points(user_id: str):
    ref = db.collection("users").document(user_id).get()
    if ref.exists:
        return {"points": ref.to_dict().get("points", 0)}
    return {"points": 0}

@app.get("/leaderboard")
async def leaderboard():
    users = db.collection("users").order_by("points", direction=firestore.Query.DESCENDING).limit(20).stream()
    data = [{"user_id": u.id, "points": u.to_dict().get("points", 0)} for u in users]
    return data

@app.post("/referral")
async def referral(data: dict):
    user_id = data.get("user_id")          # New user ID
    referral_id = data.get("referral_id")  # Referrer ID

    if not user_id or not referral_id or user_id == referral_id:
        return {"status": "error", "message": "Invalid referral"}

    user_ref = db.collection("users").document(user_id)
    user_doc = user_ref.get()

    if user_doc.exists:
        return {"status": "ok", "message": "User already registered"}

    # Save new user with referrer
    user_ref.set({
        "points": 0,
        "referred_by": referral_id,
        "joined": firestore.SERVER_TIMESTAMP
    })

    # Reward referrer
    referrer_ref = db.collection("users").document(referral_id)
    referrer_doc = referrer_ref.get()

    if referrer_doc.exists:
        data = referrer_doc.to_dict()
        current_points = data.get("points", 0)
        current_ref_count = data.get("refCount", 0)

        referrer_ref.update({
            "points": current_points + 100,
            "refCount": current_ref_count + 1
        })
    else:
        referrer_ref.set({
            "points": 100,
            "refCount": 1
        })

    return {"status": "ok", "message": f"Referral reward given to {referral_id}"}
