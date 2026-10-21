// Huecos en la toma: pausas de más de 2 minutos entre puntos consecutivos.
// "_time" es la hora del primer punto DESPUÉS del hueco; el hueco empezó "hueco_minutos" antes.
from(bucket: "__BUCKET__")
  |> range(start: -30d)
  |> filter(fn: (r) => r._measurement == "ambiental" and r._field == "temperature")
  |> elapsed(unit: 1s)
  |> filter(fn: (r) => r.elapsed > 120)
  |> map(fn: (r) => ({_time: r._time, hueco_minutos: float(v: r.elapsed) / 60.0}))
