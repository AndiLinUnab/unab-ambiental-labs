# UNAB-Ambiental · Laboratorio 6: WordPress y PrestaShop en AKS

Curso IoT + Cloud + Sistemas Distribuidos · UNAB · 2026

**Integrantes:** Andi Lin (U00180153) · Juan Sebastián Buitrago Caballero (U00179631) · Miguel Ángel Solano Díaz (U00177983)

Un clúster AKS (1 nodo `Standard_B2s_v2`, tier Free, Chile Central, Kubernetes v1.36.4) aloja dos portales
independientes. Cada uno tiene su namespace, su MariaDB, sus Secrets y sus PVC. Grafana corre como
Deployment propio en un tercer namespace.

## Arquitectura

```
                    Internet
                       │
          LoadBalancer (ingress gestionado de AKS, 1 IP pública)
          wordpress.<IP>.nip.io · prestashop.<IP>.nip.io · grafana.<IP>.nip.io
          ┌────────────────┼──────────────────┐
          ▼                ▼                  ▼
 ┌─ ns wordpress ─┐ ┌─ ns prestashop ─┐ ┌─ ns monitoring ───────────┐
 │ wordpress      │ │ prestashop      │ │ grafana                   │
 │  └ PVC wp-content│ │  └ PVC ps-html │ │ prometheus                │
 │ wp-mariadb     │ │ ps-mariadb      │ │ kube-state-metrics        │
 │  └ PVC wp-db-data│ │  └ PVC ps-db-data│ │ (ve pods de los 2 portales)│
 │ Secret wp-db   │ │ Secrets ps-db,  │ └───────────────────────────┘
 └────────────────┘ │ ps-admin        │
   Service BD:      └─────────────────┘
   ClusterIP        Service BD: ClusterIP
```

Ninguna base de datos se expone a Internet (Service `ClusterIP`). WordPress no apunta a la BD de
PrestaShop ni al revés.

## Desviaciones respecto al enunciado

| Enunciado | Qué se hizo | Motivo |
|---|---|---|
| Template `sabbour/aks-app-template` con `azd` | Clúster creado con `az aks create` | El template pide 32 vCPU como mínimo (4 nodos de 8 vCPU) y la cuota regional es de 6. Además fija Kubernetes 1.26 y APIs preview antiguas. |
| Managed Grafana del template | Grafana como Deployment propio | Managed Grafana no está disponible en Chile Central. El enunciado permite Deployment propio. |
| Un LoadBalancer o NodePort por portal | Un único LoadBalancer (ingress gestionado) con hosts nip.io | La cuota de IPs públicas era de 3 y había que dejar libre una para el ingress. |
| `azd down` | `az group delete -n rg-lab6-aks --yes` | No se usó `azd`. |

## Despliegue

1. Clúster (ajustar a lo realmente usado):

        az group create -n rg-lab6-aks -l chilecentral
        az aks create -g rg-lab6-aks -n aks-lab6 --tier free --node-count 1 --node-vm-size Standard_B2s_v2 --generate-ssh-keys
        az aks get-credentials -g rg-lab6-aks -n aks-lab6

2. Ingress gestionado y su IP:

        az aks approuting enable -g rg-lab6-aks -n aks-lab6
        kubectl get svc -n app-routing-system
        kubectl patch nginxingresscontroller default --type merge -p '{"spec":{"scaling":{"minReplicas":1,"maxReplicas":1}}}'

3. Los hosts llevan la IP con guiones (`57-156-15-124`, la del despliegue original). Sustituirla por la nueva:

        sed -i 's/57-156-15-124/NUEVA-IP-CON-GUIONES/g' manifiestos/*.yaml

4. Namespaces:

        kubectl create namespace wordpress
        kubectl create namespace prestashop
        kubectl create namespace monitoring

5. Secrets reales (no están en el repo; `manifiestos/secrets.example.yaml` solo es un ejemplo con valores falsos):

        kubectl create secret generic wp-db -n wordpress --from-literal=MARIADB_ROOT_PASSWORD="$(openssl rand -base64 18 | tr -d '/+=')" --from-literal=MARIADB_DATABASE=wordpress --from-literal=MARIADB_USER=wpuser --from-literal=MARIADB_PASSWORD="$(openssl rand -base64 18 | tr -d '/+=')"
        kubectl create secret generic ps-db -n prestashop --from-literal=MARIADB_ROOT_PASSWORD="$(openssl rand -base64 18 | tr -d '/+=')" --from-literal=MARIADB_DATABASE=prestashop --from-literal=MARIADB_USER=psuser --from-literal=MARIADB_PASSWORD="$(openssl rand -base64 18 | tr -d '/+=')"
        kubectl create secret generic ps-admin -n prestashop --from-literal=ADMIN_MAIL=correo@ejemplo.com --from-literal=ADMIN_PASSWD="$(openssl rand -base64 18 | tr -d '/+=')"
        kubectl create secret generic grafana-admin -n monitoring --from-literal=GF_SECURITY_ADMIN_USER=labadmin --from-literal=GF_SECURITY_ADMIN_PASSWORD="$(openssl rand -base64 18 | tr -d '/+=')"

6. Bases de datos (esperar `Running` y PVC `Bound`), luego portales:

        kubectl apply -f manifiestos/wp-db.yaml -f manifiestos/ps-db.yaml
        kubectl apply -f manifiestos/wordpress.yaml
        kubectl apply -f manifiestos/prestashop.yaml

7. WordPress: abrir su host y completar el asistente; crear una página de prueba.
8. PrestaShop: la instalación es automática (varios minutos). Para entrar al panel
   (`/adminlab6`) hay que borrar el instalador una sola vez:

        kubectl exec -n prestashop deploy/prestashop -- rm -rf /var/www/html/install

   Después, crear un producto de prueba.
9. Monitorización:

        kubectl apply -f manifiestos/monitoring.yaml
        kubectl apply -f manifiestos/grafana.yaml

   Dashboard "Lab6 - Portales en AKS" en la carpeta Lab6.

## Prueba de persistencia

    kubectl get pods -n wordpress
    kubectl rollout restart deployment/wordpress -n wordpress
    kubectl rollout status deployment/wordpress -n wordpress
    kubectl get pods -n wordpress

Igual con `prestashop`. El pod de la aplicación cambia de nombre y de edad, la base conserva la suya,
y la página (WordPress) o el producto (PrestaShop) siguen ahí.

## Resultados

- WordPress: la página de prueba persistió a dos reinicios del pod.
- PrestaShop: el producto de prueba persistió al reinicio; la base tiene 319 tablas antes y después.
- Grafana: el panel distingue los pods de `wordpress` y `prestashop` (pods Running por namespace,
  tabla de pods, reinicios de contenedores).
- Con 1 nodo y `strategy: Recreate`, cada reinicio deja el portal sin servicio unos segundos
  (se ve como una caída momentánea en la serie de Grafana).

## Lecciones

- Los discos Azure traen `lost+found`: se monta con `subPath` (MariaDB y PrestaShop). Sin eso, el
  instalador de PrestaShop falla con `Permission denied` y deja `install.lock` con la base vacía.
- `PS_DOMAIN` debe coincidir con el host público; `PS_ERASE_DB` nunca se usa.
- El ingress gestionado pide 2 réplicas por defecto; con 1 nodo una queda `Pending` y consume cupo
  de CPU. Se fijó a 1 réplica.
- En un nodo de 2 vCPU el cupo de CPU (requests) es lo que limita, no la memoria.
- El primer pod de PrestaShop tuvo `RESTARTS 1` sin causa verificada (el pod ya no existía al investigar).

## Apagado y costo

El entorno se apagó al terminar:

    az group delete -n rg-lab6-aks --yes

- Nodo creado: 2026-10-25 20:02:54 UTC.
- Borrado ordenado: 2026-10-28 01:57:29 UTC (≈ 54 h de nodo encendido).
- Costo según Cost Management: **PENDIENTE** (rellenar cuando aparezca el cargo).

## Evidencias

Carpeta [`evidencias/`](evidencias/README.md). Las capturas con credenciales a la vista no se incluyen.
Los portales ya no existen; las IPs que aparecen en las capturas corresponden a un entorno eliminado.
