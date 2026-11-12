
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

- Local (hoy: un restaurante con un local; el modelo admite más de uno)
- Registro inicial web: si no hay administradores, se crea el local y su administrador
- Empresas
- Trabajadores
- Usuario administrador (ingresa con correo; ve todo y escanea en su local; gestión de administradores)
- Usuario operador / garzón (ingresa con usuario y clave de 8 dígitos; escanea en su local)
- El consumo registra el local de quien escanea
- QR único por trabajador (un QR por cada registro trabajador-empresa)
- Importación masiva de trabajadores desde Excel/CSV con vista previa
- Descarga masiva de QR: PDF imprimible (6 por hoja A4) e imágenes para teléfono (ZIP)
- Escáner QR de pantalla completa (contador del día, últimos 5 registros, linterna, pantalla siempre encendida)
- Registro manual por RUT como respaldo (queda marcado como «manual» y con el operador)
- Registro de consumo
- Cupo diario de almuerzos por empresa (con excepción por trabajador) y bloqueo al agotarlo
- Dashboard básico
- Historial de consumos (búsqueda por RUT; el operador solo ve el día en curso)
- Gestión de operadores (activar/desactivar, cambiar clave y local)
- Edición de trabajadores (datos, excepción de cupo y estado activo)

## NO implementar todavía

No implementar sin solicitud explícita:

- Menús (planeado para v0.2: al escanear el QR, el garzón elige el almuerzo
  desde una lista de opciones disponibles en esa misma pantalla)
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
3. El sistema muestra nombre + empresa y el resultado del registro.

Al escanear un QR válido, el consumo se registra automáticamente si el
trabajador aún tiene cupo diario. Si el cupo está agotado, se informa y no se
crea otro registro.

## Reglas de empresas y cupos

- Cada empresa es un universo independiente: paga y ve solo sus consumos.
- Una misma persona (mismo RUT) puede estar vigente en varias empresas; tiene
  un registro y un QR distintos en cada una. El RUT es único por empresa entre
  trabajadores vigentes.
- Cada empresa define cuántos almuerzos diarios autoriza por trabajador
  (por defecto 1); un trabajador puede tener una excepción individual.
- Los cupos son independientes por empresa. Ejemplo: RUT 12492336-0 con cupo 1
  en A y 2 en B puede almorzar 3 veces al día (1 pagado por A, 2 por B).
- Si se desvincula de una empresa, su QR de esa empresa queda bloqueado; sus
  QR de otras empresas siguen funcionando.

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
