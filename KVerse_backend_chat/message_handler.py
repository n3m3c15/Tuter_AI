from KVerse_chat_main.utils import clean_history
from KVerse_chat_main.answer_agent_space import AnswerAgentSpace
from KVerse_database_system.schemas import Message_Document_kwargs
from KVerse_database_system.db_utils import update_document, structure, retrieve_document
from KVerse_question_paper_processor.scan_agent import ScanAgent    
from queue import Queue

from datetime import datetime
import json

class MessageHandler():
    def __init__(self, 
                 session_id: str, 
                 answer_agent_config: dict, 
                 complex_answer_agent_config: dict, 
                 derivation_answer_agent_config: dict,
                 session_state: dict,
                 scan_agent_config: dict,
                 chapter_list: list|None = None):
        self.session_id = session_id
        self.answering_agent_space = AnswerAgentSpace(init_agent_config=answer_agent_config,
                                                complex_agent_config=complex_answer_agent_config,
                                                derivation_agent_config=derivation_answer_agent_config,
                                                session_state = session_state,
                                                chapter_list=chapter_list)
        self.answering_agent = self.answering_agent_space.init_agent
        if scan_agent_config:
            self.scan_agent = ScanAgent(**scan_agent_config)
        else:
            self.scan_agent = None
        self.collection_name = "Message_Document"
    
    def load_history(self):
        """
        Load the chat history for the session.
        """

        if self.answering_agent_space.session_state['Current_Agent'] == "derivation_agent":
            doc = retrieve_document(collection_name='Session_State_Document',
                                    primary_key=self.answering_agent.session_id)
            if not doc:
                raise ValueError("Session state not found.")
            history = doc[0].get('History', [])
            if history:
                self.answering_agent_space.derivation_agent._num = len(history)
                for messages in history:
                    messages = [clean_history(message) for message in messages]
                    self.answering_agent_space.derivation_agent.add_to_history(messages)
        
        
        history = self.answering_agent._history_vector_store.index.fetch(namespace=self.session_id) # type: ignore
        #sort history by created_at
        if history:
            number = len(history.vectors)
            history = sorted(history.vectors, key=lambda x: x.metadata['Created_at'])
            if len(history) > self.answering_agent.history_length:
                history = history[-self.answering_agent.history_length:]
            self.answering_agent._num = number
            for message in history:
                self.answering_agent.add_to_history(clean_history(message.metadata['Content']))

    
    def reply_regular_query(self,
                            reply_id: str,
                            query: str,
                            query_id: str, 
                            addon: bool|None = None,
                            handoff_agent: str = "complex_agent",
                            attachments: list|None = None) -> tuple[str|None, dict]:
        """
        Handle a regular query and return the response.
        """
        kwargs = dict()
        if attachments:
            kwargs['file_content'] = self.answering_agent.add_attachments(attachments)
        # Process the retrieved information and generate an answer
        content, temp_history, usage = self.answering_agent_space(query=query, 
                                                                  answer_queue = Queue(), 
                                                                  handoff_agent = handoff_agent, 
                                                                  addon=addon,
                                                                  id=query_id, 
                                                                  **kwargs) #TODO: use answer_queue to handel streaming

        response = content[0] if content else None
        temp_history[0] = self.answering_agent_space.add_to_history(temp_history[0])
        content=f"query: {query}, solution: {response}"
        ret, data, write_usage = self.answering_agent_space.upsert_history(content=content,
                                                                            message = temp_history[0],
                                                                            id = reply_id,
                                                                            created_at=datetime.now().isoformat(),
                                                                            namespace=self.session_id)
        # print(f"write_usage: {usage}")
        # print("history: ", temp_history)
        if 'tool_usage' not in usage:
            usage['tool_usage'] = 0.0
        usage['tool_usage'] += write_usage if write_usage else 0.0
        return response, usage
     
    def reply_scan(self,
                   query_id: str, 
                   reply_id: str,
                   query: str|None,               
                   attachments: list[dict],
                   detections: list,
                   save_urls: list|None) -> tuple[bool, list|None]:
        
        """
        Handle a scan query and return the response.
        """
        kwargs = dict()
        query = f"query={query}, yolo_detections{detections}, diagrams_saved_at: {save_urls}"
        if not self.scan_agent:
            raise ValueError("Scan agent is not configured.")
        kwargs['file_content'] = self.scan_agent.add_attachments(attachments)
        response = None
        content, temp_history, usage = self.scan_agent(query=query, **kwargs) # type: ignore
        response = content[0] if content else None
        if not response:
            return False, None
        ret, questions = self.scan_agent.process_Response(response) #type: ignore
        return ret, questions, usage # type: ignore


    def upsert_message(self, message_id: str, message_content: dict, sender: str, inputs:str, 
                       root_message_id : str|None = None, parent_message_id: str|None = None, 
                       child_message_ids: list = []):
        """
        Update a message in the session.
        """
        structure_params = {
            "session_id": self.session_id,
            "message_id": message_id,
            "message_content": message_content,
            "sender": sender,
            "inputs": inputs,
            "root_message_id": root_message_id,
            "parent_message_id": parent_message_id,
            "child_message_ids": child_message_ids,
            "created_at": datetime.now().isoformat(),
        }

        return structure(collection_name=self.collection_name, 
                                         schema = Message_Document_kwargs, 
                                         **structure_params)
        
    def update_message(self, message_id: str, fields:dict):
        """
        Update a message in the database.
        """

        return update_document(collection_name=self.collection_name,
                               document_id=message_id,
                               updates=fields)




        