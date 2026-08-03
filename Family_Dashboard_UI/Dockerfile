# Step 1: Build React application using Vite
FROM node:20-alpine AS build
WORKDIR /app

COPY package*.json ./
RUN npm ci

COPY . .

ARG VITE_BACKEND_HOST
ARG VITE_BACKEND_PORT
ENV VITE_BACKEND_HOST=$VITE_BACKEND_HOST
ENV VITE_BACKEND_PORT=$VITE_BACKEND_PORT

RUN npm run build

# Step 2: Serve static production assets via Nginx
FROM nginx:alpine

COPY --from=build /app/dist /usr/share/nginx/html
# Custom Nginx configuration supporting React Single Page Application routing
COPY nginx.conf /etc/nginx/conf.d/default.conf

EXPOSE 80

CMD ["nginx", "-g", "daemon off;"]