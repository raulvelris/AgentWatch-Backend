/*
================================================================================
SCRIPT PARA COPIAR Y PEGAR EN JENKINS (SIN USAR GITHUB)
================================================================================
Instrucciones:
1. Crea un proyecto de tipo "Pipeline" en tu Jenkins local.
2. Marca la casilla "This project is parameterized" y añade un Choice Parameter:
   - Name: RELEASE
   - Choices: v1, v2, v2-error
3. Ve a la sección "Pipeline", selecciona "Pipeline script" en Definition.
4. Copia todo este código y pégalo en el cuadro de texto.
5. Haz clic en "Guardar" y luego en "Build with Parameters".

Nota de directorio local:
Este script asume que has montado la carpeta del proyecto en el contenedor de Jenkins
en la ruta '/var/jenkins_workspace/AgentWatch-Backend'. Si usas otra ruta, ajusta
el valor de la variable WORKSPACE_DIR abajo.
================================================================================
*/

pipeline {
    agent any

    parameters {
        choice(name: 'RELEASE', choices: ['v1', 'v2', 'v2-error'], description: 'Versión de AgentWatch-Backend a desplegar')
    }

    environment {
        // Ruta de la carpeta del backend dentro del contenedor de Jenkins
        WORKSPACE_DIR = '/var/jenkins_workspace/AgentWatch-Backend'
        IMAGE_NAME = 'agentwatch-backend'
        CONTAINER_NAME = 'agentwatch-backend-container'
        PORT = '8000'
        HEALTH_ENDPOINT = '/health'
    }

    stages {
        stage('Build') {
            steps {
                echo "=== ETAPA: BUILD ==="
                echo "Construyendo imagen Docker para AgentWatch Backend - Versión: ${params.RELEASE}..."
                // Nos movemos al directorio del proyecto local y ejecutamos el build
                dir("${WORKSPACE_DIR}") {
                    sh "docker build -t ${IMAGE_NAME}:${params.RELEASE} ."
                }
            }
        }

        stage('Deploy') {
            steps {
                echo "=== ETAPA: DEPLOY ==="
                echo "Deteniendo contenedor anterior si existe..."
                sh "docker stop ${CONTAINER_NAME} || true"
                sh "docker rm ${CONTAINER_NAME} || true"

                echo "Desplegando contenedor con la versión: ${params.RELEASE}..."
                script {
                    def simulateError = (params.RELEASE == 'v2-error') ? 'true' : 'false'
                    sh """
                        docker run -d \
                            -p ${PORT}:${PORT} \
                            --name ${CONTAINER_NAME} \
                            -e APP_VERSION=${params.RELEASE} \
                            -e SIMULATE_ERROR=${simulateError} \
                            ${IMAGE_NAME}:${params.RELEASE}
                    """
                }
            }
        }

        stage('Health Check') {
            steps {
                echo "=== ETAPA: HEALTH CHECK ==="
                echo "Esperando a que la aplicación inicie..."
                sleep 5
                echo "Verificando la salud del servicio..."
                script {
                    try {
                        // Obtiene la IP del contenedor en la red interna de Docker
                        def containerIp = sh(script: "docker inspect -f '{{range .NetworkSettings.Networks}}{{.IPAddress}}{{end}}' ${CONTAINER_NAME}", returnStdout: true).trim()
                        echo "IP del contenedor: ${containerIp}"
                        
                        // Realiza la petición HTTP al endpoint /health
                        sh "curl -f http://${containerIp}:${PORT}${HEALTH_ENDPOINT}"
                        echo "Health check superado con éxito para la versión ${params.RELEASE}."
                    } catch (Exception e) {
                        error "El Health check falló. Iniciando proceso de Rollback..."
                    }
                }
            }
        }
    }

    post {
        failure {
            echo "=== DETECTADO ERROR: INICIANDO ROLLBACK ==="
            echo "El despliegue de la versión ${params.RELEASE} no pasó el Health Check."
            echo "Restaurando la última versión estable conocida (v1)..."
            sh """
                docker stop ${CONTAINER_NAME} || true
                docker rm ${CONTAINER_NAME} || true
                docker run -d \
                    -p ${PORT}:${PORT} \
                    --name ${CONTAINER_NAME} \
                    -e APP_VERSION=v1 \
                    -e SIMULATE_ERROR=false \
                    ${IMAGE_NAME}:v1
            """
            echo "Rollback completado con éxito. La versión estable (v1) está en ejecución."
        }
        success {
            echo "=== DESPLIEGUE EXITOSO ==="
            echo "La versión ${params.RELEASE} de AgentWatch-Backend ha sido desplegada y verificada correctamente."
        }
    }
}
