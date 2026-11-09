<script setup lang="ts">
import { computed, nextTick, ref, watch } from 'vue'
import type { OutlineItem } from '@/markdown/outline'

const props = defineProps<{
  items: OutlineItem[]
  /** 当前可见区域顶部对应的源码行号，用于高亮所在章节 */
  visibleLine: number
}>()
const emit = defineEmits<{ select: [item: OutlineItem] }>()

/** 当前章节：最后一个位于可见区域顶部之上（或正好在顶部）的标题 */
const activeIndex = computed(() => {
  let index = -1
  props.items.forEach((item, i) => {
    if (item.line <= props.visibleLine + 0.5) index = i
  })
  return index
})

/** 文档中最高的标题级别，作为缩进的起点（例如全文只有 ## 和 ###，## 就不缩进） */
const baseLevel = computed(() => Math.min(...props.items.map((i) => i.level), 3))

// 当前章节变化时，让它在目录中保持可见
const list = ref<HTMLElement>()
watch(activeIndex, async (i) => {
  await nextTick()
  list.value
    ?.querySelector<HTMLElement>(`[data-index="${i}"]`)
    ?.scrollIntoView({ block: 'nearest' })
})
</script>

<template>
  <nav class="outline" aria-label="目录">
    <div class="outline-title">目录</div>
    <ul v-if="items.length" ref="list" class="outline-list">
      <li v-for="(item, i) in items" :key="`${item.line}-${item.text}`">
        <button
          type="button"
          class="outline-item"
          :class="{ active: i === activeIndex }"
          :style="{ paddingLeft: `${10 + (item.level - baseLevel) * 14}px` }"
          :data-index="i"
          :data-level="item.level"
          :title="item.text"
          @click="emit('select', item)"
        >
          {{ item.text }}
        </button>
      </li>
    </ul>
    <p v-else class="outline-empty">
      暂无标题<br />
      使用 <code>#</code>、<code>##</code>、<code>###</code> 添加标题后会显示在这里
    </p>
  </nav>
</template>

<style scoped>
.outline {
  display: flex;
  flex-direction: column;
  height: 100%;
  min-height: 0;
}
.outline-title {
  flex-shrink: 0;
  padding: 12px 14px 8px;
  font-size: 12px;
  font-weight: 600;
  color: var(--ul-text-3);
}
.outline-list {
  flex: 1;
  min-height: 0;
  margin: 0;
  padding: 0 6px 24px;
  overflow-y: auto;
  list-style: none;
}
.outline-item {
  display: block;
  width: 100%;
  padding: 4px 8px;
  border: 0;
  border-radius: 4px;
  background: transparent;
  color: var(--ul-text-2);
  font: inherit;
  font-size: 13px;
  line-height: 1.5;
  text-align: left;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  cursor: pointer;
}
.outline-item[data-level='1'] {
  font-weight: 600;
  color: var(--ul-text);
}
.outline-item:hover {
  background: var(--ul-bg-mute);
}
.outline-item.active {
  background: var(--ul-accent-soft);
  color: var(--ul-accent);
}
.outline-empty {
  margin: 0;
  padding: 4px 14px;
  font-size: 12px;
  line-height: 1.8;
  color: var(--ul-text-3);
}
.outline-empty code {
  font-family: var(--ul-font-mono);
}
</style>
