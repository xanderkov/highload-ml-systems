const ROWS = [
  ["int total = 0;", "MOV EAX, 0", "обнулить сумму"],
  ["int i = 0;", "MOV RCX, 0", "обнулить индекс"],
  ["int count = n * n;", "MOV RDX, 4", "число элементов: 2 × 2"],
  ["do {", "loop:", "начало цикла"],
  ["    int value = a[i];", "MOV EBX, [0x1000 + RCX*4]", "загрузить элемент"],
  ["    total += value;", "ADD EAX, EBX", "прибавить элемент к сумме"],
  ["    i++;", "INC RCX", "увеличить индекс"],
  ["} while (i < count);", "CMP RCX, RDX\nJL loop", "CMP устанавливает флаги; JL проверяет их и повторяет цикл, если i < count"],
];

function highlight(code, source, assembly) {
  const pattern = assembly
    ? /(;.*$|\b(?:MOV|ADD|INC|CMP|JL)\b|\b(?:EAX|EBX|RCX|RDX)\b|\b(?:0x[\da-f]+|\d+)\b)/gi
    : /(\b(?:int|do|while)\b|\b\d+\b)/g;
  let cursor = 0;
  for (const match of source.matchAll(pattern)) {
    code.append(document.createTextNode(source.slice(cursor, match.index)));
    const span = document.createElement("span");
    span.className = /^\d/.test(match[0]) ? "comparison-number"
      : /^(EAX|EBX|RCX|RDX)$/.test(match[0]) ? "comparison-register" : "comparison-keyword";
    span.textContent = match[0];
    code.append(span);
    cursor = match.index + match[0].length;
  }
  code.append(document.createTextNode(source.slice(cursor)));
}

export function mount(element) {
  element.classList.add("assembly-comparison");
  element.innerHTML = '<div class="comparison-scroll" tabindex="0" role="region" aria-label="Сопоставление C и ассемблера"><table><thead><tr><th scope="col">C</th><th scope="col">Ассемблер</th></tr></thead><tbody></tbody></table></div>';
  const body = element.querySelector("tbody");
  for (const [c, asm, comment] of ROWS) {
    const row = document.createElement("tr");
    for (const [source, assembly] of [[c, false], [asm, true]]) {
      const cell = document.createElement("td");
      const code = document.createElement("code");
      highlight(code, source, assembly);
      cell.append(code);
      if (assembly) {
        const note = document.createElement("span");
        note.className = "comparison-comment";
        note.textContent = "; " + comment;
        cell.append(note);
      }
      row.append(cell);
    }
    body.append(row);
  }
}
