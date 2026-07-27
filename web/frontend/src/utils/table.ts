import { h } from 'vue'

// 数值列排序器：按 key 取数，缺失值排到最后。
export function numSorter<T>(key: keyof T) {
  return (a: T, b: T) => ((a[key] as number) ?? -Infinity) - ((b[key] as number) ?? -Infinity)
}

// 可点击的代码/链接单元格渲染（统一蓝色链接样式）。
export function linkCell(text: string, onClick: () => void) {
  return h('a', { style: { color: '#38bdf8', cursor: 'pointer' }, onClick }, text)
}
