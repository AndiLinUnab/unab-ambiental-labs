// Puntos guardados por día (hora de Colombia, UTC-5). Con 1 punto cada 30 s, un día
// completo tiene ~2880 puntos; menos que eso indica huecos ese día.
from(bucket: "__BUCKET__")
  |> range(start: -30d)
  |> filter(fn: (r) => r._measurement == "ambiental" and r._field == "temperature")
  |> aggregateWindow(every: 1d, offset: 5h, fn: count, timeSrc: "_start", createEmpty: false)
  |> keep(columns: ["_time", "_value"])
  |> rename(columns: {_value: "puntos"})
