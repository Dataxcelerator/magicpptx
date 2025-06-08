import os
import subprocess
import time
import json
import logging
from typing import Dict, Any, Optional
import uvicorn
from fastapi import FastAPI, HTTPException, Query
from elasticsearch import Elasticsearch
from pydantic import BaseModel
import requests
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Constants
ES_PORT = 9200
ES_INDEX = "documentation_data"
FASTAPI_PORT = 8000
ES_DOWNLOAD_URL = (
    "https://artifacts.elastic.co/downloads/elasticsearch/"
    "elasticsearch-8.12.1-linux-x86_64.tar.gz"
)
ES_DIR = "elasticsearch-8.12.1"
KIBANA_PORT = 5601
KIBANA_DOWNLOAD_URL = (
    "https://artifacts.elastic.co/downloads/kibana/"
    "kibana-8.12.1-linux-x86_64.tar.gz"
)
KIBANA_DIR = "kibana-8.12.1"

# Data model for storing documentation
class DocumentData(BaseModel):
    text: str
    auid: str
    additional_args: Optional[Dict[str, Any]] = None

# Initialize FastAPI app
app = FastAPI(title="Documentation Storage API")

# Global Elasticsearch client
es_client = None

def download_elasticsearch():
    """Download Elasticsearch if not already present"""
    if not os.path.exists(ES_DIR):
        logger.info(f"Downloading Elasticsearch from {ES_DOWNLOAD_URL}")
        subprocess.run(["wget", ES_DOWNLOAD_URL], check=True)
        subprocess.run(
            ["tar", "-xzf", "elasticsearch-8.12.1-linux-x86_64.tar.gz"], 
            check=True
        )
        logger.info("Elasticsearch downloaded and configured")

def start_elasticsearch():
    """Start Elasticsearch server"""
    if not os.path.exists(ES_DIR):
        download_elasticsearch()
    
    # Check if Elasticsearch is already running
    try:
        response = requests.get(f"http://localhost:{ES_PORT}")
        if response.status_code == 200:
            logger.info("Elasticsearch is already running")
            return
    except requests.exceptions.ConnectionError:
        pass
    
    # Start Elasticsearch
    logger.info("Starting Elasticsearch server...")
    # Start the process but don't capture output to avoid blocking
    subprocess.Popen(
        [f"{ES_DIR}/bin/elasticsearch"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL
    )
    
    # Wait for Elasticsearch to start
    max_retries = 30
    for i in range(max_retries):
        try:
            response = requests.get(f"http://localhost:{ES_PORT}")
            if response.status_code == 200:
                logger.info("Elasticsearch server started successfully")
                return
        except requests.exceptions.ConnectionError:
            pass
        time.sleep(1)
    
    # If we get here, Elasticsearch didn't start
    logger.error("Failed to start Elasticsearch server")
    raise RuntimeError("Elasticsearch server failed to start")

def setup_elasticsearch_index():
    """Create Elasticsearch index if it doesn't exist"""
    global es_client
    es_client = Elasticsearch(
        f"https://localhost:{ES_PORT}",
        basic_auth=("elastic", "YgUkMD5Ea9VWEe3QhOJI"),
        verify_certs=False
    )
    
    # Check if index exists
    if not es_client.indices.exists(index=ES_INDEX):
        # Create index with mapping
        mapping = {
            "mappings": {
                "properties": {
                    "text": {"type": "text"},
                    "auid": {"type": "keyword"},
                    "additional_args": {"type": "object"},
                    "timestamp": {"type": "date"}
                }
            }
        }
        es_client.indices.create(index=ES_INDEX, body=mapping)
        logger.info(f"Created Elasticsearch index: {ES_INDEX}")

def download_kibana():
    """Download Kibana if not already present"""
    if not os.path.exists(KIBANA_DIR):
        logger.info(f"Downloading Kibana from {KIBANA_DOWNLOAD_URL}")
        subprocess.run(["wget", KIBANA_DOWNLOAD_URL], check=True)
        subprocess.run(
            ["tar", "-xzf", "kibana-8.12.1-linux-x86_64.tar.gz"],
            check=True
        )
        logger.info("Kibana downloaded and extracted")

def start_kibana():
    """Start Kibana server"""
    if not os.path.exists(KIBANA_DIR):
        download_kibana()

    # Check if Kibana is already running
    try:
        response = requests.get(f"http://localhost:{KIBANA_PORT}")
        if response.status_code == 200:
            logger.info("Kibana is already running")
            return
    except requests.exceptions.ConnectionError:
        pass

    logger.info("Starting Kibana server...")
    subprocess.Popen(
        [f"{KIBANA_DIR}/bin/kibana"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL
    )

    # Wait for Kibana to start
    max_retries = 60
    for i in range(max_retries):
        try:
            response = requests.get(f"http://localhost:{KIBANA_PORT}")
            if response.status_code == 200:
                logger.info("Kibana server started successfully")
                return
        except requests.exceptions.ConnectionError:
            pass
        time.sleep(1)
    logger.error("Failed to start Kibana server")
    raise RuntimeError("Kibana server failed to start")

@app.on_event("startup")
async def startup_event():
    """Start Elasticsearch and setup index on FastAPI startup"""
    start_elasticsearch()
    setup_elasticsearch_index()
    start_kibana()

@app.get("/storedata")
async def store_data(
    text: str = Query(..., description="Textual data to store"),
    auid: str = Query(..., description="Unique identifier for the data"),
    additional_args: Optional[str] = Query(
        None, description="JSON string of additional arguments"
    )
):
    """
    Store data in Elasticsearch
    
    Args:
        text: Textual data to store
        auid: Unique identifier for the data
        additional_args: Optional JSON string of additional arguments
    
    Returns:
        Dict with status and document ID
    """
    try:
        # Parse additional_args if provided
        additional_args_dict = json.loads(additional_args) if additional_args else {}
        
        # Create document
        document = {
            "text": text,
            "auid": auid,
            "additional_args": additional_args_dict,
            "timestamp": time.time()
        }
        
        # Store in Elasticsearch
        result = es_client.index(index=ES_INDEX, document=document)
        
        return {
            "status": "success",
            "message": "Data stored successfully",
            "document_id": result["_id"]
        }
    except Exception as e:
        logger.error(f"Error storing data: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error storing data: {str(e)}")

@app.get("/getdata")
async def get_data(
    auid: str = Query(..., description="Unique identifier to retrieve data")
):
    """
    Retrieve data from Elasticsearch based on auid
    
    Args:
        auid: Unique identifier to retrieve data
    
    Returns:
        List of documents matching the auid
    """
    try:
        # Search for documents with matching auid
        query = {
            "query": {
                "term": {
                    "auid": auid
                }
            },
            "sort": [
                {"timestamp": {"order": "desc"}}
            ]
        }
        
        result = es_client.search(index=ES_INDEX, body=query)
        
        # Extract and return documents
        documents = []
        for hit in result["hits"]["hits"]:
            doc = hit["_source"]
            doc["document_id"] = hit["_id"]
            documents.append(doc)
        
        return {
            "status": "success",
            "count": len(documents),
            "documents": documents
        }
    except Exception as e:
        logger.error(f"Error retrieving data: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error retrieving data: {str(e)}")

if __name__ == "__main__":
    # Start FastAPI server
    uvicorn.run(app, host="0.0.0.0", port=FASTAPI_PORT)
