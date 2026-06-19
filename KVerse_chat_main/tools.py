from pydantic import BaseModel, PrivateAttr
from KVerse_chat_main.utils import ReturnThread
from KVerse_database_system.db_utils import retrieve_document, update_document
from KVerse_language_engine.agent import ToolAgent
import json


update_prompt={"type": "function",
                "function":{
                    "name": "update_prompt",
                    "description": 
                        "Update the agent’s system prompt ONLY when the USER explicitly and clearly requests a long-term preference or behavioral change.The assistant MUST NOT call this function based on assumptions, inferred preferences, or indirect hints.",
                    "strict": True,
                    "parameters": {
                        "type": "object",
                        "required": ["prompt", "method", "user_explicitly_requested_persistence"],
                        "properties": {
                            "prompt": {
                                "type": "string",
                                "description": 
                                "The exact preference the USER explicitly asked to be applied in future responses. Do NOT include contextual descriptions or inferred preferences."
                            },
                            "method": {
                                "type": "string",
                                "enum": ["append", "replace"],
                                "description": 
                                "How to apply the preference. 'append' unless the user clearly says replace."
                            },
                            "user_explicitly_requested_persistence": {
                                "type": "boolean",
                                "description":
                                "Must be true ONLY if the USER clearly indicated the preference should apply to FUTURE responses using phrases like 'remember this', 'from now on', 'always', 'in future', 'store this', etc."
                            }
                            },
                            "additionalProperties": False}}}

# history_fetch={"type": "function",
#                 "function":{
#                     "name": "fetch_complete_history",
#                     "description": "Fetch the complete chat history of the agent for the session",
#                     "strict": True,
#                     "parameters": {
#                         "type": "object",
#                         "required": [],
#                         "properties":{},
#                         "additionalProperties": False}}}

book_reference={"type": "function",
                "function":{
                    "name": "get_book_references",
                    "description": "Retrieve references from the vector store of books",
                    "strict": True,
                    "parameters": {
                        "type": "object",
                        "required": ["query", "top_k", "image_top_k", "attach_metadata"],
                        "properties": {
                            "query": {
                                "type": "string",
                                "description": "Document Search query - A concise version of the query focusing on its essence and keywords for retrieving relevant subject matter documents"
                                },
                            "top_k": {
                                "type": "integer",
                                "description": "how many documents to retrieve has to be 1-10"
                                }, 
                            "image_top_k": {
                                "type": "integer", 
                                "description": "how many images to retrieve has to be < 5"
                                },
                            # "image_threshold": {
                            #     "type": "number",
                            #     "description": "threshold of how similar the image should be to the query, default is 0.0, must be between 0 and 0.3ßß"
                            #     },
                            "attach_metadata": {
                                "type": "boolean",
                                "description": "if metadata such as page number, book name, sub chapter name etc. are needed"
                                }},
                        "additionalProperties": False}}}

history_reference= {"type": "function",
                    "function": {
                        "name": "get_history_references",
                        "description": "Retrieve more questions from chat history for more context to answer the query",
                        "strict": True,
                        "parameters": {
                            "type": "object",
                            "required": ["query", "retrieval_threshold"],
                            "properties": {
                                "query": {
                                    "type": "string",
                                    "description": "Document Search query - A concise version of the query focusing on its essence and keywords to retrieve relevant history references"
                                    },
                                "retrieval_threshold": {
                                    "type": "number",
                                    "description": "threshold of how similar the history should be to the query, default is 0.2 (most history will render low scores on comparison), must be between 0 and 1"
                                    }},
                                ""
                            "additionalProperties": False}}}

# class TutorAgentSchema_StudentInterest(BaseModel):
#   curriculum: str
#   personal: str

# class TutorAgentSchema__Metrics(BaseModel):
#   followup_rate: float
#   subject_understanding: float
#   retention_rate: float
#   communication_score: float
#   student_interest: TutorAgentSchema_StudentInterest

# class TutorAgentSchema(BaseModel):
#   answer: str
#   metrics: TutorAgentSchema__Metrics

class AnsweringAgentTools(ToolAgent):
    _book_reference: dict = PrivateAttr()
    _history_reference: dict = PrivateAttr()
    _update_prompt: dict = PrivateAttr()

    def __init__(self, **data):
        super().__init__(
            name="AnsweringAgentTools",
            description="Tools for retrieving references",
            **data
        )

        self._book_reference = book_reference
        self._history_reference = history_reference
        self._update_prompt = update_prompt
        # self.name = "AnsweringAgentTools"
        # self.description = "Tools for the Answering Agent to retrieve book references and history references based on the query."

    def fetch_history(self, agent):
        """
        Fetch the complete chat history of the agent for the session.
        """
        usage = None
        ret = agent._history_vector_store.index.fetch(namespace=agent.session_id) # type: ignore
        if ret:
            usage = float(ret.usage.read_units) if ret.usage.read_units else 0.0
            return ret.vectors, usage
        return [], 0.0
    
    def update_prompt(self, agent, prompt: str, method: str = "append", user_explicitly_requested_persistence: bool = False):
        """
        Update the system prompt of the agent by the agent to help be more helpful and connected to the user in a more natural way.
        """
        if not user_explicitly_requested_persistence:
            return {"message": "User did not explicitly request persistence for the prompt."}, 0.0  
        document = retrieve_document(collection_name = "User_Document",
                                     primary_key=agent.user_id)
        if not document:
            raise ValueError(f"No user document found for user ID: {agent.user_id}")
        user_prompt = document[0].get("System_Prompt", "")
        if method == "append":
            user_prompt += f"\n{prompt}"
        elif method == "replace":
            user_prompt = prompt
        ret_message = update_document(collection_name = "User_Document",
                                      query={"user_id": agent.user_id},
                                      updates={"System_Prompt": user_prompt})
        if not ret_message:
            raise ValueError(f"Failed to update user document for user ID: {agent.user_id}")
        
        return {"message": "User prompt updated successfully"}, 0.0
        
        

    def refer_books(self, agent, query, top_k=5, image_top_k=3, image_threshold = 0.0, attach_metadata=False):
        """
        Retrieve book references based on the query.
        """
        print(f"Query: {query}, Top K: {top_k}, Image Top K: {image_top_k} Attach Metadata: {attach_metadata}, image Threshold: {image_threshold}")
        text_retrieved, image_retrieved, notes_retrieved, usage = agent.retrieve_context_subchapters(
                                                                                        query=query,
                                                                                        subject_code=agent.subject_code,
                                                                                        top_k=top_k,
                                                                                        image_top_k = image_top_k,
                                                                                        image_threshold=image_threshold,
                                                                                        image_retrieval=agent.image_retrieval,
                                                                                        notes_retrieval=agent.notes_retrieval,
                                                                                        attach_metadata=attach_metadata)
        context = {'text': text_retrieved,
                    'images': image_retrieved,
                    'notes': notes_retrieved}
        print("Image retrieval:", image_retrieved)
        return context, usage
    
    def refer_history(self, agent, query, retrieval_threshold=0.8):
        """
        Retrieve history references based on the query.
        """
        retrieved_history, usage = agent.retrieve_history(query=query, retrieval_threshold=retrieval_threshold)
        if retrieved_history:
            return retrieved_history, usage
        return list(), 0.0

    def __call__(self, agent, tool_call):
        futures = {}
        for call in tool_call:    
            name = call.get('name', None)
            id = call.get('id', None)
            kwargs = call.get('arguments', {})
            kwargs = json.loads(kwargs) if isinstance(kwargs, str) else kwargs
            if name == "get_book_references":
                kwargs['agent']= agent
                futures[id] = {'thread' : ReturnThread(
                                                target=self.refer_books,
                                                kwargs=kwargs),
                                'name' : name}
                futures[id]['thread'].start()
            elif name == "get_history_references":
                kwargs['agent']= agent
                futures[id] = {'thread' : ReturnThread(
                                                target=self.refer_history,
                                                kwargs=kwargs),
                                'name' : name}
                futures[id]['thread'].start()
            elif name == "update_prompt":
                futures[id] = {'thread' : ReturnThread(
                                                target=self.update_prompt,
                                                args=(agent, 
                                                    kwargs['prompt'], 
                                                    kwargs.get('method', 'append'))),
                                'name' : name}
                futures[id]['thread'].start()
            elif name == "fetch_complete_history":
                futures[id] = {'thread' : ReturnThread(
                                                target=self.fetch_history,
                                                args=(agent, )),
                                'name' : name}
                futures[id]['thread'].start()
            else:
                raise ValueError(f"Unknown tool call name: {name}")
        results = list()
        usages = 0.0
        for id in futures:
            name = futures[id]['name']
            ret, usage = futures[id]['thread'].join()
            results.append({"role": "tool",
                            "tool_call_id": id,
                            "name": name,
                            "content": str(ret)})
            usages += usage if usage else 0.0
        return results, usages

