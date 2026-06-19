from KVerse_language_engine.agent import GPTAgent
from KVerse_vector_space.vector_main import VectorStore
from KVerse_vector_space.vector_config import cosmos_history_endpoint, cosmos_history_key
from pydantic import Field, PrivateAttr
from KVerse_chat_main.utils import clean_history

class NameGeneratorAgent(GPTAgent):
    """
    An agent that generates a session name based on the provided context.
    """
    
    vector_store_name: str = Field(default='kverse-chats', description="Name of the vector store to use for retrieval")
    _vector_store: VectorStore = PrivateAttr()
    _history: list = PrivateAttr()

    def __init__(self, **data):
        super().__init__(**data)
        self._vector_store = VectorStore(
            endpoint=cosmos_history_endpoint,
            key=cosmos_history_key,
            index_name=self.vector_store_name
        )
        self.stream = False
        self.n = 1
        self._history = []
    
    def load_history(self, session_id):
        """
        Retrieve the chat history for the given session ID.
        """
        history_results = self._vector_store.index.fetch(namespace=session_id) # type: ignore
        if not history_results:
            raise ValueError(f"No history found for session ID: {session_id}")
        history_messages = history_results.vectors if hasattr(history_results, 'vectors') else None
        if history_messages:
            history = sorted(history_messages, key=lambda x: x.metadata['Created_at'])
            for message in history:
                content = message.metadata.get('Content', '')
                self._history.extend(clean_history(content))
        else:
            raise ValueError(f"No history found for session ID: {session_id}")

        
        
    
    





   