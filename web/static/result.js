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
  // Полоса слева различает исходы светлотой, а пунктиром — «прервано по
  // таймауту»: это не сломанный код, а не дождавшийся своего конца прогон.
  const timedOut = data.status === "timeout";
  const kind =
    (data.status === "service_error" ? "fault" : "bad") + (timedOut ? " is-timeout" : "");

  if (data.status === "unsupported_lang" || data.status === "unsupported_kind") {
    // Это не ошибка студента: блок объявлен неправильно в материалах курса.
    return `<p class="fault">${message}</p><p class="hint">Это ошибка в материалах курса, а не в вашем коде.</p>`;
  }
  return `<p class="${kind}">${message}</p>${logOf(data)}`;
}

function logOf(data) {
  // У статуса timeout лога нет вовсе — процесс убит, показывать нечего.
  return data.log ? `<pre class="log">${escapeHtml(data.log)}</pre>` : "";
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
