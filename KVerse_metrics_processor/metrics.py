from datetime import datetime
from KVerse_database_system.db_utils import retrieve_document, update_document, upsert_document
from KVerse_chat_main.utils import generate_uid
class TopicRetentionScore:
    def __init__(self, 
                 user_id:str, 
                 session_id: str, 
                 subject_code: str, 
                 strong_threshold_percentage: int =80, 
                 weak_threshold_percentage: int =50):
        self.user_id = user_id
        self.session_id = session_id
        self.subject_code = subject_code
        self.strong_threshold_percentage = strong_threshold_percentage
        self.weak_threshold_percentage = weak_threshold_percentage

    def retrive_topic_list(self): 
        docs = retrieve_document('Subject_Document', primary_key=self.subject_code)
        if not docs:
            raise ValueError(f"No subject document found for Subject_Code: {self.subject_code}")
        self.subject_topic_list = []
        for doc in docs:
            topic_dict = (doc['Chapters'])
            for chapter,subchapter_dict in topic_dict.items():
                #TODO: Clarify what these list are with Sukesh
                for subchapter_name,vecotrs in subchapter_dict.items():
                    self.subject_topic_list.append([chapter,subchapter_name])
        return self.subject_topic_list
    
    def get_avg_quiz_score(self, quiz_id):
        """
        Calculate the average quiz score for a given user, in a given subject.
        """
        docs = retrieve_document(collection_name="Quiz_Document", 
                                 multiple_keys={"Quiz_Id": quiz_id, 
                                                "Subject_Code": self.subject_code})[0]
        if not docs:
            raise ValueError(f"No quiz document found for Quiz_Id: {quiz_id} and Subject_Code: {self.subject_code}")
        self.quiz_score = docs.get('Score')
        return self.quiz_score
    
    def get_all_topics_and_question_docs(self) :
        """
        Calculate the retention rate for a specific topic for a given user in a given subject.
        """
        session_docs = retrieve_document(collection_name="Session_Document", 
                                         multiple_keys={"User_Id": self.user_id, 
                                                        "Subject_Code": self.subject_code})
        
        if session_docs:
            session_ids = [doc['Session_Id'] for doc in session_docs]
        else:
            raise ValueError(f"No session documents found for User_Id: {self.user_id} and Subject_Code: {self.subject_code}")
        
        docs = []
        if len(session_ids) > 0:
            for sid in session_ids:
                docs.append(retrieve_document(collection_name="Quiz_Document", 
                                        multiple_keys={"Session_Id": sid, 
                                                        "Subject_Code": self.subject_code}))
        if not docs:
            raise ValueError(f"No quiz documents found for Session_Id: {self.session_id} and Subject_Code: {self.subject_code}")
        total_quiz_count = len(docs)
        
        if total_quiz_count == 0:
            return None, None
        
        self.subject_topic_list = self.retrive_topic_list()
        self.topic_list = []
        self.all_question_docs = []
        
        for doc in docs:
            for obj in doc: 
                questions  = obj.get('Questions', [])
                for item in questions:
                    question_doc = retrieve_document(
                                        collection_name="Question_Document",
                                        primary_key=item['Question_Id'])[0]
                    if not question_doc:
                        raise ValueError(f"Question document with ID {item['Question_Id']} not found.")
                    result = item.get('result', '')
                    answered_at = obj.get('Scored_At', '')
                    # print(question_doc)
                    question_doc['Question']['metadata']['Created_At'] = answered_at
                    question_doc['Question']['metadata']['result'] = result
                    self.all_question_docs.append(question_doc)
                    topic = [question_doc['Question']['metadata']['Chapter'],
                            question_doc['Question']['metadata']['Subchapter']]
                    if topic not in self.topic_list and topic in self.subject_topic_list:
                        self.topic_list.append(topic)
        
        return self.topic_list,self.all_question_docs

    def get_new_and_prev_topic_scores(self, quiz_id):
        """
        Calculate topic-wise retention rates before and after the latest quiz.
        """

        if self.topic_list is None or self.all_question_docs is None:
            return None, None
        
        self.subject_topic_list = self.retrive_topic_list()
        self.prev_topic_score_dict = {}
        self.new_quiz_topic_score_dict = {}

        #### Get the latest quiz document for reference use along while updating quiz document with score
        latest_quiz_doc = retrieve_document(collection_name="Quiz_Document", 
                                            multiple_keys={"Session_Id": self.session_id, 
                                                           "Subject_Code": self.subject_code, 
                                                           'Quiz_Id': quiz_id})
        latest_quiz_question_ids = []
        # print(f'latest_quiz_doc: {latest_quiz_doc}')
        for item in latest_quiz_doc[0]['Questions']:
            # print(item)
            latest_quiz_question_ids.append(item['Question_Id'])

        for topic in self.topic_list:
            prev_topic_score = 0
            prev_topic_ques_count = 0
            new_quiz_topic_ques_count = 0
            new_quiz_topic_score = 0
            for item in self.all_question_docs:
                chapter_subchapter = [item['Question']['metadata']['Chapter'], item['Question']['metadata']['Subchapter']]
                if chapter_subchapter == topic and chapter_subchapter in self.subject_topic_list:  ### traverse each question doc by topic and exclude latest quiz question ids
                    if item['Question_Id'] not in latest_quiz_question_ids:
                        prev_topic_ques_count += 1
                        prev_topic_score += 1 if item['Question']['metadata']['result'] == 1 else 0
                    else:
                        new_quiz_topic_ques_count += 1
                        new_quiz_topic_score += 1 if item['Question']['metadata']['result'] == 1 else 0

                
            if prev_topic_ques_count > 0:
                self.prev_topic_score_dict[(topic[0],topic[1])] = (prev_topic_score / prev_topic_ques_count)  # Store avg topic score
            if new_quiz_topic_ques_count > 0:
                self.new_quiz_topic_score_dict[(topic[0],topic[1])] = (new_quiz_topic_score / new_quiz_topic_ques_count)  # Store avg topic score
        
        return self.new_quiz_topic_score_dict, self.prev_topic_score_dict

    def get_latest_retention_score_by_topic(self):
        # latest_topics = set(self.new_quiz_topic_score_dict.keys()).intersection(set(self.prev_topic_score_dict.keys()))
        latest_topics = set(self.new_quiz_topic_score_dict.keys()).union(set(self.prev_topic_score_dict.keys()))
        # print(f'latest_topics: {latest_topics}')
        self.retention_score_by_topic = []
        for topic in latest_topics:
            # print(f'topic: {topic}\n')
            if topic in self.new_quiz_topic_score_dict.keys():
                new_score = self.new_quiz_topic_score_dict[topic]
            else:
                continue
            new_score = self.new_quiz_topic_score_dict[topic]
            if topic in self.prev_topic_score_dict.keys():
                prev_score = self.prev_topic_score_dict[topic]
            else:
                prev_score = 0
            # print(f'new_SCORE: {new_score}, prev_socre: {prev_score}')
            if prev_score > 0:
                learning_gain = (new_score - prev_score) / prev_score * 100
                if learning_gain > 0:
                    retention_score = 100
                else:
                    retention_score = new_score / prev_score * 100
                    if learning_gain < 0:
                        learning_gain = 0
                    print(
                        f'topic: {topic},retention_score before percentage conversion: {retention_score}, new_score: {new_score}, prev_score: {prev_score}')
                self.retention_score_by_topic.append({'topic': topic, 'retention_score': retention_score,
                                                      'metadata': {'new_score': new_score, 'prev_score': prev_score,
                                                                   'learning_gain': learning_gain,
                                                                   'last_updated': str(datetime.now())}})
            else:
                learning_gain = new_score * 100
                self.retention_score_by_topic.append({'topic': topic, 'retention_score': 'N/A',
                                                      'metadata': {'new_score': new_score, 'prev_score': 'N/A',
                                                                   'learning_gain': learning_gain,
                                                                   'last_updated': str(datetime.now())}})
        return self.retention_score_by_topic
    
    def categroize_retention_score(self):
        strong_performance_topics = []
        weak_performance_topics = []
        moderate_performance_topics = []
        uncategorized_topics = []
        self.categorization_dict = {}
        for item in self.retention_score_by_topic:
            topic_name = item['topic']
            topic_retention_score = item['retention_score']
            if topic_retention_score == 'N/A':
                uncategorized_topics.append(topic_name)
            elif topic_retention_score >= self.strong_threshold_percentage:
                strong_performance_topics.append(topic_name)
            elif topic_retention_score <= self.weak_threshold_percentage:
                weak_performance_topics.append(topic_name)
            else:
                moderate_performance_topics.append(topic_name)
        
        self.categorization_dict = {
            'strong_performance_topics': strong_performance_topics,
            'weak_performance_topics': weak_performance_topics,
            'moderate_performance_topics': moderate_performance_topics,
            'uncategorized_topics': uncategorized_topics
        }
        return self.categorization_dict
    
    def subject_topic_coverage(self):
        metrics_docs = retrieve_document('Metrics_Document', 
                                         multiple_keys={'User_Id': self.user_id, 
                                                        'Subject_Code': self.subject_code})
        user_covered_topics = []
        if not metrics_docs:
            for item in self.retention_score_by_topic:
                topic_name = item['topic']
                user_covered_topics.append([topic_name[0],topic_name[1]])
        Topic_List = []
        
        if metrics_docs:
            for doc in metrics_docs:
                if 'Topic_Metrics' not in doc.keys():
                    raise ValueError(f"Topic_Metrics not found in Metrics_Document for User_Id: {self.user_id} and Subject_Code: {self.subject_code}")
                topic_tuple = [[chapter_name, subchapter_name] for chapter_name, value in doc['Topic_Metrics'].items() for subchapter_name in value.keys()] 
                Topic_List.extend(topic_tuple)
                user_covered_topics.extend(topic_tuple)
        count = 0
        for pair in user_covered_topics:
            if pair not in self.subject_topic_list:
                raise ValueError(f'topic: {pair} is in user Metrics but not in subject-topic-list')
            count+=1
        self.subject_topic_coverage_percentage = count/len(self.subject_topic_list)
        return self.subject_topic_coverage_percentage
    
    def subject_understanding(self):
        strong_and_moderate_count = len(self.categorization_dict['strong_performance_topics']) + len(self.categorization_dict['moderate_performance_topics'])
        self.subject_understanding_percentage = strong_and_moderate_count/len(self.subject_topic_list)
        return self.subject_understanding_percentage
    
    def subject_retention_rate(self):
        metrics_docs = retrieve_document('Metrics_Document',
                                         multiple_keys={'User_Id': self.user_id,
                                                        'Subject_Code': self.subject_code})
        Topic_List = []
        retention_scores_lists = []
        total_topic_retention_score = 0
        subject_learning_gain = 0
        topics_revised_count = 0
        topics_unlocked_count = 0
        topics_covered_count = 0

        if not metrics_docs:
            for item in self.retention_score_by_topic:
                topic_name = item['topic']
                topic_score_history = {}
                topic_score_history['retention_score'] = item['retention_score']
                topic_score_history['learning_gain'] = item['metadata']['learning_gain']
                topic_score_history['last_updated'] = item['metadata']['last_updated']
                Topic_List.append(topic_name)
                retention_scores_lists.append([topic_score_history])
        else:
            for doc in metrics_docs:
                for chapter_name, value in doc['Topic_Metrics'].items():
                    for subchapter_name, item in value.items():
                        topic_tuple = [chapter_name, subchapter_name]
                        Topic_List.extend(topic_tuple)
                        sorted_items = sorted(item, key=lambda x: x['last_updated'], reverse=True)
                        latest_item = sorted_items[0]
                        retention_scores_lists.append([latest_item])

        topics_covered_count = len(Topic_List)
        for item in retention_scores_lists:
            for obj in item:
                print(obj)
                if obj['retention_score'] == 'N/A':
                    total_topic_retention_score += 0
                    topics_unlocked_count += 1
                else:
                    total_topic_retention_score += obj['retention_score']
                    topics_revised_count += 1
                subject_learning_gain += obj['learning_gain']
        avg_subject_learning_gain = subject_learning_gain / topics_covered_count
        print(
            f'total_topic_retention_score: {total_topic_retention_score}, topics_revised_count: {topics_revised_count}')
        if topics_revised_count == 0:
            avg_topic_retention_score = 0
        else:
            avg_topic_retention_score = total_topic_retention_score / topics_covered_count
        print(
            f'topics_covered_count: {topics_covered_count}, topics_revised_count: {topics_revised_count}, topics_unlocked_count: {topics_unlocked_count}')
        self.weighted_subject_learning_gain = avg_subject_learning_gain * (
                    (len(self.subject_topic_list) - topics_covered_count) / len(self.subject_topic_list))
        self.weighted_subject_retention_score = avg_topic_retention_score * (
                    topics_covered_count / len(self.subject_topic_list))

        return self.weighted_subject_retention_score, self.weighted_subject_learning_gain
    
    def upload_user_metrics(self):
        doc = retrieve_document('Metrics_Document', 
                                multiple_keys={'User_Id': self.user_id, 
                                               'Subject_Code': self.subject_code})
        if not doc:
            doc = {'User_Id': self.user_id, 
                   'Subject_Code': self.subject_code, 
                   'Subject_Metrics': [], 
                   'Topic_Metrics': {}, 
                   'Topic_Categorization': []}
            upsert_document("Metrics_Document", doc)
            return self.upload_user_metrics()
        else:
            doc = doc[0]  # Assuming retrieve_document returns a list of documents

        _subject_metrics = doc['Subject_Metrics']
        subject_metrics = [{'subject_coverage': round(self.subject_topic_coverage_percentage*100, 2),
                                'subject_understanding': round(self.subject_understanding_percentage*100, 2),
                                'retention_score': int(self.weighted_subject_retention_score) if self.weighted_subject_retention_score != 'N/A' else 0,
                                'learning_gain' : int(self.weighted_subject_learning_gain),
                                'quiz_score': self.quiz_score*100,
                                'last_updated': str(datetime.now())}]
        subject_metrics.extend(_subject_metrics)
        # doc['Subject_Metrics'] = subject_metrics

        topic_metrics = doc['Topic_Metrics'] 
        for item in self.retention_score_by_topic:
            topic_name = item['topic']
            retention_score = item['retention_score']
            metadata = item['metadata']
            if topic_name[0] not in topic_metrics.keys():
                topic_metrics[topic_name[0]] = dict()
            if topic_name[1] not in topic_metrics[topic_name[0]].keys():
                topic_metrics[topic_name[0]][topic_name[1]] = list()
            _metrics = topic_metrics[topic_name[0]][topic_name[1]]
            metrics = [{'retention_score': retention_score if retention_score != 'N/A' else retention_score,
                        'learning_gain': metadata['learning_gain'],
                        'last_updated': metadata['last_updated']}]
            metrics.extend(_metrics)
            topic_metrics[topic_name[0]][topic_name[1]] = metrics
        # doc['Topic_Metrics'] = topic_metrics
        _topic_categorization = doc['Topic_Categorization']
        topic_categorization = [{'categorization': self.categorization_dict,
                                 'last_updated': str(datetime.now())}]
        topic_categorization.extend(_topic_categorization)
        return update_document("Metrics_Document",
                                    updates= {"Topic_Metrics": topic_metrics, 
                                              "Subject_Metrics": subject_metrics, 
                                              "Topic_Categorization": topic_categorization}, 
                                    query={"User_Id": self.user_id, 
                                            "Subject_Code": self.subject_code})

    
    def __call__(self, quiz_id):
        quiz_score = self.get_avg_quiz_score(quiz_id)
        subject_topics = self.retrive_topic_list()
        # print(f'subject_topics: {subject_topics}')
        topic_list, all_que_docs = self.get_all_topics_and_question_docs()
        # print(f"topic_list = {topic_list}\nall_ques_docs = {all_que_docs}")
        a,b = self.get_new_and_prev_topic_scores(quiz_id)
        # print(f"new topic score dict: {a},\nold topic score dict{b}")
        topic_wise_retention_scores = self.get_latest_retention_score_by_topic()
        print(f'topic_wise_retention_socres: {topic_wise_retention_scores}')
        topic_wise_categorization = self.categroize_retention_score()
        self.subject_topic_coverage_percentage = self.subject_topic_coverage()
        subject_understanding = self.subject_understanding()
        self.weighted_subject_retention_score,self.weighted_subject_learning_gain = self.subject_retention_rate()
        print(f'weighted_subject_retention_score: {self.weighted_subject_retention_score}, weighted_subject_learning_gain: {self.weighted_subject_learning_gain}')
        upload_msg = self.upload_user_metrics()
        return (self.subject_topic_coverage_percentage,subject_understanding,self.weighted_subject_retention_score,self.weighted_subject_learning_gain,upload_msg)
