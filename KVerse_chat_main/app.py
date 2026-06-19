from fastapi import FastAPI, HTTPException, File, Form, Body, Query, Header, UploadFile
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel,Field
from sympy import content

from KVerse_blob_storage.storage_utils import upload_file_to_blob
from KVerse_backend_chat.user_handler import UserHandler
from KVerse_backend_chat.session_handler import SessionHandler
from KVerse_quiz_processor.quiz_utils import get_quiz, add_results_to_quiz ,load_quiz_data
from KVerse_blob_storage.storage_utils import upload_file_to_blob
from KVerse_content_delivery.nfl_delivery import NFL
from KVerse_session_name_processor.name_generator_agent import NameGeneratorAgent
from KVerse_database_system.db_utils import retrieve_document, update_document, upsert_document
from KVerse_database_system.db_config import db_client
import json, os, jwt
from supabase import create_client, Client
from datetime import datetime
from typing import List, Optional, Annotated

user_handler = UserHandler()
class UserRequest(BaseModel):
    user_id: str
app = FastAPI()
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], 
    allow_credentials=True,
    allow_methods=["*"], 
    allow_headers=["*"],  
)

@app.get("/")
def get_home():
    return JSONResponse(content={"message": "Welcome to the KVerse Chat API. Use the /answer_query endpoint to submit queries and images."})
    
@app.get("/get_available_boards")
def get_available_boards():
    try:
        document = retrieve_document("Subject_Document",multiple_keys={"Active_Status": {"$in": [True, False]}})
        active_list = {}
        result = {}
        for doc in document:
            if doc["Board"] == "nfl" or not doc["Active_Status"]:
                continue
            board = doc["Board"]
            grade = doc["Grade"]

            if board not in active_list:
                active_list[board] = []
            if grade not in active_list[board]:
                active_list[board].append(grade)

        for doc in document:
            board = doc["Board"]
            grade = doc["Grade"]
            active = doc["Active_Status"]

            if board == "nfl":
                continue
            if not active and grade in active_list.get(board, []):
                continue

            key = (board, active)
            if key not in result:
                result[key] = {
                    "board": board,
                    "grades": [],
                    "status": active
                }

            if grade not in result[key]["grades"]:
                result[key]["grades"].append(grade)

        final_output = list(result.values())
        return final_output
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
 
@app.get("/subjects")
def get_subjects(user_id: str = Query(...)):
    """
    Endpoint to retrieve subjects for a user.
    Args:
        user_id (str): The ID of the user.
    Returns:
        JSONResponse: A response containing the subjects for the user.
    """
    if not user_id:
        raise HTTPException(status_code=400, detail="User ID is required")
    ret = user_handler.load_user(user_id=user_id)
    if not ret:
        return JSONResponse(status_code=404,content={"status": "error","message": f"User with ID {user_id} does not exist.","data": {}})
    if ret:
        subjects = user_handler.get_subjects_for_user(user_id=user_id)
        if subjects:            
            return JSONResponse(content={
                                    "data":subjects,
                                    "message": "Subjects fetched successfully",
                                    "status": "success"
            }, status_code=200
                                ) # subjects_structure - {"subject_code": "subject_name"}
    return JSONResponse(content={"message": "No subjects found for the user"}, status_code=404)

@app.get("/generate_name")
def generate_name(session_id: str = Query(...)):
    """
    Endpoint to generate a name for a session.
    Args:  
        session_id (str): The ID of the session.
    Returns:
        JSONResponse: A response containing the generated name and a boolean indicating if the name is suitable.
    """
    session_document = retrieve_document(collection_name="Session_Document", primary_key=session_id) #TODO: move to chat utils
    if not session_document:
        return JSONResponse(status_code=404, content={"status": "error", "message": f"Session with ID {session_id} does not exist."})
    session_document = session_document[0]
    generate_name = session_document.get("Generated_Name", "generated_name")
    if generate_name == "generated_name":
        agent_config = json.loads(open("KVerse_agents/name_generator_agent-config.json", "r").read())
        agent_prompt = open("KVerse_agents/name_generator_agent-prompt.txt", "r").read()
        agent_config['system_prompt'] = agent_prompt
        name_generator = NameGeneratorAgent(**agent_config)
        try:
            name_generator.load_history(session_id=session_id)
            ret, temp_history, usage = name_generator(query = "", history = name_generator._history)
            name_generator_ret = json.loads(ret[0])
            if name_generator_ret['useable']:
                ret = update_document(collection_name="Session_Document",
                                    updates={"Generated_Name": name_generator_ret['generated_name']},
                                    query={"Session_Id": session_id})
            return JSONResponse(content={
                "status": "success",
                "data": name_generator_ret,
                "message": f"name generated for session - {session_id}"
            }, status_code=200)
        except ValueError as e:
            return JSONResponse(status_code=400, content={"status": "error", "message": str(e)})
    else:
        return JSONResponse(status_code=400, content={"status": "error", "message": f"Session with ID {session_id} does not require name generation."})

@app.get("/metrics")
def get_metrics(user_id: str = Query(...)):
    """Endpoint to retrieve metrics for a user.
    Args:
        user_id (str): The ID of the user.
    Returns:
        JSONResponse: A response containing the metrics for the user.
    """
    if not user_id:
        raise HTTPException(status_code=400, detail="User ID is required")
    ret = user_handler.load_user(user_id=user_id)
    if not ret:
        return JSONResponse(status_code=404,content={"status": "error","message": f"User with ID {user_id} does not exist.","data": {}})
    if ret:
        subjects = user_handler.get_subjects_for_user(user_id=user_id)
        if subjects:   
            subject_list = [subject_doc["subject_Code"] for subject_doc in subjects['subjects']if subject_doc.get("metadata", {}).get("active") is True]
            try:
                metrics = user_handler.get_metrics(user_id=user_id, subject_codes=subject_list)
                if metrics:
                    return JSONResponse(content={
                        "status": "success",
                        "data": metrics,
                        "message": f"Metrics fetched successfully"
                    }, status_code=200)
                else:
                    return JSONResponse(status_code=404, content={"status": "error", "message": "No metrics found for the user."})
            except ValueError as e:
                return JSONResponse(status_code=404, content={"status": "failed", "message": str(e)})
        else:
            return JSONResponse(content={"message": "No subjects found for the user"}, status_code=404)
    
@app.get("/get_quiz_chapters")  
def get_quiz_chapters(user_id:str,subject_code:str):
    ret = user_handler.load_user(user_id=user_id)
    if not ret:
        return JSONResponse(status_code=404,content={"status": "error","message": f"User with ID {user_id} does not exist.","data": {}})
    try:
        chapters,questions,question_result_map = load_quiz_data(user_id=user_id,subject_code=subject_code)
        result= []
        for chapter_name, subtopics in chapters.items():
            sub_topics_list= []
            for subtopic_name in subtopics:
            #     print("LOOKING FOR:",repr(chapter_name),repr(subtopic_name)
            # )
                subtopic_questions = [
                    q for q in questions
                    if q["Question"]["metadata"]["Chapter"] == chapter_name
                    and q["Question"]["metadata"]["Subchapter"] == subtopic_name
    
                ]
    
                if subtopic_questions:
                    meta_data ={
                        "question":len(subtopic_questions),
                        "correct":sum(question_result_map.get(q["Question_Id"], {}).get("result", 0)for q in subtopic_questions)
                    }
                else:
                    meta_data = None
    
                sub_topics_list.append({
                    "subtopic_name": subtopic_name,
                    "meta_data": meta_data
                })
            result.append({"chapter_name":chapter_name,
                            "sub_topic": sub_topics_list})
        return JSONResponse(status_code=200,content={"status": "success","data": result})
    except Exception as e:
        return HTTPException(status_code=400, detail=str(e))
    
@app.get("/get_revision_questions")
def get_revision_questions(user_id:str,subject_code:str,chapter:str,subtopic_name:str = ''):
    try:
        _,questions,question_result_map = load_quiz_data(user_id=user_id,subject_code=subject_code)
        result =[]
        for q_doc in questions:
            meta = q_doc["Question"]["metadata"]
            
            if subtopic_name == '':
                if meta["Chapter"] == chapter:
                    quiz_info = question_result_map.get(q_doc["Question_Id"], {})

                    result.append({
                        "question": q_doc["Question"]["question"],
                        "options": q_doc["Question"]["options"],
                        "answer": q_doc["Question"]["answer"],
                        "explanation": q_doc["Question"]["explanation"],
                        "selected_options": quiz_info.get("selected_options"),
                        "result": quiz_info.get("result")
                    })
            else:
                if meta["Chapter"] == chapter and meta["Subchapter"] == subtopic_name:
                    quiz_info = question_result_map.get(q_doc["Question_Id"], {})

                    result.append({
                        "question": q_doc["Question"]["question"],
                        "options": q_doc["Question"]["options"],
                        "answer": q_doc["Question"]["answer"],
                        "explanation": q_doc["Question"]["explanation"],
                        "selected_options": quiz_info.get("selected_options"),
                        "result": quiz_info.get("result")
                    })
        return JSONResponse(status_code=200, content={"status": "success", "data":result})
    except Exception as e:
        print(e)
        return HTTPException(status_code=400, detail=str(e))
    
@app.get("/get_latest_session")
def get_latest_session(user_id:str):
    ret = user_handler.load_user(user_id=user_id)
    if not ret:
        return JSONResponse(status_code=404,content={"status": "error","message": f"User with ID {user_id} does not exist.","data": {}})
    try:
        doc = retrieve_document(collection_name="User_Document",primary_key=user_id)
        doc= doc[0]
        latest = doc.get("Latest_Session")
        if not latest:
            return {
                "status":None,
                "data":{"latest_subject": None,
                "session_id": None,
                "generated_name": None}
            }
        latest_subject = latest.get("latest_subject")
        subjects = latest.get("subjects", {})
        s = subjects.get(latest_subject)
        session_id = s.get("Session_Id")
        generated_name = s.get("Generated_Name")
        latest_subject_name = latest_subject.split("-")[-1]
        result = {"latest_subject": latest_subject_name,"latest_subject_code":latest_subject,"session_id": session_id,"generated_name":generated_name}
        return {
            "status":"success",
            "data":result
        }
    except ValueError as e:
        return JSONResponse(status_code=404,content={"status": "failed","data": str(e)})
@app.get("/get_session_revision")
def get_session_revision(user_id: str,session_id:str):
    '''
    endpoint to retrive session wise summary for a user.
    '''
    ret = user_handler.load_user(user_id=user_id)
    if not ret:
        return JSONResponse(status_code=404,content={"status": "error","message": f"User with ID {user_id} does not exist.","data": {}})
    try:
        session_id,message_id = user_handler.load_session(user_id=user_id,session_id=session_id,load_message_handler=True)
        session_handler = user_handler.users[user_id]["session"]
        result = session_handler.generate_revision_sheet(session_id=session_id)
        return JSONResponse(content={"status":"success","data":result},status_code=200)
    except Exception as e:
        return JSONResponse(content={"status":"failed","data":str(e)},status_code=400)

@app.post("/subjects/{subject_code}")
def get_session(subject_code:str,request:UserRequest):
    """
    Endpoint to retrieve a session by session ID.
    Args:
        user_id (str): The ID of the user.
        subject_code (str): subject code to retrieve the session for.
    Returns:
        JSONResponse: A response containing the session details.
    """
    user_id= request.user_id
    ret = user_handler.load_user(user_id=user_id)
    if not ret:
        return JSONResponse(status_code=404,content={"status": "error","message": f"User with ID {user_id} does not exist.","data": {}})
    try:
        session_dict = user_handler.retrieve_subjects_sessions(user_id=user_id, 
                                                               subject_code=subject_code)
    except ValueError as e:
        return JSONResponse(status_code=404,content={"status": "failed","message": str(e)})
    if session_dict:
        return JSONResponse(content={
            "status": "success",
            "data": {
                "sessions": session_dict,
                "total_sessions": len(session_dict)
            },
            "message": "Sessions fetched successfully"
        },
                status_code=200)


@app.post("/subjects/{subject_code}/{session_id}")
def get_messages(subject_code: str, session_id: str,request: UserRequest):
    """
    Endpoint to retrieve messages for a specific session.
    Args:
        user_id (str): The ID of the user.
    """
    user_id= request.user_id
    try:
        ret = user_handler.load_user(user_id=user_id)
    except ValueError as e: 
        raise HTTPException(status_code=404, detail=str(e))
    if ret:
        session_id, messages_data = user_handler.load_session(user_id=user_id,
                                                              subject_code=subject_code,
                                                              session_id=session_id,
                                                              get_messages=True)
        if messages_data:
           formatted_messages = []
           for msg in messages_data:
               sender = msg["Message_Sender"]
               created_at = msg["Created_At"]
               message_content = msg.get("Message", {})
               attachments = message_content.get("Attachments", [])
               block = {
                "type": "text",
                "content": message_content.get("Query") or message_content.get("Solution") or "",
                "images": attachments if attachments else [],
                }
               formatted_messages.append({
                    "message_id": msg["Message_Id"],
                    "sender": sender,
                    "createdAt": created_at,
                    "blocks": [block],
                    "inputs": msg.get("Inputs", "")
                })
        session_state = retrieve_document(collection_name="Session_State_Document", primary_key=session_id)[0]
        if session_state:
            session_state = session_state.get("State", {})
            session_agent = session_state.get("Current_Agent", "init_agent")
        else:
            session_agent = "init_agent"
        return JSONResponse(
                content={
                    "status": "success",
                    "data": {
                        "sessionId": session_id,
                        "messages": formatted_messages,
                        "sessionAgent": session_agent,
                 },
                    "message": "Messages fetched successfully"
        },
        status_code=200)
    return JSONResponse(content={"message": f"User with ID {user_id} does not exist"}, status_code=404)

@app.get("/get_state")
def get_state_agent(user_id: str = Query(...), session_id: str = Query(...)):
    """
    Endpoint to retrieve current agent in session state.
    Args:
        user_id (str): The ID of the user.
        session_id (str): The ID of the session.
    Returns:
        JSONResponse: A response containing the current agent in session state.
    """
    ret = user_handler.load_user(user_id=user_id, load_session_handler=True)
    if not ret:
        return JSONResponse(content={"message": f"User with ID {user_id} does not exist"}, status_code=404)
    if ret:
        session_state = retrieve_document(collection_name="Session_State_Document", primary_key=session_id)[0]
        if session_state:
            session_state = session_state.get("State", {})
            current_agent = session_state.get("Current_Agent", "init_agent")
            return JSONResponse(content={"sessionAgent": current_agent}, status_code=200)
        else:
            return JSONResponse(content={"sessionAgent":"init_agent"},status_code=200 )
    
        
@app.post("/create_session")
def create_session(user_id: str = Body(...), subject_code: str = Body(...)):
    """
    Endpoint to create a new session.
    Args:
        user_id (str): The ID of the user.
        subject_code (str): The subject code for the session.
    Returns:
        JSONResponse: A response containing the created session details.
    """
   
    ret = user_handler.load_user(user_id=user_id, load_session_handler=True)
    if not ret:
        return JSONResponse(content={"message": f"User with ID {user_id} does not exist"}, status_code=404)
    if ret:
        session_id, messages_data = user_handler.load_session(user_id=user_id,
                                                              subject_code=subject_code)
        return JSONResponse(content={"session_id": session_id}, status_code=200)
    
    return JSONResponse(content={"message": f"User with ID {user_id} does not exist"}, status_code=404)

@app.post("/upload_file")
async def upload_file(user_id: str = Form(...),session_id: str = Form(...), file: UploadFile = File(...)):
    """
    End point to upload a file toblob storage
    """
    t1=datetime.now()
    ret = user_handler.load_user(user_id=user_id, load_session_handler=True)
    if not ret:
        return JSONResponse(content={"message": f"User with ID {user_id} does not exist"}, status_code=404)
    blob_url, mime_type,file_name = upload_file_to_blob(upload_file=file,user_id=user_id,session_id=session_id)
    print("time:",datetime.now()-t1)
    return JSONResponse(content={"blob_url": blob_url, "mime_type": mime_type, "file_name": file_name}, status_code=200)

@app.post("/get_bounding_boxes")
def get_bounding_boxes(user_id: str = Form(...),
                       session_id: str = Form(...), 
                       attachments_json: str = Form(...)):
    """
    Endpoint to get bounding boxes from a question paper image.
    Args:
        user_id (str): The ID of the user.
        subject_code (str): The subject code.
        question_paper_image (UploadFile): The question paper image file.
        """
    ret = user_handler.load_user(user_id=user_id, load_session_handler=True)
    if not ret:
        return JSONResponse(content={"message": f"User with ID {user_id} does not exist"}, status_code=404)
    if ret:
        session_id, messages_data = user_handler.load_session(user_id=user_id,
                                                              session_id=session_id,
                                                              load_message_handler=True)
        
        session_handler = user_handler.users[user_id]["session"]
        question_paper_image: List[dict] = json.loads(attachments_json) if attachments_json else []

        image_url = question_paper_image[0]['blob_url'] if question_paper_image else None
        if not image_url:
            raise HTTPException(status_code=400, detail="Question paper image URL is required")
        try:
            bounding_boxes, save_urls, image_content = session_handler.get_bbox(question_paper_image_url=image_url,
                                                                session_id=session_id)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))
        
    return  {
                "sid": session_id,
                "data": 
                    {
                        "bounding_boxes":bounding_boxes,
                        "image":image_content,
                        "diag_urls":save_urls,
                    }
                              
            }

@app.post("/extract_questions")
def extract_questions(user_id: str = Form(...),
                      session_id: str = Form(...),
                      query: str = Form(None),
                      attachments_json: str = Form(...),
                      detections: str = Form(...),      # Changed to str
                      diag_urls: str = Form(...)):      # Changed to str
    """
    Endpoint to extract questions from a question paper image.
    """
    ret = user_handler.load_user(user_id=user_id, load_session_handler=True)
    if not ret:
        return JSONResponse(content={"message": f"User with ID {user_id} does not exist"}, status_code=404)
    if ret:
        session_id, messages_data = user_handler.load_session(user_id=user_id,
                                                              session_id=session_id,
                                                              load_message_handler=True)
        
        session_handler = user_handler.users[user_id]["session"]
        question_paper_image: List[dict] = json.loads(attachments_json) if attachments_json else []
        
        # Parse the JSON strings
        detections_list = json.loads(detections) if detections else []
        diag_urls_list =diag_urls if diag_urls else []

        try:
            response = session_handler.scan_image(session_id=session_id, 
                                                   query=query, 
                                                   image_url=question_paper_image,
                                                   detections=detections_list,
                                                   save_urls=diag_urls_list)
            if isinstance(response, dict) and "response" in response:
                answer_text = response["response"]
            else:
                answer_text = response
            return {
                "sid": session_id,
                "blocks": [
                    {
                        "type": "questions",
                        "content": answer_text,
                        "images": question_paper_image,
                        "streaming": True
                    }
                ] 
            }
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))

    
@app.post("/generate_subject_quiz")
def generate_subject_quiz(user_id:str=Body(...),n: int=Body(...), chapters: str=Body(...), difficulty: str=Body(...), q_type: str | None = Body(None)):
    """
    Endpoint to generate quiz for selected chapter/chapter
    """
    ret = user_handler.load_user(user_id=user_id, load_session_handler=True)
    if not ret:
        return JSONResponse(status_code=404,content={"status": "error","message": f"User with ID {user_id} does not exist.","data": {}})
    try:
        result,quiz_id = user_handler.get_subject_questions(user_id=user_id,n = n,chapters=chapters,difficulty=difficulty)
        return JSONResponse(content={
            "status": "success",
            "type":"quiz",
            "data": {
                "quiz_id":quiz_id,
                "content":result
            }
        }, status_code=200)
    except Exception as e:
        return JSONResponse(content={"status": "failed", "data": str(e)}, status_code=400)

@app.post("/update_subject_quiz")
def update_subject_quiz(user_id : str = Form(...), quiz_id: str =Form(...), result_json:str=Form(...)):
    ret = user_handler.load_user(user_id=user_id)
    if not ret:
        return JSONResponse(content={"message": f"User with ID {user_id} does not exist"}, status_code=404)
    try:
       result_returned: List[dict] = json.loads(result_json)
       response = add_results_to_quiz(result_list=result_returned,
                                   quiz_id=quiz_id)
       return JSONResponse(content={"status": "success", "data": response}, status_code=200)
    except Exception as e:
        return JSONResponse(content={"status": "failed", "data": str(e)}, status_code=400)


@app.post("/generate_quiz")
async def generate_quiz(user_id: str=Form(...), session_id: str=Form(...)):

    """
    Generate a quiz for a given user, subject, and session.
    Example:
    POST /generate_quiz?user_id=123&subject_code=cbse-12-physics&session_id=abc123
    """
    ret = user_handler.load_user(user_id=user_id)
    if not ret:
        return JSONResponse(content={"message": f"User with ID {user_id} does not exist"}, status_code=404)
    if ret:
        session_id, messages_data = user_handler.load_session(user_id=user_id,
                                                              session_id=session_id,
                                                              load_message_handler=True)
        
        session_handler = user_handler.users[user_id]["session"]
        try:
            ret, quiz_id = session_handler.generate_quiz(session_id=session_id)
            if ret:
                Flag = True
            else:
                Flag = False
            return {
                "sid":session_id,
                "type":"Quiz",
                "content":{
                           "quiz_ids": quiz_id,
                           "flag": Flag,
                        },
                    } 

        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))

@app.post("/get_quiz_questions")
def get_quiz_questions(user_id : str = Form(...), session_id:str =Form(...), quiz_id: str =Form(...)):
    ret = user_handler.load_user(user_id=user_id)
    if not ret:
        return JSONResponse(content={"message": f"User with ID {user_id} does not exist"}, status_code=404)
    try:
        content=get_quiz(quiz_id=quiz_id, session_id=session_id)
        return{
                "sid":session_id,
                "content":content
                    } 
        
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
        
@app.post("/update_quiz_score")
def update_quiz(user_id : str = Form(...), session_id:str =Form(...), quiz_id: str =Form(...), result_json:str=Form(...)):
    ret= user_handler.load_user(user_id=user_id)
    if not ret:
        return JSONResponse(content={"message": f"User with ID {user_id} does not exist"}, status_code=404)
    else:
        session_id, messages_data = user_handler.load_session(user_id=user_id,
                                                              session_id=session_id,
                                                              load_message_handler=True)
        
        session_handler = user_handler.users[user_id]["session"].sessions[session_id]
    try:
       result_returned: List[dict] = json.loads(result_json) 
       metrics_calculator = session_handler['metrics_calculator']
       response = add_results_to_quiz(result_list=result_returned,
                                      quiz_id=quiz_id)
       metrics_calculator(quiz_id=quiz_id)
       return{
           "sid":session_id,
           "block":[
               {
                   "type":"quiz",
                   "content":response
               }
           ]
       }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    
@app.post("/answer_query")
def answer_query(user_id: str = Form(...), 
                 session_id: str =Form (...), 
                 query: str = Form(...), 
                 answer_type: str = Form(...), 
                 attachments_json: Optional[str] = Form(None),
                 addon : Optional[bool] = Form(None)):
    """
    Endpoint to answer a query with optional attachments.
    Args:
        user_id (str): The ID of the user.
        session_id (str): The ID of the session.
        query (str): The query to be answered.
        attachments (list, optional): List of attachments related to the query.
        created_at (str): Timestamp of when the query was created.
        answer_type (str): Type of answer to be provided (e.g., derivation, exam, eli5, irl, complex).
        addon (bool, optional): Additional information or context for the query.
    Returns:
        JSONResponse: A response containing the answer to the query.
    """
    if answer_type == "derivation":
        handoff_agent = "derivation_agent"
    elif answer_type == "exam":
        handoff_agent = "exam_agent"
    else:
        handoff_agent = "complex_agent"

    t1 = datetime.now()
    try:
        ret = user_handler.load_user(user_id=user_id, load_session_handler=True)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    if ret:
        session_id, messages_data = user_handler.load_session(user_id=user_id,
                                                              session_id=session_id,
                                                              load_message_handler=True)
        
        session_handler = user_handler.users[user_id]["session"]
        user_handler.update_latest_session_db(user_id=user_id,session_id=session_id)
        attachments: List[dict] = json.loads(attachments_json) if attachments_json else []
        try:
            response = session_handler.get_answer(session_id=session_id, 
                                                  query=query, 
                                                  attachments=attachments, 
                                                  handoff_agent = handoff_agent,
                                                  addon=addon,
                                                  query_type='regular')
           
            quiz_flag = response.get("quiz_flag", False)
            answer_text = response.get("response", "")
            print("time taken:",datetime.now()-t1)
            return {
                "sid": session_id,
                "message_id": response.get("reply_id"),
                "blocks": [
                    { 
                        "type": "text",
                        "content":answer_text,
                        "images":attachments if attachments else [],
                        "streaming":True
                    }],
                "generate_quiz":quiz_flag           
            }
            # return JSONResponse(content=simplified_response, status_code=200)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))
        
def verify_supabase_token(token: str):
    print("Token Recieved for Verification")
    if not token:
        raise HTTPException(status_code=400, detail="Token is missing")

    try:
        print("Verification Started")
        response = supabase.auth.get_user(token)
        if not response:
            raise HTTPException(status_code=401, detail="Invalid or expired token")
        print("Response Recieved : ", response)
    except Exception as e:
        print(e)
        raise HTTPException(status_code=401, detail="Invalid or expired token")

    if not response.user:
        raise HTTPException(status_code=401, detail="Invalid or expired token")

    return  response.user.id, response.user.email


MONGO_URI = os.getenv("MONGO_URI")
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_KEY")
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY) #type: ignore

users_collection = db_client["User_Document"]

PHONE_NUMBER = r"^\d{10}$"

class Address(BaseModel):
    h_no: str = Field(...)
    floor_house_name: str = Field(...)
    street: str = Field(...)
    pin_code: str = Field(...)

class UserRegistration(BaseModel):
    firstName: str = Field(...)
    lastName: str = Field(...)
    email: str = Field(...)
    phoneNumber: str = Field( ...)
    dateOfBirth: str = Field(...)
    gender: str = Field(...)
    state: str = Field(...)
    city: str = Field(...)
    guardianName: str = Field(...)
    schoolName: str = Field(...)
    board: str = Field(...)
    grade: str = Field(...) 
    access: str = Field("basic")


@app.post("/check-user")
async def check_user(authorization: str= Header(None)):
    if not authorization:
        raise HTTPException(status_code=401, detail="Authorization header missing")
    try:
        print(authorization)
        token = authorization.split(" ")[1]
    except IndexError:
        raise HTTPException(status_code=401, detail="Invalid authorization header format")
    decoded = jwt.decode(token, options={"verify_signature": False}) 
    print("Recieved Token : ", decoded)
    user_id, email = verify_supabase_token(token)
    print("User Details : ", user_id, email)
    existing_user = users_collection.find_one({"user_id": user_id})
    print("Exisint User", existing_user)
    if existing_user:
        existing_user["_id"] = str(existing_user["_id"])
    if existing_user:
        return {
                "message": "Existing user found",
                "status": "existing",
                "user_data": existing_user
            }
    else:
            return {
                "message": "User not found",
                "status": "new_user"
            }


    
@app.post("/add-user")
async def add_user(user: UserRegistration,authorization: str = Header(None)):

    if not authorization:
        raise HTTPException(status_code=401, detail="Authorization header missing")

    try:
        token = authorization.split(" ")[1]
    except IndexError:
        raise HTTPException(status_code=401, detail="Invalid authorization header format")

    user_id, email = verify_supabase_token(token)
    existing_user = users_collection.find_one({"user_id": user_id})
    print("User ID being Populated : ", user_id, existing_user)
    if existing_user:
        existing_user["_id"] = str(existing_user["_id"])
        return {
            "message": "User already exists",
            "status": "existing",
            "user_data": existing_user
        }
      
    new_user = {
        "user_id": user_id,
        "first_name": user.firstName,
        "last_name": user.lastName,
        "email":email,
        "phone_number":user.phoneNumber,
        "date_of_birth": user.dateOfBirth,
        "gender": user.gender,
        "state": user.state,
        "city": user.city,
        "Parent/Guardian Name": user.guardianName,
        "school_name": user.schoolName,
        "Board": user.board,
        "grade": user.grade,
        "Created_At": str(datetime.now()),
        "access": "basic"
    }
    
    result = users_collection.update_one(
        {"user_id": user_id},        
        {"$set": new_user},           
        upsert=True                    
    )
    existing_user = users_collection.find_one({"user_id": user_id})
    if not existing_user:
        raise HTTPException(status_code=500, detail="Failed to create user")
    existing_user["_id"] = str(existing_user["_id"])
    return {
                "message": "New user added",
                "status": "new_user",
                "user_data": existing_user
            }

@app.get("/get-user")
async def get_user(authorization: str = Header(None)):
    if not authorization:
        raise HTTPException(status_code=401, detail="Authorization header missing")

    try:
        token = authorization.split(" ")[1]
    except IndexError:
        raise HTTPException(status_code=401, detail="Invalid authorization header format")

    user_id, email = verify_supabase_token(token)
    print("Fetching user details for:", user_id, email)
    
    existing_user = users_collection.find_one({"user_id": user_id})
    
    if not existing_user:
        raise HTTPException(status_code=404, detail="User not found in database")
    
    # Convert ObjectId to string for JSON serialization
    existing_user["_id"] = str(existing_user["_id"])
    
    return {
        "message": "User details retrieved successfully",
        "status": "success",
        "user_data": existing_user
    }


@app.delete("/remove-user")
async def remove_user(email: str = Query(...)):
    result = users_collection.delete_one({"email": email})

    if result.deleted_count == 0:
        return {
            "message": "User not found",
            "status": "no_user"
        }

    return {
        "message": "User removed successfully",
        "status": "removed",
        "email": email
    }
@app.delete("/delete_user")
async def delete_user(user_id:str):
    ret = user_handler.load_user(user_id=user_id)
    if not ret:
        return JSONResponse(status_code=404, content={"status": "error","message": "User does not exist."})
    try:
        result = user_handler.remove_user(user_id=user_id)
        return JSONResponse(status_code=200,content=result)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.post("/modify_user_information")
def update_user(user_id:str = Body(...),updates:dict = Body(...)):
    ret = user_handler.load_user(user_id=user_id)
    if not ret:
        return JSONResponse(status_code=404, content={"status": "error", "message": "User does not exist."})
    try:
        result = user_handler.modify_user(user_id=user_id,updates=updates)
        return JSONResponse(status_code=200, content=result)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
@app.get("/nfl_modules")
def get_nfl_modules(user_id:str):
    '''
    To get the List of NFL moduels for the user
    '''
    if not user_id:
        raise HTTPException(status_code=400, detail="User ID is required")
    ret = user_handler.load_user(user_id=user_id)
    if not ret:
        return JSONResponse(status_code=404,content={"status": "error","message": f"User with ID {user_id} does not exist."})
    
    nfl_handler = NFL(user_id= user_id)
    try:
        result = nfl_handler.get_modules()
    except ValueError as e:
        return JSONResponse(status_code=400,content={"status":"error","messager":str(e)})
    
    return {
        "status":"success",
        "data": result
    }

@app.get("/get_nfl_chapters")
def get_chapters(user_id: str, subject_code: str):
    '''
    To get the List of NFL moduels for the user
    '''
    if not user_id:
        raise HTTPException(status_code=400, detail="User ID is required")
    ret = user_handler.load_user(user_id=user_id)
    if not ret:
        return JSONResponse(status_code=404,content={"status": "error","message": f"User with ID {user_id} does not exist."})
    
    nfl_handler = NFL(user_id= user_id,subject_code= subject_code)
    try:
        result = nfl_handler.get_module_progress()
    except ValueError as e:
        return JSONResponse(status_code=400,content={"status":"error","messager":str(e)})
    
    return {
        "status":"success",
        "data": result
    }

@app.get("/nfl_remaining/{module_name}/{chapter_name}")
def get_rem_topics(user_id: str, subject_code: str, chapter_name: str):
    '''
    To get the remaining topics in a chapter of a module for the user
    '''
    if not user_id:
        raise HTTPException(status_code=400, detail="User ID is required")
    ret = user_handler.load_user(user_id=user_id)
    if not ret:
        return JSONResponse(status_code=404,content={"status": "error","message": f"User with ID {user_id} does not exist."})
    
    nfl_handler = NFL(user_id= user_id,subject_code= subject_code)
    try:
        result = nfl_handler.get_remaining_topics(chapter_name= chapter_name)
    except ValueError as e:
        return JSONResponse(status_code=400,content={"status":"error","messager":str(e)})
    
    return {
        "status":"success",
        "data": result
    }
    
@app.post("/nfl_progress")
def add_progress(user_id:str, subject_code:str, chapter:str=Body(...),topics:str=Body(...)):
    """
    To add progress of the user in a chapter of module
    """
    if not user_id:
        raise HTTPException(status_code=400, detail="User ID is required")
    ret = user_handler.load_user(user_id=user_id)
    if not ret:
        return JSONResponse(status_code=404,content={"status": "error","message": f"User with ID {user_id} does not exist."})
    
    nfl_handler = NFL(user_id= user_id,subject_code= subject_code)
    try:
        result = nfl_handler.add_progress(chapter= chapter, topic= topics)
    except ValueError as e:
        return JSONResponse(status_code=400,content={"status":"error","messager":str(e)})
    
    return {
        "status":"success",
        "data": result
    }

@app.get("/get_question_bank_chapters")
def get_question_bank_chapters(subject_code: str):
    """
    To get the List of chapters in the question bank for the user.
    """
    ret = retrieve_document(collection_name="Question_Bank_Document", multiple_keys={"Subject_Code": subject_code})
    if not ret:
        return JSONResponse(status_code=404, content={"status": "error", "message": f"Question Bank for subject {subject_code} does not exist."})
    chapters = [doc["Chapter_Name"] for doc in ret]
    chapters = sorted(
        chapters,
        key=lambda x: (0, int(x.split("-")[1]))
        if len(x.split("-")) > 1 and x.split("-")[1].isdigit()
        else (1, 0)
    )
    return JSONResponse(content={
        "status": "success",
        "data": chapters,
        "message": f"Chapters fetched successfully for subject {subject_code}"
    }, status_code=200)

@app.get("/get_question_bank_questions")
def get_question_bank_questions(subject_code: str, chapter_name: str):
    """
    To get the List of questions in a chapter of the question bank for the user.
    """
    ret = retrieve_document(collection_name="Question_Bank_Document", 
                            multiple_keys={"Subject_Code": subject_code, "Chapter_Name": chapter_name})
    if not ret:
        return JSONResponse(status_code=404, content={"status": "error", "message": f"Questions for chapter {chapter_name} in subject {subject_code} do not exist."})
    
    questions = ret[0].get("Questions", [])
    for i,q in enumerate(questions,start =0):
        q["index"] = i
    #questions = [q for q in questions if not q.get("flag", False)]
    payload = [obj for obj in questions if obj['Answer']['answer'] and obj['Answer']['explanation'] and not obj.get("flag", False)]
    return JSONResponse(content={
        "status": "success",
        "question_bank_id":ret[0].get("Question_Bank_Id"),
        "data": payload,
        "message": f"Questions fetched successfully for chapter {chapter_name} in subject {subject_code}"
    }, status_code=200)

@app.post("/feedback_form")
def feedback_form(user_id:str =Form(...),feedback:str=Form(...), urls: Optional[str] = Form(None)):
    ret = user_handler.load_user(user_id=user_id)
    if not ret:
        return JSONResponse(content={"message": f"User with ID {user_id} does not exist"}, status_code=404)
    try:
        collection_name = "Feedback_Document"
        document = {}
        document["User_Id"] = user_id
        document["Feedback"] = feedback
        document["Created_At"] = datetime.now()
        if urls:
            document["Images"]= json.loads(urls)
        result = upsert_document(collection_name=collection_name, document=document)
        return JSONResponse(content={"status": "success", "data": "Your Feedback is submitted"}, status_code=200)
    except ValueError as e:
        return JSONResponse(status_code=400,content={"status":"error","message":str(e)})
        
@app.post("/chat_feedback")
def chat_feedback(message_id:str=Body(...),flag:bool =Body(...)):
    try:
        result  = update_document(collection_name="Message_Document", updates={"Message.Feedback":flag},query={"Message_Id":message_id})
        return JSONResponse(status_code=200,content={"status": "success", "data": "Your Feedback is updated"})
    except ValueError as e:
        return JSONResponse(status_code=400,content={"status":"error","message":str(e)})

@app.post("/flag_quiz_questions")
def flag_questions(user_id:str =Body(...),question_id:str =Body(...),report:Optional[str] = Body(default=None)):
    ret = user_handler.load_user(user_id=user_id)
    if not ret:
        return JSONResponse(content={"message": f"User with ID {user_id} does not exist"}, status_code=404)
    try:
        result = user_handler.check_flag_quiz_questions(user_id=user_id, question_id=question_id,report=report)
        return JSONResponse(content={"status": "success", "data": "Your Feedback has submitted"}, status_code=200)
    except ValueError as e:
        return JSONResponse(status_code=400,content={"status":"error","data":str(e)})

@app.post("/flag_question_bank_questions")
def flag_question_bank_questions(user_id:str =Body(...),question_bank_id:str =Body(...),question_index:int =Body(...),report:Optional[str] = Body(default=None)):
    ret = user_handler.load_user(user_id=user_id)
    if not ret:
        return JSONResponse(content={"message": f"User with ID {user_id} does not exist"}, status_code=404)
    try:
        result = user_handler.check_flag_question_bank_questions(user_id=user_id,question_bank_id=question_bank_id,question_number = question_index,report=report)
        return JSONResponse(content={"status": "success", "data": "Your Feedback has submitted"}, status_code=200)
    except ValueError as e:
        return JSONResponse(status_code=400, content={"status": "error", "data": str(e)})
