from KVerse_data_processor.content_uploader import UploadContent
from KVerse_vector_space.vector_main import VectorStore

class BookUploader():
    def __init__(self, vector_store: VectorStore):
        self.content_uploader = UploadContent(vector_store)
    def get_chapter_index(self, book, chapter_name):
        pass

    def get_text_content(self, file_path):
        pass