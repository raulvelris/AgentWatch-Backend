# Estrategias de Despliegue Seguro - Prototipo Jenkins + Docker para AgentWatch-Backend (Modo Local)

Este documento detalla cómo configurar y ejecutar la estrategia de **Recreate Deployment** con **Health Check** y **Rollback Automático** utilizando tu Jenkins y Docker locales, **sin necesidad de usar GitHub**. El script está diseñado para ser copiado y pegado directamente en la interfaz de Jenkins.

---

## 1. Estructura del Entorno

Los archivos agregados a `AgentWatch-Backend` son:

```text
AgentWatch-Backend/
│
├── Jenkinsfile                  # Código del pipeline listo para copiar y pegar en Jenkins
├── jenkins-local/
│   └── Dockerfile               # Dockerfile para levantar un Jenkins local con soporte Docker CLI
└── DESPLIEGUE_SEGURO_JENKINS.md # Estas instrucciones
```

---

## 2. Preparación de Jenkins en Local (DooD - Docker-out-of-Docker)

Para que el contenedor de Jenkins pueda construir y desplegar imágenes Docker en tu misma máquina local, se enlaza el socket de Docker.

### Paso 2.1: Construir la imagen personalizada de Jenkins
Abre una terminal en la carpeta de Jenkins y construye la imagen:

```bash
cd AgentWatch-Backend/jenkins-local
docker build -t jenkins-docker-local .
```

### Paso 2.2: Levantar el contenedor de Jenkins con la carpeta del proyecto montada
Ejecuta el siguiente comando para iniciar Jenkins. El volumen `-v` monta la carpeta del proyecto de tu PC en la ruta `/var/jenkins_workspace` dentro de Jenkins:

**En Windows (PowerShell):**
```powershell
docker run -d `
  -p 8080:8080 `
  -p 50000:50000 `
  --name jenkins-agentwatch `
  -v //var/run/docker.sock:/var/run/docker.sock `
  -v jenkins_home_agentwatch:/var/jenkins_home `
  -v ${PWD}/..:/var/jenkins_workspace `
  jenkins-docker-local
```

---

## 3. Configuración y Copiar/Pegar en Jenkins

1. Abre tu navegador en `http://localhost:8080` (la contraseña inicial se obtiene con `docker logs jenkins-agentwatch`).
2. Crea un nuevo ítem de tipo **Pipeline** (llámalo `AgentWatch-Backend-Local`).
3. En la configuración del proyecto:
   - Marca la casilla **This project is parameterized** (Este proyecto está parametrizado).
   - Agrega un parámetro de tipo **Choice Parameter** (Parámetro de elección):
     - **Name:** `RELEASE`
     - **Choices:**
       ```text
       v1
       v2
       v2-error
       ```
     - **Description:** `Selecciona la versión a desplegar. v2-error simula un fallo para probar el rollback automático.`
4. En la sección **Pipeline**:
   - En **Definition**, selecciona **Pipeline script** (manual).
   - Abre el archivo `Jenkinsfile` de tu carpeta del proyecto, **copia todo su contenido** y **pégalo** en el cuadro de texto de Jenkins.
5. Guarda los cambios.

---

## 4. Ejecución de los Escenarios de Despliegue Seguro

Haz clic en **Build with Parameters** en el menú de la izquierda y prueba los escenarios:

### Escenario 1: Versión Estable (`v1`)
- Selecciona `v1` y ejecuta.
- Jenkins construirá la imagen `agentwatch-backend:v1`, desplegará el contenedor y pasará el Health Check (HTTP 200). El pipeline finaliza con éxito (**SUCCESS**).

### Escenario 2: Nueva Versión (`v2`)
- Selecciona `v2` y ejecuta.
- Se actualizará el contenedor a la versión `v2`. Al responder correctamente al Health Check, se confirma el despliegue (**SUCCESS**).

### Escenario 3: Fallo y Rollback Automático (`v2-error`)
- Selecciona `v2-error` y ejecuta.
- Se desplegará el contenedor inyectando `SIMULATE_ERROR=true`.
- Al llegar al **Health Check**, el endpoint `/health` del backend responderá con código `500`.
- El pipeline marcará la etapa como fallida y ejecutará la sección `post { failure }` (Rollback), que detiene el contenedor erróneo y vuelve a levantar la versión estable `v1` de forma inmediata.
