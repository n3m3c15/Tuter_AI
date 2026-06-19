from KVerse_blob_storage.storage_config import image_container_client, storage_client, temp_container_client
import os
from fastapi import UploadFile

def upload_to_blob(file_path, blob_path, container_client = image_container_client):
    file_name = file_path.split("/")[-1]
    blob_name = f"{blob_path}/{file_name}"
    with open(file_path, "rb") as data:
        blob_client = container_client.get_blob_client(blob_name)
        blob_client.upload_blob(data, overwrite=True)
        return blob_client.url
    
def download_from_url(url, ouput_folder="downloads"):
    if not os.path.exists(ouput_folder):
        os.makedirs(ouput_folder)
    
    file_name = url.split("/")[-1]
    output_path = os.path.join(ouput_folder, file_name) 
    
    import requests
    response = requests.get(url)
    
    if response.status_code == 200:
        with open(output_path, 'wb') as f:
            f.write(response.content)
        return output_path   
    else:
        raise Exception(f"Failed to download file from {url}. Status code: {response.status_code}")


def upload_file_to_blob(upload_file: "UploadFile",user_id:str,session_id:str, container_client=temp_container_client):
    """
    Uploads an UploadFile object directly to Azure Blob Storage.
    """
    file_name = upload_file.filename
    blob_name = f"{user_id}/{session_id}/{file_name}"   
    upload_file.file.seek(0) 
    mime_type = upload_file.content_type     
    blob_client = container_client.get_blob_client(blob_name)
    blob_client.upload_blob(upload_file.file, overwrite=True)
    blob_url = blob_client.url
    return blob_url, mime_type, file_name