// Identical nested loops; only the two address strides differ.
const ROWS = [
  ["MOV EAX, 0", "MOV EAX, 0"],
  ["MOV RDX, 0", "MOV RDX, 0"],
  ["outer:", "outer:"],
  ["    MOV RSI, RDI", "    MOV RSI, RDI"],
  ["    MOV RCX, 0", "    MOV RCX, 0"],
  ["loop:", "loop:"],
  ["    MOV EBX, [RSI]", "    MOV EBX, [RSI]"],
  ["    ADD EAX, EBX", "    ADD EAX, EBX"],
  ["    ADD RSI, 4", "    ADD RSI, 8192"],
  ["    INC RCX", "    INC RCX"],
  ["    CMP RCX, 2048", "    CMP RCX, 2048"],
  ["    JL loop", "    JL loop"],
  ["    ADD RDI, 8192", "    ADD RDI, 4"],
  ["    INC RDX", "    INC RDX"],
  ["    CMP RDX, 2048", "    CMP RDX, 2048"],
  ["    JL outer", "    JL outer"],
];

export function mount(element) {
  element.classList.add("assembly-comparison", "traversal-comparison");
  element.innerHTML = '<div class="comparison-scroll" tabindex="0" role="region" aria-label="Обход строки и столбца"><table><thead><tr><th scope="col">По строкам</th><th scope="col">По столбцам</th></tr></thead><tbody></tbody></table></div>';
  const body = element.querySelector("tbody");
  for (const pair of ROWS) {
    const row = document.createElement("tr");
    if (pair[0] !== pair[1]) row.className = "comparison-stride";
    for (const line of pair) {
      const cell = document.createElement("td");
      const code = document.createElement("code");
      const match = line.match(/^(\s*)(MOV|ADD|SUB|INC|CMP|JL)(.*)$/);
      if (match) {
        const opcode = document.createElement("span");
        opcode.className = "comparison-keyword";
        opcode.textContent = match[2];
        code.append(document.createTextNode(match[1]), opcode, document.createTextNode(match[3]));
      } else code.textContent = line;
      cell.append(code);
      row.append(cell);
    }
    body.append(row);
  }
}
