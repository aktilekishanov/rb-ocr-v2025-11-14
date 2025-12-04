# forte-fx-complex

## Getting started

### Building and Deploying - Dev (local)
```bash
  docker build -t exchange-control .
  docker save exchange-control > exchange-control.tar
  scp exchange-control.tar dladmin@10.0.94.205:/home/dladmin/fxcomplex/docker-images
  docker compose -f docker-compose.dev.yml
  docker exec -it app_exchange_control sh
  alembic upgrade head
```
### Building and Deploying - Dev (local, only db and redis)
```bash
  docker build -t exchange-control .
  docker compose -f docker-compose.db.yml
  docker exec -it app_exchange_control sh
  alembic upgrade head
```
### Building and Deploying - Prod
```bash
  docker build -t exchange-control .
  docker compose -f docker-compose.prod.yml
  docker exec -it app_exchange_control sh
  alembic upgrade head
```