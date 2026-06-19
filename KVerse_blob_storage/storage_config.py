from azure.storage.blob import BlobServiceClient
import dotenv
import os

#importing environment variables
dotenv.load_dotenv()

storage_account_name = os.getenv('storage_account_name')
storage_subscription_key = os.getenv('storage_subscription_key')
storage_connection_string = f"DefaultEndpointsProtocol=https;AccountName={storage_account_name};AccountKey={storage_subscription_key};EndpointSuffix=core.windows.net"


storage_client = BlobServiceClient.from_connection_string(
    conn_str=storage_connection_string
)

image_container_name = "imagecorpus"
image_container_client = storage_client.get_container_client(image_container_name)

temp_container_name = "temp-container"
temp_container_client = storage_client.get_container_client(temp_container_name)


allowed_mime_types = {
        "image/png",
        "image/jpeg",
        "image/jpg",
        "image/webp",
        "image/gif",
        "application/pdf",
        "application/msword",
        "application/json",
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "text/plain",
        "text/csv",
        "text/markdown",
        "text/html"
    }