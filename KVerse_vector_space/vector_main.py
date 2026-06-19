from pinecone.grpc import PineconeGRPC
from cosmos.cosmos_vector_store import CosmosVectorStore
# from KVerse_vector_space.vector_config import pinecone_api_key, cosmos_endpoint, cosmos_key
import dotenv
import os
from KVerse_language_engine.llm_utils import get_embeddings_openai
from uuid import uuid4

# Load environment variables
dotenv.load_dotenv()

pinecone_api_key = os.getenv('pinecone_api_key')
cosmos_history_endpoint = os.getenv('cosmos_history_endpoint')
cosmos_history_key = os.getenv('cosmos_history_key')
database_name = os.getenv('database_name')
cosmos_endpoint = os.getenv('cosmos_endpoint')
cosmos_key = os.getenv('cosmos_key')

class VectorStore():
    def __init__(self, pinecone=False, index_name=None, endpoint=cosmos_endpoint, key=cosmos_key):
        if pinecone:
            self.store = PineconeGRPC(
                api_key=key)
        else:
            self.store = CosmosVectorStore(
                endpoint=endpoint,
                key=key,
                database_name='kverse'
            )
        if index_name:
            self.index = self.load_index(index_name)
    
    def load_index(self, index_name):
        """
        Load the specified index from the vector store.
        """
        return self.store.Index(index_name)

    
    def upsert_content(self, embeddings, metadata, namespace, index_name = None, id = None):
        """
        Upsert content into the vector store.
        """

        if index_name:
            index = self.load_index(index_name)
        else:
            index = self.index

        if not id:
            id = str(uuid4())
        metadata['id'] = id

        ret = index.upsert(
            vectors=[{
                'id': metadata['id'],
                'values': embeddings,
                'metadata': metadata
            }],
            namespace=namespace)
        try:
            usage = ret.usage # type: ignore
        except AttributeError:
            usage = None
        return True, metadata, usage
    
    def upsert_content_bulk(self, vector_list, namespace, index_name=None):
        """
        Upsert multiple content vectors into the vector store.
        """
        if index_name:
            index = self.load_index(index_name)
        else:
            index = self.index

        vectors = []
        for vector in vector_list:
            
            values = vector['values']
            metadata = vector['metadata']

            if 'id' not in metadata:
                metadata['id'] = str(uuid4())
            vectors.append({
                'id': metadata['id'],
                'values': values,
                'metadata': metadata
            })
        ret = index.upsert(vectors=vectors, namespace=namespace)
        try:
            usage = ret.usage # type: ignore
        except AttributeError:
            usage = None
        return True, [v['metadata'] for v in vectors], usage

    def query_content(self, query: str|None, namespace: str|None=None, top_k: int|None = 5, **kwargs):
        """
        Query the vector store for content similar to the query.
        filters :
            $eq : exact match
            $gt : greater than
            $lt : less than
            $gte : greater than or equal to
            $lte : less than or equal to
            $ne : not equal
            $in : in a list
            $nin : not in a list
            $exists : field exists
            $and : logical AND
            $or : logical OR
        """
        if kwargs.get('index_name'):
            index = self.load_index(kwargs['index_name'])
        else:
            index = self.index

        filter = kwargs.get('filter', None)
        if query:
            query_embedding = get_embeddings_openai(content=query)
        else:
            query_embedding = None

        results = index.query(
            vector=query_embedding,
            top_k=top_k,
            filter=filter,
            include_metadata=True,
            namespace=namespace,
        )

        return results