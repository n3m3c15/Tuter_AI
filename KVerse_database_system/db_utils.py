from typing import Dict, Any
from bson import ObjectId   
from KVerse_database_system.schemas import primary_key_dict
from KVerse_database_system.db_config import db_client
from pymongo.database import Database

def structure(collection_name:str, schema: Dict[str, Any], db_client: Database = db_client, **kwargs): 
    document = dict() 
    for field, param_name in schema.items():
        if param_name in kwargs:
            document[field] = kwargs[param_name]
        elif callable(param_name):
            document[field] = param_name()
        else:
            document[field] = param_name

    id = upsert_document(collection_name, document, db_client)
    document['_id'] = id
    return document

def retrieve_document(collection_name: str, document_id: str|None = None, primary_key: str|None = None, multiple_keys: dict|None = None, db_client: Database = db_client) -> list[Any]:
    document = list()
    if not collection_name in db_client.list_collection_names():
        raise ValueError(f"Collection '{collection_name}' does not exist")
    collection = db_client[collection_name]
    if not document_id and not primary_key and not multiple_keys:
        raise ValueError("Either document_id or primary_key  or multiple_keys must be provided")
    if document_id:
        try:
            document = [collection.find_one({'_id': document_id})]
        except Exception as e:
            raise ValueError(f"Invalid document ID format: {e}")
    elif primary_key:
        if collection_name not in primary_key_dict:#changed
            raise ValueError(f"Collection '{collection_name}' is not defined in primary_key_dict")
        query = {primary_key_dict[collection_name]: primary_key}
        try:
            document = [collection.find_one(query)]
        except Exception as e:
            raise ValueError(f"Error retrieving document with primary key '{primary_key}': {e}")
    elif multiple_keys:
        if not isinstance(multiple_keys, dict):
            raise ValueError("multiple_keys must be a non-empty dictionary")
        try:
            document_cursor = collection.find(multiple_keys)
            document = list(document_cursor)
        except Exception as e: 
            raise ValueError(f"Error retrieving document with multiple keys {multiple_keys}: {e}")
    for doc in document:
        if doc is not None and '_id' in doc:
            del doc['_id']
    return document

def create_collection(collection_name: str, db_client: Database = db_client):
    if collection_name in db_client.list_collection_names():
        raise ValueError(f"Collection '{collection_name}' already exists")
    db_client.create_collection(collection_name)
    return f"Collection '{collection_name}' created successfully"

def upsert_document(collection_name: str, document: Dict[str, Any], db_client: Database = db_client):
    if collection_name not in db_client.list_collection_names():
        raise ValueError(f"Collection '{collection_name}' does not exist")
    collection = db_client[collection_name]
    if "name" in document:
        existing_doc = collection.find_one({"name": document["name"]})
        if existing_doc and (
            "_id" not in document or str(existing_doc["_id"]) != str(document["_id"])
        ):
            raise ValueError(f"Document with name '{document['name']}' already exists")
    if '_id' in document:
        try:
            document['_id'] = ObjectId(document['_id'])
        except Exception as e:
            raise ValueError(f"Invalid '_id' format: {e}")
        result = collection.replace_one({'_id': document['_id']}, document, upsert=True)
    else:
        result = collection.insert_one(document)

    return result

def update_document(collection_name: str , updates: Dict[str, Any], query : Dict[str,Any]|None=None, document_id: str|None = None,db_client: Database = db_client):
    if not collection_name in db_client.list_collection_names():
        raise ValueError(f"Collection '{collection_name}' does not exist")
    if not document_id and not query:
        raise ValueError("Document ID or Query must be provided")
    collection = db_client[collection_name]
    if document_id:
        try:
            obj_id = ObjectId(document_id)
        except Exception as e:
            raise ValueError(f"Invalid document ID format: {e}")
        result = collection.update_one({'_id': obj_id}, {'$set': updates})
        if result.matched_count == 0:
            raise ValueError(f"No document found with _id: {document_id}")
    elif query:
        result= collection.update_many(query,{'$set': updates})
        if result.matched_count == 0:
            raise ValueError(f"No documents found with query: {query}")
    return f"Document with _id: {document_id} updated successfully"

def delete_document(collection_name: str, document_id: str|None = None, multiple_keys: dict|None = None, db_client: Database = db_client):
    if not document_id and not multiple_keys:
        raise ValueError("Document ID or multiple_keys must be provided")
    if not collection_name in db_client.list_collection_names():   
        raise ValueError(f"Collection '{collection_name}' does not exist")
    collection = db_client[collection_name]
    if document_id:
        try:
            obj_id = ObjectId(document_id)
        except Exception as e:  
            raise ValueError(f"Invalid document ID format: {e}")
        result = collection.delete_one({'_id': obj_id})
        if result.deleted_count == 0:
            raise ValueError(f"No document found with _id: {document_id}")  
    elif multiple_keys:
        if not isinstance(multiple_keys, dict):
            raise ValueError("multiple_keys must be a non-empty dictionary")
        result = collection.delete_many(multiple_keys)
        if result.deleted_count == 0:
            raise ValueError(f"No documents found with keys: {multiple_keys}")
    return f"Document with _id: {document_id} deleted successfully"

def delete_collection(collection_name: str, db_client: Database = db_client):
    if not collection_name in db_client.list_collection_names():
        raise ValueError(f"Collection '{collection_name}' does not exist")
    if collection_name not in db_client.list_collection_names():
        raise ValueError(f"Collection '{collection_name}' does not exist")
    db_client.drop_collection(collection_name)
    return f"Collection '{collection_name}' deleted successfully"
# Example usage:
#create_collection("Test_Collection")

# def test_create_collection():
#     print(create_collection("Test_Collection"))
# #test_create_collection()
# def test_upsert():
#     doc = {
#         "name": "Test Document",
#         "value": 123
#     }
#     print(upsert_document("Test_Collection", doc))
# #test_upsert()

# def test_update():
#     # Replace with a valid document ID from your collection
#     document_id = "68e63414b3e4abbf3aebd708"  
#     updates = {
#         "name": "Updated Document",
#         "value": 456,
#         "new_field": "Added"
#     }
#     print(update_document("Test_Collection", document_id, updates))
# #test_update()
# def test_delete():
#     document_id = "68e63414b3e4abbf3aebd708"         
#     print(delete_document("Test_Collection", document_id))
# #test_delete()

# def test_delete_collection():
#     print(delete_collection("Test_Collection"))

# test_delete_collection()
