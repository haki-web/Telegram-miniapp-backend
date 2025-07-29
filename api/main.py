from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import firebase_admin
from firebase_admin import credentials, firestore
import os
import logging
from fastapi import HTTPException
from pydantic import BaseModel
import asyncio

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
        logger.info(f"Fetching leaderboard with limit: {limit}")
        
        # Use async for better performance
        def fetch_leaderboard():
            users_ref = db.collection("users")
            query = users_ref.order_by("points", direction=firestore.Query.DESCENDING)
            if limit > 0:
                query = query.limit(limit)
            return query.stream()
        
        # Run in thread to avoid blocking
        users = await asyncio.to_thread(fetch_leaderboard)
        
        data = []
        for u in users:
            user_data = u.to_dict()
            # Make sure we have all required fields
            if "points" in user_data:
                data.append({
                    "user_id": u.id,
                    "username": user_data.get("username", "Anonymous"),
                    "points": user_data.get("points", 0),
                    "referral_count": user_data.get("referral_count", 0)
                })
        
        logger.info(f"Returning {len(data)} leaderboard entries")
        return {
            "status": "ok",
            "count": len(data),
            "leaderboard": data
        }
    
    except Exception as e:
        logger.exception("Leaderboard error")
        return {
            "status": "error",
            "message": "Failed to load leaderboard. Please try again later.",
            "leaderboard": []
        }
        
@app.post("/add_points")
async def add_points(request: PointsRequest):
    try:
        user_id = request.user_id
        amount = request.amount
        
        if amount <= 0:
            raise HTTPException(status_code=400, detail="Amount must be positive")
        
        logger.info(f"Adding {amount} points to user {user_id}")
        user_ref = db.collection("users").document(user_id)
        
        # Use atomic increment to ensure consistency
        await user_ref.set({
            "points": firestore.Increment(amount),
            "last_updated": firestore.SERVER_TIMESTAMP
        }, merge=True)
        
        # Get updated balance to return
        user_doc = await asyncio.to_thread(user_ref.get)
        new_balance = user_doc.get("points", 0) if user_doc.exists else amount
        
        return {
            "status": "ok",
            "points_added": amount,
            "new_balance": new_balance,
            "user_id": user_id
        }
    
    except Exception as e:
        logger.exception(f"Error adding points: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to add points. Please try again.")

@app.post("/referral")
async def referral(request: ReferralRequest):
    try:
        user_id = request.user_id
        referral_id = request.referral_id

        if user_id == referral_id:
            return {"status": "error", "message": "Cannot refer yourself"}
        
        logger.info(f"Processing referral: {user_id} -> {referral_id}")
        referrer_ref = db.collection("users").document(user_id)
        referral_ref = db.collection("users").document(referral_id)
        
        # Check if referral already exists
        referral_doc = await asyncio.to_thread(referral_ref.get)
        if referral_doc.exists and referral_doc.get("referred_by"):
            return {"status": "error", "message": "This user was already referred"}
        
        # Create both updates in a batch
        batch = db.batch()
        
        # Create referral record
        batch.set(referral_ref, {
            "referred_by": user_id,
            "referral_timestamp": firestore.SERVER_TIMESTAMP
        }, merge=True)
        
        # Update referrer's points and count
        batch.update(referrer_ref, {
            "points": firestore.Increment(100),
            "referral_count": firestore.Increment(1),
            "last_updated": firestore.SERVER_TIMESTAMP
        })
        
        # Commit the batch operation
        await asyncio.to_thread(batch.commit)
        
        # Get updated referral count
        referrer_doc = await asyncio.to_thread(referrer_ref.get)
        new_count = referrer_doc.get("referral_count", 0) if referrer_doc.exists else 1
        
        return {
            "status": "ok", 
            "message": "Referral recorded", 
            "reward": 100,
            "new_referral_count": new_count
        }
    
    except Exception as e:
        logger.exception(f"Referral error: {str(e)}")
        return {"status": "error", "message": "Failed to process referral. Please try again."}
