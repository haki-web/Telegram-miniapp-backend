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

@app.get("/leaderboard")
async def leaderboard(limit: int = 20):
    try:
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
                "username": user_data.get("username", "Anonymous"),
                "points": user_data.get("points", 0),
                "referral_count": user_data.get("referral_count", 0)
            })
        
        # Ensure we always return an array, even if empty
        return {
            "status": "ok",
            "count": len(data),
            "leaderboard": data or []  # Return empty array if no data
        }
    
    except Exception as e:
        logger.error(f"Leaderboard error: {str(e)}")
        return {
            "status": "error",
            "message": str(e),
            "leaderboard": []  # Frontend can handle empty state
        }
        
@app.post("/add_points")
async def add_points(request: PointsRequest):
    try:
        user_id = request.user_id
        amount = request.amount
        
        if amount <= 0:
            raise HTTPException(status_code=400, detail="Amount must be positive")
        
        user_ref = db.collection("users").document(user_id)
        
        # Get user document (synchronous operation)
        user_doc = user_ref.get()
        
        # Get points safely
        current_points = 0
        if user_doc.exists:
            # CORRECT: Only 2 arguments - field name and default value
            current_points = user_doc.get("points", 0)  
        
        # Update points (async operation)
        await user_ref.set({
            "points": firestore.Increment(amount),
            "last_updated": firestore.SERVER_TIMESTAMP,
            "username": user_doc.get("username", f"User-{user_id[:4]}")
        }, merge=True)
        
        return {
            "status": "ok",
            "points_added": amount,
            "new_balance": current_points + amount,
            "user_id": user_id
        }
    
    except Exception as e:
        logger.error(f"Error adding points: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))
        
@app.post("/referral")
async def referral(request: ReferralRequest):
    try:
        user_id = request.user_id
        referral_id = request.referral_id

        if user_id == referral_id:
            return {"status": "error", "message": "Cannot refer yourself"}
        
        referrer_ref = db.collection("users").document(user_id)
        referral_ref = db.collection("users").document(referral_id)
        
        # Check if referral already exists
        referral_doc = await referral_ref.get()
        if referral_doc.exists and referral_doc.get("referred_by"):
            return {"status": "error", "message": "Already referred"}
        
        # Batch write for atomic operation
        batch = db.batch()
        batch.set(referral_ref, {
            "referred_by": user_id,
            "referral_timestamp": firestore.SERVER_TIMESTAMP
        }, merge=True)
        
        batch.update(referrer_ref, {
            "points": firestore.Increment(100),
            "referral_count": firestore.Increment(1),
            "last_updated": firestore.SERVER_TIMESTAMP
        })
        
        await batch.commit()
        
        return {"status": "ok", "message": "Referral recorded", "reward": 100}
    
    except Exception as e:
        logger.error(f"Referral error: {str(e)}")
        return {"status": "error", "message": str(e)}
