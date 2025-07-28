import json
import os
import firebase_admin
from firebase_admin import credentials, firestore

def get_app():
    if not firebase_admin._apps:
        cred = credentials.Certificate({
            "type": os.environ.get("FB_TYPE"),
            "project_id": os.environ.get("FB_PROJECT_ID"),
            "private_key_id": os.environ.get("FB_PRIVATE_KEY_ID"),
            "private_key": os.environ.get("FB_PRIVATE_KEY").replace("\\n", "\n"),
            "client_email": os.environ.get("FB_CLIENT_EMAIL"),
            "client_id": os.environ.get("FB_CLIENT_ID"),
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
            "auth_provider_x509_cert_url": "https://www.googleapis.com/oauth2/v1/certs",
            "client_x509_cert_url": os.environ.get("FB_CLIENT_CERT_URL")
        })
        firebase_admin.initialize_app(cred)

get_app()
db = firestore.client()

def handler(request, *args, **kwargs):
    try:
        if request.method != 'POST':
            return json_response({ "message": "Only POST allowed." }, 405)

        body = request.json
        user_id = str(body.get("id"))
        name = body.get("name")
        username = body.get("username")

        if not user_id:
            return json_response({ "error": "Missing user ID" }, 400)

        db.collection("users").document(user_id).set({
            "name": name,
            "username": username
        }, merge=True)

        return json_response({ "message": f"Saved {name}" })
    
    except Exception as e:
        return json_response({ "error": str(e) }, 500)

def json_response(data, status=200):
    return {
        "statusCode": status,
        "headers": { "Content-Type": "application/json" },
        "body": json.dumps(data)
    }
