from KVerse_database_system.db_utils import retrieve_document, update_document, delete_document,upsert_document
from KVerse_backend_chat.session_handler import SessionHandler
from KVerse_metrics_processor.metrics_utils import process_metrics
from KVerse_quiz_processor.quiz_utils import process_subject_response
from KVerse_database_system.db_config import db_client
from time import time
from datetime import datetime
import random

class UserHandler():
    def __init__(self, collection_name: str = "User_Document"):
        self.collection_name = collection_name
        self.users = dict()

    def create_user(self, user_id: str, user_data: dict) -> dict:
        """
        Create a new user document in the database.
        Args:
            user_id (str): The ID of the user.
            user_data (dict): The data of the user to be stored.
        Returns:
            dict: The created user document.
        """
        user_document = {
            "User_Id": user_id,
            **user_data
        }
        #TODO : create user
        self.users[user_id] = user_document  # Store in memory for quick access 

        return user_document
    
    def load_user(self, user_id: str, load_session_handler: bool = False) -> dict:
        """
        Load a user document from the database.
        Args:
            user_id (str): The ID of the user.
        Returns:
            dict: The user document if found, otherwise raises an exception.
        """
        user_document = dict()
        if self.users.get(user_id):
            return self.users[user_id]["document"]  # Return from memory if available
        else:
            try:
                user_document_list = retrieve_document(collection_name=self.collection_name, 
                                                  primary_key=user_id)
                if user_document_list:
                    user_document = user_document_list[0]  # Get the first document
                    if load_session_handler:
                        self.users[user_id] = {"document" : user_document}  # Store in memory for quick access
                        self.users[user_id]["session"] = SessionHandler(user_id=user_id)
            except ValueError as e:
                raise ValueError(f"User with ID {user_id} does not exist. Exception : {e}")
        return user_document
    
    def get_subjects_for_user(self, user_id: str) -> dict:
        """
        Retrieve subjects for a user.
        Args:
            user_id (str): The ID of the user.
        """
        user_document = self.load_user(user_id=user_id) 
        subjects = retrieve_document(collection_name="Subject_Document",
                                     multiple_keys={"Board": user_document.get("Board", ""),
                                                    "Grade": user_document.get("grade", "")})
        
        sub_list=[]
        context=dict()
        for s in subjects:
            subject_code = s.get("Subject_Code", "")
            subject_name = s.get("Subject_Code", "").split('-')[-1]
            sub_list.append( {            
                "subject_Code": subject_code,
                "subject_Name": subject_name,
                "metadata": {"active":s.get("Active_Status", False),
                             "derivation":s.get("Derivation_Agent", False),
                             "exam":s.get("Exam_Agent", False)}
            })
        context ={
            "user_id": user_id,
            "subjects": sub_list
        }
        return context

    def retrieve_subjects_sessions(self, user_id: str, subject_code: str) -> list:
        """
        Retrieve subjects for a user.
        Args:
            user_id (str): The ID of the user.
        Returns:
            dict: A dictionary containing the subjects for the user.
        """
        #session_dict = dict()
        subjects_dict = self.get_subjects_for_user(user_id) #TODO: update subjects_dict to use user_document
        subjects = [s['subject_Code'] for s in subjects_dict['subjects']]
        finder_dict = {'User_Id': user_id,
                       'Subject_Code': subject_code}
        if subject_code in subjects:
            
            sessions = retrieve_document(collection_name="Session_Document", 
                                         multiple_keys=finder_dict)
        else:
            raise ValueError(f"Subject code {subject_code} not found for user {user_id}.\n {finder_dict}")
        session_list = []
        if sessions:                                                                                    
             for session in sessions:
                session_list.append({
                "session_id": session.get("Session_Id", None),
                "name": session.get("Generated_Name", None),
                "createdAt": session.get("Created_At", None)
            })
        return session_list
    
    def load_session(self, 
                     user_id: str, 
                     subject_code: str|None = None, 
                     session_id: str|None = None, 
                     load_message_handler: bool = False, 
                     get_messages: bool = False) -> tuple:
        """
        Load a session for a user.
        Args:
            user_id (str): The ID of the user.
            subject_code (str): The code of the subject for which the session is created.
            session_id (str): The ID of the session to be loaded.
        Returns:
            tuple: A tuple containing the session ID and the messages of the session.
        """
        if not subject_code and not session_id:#changed
            raise ValueError("Either subject_code or session_id are required to load a session.")
        if user_id not in self.users:
            user_document = self.load_user(user_id, load_session_handler=True)
        self.user_session = self.users[user_id]["session"]
        session_id, session_messages= self.user_session.load_session(subject_code=subject_code,
                                                                      session_id=session_id,
                                                                      load_message_handler=load_message_handler,
                                                                      get_messages=get_messages)
        
        return session_id, session_messages
    
    def get_metrics(self, user_id: str, subject_codes: list) -> dict:
        """
        Retrieve metrics for a user.
        Args:
            user_id (str): The ID of the user.
            subject_codes (str): The list of code of the subjects for which metrics are retrieved.
        Returns:
            dict: A dictionary containing the metrics for the user.
        """
        if user_id not in self.users:
            user_document = self.load_user(user_id, load_session_handler=True)
            
        return(process_metrics(user_id=user_id, 
                                subject_codes=subject_codes))
    


    def update_latest_subject(self,user_id:str,session_id:str):
        if user_id not in self.users:
            user_document = self.load_user(user_id, load_session_handler=True)
        user_document = self.users[user_id]["document"]
        session_handler = self.users[user_id]["session"]
        latest = user_document.get("Latest_Session")
        if not latest or latest is None:
            latest = {"subjects": {},"latest_subject": None}
        session_doc = session_handler.sessions[session_id]["document"]
        subject_code = session_doc.get("Subject_Code")
        generated_name = session_doc.get("Generated_Name")
        if subject_code not in latest["subjects"]:
            latest["subjects"][subject_code] = None
        latest["subjects"][subject_code] = {
                    "Session_Id": session_id,
                    "Generated_Name": generated_name
         }
        latest["latest_subject"] = subject_code
        self.users[user_id]["document"]["Latest_Session"] = latest
        return latest
   
    def update_latest_session_db(self,user_id:str,session_id:str) -> dict|None:
        """
        Persist Latest_Session from memory to DB.
        """

        if user_id not in self.users:
            raise ValueError("User not loaded in memory")

        latest = self.update_latest_subject(
            user_id=user_id,
            session_id=session_id
        )
        if not latest:
            raise ValueError("Latest_Session not initialized")
        query= {"user_id":user_id}
        update_document(
            collection_name=self.collection_name,
            query=query,
            updates={"Latest_Session": latest}
        )
        return latest

    def get_subject_questions(self,user_id:str,n: int, chapters: str, difficulty: str, q_type: str | None = None):
        chptrs = [c.strip() for c in chapters.split(",")]
        docs = retrieve_document(collection_name="Question_Document",
                                 multiple_keys={"Question.metadata.purpose": "subject_quiz",
                                                "Question.metadata.Chapter": {"$in": chptrs},
                                                "Question.metadata.difficulty": difficulty}

                                 )
        if not docs:
            return []
        else:
            docs =[q for q in docs if not q.get("flag",False)]
            questions = random.sample(docs, n)
            quiz_dict = {}
            quiz_dict["quiz_difficulty"] = difficulty
            if q_type is not None:
                quiz_dict["quiz_type"] = q_type
            else:
                quiz_dict["quiz_type"] = "mcq"
            quiz_dict["question"] = questions
            quiz_dict["chapters"] = chapters
            subject_code = questions[0].get("Subject_Code")
            result,quiz_id = process_subject_response(user_id=user_id, quiz_dict=quiz_dict, subject_code=subject_code)
            ques = []
            for q in questions:
                ques.append({
                    "Question_Id": q['Question_Id'],
                    "question": q['Question']['question'],
                    "options": q['Question']['options'],
                    "answer": q['Question']['answer'],
                    "explanation": q['Question']['explanation'],
                    "result": 0.0,
                    "selected_options": [],
                    "review": q.get("review",False),
                })

            return ques,quiz_id



    def remove_user_data(self, user_id:str) -> dict:
        """
        Modify user data in the database.
        Args:
            user_id (str): The ID of the user.
        Returns:
            dict: A dictionary containing the status of the operation.
        """
        returned_data = dict()
        mod = user_id + str(time())
        try:
            ret = update_document(collection_name="Session_Document",
                            query={"User_Id": user_id},
                            updates={"User_Id":mod})
            returned_data['Session_Document'] = ret
        except ValueError as e:
            returned_data['Session_Document'] = f"Failed to update user document: {e}"

        try:
            ret = update_document(collection_name="NFL_Document", 
                                  query={"User_Id": user_id},
                                  updates={"User_Id": mod})
            returned_data['NFL_Document'] = ret
        except ValueError as e:
            returned_data['NFL_Document'] = f"Failed to update user document: {e}"

        try:
            ret = update_document(collection_name="Quiz_Document", 
                                  query={"User_Id": user_id},
                                  updates={"User_Id": mod})
            returned_data['Quiz_Document'] = ret
        except ValueError as e:
            returned_data['Quiz_Document'] = f"Failed to update user document: {e}"
        try:
            ret = update_document(collection_name="Metrics_Document", 
                                  query={"User_Id": user_id},
                                  updates={"User_Id": mod})
            returned_data['Metrics_Document'] = ret
        except ValueError as e:
            returned_data['Metrics_Document'] = f"Failed to delete user document: {e}"

        returned_data['mod'] = mod
        return returned_data

    def remove_user(self, user_id: str) -> dict:
        """
        Remove a user document from the database.
        Args:
            user_id (str): The ID of the user.
        Returns:
            dict: A dictionary containing the status of the operation.
        """
        ret = self.remove_user_data(user_id)
        mod = ret['mod']
        try:
            ret = update_document(collection_name=self.collection_name, 
                                  query={"user_id": user_id},
                                  updates={"user_id": mod})
        except ValueError as e:
            ret = f"Failed to update user document: {e}"

        if user_id in self.users:
            del self.users[user_id]  # Remove from memory

        return {"message": ret, "user_id": user_id}

    def modify_user(self, user_id: str, updates: dict) -> dict:
        """
        Modify user data in the database.
        Args:
            user_id (str): The ID of the user.
            updates (dict): The updates to be applied to the user document.
        Returns:
            dict: A dictionary containing the status of the operation.
        """
        updateable = ["Board", "grade"]
        if not set(updates.keys()).issubset(set(updateable)):
            raise ValueError(f"Invalid updates: {updates}. Only {updateable} are allowed.")
        if user_id in self.users:
            del self.users[user_id]  # Remove from memory to avoid stale data
        ret = self.remove_user_data(user_id)
        updates["Latest_Session"] = None
        try:
            update_document(collection_name=self.collection_name, 
                            query={"user_id": user_id},
                            updates=updates)
        except ValueError as e:
            return {"message": f"Failed to update user document: {e}", "user_id": user_id}
        self.load_user(user_id, load_session_handler=True)  # Reload user to update in-memory cache
        return {"message": "User updated successfully", "user_id": user_id}

    def check_flag_quiz_questions(self,user_id:str,question_id:str,report:str|None=None):
        user_document = self.load_user(user_id = user_id)
        access = user_document["access"]
        if access == "admin":
            result = update_document(collection_name="Question_Document",updates={"review":True,"flag":True},query={"Question_Id":question_id})
            document = {}
            document["User_Id"] = user_document["email"]
            document["Type"] = "Quiz"
            document["Question_Id"] = question_id
            document["Created_At"] = datetime.now()
            if report is not None:
                document["Report"] = report
            res = upsert_document(collection_name="Flag_Document", document=document)
        elif access == "basic":
            updates = dict()
            result = update_document(collection_name="Question_Document",updates={"review":True,"flag":False},query={"Question_Id":question_id})
            collection_name = "Flag_Document"
            try:
                updates["Updated_At"] = datetime.now()
                if report is not None:
                    updates["Report"] = report
                res = update_document(collection_name=collection_name, updates=updates,
                                      query={"User_Id": user_id, "Question_Id": question_id})
            except ValueError:
                document = {}
                document["User_Id"] = user_id
                document["Type"] = "Quiz"
                document["Question_Id"] = question_id
                document["Created_At"] = datetime.now()
                if report is not None:
                    document["Report"] = report
                res = upsert_document(collection_name=collection_name, document=document)
        return result

    def check_flag_question_bank_questions(self,user_id:str,question_bank_id:str,question_number:int,report:str|None=None):
        user_document = self.load_user(user_id=user_id)
        access = user_document["access"]
        if access == "admin":
            result = update_document(collection_name="Question_Bank_Document",query={"Question_Bank_Id":question_bank_id},updates={f"Questions.{question_number}.review":True,f"Questions.{question_number}.flag":True})
            document = {}
            document["User_Id"] = user_document["email"]
            document["Type"] = "Question_Bank"
            document["Question_Id"] = f"{question_bank_id}-[{question_number}]"
            document["Created_At"] = datetime.now()
            if report is not None:
                document["Report"] = report
            res = upsert_document(collection_name="Flag_Document", document=document)
        if access == "basic":
            updates = dict()
            result = update_document(collection_name="Question_Bank_Document",query={"Question_Bank_Id":question_bank_id},updates={f"Questions.{question_number}.review":True,f"Questions.{question_number}.flag":False})
            collection_name = "Flag_Document"
            try:
                updates["Updated_At"] = datetime.now()
                if report is not None:
                    updates["Report"] = report
                res = update_document(collection_name=collection_name, updates=updates,
                                      query={"User_Id": user_id, "Question_Id": f"{question_bank_id}-[{question_number}]"})
            except ValueError:
                document = {}
                document["User_Id"] = user_id
                document["Type"] = "Question_Bank"
                document["Question_Id"] = f"{question_bank_id}-[{question_number}]"
                document["Created_At"] = datetime.now()
                if report is not None:
                    document["Report"] = report
                res = upsert_document(collection_name=collection_name, document=document)
        return result
    # def save_session(self, user_id: str, sessions: SessionHandler) -> dict:
    #     """
    #     Save a session for a user.
    #     Args:
    #         user_id (str): The ID of the user.
    #         sessions (SessionHandler): The session handler containing session data.
    #     Returns:
    #         dict: The updated user document with the new session.
    #     """
    #     if user_id not in self.users:
    #         raise ValueError(f"User with ID {user_id} does not exist.")
    #     user_document = self.users.get(user_id)
    #     user_document["Sessions"] = sessions # type: ignore
    #     try:
    #         update_document(collection_name=self.collection_name, 
    #                         document_id=user_document["_id"], # type: ignore
    #                         updates={"Sessions": sessions})
    #     except ValueError as e:
    #         raise ValueError(f"Failed to update user document: {e}")
    #     del self.users[user_id]  # Remove from memory to avoid stale data
    #     return {"message": "user saved successfully", "user_id": user_id}  # type: ignore
    


    

        
        

