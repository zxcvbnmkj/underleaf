<script setup lang="ts">
import { computed } from 'vue'
import { NIcon, NTooltip } from 'naive-ui'
import { Check, CloudOff, LoaderCircle, TriangleAlert } from 'lucide-vue-next'
import type { SaveStatus } from '@/composables/useNoteEditor'

const props = defineProps<{ status: SaveStatus; error?: string }>()
const emit = defineEmits<{ save: [] }>()

const isMac = /Mac|iPhone|iPad/.test(navigator.platform)
/** 有未保存的修改或保存失败时，可以点击立即保存 */
const clickable = computed(() => props.status === 'dirty' || props.status === 'error')
const tooltip = computed(() => {
  if (props.status === 'error') return `${props.error ?? '保存失败'}，点击重试`
  if (props.status === 'dirty')
    return `停止输入 30 秒后自动保存；点击或按 ${isMac ? '⌘' : 'Ctrl'}+S 立即保存`
  return ''
})

const view = computed(() => {
  switch (props.status) {
    case 'dirty':
      return { text: '未保存', icon: null, cls: 'muted' }
    case 'saving':
      return { text: '保存中…', icon: LoaderCircle, cls: 'muted spin' }
    case 'error':
      return { text: '保存失败', icon: CloudOff, cls: 'danger' }
    case 'conflict':
      return { text: '版本冲突', icon: TriangleAlert, cls: 'warning' }
    default:
      return { text: '已保存', icon: Check, cls: 'muted' }
  }
})
</script>

<template>
  <NTooltip :disabled="!tooltip">
    <template #trigger>
      <button
        v-if="clickable"
        type="button"
        class="save-status clickable"
        :class="view.cls"
        role="status"
        @click="emit('save')"
      >
        <NIcon v-if="view.icon" :size="14"><component :is="view.icon" /></NIcon>
        <span>{{ view.text }}</span>
      </button>
      <span v-else class="save-status" :class="view.cls" role="status">
        <NIcon v-if="view.icon" :size="14"><component :is="view.icon" /></NIcon>
        <span>{{ view.text }}</span>
      </span>
    </template>
    {{ tooltip }}
  </NTooltip>
</template>

<style scoped>
.save-status {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  font-size: 12px;
  white-space: nowrap;
}
.clickable {
  padding: 2px 6px;
  margin: -2px -6px;
  border: 0;
  border-radius: 4px;
  background: transparent;
  font: inherit;
  font-size: 12px;
  cursor: pointer;
}
.clickable:hover {
  background: var(--ul-bg-mute);
}
.muted {
  color: var(--ul-text-3);
}
.danger {
  color: var(--ul-danger);
}
.warning {
  color: var(--ul-warning);
}
.spin :deep(svg) {
  animation: spin 1s linear infinite;
}
@keyframes spin {
  to {
    transform: rotate(360deg);
  }
}
</style>
