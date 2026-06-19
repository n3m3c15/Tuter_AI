from threading import Thread
from pdf2image import convert_from_path
import io
import base64
import os
import uuid
from openai.types.chat.parsed_chat_completion import ParsedChatCompletionMessage
from openai.types.chat.parsed_function_tool_call import ParsedFunctionToolCall, ParsedFunction
import re

class ReturnThread(Thread):
    def __init__(self, group=None, target=None, name=None,
                 args=(), kwargs={}):
        Thread.__init__(self, group, target, name, args, kwargs)
        self._Thread__target = target
        self._Thread__args = args
        self._Thread__kwargs = kwargs
        self._return = None
    def run(self):
        self._return = self._Thread__target(*self._Thread__args, #type: ignore
                                            **self._Thread__kwargs)
    def join(self):
        Thread.join(self)
        return self._return

def convert_pdf_to_images(pdf_path):
    images = convert_from_path(pdf_path)
    return images

def convert_image_to_imguri(image):
    png_buffer = io.BytesIO()
    image.save(png_buffer, format="PNG")
    png_buffer.seek(0)

    base64_png = base64.b64encode(png_buffer.read()).decode('utf-8')

    data_uri = f"data:image/png;base64,{base64_png}"
    return data_uri

def delete_file(file_path):
    try:
        os.remove(file_path)
    except OSError as e:
        print(f"Error deleting file {file_path}: {e}")
        return False
    return True

def generate_uid() -> str:
    return str(uuid.uuid4())

def clean_history(raw: str) -> list:
    raw = re.sub('NoneType', 'None', raw)
    objects = eval(raw)
    return objects