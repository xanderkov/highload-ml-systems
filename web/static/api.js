// Единственная точка обращения к серверу. Вынесена из app.js отдельным
// модулем, чтобы блоки не импортировали app.js (тот сам грузит блоки —
// получился бы цикл импортов).

export async function run(sectionId, blockId, code) {
  const response = await fetch("/api/run", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ section: sectionId, block: blockId, code }),
  });
  if (!response.ok) {
    // Сюда попадают только сбои самой страницы курса: 404 на блок и 502,
    // когда сервис замеров не отвечает вовсе. Все исходы прогона
    // (включая ошибки в коде студента) приходят с кодом 200.
    let detail = `сервер ответил ${response.status}`;
    try {
      const body = await response.json();
      if (body.detail) detail = body.detail;
    } catch {
      /* тело не JSON — остаётся код ответа */
    }
    throw new Error(detail);
  }
  return response.json();
}
