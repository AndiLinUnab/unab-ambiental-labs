// Primer y último dato guardado en toda la TSDB (inicio y fin reales de la toma).
base = from(bucket: "__BUCKET__")
  |> range(start: 0)
  |> filter(fn: (r) => r._measurement == "ambiental" and r._field == "temperature")
  |> group()
  |> keep(columns: ["_time", "_value"])

base |> min(column: "_time") |> yield(name: "primer_dato")
base |> max(column: "_time") |> yield(name: "ultimo_dato")
