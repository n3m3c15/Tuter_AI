from KVerse_database_system.db_config import db_client
from KVerse_database_system.db_utils import retrieve_document
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware


app = FastAPI()
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], 
    allow_credentials=True,
    allow_methods=["*"], 
    allow_headers=["*"],  
)


@app.get("/users")
def get_all_users():
    doc = db_client["User_Document"]
    cursor = doc.find({}, {"_id": 0, "user_id": 1})
    all_users = [item["user_id"] for item in cursor]  
    return all_users

@app.get("/subjects/{user_id}")
def get_subjects_by_user(user_id:str):
    user_document = retrieve_document(collection_name="User_Document",primary_key=user_id)
    user_doc= user_document[0]
    board = user_doc.get("Board").lower()
    grade = user_doc.get("grade")
    subjects = retrieve_document(collection_name="Subject_Document",multiple_keys={"Board":board,"Grade":grade})
    sub_list=[]
    for s in subjects:
        subject_code = s.get("Subject_Code")
        subject_name = s.get("Subject_Code", "").split('-')[-1]
        sub_list.append( {            
            "subject_name": subject_name,
            "subject_code": subject_code
        })

    return sub_list

@app.get("/sessions/{user_id}/{subject_code}")
def get_all_sessions_by_user(user_id:str, subject_code:str):
    session_doc = retrieve_document(collection_name="Session_Document",multiple_keys={"User_Id":user_id,"Subject_Code":subject_code})
    session_list=[]
    for s in session_doc:
        session_id = s.get("Session_Id")
        session_name = s.get("Generated_Name")
        session_created_at = s.get("Created_At") 
        session_list.append({
            "session_id": session_id,
            "name": session_name,
            "createdAt": session_created_at
        })
    return session_list

@app.get("/chats/{user_id}/{session_id}")
def get_all_chats(user_id:str,session_id:str):
    message_data = retrieve_document(collection_name="Message_Document",multiple_keys={"Session_Id":session_id})
    message_data = sorted(message_data,key=lambda x: x["Created_At"])
    #print(f"get:{message_data}")
    formatted_messages = []
    for msg in message_data:
        sender = "bot" if msg.get("Message", {}).get("Solution") else "user"
        created_at = msg["Created_At"]
        message_content = msg.get("Message", {})
        attachments = message_content.get("Attachments", [])
        block = {
        "content": message_content.get("Query") or message_content.get("Solution") or "",
        "images": attachments if attachments else [],
    }
        formatted_messages.append({
            "sender": sender,
            "createdAt": created_at,
            "blocks": [block],
            "inputs": msg.get("Inputs", "")
    })
    return formatted_messages
