<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import {
  NButton,
  NForm,
  NFormItem,
  NInput,
  NModal,
  useMessage,
  type FormInst,
  type FormRules,
} from 'naive-ui'
import { authApi } from '@/api/auth'
import { useAuthStore } from '@/stores/auth'

const show = defineModel<boolean>('show', { required: true })
const auth = useAuthStore()
const message = useMessage()

const hasPassword = computed(() => !!auth.user?.hasPassword)
const form = ref({ oldPassword: '', newPassword: '', confirm: '' })
const formRef = ref<FormInst>()
const submitting = ref(false)

watch(show, (v) => {
  if (v) form.value = { oldPassword: '', newPassword: '', confirm: '' }
})

const rules: FormRules = {
  oldPassword: { required: true, message: '请输入原密码', trigger: 'blur' },
  newPassword: [
    { required: true, message: '请输入新密码', trigger: 'blur' },
    { min: 8, message: '密码至少 8 位', trigger: 'blur' },
  ],
  confirm: {
    trigger: ['blur', 'input'],
    validator: (_r, v: string) =>
      v === form.value.newPassword ? true : new Error('两次输入的密码不一致'),
  },
}

async function submit() {
  try {
    await formRef.value?.validate()
  } catch {
    return
  }
  submitting.value = true
  try {
    const user = await authApi.changePassword(
      form.value.newPassword,
      hasPassword.value ? form.value.oldPassword : undefined,
    )
    auth.setUser(user)
    message.success(
      hasPassword.value
        ? '密码已修改，其他设备需要重新登录'
        : '密码设置成功，之后可以用邮箱 + 密码登录',
    )
    show.value = false
  } catch (e) {
    message.error((e as Error).message)
  } finally {
    submitting.value = false
  }
}
</script>

<template>
  <NModal
    v-model:show="show"
    preset="card"
    :title="hasPassword ? '修改密码' : '设置密码'"
    style="width: min(420px, calc(100vw - 32px))"
    :bordered="false"
  >
    <p v-if="!hasPassword" class="hint">
      你目前通过邮箱验证码登录。设置密码后，也可以用邮箱 + 密码登录。
    </p>
    <NForm
      ref="formRef"
      :model="form"
      :rules="rules"
      label-placement="top"
      @submit.prevent="submit"
    >
      <NFormItem v-if="hasPassword" label="原密码" path="oldPassword">
        <NInput v-model:value="form.oldPassword" type="password" show-password-on="click" />
      </NFormItem>
      <NFormItem label="新密码" path="newPassword">
        <NInput
          v-model:value="form.newPassword"
          type="password"
          show-password-on="click"
          placeholder="至少 8 位"
        />
      </NFormItem>
      <NFormItem label="确认新密码" path="confirm">
        <NInput v-model:value="form.confirm" type="password" show-password-on="click" />
      </NFormItem>
      <NButton type="primary" block attr-type="submit" :loading="submitting">确定</NButton>
    </NForm>
  </NModal>
</template>

<style scoped>
.hint {
  margin: 0 0 16px;
  font-size: 13px;
  color: var(--ul-text-2);
  line-height: 1.6;
}
</style>
