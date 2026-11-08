<script setup lang="ts">
import { computed } from 'vue'
import { NIcon, NTooltip } from 'naive-ui'
import { Check, CloudOff, LoaderCircle, TriangleAlert } from 'lucide-vue-next'
import type { SaveStatus } from '@/composables/useNoteEditor'

const props = defineProps<{ status: SaveStatus; error?: string }>()

const view = computed(() => {
  switch (props.status) {
    case 'dirty':
      return { text: '未保存', icon: null, cls: 'muted' }
    case 'saving':
      return { text: '保存中…', icon: LoaderCircle, cls: 'muted spin' }
    case 'error':
      return { text: '保存失败，稍后重试', icon: CloudOff, cls: 'danger' }
    case 'conflict':
      return { text: '版本冲突', icon: TriangleAlert, cls: 'warning' }
    default:
      return { text: '已保存', icon: Check, cls: 'muted' }
  }
})
</script>

<template>
  <NTooltip :disabled="status !== 'error' || !error">
    <template #trigger>
      <span class="save-status" :class="view.cls" role="status">
        <NIcon v-if="view.icon" :size="14"><component :is="view.icon" /></NIcon>
        <span>{{ view.text }}</span>
      </span>
    </template>
    {{ error }}
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
