# Backend standards

- Instala dependencias de desarrollo: `pip install -r requirements-dev.txt`.
- Linter: `ruff check backend app tests`.
- Formato: `ruff format backend app tests`.

La configuración de reglas está en `ruff.toml` y la de indentado/fin de línea en `.editorconfig`.

## Base de datos
- Define `DATABASE_URL` con la cadena de conexión a PostgreSQL que vayas a usar; el backend toma ese valor directo (por ejemplo la URL que tienes en Render o en tu instancia local).  
- Si prefieres construir la URL manualmente, mantén `DB_TYPE=postgresql` y rellena `DB_HOST`, `DB_PORT`, `DB_USER`, `DB_PASSWORD` y `DB_NAME`; el módulo de base de datos usará `postgresql+psycopg2://...`.  
- Si alguna vez necesitas volver a MySQL/MaríaDB, cambia `DB_TYPE=mysql` y el sistema generará `mysql+pymysql://...`, de modo que el resto de la configuración no se modifica.
