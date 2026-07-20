# Stage 1: Build the React application
FROM node:20-alpine AS build
WORKDIR /app

# Install dependencies first to leverage Docker layer caching
COPY package*.json ./
RUN npm ci

# Copy source files and build the production assets
COPY . .
RUN npm run build

# Stage 2: Serve the assets using Nginx
FROM nginx:stable-alpine
# Copy the compiled production assets from Stage 1
COPY --from=build /app/dist /usr/share/nginx/html

# Copy our custom nginx configuration
COPY nginx.conf /etc/nginx/conf.d/default.conf

EXPOSE 80
CMD ["nginx", "-g", "daemon off;"]