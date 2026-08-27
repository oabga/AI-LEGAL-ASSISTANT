# Build SPA rồi serve tĩnh bằng nginx, nginx cũng proxy /api sang backend nên
# frontend và backend cùng origin (không cần CORS, SSE đi qua thoải mái).
FROM node:22-alpine AS build

WORKDIR /app

COPY package.json package-lock.json ./
RUN npm ci

COPY . .
# Để rỗng nghĩa là gọi API bằng đường dẫn tương đối, đúng cho trường hợp nginx
# cùng origin. Chỉ set khi backend nằm ở domain khác.
ARG VITE_API_BASE_URL=""
ENV VITE_API_BASE_URL=$VITE_API_BASE_URL
RUN npm run build

FROM nginx:1.27-alpine AS runtime

COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/dist /usr/share/nginx/html

EXPOSE 80
