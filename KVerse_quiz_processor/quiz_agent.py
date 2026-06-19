from typing import Literal, Any
from pydantic import PrivateAttr
from KVerse_language_engine.agent import GPTAgent
from KVerse_vector_space.vector_main import VectorStore
from KVerse_language_engine.rag_flow import RetrieverModule
from pydantic import Field
from KVerse_database_system.db_utils import retrieve_document, upsert_document
from KVerse_quiz_processor.quiz_utils import get_previously_used_message_ids
from datetime import datetime
from uuid import uuid4
import json

class QuizGenerationAgent(GPTAgent):
    """
    An agent that generates topic-relevant quizzes from previous chat history.
    """
    vector_store_name: str = Field(default='kverse-books', description="Name of the vector store to use for retrieval")
    session_id: str = Field(..., description="Session ID for the quiz generation")
    subject_code: str = Field(..., description="Subject code for the quiz generation")
    _threshold:int=PrivateAttr()
    _vector_store: VectorStore  = PrivateAttr()
    _retriever: RetrieverModule  = PrivateAttr()

    # _conversation: str = PrivateAttr(default="")
    # _history: dict[str, Any] = PrivateAttr(default=dict())
    # _previously_used_msgs: list[str] = PrivateAttr(default=list())
   
    # quiz_difficulty: Literal["easy", "medium", "hard"] = "medium"
    # question_count: int = 5
    # question_types: Literal["mcq", "short_answer"] = "mcq"
    # format_style: Literal["json", "markdown"] = "json"\

    def __init__(self, **data):
        super().__init__(**data)
        self._threshold = 3
        self._vector_store = VectorStore(index_name=self.vector_store_name)
        self._retriever = RetrieverModule()
        
    def check_quiz_readiness(self, model1 = "gpt-4o-mini", model2 = "gpt-5.1-chat") -> tuple[bool, list[Any], list[Any], list[Any]]:
        messages = retrieve_document(
            collection_name="Message_Document",
            multiple_keys={"Session_Id": self.session_id}
        )
        date_format = "%Y-%m-%dT%H:%M:%S.%f"
        messages = sorted(messages, key=lambda x: datetime.strptime(x['Created_At'], date_format))
        previous_used_msgs, quiz_docs = get_previously_used_message_ids(session_id=self.session_id)
        message_count = 0
        message_count += sum(
                            map(lambda m: 1,
                                filter(
                                    lambda m: (
                                        m["Message_Id"] not in previous_used_msgs
                                        and "Solution" in m["Message"].keys()
                                        and m["Message"]["Solution"]
                                        and "usage" in m["Message"].keys()
                                        and model1 in m["Message"]["usage"].keys()
                                        and float(m["Message"]["usage"][model1]["output"]) > 0.0
                                        and model2 in m["Message"]["usage"].keys()
                                        and float(m["Message"]["usage"][model2]["output"]) > 0.0),
                                    messages)))
        if message_count < (self._threshold):
            ids = []
            if quiz_docs:
                ids = [{"Quiz_Id": quiz_docs[-1]["Quiz_Id"], "Score": quiz_docs[-1].get("Score", 0.0)}]
                print(f"Quiz already exists for session {self.session_id}.")
            return False, ids, [], []
        print(f"Quiz is ready to be generated for session {self.session_id}.")
        return True, [], previous_used_msgs, messages
        
    
    def build_prompt_from_history(self,
                                  history:list[Any], 
                                  previously_used_msgs: list[Any],
                                  quiz_difficulty: Literal["easy", "medium", "hard"] = "medium",
                                  question_count: int = 5,
                                  model: str = "gpt-5.1-chat",
                                  question_types: list[Literal["mcq", "short_answer"]] = ["mcq"]) -> tuple[str, list[Any]]:
        """
        Builds a contextual user prompt from conversation history.
        """
        conversation = ""
        included_msgs = []
        formatted_history = {msg["Message_Id"]: msg for msg in history if msg["Message_Id"] not in previously_used_msgs}
        print(f"Formatted History Length: {len(formatted_history)}")
        for id, msg in formatted_history.items():
            # print("debugiing - 1")
            if "Query" in msg["Message"].keys():
                # print("debugiing - 2")
                if msg["Message"]["Query"]:
                    # print("debugiing - 3")
                    query_content = {'Content' : msg["Message"]["Query"]}
                    child_message = msg['Child_Message_Ids']
                    child_message_id = child_message[0]
                    sol_msg = formatted_history.get(child_message_id, [])
                    if not sol_msg:
                        continue
                    if sol_msg["Message"]["Solution"]:
                        # print("debugiing - 4")
                        # if not sol_msg['Message'].get("usage", {}).get("tool_usage", 0.0) > 0.0:
                        #     continue
                        if not sol_msg['Message'].get("usage", {}).get(model, {}).get("output", 0.0) > 0.0:
                            continue
                        content = {'Content' : sol_msg["Message"]["Solution"]}
                        document, usage = self._retriever.retrieve_context(query=content["Content"], 
                                                                           top_k=1, 
                                                                           vector_store=self._vector_store,
                                                                           namespace=self.subject_code)
                        
                        if not document:
                            continue
                        #print(f"document:{document}")
                        Chapter =  document[0][1]['Chapter_Index']
                        Subchapter =  document[0][1].get('Sub_Chapter_Index')
                        if not Subchapter:
                            continue
                        # print("Metadata Retrieved: ", Chapter, Subchapter)
                        content['Metadata'] = {'Chapter': Chapter, 'Subchapter': Subchapter,'difficulty':quiz_difficulty,'purpose':'session_quiz'}
                        included_msgs.append(id)
                        conversation += f"user : {query_content}\n"
                        included_msgs.append(child_message_id)
                        conversation += f"system : {content}\n"  ### adding new msg to previously used msgs list so as to avoid repetition in future quizzes        
                        print(f'conversation: {conversation}\n\n')
        # self._conversation = conversation
        # self._history = formatted_history
        # self._previously_used_msgs = previously_used_msgs
        print(f'Converstion: {conversation}\n\nIncluded Msgs: {included_msgs}')
        if not conversation or not included_msgs:
            return "", []
        user_prompt = (
            f"Based on the following student-tutor conversation, "
            f"generate a {quiz_difficulty} difficulty quiz with {question_count} questions. "
            f"Question types: {(question_types)}.\n\n"
            f"Conversation:\n{conversation}"
        )
        return user_prompt, included_msgs

    def add_to_question_document(self, quiz_dict: dict, subject_code: str) -> list[str]:
        existing_questions_docs = retrieve_document(
            collection_name="Question_Document",
            multiple_keys={"subject_code": subject_code}
        )
        existing_questions = {doc['Question']['question']:doc['Question_id'] for doc in existing_questions_docs}
        new_questions = []
        question_ids = []
        for item in quiz_dict.get('questions', []):
            if item['question'] not in existing_questions.keys():
                print(f"Metadata: {item.get('Metadata', {})}")
                new_questions.append({'question': item['question'], 
                                      'options' : item['options'], 
                                      'answer': item['answer'], 
                                      'explanation' : item['explanation'], 
                                      'metadata' : item['metadata']})### add logic to uspert new questions to questions document
            else:
                question_ids.append(existing_questions[item['Question']])
        
        for question in new_questions:
            question_id = str(uuid4())
            question_doc = {
                'Question_Id': question_id,
                'Subject_Code': subject_code,
                'Question': question,
                'Created_At': str(datetime.now())
            }
            question_ids.append(question_id)
            result = upsert_document(collection_name="Question_Document", document=question_doc)

        return question_ids
    
    def process_response(self, response: str, included_message_ids: list[str], usage: dict):
        try:
            response = json.loads(response)
        except json.JSONDecodeError:
            raise ValueError("Response is not in valid JSON format.")
        if not isinstance(response, dict):
            return {}, None

        quiz_id = str(uuid4())
        structure = {
            'Quiz_Id': quiz_id,
            'User_Id': self.user_id,
            'Session_Id': self.session_id,
            'Subject_Code': self.subject_code,
            'Quiz_Title': response.get('quiz_title'),
            'Quiz_Difficulty': response.get('quiz_difficulty'),
            'Quiz_Type': response.get('quiz_type'),
            'Created_At': str(datetime.now()),
            'Included_Message_Ids': included_message_ids,
            'Score': 0.0,
            'Usage': usage,
            'Scored_At': None,
            'Answered': False,
        }

        question_ids = self.add_to_question_document(quiz_dict=response, 
                                                     subject_code=self.subject_code)

        structure['Questions'] = [{'Question_Id': qid, 
                                   'selected_options': [],
                                   'result' : 0.0} for qid in question_ids]  ### replacing question details with question ids and cortresponsing results(correct/wrong) only
    
        result = upsert_document(collection_name="Quiz_Document", document=structure)
        quiz_id = {"Quiz_Id": quiz_id, "Score": None}
            
        return quiz_id, result





