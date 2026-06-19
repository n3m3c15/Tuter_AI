from KVerse_chat_main.answering_agent import QuestionAnswerAgent
from KVerse_chat_main.tools import AnsweringAgentTools
from KVerse_chat_main.utils import generate_uid
from KVerse_language_engine.llm_utils import get_embeddings_openai
from KVerse_database_system.db_utils import retrieve_document, update_document
from queue import Queue
from datetime import datetime
import json

class AnswerAgentSpace():
    def __init__(self, init_agent_config, complex_agent_config, derivation_agent_config, session_state, chapter_list):
        tool_agent = AnsweringAgentTools()
        self.chapter_list = chapter_list if chapter_list else []
        # init_agent_config['tools'] = [tool_agent._update_prompt]
        self.init_agent = QuestionAnswerAgent(**init_agent_config)

        complex_agent_config['tools'] = [tool_agent._book_reference, tool_agent._history_reference]
        self.complex_agent = QuestionAnswerAgent(**complex_agent_config)

        derivation_agent_config['tools'] = []
        self.derivation_agent = QuestionAnswerAgent(**derivation_agent_config)

        self.session_state = session_state

    def get_ids(self):
        """
        Get the IDs of the vector store and history vector store.
        """
        return {"query_Message_Id": generate_uid(),
                "response_Message_Id": generate_uid()}
    
    def add_to_history(self, content):
        if self.session_state['Current_Agent'] == "init_agent":
            self.init_agent.add_to_history(content)
        elif self.session_state['Current_Agent'] == "derivation_agent":
            self.derivation_agent.add_to_history(content)
            last_history_key = self.init_agent._num - 1
            if last_history_key < 0:
                raise ValueError("No history available in init agent.")
            last_history = self.init_agent._history[last_history_key]
            last_history.extend(content)
            self.init_agent._history[last_history_key] = last_history
            # content = last_history
        return content
    
    def upsert_history(self, 
                       content:str,
                       message:list, 
                       id: str, 
                       created_at: str, 
                       namespace: str|None = '__default__', **kwargs):
        """
        Upsert a message into the history vector store.
        """
        if self.session_state['Current_Agent'] == "derivation_agent":
            state_document = retrieve_document(
                collection_name='Session_State_Document',
                primary_key=self.init_agent.session_id)
            if not state_document:
                raise ValueError("Session state not found.")
            messages = state_document[0].get('History', [])
            if namespace is None or namespace == '__default__':
                namespace = self.init_agent.session_id
            message = [str(msg) for msg in message]
            messages.append(message)
            update_document(
                collection_name='Session_State_Document',
                query={"Session_Id": namespace},
                updates={"History": messages})
            return True, message, 0.0


        elif self.session_state['Current_Agent'] == "init_agent":
            embeddings = get_embeddings_openai(content, model='text-embedding-3-large', dimensions=1024) #TODO: make config
            root_id = kwargs.get('root_id', id)
            parent_id = kwargs.get('parent_id', [])
            metadata = {'id': id, 
                        'Content': str(message),
                        'Created_at': created_at,
                        'Root_Message_Id': root_id,
                        'Parent_Message_Id': parent_id,}
            success, metadata, usage = self.init_agent._history_vector_store.upsert_content(
                embeddings=embeddings,
                metadata=metadata,
                namespace=namespace, #
                id=id
            )
            return success, metadata, float(usage.writeUnits) if usage else 0.0
        else:
            return False, {}, 0.0
        
    def update_state(self, state :str):
        """
        Update the current agent state.
        """
        if state not in ["init_agent", "derivation_agent"]:
            raise ValueError("Invalid agent state.")
        self.session_state['Current_Agent'] = state
        update_document(
            collection_name="Session_State_Document",
            query={"Session_Id": self.init_agent.session_id},
            updates={"State" : {"Current_Agent": state},
                     "History" : []})
        if state == "derivation_agent":
            self.derivation_agent._num = 0
            self.derivation_agent._history = dict()

    
    def __call__(self, query: str, 
                 answer_queue=Queue(), 
                 handoff_agent = "complex_agent", 
                 addon: bool|None = None,
                 usage_dict = {}, 
                 **kwargs) -> tuple[list, dict, dict]:
        """
        Call the agent with a query and return the response.
        """
        if handoff_agent == 'exam_agent':
            handoff_agent = "complex_agent"
            prompt = open("KVerse_agents/kverse-india-exam-prompt.txt", "r").read()
            kwargs['dev_prompt'] = prompt
            if addon:
                prompt = open("KVerse_agents/kverse-india-highlight-prompt.txt", "r").read()
                kwargs['dev_prompt'] += prompt
        
        elif handoff_agent == "complex_agent":
            if addon:
                prompt = open("KVerse_agents/kverse-india-simple-prompt.txt", "r").read()
                kwargs['dev_prompt'] = kwargs.get('dev_prompt', '') + prompt


        if self.init_agent.input_format is None:
            self.init_agent.input_format = {
                'learning_flow': 'learn',
                'chapter_list': self.chapter_list,
                'subject_code': self.init_agent.subject_code,
                'unit_system': 'SI',
            }
            
        if handoff_agent == 'derivation_agent':
            self.init_agent.input_format['learning_flow'] = 'derive'

        init_answer_queue = Queue()
        derivation_answer_queue = Queue()
        
        state_doc = retrieve_document(
            collection_name="Session_State_Document",
            primary_key= self.init_agent.session_id)
        if not state_doc:
            raise ValueError("Session state not found.")
        self.session_state = state_doc[0]['State']
        # print(f"Answering Agent received query: {query}")
        if self.session_state['Current_Agent'] == "init_agent" or handoff_agent == "complex_agent":
            if 'history' not in kwargs:
                history = self.init_agent.get_history()
                kwargs['history'] = history
            full_content, temp_history, token_usage_dict = self.init_agent(query=query, answer_queue=init_answer_queue, **kwargs)

        elif self.session_state['Current_Agent'] == "derivation_agent" and handoff_agent == "derivation_agent":
            print("Derivation Agent processing query...")
            if 'history' not in kwargs:
                history = self.derivation_agent.get_history()
                kwargs['history'] = history
            full_content, temp_history, token_usage_dict = self.derivation_agent(query=query, answer_queue=derivation_answer_queue, **kwargs)
            print('derivation_history: ', temp_history)
        else:
            raise ValueError("Invalid agent state.")
        full_content_dict = json.loads(full_content[0])
        # print(f"Answering Agent completed query: {query} with response: {full_content}")
        if  full_content_dict["kind"] == "handoff_downstream":
            if handoff_agent == "complex_agent":
                print("Handoff detected, processing complex agent...")
                query = json.dumps(full_content_dict["handoff_context"])
                full_content, temp_history_complex, token_usage_dict_complex = self.complex_agent(query=query, answer_queue=answer_queue, **kwargs) 
                print("got answer - complex")
                model_keys = list(token_usage_dict.keys())
                model_keys.extend(list(token_usage_dict_complex.keys()))
                model_keys = list(set(model_keys))

                token_keys = list()
                for key in model_keys:
                    if key in token_usage_dict.keys():
                        token_keys.extend(list(token_usage_dict[key].keys()))
                    if key in token_usage_dict_complex.keys():
                        token_keys.extend(list(token_usage_dict_complex[key].keys()))
                token_keys = list(set(token_keys))

                for model in model_keys:
                    if model not in token_usage_dict.keys():
                        token_usage_dict[model] = dict()
                    if model not in token_usage_dict_complex.keys():
                        token_usage_dict_complex[model] = dict()
                    for key in token_keys:
                        token_usage_dict[model][key] = token_usage_dict[model].get(key, 0.0) + token_usage_dict_complex[model].get(key, 0.0)
                temp_history[0].append(temp_history_complex[0][-1])

            elif handoff_agent == "derivation_agent":
                print("Handoff detected, processing derivation agent...")
                self.add_to_history(temp_history[0])
                self.upsert_history(content=f'quey :{query}, handoff: {full_content_dict["handoff_context"]}',
                                    message=temp_history[0],
                                    id=kwargs.get('id', generate_uid()),
                                    created_at=datetime.now().isoformat(),
                                    namespace=self.init_agent.session_id)
                self.update_state("derivation_agent")
                search_query = json.dumps(full_content_dict["handoff_context"])
                context, usage = self.derivation_agent._tool_agent.refer_books(
                                                            agent = self.derivation_agent,
                                                            query=search_query)
                full_content_dict['handoff_context']['context_summary'] = full_content_dict.get('context_summary', "")
                full_content_dict['handoff_context']['context_summary'] += json.dumps(context)
                usage_dict = token_usage_dict
                # print("usage_dict: ", usage_dict)
                usage_dict[self.init_agent.model]['tool_usage'] = usage_dict[self.init_agent.model].get('tool_usage', 0.0) + usage if usage else 0.0
                kwargs['history'] = list()
                return self.__call__(query=json.dumps(full_content_dict['handoff_context']),
                                    answer_queue=answer_queue,
                                    usage_dict=usage_dict,
                                    handoff_agent=handoff_agent,
                                        **kwargs)
            
        elif full_content_dict["kind"] == "markdown":
            answer_queue.put(["content", full_content_dict["reply_markdown"]])
            full_content = [full_content_dict["reply_markdown"]]

        elif full_content_dict["kind"] == "step":
            answer_queue.put(["content", full_content_dict["content"]])
            full_content = [full_content_dict["content"]]

        elif full_content_dict["kind"] == "handoff_stop":
            print("Handoff complete, returning final content...")
            answer_queue.put(["content", full_content_dict["content"]])
            full_content = [full_content_dict["content"]]
            self.update_state("init_agent")
        
        
        model_keys = list(token_usage_dict.keys())
        model_keys.extend(list(usage_dict.keys()))
        model_keys = list(set(model_keys))

        token_keys = list()
        for key in model_keys:
            if key in token_usage_dict.keys():
                token_keys.extend(list(token_usage_dict[key].keys()))
            if key in usage_dict.keys():
                token_keys.extend(list(usage_dict[key].keys()))
        token_keys = list(set(token_keys))

        for model in model_keys:
            if model not in token_usage_dict.keys():
                token_usage_dict[model] = dict()
            if model not in usage_dict.keys():
                usage_dict[model] = dict()
            for key in token_keys:
                token_usage_dict[model][key] = token_usage_dict[model].get(key, 0.0) + usage_dict[model].get(key, 0.0)

        # print("history: ", temp_history)
        return full_content, temp_history, token_usage_dict
