# Documentación Arquitectónica: Patrón Cache-Aside

Este documento detalla la implementación del patrón **Cache-Aside** (basado en la arquitectura recomendada por Microsoft Azure) en el backend de AgentWatch, y su relación con el Módulo 6 (Aplicación Móvil).

## 1. ¿Qué es el Patrón Cache-Aside?

Es una estrategia de arquitectura en la nube diseñada para proteger la base de datos principal (PostgreSQL) ante picos masivos de tráfico y reducir los tiempos de respuesta. Consiste en interponer una memoria ultrarrápida (Redis) entre la aplicación y la base de datos.

### Flujo implementado en los agentes:
1. **Lectura (Cache Hit):** La app intenta leer los agentes de Redis. Si están, responde en <10ms.
2. **Lectura (Cache Miss):** Si no están, va a PostgreSQL, extrae los datos, los **guarda en Redis** (con un TTL de 60s) y luego responde.
3. **Escritura e Invalidación:** Cuando un usuario crea, edita o pausa un agente, se actualiza PostgreSQL e inmediatamente se **borra (invalida)** la caché en Redis para garantizar la coherencia de datos.

---

## 2. Archivos Modificados e Implementación

La implementación fue puramente de backend, afectando los siguientes archivos:

1. **`requirements.txt`**: Se agregó la dependencia `redis==5.0.3`.
2. **`app/core/redis_client.py`**: Se creó un cliente de conexión a Redis tolerante a fallos (*fail-open*). Si el contenedor de Redis se cae, la app sobrevive ruteando todo a PostgreSQL silenciosamente.
3. **`app/routers/agents.py`**: Se aplicó la lógica de lectura e invalidación a los 4 endpoints principales que consume la app móvil:
   - `GET /api/v1/agents/` (Lista)
   - `GET /api/v1/agents/{id}` (Detalle)
   - `PATCH /api/v1/agents/{id}/state` (Pausar/Reactivar - Invalida Caché)
   - `POST /api/v1/agents/` (Crear - Invalida Caché)
4. **`tests/test_cache_aside.py`**: Se añadió una suite de pruebas unitarias usando *Mocking* que verifica matemáticamente los Cache Hits, Misses y borrados de memoria.

---

## 3. Caché Frontend vs. Caché Backend (Aclaración de Arquitectura)

Es vital entender que el proyecto Módulo 6 ahora cuenta con **dos niveles de caché independientes** que resuelven problemas distintos.

### Caché Frontend (Offline-First en la App Móvil)
- **Dónde vive:** En la memoria interna del teléfono celular (usando `expo-sqlite` y React Query).
- **Problema que resuelve:** La inestabilidad de la red. Si el usuario entra a un túnel, pierde conexión 4G o el servidor se cae, esta caché permite que la aplicación móvil siga funcionando de manera local.
- **Enfoque:** Resiliencia, Supervivencia sin red y Experiencia de Usuario Continua.

### Caché Backend (Cache-Aside con Redis)
- **Dónde vive:** En los servidores en la nube de la infraestructura backend, justo al lado de la base de datos PostgreSQL.
- **Problema que resuelve:** La latencia y la sobrecarga del servidor. Si el usuario **SÍ** tiene internet, pero hay 10,000 gerentes abriendo la app al mismo tiempo, esta caché responde las peticiones desde la RAM del servidor en milisegundos, evitando que la base de datos colapse.
- **Enfoque:** Rendimiento extremo (Speed) y Escalabilidad en la Nube.

> **💡 Analogía del Restaurante:**
> - **PostgreSQL (Base de Datos):** Es el Chef en la cocina. Hace el trabajo pesado y meticuloso.
> - **Cache-Aside Redis (Caché Backend):** Es el Mesero. Si varios clientes preguntan *"¿Cuál es la sopa del día?"*, el mesero se lo pregunta al chef una vez (*Cache Miss*), lo anota en su libreta, y a los demás les responde al instante sin ir a la cocina (*Cache Hit*).
> - **SQLite Móvil (Caché Frontend):** Es la memoria propia del Cliente. Si el cliente sale del restaurante a la calle (se queda sin internet), sigue recordando que la sopa era de tomate porque lo guardó en su mente.

---

## 4. Ejecución de Pruebas

Para verificar que el patrón de Cache-Aside no se ha roto tras futuras modificaciones al código, el proyecto cuenta con pruebas TDD que simulan la memoria RAM. Ejecuta el siguiente comando en la raíz del proyecto backend:

```bash
pytest tests/test_cache_aside.py
```
