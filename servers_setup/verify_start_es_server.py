import subprocess
import time
import requests
import json
import os
import sys
import signal
import webbrowser
from datetime import datetime
from pathlib import Path
import uvicorn
from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
import logging
import threading
import random
import string

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Constants
ES_SERVER_PORT = 9200
FASTAPI_PORT = 8000
REPORT_PORT = 8011
ES_SERVER_SCRIPT = "servers_setup/start_es_server.py"
REPORT_DIR = "verification_reports"
REPORT_FILE = f"{REPORT_DIR}/verification_report.html"

# Global variables
es_server_process = None
report_app = FastAPI(title="ES Server Verification Report")
test_results = []
report_generated = False


def generate_random_string(length=10):
    """Generate a random string for testing"""
    return ''.join(random.choices(string.ascii_letters + string.digits, k=length))


def start_es_server():
    """Start the Elasticsearch server script"""
    global es_server_process
    
    # Create a new process to run the ES server
    es_server_process = subprocess.Popen(
        [sys.executable, ES_SERVER_SCRIPT],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True
    )
    
    # Wait for the server to start
    max_retries = 30
    for i in range(max_retries):
        try:
            # Check if Elasticsearch is running
            es_response = requests.get(f"http://localhost:{ES_SERVER_PORT}")
            if es_response.status_code == 200:
                # Check if FastAPI server is running
                api_response = requests.get(f"http://localhost:{FASTAPI_PORT}/docs")
                if api_response.status_code == 200:
                    logger.info("Elasticsearch and FastAPI servers started successfully")
                    return True
        except requests.exceptions.ConnectionError:
            pass
        time.sleep(1)
    
    logger.error("Failed to start Elasticsearch or FastAPI server")
    return False


def stop_es_server():
    """Stop the Elasticsearch server process"""
    global es_server_process
    if es_server_process:
        # Send SIGTERM to the process group
        os.killpg(os.getpgid(es_server_process.pid), signal.SIGTERM)
        es_server_process.wait(timeout=5)
        logger.info("Elasticsearch server stopped")


def run_test(test_name, test_func):
    """Run a test and record the result"""
    start_time = time.time()
    try:
        result = test_func()
        success = True
        message = "Test passed"
    except Exception as e:
        success = False
        message = f"Test failed: {str(e)}"
    
    duration = time.time() - start_time
    
    test_result = {
        "name": test_name,
        "success": success,
        "message": message,
        "duration": f"{duration:.2f}s",
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    }
    
    test_results.append(test_result)
    logger.info(f"Test '{test_name}': {'PASSED' if success else 'FAILED'} - {message}")
    
    return success


def test_elasticsearch_connection():
    """Test connection to Elasticsearch server"""
    response = requests.get(f"http://localhost:{ES_SERVER_PORT}")
    if response.status_code != 200:
        raise Exception(f"Elasticsearch server returned status code {response.status_code}")
    return True


def test_store_data():
    """Test storing data via the /storedata endpoint"""
    # Generate random test data
    test_text = f"Test data: {generate_random_string()}"
    test_auid = f"test_{generate_random_string(5)}"
    test_args = json.dumps({"test_key": "test_value"})
    
    # Store the data
    url = f"http://localhost:{FASTAPI_PORT}/storedata"
    params = {
        "text": test_text,
        "auid": test_auid,
        "additional_args": test_args
    }
    
    response = requests.get(url, params=params)
    if response.status_code != 200:
        raise Exception(f"Failed to store data: {response.text}")
    
    result = response.json()
    if result["status"] != "success":
        raise Exception(f"Store data returned error: {result}")
    
    return result["document_id"]


def test_get_data(auid):
    """Test retrieving data via the /getdata endpoint"""
    url = f"http://localhost:{FASTAPI_PORT}/getdata"
    params = {"auid": auid}
    
    response = requests.get(url, params=params)
    if response.status_code != 200:
        raise Exception(f"Failed to get data: {response.text}")
    
    result = response.json()
    if result["status"] != "success":
        raise Exception(f"Get data returned error: {result}")
    
    if result["count"] == 0:
        raise Exception(f"No documents found for auid: {auid}")
    
    return result["documents"]


def test_invalid_auid():
    """Test retrieving data with an invalid auid"""
    url = f"http://localhost:{FASTAPI_PORT}/getdata"
    params = {"auid": "nonexistent_auid"}
    
    response = requests.get(url, params=params)
    if response.status_code != 200:
        raise Exception(f"Failed to get data: {response.text}")
    
    result = response.json()
    if result["count"] != 0:
        raise Exception(f"Expected 0 documents for nonexistent auid, got {result['count']}")
    
    return True


def generate_html_report():
    """Generate an HTML report of the test results"""
    # Create report directory if it doesn't exist
    os.makedirs(REPORT_DIR, exist_ok=True)
    
    # Calculate summary statistics
    total_tests = len(test_results)
    passed_tests = sum(1 for r in test_results if r["success"])
    failed_tests = total_tests - passed_tests
    success_rate = (passed_tests / total_tests) * 100 if total_tests > 0 else 0
    
    # Generate HTML content
    html_content = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <title>Elasticsearch Server Verification Report</title>
        <style>
            body {{ font-family: Arial, sans-serif; margin: 20px; }}
            h1, h2 {{ color: #333; }}
            .summary {{ background-color: #f5f5f5; padding: 15px; border-radius: 5px; margin-bottom: 20px; }}
            .summary-item {{ margin: 5px 0; }}
            .test-results {{ border-collapse: collapse; width: 100%; }}
            .test-results th, .test-results td {{ border: 1px solid #ddd; padding: 8px; text-align: left; }}
            .test-results th {{ background-color: #f2f2f2; }}
            .test-results tr:nth-child(even) {{ background-color: #f9f9f9; }}
            .pass {{ color: green; }}
            .fail {{ color: red; }}
            .timestamp {{ color: #666; font-size: 0.9em; }}
        </style>
    </head>
    <body>
        <h1>Elasticsearch Server Verification Report</h1>
        <div class="timestamp">Generated on: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}</div>
        
        <div class="summary">
            <h2>Summary</h2>
            <div class="summary-item">Total Tests: {total_tests}</div>
            <div class="summary-item">Passed: <span class="pass">{passed_tests}</span></div>
            <div class="summary-item">Failed: <span class="fail">{failed_tests}</span></div>
            <div class="summary-item">Success Rate: {success_rate:.1f}%</div>
        </div>
        
        <h2>Test Results</h2>
        <table class="test-results">
            <tr>
                <th>Test Name</th>
                <th>Status</th>
                <th>Message</th>
                <th>Duration</th>
                <th>Timestamp</th>
            </tr>
    """
    
    # Add test results to the table
    for result in test_results:
        status_class = "pass" if result["success"] else "fail"
        status_text = "PASS" if result["success"] else "FAIL"
        
        html_content += f"""
            <tr>
                <td>{result["name"]}</td>
                <td class="{status_class}">{status_text}</td>
                <td>{result["message"]}</td>
                <td>{result["duration"]}</td>
                <td>{result["timestamp"]}</td>
            </tr>
        """
    
    # Close HTML tags
    html_content += """
        </table>
    </body>
    </html>
    """
    
    # Write the report to a file
    with open(REPORT_FILE, "w") as f:
        f.write(html_content)
    
    logger.info(f"HTML report generated: {REPORT_FILE}")
    return REPORT_FILE


@report_app.get("/", response_class=HTMLResponse)
async def get_report():
    """Serve the HTML report"""
    global report_generated
    
    if not report_generated:
        # Generate the report if it hasn't been generated yet
        report_path = generate_html_report()
        report_generated = True
    
    # Read the report file
    with open(REPORT_FILE, "r") as f:
        html_content = f.read()
    
    return HTMLResponse(content=html_content)


def run_verification():
    """Run all verification tests"""
    try:
        # Start the Elasticsearch server
        if not start_es_server():
            logger.error("Failed to start Elasticsearch server")
            return False
        
        # Run tests
        run_test("Elasticsearch Connection", test_elasticsearch_connection)
        
        # Test storing and retrieving data
        doc_id = run_test("Store Data", test_store_data)
        if doc_id:
            # Extract auid from the stored document
            auid = None
            try:
                # Get the document from Elasticsearch to extract auid
                response = requests.get(f"http://localhost:{ES_SERVER_PORT}/{ES_INDEX}/_doc/{doc_id}")
                if response.status_code == 200:
                    doc = response.json()
                    auid = doc["_source"]["auid"]
            except Exception as e:
                logger.error(f"Error extracting auid: {str(e)}")
            
            if auid:
                run_test("Get Data", lambda: test_get_data(auid))
        
        # Test with invalid auid
        run_test("Invalid AUID", test_invalid_auid)
        
        # Generate the report
        report_path = generate_html_report()
        
        # Start the report server
        report_thread = threading.Thread(
            target=lambda: uvicorn.run(
                report_app, 
                host="0.0.0.0", 
                port=REPORT_PORT
            )
        )
        report_thread.daemon = True
        report_thread.start()
        
        # Open the report in a browser
        webbrowser.open(f"http://localhost:{REPORT_PORT}")
        
        logger.info(f"Verification complete. Report available at http://localhost:{REPORT_PORT}")
        
        # Keep the script running to serve the report
        while True:
            time.sleep(1)
            
    except KeyboardInterrupt:
        logger.info("Verification interrupted by user")
    except Exception as e:
        logger.error(f"Verification failed: {str(e)}")
    finally:
        # Stop the Elasticsearch server
        stop_es_server()


if __name__ == "__main__":
    run_verification()
