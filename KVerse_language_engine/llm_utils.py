from KVerse_language_engine.llm_config import client
from datetime import datetime 
import math

def get_embeddings_openai(content, model = 'text-embedding-3-large', dimensions=1024, client = client):
        """
        Get embeddings for the content using the specified model.
        """
        response = client.embeddings.create(
            input=content,
            model=model,
            dimensions=dimensions
        )
        return response.data[0].embedding

def calculate_entity_overlap_score(query_entities: set, msg_entities: set) -> float:
        if not query_entities:
            return 0.0
        overlap = len(query_entities.intersection(msg_entities))
        return overlap / len(query_entities)

def calculate_recency_score(message_time: str, query_time: str, message_number : int, query_number: int,  half_life_minutes: int =30, alpha: float = 0.5) -> float:
    """
    Returns a score between 0 and 1, decaying over time.
    """
    delta = (datetime.fromisoformat(query_time) - datetime.fromisoformat(message_time)).total_seconds() / 60  # minutes ago
    time_decay_score =  math.exp(-delta / half_life_minutes)
    position_score = 1 - (message_number / query_number) if query_number > 0 else 1
    final_recency = alpha * time_decay_score + (1 - alpha) * position_score

    return final_recency if final_recency > 0 else 0.0
