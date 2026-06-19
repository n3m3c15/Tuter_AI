from pymongo import MongoClient
from typing import Dict, Any
from pymongo.errors import ServerSelectionTimeoutError
import certifi
import os
import dotenv

dotenv.load_dotenv()
username = os.getenv('db_username')
password = os.getenv('db_password')
database_name = "kverse-db"

mongo_connection_string = f"mongodb+srv://{username}:{password}@{database_name}.mongocluster.cosmos.azure.com/?tls=true&authMechanism=SCRAM-SHA-256&retrywrites=false&maxIdleTimeMS=120000"       
db_client = MongoClient(mongo_connection_string,tlsCAFile=certifi.where())["Test_3"]

try:
    db_client.command("ping")
    print("MongoDB connection successful!")
except ServerSelectionTimeoutError as err:
    print("MongoDB connection failed:", err)
    
