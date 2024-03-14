import os
import json
import uuid
import urllib3
import boto3

from urllib.parse import urlparse
from botocore.config import Config
from botocore.exceptions import ClientError
from flask import Flask, jsonify, make_response, request

app = Flask(__name__)
app.config['DEBUG'] = True

# Initialize AWS clients
dynamodb_client = boto3.client('dynamodb')
textract_client = boto3.client('textract')
s3_client = boto3.client('s3', config=Config(signature_version='s3v4'))

# Check if running offline for DynamoDB
if os.environ.get('IS_OFFLINE'):
    dynamodb_client = boto3.client(
        'dynamodb', region_name='localhost', endpoint_url='http://localhost:8000'
    )

# Environment variable names
TABLE_NAME = os.environ['TABLE_NAME']
BUCKET_NAME = os.environ['BUCKET_NAME']

# Function to check if URL is valid
def is_valid_url(url):
    parsed_url = urlparse(url)
    return all([parsed_url.scheme, parsed_url.netloc])

# Route for getting upload url
@app.route('/files', methods=['POST'])
def get_upload_url():
    # Extract callback URL from request
    callback_url = request.json.get('callback_url')
    # Validate callback URL
    if not callback_url or not is_valid_url(callback_url):
        return jsonify({'error': 'Invalid callback URL supplied'}), 400

    # Generate unique file ID
    file_id = str(uuid.uuid4())

    # Store file metadata in DynamoDB
    dynamodb_client.put_item(
        TableName=TABLE_NAME,
        Item={'file_id': {'S': file_id}, 'callback_url': {'S': callback_url}},
    )

    # Generate presigned URL for uploading file to S3
    try:
        upload_url = s3_client.generate_presigned_url(
            ClientMethod='put_object',
            Params={'Bucket': BUCKET_NAME, 'Key': f'{file_id}'},
            ExpiresIn=3600,
            HttpMethod='PUT',
        )
    except ClientError as e:
        return jsonify({'error': str(e)}), 400

    # Return file ID and upload URL
    return jsonify({'file_id': file_id, 'upload_url': upload_url}), 201

# Route for retrieving textract result
@app.route('/files/<string:file_id>')
def get_result(file_id):
    # Retrieve file metadata from DynamoDB
    file = dynamodb_client.get_item(
        TableName=TABLE_NAME, Key={'file_id': {'S': file_id}}
    ).get('Item')

    # Check if file exists
    if not file:
        return jsonify({'error': 'File not found'}), 404

    # Retrieve text blocks associated with the file
    text_blocks = file.get('text', {}).get('SS', [])

    # Return file ID and text blocks
    return jsonify({'file_id': file_id, 'text': text_blocks}), 200

# Function to process uploaded file
def process_file(event, context):
    # Extract bucket and key from S3 event
    bucket = event['Records'][0]['s3']['bucket']['name']
    key = event['Records'][0]['s3']['object']['key']

    result = dynamodb_client.get_item(
        TableName=TABLE_NAME, Key={"file_id": {"S": key}}
    ).get("Item")

    # Use Textract to detect text in the document
    try:
        response = textract_client.detect_document_text(
            Document={'S3Object': {'Bucket': bucket, 'Name': key}}
        )
    except Exception as e:
        http = urllib3.PoolManager()
        callback_url = result.get('callback_url', {}).get('S', '').strip()
        response = http.request(
            'POST',
            callback_url,
            body=json.dumps({"file_id": key, 'error': 'Error with detecting text in document'}),
            headers={"Content-Type": "application/json"},
            retries=False
        )
        return jsonify({'error': str(e)}), 404

    # Extract text blocks from Textract response
    text_blocks = [block['Text'] for block in response['Blocks'] if block['BlockType'] == 'LINE']
    text_blocks_set = set(text_blocks)

    if len(text_blocks_set) == 0:
        http = urllib3.PoolManager()
        callback_url = result.get('callback_url', {}).get('S', '').strip()
        response = http.request(
            'POST',
            callback_url,
            body=json.dumps({"file_id": key, 'error': 'Error with detecting text in document'}),
            headers={"Content-Type": "application/json"},
            retries=False
        )
        return jsonify({'error': str(e)}), 404

    # Prepare item for DynamoDB update
    item = {
        'file_id': {'S': key},
        'callback_url': {'S': result.get('callback_url', {}).get('S', '')},
        'text': {'SS': list(text_blocks_set)}
    }

    # Update DynamoDB with extracted text
    dynamodb_client.put_item(TableName=TABLE_NAME, Item=item)

    return {'statusCode': 200}

# Function to handle callback after processing file
def callback(event, context):
    file_id = event['Records'][0]['dynamodb']['Keys']['file_id']['S']
    result = dynamodb_client.get_item(
        TableName=TABLE_NAME, Key={'file_id': {'S': file_id}}
    ).get('Item')

    # Check if file record exists
    if not result:
        return {
            'statusCode': 400,
            'body': json.dumps({'error': 'No record with specified file ID'})
        }

    # Retrieve text blocks from DynamoDB
    text_blocks = result.get('text', {}).get('SS', [])

    # Check if text blocks exist
    if not text_blocks:
        return {
            'statusCode': 400,
            'body': json.dumps({'error': 'No text blocks found for specified file ID'})
        }

    # Retrieve callback URL
    callback_url = result.get('callback_url', {}).get('S', '').strip()
    if not callback_url:
        return {
            'statusCode': 400,
            'body': json.dumps({'error': 'Callback URL not provided'})
        }

    # Prepare data for callback
    data = {'file_id': file_id, 'text': text_blocks}

    # Send callback request
    http = urllib3.PoolManager()
    response = http.request(
        'POST',
        callback_url,
        body=json.dumps(data),
        headers={"Content-Type": "application/json"},
        retries=False
    )

    return {'statusCode': response.status}

# Error handler for 404 Not Found
@app.errorhandler(404)
def resource_not_found(e):
    return make_response(jsonify(error='Not found!'), 404)
