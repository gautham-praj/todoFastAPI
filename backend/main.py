from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from pymongo import MongoClient
import os
import redis
import pika
import json
import threading


app = FastAPI()

# MongoDB setup
MONGO_URI = os.getenv("MONGO_URI", "mongodb://localhost:27017/tododb")
client = MongoClient(MONGO_URI)
db = client.get_database()

# Redis setup
redis_host = os.getenv("REDIS_HOST", "localhost")
redis_client = redis.Redis(host=redis_host, port=6379, decode_responses=True)

# RabbitMQ setup
rabbitmq_host = os.getenv("RABBITMQ_HOST", "localhost")
connection = pika.BlockingConnection(pika.ConnectionParameters(host=rabbitmq_host))
channel = connection.channel()
channel.queue_declare(queue='task_queue', durable=True)

class Task(BaseModel):
    title: str
    description: str = ""

@app.get("/ping")
def ping():
    return {"message": "pong"}

@app.get("/tasks")
def get_tasks():
    tasks = list(db.tasks.find({}, {"_id": 0}))
    return {"tasks": tasks}

import logging

@app.post("/tasks")
def create_task(task: Task):
    try:
        task_dict = task.dict()
        db.tasks.insert_one(task_dict)

        redis_client.incr("tasks_created")

        message = json.dumps(task_dict)
        channel.basic_publish(
            exchange='',
            routing_key='task_queue',
            body=message,
            properties=pika.BasicProperties(
                delivery_mode=2,
            )
        )

        return {"message": "Task created", "task": task_dict}

    except Exception as e:
        logging.error(f"Error creating task: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


def callback(ch, method, properties, body):
    print("Received task message:", body.decode())
    # Here you can add logic to process the task message

def rabbitmq_consumer():
    connection = pika.BlockingConnection(pika.ConnectionParameters(host='rabbitmq'))
    channel = connection.channel()
    channel.queue_declare(queue='task_queue', durable=True)

    channel.basic_consume(queue='task_queue', on_message_callback=callback, auto_ack=True)
    print("Started consuming from RabbitMQ")
    channel.start_consuming()

# Start consumer in a separate thread when FastAPI app starts
@app.on_event("startup")
def startup_event():
    thread = threading.Thread(target=rabbitmq_consumer, daemon=True)
    thread.start()
