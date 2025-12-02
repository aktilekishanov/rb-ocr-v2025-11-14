
FLOW:
1. USER uploads a file on mobile app
2. Mobile app sends a request to Kafka topic `dl-loan-delay.event.docs-uploaded`
3. Kafka topic is consumed by `RB Loan Deferment IDP` service
4. `RB Loan Deferment IDP` service downloads the file from MinIO
5. `RB Loan Deferment IDP` service sends a POST request to fastapi service `v1/verify` endpoint
6. `v1/verify` endpoint processes the file and returns a response and stores it in Database
7. `RB Loan Deferment IDP` service sends a POST request to UNKNOWN

------------------------------------------------------------------------------------

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
DOMAIN:     s3-dev.fortebank.com:9000
BUCKET:     loan-statements-dev
ACCESS KEY: fyz13d2czRW7l4sBW8gD
SECRET KEY: 1ixYVVoZKSnG0rwfvTy0vnqQplupXOOn8DF9gS1A
API:        s3v4
PATH:       auto

------------------------------------------------------------------------------------

