On Mac (Build & Export)
bash
# Navigate to project directory
cd ~/Documents/career/forte/ds/rb_ocr/2025-11-14-apps-from-server-RBOCR/apps

# Rebuild both images (or just one if you only changed backend/ui)
docker compose build

# OR rebuild specific service only:
# docker compose build backend
# docker compose build ui

# Save images to tarballs
docker save -o rb-ocr-backend.tar rb-ocr-backend:latest
docker save -o rb-ocr-ui.tar rb-ocr-ui:latest

# Compress tarballs
gzip -f rb-ocr-backend.tar
gzip -f rb-ocr-ui.tar

# Verify files created
ls -lh *.tar.gz
On Server (Deploy)
bash
# Navigate to deployment directory
cd ~/rb-loan-deferment-idp

# Stop running containers
sudo docker compose down

# Remove old images
sudo docker rmi rb-ocr-backend:latest
sudo docker rmi rb-ocr-ui:latest

# Load new images (after transferring tarballs to ~/rb-loan-deferment-idp/docker-deploy/)
cd ~/rb-loan-deferment-idp/docker-deploy
sudo gunzip -c rb-ocr-backend.tar.gz | sudo docker load
sudo gunzip -c rb-ocr-ui.tar.gz | sudo docker load

# Verify images loaded
sudo docker images | grep rb-ocr

# Start containers
cd ~/rb-loan-deferment-idp
sudo docker compose up -d

# Check status
sudo docker compose ps
