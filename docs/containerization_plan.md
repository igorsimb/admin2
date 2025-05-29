# Containerization Strategy for admin2

## Overview

This document describes the containerization strategy for the `admin2` Django project, focusing on both development and production environments. The project uses Docker, Docker Compose, and the `uv` dependency manager.

## 1. Service Architecture

### Core Services

- **Django** (admin2 web app)
  - Gunicorn for production
  - Development server for staging
  - Static/media file handling
  - Database migrations

- **Celery** (background task worker)
  - Eventlet pool for production
  - Standard pool for staging
  - Task queue management

- **Redis** (Celery broker/result backend)
  - Different ports for staging (6377) and production (6378)
  - Health checks implemented
  - Persistent storage

- **PostgreSQL** (Django database)
  - Custom configuration
  - Health checks
  - Data persistence
  - Initialization scripts

- **ClickHouse** (External database)
  - Connection to external server (87.242.110.159)
  - Read-only access for analytics

- **Nginx** (reverse proxy)
  - Static file serving
  - SSL termination (if needed)
  - Load balancing (if needed)
  - Different ports for staging (8071) and production (8061)

### Volumes

- **Static files**: `/app/static`
- **Media files**: `/app/media`
- **Database data**: 
  - PostgreSQL: `postgres_data`
  - Redis: `redis_data_prod` (production) or `redis_data_staging` (staging)
- **SQLite data** (staging only): `sqlite_data`

## 2. Environment Separation

### Staging Environment

- Uses `docker-compose.staging.yml`
- Development server for Django
- SQLite for database
- Port 8071 for Nginx
- Port 6377 for Redis
- Hot reload enabled
- Source code mounted as volume

### Production Environment

- Uses `docker-compose.production.yml`
- Gunicorn for Django
- PostgreSQL for database
- Port 8061 for Nginx
- Port 6378 for Redis
- No source code mounting
- Optimized for performance

## 3. Health Checks

### Redis Health Check
```yaml
healthcheck:
  test: ["CMD", "redis-cli", "ping"]
  interval: 5s
  timeout: 3s
  retries: 3
```

### PostgreSQL Health Check
```yaml
healthcheck:
  test: ["CMD", "pg_isready", "-U", "admin2"]
  interval: 5s
  timeout: 5s
  retries: 5
  start_period: 10s
```

### Service Dependencies
```yaml
depends_on:
  redis:
    condition: service_healthy
  db:
    condition: service_healthy
```

## 4. Deployment Workflow

### Production Deployment

1. SSH to server (87.242.110.159)
2. Git pull latest changes
3. Build and start services:
   ```bash
   docker-compose -f docker-compose.production.yml up --build -d
   ```
4. Access application at server IP:8061

### Staging Deployment

1. Local development:
   ```bash
   docker-compose -f docker-compose.staging.yml up --build
   ```
2. Access at localhost:8071

## 5. Environment Variables

### Required Variables

- **Django Settings**
  - `DJANGO_SECRET_KEY`
  - `DJANGO_DEBUG`
  - `DJANGO_ENVIRONMENT`

- **Database Settings**
  - PostgreSQL credentials
  - ClickHouse connection details

- **Redis/Celery Settings**
  - `CELERY_BROKER_URL`
  - `CELERY_RESULT_BACKEND`

- **Nginx Settings**
  - `PORT_NGINX`
  - `PORT_WEB`

## 6. Security Considerations

- No sensitive data in Dockerfiles
- Environment variables for secrets
- Proper file permissions
- Network isolation
- Regular security updates

## 7. Monitoring and Maintenance

### Logs
- Docker logs for all services
- Nginx access/error logs
- Django application logs
- Celery worker logs

### Maintenance Tasks
- Regular database backups
- Log rotation
- Security updates
- Performance monitoring

## 8. Troubleshooting

### Common Issues

1. **Redis Connection Issues**
   - Check Redis health check
   - Verify port mapping
   - Check network connectivity

2. **Database Connection Issues**
   - Verify PostgreSQL health
   - Check credentials
   - Verify network connectivity

3. **Static Files Issues**
   - Check volume mounts
   - Verify collectstatic
   - Check Nginx configuration

### Debug Commands

```bash
# Check service status
docker-compose ps

# View logs
docker-compose logs -f [service]

# Check Redis
docker-compose exec redis redis-cli ping

# Check PostgreSQL
docker-compose exec db pg_isready -U admin2
```

## 9. Best Practices

1. **Always use health checks**
2. **Proper service dependencies**
3. **Environment-specific configurations**
4. **Regular backups**
5. **Security-first approach**
6. **Proper logging**
7. **Resource limits**
8. **Regular updates**

## 10. Future Improvements

1. **CI/CD Integration**
2. **Automated backups**
3. **Monitoring system**
4. **Load balancing**
5. **SSL/TLS configuration**
6. **Container resource limits**
7. **Automated testing**

## 11. References

- [Docker Documentation](https://docs.docker.com/)
- [Docker Compose Documentation](https://docs.docker.com/compose/)
- [Django Deployment Checklist](https://docs.djangoproject.com/en/5.0/howto/deployment/checklist/)
- [Nginx Documentation](https://nginx.org/en/docs/)
- [Redis Documentation](https://redis.io/documentation)
- [PostgreSQL Documentation](https://www.postgresql.org/docs/)
