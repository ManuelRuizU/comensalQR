
 # ComensalQR — Instrucciones para el agente

## Estado actual

Estamos construyendo el MVP v0.1.

## Objetivo actual

Permitir que un restaurante registre mediante QR:

- quién almorzó;
- de qué empresa viene;
- fecha y hora del consumo;
- cantidad total de almuerzos.

## Funcionalidades permitidas en MVP v0.1

- Local
- Empresas
- Trabajadores
- Usuario administrador
- Usuario operador
- QR único por trabajador
- Escáner QR
- Registro de consumo
- Prevención de doble consumo diario
- Dashboard básico
- Historial de consumos

## NO implementar todavía

No implementar sin solicitud explícita:

- Menús
- Costos
- IVA
- Rentabilidad
- Facturación
- Portal de empresas
- NFC
- Biometría
- Reconocimiento facial
- Aplicación móvil nativa
- Integraciones externas

## Regla principal

No agregar funcionalidades por iniciativa propia.

Si una funcionalidad futura parece necesaria,
preguntar antes de implementarla.

## Flujo principal

Trabajador
↓
QR
↓
Escaneo
↓
Identificación
↓
Empresa
↓
Registrar consumo
↓
Fecha y hora
↓
Dashboard

## Seguridad

El QR no debe contener:

- RUT
- nombre
- empresa
- datos personales

Debe contener solamente un identificador/token aleatorio.

## UX del operador

El operador debe poder:

1. Abrir escáner.
2. Escanear QR.
3. Ver nombre + empresa.
4. Saber si puede registrar.
5. Registrar consumo.

El proceso debe tomar pocos segundos.

## Tecnología

Backend:
Python + Django

Base de datos:
PostgreSQL

Frontend:
Django Templates + Bootstrap + JavaScript

## Metodología

Antes de implementar una nueva funcionalidad:

1. Revisar AGENTS.md.
2. Revisar el código existente.
3. Verificar que la funcionalidad pertenece al MVP actual.
4. No modificar funcionalidades existentes innecesariamente.
5. Implementar.
6. Probar.
7. Informar qué archivos fueron modificados.
8. Actualizar documentación si corresponde.
