from KVerse_language_engine.agent import GPTAgent
from pydantic import BaseModel, Field, PrivateAttr
from KVerse_chat_main.utils import generate_uid

from openai.types.chat import ParsedChatCompletionMessage
import json

class ScanAgent(GPTAgent):
    """
    Represents a question-answering agent in the KVerse system.
    This agent is designed to retrieve and process information from a vector store.
    """
    def __init__(self, **data):
        super().__init__(**data)
        pass
        
    def get_ids(self):
        """
        Get the IDs of the vector store and history vector store.
        """
        return {"query_Message_Id": generate_uid(),
                "response_Message_Id": generate_uid()}
    def process_Response(self, response: str):
        resp = json.loads(response) 
        if resp['readability_score'] <=6:
            return False, resp['readability_score']
        questions = resp['extracted_questions']
        return True, questions
