from KVerse_database_system.db_config import db_client
from datetime import datetime
from KVerse_database_system.schemas import Session_Document_kwargs
from KVerse_database_system.db_utils import retrieve_document, update_document, structure, upsert_document
from KVerse_chat_main.utils import generate_uid
from KVerse_backend_chat.message_handler import MessageHandler
from pydantic import BaseModel, Field
from KVerse_question_paper_processor.operations import preprocess_image
from KVerse_blob_storage.storage_utils import download_from_url
from KVerse_chat_main.utils import ReturnThread
from KVerse_quiz_processor.quiz_agent import QuizGenerationAgent
from KVerse_quiz_processor.quiz_utils import get_previously_used_message_ids
from typing import Any, Literal
from KVerse_revision_module.RevisionAgent import RevisionAgent
import json, time
from KVerse_metrics_processor.metrics import TopicRetentionScore


class SessionHandler(BaseModel):
    user_id: str = Field(..., description="The ID of the user")
    collection_name: str = Field(default="Session_Document",
                                 description="The name of the collection to store session documents")
    sessions: dict = dict()  # changed

    def __init__(self, **data):  # changed
        super().__init__(**data)

    # self.sessions = dict()

    def create_session(self, subject_code: str | None) -> tuple[str, dict, dict]:
        session_id = generate_uid()
        created_at = datetime.now().isoformat()
        Generated_Name = "generated_name"
        session_document = structure(collection_name=self.collection_name,
                                     schema=Session_Document_kwargs,
                                     Session_Id=session_id,
                                     User_Id=self.user_id,
                                     Generated_Name=Generated_Name,
                                     Subject_Code=subject_code,
                                     created_at=created_at)
        state_document = {
            "Session_Id": session_id,
            "User_Id": self.user_id,
            "State": {
                "Current_Agent": "init_agent"}}
        ret = upsert_document(collection_name="Session_State_Document",
                              document=state_document)
        if not ret:
            raise ValueError("Failed to create session state document.")
        return session_id, session_document, state_document

    def load_session(self,
                     subject_code: str | None = None,
                     session_id: str | None = None,
                     load_message_handler: bool = False,
                     get_messages: bool = False) -> tuple[str, list[Any]]:
        """ Load a session by session ID and subject code.
        Args:
            session_id (str): The ID of the session to load.
            subject_code (str): The subject code associated with the session.
        Returns:
            tuple: A tuple containing the session ID and the messages of the session.
        """
        session_messages = list()
        if session_id and get_messages:
            session_messages = retrieve_document(collection_name="Message_Document",
                                                 multiple_keys={"Session_Id": session_id})
            solution_messages = {message['Message_Id']: message for message in session_messages if
                                 'Query' not in message['Message']}
            messages = dict()
            for message in session_messages:
                if 'Query' in message['Message']:
                    child_message_ids = message.get('Child_Message_Ids', [])
                    if child_message_ids:
                        for child_id in child_message_ids:
                            if child_id in solution_messages:
                                message['Message_Sender'] = 'user'
                                messages[message['Created_At']] = [message]
                                solution_message = solution_messages[child_id]
                                solution_message['Message_Sender'] = 'bot'
                                messages[message['Created_At']].append(solution_message)
            sorted_messages = sorted(messages.items(), key=lambda x: x[0])
            session_messages = list()
            for id, message_pair in sorted_messages:
                session_messages.extend(message_pair)

        if not session_id and subject_code:
            session_id, session_document, state_document = self.create_session(subject_code=subject_code)
        elif not subject_code:
            session_document_list = retrieve_document(collection_name="Session_Document",
                                                      primary_key=session_id)
            state_document_list = retrieve_document(collection_name="Session_State_Document",
                                                    primary_key=session_id)
            if not state_document_list:
                raise ValueError(f"Session state document with ID {session_id} not found.")
            if not session_document_list:
                raise ValueError(f"Session document with ID {session_id} not found.")
            session_document = session_document_list[0]
            subject_code = session_document.get("Subject_Code")
            state_document = state_document_list[0]
            if not subject_code:
                raise ValueError(f"Subject code not found in session document with ID {session_id}.")
        elif not session_id and not subject_code:
            raise ValueError("Either subject_code or session_id are required to load a session.")

        if load_message_handler and session_id:
            subject_document_list = retrieve_document(collection_name="Subject_Document",
                                                      primary_key=subject_code)
            if not subject_document_list:
                raise ValueError(f"Subject document for subject code {subject_code} not found.")
            subject_document = subject_document_list[0]
            config_file = f"KVerse_agents/kverse-india-english-init-config.json"
            agent_config = json.load(open(config_file, 'r'))
            answer_system_prompt = open("KVerse_agents/kverse-india-init-system-prompt.txt", 'r',
                                        encoding='utf-8').read()
            chapter_list = list(subject_document["Chapters"].keys())

            config_file = f"KVerse_agents/kverse-india-english-config.json"
            complex_agent_config = json.load(open(config_file, 'r'))
            complex_answer_system_prompt = open("KVerse_agents/kverse-india-system-prompt.txt", 'r',
                                                encoding='utf-8').read()

            config_file = f"KVerse_agents/kverse-india-english-derivation-config.json"
            derivation_agent_config = json.load(open(config_file, 'r'))
            derivation_answer_system_prompt = open("KVerse_agents/kverse-india-derivation-system-prompt.txt", 'r',
                                                   encoding='utf-8').read()

            answer_system_prompt = answer_system_prompt.format(chapter_list=chapter_list, subject_code=subject_code)
            agent_config['system_prompt'] = answer_system_prompt
            agent_config['subject_code'] = subject_code
            subject_name = subject_code.split("-")[-1]
            board = subject_document.get("Board")
            grade = subject_document.get("Grade")
            agent_config['name'] = f"{subject_name}_answer_agent"
            agent_config[
                'description'] = f"Answering agent for {subject_name} subject of {grade} grade under {board} board."
            agent_config[
                'user_prompt'] = f"you're playing {grade} grade {subject_name} tutor for {board} board students,\n"
            agent_config['history_vector_store_name'] = "kverse-chats"
            agent_config['session_id'] = session_id
            agent_config['user_id'] = self.user_id

            complex_agent_config['name'] = f"{subject_name}_answer_agent_2"
            complex_agent_config[
                'description'] = f"Answering agent for {subject_name} subject of {grade} grade under {board} board."
            complex_agent_config[
                'user_prompt'] = f"you're playing {grade} grade {subject_name} tutor for {board} board students,\n"
            complex_agent_config['subject_code'] = subject_code
            complex_agent_config['system_prompt'] = complex_answer_system_prompt.format(chapter_list=chapter_list,
                                                                                        subject_code=subject_code)
            complex_agent_config['session_id'] = session_id
            complex_agent_config['user_id'] = self.user_id + "_complex"

            derivation_agent_config['name'] = f"{subject_name}_answer_agent_3"
            derivation_agent_config[
                'description'] = f"Answering agent for {subject_name} subject of {grade} grade under {board} board."
            derivation_agent_config[
                'user_prompt'] = f"you're playing {grade} grade {subject_name} tutor for {board} board students,\n"
            derivation_agent_config['subject_code'] = subject_code
            derivation_agent_config['system_prompt'] = derivation_answer_system_prompt.format(chapter_list=chapter_list,
                                                                                              subject_code=subject_code)
            derivation_agent_config['session_id'] = session_id
            derivation_agent_config['user_id'] = self.user_id + "_derivation"

            config_file = f"KVerse_agents/scan_agent-config.json"
            scan_agent_config = json.load(open(config_file, 'r'))
            scan_system_prompt = open("KVerse_agents/scan_agent-system-prompt.txt", 'r').read()
            scan_agent_config['system_prompt'] = scan_system_prompt
            quiz_agent_config = json.load(open("KVerse_agents/quiz_agent-config.json", 'r'))
            quiz_agent_config['system_prompt'] = open("KVerse_agents/quiz_agent-system-prompt.txt", 'r').read()
            quiz_agent_config['session_id'] = session_id
            quiz_agent_config['subject_code'] = subject_code
            quiz_agent_config['user_id'] = self.user_id
            revision_agent_config = json.load(open("KVerse_agents/revision_agent-config.json", 'r'))
            revision_agent_config['system_prompt'] = open("KVerse_agents/revision_agent-system-prompt.txt", 'r').read()
            revision_agent_config['session_id'] = session_id
            revision_agent_config['subject_code'] = subject_code
            revision_agent_config['user_id'] = self.user_id
            self.sessions[session_id] = {'message_handler': MessageHandler(session_id=session_id,  # type:ignore
                                                                           answer_agent_config=agent_config,
                                                                           complex_answer_agent_config=complex_agent_config,
                                                                           derivation_answer_agent_config=derivation_agent_config,
                                                                           session_state=state_document.get('State',
                                                                                                            {}),
                                                                           scan_agent_config=scan_agent_config,
                                                                           chapter_list=chapter_list),
                                         # Initialize the message handler for the session
                                         'document': session_document,
                                         'quiz_agent': QuizGenerationAgent(**quiz_agent_config),
                                         'metrics_calculator': TopicRetentionScore(user_id=self.user_id,
                                                                                   session_id=session_id,
                                                                                   subject_code=subject_code,
                                                                                   strong_threshold_percentage=80,
                                                                                   weak_threshold_percentage=50),
                                         'revision_agent': RevisionAgent(**revision_agent_config)}

            self.sessions[session_id]['message_handler'].load_history()  # Load the chat history for the session
        return session_id, session_messages  # ,generated_name, created_at #type:ignore

    def get_answer(self, 
                   session_id: str, 
                   query: str, 
                   attachments: list | None = None, 
                   handoff_agent="complex_agent",
                   addon: bool | None = None,
                   query_type: str = 'regular') -> dict:
        """
        Get the answer for a query in a session.
        Args:
            session_id (str): The ID of the session.
            query (str): The query to be answered.
            attachments (list|None): Optional list of attachments related to the query.
            query_type (str): Type of the query, e.g., 'regular', 'test_paper, etc.
            handoff_agent (str): The agent to which the query should be handed off.
            addon (str|None): Optional addon to be used with the query.
        Returns:
            dict: The response containing the answer to the query.
        """
        if session_id not in self.sessions:
            raise ValueError(f"Session with ID {session_id} does not exist.")

        message_handler = self.sessions[session_id]['message_handler']
        futures = dict()
        query_id, reply_id = message_handler.answering_agent_space.get_ids().values()
        futures['upsert_query'] = ReturnThread(target=message_handler.upsert_message,
                                               kwargs={'message_id': query_id,
                                                       'message_content': {'Query': query,
                                                                           'Attachments': attachments,
                                                                           'Special_Type': '',
                                                                           'Remark_Flag': '',
                                                                           'Reply_Message_Id': None},
                                                       'sender': self.user_id,
                                                       'inputs': '',
                                                       'child_message_ids': [reply_id]})
        futures['upsert_query'].start()
        if query_type == 'regular':
            futures['reply'] = ReturnThread(target=message_handler.reply_regular_query,
                                            kwargs={'query_id': query_id,
                                                    'reply_id': reply_id,
                                                    'query': query,
                                                    'handoff_agent': handoff_agent,
                                                    'addon': addon,
                                                    'attachments': attachments})
            futures['reply'].start()

            response, usage = futures['reply'].join()  # type:ignore
            if response:
                futures['upsert_reply'] = ReturnThread(target=message_handler.upsert_message,
                                                       kwargs={'message_id': reply_id,
                                                               'message_content': {'Solution': response,
                                                                                   'Feedback': '',
                                                                                   'Remark_Flag': '',
                                                                                   "usage": usage},
                                                               'sender': message_handler.answering_agent.name,
                                                               'inputs': '',
                                                               'root_message_id': query_id,
                                                               'parent_message_id': query_id,
                                                               'child_message_ids': []})
                futures['upsert_reply'].start()
                futures['upsert_query'].join()  # Wait for the query to be upsert
                futures['upsert_reply'].join()
                model1 = self.sessions[session_id]['message_handler'].answering_agent_space.init_agent.model
                model2 = self.sessions[session_id]['message_handler'].answering_agent_space.complex_agent.model
                ret, quiz_ids, previous_used_message_ids, messages = self.sessions[session_id][
                    'quiz_agent'].check_quiz_readiness(model1=model1, model2=model2)
                # print(f"got{response}") # Wait for the reply to be upsert
                return {"response": response,
                        "query_id": query_id,
                        "reply_id": reply_id,
                        "quiz_flag": ret}
            else:
                raise ValueError("No response received from the agent.")
        else:
            raise ValueError(f"Query type '{query_type}' is not supported.")

    def get_bbox(self, question_paper_image_url: str, session_id: str) -> tuple[list | None, list | None, dict | None]:
        """
        Get bounding boxes for the question paper image.
        Args:
            question_paper_image_url (str): The URL of the question paper image.
        Returns:
            list|None: A list of bounding boxes for each question in the image, or None if no boxes are found.
        """
        bounding_boxes, save_files, image_content = None, None, None
        # try:
        #     file_path = download_from_url(question_paper_image_url)
        # except Exception as e:
        #     raise ValueError(f"Error downloading question paper image: {e}")
        try:
            st = time.time()
            bounding_boxes, save_files, image_content = preprocess_image(image_url=question_paper_image_url,
                                                                         session_id=session_id)
            # print("Inference Time : ", time.time()-st)
            # print(f"got1:{bounding_boxes,save_files,image_content}")
        except Exception as e:
            raise ValueError(f"Error processing question paper image: {e}")

        return bounding_boxes, save_files, image_content

    def scan_image(self, session_id, query, image_url, detections, save_urls):
        if session_id not in self.sessions:
            raise ValueError(f"Session with ID {session_id} does not exist.")

        message_handler = self.sessions[session_id]['message_handler']
        futures = dict()
        query_id, reply_id = message_handler.scan_agent.get_ids().values()
        futures['upsert_query'] = ReturnThread(target=message_handler.upsert_message,
                                               kwargs={'message_id': query_id,
                                                       'message_content': {'Query': query,
                                                                           'Attachments': {'image': image_url,
                                                                                           'yolo_detections': detections,
                                                                                           'diagrams_saved_at': save_urls},
                                                                           'Special_Type': '',
                                                                           'Remark_Flag': '',
                                                                           'Reply_Message_Id': None},
                                                       'sender': self.user_id,
                                                       'inputs': '',
                                                       'child_message_ids': [reply_id]})
        futures['upsert_query'].start()
        futures['reply'] = ReturnThread(target=message_handler.reply_scan,
                                        kwargs={'query_id': query_id,
                                                'reply_id': reply_id,
                                                'query': query,
                                                'attachments': image_url,
                                                'detections': detections,
                                                'save_urls': save_urls})
        futures['reply'].start()
        ret, response, usage = futures['reply'].join()  # type:ignore
        if ret:
            futures['upsert_reply'] = ReturnThread(target=message_handler.upsert_message,
                                                   kwargs={'message_id': reply_id,
                                                           'message_content': {'Questions': response,
                                                                               "usage": usage},
                                                           'sender': message_handler.scan_agent.name,
                                                           'inputs': '',
                                                           'root_message_id': query_id,
                                                           'parent_message_id': query_id,
                                                           'child_message_ids': []})
            futures['upsert_reply'].start()
            futures['upsert_query'].join()  # Wait for the query to be upsert
            futures['upsert_reply'].join()  # Wait for the reply to be upsert

            return {"response": response}
        else:
            raise ValueError(
                f"Image redability score provided by LLM is too low for confident OCR; Readability Score Assigned:{response}")

    def generate_quiz(self,
                      session_id: str,
                      quiz_difficulty: Literal["easy", "medium", "hard"] = "medium",
                      question_count: int = 5,
                      question_types: list[Literal["mcq", "short_answer"]] = ["mcq"]) -> tuple[bool, list[str]]:
        """
        Generate a quiz for the session.
        """
        quiz_agent = self.sessions[session_id]['quiz_agent']
        model1 = self.sessions[session_id]['message_handler'].answering_agent_space.init_agent.model
        model2 = self.sessions[session_id]['message_handler'].answering_agent_space.complex_agent.model
        ret, ids, previous_used_message_ids, messages = quiz_agent.check_quiz_readiness(model1=model1, 
                                                                                        model2=model2,)
        if not ret:
            return ret, ids
        query, included_msgs = quiz_agent.build_prompt_from_history(history=messages,
                                                                    previously_used_msgs=previous_used_message_ids,
                                                                    quiz_difficulty=quiz_difficulty,
                                                                    question_count=question_count,
                                                                    question_types=question_types,
                                                                    model=model2)
        if not query or not included_msgs:
            raise ValueError("No valid query or included messages found for quiz generation.")

        response_content = ''
        content, temp_history, usage = quiz_agent(query=query)
        response_content = content[0] if content else None
        if not response_content:
            raise ValueError("Quiz generation failed. No response received from the agent.")
        else:
            quiz_id, quiz_doc = quiz_agent.process_response(response=response_content,
                                                            included_message_ids=included_msgs,
                                                            usage=usage)

            return True, [quiz_id]

    def generate_revision_sheet(self, session_id: str):
        """
        Generate a revision sheet for the session.
        """
        # print(self.sessions)
        revision_agent = self.sessions[session_id]['revision_agent']
        query, updated_incl_msgs = revision_agent.generate_query(session_id=session_id)

        if not query:
            raise ValueError("No valid query found for revision sheet generation.")

        if not updated_incl_msgs:
            # print("### No new messages to process for revision sheet generation. Returning previous sheet if exists.")
            return json.loads(query)["summary"]

        response_content = ''
        content, temp_history, usage = revision_agent(query=query)
        response_content = content[0] if content else None
        if not response_content:
            raise ValueError("Revision sheet generation failed. No response received from the agent.")
        else:
            response_content_str = json.loads(response_content)["summary"]
            revision_agent.update_revision_sheet(session_id=session_id, revision_sheet=response_content,
                                                 updated_incl_msgs=updated_incl_msgs)
            return response_content_str

            # def save_session(self, session_id: str):
    #     if session_id not in self.sessions:
    #         raise HTTPException(status_code=404, detail="Session ID not found")
    #     session = self.sessions[session_id]
    #     pickled_session = pickle.dumps(session)
    #     document = session['document']
    #     id = document['_id']
    #     try:
    #         update_document(collection_name=self.collection_name,
    #                         document_id = id,
    #                         updates={"session_data": pickled_session},
    #                         db_client=self.db_handler.db_client)
    #     except ValueError as e:
    #         raise HTTPException(status_code=500, detail=f"Failed to save session: {e}")
    #     del self.sessions[session_id]  # Remove from memory to avoid stale data
    #     return {"message": "Session saved successfully", "session_id": session_id}


