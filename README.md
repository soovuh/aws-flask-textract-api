# Flask API service on AWS for text extraction

This API have 2 endpoints: 

POST /files - should accept callback_url for receiving callback when text extraction will be ended, and return upload_url for uploading files and file_id

GET /files/{file_id} - Should return information about results for specified file

## Usage
### Deployment

Clone repository:

```
git clone https://github.com/soovuh/aws-flask-textract-api.git
```

Go to severless app:

```
cd aws-python-flask-dynamodb-api-project
```

In order to deploy with dashboard, you need to first login with:

```
serverless login
```

Before running or making any changes, ensure to update the 'org' field in the file 'aws-python-flask-dynamodb-api-project/serverless.yml' with your org name:

```
org: <your_org_name>
```

install dependencies with:

```
npm install
```

and then perform deployment with:

```
serverless deploy
```

After running deploy, you should see output similar to:

```bash
Deploying aws-python-flask-dynamodb-api-project to stage dev (us-east-1)

✔ Service deployed to stack aws-python-flask-dynamodb-api-project-dev (182s)

endpoint: ANY - https://xxxxxxxx.execute-api.us-east-1.amazonaws.com
functions:
  api: aws-python-flask-dynamodb-api-project-dev-api (32 MB)
  process_file: aws-python-flask-dynamodb-api-project-dev-process_file (32 MB)
  callback: aws-python-flask-dynamodb-api-project-dev-callback (32 MB)
```

### API Endpoints

```
POST /files
```

#### When using POST endpoint, you need to specify callback_url in the body
Example:

```json
{"callback_url": "https://webhook.site/test"}
```

#### Response

```json
{
  "file_id": "4f2b223d-ae7a-42f0-9ee1-c2cdfcb9fbfa",
  "upload_url": "https://some_upload_url"
}
```

_Note_ file_id records to dynamoDB with callback_url, upload_url - the link where the client can send file using PUT request

```
PUT <upload_url>
```

#### Once the 'upload_url' is obtained, the client must send the file
```json
{
  "file_id": "4f2b223d-ae7a-42f0-9ee1-c2cdfcb9fbfa",
  "text": [
    "Some",
    "Text"
  ]
}
```
#### After successful uploading and processing, the user will receive a POST request to the callback URL

```json
{
  "file_id": "4f2b223d-ae7a-42f0-9ee1-c2cdfcb9fbfa",
  "error": "Error with detecting text in document",
}
```
#### Alternatively, response in case of an error

```
GET /files/{file_id}
```
#### Response will be similar to callback request body:

```json
{
  "file_id": "4f2b223d-ae7a-42f0-9ee1-c2cdfcb9fbfa",
  "text": [
    "Some",
    "Text"
  ]
}
```
