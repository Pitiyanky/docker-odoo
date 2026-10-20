# ARCHITECTURE.md — Decisiones Técnicas y de Diseño

Este documento justifica las decisiones arquitectónicas tomadas en el desarrollo del módulo `payment_request` para Odoo 19.

---

## 1. Concurrencia y Bloqueo Pesimista en Base de Datos

### El Problema
En entornos de producción con múltiples workers (gevent / multiprocessing), las validaciones a nivel de Python como:
```python
if self.state != 'to_approve':
    raise UserError(...)
```
son vulnerables a condiciones de carrera (*race conditions*). Si dos aprobadores o dos operadores de tesorería abren el registro y envían la petición HTTP en la misma fracción de segundo, ambos procesos leerán el estado antiguo de la base de datos antes de que cualquiera guarde el nuevo, provocando aprobaciones duplicadas o pagos duplicados.

### La Solución Implementada
Se implementó bloqueo pesimista mediante PostgreSQL:
```python
self.flush_recordset()
self.env.cr.execute(
    "SELECT id, state, current_step FROM payment_request WHERE id = %s FOR UPDATE NOWAIT",
    [self.id]
)
```
- **`self.flush_recordset()`**: Es obligatorio antes de la consulta cruda para asegurar que cualquier modificación previa en la caché del ORM haya sido escrita en PostgreSQL.
- **`FOR UPDATE NOWAIT`**: Adquiere un bloqueo exclusivo a nivel de fila (*row-level lock*). Si otra transacción ya tiene bloqueada la solicitud, PostgreSQL lanza de inmediato una excepción `OperationalError`, la cual es capturada para avisar al usuario que el registro está en procesamiento, impidiendo colisiones.
- **Atomicidad Transaccional**: La creación y validación del `account.payment` ocurre dentro de la misma transacción de la solicitud. Si el diario contable falla o no tiene fondos/cuentas configuradas, la transacción completa hace *rollback* y la solicitud jamás pasa a estado `Pagada`.

---

## 2. Aprobación Secuencial Multi-Paso (`payment.approval.policy`)

Para satisfacer la necesidad de que los montos mayores requieran escalamiento progresivo (ej. Jefe de Área $\rightarrow$ Gerente General):
- Se desacopló la regla fija de aprobación en dos modelos: `payment.approval.policy` (cabecera con rango de montos) y `payment.approval.policy.line` (secuencia ordenada de aprobadores).
- Al hacer clic en **Enviar**, el sistema evalúa el monto convertido a la moneda de la compañía y enlaza la política correspondiente fijando el `current_step = 1`.
- En cada aprobación, se guarda un registro en `payment.historical.validation` (modelo inmutable con usuario, fecha, paso y rol) y se crea la actividad correspondiente al siguiente aprobador.
- Solo cuando `current_step == total_steps`, la solicitud transita a `approved`.

---

## 3. Bloqueo de Bypass en Contabilidad (`account.payment`)

Para cerrar la brecha donde los usuarios podían saltarse el control creando pagos directamente en *Contabilidad > Proveedores > Pagos*:
- Se heredó `account.payment` interceptando el método `create()`.
- Si `payment_type == 'outbound'` y `partner_type == 'supplier'`, se exige que la llamada provenga del contexto del wizard (`context.get('from_payment_request')`) o que el usuario pertenezca al grupo `group_payment_request_manager`.
- De lo contrario, se dispara un `AccessError`, garantizando que todo egreso a proveedores pase obligatoriamente por el flujo de solicitudes.

---

## 4. Multi-Moneda y Tasa de Cambio (USD / VES)

- Las solicitudes admiten cualquier moneda activa en el sistema.
- En el wizard de pago, cuando el diario seleccionado tiene una divisa diferente a la solicitud (ej. solicitud en USD y banco en VES), se ejecuta la conversión automática:
  ```python
  payment_amount = currency_request_id._convert(
      amount_request, payment_currency_id, company_id, payment_date
  )
  ```
- Se utiliza la tasa del día de la liquidación bancaria (`payment_date`), asegurando que el asiento contable refleje el monto en bolívares exacto según la fluctuación cambiaria.

---

## 5. Multi-Compañía

- Se crearon reglas de registro globales (`ir.rule`) tanto en `payment.request` como en `payment.approval.policy` utilizando el dominio estándar:
  ```xml
  [('company_id', 'in', company_ids)]
  ```
- Un usuario perteneciente a la Compañía B no puede leer, listar ni aprobar solicitudes de la Compañía A.