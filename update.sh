#!/bin/bash

# Check if at least one container argument was provided
if [ $# -eq 0 ]; then
  echo "Error: Please provide at least one container name."
  echo "Usage: ./update.sh <container_name1> [container_name2 ...]"
  echo "Example: ./update.sh family_dashboard game_scanner_api"
  exit 1
fi

echo "[1/4] Pulling latest changes from Git..."
git pull origin main

echo "[2/4] Rebuilding Docker images for: $@"
sudo docker compose build "$@"

echo "[3/4] Recreating containers for: $@"
sudo docker compose up -d "$@"

echo "[4/4] Cleaning up unused system images..."
sudo docker image prune -f

echo "Deployment complete for: $@"