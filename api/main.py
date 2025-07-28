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
    user_id = data.get("user_id")        
    referral_id = data.get("referral_id")  

    if not user_id or not referral_id or user_id == referral_id:
        return {"status": "error", "message": "Invalid referral"}

    referral_user_ref = db.collection("users").document(referral_id)
    referral_doc = referral_user_ref.get()

    if referral_doc.exists:
        if referral_doc.to_dict().get("referred_by"):
            return {"status": "ok", "message": "Referral already counted"}
    else:
        referral_user_ref.set({})  # Create empty if doesn't exist

    # Set referred_by field
    referral_user_ref.update({"referred_by": user_id})

    # Add points to referrer
    referrer_ref = db.collection("users").document(user_id)
    doc = referrer_ref.get()
    if doc.exists:
        current_points = doc.to_dict().get("points", 0)
        referrer_ref.update({"points": current_points + 100}) 
    else:
        referrer_ref.set({"points": 100})

    return {"status": "ok", "message": f"Referral reward given to {user_id}"}
