#main.py
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from pymongo import MongoClient
import os
import redis
import pika
import json
import threading
import traceback
import time
import logging
from dependencies import get_current_user
from fastapi import Depends
from fastapi import Depends
from fastapi.security import OAuth2PasswordRequestForm
from auth_utils import get_user_by_username, create_user, verify_password
from jwt_utils import create_access_token

app = FastAPI()

# ----------------- MongoDB Setup -----------------
MONGO_URI = os.getenv("MONGO_URI", "mongodb://localhost:27017/tododb")
mongo_client = MongoClient(MONGO_URI)
db = mongo_client.get_database()
collection = db.tasks

# ----------------- Redis Setup -----------------
redis_host = os.getenv("REDIS_HOST", "localhost")  # Use 'redis' if running in Docker
redis_client = redis.Redis(host=redis_host, port=6379, decode_responses=True)

# ----------------- RabbitMQ Setup -----------------
rabbitmq_host = os.getenv("RABBITMQ_HOST", "localhost")  # Use 'rabbitmq' in Docker

# ----------------- Task Model -----------------
class Task(BaseModel):
    title: str
    description: str = ""

# ----------------- Health Check -----------------
@app.get("/ping")
def ping():
    return {"message": "pong"}

# ----------------- Get All Tasks -----------------
@app.get("/tasks")
def get_tasks(current_user: dict = Depends(get_current_user)):
    cached_tasks = redis_client.get("tasks_cache")
    if cached_tasks:
        print("Returning cached tasks")
        return {"tasks": json.loads(cached_tasks)}

    print("Fetching tasks from MongoDB")
    tasks = list(collection.find({}, {"_id": 0}))
    redis_client.set("tasks_cache", json.dumps(tasks), ex=60)
    return {"tasks": tasks}

# ----------------- Create Task -----------------
@app.post("/tasks", response_model=Task)
def create_task(task: Task, current_user: dict = Depends(get_current_user)):
    task_dict = task.dict()
    result = collection.insert_one(task_dict)
    task_dict["_id"] = str(result.inserted_id)

    # Invalidate Redis cache
    redis_client.delete("tasks_cache")

    # Publish to RabbitMQ
    try:
        connection = pika.BlockingConnection(pika.ConnectionParameters(host=rabbitmq_host))
        channel = connection.channel()
        channel.queue_declare(queue='task_queue', durable=True)

        channel.basic_publish(
            exchange='',
            routing_key='task_queue',
            body=json.dumps(task_dict),
            properties=pika.BasicProperties(delivery_mode=2)  # persistent message
        )
        connection.close()
    except Exception as e:
        print("Failed to publish to RabbitMQ:", e)
        traceback.print_exc()
        raise HTTPException(status_code=500, detail="RabbitMQ failed")

    task_dict.pop("_id", None)  # Hide internal MongoDB ID
    return task_dict

# ----------------- RabbitMQ Consumer -----------------
def callback(ch, method, properties, body):
    print("Received task message:", body.decode())

def rabbitmq_consumer():
    while True:
        try:
            connection = pika.BlockingConnection(pika.ConnectionParameters(host=rabbitmq_host))
            channel = connection.channel()
            channel.queue_declare(queue='task_queue', durable=True)

            channel.basic_consume(
                queue='task_queue',
                on_message_callback=callback,
                auto_ack=True
            )

            print("Started RabbitMQ consumer. Waiting for messages...")
            channel.start_consuming()
        except pika.exceptions.AMQPConnectionError:
            print("RabbitMQ not ready, retrying in 5 seconds...")
            time.sleep(5)
        except Exception as e:
            print(f"RabbitMQ consumer failed: {e}")
            traceback.print_exc()
            time.sleep(5)  # Retry after delay

# ----------------- App Startup Event -----------------
@app.on_event("startup")
def startup_event():
    # Launch RabbitMQ consumer in a background thread
    thread = threading.Thread(target=rabbitmq_consumer, daemon=True)
    thread.start()


class RegisterModel(BaseModel):
    username: str
    password: str

@app.post("/register")
def register_user(user: RegisterModel):
    if get_user_by_username(user.username):
        raise HTTPException(status_code=400, detail="Username already exists")
    create_user(user.username, user.password)
    return {"message": "User registered successfully"}

@app.post("/login")
def login(form_data: OAuth2PasswordRequestForm = Depends()):
    user = get_user_by_username(form_data.username)
    if not user or not verify_password(form_data.password, user["hashed_password"]):
        raise HTTPException(status_code=401, detail="Invalid credentials")

    access_token = create_access_token({"sub": user["username"]})
    return {"access_token": access_token, "token_type": "bearer"}

@app.get("/me")
def read_current_user(current_user: dict = Depends(get_current_user)):
    # This will only work if the token is valid
    return {"username": current_user["username"]}
