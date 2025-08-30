from flask import Flask
app = Flask(__name__)

@app.get("/")
def home():
    return "ok", 200

@app.get("/health")
def health():
    return {"status":"up"}, 200
