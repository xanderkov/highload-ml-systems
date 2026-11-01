import {mount as mountBlocks} from './execution-blocks.js';

export function mount(element, options = {}) {
  mountBlocks(element, {...options, params: {...options.params, parallel: true}});
}
