<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import {
  NButton,
  NEmpty,
  NIcon,
  NInput,
  NInputGroup,
  NModal,
  NSelect,
  NSpin,
  useDialog,
  useMessage,
} from 'naive-ui'
import { Copy, Eye, EyeOff } from 'lucide-vue-next'
import { gitApi } from '@/api/git'
import type { AccessToken, GitInfo } from '@/types'
import { copyText } from '@/utils/clipboard'
import { formatDateTime, formatRelative } from '@/utils/format'

const show = defineModel<boolean>('show', { required: true })
const message = useMessage()
const dialog = useDialog()

const loading = ref(false)
const info = ref<GitInfo | null>(null)
const tokens = ref<AccessToken[]>([])
/** 显示完整令牌的行（默认遮住，避免旁人看到） */
const revealed = ref(new Set<number>())
function toggleReveal(id: number) {
  const next = new Set(revealed.value)
  if (!next.delete(id)) next.add(id)
  revealed.value = next
}
function masked(t: AccessToken) {
  return revealed.value.has(t.id) ? (t.token ?? '') : `ulp_${'•'.repeat(16)}${t.lastChars}`
}

const cloneUrl = computed(() => (info.value ? `${location.origin}${info.value.clonePath}` : ''))
const cloneCommand = computed(() => `git clone ${cloneUrl.value}`)

async function load() {
  loading.value = true
  try {
    const [i, t] = await Promise.all([gitApi.info(), gitApi.listTokens()])
    info.value = i
    tokens.value = t
  } catch (e) {
    message.error((e as Error).message)
  } finally {
    loading.value = false
  }
}

watch(show, (v) => {
  if (v) {
    revealed.value = new Set()
    newName.value = ''
    void load()
  }
})

// ---------- 新建令牌 ----------
const newName = ref('')
const expiry = ref<number>(0)
const expiryOptions = [
  { label: '永不过期', value: 0 },
  { label: '30 天', value: 30 },
  { label: '90 天', value: 90 },
  { label: '1 年', value: 365 },
]
const creating = ref(false)

async function createToken() {
  const name = newName.value.trim()
  if (!name) {
    message.warning('请给令牌起个名字，如「家里的电脑」')
    return
  }
  creating.value = true
  try {
    const token = await gitApi.createToken(name, expiry.value || null)
    newName.value = ''
    tokens.value = [token, ...tokens.value]
    // 默认遮住；顺便复制到剪贴板，复制失败时用户可以点「复制」按钮
    if (token.token && (await copyText(token.token))) message.success('令牌已生成并复制')
    else message.success('令牌已生成')
  } catch (e) {
    message.error((e as Error).message)
  } finally {
    creating.value = false
  }
}

function revoke(token: AccessToken) {
  dialog.warning({
    title: '吊销令牌',
    content: `吊销「${token.name}」后，使用它的设备将无法再 pull / push，需要换用新的令牌。`,
    positiveText: '吊销',
    negativeText: '取消',
    onPositiveClick: async () => {
      try {
        await gitApi.revokeToken(token.id)
        tokens.value = tokens.value.filter((t) => t.id !== token.id)
        message.success('已吊销')
      } catch (e) {
        message.error((e as Error).message)
      }
    },
  })
}

async function copy(text: string, what: string) {
  if (await copyText(text)) message.success(`${what}已复制`)
  else message.warning('复制失败，请手动选择后复制')
}

function selectAll(e: FocusEvent) {
  ;(e.target as HTMLInputElement).select()
}
</script>

<template>
  <NModal
    v-model:show="show"
    preset="card"
    title="Git 同步"
    style="width: min(560px, calc(100vw - 32px))"
    :bordered="false"
  >
    <NSpin :show="loading">
      <p class="hint">
        用 Git 把笔记克隆到本地，用任意编辑器修改后 push 回来，网页上的修改用 pull 拉取。
      </p>

      <section class="block">
        <div class="label">仓库地址</div>
        <NInputGroup>
          <NInput :value="cloneCommand" readonly @focus="selectAll" />
          <NButton type="primary" ghost @click="copy(cloneCommand, '命令')">
            <template #icon
              ><NIcon><Copy /></NIcon
            ></template>
            复制
          </NButton>
        </NInputGroup>
      </section>

      <section class="block">
        <div class="label">访问令牌</div>
        <div class="create-row">
          <NInput
            v-model:value="newName"
            placeholder="令牌名称"
            :maxlength="64"
            @keydown.enter="createToken"
          />
          <NSelect v-model:value="expiry" :options="expiryOptions" class="expiry" />
          <NButton type="primary" :loading="creating" @click="createToken">生成</NButton>
        </div>

        <NEmpty v-if="!tokens.length && !loading" size="small" description="还没有令牌" />
        <ul v-else class="tokens">
          <li v-for="t in tokens" :key="t.id" class="token">
            <div class="token-head">
              <div class="token-main">
                <div class="token-name">{{ t.name }}</div>
                <div class="token-meta">
                  创建于 {{ formatDateTime(t.createdAt).slice(0, 10) }} ·
                  {{
                    t.expiresAt ? `${formatDateTime(t.expiresAt).slice(0, 10)} 过期` : '永不过期'
                  }}
                  ·
                  {{ t.lastUsedAt ? `${formatRelative(t.lastUsedAt)}使用过` : '从未使用' }}
                </div>
              </div>
              <NButton size="small" type="error" quaternary @click="revoke(t)">吊销</NButton>
            </div>
            <NInputGroup v-if="t.token">
              <NInput :value="masked(t)" readonly size="small" class="mono" @focus="selectAll" />
              <NButton
                size="small"
                :aria-label="revealed.has(t.id) ? '隐藏' : '显示'"
                @click="toggleReveal(t.id)"
              >
                <template #icon
                  ><NIcon><EyeOff v-if="revealed.has(t.id)" /><Eye v-else /></NIcon
                ></template>
              </NButton>
              <NButton size="small" type="primary" ghost @click="copy(t.token, '令牌')">
                <template #icon
                  ><NIcon><Copy /></NIcon
                ></template>
                复制
              </NButton>
            </NInputGroup>
            <div v-else class="note">无法显示（服务器密钥已更换），需要查看时请重新生成</div>
          </li>
        </ul>
      </section>
    </NSpin>
  </NModal>
</template>

<style scoped>
.hint {
  margin: 0 0 16px;
  font-size: 13px;
  color: var(--ul-text-2);
  line-height: 1.6;
}
.block {
  margin-bottom: 18px;
}
.label {
  font-weight: 600;
  font-size: 13px;
  margin-bottom: 8px;
}
.note {
  margin: 6px 0;
  font-size: 12px;
  color: var(--ul-text-2);
  line-height: 1.6;
}
.mono :deep(input) {
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
}
.create-row {
  display: flex;
  gap: 8px;
  margin-bottom: 10px;
}
.expiry {
  width: 120px;
  flex-shrink: 0;
}
.tokens {
  list-style: none;
  margin: 0;
  padding: 0;
}
.token {
  padding: 10px 0;
  border-top: 1px solid var(--ul-border);
}
.token-head {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 6px;
}
.token-main {
  flex: 1;
  min-width: 0;
}
.token-name {
  font-size: 14px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.token-meta {
  font-size: 12px;
  color: var(--ul-text-2);
}
@media (max-width: 480px) {
  .create-row {
    flex-wrap: wrap;
  }
  .expiry {
    width: auto;
    flex: 1;
  }
}
</style>
