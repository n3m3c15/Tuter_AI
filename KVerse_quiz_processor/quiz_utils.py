from KVerse_database_system.db_utils import retrieve_document, upsert_document, update_document
from datetime import datetime
from uuid import uuid4
from itertools import chain

def get_previously_used_message_ids(session_id: str):
    """
    Retrieves previously used message IDs from the quiz document to avoid repetition.
    """
    docs = retrieve_document(collection_name="Quiz_Document",
                             multiple_keys={"Session_Id": session_id})
    if not docs:
        return [], []
    
    return list(set(chain.from_iterable(doc.get("Included_Message_Ids", []) for doc in docs))), docs

def add_results_to_quiz(result_list: list, quiz_id: str):
    """
    Adds the result (correct/wrong) to the corresponding question document.
    """
    score = sum(result['result'] for result in result_list if result['result'] is not None)/len(result_list)
    updates = {
        'Questions': [{
                        'Question_Id': result['Question_Id'],
                        'selected_options': result['selected_options'],
                        'result': result['result']
                    } for result in result_list
                    ],
        'Score': score,
        'Scored_At': str(datetime.now()),
        'Answered': True
    }
    
    msg = update_document(
        collection_name="Quiz_Document",
        query={"Quiz_Id": quiz_id},
        updates=updates
    )
    return msg

def get_quiz(quiz_id:str, session_id: str) -> dict|None:
    """
    Retrieves a quiz document by its ID.
    """
    try:
        quiz_doc = retrieve_document(
            collection_name="Quiz_Document",
            primary_key=quiz_id)
    except ValueError as e:
        raise ValueError(f"Error retrieving quiz document: {e}")
    if quiz_doc is None or len(quiz_doc) == 0:
         return None
    else:
        quiz_doc = quiz_doc[0]
        if quiz_doc['Session_Id'] != session_id:
            raise ValueError(f"Quiz with ID {quiz_id} does not belong to session {session_id}.")
        questions = []
        for question in quiz_doc['Questions']:
            try:
                question_doc = retrieve_document(
                    collection_name="Question_Document",
                    primary_key=question['Question_Id']
                )
            except ValueError as e:
                raise ValueError(f"Error retrieving question document: {e}")
            if question_doc is not None or len(question_doc) != 0:
                questions.append({
                    "Question_Id": question_doc[0]['Question_Id'],
                    "question": question_doc[0]['Question']['question'],
                    "options": question_doc[0]['Question']['options'],
                    "answer": question_doc[0]['Question']['answer'],
                    "explanation": question_doc[0]['Question']['explanation'],
                    "result": question['result'],
                    "selected_options": question.get('selected_options', [])
                })
        quiz_doc['Questions'] = questions
        del quiz_doc['Included_Message_Ids']
        return quiz_doc  # Assuming the document is found, return the first one

def load_quiz_data(user_id:str,subject_code:str):
    doc = retrieve_document("Subject_Document", primary_key=subject_code)[0]
    chapters = doc['Chapters']
    chapters = dict(sorted(chapters.items(),
                           key=lambda x: (0, int(x[0].split("-")[1]))
                           if len(x[0].split("-")) > 1 and x[0].split("-")[1].isdigit()
                           else (1, 0)
                           ))
    quiz_doc = retrieve_document(collection_name="Quiz_Document",multiple_keys={"User_Id":user_id})
    question_ids = [q["Question_Id"]for quiz in quiz_doc for q in quiz.get("Questions", []) if quiz.get("Answered") == True]
    questions = retrieve_document(collection_name="Question_Document",multiple_keys={"Question_Id": {"$in": question_ids}})
    question_result_map = {}
    for quiz in quiz_doc:
        for q in quiz.get("Questions", []):
            question_result_map[q["Question_Id"]] = {
            "selected_options": q.get("selected_options"),
            "result": q.get("result", 0)
        }
    return chapters,questions,question_result_map


def process_subject_response(user_id :str,quiz_dict: dict, subject_code: str):

    quiz_id = str(uuid4())
    created_at =str(datetime.now())
    chapters = quiz_dict.get("chapters")
    structure = {
        'Quiz_Id': quiz_id,
        'User_Id': user_id,
        'Session_Id': None,
        'Subject_Code': subject_code,
        'Quiz_Title': f"{chapters}{created_at}",
        'Quiz_Difficulty': quiz_dict.get('quiz_difficulty'),
        'Quiz_Type': quiz_dict.get('quiz_type'),
        'Created_At': created_at,
        'Included_Message_Ids': None,
        'Score': 0.0,
        'Usage': None,
        'Scored_At': None,
        'Answered': False
    }
    question_ids = quiz_dict['question']
    structure['Questions'] = [{'Question_Id': qid.get('Question_Id'),
                               'selected_options': [],
                               'result': 0.0} for qid in question_ids]

    result = upsert_document(collection_name="Quiz_Document", document=structure)

    return result,quiz_id
