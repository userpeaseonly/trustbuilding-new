---
name: Migration Workflow Rule
description: Defines the correct workflow for running Django migrations in this Dockerized environment.
---

# Migration Workflow

When dealing with database migrations in this project, follow this rule strictly:

1. **`makemigrations`**: ALWAYS execute `python manage.py makemigrations` outside of the Docker container on the host machine. Do not run it inside the container.
2. **`migrate`**: NEVER run `python manage.py migrate` manually (neither inside nor outside the container). The user will stop and restart the Docker container, which automatically executes the migrate command during its startup sequence.
