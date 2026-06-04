# GRAPH_SCHEMA - RF17

## Objetivo

Este schema representa cada ejecución de un agente como un grafo en Neo4j.

## Nodos

### ExecutionStart
Representa el inicio de una ejecución.

Propiedades:
- execution_id
- tenant_id
- agent_id
- timestamp

### LLMCall
Representa la llamada al modelo de lenguaje.

Propiedades:
- model

### ToolCall
Representa la herramienta utilizada por el agente.

Propiedades:
- tool_name

### PolicyCheck
Representa la validación de políticas.

Propiedades:
- result

### ExecutionEnd
Representa el cierre de la ejecución.

Propiedades:
- status

## Relaciones

### TRIGGERED_BY
Relaciona la llamada al LLM con el inicio de ejecución.

### LED_TO
Representa el flujo causal entre pasos.

### PRODUCED
Representa el resultado final producido por la ejecución.

## Consulta principal

```cypher
MATCH p=(s:ExecutionStart {execution_id:$execution_id})-[*]-()
RETURN p;

