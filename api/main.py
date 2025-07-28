import json
import firebase_admin
from firebase_admin import credentials, firestore
import os

# Initialize Firebase Admin SDK only once
if not firebase_admin._apps:
    cred = credentials.Certificate({
        "type": os.environ["FB_TYPE"],
        "project_id": os.environ["FB_PROJECT_ID"],
        "private_key_id": os.environ["FB_PRIVATE_KEY_ID"],
        "private_key": os.environ["FB_PRIVATE_KEY"].replace("\\n", "\n"),
        "client_email": os.environ["FB_CLIENT_EMAIL"],
        "client_id": os.environ["FB_CLIENT_ID"],
        "auth_uri": "https://accounts.google.com/o/oauth2/auth",
        "token_uri": "https://oauth2.googleapis.com/token",
        "auth_provider_x509_cert_url": "https://www.googleapis.com/oauth2/v1/certs",
        "client_x509_cert_url": os.environ["FB_CLIENT_CERT_URL"]
    })
    firebase_admin.initialize_app(cred)

db = firestore.client()

def handler(request, *args, **kwargs):
    if request.method != 'POST':
        return json_response({ "message": "Only POST allowed." }, 405)

    try:
        body = request.json
        user_id = str(body.get("id"))
        name = body.get("name")
        username = body.get("username")

        doc_ref = db.collection("users").document(user_id)
        doc_ref.set({
            "name": name,
            "username": username,
        }, merge=True)

        return json_response({ "message": f"User {name} saved!" })
    except Exception as e:
        return json_response({ "error": str(e) }, 500)

def json_response(data, status=200):
    return {
        "statusCode": status,
        "headers": { "Content-Type": "application/json" },
        "body": json.dumps(data)
    }
