# PlatformOps local PostgreSQL

PlatformOps uses PostgreSQL for both local development and production. This
compose service is the local development database; it is separate from the
Authentik development database.

```sh
export PLATFORMOPS_POSTGRES_PASSWORD='choose-a-local-secret'
docker compose -f deploy/platformops-postgres/docker-compose.yml up -d
export PLATFORMOPS_DATABASE_URL='postgresql://platformops:choose-a-local-secret@localhost:5432/platformops_dev'
```

Run PostgreSQL integration tests only against an isolated development/test
database. They create and remove only the registration tables defined by the
user-registration migration.
