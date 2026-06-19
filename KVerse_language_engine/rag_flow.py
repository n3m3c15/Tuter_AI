from KVerse_chat_main.utils import ReturnThread
from KVerse_vector_space.vector_main import VectorStore
from KVerse_language_engine.llm_utils import calculate_entity_overlap_score, calculate_recency_score

class RetrieverModule():
    def __init__(self):
        pass

    def build_history_chain(self, query: dict, 
                            retrieved_history: list, 
                            chat_history: list, 
                            alpha: float = 0.3, 
                            beta: float = 0.2, 
                            gamma:float = 0.5, 
                            total_len: int = 10) -> list:
        """
        Build a chain of history messages based on the query and retrieved history.
        args:
            query: dict containing the query information
            retrieved_history: list of tuples containing the retrieved history messages
            chat_history: list of chat history messages
            alpha: weight for recency score
            beta: weight for entity overlap score
            gamma: weight for similarity score
        returns:
            list of messages that form the history chain
        """
        chain = []
        for history in retrieved_history:
            similarity_score = history[0]
            msg = history[1]
            #check if message_Sender is user and relevant child id is in retrieved_history['metadata']['Child_Message_Id']
            if any(e.lower() in msg["content"].lower() for e in query["entities"]):
                recency_score = calculate_recency_score(message_time=msg['created_at'],
                                                        query_time=query['created_at'],
                                                        message_number=msg['number'],
                                                        query_number=query['number'])
                entity_overlap_score = calculate_entity_overlap_score(query_entities=set(query['entities']), msg_entities=set(msg['entities']))
                msg['score'] = alpha * recency_score + (beta) * entity_overlap_score, gamma * similarity_score
                chain.append(msg)
        chain.sort(key=lambda x: x['score'])
        if not chain and query["pronouns"]:
            # chat_history.extend(chain)
            chain = chat_history
        return chain

    def retieve_n_score(self, vector_store, node, query, weight, top_k=5):
        all_results = list()
        results = vector_store.query_content(query, index_name=node, top_k=top_k)
        if results:
            for match in results.matches:
                score = match.score * weight
                all_results.append((score, match.metadata, node))
            return all_results
        else:
            return None

    def retrieve_context_graph(self, vector_db, query, topic_graph, top_k=5):
        """
        Retrieve context from the vector store based on the query.
        """
        all_results = list() 
        futures = dict()
        for node, weight in topic_graph.items:
            futures[node] = ReturnThread(
                target=self.retieve_n_score,
                args=(vector_db[node], query, weight, top_k)
                )
            futures[node].run
        for future in futures.values():
            result = future.result
            if result:
                all_results.extend(result)
        all_results.sort(key=lambda x: x[0], reverse=True)
        return all_results[:top_k] if top_k else all_results
    
    def retrieve_context(self, query:str|None, vector_store:VectorStore, top_k:int|None = 5, **kwargs) -> tuple[list|None, float|None]:
        """
        Retrieve context from the vector store based on the query.
        """
        results = vector_store.query_content(query, index_name=None, top_k=top_k, **kwargs)
        if results:
            all_results = []
            for match in results.matches: # type: ignore
                all_results.append((match.score, match.metadata))
            return all_results, float(results.usage.readUnits) # type: ignore
        else:
            return None, None
    
    def retrieve_by_id(self, vector_store, id, namespace=None):
        all_results = []
        results = vector_store.index.fetch(ids=id,
                                           namespace=namespace,
                                           include_metadata=True)
        if results:
            for match in results.vectors.values():
                all_results.append(match['metadata'])
        return all_results, float(results.usage.read_units)
    
    def complete_history_pairs(self, results, vector_store, namespace=None):
        """
        Complete the history pairs by ensuring each message has a corresponding response.
        """
        all_results = {doc["id"]:doc for doc in results}
        seen_ids = set(all_results.keys())
        all_needed = set()
        for doc in results:
            root = doc["metadata"].get("Root_Message_Id")
            child = doc["metadata"].get("Child_Message_Id")
            if root and root not in seen_ids:
                all_needed.add(root)
            if child and child not in seen_ids:
                all_needed.add(child)
        usage = 0.0
        if all_needed:
            needed_results, usage = self.retrieve_by_id(vector_store=vector_store, id=list(all_needed), namespace=namespace)
            for doc in needed_results:
                all_results[doc["id"]] = doc
        history_pairs = {}
        for id, doc in all_results.items():
            root = doc["metadata"].get("Root_Message_Id")
            child = doc["metadata"].get("Child_Message_Id")
            if root:
                history_pairs[all_results[root]["Number"]] = [{'role': 'user', 'content' : all_results[root]["content"]},
                                                              {'role': 'assistant', 'content' : doc['content']}]
                del all_results[root]  # Remove root to avoid duplication
                del all_results[id]  # Remove current doc as it is processed
            elif child:
                history_pairs[doc["Number"]] = [{'role': 'user', 'content' : doc["content"]},
                                                {'role': 'assistant', 'content' : all_results[child]['content']}]
                del all_results[child]  # Remove child to avoid duplication
                del all_results[id]  # Remove current doc as it is processed
        # Sort by key to get list of values in order
        sorted_history_pairs = [value for key in sorted(history_pairs.keys()) for value in history_pairs[key]]
        # unpack list of lists into list
        return sorted_history_pairs, usage


