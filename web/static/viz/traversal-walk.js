import { mount as mountWalk } from "./stride-walk.js";

export function mount(element, options = {}) {
  mountWalk(element, { ...options, params: { ...options.params, cache: false } });
}
