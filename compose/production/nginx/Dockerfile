FROM nginx:latest

COPY compose/production/nginx/nginx.conf /etc/nginx/nginx.conf
COPY static/ /var/www/static/
COPY media/ /var/www/media/

EXPOSE 80
