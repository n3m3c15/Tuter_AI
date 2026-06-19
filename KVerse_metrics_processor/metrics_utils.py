from KVerse_database_system.db_utils import retrieve_document
from datetime import datetime

def resolve_latest_categorization(data):
    entries = data["Topic_Categorization"]

    sorted_entries = sorted(         # Sort based on last_updated in descending order (latest first)
        entries,
        key=lambda x: datetime.fromisoformat(x["last_updated"]),
        reverse=True
    )

    topic_final_category = {}

    for entry in sorted_entries:
        categorization = entry["categorization"]

        for category_name, topics in categorization.items():
            for topic in topics:
                topic_key = tuple(topic)  # fucking mongo storing tuples as lists, convert to tuple for immutability and hashing

                if topic_key not in topic_final_category:    # Only assign if not already assigned (latest antry assigned first)
                    topic_final_category[topic_key] = category_name

    final_output = {
        "strong_performance_topics": [],
        "weak_performance_topics": [],
        "moderate_performance_topics": [],
        "uncategorized_topics": []
    }

    for topic_key, category in topic_final_category.items():
        final_output[category].append(list(topic_key))

    return final_output


def process_individual_metrics(user_id: str, subject_code: str) -> dict:
    """
    Process metrics for a user and subject code.
    Args:
        user_id (str): The ID of the user.
        subject_code (str): The subject code for which metrics are to be processed.
    Returns:
        dict: Processed metrics data.
    """
    metrics_docs = retrieve_document(collection_name="Metrics_Document", 
                                     multiple_keys={'User_Id': user_id,
                                                   'Subject_Code': subject_code})
    
    if not metrics_docs:
        raise ValueError(f"No metrics found for User_Id: {user_id} and Subject_Code: {subject_code}")
    metrics_doc = metrics_docs[0]  # Assuming we only need the first document
    print(f"Retrieved metrics document: {metrics_doc}")
    subject_metrics = metrics_doc.get('Subject_Metrics', [])
    topic_metrics = metrics_doc.get('Topic_Metrics', {})
    topic_categorization = resolve_latest_categorization(metrics_doc)
    
    print(f"Initial: {metrics_doc.get('Topic_Categorization', [])}\nResolved topic categorization: {topic_categorization}")

    top_topics = list()
    bottom_topics = list()
    all_topics = dict()
    for chapter, topics in topic_metrics.items():
        for topic, metrics in topics.items():
            ret_score = metrics[0].get('retention_score', 0)
            if ret_score is not None:
                if isinstance(ret_score, (int, float)):
                    if ret_score > 0:
                        all_topics[(chapter, topic)] = ret_score
    if not all_topics:
        sorted_topics = sorted(all_topics.items(), key=lambda x: x[1], reverse=True)
        top_topics =  [{'chapter_name': chapter, 'sub_chapter_name': topic, 'retention_score': score} for (chapter, topic), score in sorted_topics[:3]]
        bottom_topics = [{'chapter_name': chapter, 'sub_chapter_name': topic, 'retention_score': score} for (chapter, topic), score in sorted_topics[-3:]]
    retention_rate_change = subject_metrics[0]['retention_score'] - subject_metrics[1]['retention_score'] if len(subject_metrics) > 1 else 0
    assessment_score_change = subject_metrics[0]['quiz_score'] - subject_metrics[1]['quiz_score'] if len(subject_metrics) > 1 else 0
    avg_score =sum(q.get("quiz_score", 0) for q in subject_metrics) / len(subject_metrics) if subject_metrics else 0
    return {
        'subject_metrics': subject_metrics,
        'topic_categorization': topic_categorization,
        'top_topics': top_topics,
        'bottom_topics': bottom_topics,
        'retention_rate_change': retention_rate_change,
        'assessment_score_change': assessment_score_change,
        'average_quiz_score': avg_score
    }

def process_metrics(user_id: str, subject_codes: list) -> dict[list|bool, dict]:
    metrics = dict()
    output_metric = dict()
    output_metric['subjects'] = list()
    for subject_code in subject_codes:
        subject_name = subject_code.split('-')[-1]
        try:
            metrics[subject_name] = process_individual_metrics(user_id=user_id, 
                                                               subject_code=subject_code)
            output_metric['subjects'].append({
                'subject_name': subject_name,
                'metrics': metrics[subject_name]
            })
        except ValueError:
            output_metric["subjects"].append({
                "subject_name": subject_name,
                "metrics": None
            })
    average_retention_rate_change = sum(
        [metrics[subject_name]['retention_rate_change'] for subject_name in metrics]) / len(metrics) if metrics else 0
    average_assessment_score_change = sum(
        [metrics[subject_name]['assessment_score_change'] for subject_name in metrics]) / len(metrics) if metrics else 0
    
    output_metric['exists'] = bool(metrics)
    output_metric['average_retention_rate_change'] = average_retention_rate_change
    output_metric['average_assessment_score_change'] = average_assessment_score_change

    return output_metric
        
