<script setup lang="ts">
import { computed, onBeforeUnmount, ref } from 'vue'
import { NButton, useMessage } from 'naive-ui'
import { authApi } from '@/api/auth'
import { USE_MOCK } from '@/api/http'
import { MOCK_CODE } from '@/api/mock/constants'
import type { EmailCodePurpose } from '@/types'
import { EMAIL_RE } from '@/utils/format'

const props = defineProps<{ email: string; purpose: EmailCodePurpose }>()
const emit = defineEmits<{ sent: [] }>()
const message = useMessage()

const countdown = ref(0)
const sending = ref(false)
let timer: ReturnType<typeof setInterval> | undefined

const label = computed(() => (countdown.value > 0 ? `${countdown.value} 秒后重发` : '获取验证码'))

async function send() {
  if (!EMAIL_RE.test(props.email.trim())) {
    message.warning('请先填写正确的邮箱')
    return
  }
  sending.value = true
  try {
    await authApi.sendEmailCode(props.email.trim(), props.purpose)
    message.success(USE_MOCK ? `演示模式：验证码为 ${MOCK_CODE}` : '验证码已发送，请查收邮件', {
      duration: USE_MOCK ? 6000 : 3000,
    })
    countdown.value = 60
    clearInterval(timer)
    timer = setInterval(() => {
      if (--countdown.value <= 0) clearInterval(timer)
    }, 1000)
    emit('sent')
  } catch (e) {
    message.error((e as Error).message)
  } finally {
    sending.value = false
  }
}

onBeforeUnmount(() => clearInterval(timer))
</script>

<template>
  <NButton :disabled="countdown > 0" :loading="sending" class="send-code" @click="send">{{
    label
  }}</NButton>
</template>

<style scoped>
.send-code {
  min-width: 112px;
}
</style>
