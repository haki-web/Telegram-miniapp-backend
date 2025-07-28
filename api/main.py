from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import firebase_admin
from firebase_admin import credentials, firestore
import os

# Initialize Firebase
if not firebase_admin._apps:
    cred = credentials.Certificate("firebase-adminsdk.json")  # Make sure this file is in your root dir
    firebase_admin.initialize_app(cred)

db = firestore.client()

# FastAPI app
app = FastAPI()

# Allow frontend origin
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # You can restrict this to your frontend URL
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class UserData(BaseModel):
    user_id: str
    username: str = ""
    photo_url: str = ""
    referrer_id: str = None  # optional

class PointsUpdate(BaseModel):
    user_id: str
    amount: int

@app.get("/")
def root():
    return {"status": "ok", "message": "Firebase FastAPI Backend Running!"}

@app.post("/register_user")
def register_user(data: UserData):
    user_ref = db.collection("users").document(data.user_id)
    doc = user_ref.get()

    if not doc.exists:
        user_ref.set({
            "user_id": data.user_id,
            "username": data.username,
            "photo_url": data.photo_url,
            "points": 0,
            "referrer_id": data.referrer_id,
        })
        if data.referrer_id:
            ref_ref = db.collection("users").document(data.referrer_id)
            ref_doc = ref_ref.get()
            if ref_doc.exists:
                ref_points = ref_doc.to_dict().get("points", 0)
                ref_ref.update({"points": ref_points + 10})  # reward 10 points to referrer

    return {"status": "ok", "message": "User registered"}

@app.post("/add_points")
def add_points(data: PointsUpdate):
    user_ref = db.collection("users").document(data.user_id)
    doc = user_ref.get()
    if doc.exists:
        current_points = doc.to_dict().get("points", 0)
        user_ref.update({"points": current_points + data.amount})
        return {"status": "ok", "new_points": current_points + data.amount}
    return {"status": "error", "message": "User not found"}

@app.get("/balance/{user_id}")
def get_balance(user_id: str):
    user_ref = db.collection("users").document(user_id)
    doc = user_ref.get()
    if doc.exists:
        points = doc.to_dict().get("points", 0)
        return {"status": "ok", "points": points}
    return {"status": "error", "message": "User not found"}

@app.get("/leaderboard")
def leaderboard():
    users_ref = db.collection("users").order_by("points", direction=firestore.Query.DESCENDING).limit(10)
    users = users_ref.stream()
    leaderboard = []

    for user in users:
        data = user.to_dict()
        leaderboard.append({
            "user_id": data.get("user_id"),
            "username": data.get("username"),
            "photo_url": data.get("photo_url"),
            "points": data.get("points"),
        })

    return {"status": "ok", "leaderboard": leaderboard}
