# Stage 1: Build static React bundle
FROM node:20-alpine AS build
WORKDIR /app

ARG VITE_HOME_LATITUDE
ARG VITE_HOME_LONGITUDE
ARG VITE_TOMORROW_API_KEY
ENV VITE_HOME_LATITUDE=$VITE_HOME_LATITUDE
ENV VITE_HOME_LONGITUDE=$VITE_HOME_LONGITUDE
ENV VITE_TOMORROW_API_KEY=$VITE_TOMORROW_API_KEY

COPY package*.json ./
RUN npm install
COPY . .
RUN npm run build

# Stage 2: Serve static files via Nginx
FROM nginx:alpine
COPY --from=build /app/dist /usr/share/nginx/html
EXPOSE 80
CMD ["nginx", "-g", "daemon off;"]