from openai import AzureOpenAI, OpenAI
import json
import dotenv
import os
# Load environment variables
dotenv.load_dotenv()
openai_subscription_key = os.getenv('openai_subscription_key')
deepseek_api_key = os.getenv('deepseek_api_key')

class AzureChatgpt():    
    def __init__(self, 
                 api_version="2024-12-01-preview", 
                 azure_endpoint="https://ed-gpt.openai.azure.com/",
                 openai_api_key=openai_subscription_key): #TODO: make it env
        
        self.client = AzureOpenAI(
                api_version=api_version,
                azure_endpoint=azure_endpoint,
                api_key=openai_api_key,
            )
        
    # def _fix_content_types(self, content_list):
    #     """Replace 'file_url' with 'image_url' for Azure OpenAI compatibility."""
    #     fixed_content = []
    #     for item in content_list:
    #         if isinstance(item, dict):
    #             fixed_item = item.copy()
                
    #             if fixed_item.get('type') == 'file_url':
    #                 fixed_item['type'] = 'image_url'
    #                 if 'file_url' in fixed_item:
    #                     url = fixed_item.pop('file_url')
    #                     # Handle both string and dict formats
    #                     if isinstance(url, str):
    #                         fixed_item['image_url'] = {'url': url}
    #                     else:
    #                         fixed_item['image_url'] = url
                
    #             fixed_content.append(fixed_item)
    #         else:
    #             fixed_content.append(item)
        
    #     return fixed_content

    # def _fix_all_messages(self, messages):
    #     """Fix all messages to use image_url instead of file_url."""
    #     fixed_messages = []
    #     for msg in messages:
    #         if isinstance(msg, dict):
    #             fixed_msg = msg.copy()
    #             if 'content' in fixed_msg and isinstance(fixed_msg['content'], list):
    #                 fixed_msg['content'] = self._fix_content_types(fixed_msg['content'])
    #             fixed_messages.append(fixed_msg)
    #         else:
    #             fixed_messages.append(msg)
    #     return fixed_messages

    def get_response(self, agent, query, tool_call_check=False, **kwargs):
        token_usage_dict = {
            "input": 0.0,
            "output": 0.0,
            "cached_input": 0.0,
            "reasoning": 0.0,
        }
        self.messages = [{"role": "system", "content": agent.system_prompt}]
        if kwargs.get('history'):
                self.messages += kwargs['history']
        if kwargs.get('dev_prompt', None):
            self.messages.append({"role": "developer", "content": kwargs['dev_prompt']})
        
        if kwargs.get('input_format', None):
            if isinstance(kwargs['input_format'], dict):
                self.messages.append({"role": "developer", "content": json.dumps(kwargs['input_format'])})
        else:
            if agent.input_format:
                self.messages.append({"role": "developer", "content": json.dumps(agent.input_format)})
        if not tool_call_check:
            if kwargs.get('context', None):
                query = json.dumps({'query': query, 'context': kwargs['context']})

            user_message = {"role": "user", 
                "content": [{
                            "type":"text", 
                            "text":f"{agent.user_prompt} \n {query}"}]
            }

            if kwargs.get('file_content'):
                # fixed_content = self._fix_content_types(kwargs['file_content'])
                # user_message['content'].extend(fixed_content)
                user_message['content'].extend(kwargs['file_content'])
            
            self.messages.append(user_message)
                
            # self.messages.extend(query)

        
        # self.messages = self._fix_all_messages(self.messages)

        params = {
            "temperature": kwargs.get("temperature", agent.temperature),
            "max_completion_tokens": kwargs.get("max_tokens", agent.max_tokens),
            "response_format": kwargs.get("response_format", agent.output_format),
            "n": kwargs.get('n', 1)
        }
        
        if agent.model != "gpt-5.1-chat":
            top_p = kwargs.get('top_p', agent.top_p)
            if top_p:
                params['top_p'] = top_p
        reasoning_effort = kwargs.get('reasoning_effort', agent.reasoning_effort)
        if reasoning_effort:
            params['reasoning_effort'] = reasoning_effort
        if agent.user_id:
            params['user'] = agent.user_id
        if agent.tools != []:
            params['tools'] = agent.tools
            params['tool_choice'] = agent.tool_choice
        if agent.web_search_options:
            params['web_search_options'] = agent.web_search_options
        # print("Recieved Message : ", self.messages)
        tool_calls = [None] * params['n']
        if kwargs.get('stream', agent.stream):
            tokenizer = kwargs.get('tokenizer', agent._tokenizer)
            with self.client.chat.completions.stream(
                messages=self.messages, #type: ignore
                model=agent.model,
                **params
            ) as stream:
                if not stream:
                    yield None, None, token_usage_dict, None, None
                    return None, None, token_usage_dict, None, None
                for event in stream:
                    if event.type == 'chunk':
                        content = [event.chunk.choices[num].delta.content for num in range(params['n'])]
                        if content != [None] * params['n'] and\
                            content != [] * params['n'] and\
                            content != [""] * params['n']:
                            yield 'content', content, token_usage_dict, None, None
                        messages = [event.snapshot.choices[num].message for num in range(params['n'])]
                        filters = [event.snapshot.choices[num].content_filter_results for num in range(params['n'])] # type: ignore
                tool_calls = [message.tool_calls for message in messages]
                token_usage_dict = {"input": float(len(tokenizer.encode(str(self.messages)))), 
                                    "output": float(sum([len(tokenizer.encode(str(choice))) for choice in messages])),
                                    "cached_input": 0.0,
                                    "reasoning": 0.0}
                    
        else:
            response = self.client.chat.completions.parse(  
                messages=self.messages, #type: ignore
                model=agent.model,
                **params
            ) # type: ignore
            if not response:
                yield None, None, token_usage_dict, None, None
                return None, None, token_usage_dict, None, None
            # print('got: ', response)
            messages = [response.choices[num].message for num in range(params['n'])]
            content = [response.choices[num].message.content for num in range(params['n'])]
            tool_calls = [response.choices[num].message.tool_calls for num in range(params['n'])]
            filters = [response.choices[num].content_filter_results for num in range(params['n'])] # type: ignore
            if content != [None] * params['n'] and\
                content != [] * params['n'] and\
                content != [""] * params['n']:
                yield 'content', content, token_usage_dict, None, None
            token_usage = response.usage # type: ignore
            token_usage_dict = {
                "input": float(token_usage.prompt_tokens), # type: ignore
                "output": float(token_usage.completion_tokens), # type: ignore
                "cached_input": float(token_usage.prompt_tokens_details.cached_tokens), # type: ignore
                "reasoning": float(token_usage.completion_tokens_details.reasoning_tokens) # type: ignore
            }
        
        yield 'stop', messages, token_usage_dict, filters, self.messages

        if tool_calls != [None] * params['n'] and\
            tool_calls != [] * params['n'] and\
            tool_calls != [""] * params['n']:
            print("calling tools: ", tool_calls)
            tools = [[{'id': tool.id,
                        'name': tool.function.name,
                        'arguments': tool.function.arguments} for tool in tool_call] for tool_call in tool_calls] # type: ignore
            yield 'tool', messages, token_usage_dict, tools, self.messages
    

    def attach_file(self, file_path: str):
        """
        Attaches a file to the context of the Azure OpenAI client.
        Args:
            file_path (str): The path to the file to be attached.
        Returns:
            dict: A dictionary containing the file attachment details.
        """
        with open(file_path, 'rb') as file:
            return self.client.files.create(file=file, purpose="assistants")
             
client_obj = AzureChatgpt(
    api_version="2024-12-01-preview",
    azure_endpoint="https://ed-gpt.openai.azure.com/",
    openai_api_key=openai_subscription_key
)
client = client_obj.client

deepseek_client_obj = AzureChatgpt(
    api_version="2024-05-01-preview",
    azure_endpoint="https://nanda-m6tufswd-eastus.services.ai.azure.com/",
    openai_api_key=deepseek_api_key
)
deepseek_client = deepseek_client_obj.client
