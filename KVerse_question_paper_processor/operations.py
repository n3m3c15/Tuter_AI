import requests
from typing import Tuple, List, Dict
import os, time
from dotenv import load_dotenv
import aiohttp

load_dotenv()


def preprocess_image(image_url: str, session_id: str) -> Tuple[List, List, Dict]:
    """
    Client function to call the deployed microservice for image preprocessing.
    Sends the image URL to the microservice which downloads and processes it.
    
    Args:
        image_url: URL of the image to process (e.g., blob storage URL)
        session_id: Session identifier for organizing uploaded files
        
    Returns:
        Tuple containing (detections, save_urls, image_content)
    """
    microservice_url = os.getenv('PREPROCESS_SERVICE_URL', 'http://localhost:8000')
    endpoint = f"{microservice_url}/api/preprocess-image"
    
    try:
        # Send JSON payload with image URL
        payload = {
            'image_url': image_url,
            'session_id': session_id
        }
        
        # Make POST request to microservice
        st = time.time()
        response = requests.post(
            endpoint,
            json=payload,
            timeout=120  # 120 second timeout for processing
        )
        print("YOLO Microservice API Call : ", time.time()-st)
        
        # Check response status
        if response.status_code == 200:
            result = response.json()
            return (
                result['detections'],
                result['diagram_urls'],
                result['cropped_image']
            )
        elif response.status_code == 400:
            error_detail = response.json().get('detail', 'Bad request')
            raise ValueError(f"Bad request: {error_detail}")
        elif response.status_code == 500:
            error_detail = response.json().get('detail', 'Internal server error')
            raise ValueError(f"Service error: {error_detail}")
        else:
            raise ValueError(f"Unexpected status code: {response.status_code}")
            
    except requests.exceptions.Timeout:
        raise ValueError("Request timeout - image processing took too long")
    except requests.exceptions.ConnectionError:
        raise ValueError(f"Cannot connect to preprocessing service at {microservice_url}")
    except ValueError:
        raise  # Re-raise ValueError as-is
    except Exception as e:
        raise ValueError(f"Error calling preprocessing service: {str(e)}")


async def preprocess_image_async(image_url: str, session_id: str) -> Tuple[List, List, Dict]:
    """
    Async version using aiohttp for non-blocking calls.
    """
    microservice_url = os.getenv('PREPROCESS_SERVICE_URL', 'http://localhost:8000')
    endpoint = f"{microservice_url}/api/preprocess-image"
    
    try:
        # Configure timeout
        timeout = aiohttp.ClientTimeout(total=120)
        
        payload = {
            'image_url': image_url,
            'session_id': session_id
        }
        
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.post(endpoint, json=payload) as response:
                if response.status == 200:
                    result = await response.json()
                    return (
                        result['detections'],
                        result['diagram_urls'],
                        result['cropped_image']
                    )
                elif response.status == 400:
                    error_data = await response.json()
                    raise ValueError(f"Bad request: {error_data.get('detail', 'Unknown error')}")
                elif response.status == 500:
                    error_data = await response.json()
                    raise ValueError(f"Service error: {error_data.get('detail', 'Internal server error')}")
                else:
                    raise ValueError(f"Unexpected status code: {response.status}")

    except aiohttp.ServerTimeoutError:
        raise ValueError("Request timeout - image processing took too long")              
    except aiohttp.ClientConnectionError:
        raise ValueError(f"Cannot connect to preprocessing service at {microservice_url}")
    except ValueError:
        raise  # Re-raise ValueError as-is
    except Exception as e:
        raise ValueError(f"Error calling preprocessing service: {str(e)}")
