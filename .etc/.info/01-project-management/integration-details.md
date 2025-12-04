&lt;!-- STATUS: KEEP - CRITICAL REFERENCE. Contains Kafka integration details, MinIO S3 credentials, and event body schema. Required for upcoming Kafka integration work (see todo.md). --&gt;

FLOW:
1. USER uploads a file on mobile app
2. Mobile app sends a request to Kafka topic `dl-loan-delay.event.docs-uploaded`
3. Kafka topic is consumed by `RB Loan Deferment IDP` (us):
    the event body is:
    {
        "request_id": 123123,
        "document_type": 4,
        "s3_path": "some_s3_address",
        "iin": 960125000000,
        "first_name": "Иван",
        "last_name": "Иванов",
        "second_name": "Иванович",  
    }
4. `RB Loan Deferment IDP` (us) take the `s3_path` and downloads the file from their MinIO
5. `RB Loan Deferment IDP` (us) passes the file with fio via sending a POST request to our fastapi service `v1/verify` endpoint
6.  Our fastapi service `v1/verify` endpoint processes the file and returns a response and stores it in our Database
7. `RB Loan Deferment IDP` (us) service takes the response from our fastapi service and sends a POST request to them (currently unknown which api endpoint)

------------------------------------------------------------------------------------

10.0.94.86:9092
10.0.94.87:9092
10.0.94.88:9092

group id: nohd_MSB

KAFKA TOPIC: dl-loan-delay.event.docs-uploaded
EVENT BODY:
{
    "request_id": 123123,
    "document_type": 4,
    "s3_path": "some_s3_address",
    "iin": 960125000000,
    "first_name": "Иван",
    "last_name": "Иванов",
    "second_name": "Иванович",  
}

------------------------------------------------------------------------------------

DEV MINIO:
IP:         10.0.99.212
DOMAIN:     s3-dev.fortebank.com:9443
BUCKET:     loan-statements-dev
ACCESS KEY: fyz13d2czRW7l4sBW8gD
SECRET KEY: 1ixYVVoZKSnG0rwfvTy0vnqQplupXOOn8DF9gS1A
API:        s3v4
PATH:       auto

------------------------------------------------------------------------------------

