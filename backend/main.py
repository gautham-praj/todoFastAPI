from fastapi import FastAPI
from pymongo import MongoClient
import os

app = FastAPI()

MONGO_URI = os.getenv("MONGO_URI", "mongodb://localhost:27017/tododb")
client = MongoClient(MONGO_URI)
db = client.get_database()

@app.get("/ping")
def ping():
    return {"message": "pong"}

@app.get("/tasks")
def get_tasks():
    tasks = list(db.tasks.find({}, {"_id": 0}))
    return {"tasks": tasks}
