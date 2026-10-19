#!/bin/sh
# Rebuild the image and replace the running container (old one keeps serving until the build succeeds)
cd "$(dirname "$0")"
docker compose up -d --build
