// Разбор ответа сервиса замеров, общий для exercise и benchmark.

// Runner отвечает 200 на любой исход и различает их полем status. Шесть
// статусов — его собственные, service_error добавляет прокси web при поломке
// runner'а. Тексты здесь — только запасные: runner присылает своё сообщение
// на русском, и оно точнее (в нём есть числа лимитов).
const FALLBACK_MESSAGE = {
  unsupported_lang: "Блок объявлен на языке, которого сервис замеров не знает.",
  unsupported_kind: "У харнесса этого блока неизвестный тип прогона.",
  timeout: "Код не уложился в отведённое время.",
  runtime_error: "Программа завершилась с ошибкой.",
  output_error: "Бенчмарк не вернул корректных результатов.",
  service_error: "Сбой сервиса замеров.",
};

// runner.jobs.MAX_SPEEDUP: медиана времени решения оказалась нулевой, то есть
// замер провалился ниже разрешения таймера. Показывать «1000000×» нельзя —
// это не измерение, а его отсутствие.
const MAX_SPEEDUP = 1000000;

export function escapeHtml(text) {
  const div = document.createElement("div");
  div.textContent = text === undefined || text === null ? "" : String(text);
  return div.innerHTML;
}

export function formatMs(value) {
  return `${Number(value).toFixed(3)} мс`;
}

export function formatSpeedup(value) {
  if (!Number.isFinite(value) || value >= MAX_SPEEDUP) return "не измеряется";
  return `${value.toFixed(2)}×`;
}

/** Возвращает HTML с объяснением неудачи или null, если прогон удался. */
export function renderProblem(data) {
  if (data.status === "ok") return null;

  const message = escapeHtml(data.message || FALLBACK_MESSAGE[data.status] || data.status);
  if (data.status === "unsupported_lang" || data.status === "unsupported_kind") {
    // Это не ошибка студента: блок объявлен неправильно в материалах курса.
    return `<p class="font-medium text-bad">${message}</p>
      <p class="mt-1 text-sm text-muted">Это ошибка в материалах курса, а не в вашем коде.</p>`;
  }
  if (data.status === "service_error") {
    return `<p class="font-medium text-ink">${message}</p>${logOf(data)}`;
  }
  return `<p class="font-medium text-bad">${message}</p>${logOf(data)}`;
}

/** Трассировка или лог: моноширинно, с прокруткой внутри блока. */
export function renderLog(text) {
  return `<pre class="mt-3 max-h-96 overflow-auto rounded-md border border-line bg-surface p-3 font-mono text-xs leading-relaxed text-ink">${escapeHtml(text)}</pre>`;
}

function logOf(data) {
  // У статуса timeout лога нет вовсе — процесс убит, показывать нечего.
  return data.log ? renderLog(data.log) : "";
}

/** Ошибка сети или прокси: до runner'а запрос не дошёл. */
export function renderFault(error) {
  return `<p class="font-medium text-bad">Не получилось запустить: ${escapeHtml(error?.message || error)}</p>`;
}

// Короткая метка исхода для шапки блока. Различение трёхуровневое: успех,
// недобор (код верен, порога не хватило), ошибка в коде — и отдельно сбой
// сервиса, который не вина студента.
const STATUS_LABEL = {
  unsupported_lang: "ошибка в материалах",
  unsupported_kind: "ошибка в материалах",
  timeout: "не уложилось во время",
  runtime_error: "упало на прогоне",
  output_error: "замер не дал чисел",
  service_error: "сбой сервиса",
};

export function statusLabel(data) {
  if (data.status !== "ok") return STATUS_LABEL[data.status] || data.status;
  if (data.correct === false) return "ответ не тот";
  return "не хватило";
}
