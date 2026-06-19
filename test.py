from KVerse_database_system.db_utils import retrieve_document, update_document

def normalize_selected_options(selected_options, options: list):
    if not isinstance(selected_options, list):
        return None

    normalized = []

    for opt in selected_options:

        if isinstance(opt, int):
            if 0 <= opt < len(options):
                normalized.append(opt)
            else:
                return None


        elif isinstance(opt, str) and len(opt) == 1 and opt.isalpha():
            idx = ord(opt.lower()) - ord('a')
            if 0 <= idx < len(options):
                normalized.append(idx)
            else:
                return None


        elif isinstance(opt, str):
            try:
                normalized.append(options.index(opt))
            except ValueError:
                return None

        else:
            return None

    return normalized


def normalize_all_quiz_selected_options():
    quiz_docs = retrieve_document(
        collection_name="Quiz_Document",
        multiple_keys={"_id": {"$exists": True}}
    )

    if not quiz_docs:
        return {"status": "success", "message": "No quizzes found"}

    question_ids = set()
    for quiz in quiz_docs:
        for q in quiz.get("Questions", []):
            if "Question_Id" in q:
                question_ids.add(q["Question_Id"])

    if not question_ids:
        return {"status": "success", "message": "No questions found"}

    question_docs = retrieve_document(
        collection_name="Question_Document",
        multiple_keys={"Question_Id": {"$in": list(question_ids)}}
    )

    question_options_map = {}
    for q in question_docs:
        question_id = q.get("Question_Id")
        options = q.get("Question", {}).get("options", [])
        question_options_map[question_id] = options

    updated_quizzes = 0
    normalized_count = 0
    failed_question_ids = set()

    for quiz in quiz_docs:
        updated_questions = []
        changed = False

        for q in quiz.get("Questions", []):
            question_id = q.get("Question_Id")
            selected_options = q.get("selected_options")

            options = question_options_map.get(question_id)

            if not options:
                failed_question_ids.add(question_id)
                updated_questions.append(q)
                continue

            normalized = normalize_selected_options(selected_options, options)

            if normalized is not None and normalized != selected_options:
                q["selected_options"] = normalized
                changed = True
                normalized_count += 1
            elif normalized is None:
                failed_question_ids.add(question_id)

            updated_questions.append(q)

        if changed:
            update_document(
                collection_name="Quiz_Document",
                query={"Quiz_Id": quiz["Quiz_Id"]},
                updates={"Questions": updated_questions}
            )
            updated_quizzes += 1

    return {
        "status": "success",
        "quizzes_updated": updated_quizzes,
        "normalized_questions": normalized_count,
        "failed_question_ids": list(failed_question_ids)
    }


result = normalize_all_quiz_selected_options()
print(result)
