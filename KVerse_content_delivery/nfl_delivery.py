import sys
sys.path.append("..")
from KVerse_vector_space.vector_main import VectorStore
from KVerse_database_system import db_utils
from KVerse_backend_chat.user_handler import UserHandler


class NFL:
    def __init__(self, user_id:str, subject_code : str|None=None) :
        self.user_id = user_id
        self.subject_code = subject_code
        self.completion = {}
        self.vector_store = VectorStore(index_name='kverse-books')

    def fetch_or_create_nfl_doc(self):
        try:
            db_utils.create_collection('NFL_Document')
        except Exception as e:
            pass   ###Collection expected to exist
        
        doc = db_utils.retrieve_document(collection_name='NFL_Document', multiple_keys={'User_Id' : self.user_id})
        if not doc:
            user_handler = UserHandler()
            user= user_handler.load_user(user_id=self.user_id)
            subjects = db_utils.retrieve_document(collection_name="Subject_Document",
                                     multiple_keys={"Board": "nfl",
                                                    "Grade": user.get("grade", "")})
            for s in subjects:
                subject_code = s.get("Subject_Code", "")
                self.completion[subject_code] = []
            document = {
                'User_Id' : self.user_id,
                'NFL_Progress' : self.completion
            }
            
            result = db_utils.upsert_document(collection_name='NFL_Document', document=document)
            return self.completion
        
        if len(doc) > 1:
            raise ValueError(f'Found multiple docs for the given User Id')
        
        result = doc[0]['NFL_Progress']
        return result

    def get_modules(self):
        user_handler = UserHandler()
        user= user_handler.load_user(user_id=self.user_id)
        grade = user.get('Grade',None)
        subjects = db_utils.retrieve_document(collection_name="Subject_Document",
                                     multiple_keys={"Board": "nfl",
                                                    "Grade": user.get("grade", "")})

        sub_list=[]
        for s in subjects:
            subject_code = s.get("Subject_Code", "")
            subject_name = s.get("Subject_Code", "").split('-')[-1]
            Active_status = s.get("Active_Status","")
            # compl = round(len(self.completion)/(len(s.get('Chapters',{}))),2)
            if Active_status == True :
                self.completion = self.fetch_or_create_nfl_doc()
                module = s["Chapters"]
                total_topics_in_module = 0
                completed_topics_in_module = 0
                for chapter_name, topics in module.items():

                    # All topics in this chapter
                    chapter_topic_names = [k for k,v in topics.items() if k != 'Description']
                    total_topics_in_module += len(chapter_topic_names)

                    # Completed topics in this chapter
                    completed_in_chapter = [
                        topic
                        for (chap, topic) in self.completion.get(subject_code)  #type:ignore
                        if chap == chapter_name
                    ]

                    completed_topics_in_module += len(completed_in_chapter)
                
                module_progress = round((completed_topics_in_module/total_topics_in_module)*100,2)
                # print(f'subject_code: {subject_code}, module_progress: {module_progress}\n\n')
            else:
                module_progress = 'N/A'
            sub_list.append( {            
                "module_Code": subject_code,
                "module_Name": subject_name,
                "metadata": {
                    "Active" : Active_status,
                    "progress" : module_progress
                }
            })
        return sub_list

    def get_module_progress(self):
        self.completion = self.fetch_or_create_nfl_doc()
        doc = db_utils.retrieve_document(collection_name='Subject_Document',primary_key=self.subject_code)
        if not doc:
            raise ValueError(f'No matching document in Subject Documents for the given subject code')
        
        if len(doc) > 1:
            raise ValueError(f'Found multiple docs for the given Subject Code')

        module = doc[0]['Chapters']

        total_topics = 0
        completed_topics = 0   #### Add logic to get completed topics count
        #chapter_wise = {}
        chapter_list =[]

        for chapter_name, topics in module.items():

            # All topics in this chapter
            chapter_topic_names = [k for k,v in topics.items() if k!= 'Description']
            chapter_description =  (lambda topics : next((self.vector_store.index.fetch(ids=v, namespace=self.subject_code).vectors[0].metadata["Content"] for k,v in topics.items() if k== "Description"),None))(topics)  #type:ignore
            # print(chapter_description)
            total_topics += len(chapter_topic_names)
            self.completion = self.fetch_or_create_nfl_doc()

            # Completed topics in this chapter
            completed_in_chapter = [
                topic
                for (chap, topic) in self.completion[self.subject_code]
                if chap == chapter_name
            ]

            completed_topics += len(completed_in_chapter)

            # chapter_wise= {
            #     "chapter_total": len(chapter_topic_names),
            #     "chapter_completed": len(completed_in_chapter),
            #     "completed_topics": completed_in_chapter
            # }
            
            chapter_list.append({
            "chapter_name": chapter_name,
            "chapter_description": chapter_description,
            "completion": round((len(completed_in_chapter) / len(chapter_topic_names)) * 100 if len(chapter_topic_names) > 0 else 0,2)
        })
            
        return {
            "subject_code": self.subject_code,
            # "total_topics_in_module": total_topics,
            # "completed_topics_in_module": completed_topics,
            # "completion_percentage": round((completed_topics / total_topics) * 100, 2)
            #     if total_topics > 0 else 0,
            "chapter_wise_progress": chapter_list
        }

   
    def get_remaining_topics(self, chapter_name: str):
        self.completion = self.fetch_or_create_nfl_doc()
        doc = db_utils.retrieve_document(collection_name='Subject_Document',primary_key=self.subject_code)
        
        if not doc:
            raise ValueError(f'No matching document in Subject Documents for the given subject code')
        
        if len(doc) > 1:
            raise ValueError(f'Found multiple docs for the given SUbject Code')

        module = doc[0]['Chapters']

        # print(module[chapter_name])
        all_topics = [k for k,v in module[chapter_name].items() if k!= "Description"]
        completed = {
            topic for (chap, topic) in self.completion[self.subject_code]
            if chap == chapter_name
        }

        topics = [
            {
                "topic": k, 
                "content": self.vector_store.index.fetch(ids=v, namespace=self.subject_code).vectors[0].metadata["Content"], #type:ignore
                "completed": (k in completed),
                "image_url": self.vector_store.index.fetch(ids=v, namespace=self.subject_code).vectors[0].metadata["Page_Numbers"] #type:ignore
                } for k ,v in module[chapter_name].items() if k!= 'Description']
       #print(topics)  
        # remaining = [t for t in all_topics if t not in completed and t!= "Description"]
        # print(remaining)
        #remaining_topic_content = []
        # remaining_topic_content = [{k:self.vector_store.index.fetch(ids=v,
        #                                                             namespace=self.subject_code).vectors[0].metadata['Content']} #type: ignore
        #                                                             for k,v in module[chapter_name].items() 
        #                                                             if k in remaining] 

        return {
            "Subject_code": self.subject_code,
            "chapter": chapter_name,
            "topics": topics
        }
    

    def add_progress(self, chapter:str, topic:str):

        self.completion = self.fetch_or_create_nfl_doc()
        
        subject_completion = self.completion[self.subject_code]
        # Append to list
        subject_completion.append((chapter,topic))
        self.completion[self.subject_code] = subject_completion
        
        try:
            result = db_utils.update_document(collection_name='NFL_Document', updates={'NFL_Progress' : self.completion}, query={'User_Id' : self.user_id})
        except Exception as e:
            raise ValueError(e)

        return {
            "message": "Progress updated",
            "progress": subject_completion[-1]
        }