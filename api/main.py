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
        
        return {
            "status": "ok",
            "count": len(data),
            "leaderboard": data or []
        }
    
    except Exception as e:
        logger.error(f"Leaderboard error: {str(e)}")
        return {
            "status": "error",
            "message": str(e),
            "leaderboard": []
        }
        
@app.post("/add_points")
async def add_points(request: PointsRequest):
    try:
        user_id = request.user_id
        amount = request.amount
        
        if amount <= 0:
            raise HTTPException(status_code=400, detail="Amount must be positive")
        
        user_ref = db.collection("users").document(user_id)
        
        # Use transaction to ensure atomic update
        @firestore.transactional
        def update_points(transaction, user_ref, amount):
            snapshot = user_ref.get(transaction=transaction)
            current_points = snapshot.get("points", 0) if snapshot.exists else 0
            new_points = current_points + amount
            
            transaction.update(user_ref, {
                "points": new_points,
                "last_updated": firestore.SERVER_TIMESTAMP
            })
            
            return new_points
        
        transaction = db.transaction()
        new_balance = update_points(transaction, user_ref, amount)
        
        return {
            "status": "ok",
            "points_added": amount,
            "new_balance": new_balance,
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
        
        # Use transaction to ensure atomic operation
        @firestore.transactional
        def process_referral(transaction, referrer_ref, referral_ref):
            # Check if referral exists and has already been referred
            referral_snap = referral_ref.get(transaction=transaction)
            if referral_snap.exists and referral_snap.get("referred_by"):
                return False, "Already referred"
            
            # Update referral document
            transaction.set(referral_ref, {
                "referred_by": user_id,
                "referral_timestamp": firestore.SERVER_TIMESTAMP
            }, merge=True)
            
            # Update referrer's points and count
            referrer_snap = referrer_ref.get(transaction=transaction)
            current_points = referrer_snap.get("points", 0) if referrer_snap.exists else 0
            current_count = referrer_snap.get("referral_count", 0) if referrer_snap.exists else 0
            
            transaction.update(referrer_ref, {
                "points": current_points + 100,
                "referral_count": current_count + 1,
                "last_updated": firestore.SERVER_TIMESTAMP
            })
            
            return True, "Referral recorded"
        
        transaction = db.transaction()
        success, message = process_referral(transaction, referrer_ref, referral_ref)
        
        if not success:
            return {"status": "error", "message": message}
            
        return {"status": "ok", "message": message, "reward": 100}
    
    except Exception as e:
        logger.error(f"Referral error: {str(e)}")
        return {"status": "error", "message": str(e)}
