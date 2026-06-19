from langchain.text_splitter import RecursiveCharacterTextSplitter 
from KVerse_language_engine.llm_utils import get_embeddings_openai
from KVerse_data_processor.data_config import chunking_config, sub_chapter_kwargs, chapter_kwargs
from KVerse_blob_storage.storage_utils import upload_to_blob
from KVerse_database_system.db_utils import update_document, retrieve_document

class UploadContent():
    def __init__(self, vector_store):
        self.vector_store = vector_store

    def chunk_text(self, text, granularity='chapter'):
        try:
            config = chunking_config[granularity]
        except KeyError as e:
            raise ValueError("Invalid granularity. Choose 'sub_chapter' or 'chapter'.")

        text_splitter = RecursiveCharacterTextSplitter(
            chunk_size = config['chunk_size'],
            chunk_overlap = config['chunk_overlap'],
            length_function = config['length_function']
        )   
        
        return text_splitter.split_text(text)
    
    def get_metadata(self, kwargs_template, content, granularity, chunk_num, **kwargs):
        metadata = dict()

        for key, value in kwargs_template.items():
            if value in kwargs:
                metadata[key] = kwargs[value]
        metadata['Content'] = content
        metadata['Granularity'] = granularity
        metadata['Chunk_Number'] = chunk_num
        
        return metadata
        
    def upload_text_content(self, content, granularity = 'chapter', namespace = None, **kwargs):
        all_vectors = list()
        if kwargs.get('chunk', True):
            chunks = self.chunk_text(content, granularity)
        else:
            chunks = [content]
        for num, chunk in enumerate(chunks):
            if granularity == 'sub_chapter':
                granularity_kwargs = sub_chapter_kwargs
            elif granularity == 'chapter':
                granularity_kwargs = chapter_kwargs
            metadata = self.get_metadata(granularity_kwargs, chunk, granularity, num, **kwargs)
            embeddings = get_embeddings_openai(chunk)
            all_vectors.append({
                'values' : embeddings,
                'metadata' : metadata
            })

        ret, vectors = self.vector_store.upsert_content_bulk(vector_list=all_vectors, namespace=namespace)
        if granularity == 'sub_chapter' and ret:
            subject_document = retrieve_document('Subject_Document', primary_key=kwargs['subject_code'])
            chapter_name = kwargs.get('chapter_name')
            sub_chapter_name = kwargs.get('sub_chapter_name')
            if not subject_document or not chapter_name or not sub_chapter_name:
                raise ValueError("Subject code, chapter name, and sub-chapter name must be provided for sub-chapter granularity.")
            subject_document = subject_document[0]
            chapters = subject_document.get('Chapters', {})
            if chapter_name not in chapters:
                chapters[chapter_name] = {}
            if sub_chapter_name not in chapters[chapter_name]:
                chapters[chapter_name][sub_chapter_name] = []
            chapters[chapter_name][sub_chapter_name].extend([vector['id'] for  vector in vectors]) 
            update_document(
                collection_name='Subject_Document',
                query={'Subject_Code': kwargs['subject_code']},
                updates={'Chapters': chapters})

        return ret, vectors
    
    def upload_image(self, image_path, image_size, image_description, page_number, book_name, chapter_name, subject_code, sub_chapter_name, namespace=None):
        url = upload_to_blob(image_path, subject_code)
        embeddings = get_embeddings_openai(image_description)
        metadata = {
            'Subject_Code' : subject_code,
            'Book_Index' : book_name,
            'Chapter_Index' : chapter_name,
            'Sub_Chapter_Index' : sub_chapter_name,
            'Content' : image_description,
            'URL' : url,
            'Granularity' : 'image',                                            
            'Page_Numbers' : page_number,
            'Image_Size' : image_size
        }

        return self.vector_store.upsert_content(embeddings=embeddings, metadata=metadata, namespace=namespace)
    
    def upload_note(self, note_content, page_number, book_name, chapter_name, subject_code, sub_chapter_name, namespace=None):
        embeddings = get_embeddings_openai(note_content)
        metadata = {
            'Subject_Code' : subject_code,
            'Book_Index' : book_name,
            'Chapter_Index' : chapter_name,
            'Sub_Chapter_Index' : sub_chapter_name,
            'Content' : note_content,
            'Granularity' : 'note',
            'Page_Numbers' : page_number
        }

        return self.vector_store.upsert_content(embeddings=embeddings, metadata=metadata, namespace=namespace)
        
