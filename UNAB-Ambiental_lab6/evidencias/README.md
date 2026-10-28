# Evidencias

Una captura por fila. Los nombres de archivo son una sugerencia: renombrar las capturas para que coincidan.

| Archivo | Qué muestra |
|---|---|
| `01_nodo_ready.png` | `kubectl get nodes -o wide`: nodo `Ready`, Kubernetes v1.36.4 |
| `02_cuota_ips_publicas.png` | Cuota de IPs públicas 3 de 3 y su causa |
| `03_ingress_ip.png` | `kubectl get svc -n app-routing-system` e `ingressclass` |
| `04_bd_running_bound.png` | Etapa 2: pods de BD `Running`, PVC `Bound`, Service `ClusterIP` |
| `05_wordpress_instalador.png` | Asistente de WordPress cargando por su host |
| `06_wordpress_pagina_antes.png` | Página de prueba publicada |
| `07_wordpress_reinicio_pods.png` | `get pods` antes y después del reinicio |
| `08_wordpress_pagina_despues.png` | La página sigue tras el reinicio |
| `09_prestashop_fallo_lostfound.png` | Log del fallo de instalación (`lost+found`) |
| `10_prestashop_319_tablas.png` | Instalación correcta: 319 tablas y `200 OK` |
| `11_prestashop_producto_antes.png` | Producto `Sensor Prueba Lab6` en la tienda |
| `12_prestashop_reinicio_pods.png` | `get pods` antes y después, y conteo de tablas (recortada, sin contraseñas) |
| `13_prestashop_producto_despues.png` | El producto sigue tras el reinicio |
| `14_grafana_dashboard.png` | Dashboard con los pods de `wordpress` y `prestashop` |
| `15_wordpress_reinicio2_pods.png` | Segundo reinicio de WordPress |
| `16_estado_final.png` | Pods, PVC, Service e Ingress al cierre |
| `17_cuota_vcpu.png` | Cuota de vCPU (6 por región) frente a los 32 vCPU del template |
| `18_insufficientvcpuquota.png` | Error del primer intento con 2 nodos (si existe la captura) |
| `19_borrado_grupo.png` | `az group delete` y comprobación `false` |
| `20_costo.png` | Cost Management (cuando aparezca) |

**No subir:** asistente de WordPress con la contraseña visible, `get secret ps-admin`, login de clientes de
PrestaShop con la contraseña escrita, ni la captura de reinicio de PrestaShop sin recortar.
