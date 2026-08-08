# Stage 1: Build the React Application
FROM node:22-alpine AS builder
WORKDIR /app

COPY package*.json ./
RUN npm install
COPY . .

# Accept the API base URL from docker-compose and set it as an environment variable
ARG VITE_API_BASE_URL
ENV VITE_API_BASE_URL=$VITE_API_BASE_URL

# Compile the application for production
RUN npm run build

# Stage 2: Serve via Nginx
FROM nginx:alpine

# Copy compiled static assets
COPY --from=builder /app/dist /usr/share/nginx/html

# Copy custom Nginx routing configuration for SPA
COPY nginx.conf /etc/nginx/conf.d/default.conf

EXPOSE 80

CMD ["nginx", "-g", "daemon off;"]