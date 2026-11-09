<script setup lang="ts">
import { computed, ref } from 'vue'
import { NButton, NIcon, NInput, NInputGroup, NPopover, NSwitch, useMessage } from 'naive-ui'
import { Copy, Globe, Share2 } from 'lucide-vue-next'
import { useWorkspaceStore } from '@/stores/workspace'
import { copyText } from '@/utils/clipboard'

const props = defineProps<{ noteId: number; compact?: boolean }>()
const store = useWorkspaceStore()
const message = useMessage()

const meta = computed(() => store.noteById(props.noteId))
const link = computed(() => (meta.value ? `${location.origin}/s/${meta.value.publicId}` : ''))
const updating = ref(false)

async function toggle(value: boolean) {
  updating.value = true
  try {
    await store.updateNote(props.noteId, { isPublic: value })
    message.success(value ? '已开启公开分享' : '已关闭公开分享，链接已失效')
  } catch (e) {
    message.error((e as Error).message)
  } finally {
    updating.value = false
  }
}

async function copy() {
  if (await copyText(link.value)) message.success('链接已复制')
  else message.warning('复制失败，请手动选择链接复制')
}
</script>

<template>
  <NPopover trigger="click" placement="bottom-end" :width="340">
    <template #trigger>
      <NButton
        size="small"
        :type="meta?.isPublic ? 'primary' : 'default'"
        :secondary="meta?.isPublic"
      >
        <template #icon>
          <NIcon><Globe v-if="meta?.isPublic" /><Share2 v-else /></NIcon>
        </template>
        <span v-if="!compact">{{ meta?.isPublic ? '已分享' : '分享' }}</span>
      </NButton>
    </template>
    <div class="share-panel">
      <div class="share-row">
        <div>
          <div class="share-title">公开分享</div>
          <div class="share-desc">拿到链接的任何人都可以查看（只读），链接永久有效</div>
        </div>
        <NSwitch :value="meta?.isPublic" :loading="updating" @update:value="toggle" />
      </div>
      <template v-if="meta?.isPublic">
        <NInputGroup>
          <NInput
            :value="link"
            readonly
            size="small"
            @focus="($event.target as HTMLInputElement).select()"
          />
          <NButton size="small" type="primary" @click="copy">
            <template #icon
              ><NIcon><Copy /></NIcon
            ></template>
            复制
          </NButton>
        </NInputGroup>
        <a class="share-open" :href="link" target="_blank" rel="noopener">在新窗口中打开 ↗</a>
      </template>
    </div>
  </NPopover>
</template>

<style scoped>
.share-panel {
  display: flex;
  flex-direction: column;
  gap: 12px;
  padding: 4px 2px;
}
.share-row {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 16px;
}
.share-title {
  font-weight: 600;
  margin-bottom: 2px;
}
.share-desc {
  font-size: 12px;
  color: var(--ul-text-2);
  line-height: 1.5;
}
.share-open {
  font-size: 12px;
  color: var(--ul-accent);
  text-decoration: none;
}
.share-open:hover {
  text-decoration: underline;
}
</style>
