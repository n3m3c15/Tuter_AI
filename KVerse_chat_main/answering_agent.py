from KVerse_language_engine.agent import GPTAgent
from KVerse_language_engine.rag_flow import RetrieverModule
from KVerse_vector_space.vector_main import VectorStore
from KVerse_vector_space.vector_config import cosmos_history_endpoint, cosmos_history_key
from pydantic import Field, PrivateAttr
# import spacy
# from spacy.language import Language
from KVerse_chat_main.tools import AnsweringAgentTools

class QuestionAnswerAgent(GPTAgent):
    """
    Represents a question-answering agent in the KVerse system.
    This agent is designed to retrieve and process information from a vector store.
    """
    vector_store_name: str = Field(default='kverse-books', description="Name of the vector store to use for retrieval")
    subject_code: str = Field(..., description="Subject code for the content being processed")
    history_vector_store_name: str = Field(default='kverse-chats', description="Name of the vector store for maintaining history")
    session_id: str = Field(..., description="Session ID for the agent's interactions")
    image_retrieval: bool = Field(default=True, description="Whether to retrieve images related to the query")
    notes_retrieval: bool = Field(default=True, description="Whether to retrieve notes related to the query")

    # top_k: int = Field(default=5, description="Number of top results to retrieve for context")  
    # image_retrieval: bool = Field(default=True, description="Whether to retrieve images related to the query")
    # notes_retrieval: bool = Field(default=True, description="Whether to retrieve notes related to the query")
    _vector_store: VectorStore = PrivateAttr()
    _history_vector_store: VectorStore = PrivateAttr()
    _retriever: RetrieverModule = PrivateAttr()
    _complex_agent: GPTAgent = PrivateAttr()
    _tool_agent: AnsweringAgentTools = PrivateAttr()
    # _nlp_client: Language = PrivateAttr()
    
    def __init__(self, **data):
        super().__init__(**data)
        # self._nlp_client = spacy.load("en_core_web_sm")  # Load the spaCy NLP model
        self._vector_store = VectorStore(index_name=self.vector_store_name)
        self._history_vector_store = VectorStore(index_name=self.history_vector_store_name,
                                                 endpoint=cosmos_history_endpoint,
                                                 key=cosmos_history_key)  
        self._retriever = RetrieverModule()  # Initialize the retriever module
        self._tool_agent = AnsweringAgentTools()  # Initialize the tool agent
        # Initialize the tool agent for complex agent
        # self.output_format = TutorAgentSchema  # Set the output format to the TutorAgentSchema
    
    # def preprocess_query(self, query: str) -> dict:
    #     """
    #     Preprocess the query to ensure it is suitable for retrieval.
    #     """
    #     query = query.strip()
    #     doc = self._nlp_client(query)
    #     entities = [ent.text for ent in doc.ents]
    #     pronouns = [token.text for token in doc if token.pos_ == 'PRON']
    #     embeddings = get_embeddings_openai(query, model='text-embedding-3-small', dimensions=1024)
    #     return {"entities" : entities, "pronouns" : pronouns, "embeddings" : embeddings}

    
    def retrieve_history(self, query, retrieval_threshold = 0.8):
        retrieved_history, usage = self._retriever.retrieve_context(query=query,
                                                                    vector_store=self._history_vector_store,
                                                                    top_k=self.history_length*2,
                                                                    namespace=self.session_id) # type: ignore
            
        if retrieved_history:
            retrieved_history = [vector[1] for vector in retrieved_history if vector[0] > retrieval_threshold] #TODO:use chain builder # type: ignore
            # retrieved_history, completion_usage = self._retriever.complete_history_pairs(results=retrieved_history,
            #                                                            vector_store=self._history_vector_store,
            #                                                            namespace=self.session_id) # type: ignore
        
        usage = usage if usage else 0.0
        # usage += completion_usage if completion_usage else 0.0
        return retrieved_history, usage
        # history_scored = self._retriever.build_history_chain(
        #     query=self.preprocess_query(' '.join(recent_history)),
        #     retrieved_history=retrieved_history,
        #     chat_history=recent_history)
        # return history_scored[-self.history_length:] if history_scored else list()

    def retrieve_context_subchapters(self, query, subject_code, top_k=5, image_retrieval=True, notes_retrieval=False, attach_metadata=True, **kwargs):
        """
        Retrieve context from the vector store based on the query.
        """
        text_retrieved = None
        image_retrieved = None
        notes_retrieved = None
        usage = 0.0
        # if filter := kwargs.get('filter', None):
        #     kwargs['filter'] = {'Subject_Code': subject_code, **filter}
        if top_k != 0:
            text_retrieved, text_usage = self._retriever.retrieve_context(query=query,
                                                                        vector_store=self._vector_store, 
                                                                        top_k=top_k,
                                                                        namespace=subject_code,
                                                                        **kwargs) # type: ignore
        else:
            text_retrieved, text_usage = [], 0.0
        usage += text_usage if text_usage else 0.0
        if text_retrieved:
            image_filter = {'Chapter_Index': list(set([doc[1]['Chapter_Index'] for doc in text_retrieved]))}
        else:
            image_filter = None
        if (text_retrieved and image_retrieval) or (top_k == 0 and image_retrieval):
            image_top_k = kwargs.get('image_top_k', 5)
            if image_top_k > 0:
                image_retrieved, image_usage = self._retriever.retrieve_context(vector_store=self._vector_store, 
                                                                                query=query, 
                                                                                namespace=subject_code+'_images', 
                                                                                top_k=image_top_k,
                                                                                filter=image_filter) # type: ignore
                if image_retrieved:
                    image_retrieved = [doc for doc in image_retrieved if doc[0] > kwargs.get('image_threshold', 0.0)]
            else:
                image_retrieved, image_usage = [], 0.0
            usage += image_usage if image_usage else 0.0
        if text_retrieved and notes_retrieval:
            notes_retrieved, note_usage = self._retriever.retrieve_context(vector_store=self._vector_store, 
                                                                           query=query, 
                                                                           namespace=subject_code+'_notes', 
                                                                           top_k=3) # type: ignore
            usage += note_usage if note_usage else 0.0
        if text_retrieved:
            text_retrieved = self.process_context(text_retrieved, context_type='text', attach_metadata=attach_metadata)
        if image_retrieved:
            image_retrieved = self.process_context(image_retrieved, context_type='image', attach_metadata=attach_metadata)
        if notes_retrieved:
            notes_retrieved = self.process_context(notes_retrieved, context_type='note', attach_metadata=attach_metadata)
        return text_retrieved, image_retrieved, notes_retrieved , usage
    
    def process_context(self, context, context_type='text', attach_metadata=False):
        """
        Process the context based on its type.
        """
        ret_context = list()
        for content in context:
            if context_type == 'text':
                ret_content = content[1]['Content']
                if attach_metadata:
                    ret_content += f"(Chapter: {content[1]['Chapter_Index']}, "\
                                   f"Subchapter: {content[1]['Sub_Chapter_Index']}, "\
                                   f"Page Numbers: {content[1]['Page_Numbers']}, "\
                                   f"Book: {content[1]['Book_Index']})"
                ret_context.append(ret_content)
            elif context_type == 'image':
                ret_content = content[1]['Content'] + f"Image URL: {content[1]['URL']}"
                if attach_metadata:
                    ret_content += f"(Page Numbers: {content[1]['Page_Numbers']}, "\
                                   f"Book: {content[1]['Book_Index']}, "\
                                   f"Image size: {content[1]['Image_Size']})"
                ret_context.append(ret_content)
            elif context_type == 'note':
                ret_content = content[1]['Content']
                ret_context.append(ret_content)
        return ret_context if ret_context else None

     
        
                
    

    

    

        
