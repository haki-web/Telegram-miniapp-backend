from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import firebase_admin
from firebase_admin import credentials, firestore
import os
import logging
from fastapi import HTTPException
from pydantic import BaseModel

class PointsRequest(BaseModel):
    user_id: str
    amount: int

class ReferralRequest(BaseModel):
    user_id: str
    referral_id: str
    
# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

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
    try:
        user_id = data.get("user_id")
        amount = int(data.get("amount", 0))
        
        if not user_id or amount <= 0:
            return {"status": "error", "message": "Invalid user_id or amount"}
        
        ref = db.collection("users").document(user_id)
        
        # Atomic update (prevents race conditions)
        @firestore.transactional
        def update_in_transaction(transaction, ref, amount):
            doc = ref.get(transaction=transaction)
            current_points = doc.get("points", 0) if doc.exists else 0
            transaction.update(ref, {"points": current_points + amount})
        
        transaction = db.transaction()
        update_in_transaction(transaction, ref, amount)
        
        return {"status": "ok", "points_added": amount}
    
    except Exception as e:
        return {"status": "error", "message": str(e)}
        
@app.get("/points/{user_id}")
async def get_points(user_id: str):
    ref = db.collection("users").document(user_id).get()
    if ref.exists:
        return {"points": ref.to_dict().get("points", 0)}
    return {"points": 0}

@app.get("/leaderboard")
async def leaderboard(limit: int = 20):
    try:
        # Only show users with points > 0
        users_ref = db.collection("users")
        query = users_ref.where("points", ">", 0)\
                       .order_by("points", direction=firestore.Query.DESCENDING)\
                       .limit(limit)
        
        users = query.stream()
        
        data = []
        for u in users:
            user_data = u.to_dict()
            data.append({
                "user_id": u.id,
                "username": user_data.get("username", "Anonymous"),  # Add username if available
                "points": user_data.get("points", 0),
                "referral_count": user_data.get("referral_count", 0)  # Track referrals
            })
        
        return {
            "status": "ok",
            "count": len(data),
            "leaderboard": data
        }
    
    except Exception as e:
        return {"status": "error", "message": str(e)}

@app.post("/referral")
async def referral(data: dict):
    try:
        user_id = data.get("user_id")        
        referral_id = data.get("referral_id")  

        if not user_id or not referral_id or user_id == referral_id:
            return {"status": "error", "message": "Invalid referral"}

        referrer_ref = db.collection("users").document(user_id)
        referral_ref = db.collection("users").document(referral_id)

        @firestore.transactional
        def process_referral(transaction, referrer_ref, referral_ref):
            # Prevent duplicate referrals
            referral_doc = referral_ref.get(transaction=transaction)
            if referral_doc.exists and referral_doc.get("referred_by"):
                return False
            
            # Update referrer's points + count
            referrer_doc = referrer_ref.get(transaction=transaction)
            current_ref_count = referrer_doc.get("referral_count", 0) if referrer_doc.exists else 0
            current_points = referrer_doc.get("points", 0) if referrer_doc.exists else 0
            
            transaction.update(referral_ref, {
                "referred_by": user_id,
                "referral_timestamp": firestore.SERVER_TIMESTAMP
            })
            
            transaction.update(referrer_ref, {
                "referral_count": current_ref_count + 1,
                "points": current_points + 100  # 100 points per referral
            })
            
            return True

        transaction = db.transaction()
        success = process_referral(transaction, referrer_ref, referral_ref)
        
        if not success:
            return {"status": "ok", "message": "Referral already counted"}
            
        return {"status": "ok", "message": f"Referral reward given to {user_id}"}
    
    except Exception as e:
        return {"status": "error", "message": str(e)}
