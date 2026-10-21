// Último punto de cada variable en los últimos 15 minutos (comprueba que la ingesta está viva).
from(bucket: "__BUCKET__")
  |> range(start: -15m)
  |> filter(fn: (r) => r._measurement == "ambiental")
  |> last()
  |> keep(columns: ["_time", "sala", "_field", "_value"])
