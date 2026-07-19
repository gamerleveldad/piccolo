# ==========================================
# STAGE 1: Build the React Frontend
# ==========================================
FROM node:20-alpine AS frontend-builder
WORKDIR /build

# Copy everything from the frontend folder
COPY frontend/ ./

# Nuke copied Windows node_modules, do a clean Linux install, and build
RUN rm -rf node_modules && npm install && npm run build

# ==========================================
# STAGE 2: Build the Python Backend
# ==========================================
FROM python:3.11-slim
WORKDIR /app

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy Python backend code
COPY . .

# Extract ONLY the compiled static files from Stage 1
RUN mkdir -p static
COPY --from=frontend-builder /build/dist/ ./static/

# Expose ports
EXPOSE 8000
EXPOSE 50222/udp

# Launch Uvicorn using standard asyncio loop
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000", "--loop", "asyncio"]