from pymongo import MongoClient
from passlib.context import CryptContext
import os

MONGO_URI = os.getenv("MONGO_URI", "mongodb://localhost:27017/tododb")
mongo_client = MongoClient(MONGO_URI)
db = mongo_client.get_database()
user_collection = db.users  # New collection for users

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

def get_user_by_username(username: str):
    return user_collection.find_one({"username": username})

def create_user(username: str, password: str):
    hashed_password = pwd_context.hash(password)
    user = {"username": username, "hashed_password": hashed_password}
    user_collection.insert_one(user)

def verify_password(plain_password, hashed_password):
    return pwd_context.verify(plain_password, hashed_password)
